import asyncio
from datetime import date, timedelta

from BOOKzMA.services import mesbak_freezes
from BOOKzMA.services.streak import compute_streak

TODAY = date(2026, 10, 26)


def test_mesbak_freeze_is_earned_after_seven_real_completed_days(monkeypatch):
    async def run_test():
        completed = {TODAY - timedelta(days=offset) for offset in range(7)}
        events = []

        async def lock_user(_session, _user_id):
            return None

        async def completed_days(_session, _user_id):
            return completed

        async def balance(_session, _user_id, *, habit):
            assert habit == "mesbak"
            return 0

        async def add_event(_session, _user_id, kind, day, *, habit):
            events.append((kind, day, habit))
            return True

        monkeypatch.setattr(mesbak_freezes.streak_freezes, "lock_user", lock_user)
        monkeypatch.setattr(
            mesbak_freezes.mesbak, "completed_day_set", completed_days
        )
        monkeypatch.setattr(mesbak_freezes.streak_freezes, "balance", balance)
        monkeypatch.setattr(mesbak_freezes.streak_freezes, "add_event", add_event)

        change = await mesbak_freezes.on_completed_day(object(), 777, TODAY)

        assert change.earned is True
        assert events == [("earned", TODAY, "mesbak")]

    asyncio.run(run_test())


def test_mesbak_freeze_protects_only_one_missed_day_after_real_completion(monkeypatch):
    async def run_test():
        completed = {TODAY, TODAY - timedelta(days=2)}
        events = []

        async def lock_user(_session, _user_id):
            return None

        async def completed_days(_session, _user_id):
            return completed

        async def balance(_session, _user_id, *, habit):
            assert habit == "mesbak"
            return 1

        async def add_event(_session, _user_id, kind, day, *, habit):
            events.append((kind, day, habit))
            return True

        monkeypatch.setattr(mesbak_freezes.streak_freezes, "lock_user", lock_user)
        monkeypatch.setattr(
            mesbak_freezes.mesbak, "completed_day_set", completed_days
        )
        monkeypatch.setattr(mesbak_freezes.streak_freezes, "balance", balance)
        monkeypatch.setattr(mesbak_freezes.streak_freezes, "add_event", add_event)

        change = await mesbak_freezes.on_completed_day(object(), 777, TODAY)

        assert change.used_day == TODAY - timedelta(days=1)
        assert change.earned is False
        assert events == [("used", TODAY - timedelta(days=1), "mesbak")]
        assert compute_streak(completed, TODAY, [change.used_day]) == 3
        assert TODAY - timedelta(days=1) not in completed

    asyncio.run(run_test())


def test_mesbak_freeze_does_not_cover_multiple_missed_days(monkeypatch):
    async def run_test():
        completed = {TODAY, TODAY - timedelta(days=3)}
        events = []

        async def lock_user(_session, _user_id):
            return None

        async def completed_days(_session, _user_id):
            return completed

        async def balance(_session, _user_id, *, habit):
            return 1

        async def add_event(*_args, **_kwargs):
            events.append(True)
            return True

        monkeypatch.setattr(mesbak_freezes.streak_freezes, "lock_user", lock_user)
        monkeypatch.setattr(
            mesbak_freezes.mesbak, "completed_day_set", completed_days
        )
        monkeypatch.setattr(mesbak_freezes.streak_freezes, "balance", balance)
        monkeypatch.setattr(mesbak_freezes.streak_freezes, "add_event", add_event)

        change = await mesbak_freezes.on_completed_day(object(), 777, TODAY)

        assert change.used_day is None
        assert events == []

    asyncio.run(run_test())
