from BOOKzMA import keyboards, texts
from BOOKzMA.services.books import normalize_author, normalize_title, progress_percent
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
