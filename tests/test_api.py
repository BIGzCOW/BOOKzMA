import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, sentinel
from urllib.parse import urlencode

import jwt
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from BOOKzMA.api import (
    _create_access_token,
    _decode_access_token,
    _verify_init_data,
    create_app,
)
from BOOKzMA.config import Settings

BOT_TOKEN = "test-bot-token"


def _signed_init_data(auth_date: int | None = None, include_signature: bool = False) -> str:
    values = {
        "auth_date": str(auth_date or int(time.time())),
        "user": json.dumps({"id": 12345, "username": "reader"}, separators=(",", ":")),
    }
    if include_signature:
        values["signature"] = "telegram-ed25519-signature"
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    values["hash"] = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode(values)


def test_telegram_init_data_verifies_identity():
    assert _verify_init_data(_signed_init_data(), BOT_TOKEN).id == 12345
    assert _verify_init_data(_signed_init_data(include_signature=True), BOT_TOKEN).id == 12345


def test_telegram_init_data_rejects_tampering_and_expired_data():
    with pytest.raises(ValueError):
        _verify_init_data(_signed_init_data().replace("reader", "attacker"), BOT_TOKEN)
    with pytest.raises(ValueError):
        _verify_init_data(_signed_init_data(int(time.time()) - 90_000), BOT_TOKEN)


def test_access_token_round_trip_and_signature_validation():
    identity = _verify_init_data(_signed_init_data(), BOT_TOKEN)
    token = _create_access_token(identity, BOT_TOKEN)

    assert _decode_access_token(token, BOT_TOKEN) == identity
    with pytest.raises(jwt.InvalidTokenError):
        _decode_access_token(token, "different-bot-token")


def test_api_routes_are_versioned_and_documented():
    settings = Settings(bot_token=SecretStr(BOT_TOKEN))
    schema = create_app(settings, run_bot=False).openapi()

    assert "/api/v1/auth/telegram" in schema["paths"]
    assert "/api/v1/me/weekly-summary" in schema["paths"]
    assert "/api/v1/me/reminders" in schema["paths"]


def test_health_and_telegram_auth_endpoints():
    settings = Settings(bot_token=SecretStr(BOT_TOKEN))
    with TestClient(create_app(settings, run_bot=False, run_migrations=False)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/api/v1/me").status_code == 401
        response = client.post(
            "/api/v1/auth/telegram", json={"init_data": _signed_init_data()}
        )

    assert response.status_code == 200
    assert response.json()["token_type"] == "bearer"


def test_startup_runs_database_migrations(monkeypatch):
    settings = Settings(bot_token=SecretStr(BOT_TOKEN))
    migrated_urls = []
    monkeypatch.setattr("BOOKzMA.api._upgrade_database", migrated_urls.append)

    with TestClient(create_app(settings, run_bot=False)) as client:
        assert client.get("/health").status_code == 200

    assert migrated_urls == [settings.database_url]


def test_startup_passes_injected_bot_session(monkeypatch):
    settings = Settings(bot_token=SecretStr(BOT_TOKEN))
    session_pool = object()
    injected_session = sentinel.bot_session
    engine = SimpleNamespace(dispose=AsyncMock())
    bot = SimpleNamespace(session=SimpleNamespace(close=AsyncMock()))
    received = []

    async def fake_start_bot(settings, pool, bot_session=None):
        received.append((pool, bot_session))
        return bot, []

    monkeypatch.setattr(
        "BOOKzMA.api.create_session_pool", lambda database_url: (engine, session_pool)
    )
    monkeypatch.setattr("BOOKzMA.api.start_bot", fake_start_bot)

    with TestClient(
        create_app(settings, run_migrations=False, bot_session=injected_session)
    ) as client:
        assert client.get("/health").status_code == 200

    assert received == [(session_pool, injected_session)]
    engine.dispose.assert_awaited_once()
    bot.session.close.assert_awaited_once()
