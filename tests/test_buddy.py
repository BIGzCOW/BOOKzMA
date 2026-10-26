from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

from BOOKzMA import keyboards
from BOOKzMA import texts
from BOOKzMA.handlers.buddy import _callback_pair_id
from BOOKzMA.services.buddy_invites import create_invite_token, invite_token_hash
from BOOKzMA.services.buddy_nudges import classify_nudge_targets


def test_buddy_name_escapes_html_and_newlines():
    assert texts.buddy_name("<b>علی</b>\nروزخوان") == "&lt;b&gt;علی&lt;/b&gt; روزخوان"
    assert texts.buddy_name(None) == "کتاب‌خوان"
    assert texts.buddy_name("   ") == "کتاب‌خوان"


def test_buddy_screen_shows_status_and_streak():
    screen = texts.buddy_screen("علی", 12, True)
    assert "علی" in screen
    assert "۱۲" in screen
    assert "ثبت کرده" in screen
    waiting = texts.buddy_screen("علی", 0, False)
    assert "هنوز امروز نخونده" in waiting


def test_buddy_overview_escapes_names_and_shows_queue_state():
    overview = texts.buddy_overview(["<b>علی</b>", "سارا"], queued=True)

    assert "&lt;b&gt;علی&lt;/b&gt;" in overview
    assert "سارا" in overview
    assert "صف پیدا کردن رفیق ناشناس" in overview


def test_pair_callback_id_requires_a_bounded_positive_database_id():
    assert _callback_pair_id("buddy:open:123", "buddy:open:") == 123
    assert _callback_pair_id("buddy:open:0", "buddy:open:") is None
    assert _callback_pair_id("buddy:open:-1", "buddy:open:") is None
    assert _callback_pair_id("buddy:open:2147483648", "buddy:open:") is None
    assert _callback_pair_id("buddy:open:1" * 20, "buddy:open:") is None


def test_nudge_classification_skips_read_and_already_nudged_friends():
    nudge_day = date(2026, 10, 26)
    read_friend = SimpleNamespace(id=1)
    capped_friend = SimpleNamespace(id=2)
    eligible_friend = SimpleNamespace(id=3)
    buddies = [
        (SimpleNamespace(last_nudge_on=None), read_friend),
        (SimpleNamespace(last_nudge_on=nudge_day), capped_friend),
        (SimpleNamespace(last_nudge_on=None), eligible_friend),
    ]

    targets, already_read, already_nudged = classify_nudge_targets(
        buddies, {read_friend.id}, nudge_day
    )

    assert targets == [buddies[2]]
    assert already_read == 1
    assert already_nudged == 1


def test_nudge_buttons_and_summary_explain_skipped_friends():
    markup = keyboards.buddy_list_kb([(12, "سارا")], queued=False)
    data = [button.callback_data for row in markup.inline_keyboard for button in row]
    prompt = keyboards.buddy_nudge_prompt_kb()
    prompt_data = [button.callback_data for row in prompt.inline_keyboard for button in row]

    assert "buddy:nudge:all" in data
    assert "buddy:nudge:all" in prompt_data
    assert "buddy:nudge:dismiss" in prompt_data
    summary = texts.buddy_nudge_summary(1, 2, 1, 0)
    assert "۱ نفر تلنگر رفت" in summary
    assert "۲ نفر امروز خوانده بودند" in summary
    assert "۱ نفر امروز قبلاً تلنگر زده بودی" in summary


def test_invite_payload_is_valid_and_stores_only_a_hash():
    payload, stored_hash = create_invite_token()

    assert len(payload.encode()) <= 64
    assert invite_token_hash(payload) == stored_hash
    assert payload.startswith("buddy_")
    assert payload not in stored_hash


def test_invite_payload_rejects_invalid_and_overlong_values():
    assert invite_token_hash(None) is None
    assert invite_token_hash("buddy_short") is None
    assert invite_token_hash("buddy_" + "a" * 65) is None


def test_buddy_invite_share_text_encodes_spaces_without_plus_signs():
    markup = keyboards.buddy_invite_kb("https://t.me/bookzma_bot?start=buddy_token")
    share_url = markup.inline_keyboard[0][0].url
    query = urlsplit(share_url).query

    assert "+" not in query
    assert parse_qs(query)["text"] == ["بیا رفیق مطالعه‌ام شو 🤝"]
