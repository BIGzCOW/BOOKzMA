import sqlite3
from collections import defaultdict

from BOOKzMA import keyboards, texts
from BOOKzMA.handlers.catalog import _book_title
from BOOKzMA.services.books import normalize_author, normalize_title, progress_percent
from BOOKzMA.services.book_catalog_sync import (
    _read_source_batch,
    clean_caption,
    seconds_until_next_sync,
)
from BOOKzMA.utils import parse_positive_int


def test_book_text_normalization_and_limits():
    assert normalize_title("  سمفونی   مردگان  ") == "سمفونی مردگان"
    assert normalize_author("  عباس   معروفی ") == "عباس معروفی"
    assert normalize_title("   ") is None
    assert normalize_author("x" * 201) is None


def test_page_number_parsing_accepts_persian_digits_and_bounds_values():
    assert parse_positive_int("۱۲۳", 100_000) == 123
    assert parse_positive_int("٠٧", 100_000) == 7
    assert parse_positive_int("0", 100_000) is None
    assert parse_positive_int("12.5", 100_000) is None
    assert parse_positive_int("100001", 100_000) is None


def test_progress_percent_is_bounded():
    assert progress_percent(0, 320) == 0
    assert progress_percent(80, 320) == 25
    assert progress_percent(320, 320) == 100
    assert progress_percent(400, 320) == 100
    assert progress_percent(1, 0) == 0
    assert progress_percent(199, 200) == 99
    assert progress_percent(99_999, 100_000) == 99
    assert progress_percent(-1, 100) == 0


def test_catalog_caption_removes_channel_signature_and_limits_preview():
    _display, preview, searchable = clean_caption(
        "عنوان کتاب @BOOKzMA\nاین توضیح t.me/BOOKzMA ادامه دارد.", "BOOKzMA"
    )

    assert "BOOKzMA" not in searchable
    assert "t.me" not in searchable
    assert searchable.startswith("عنوان کتاب")
    assert len(preview) <= 221


def test_catalog_batch_reads_only_main_channel_metadata(tmp_path):
    database_path = tmp_path / "channel_data.db"
    connection = sqlite3.connect(database_path)
    connection.executescript(
        """
        CREATE TABLE channels (id INTEGER, username TEXT, is_main INTEGER);
        CREATE TABLE messages (
            id INTEGER, message_id INTEGER, channel_id INTEGER, file_name TEXT,
            file_size INTEGER, mime_type TEXT, media_type TEXT, date TEXT,
            text TEXT, in_main INTEGER, is_duplicate INTEGER, raw_data TEXT
        );
        INSERT INTO channels VALUES (24, 'BOOKzMA', 1);
        INSERT INTO channels VALUES (25, 'other', 0);
        INSERT INTO messages VALUES
            (10, 100, 24, 'Book.pdf', 1000, 'application/pdf', 'Document',
             '2026-11-03', 'A useful caption @BOOKzMA', 1, 0, 'PRIVATE_RAW');
        INSERT INTO messages VALUES
            (11, 101, 25, 'Other.pdf', 2000, 'application/pdf', 'Document',
             '2026-11-03', 'other channel', 0, 0, 'PRIVATE_RAW');
        INSERT INTO messages VALUES
            (12, 102, 24, 'Rejected.pdf', 3000, 'application/pdf', 'Document',
             '2026-11-03', 'duplicate', 1, 1, 'PRIVATE_RAW');
        """
    )
    connection.close()

    batch = _read_source_batch(database_path, "BOOKzMA", 0, 100)

    assert batch.source_rows == 2
    assert batch.next_source_row_id == 12
    assert len(batch.entries) == 1
    assert batch.entries[0]["message_id"] == 100
    assert batch.entries[0]["caption_search"] == "a useful caption"
    assert "raw_data" not in batch.entries[0]


def test_catalog_sync_waits_until_the_next_configured_utc_hour():
    from datetime import datetime, timezone

    before = datetime(2026, 11, 7, 2, 0, tzinfo=timezone.utc)
    at_hour = datetime(2026, 11, 7, 3, 0, tzinfo=timezone.utc)
    after = datetime(2026, 11, 7, 4, 0, tzinfo=timezone.utc)

    assert seconds_until_next_sync(before, 3) == 3600
    assert seconds_until_next_sync(at_hour, 3) == 24 * 3600
    assert seconds_until_next_sync(after, 3) == 23 * 3600


def test_book_text_escapes_user_values_and_callbacks_stay_bounded():
    detail = texts.book_detail("<script>", "A & B", 10, 100, "reading")

    assert "<script>" not in detail
    assert "&lt;script&gt;" in detail
    assert "A &amp; B" in detail

    markup = keyboards.book_detail_kb(2_147_483_647, "reading")
    callback_values = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]
    assert callback_values
    assert all(len(value.encode()) <= 64 for value in callback_values)


def test_catalog_channel_handle_is_removed_from_filename_and_library_title():
    file_name = "@Blue_library  درود بر کاتالونیا.pdf"

    result = texts.catalog_result(file_name, None, 682_629, "application/pdf")
    title = _book_title(file_name, None, "Document", 17)

    assert "@Blue_library" not in result
    assert "درود بر کاتالونیا.pdf" in result
    assert title == "درود بر کاتالونیا"


def test_embedded_channel_handle_keeps_file_extension_and_is_hidden_from_search_title():
    file_name = "برونرپوست@EppiccNURSE.pdf"

    assert texts.catalog_result(file_name, None, 1024, "application/pdf").startswith(
        "📚 <b>برونرپوست.pdf</b>"
    )
    assert _book_title(file_name, None, "Document", 289_334) == "برونرپوست"
    assert "@EppiccNURSE" not in texts.book_detail(file_name, None, 0, 100, "reading")
    assert "@EppiccNURSE" not in texts.pages_logged(
        file_name, 10, 10, 100, False, "استریک ثبت شد"
    )


def test_catalog_file_size_is_rounded_to_one_decimal_place():
    result = texts.catalog_result("کتاب.pdf", None, 21_999_999, "application/pdf")

    assert "حجم: ۲۱ مگابایت" in result


def test_catalog_mime_type_is_escaped_in_html_output():
    result = texts.catalog_result("کتاب.pdf", None, None, "application/<b>spoof</b>")

    assert "فرمت: &lt;b&gt;spoof&lt;/b&gt;" in result
    assert "فرمت: <b>spoof</b>" not in result


def test_admin_dashboard_shows_book_archive_and_page_session_metrics():
    stats = defaultdict(
        int,
        {
            "archived_books": 4,
            "books_added_7d": 3,
            "books_archived_7d": 2,
            "books_restored_7d": 1,
            "catalog_searches_7d": 15,
            "catalog_searches_30d": 42,
            "catalog_result_pages_7d": 20,
            "catalog_results_shown_7d": 86,
            "catalog_empty_searches_7d": 3,
            "catalog_books_added_7d": 5,
            "catalog_downloads_succeeded_7d": 7,
            "catalog_downloads_failed_7d": 1,
            "page_sessions_7d": 8,
            "pages_7d": 120,
            "page_counts_set_7d": 2,
            "support_tickets_open": 5,
            "support_tickets_7d": 3,
            "support_messages_7d": 9,
            "support_replies_7d": 8,
            "support_blocked_users": 1,
        },
    )

    report = texts.admin_dashboard(stats, [])

    assert "کتاب‌های آرشیوشده: ۴" in report
    assert "افزوده/آرشیو/بازگردانی در ۷ روز: ۳ / ۲ / ۱" in report
    assert "جستجو ۷/۳۰ روز: ۱۵ / ۴۲" in report
    assert "صفحه/نتیجه/بی‌نتیجهٔ ۷روزه: ۲۰ / ۸۶ / ۳" in report
    assert "ارسال فایل کاتالوگ ۷ روزه · موفق/ناموفق: ۷ / ۱" in report
    assert "نشست/صفحهٔ مطالعه در ۷ روز: ۸ / ۱۲۰" in report
    assert "تنظیم تعداد صفحات در ۷ روز: ۲" in report
    assert "تیکت باز/جدید: ۵ / ۳" in report
    assert "پیام/پاسخ ۷روزه: ۹ / ۸" in report
    assert "مسدود: ۱" in report


def test_catalog_book_details_offer_download_and_channel_link():
    markup = keyboards.book_detail_with_pages_kb(
        1,
        "reading",
        has_page_count=True,
        catalog_message_id=358_266,
        catalog_url="https://t.me/BOOKzMA/358266",
    )
    buttons = [button for row in markup.inline_keyboard for button in row]

    assert any(button.callback_data == "catalog:download:358266" for button in buttons)
    link_button = next(button for button in buttons if button.url is not None)
    assert link_button.url == "https://t.me/BOOKzMA/358266"
    assert link_button.style is None
    assert "style" not in link_button.model_dump(exclude_none=True)


def test_archived_shelf_keyboard_has_separate_navigation_and_pagination():
    markup = keyboards.bookshelf_kb(
        [(8, "Old@EppiccNURSE title", "archived")],
        page=1,
        has_previous=True,
        has_next=True,
        can_add=False,
        archived=True,
    )
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]

    assert "books:archive:p:0" in callbacks
    assert "books:archive:p:2" in callbacks
    assert "books" in callbacks
    assert "books:p:0" not in callbacks
    labels = [button.text for row in markup.inline_keyboard for button in row]
    assert all("@EppiccNURSE" not in label for label in labels)


def test_archived_book_detail_offers_restore_instead_of_archive():
    markup = keyboards.book_detail_with_pages_kb(
        42, "archived", has_page_count=True
    )
    callbacks = [
        button.callback_data
        for row in markup.inline_keyboard
        for button in row
        if button.callback_data is not None
    ]
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert "book:restore:42" in callbacks
    assert "book:archive:42" not in callbacks
    assert any("بازگردانی" in label for label in labels)
    assert markup.inline_keyboard[0][0].style == "success"


def test_finished_book_detail_offers_archive_alongside_catalog_actions():
    markup = keyboards.book_detail_with_pages_kb(
        42,
        "finished",
        has_page_count=True,
        catalog_message_id=358_266,
        catalog_url="https://t.me/BOOKzMA/358266",
    )
    buttons = [button for row in markup.inline_keyboard for button in row]
    callbacks = {button.callback_data for button in buttons if button.callback_data}
    labels = [button.text for button in buttons]

    assert "catalog:download:358266" in callbacks
    assert "book:archive:42" in callbacks
    assert not any(callback in callbacks for callback in ("book:log:42", "book:set_pages:42"))
    assert any("آرشیو کتاب" in label for label in labels)


def test_book_detail_and_note_page_offer_private_note_actions():
    detail = keyboards.book_detail_with_pages_kb(
        42, "archived", has_page_count=True, has_note=True
    )
    note = keyboards.book_note_kb(42, has_note=True)
    detail_callbacks = {
        button.callback_data for row in detail.inline_keyboard for button in row
    }
    note_callbacks = {
        button.callback_data for row in note.inline_keyboard for button in row
    }

    assert "book:note:42" in detail_callbacks
    assert "book:note:edit:42" in note_callbacks
    assert "book:note:clear:42" in note_callbacks
    assert "book:open:42" in note_callbacks


def test_book_note_display_escapes_title_and_user_text():
    rendered = texts.book_note("<Book>", "<b>private</b> & personal")

    assert "&lt;Book&gt;" in rendered
    assert "&lt;b&gt;private&lt;/b&gt; &amp; personal" in rendered


def test_inline_button_styles_are_consistent_by_action():
    home = keyboards.home_kb(read_today=False)
    home_buttons = [button for row in home.inline_keyboard for button in row]
    styles = {button.callback_data: button.style for button in home_buttons}

    assert styles["read"] == "success"
    assert list(styles) == ["read"]

    detail = keyboards.book_detail_kb(7, "reading")
    detail_buttons = [button for row in detail.inline_keyboard for button in row]
    detail_styles = {button.callback_data: button.style for button in detail_buttons}
    assert detail_styles["book:log:7"] == "success"
    assert detail_styles["book:archive:7"] == "danger"

    archived = keyboards.book_detail_kb(7, "archived")
    restore = archived.inline_keyboard[0][0]
    assert restore.callback_data == "book:restore:7"
    assert restore.style == "success"


def test_streak_leaderboard_shows_only_top_25_and_escapes_names():
    scores = [
        (30 - index, "<reader>" if index == 0 else f"reader {index}")
        for index in range(30)
    ]

    leaderboard = texts.streak_leaderboard(scores)

    assert leaderboard.count("\n") == 25
    assert "&lt;reader&gt;" in leaderboard
    assert "reader 24" in leaderboard
    assert "reader 25" not in leaderboard


def test_leaderboard_toggle_colors_follow_the_action():
    opted_in = keyboards.profile_kb(opt_out=False).inline_keyboard[0][0]
    opted_out = keyboards.profile_kb(opt_out=True).inline_keyboard[0][0]

    assert opted_in.style == "danger"
    assert opted_out.style == "success"


def test_library_label_uses_requested_spelling():
    assert "کتابخانهٔ" not in keyboards.menu_kb().keyboard[1][0].text
    assert "کتابخانهٔ" not in texts.bookshelf(0, 0)


def test_reply_menus_group_secondary_destinations():
    main_labels = [button.text for row in keyboards.menu_kb().keyboard for button in row]
    profile_labels = [
        button.text for row in keyboards.profile_menu_kb(opt_out=False).keyboard for button in row
    ]
    settings_labels = [
        button.text for row in keyboards.profile_settings_menu_kb().keyboard for button in row
    ]
    more_labels = [
        button.text for row in keyboards.more_menu_kb(is_admin=True).keyboard for button in row
    ]

    assert main_labels == [
        "🏠 خانه",
        "👤 پروفایل",
        "📚 کتابخانه من",
        "🪥 مسباک",
        "🤝 رفیق مطالعه",
        "🧭 بیشتر",
    ]
    assert "🌍 منطقه زمانی" not in main_labels
    assert "🌍 منطقه زمانی" in settings_labels
    assert "⏰ یادآورها" in settings_labels
    assert "🏅 لیدربورد" in more_labels
    assert "⚙️ مدیریت ربات" in more_labels
    assert "➖ خروج از لیدربورد" in profile_labels


def test_bookshelf_summary_lists_started_books_and_all_categories():
    screen = texts.bookshelf(
        2,
        5,
        finished=1,
        planned=1,
        unstarted=1,
        archived_count=2,
        total_count=7,
        reading_titles=("Book A", "<Book B>"),
    )

    assert "در حال مطالعه (حداقل ۱ صفحه): ۲" in screen
    assert "• Book A" in screen
    assert "• &lt;Book B&gt;" in screen
    assert "تمام‌شده: ۱" in screen
    assert "برنامه‌ریزی‌شده: ۱" in screen
    assert "شروع‌نشده: ۱" in screen
    assert "آرشیوشده: ۲" in screen
    assert "کل کتاب‌ها: ۷" in screen


def test_archived_bookshelf_shows_archived_and_total_counts():
    screen = texts.bookshelf(
        0,
        3,
        archived=True,
        archived_count=3,
        total_count=8,
    )

    assert "کتاب‌های آرشیوشده: ۳" in screen
    assert "کل کتاب‌ها: ۸" in screen
