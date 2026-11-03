from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from BOOKzMA import keyboards, texts
from BOOKzMA.services.mesbak import (
    completed_days,
    current_streak,
    default_schedule,
    effective_goal,
    longest_streak,
    is_legacy_default_schedule,
    next_occurrence,
    reminder_due,
    validate_daily_goal,
    validate_schedule,
)
from BOOKzMA.services.mesbak_social import (
    challenge_failed,
    challenge_end_date,
    challenge_progress,
    invite_token_hash,
    new_invite_token,
)

TODAY = date(2026, 10, 26)


@pytest.mark.parametrize("goal", [1, 2, 3, 4, 5])
def test_daily_goal_accepts_one_through_five(goal):
    assert validate_daily_goal(goal) == goal


@pytest.mark.parametrize("goal", [0, 6, -1, True, "2"])
def test_daily_goal_rejects_out_of_range_values(goal):
    with pytest.raises(ValueError):
        validate_daily_goal(goal)


def test_next_occurrence_skips_completed_slots_and_stops_at_goal():
    assert next_occurrence([], 1) == 1
    assert next_occurrence([1, 3], 5) == 2
    assert next_occurrence([1, 2, 3, 4, 5], 5) is None


def test_schedule_requires_one_unique_time_per_occurrence():
    assert validate_schedule(2, [time(6, 30), time(13)]) == [time(6, 30), time(13)]
    with pytest.raises(ValueError):
        validate_schedule(2, [time(6, 30)])
    with pytest.raises(ValueError):
        validate_schedule(2, [time(6, 30), time(6, 30)])


@pytest.mark.parametrize(
    ("goal", "expected"),
    [
        (1, [time(22)]),
        (2, [time(6, 30), time(22)]),
        (3, [time(6, 30), time(13), time(22)]),
        (4, [time(6, 30), time(13), time(19), time(22)]),
        (5, [time(6, 30), time(13), time(16), time(19), time(22)]),
    ],
)
def test_default_schedule_matches_local_default_reminder_pattern(goal, expected):
    assert default_schedule(goal) == expected


def test_legacy_default_schedule_is_detected_without_reclassifying_custom_times():
    assert is_legacy_default_schedule(1, [time(6, 30)])
    assert not is_legacy_default_schedule(1, [time(7, 30)])


def test_goal_change_takes_effect_on_its_local_effective_date():
    tomorrow = TODAY + timedelta(days=1)
    assert effective_goal(2, 4, tomorrow, TODAY) == 2
    assert effective_goal(2, 4, tomorrow, tomorrow) == 4
    assert effective_goal(2, 4, TODAY, TODAY) == 4


def test_only_days_that_reach_their_snapshot_goal_are_completed():
    records = [
        (TODAY, 1, 1),
        (TODAY - timedelta(days=1), 2, 3),
        (TODAY - timedelta(days=2), 5, 5),
        (TODAY - timedelta(days=3), 0, 0),
    ]

    assert completed_days(records) == {TODAY, TODAY - timedelta(days=2)}


def test_current_streak_includes_yesterday_until_today_ends():
    days = {TODAY - timedelta(days=1), TODAY - timedelta(days=2)}

    assert current_streak(days, TODAY) == 2
    assert current_streak(days | {TODAY}, TODAY) == 3


def test_missed_day_breaks_current_streak():
    assert current_streak({TODAY - timedelta(days=2), TODAY - timedelta(days=3)}, TODAY) == 0


def test_longest_streak_is_derived_from_completed_days():
    days = {TODAY, TODAY - timedelta(days=1), TODAY - timedelta(days=4)}

    assert longest_streak(days) == 2
    assert longest_streak([]) == 0


def test_challenge_duration_and_consecutive_progress():
    assert challenge_end_date(TODAY, 7) == TODAY + timedelta(days=6)
    with pytest.raises(ValueError):
        challenge_end_date(TODAY, 14)
    assert (
        challenge_progress(
            {TODAY, TODAY + timedelta(days=1)}, TODAY, TODAY + timedelta(days=2)
        )
        == 2
    )
    assert challenge_progress({TODAY + timedelta(days=1)}, TODAY, TODAY + timedelta(days=2)) == 0


def test_challenge_fails_after_a_closed_day_is_missed_but_not_during_today():
    yesterday = TODAY - timedelta(days=1)
    assert not challenge_failed({TODAY}, TODAY, TODAY + timedelta(days=6), TODAY)
    assert challenge_failed(
        {TODAY, TODAY + timedelta(days=2)}, TODAY, TODAY + timedelta(days=6),
        TODAY + timedelta(days=3),
    )
    assert not challenge_failed(
        {TODAY, yesterday}, yesterday, yesterday + timedelta(days=6), TODAY
    )


def test_mesbak_invite_token_is_validated_and_hashed():
    token = new_invite_token()

    assert invite_token_hash(token) is not None
    assert invite_token_hash(token) == invite_token_hash(token)
    assert invite_token_hash("../../bad") is None


def test_mesbak_screen_shows_independent_badges():
    screen = texts.mesbak_screen(1, 1, 7, 7, ["06:30"], None, None, ["streak_7"])

    assert "🏅 دستاوردها: ۷ روز" in screen


def test_mesbak_league_shows_only_top_25():
    rows = [(user_id, f"member {user_id}", 30 - user_id) for user_id in range(30)]

    league = texts.mesbak_league(rows, opted_in=True)

    assert league.count("\n") == 25
    assert "member 24" in league
    assert "member 25" not in league


def test_mesbak_buddy_button_labels_are_bounded_and_single_line():
    keyboard = keyboards.mesbak_buddy_list_kb([(1, "نام\n" + "x" * 100)])
    buddy_button = keyboard.inline_keyboard[1][0]

    assert "\n" not in buddy_button.text
    assert len(buddy_button.text) <= 64
    assert buddy_button.callback_data == "mesbak:buddy:open:1"


def _kb_callbacks(kb) -> list[str]:
    return [button.callback_data for row in kb.inline_keyboard for button in row]


def test_mesbak_buddy_screen_offers_anonymous_match_and_queue_cancel():
    empty = keyboards.mesbak_buddy_list_kb([])
    assert empty.inline_keyboard[0][0].callback_data == "mesbak:buddy:random:join"
    assert "mesbak:buddy:invite" in _kb_callbacks(empty)
    assert "mesbak:buddy:nudge:all" not in _kb_callbacks(empty)

    queued = keyboards.mesbak_buddy_list_kb([], queued=True)
    assert queued.inline_keyboard[0][0].callback_data == "mesbak:buddy:random:leave"
    queued_callbacks = _kb_callbacks(queued)
    assert "mesbak:buddy:invite" in queued_callbacks
    assert "mesbak:buddy:random:join" not in queued_callbacks
    assert "رفیق ناشناس" in texts.mesbak_buddies([], queued=True)

    # با چند رفیق فعال هم دکمهٔ ناشناس و لینک در دسترس می‌ماند + تلنگر گروهی
    with_buddies = keyboards.mesbak_buddy_list_kb([(1, "رفیق یک"), (2, "رفیق دو")])
    buddy_callbacks = _kb_callbacks(with_buddies)
    assert with_buddies.inline_keyboard[0][0].callback_data == "mesbak:buddy:nudge:all"
    assert buddy_callbacks.count("mesbak:buddy:open:1") == 1
    assert buddy_callbacks.count("mesbak:buddy:open:2") == 1
    assert "mesbak:buddy:random:join" in buddy_callbacks
    assert "mesbak:buddy:invite" in buddy_callbacks

    pair_kb = keyboards.mesbak_buddy_pair_kb(1)
    assert [button.callback_data for button in pair_kb.inline_keyboard[0]] == [
        "mesbak:buddy:nudge:1"
    ]
    assert pair_kb.inline_keyboard[1][0].callback_data == "mesbak:buddy:end:1"
    assert "پایان رفاقت" in pair_kb.inline_keyboard[1][0].text
    assert "پایان رفاقت 1" not in pair_kb.inline_keyboard[1][0].text
    assert "رفاقت مسباک تمام شد" in texts.MESBAK_BUDDY_ENDED


def test_mesbak_buddy_nudge_summary_matches_library_buddy_style():
    empty = texts.mesbak_buddy_nudge_summary(0, 0, 0, 0)
    assert empty == "امروز موردی برای تلنگر نبود."
    summary = texts.mesbak_buddy_nudge_summary(2, 1, 1, 0)
    assert "۲ نفر" in summary
    assert "کامل کرده بودند" in summary
    assert "قبلاً تلنگر" in summary


def test_mesbak_goal_keyboard_has_valid_rows_and_callbacks():
    keyboard = keyboards.mesbak_goal_kb()

    assert len(keyboard.inline_keyboard) == 2
    assert [button.callback_data for button in keyboard.inline_keyboard[0]] == [
        f"mesbak:goal:{goal}" for goal in range(1, 6)
    ]
    assert keyboard.inline_keyboard[1][0].callback_data == "mesbak:open"


def test_league_toggle_button_color_matches_action():
    joining = keyboards.mesbak_league_kb(opted_in=False).inline_keyboard[0][0]
    leaving = keyboards.mesbak_league_kb(opted_in=True).inline_keyboard[0][0]

    assert joining.style == "success"
    assert leaving.style == "danger"


def test_reminder_due_respects_late_window_retry_and_daily_dedup():
    now = datetime(2026, 10, 26, 6, 40, tzinfo=ZoneInfo("Asia/Tehran"))

    assert reminder_due(now, time(6, 30), None, 0, None)
    assert not reminder_due(now, time(6, 29), TODAY, 0, None)
    assert not reminder_due(now, time(6, 0), None, 0, None)
    assert not reminder_due(now, time(6, 30), None, 3, None)
    assert not reminder_due(now, time(6, 30), None, 1, now + timedelta(minutes=1))


def test_nonexistent_dst_wall_time_is_not_sent_late():
    now = datetime(2026, 3, 8, 3, 5, tzinfo=ZoneInfo("America/New_York"))

    assert not reminder_due(now, time(2, 30), None, 0, None)


def test_ambiguous_dst_reminder_is_suppressed_after_first_fold_send():
    first_fold = datetime(
        2026, 11, 1, 1, 30, tzinfo=ZoneInfo("America/New_York"), fold=0
    )
    second_fold = first_fold.replace(fold=1)

    assert reminder_due(first_fold, time(1, 30), None, 0, None)
    assert not reminder_due(second_fold, time(1, 30), first_fold.date(), 1, None)

def test_mesbak_buddy_nudge_all_targets_only_incomplete_buddies(monkeypatch):
    import asyncio
    from datetime import timezone
    from types import SimpleNamespace

    from aiogram.types import Chat, Message as TgMessage

    from BOOKzMA.handlers import mesbak_social

    async def run_test():
        pairs = [SimpleNamespace(id=11), SimpleNamespace(id=22), SimpleNamespace(id=33)]
        buddies = [
            SimpleNamespace(id=101, timezone="Asia/Tehran", display_name="کامل"),
            SimpleNamespace(id=102, timezone="Asia/Tehran", display_name="ناقص"),
            SimpleNamespace(id=103, timezone="Asia/Tehran", display_name="تلنگرخورده"),
        ]
        answered = []
        answered_message = []

        async def active_user(_session, _tg):
            me = SimpleNamespace(id=1, display_name="من", timezone="Asia/Tehran")
            return me, date(2026, 10, 26)

        async def buddy_users(_session, _user_id):
            return list(zip(pairs, buddies))

        async def completed_on_days(_session, user_days):
            return {101}

        async def claim(_session, _user_id, pair_id, _today):
            if pair_id == 22:
                return "ok", 102, "random"
            return "limit", 103, "random"

        class FakeBot:
            def __init__(self):
                self.sent_to = []
                self.methods = []

            async def __call__(self, method):
                self.methods.append(method)

            async def send_message(self, chat_id, text, **kwargs):
                self.sent_to.append((chat_id, text))

        fake_bot = FakeBot()
        monkeypatch.setattr(mesbak_social, "_active_user", active_user)
        monkeypatch.setattr(mesbak_social.mesbak_repo, "buddy_users", buddy_users)
        monkeypatch.setattr(
            mesbak_social.mesbak_repo, "users_completed_on_days", completed_on_days
        )
        monkeypatch.setattr(mesbak_social.mesbak_repo, "claim_buddy_nudge", claim)

        async def commit():
            return None

        async def answer(text=None, show_alert=False):
            answered.append(text)

        chat = Chat(id=1, type="private")

        def make_fake_message(sink):
            class FakeMessage(TgMessage):
                async def answer(self, text, **kwargs):
                    sink.append(text)

            return FakeMessage(
                message_id=1, date=datetime.now(tz=timezone.utc), chat=chat
            )

        session = SimpleNamespace(commit=commit)
        callback = SimpleNamespace(
            from_user=SimpleNamespace(id=1, username="u", full_name="من"),
            data="mesbak:buddy:nudge:all",
            answer=answer,
            message=make_fake_message(answered_message),
        )
        await mesbak_social.on_buddy_nudge_all(callback, session, fake_bot)

        assert [chat_id for chat_id, _text in fake_bot.sent_to] == [102]
        assert "من" in fake_bot.sent_to[0][1]
        assert answered_message and "۱ نفر" in answered_message[0]
        assert "کامل کرده بودند" in answered_message[0]
        assert "قبلاً تلنگر" in answered_message[0]

    asyncio.run(run_test())
