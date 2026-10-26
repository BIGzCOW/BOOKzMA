import hashlib
import hmac
import json
import logging
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jwt
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from aiogram.client.session.base import BaseSession
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from BOOKzMA.bot import start_bot
from BOOKzMA.config import Settings
from BOOKzMA.db.session import create_session_pool
from BOOKzMA.repositories import readings, reminders, users
from BOOKzMA.repositories import streak_freezes
from BOOKzMA.services.streak import longest_streak, weekly_summary
from BOOKzMA.services.streak_freezes import on_read
from BOOKzMA.utils import local_today

log = logging.getLogger(__name__)
ACCESS_TOKEN_TTL = timedelta(hours=1)
INIT_DATA_MAX_AGE = timedelta(days=1)
bearer_scheme = HTTPBearer(auto_error=False)


class TelegramAuthRequest(BaseModel):
    init_data: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: int
    username: str | None
    timezone: str


class DayResponse(BaseModel):
    date: date
    read: bool


class WeeklySummaryResponse(BaseModel):
    start: date
    end: date
    days_read: int
    streak: int
    longest_streak: int
    days: list[DayResponse]


class ReadResponse(BaseModel):
    created: bool
    summary: WeeklySummaryResponse


class ReminderCreate(BaseModel):
    time: time


class ReminderResponse(BaseModel):
    id: int
    time: time


class TimezoneUpdate(BaseModel):
    timezone: str


class Identity(BaseModel):
    id: int
    username: str | None = None


def _verify_init_data(init_data: str, bot_token: str) -> Identity:
    pairs = parse_qsl(init_data, keep_blank_values=True)
    values = dict(pairs)
    if len(values) != len(pairs) or "hash" not in values:
        raise ValueError("Invalid Telegram init data")

    received_hash = values.pop("hash")
    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(values.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Invalid Telegram init data")

    try:
        auth_date = datetime.fromtimestamp(int(values["auth_date"]), tz=timezone.utc)
        age = datetime.now(timezone.utc) - auth_date
        if age < timedelta(seconds=-30) or age > INIT_DATA_MAX_AGE:
            raise ValueError("Expired Telegram init data")
        user_data = json.loads(values["user"])
        user_id = user_data["id"]
        if isinstance(user_id, bool) or not isinstance(user_id, int):
            raise ValueError("Invalid Telegram user")
        username = user_data.get("username")
        if username is not None and not isinstance(username, str):
            username = None
        return Identity(id=user_id, username=username)
    except (KeyError, TypeError, ValueError, OverflowError, OSError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid Telegram init data") from exc


def _token_secret(bot_token: str) -> bytes:
    return hmac.new(bot_token.encode(), b"BOOKzMA API access token v1", hashlib.sha256).digest()


def _create_access_token(identity: Identity, bot_token: str) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(identity.id),
            "username": identity.username,
            "iat": now,
            "exp": now + ACCESS_TOKEN_TTL,
        },
        _token_secret(bot_token),
        algorithm="HS256",
    )


def _decode_access_token(token: str, bot_token: str) -> Identity:
    payload = jwt.decode(token, _token_secret(bot_token), algorithms=["HS256"])
    subject = payload.get("sub")
    if not isinstance(subject, str) or not subject.isdecimal():
        raise jwt.InvalidTokenError("Invalid subject")
    username = payload.get("username")
    return Identity(id=int(subject), username=username if isinstance(username, str) else None)


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    pool: async_sessionmaker[AsyncSession] = request.app.state.session_pool
    async with pool() as session:
        yield session


async def require_identity(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> Identity:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = credentials.credentials
    bot_token = request.app.state.settings.bot_token.get_secret_value()
    try:
        return _decode_access_token(token, bot_token)
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


async def _load_user(session: AsyncSession, identity: Identity):
    if await users.is_deleted(session, identity.id):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account deleted")
    user = await users.get_or_create(session, identity.id, identity.username)
    await session.commit()
    return user


async def _get_weekly_summary(session: AsyncSession, user_id: int, tz_name: str):
    today = local_today(tz_name)
    days = await readings.get_days(session, user_id)
    frozen_days = await streak_freezes.used_days(session, user_id)
    summary = weekly_summary(days, today, frozen_days)
    summary["longest_streak"] = longest_streak(days, frozen_days)
    return summary


def _upgrade_database(database_url: str) -> None:
    project_root = Path(__file__).resolve().parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.attributes["database_url"] = database_url
    command.upgrade(config, "head")


@asynccontextmanager
async def _lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    if app.state.run_migrations:
        await asyncio.to_thread(_upgrade_database, settings.database_url)
        log.info("database migrations are up to date")
    engine, session_pool = create_session_pool(settings.database_url)
    app.state.engine = engine
    app.state.session_pool = session_pool
    bot = None
    tasks = []
    try:
        if app.state.run_bot:
            bot, tasks = await start_bot(
                settings, session_pool, bot_session=app.state.bot_session
            )
        yield
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if bot is not None:
            await bot.session.close()
        await engine.dispose()


def create_app(
    settings: Settings | None = None,
    run_bot: bool = True,
    run_migrations: bool = True,
    bot_session: BaseSession | None = None,
) -> FastAPI:
    app = FastAPI(title="BOOKzMA API", version="1.1.0", lifespan=_lifespan)
    app.state.settings = settings or Settings()
    app.state.run_bot = run_bot
    app.state.run_migrations = run_migrations
    app.state.bot_session = bot_session
    origins = [
        origin.strip()
        for origin in app.state.settings.web_origins.split(",")
        if origin.strip()
    ]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Authorization", "Content-Type"],
        )

    @app.get("/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/auth/telegram", response_model=TokenResponse, tags=["auth"])
    async def telegram_auth(payload: TelegramAuthRequest) -> TokenResponse:
        token_value = app.state.settings.bot_token.get_secret_value()
        try:
            identity = _verify_init_data(payload.init_data, token_value)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Telegram init data"
            ) from exc
        return TokenResponse(
            access_token=_create_access_token(identity, token_value),
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
        )

    @app.get("/api/v1/me", response_model=UserResponse, tags=["account"])
    async def get_me(
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> UserResponse:
        user = await _load_user(session, identity)
        return UserResponse(id=user.id, username=user.username, timezone=user.timezone)

    @app.put("/api/v1/me/timezone", response_model=UserResponse, tags=["account"])
    async def update_timezone(
        payload: TimezoneUpdate,
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> UserResponse:
        try:
            ZoneInfo(payload.timezone)
        except ZoneInfoNotFoundError as exc:
            raise HTTPException(status_code=422, detail="Unknown timezone") from exc
        user = await _load_user(session, identity)
        await users.set_timezone(session, user.id, payload.timezone)
        await session.commit()
        return UserResponse(id=user.id, username=user.username, timezone=payload.timezone)

    @app.get(
        "/api/v1/me/weekly-summary",
        response_model=WeeklySummaryResponse,
        tags=["reading"],
    )
    async def get_weekly_summary(
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> WeeklySummaryResponse:
        user = await _load_user(session, identity)
        return WeeklySummaryResponse(**await _get_weekly_summary(session, user.id, user.timezone))

    @app.post("/api/v1/me/read", response_model=ReadResponse, tags=["reading"])
    async def mark_read_today(
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> ReadResponse:
        user = await _load_user(session, identity)
        today = local_today(user.timezone)
        created = await readings.mark_read(session, user.id, today)
        if created:
            await on_read(session, user.id, today)
        await session.commit()
        return ReadResponse(
            created=created,
            summary=WeeklySummaryResponse(
                **await _get_weekly_summary(session, user.id, user.timezone)
            ),
        )

    @app.get("/api/v1/me/reminders", response_model=list[ReminderResponse], tags=["reminders"])
    async def list_reminders(
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> list[ReminderResponse]:
        user = await _load_user(session, identity)
        records = await reminders.list_for_user(session, user.id)
        return [ReminderResponse(id=item.id, time=item.remind_at) for item in records]

    @app.post(
        "/api/v1/me/reminders",
        response_model=ReminderResponse,
        status_code=201,
        tags=["reminders"],
    )
    async def add_reminder(
        payload: ReminderCreate,
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> ReminderResponse:
        user = await _load_user(session, identity)
        result = await reminders.add(session, user.id, payload.time)
        if result == "limit":
            await session.rollback()
            raise HTTPException(status_code=409, detail="Reminder limit reached")
        if result == "dup":
            await session.rollback()
            raise HTTPException(status_code=409, detail="Reminder already exists")
        await session.commit()
        record = next(
            item
            for item in await reminders.list_for_user(session, user.id)
            if item.remind_at == payload.time
        )
        return ReminderResponse(id=record.id, time=record.remind_at)

    @app.delete("/api/v1/me", status_code=204, tags=["account"])
    async def delete_me(
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        await users.delete_account(session, identity.id)
        await session.commit()

    @app.delete("/api/v1/me/reminders/{reminder_id}", status_code=204, tags=["reminders"])
    async def delete_reminder(
        reminder_id: int,
        identity: Identity = Depends(require_identity),
        session: AsyncSession = Depends(get_session),
    ) -> None:
        user = await _load_user(session, identity)
        deleted = await reminders.delete_one(session, user.id, reminder_id)
        if not deleted:
            await session.rollback()
            raise HTTPException(status_code=404, detail="Reminder not found")
        await session.commit()

    return app

