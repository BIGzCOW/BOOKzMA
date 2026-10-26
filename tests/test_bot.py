import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pydantic import SecretStr

from BOOKzMA import bot as bot_module
from BOOKzMA.config import Settings


def test_polling_does_not_override_uvicorn_signal_handlers(monkeypatch):
    polling_options = {}

    class StubBot:
        def __init__(self, **kwargs):
            self.session = SimpleNamespace(close=AsyncMock())

        async def set_my_commands(self, *args, **kwargs):
            return None

    async def idle_loop(*args):
        await asyncio.Event().wait()

    async def fake_start_polling(self, bot, **kwargs):
        polling_options.update(kwargs)
        await asyncio.Event().wait()

    monkeypatch.setattr(bot_module, "Bot", StubBot)
    monkeypatch.setattr(bot_module.Dispatcher, "start_polling", fake_start_polling)
    monkeypatch.setattr(bot_module, "reminder_loop", idle_loop)
    monkeypatch.setattr(bot_module, "broadcast_loop", idle_loop)
    monkeypatch.setattr(bot_module, "risk_alert_loop", idle_loop)

    async def run_startup():
        settings = Settings(bot_token=SecretStr("test-token"))
        _, tasks = await bot_module.start_bot(settings, object())
        await asyncio.sleep(0)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(run_startup())

    assert polling_options == {"handle_signals": False}