import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from BOOKzMA.handlers.miswak import render_miswak


class Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


def test_direct_miswak_entry_marks_new_user_as_started(monkeypatch):
    async def run_test():
        user = SimpleNamespace(
            id=777,
            username="user",
            full_name="User",
            timezone="Asia/Tehran",
            started_at=None,
        )
        started = []
        shown = []

        async def get_or_create(_session, *_args):
            return user

        async def mark_started(_session, user_id):
            started.append(user_id)
            user.started_at = datetime.now(timezone.utc)
            return True

        async def get_profile(_session, _user_id, _today):
            return None

        async def show(_event, text, keyboard):
            shown.append((text, keyboard))

        monkeypatch.setattr("BOOKzMA.handlers.miswak.users.get_or_create", get_or_create)
        monkeypatch.setattr("BOOKzMA.handlers.miswak.users.mark_started", mark_started)
        monkeypatch.setattr("BOOKzMA.handlers.miswak.miswak_repo.get_profile", get_profile)
        monkeypatch.setattr("BOOKzMA.handlers.miswak.show", show)

        session = Session()
        await render_miswak(SimpleNamespace(), session, SimpleNamespace(
            id=777, username="user", full_name="User"
        ))

        assert started == [777]
        assert shown
        assert session.commits == 1

    asyncio.run(run_test())