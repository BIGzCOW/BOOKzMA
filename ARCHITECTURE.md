# Architecture (Current)

This repository contains a Persian Telegram reading bot and a FastAPI HTTP API. The API authenticates Telegram Web App `initData`, issues one-hour bearer tokens, and exposes account, reading, and reminder endpoints. The Docker application runs Uvicorn; its default lifespan also starts Telegram long polling and the reminder task in the same process.

## Runtime Flow

- `src/BOOKzMA/__main__.py` starts `BOOKzMA.api:create_app` through Uvicorn. `Dockerfile` uses the same factory and binds port 8000 inside the container.
- `create_app()` runs Alembic upgrades at startup by default, creates an async SQLAlchemy engine/session pool, and starts the bot unless its factory options disable those behaviors.
- `bot.py` creates an aiogram `Dispatcher` with `SimpleEventIsolation`: updates sharing a user/chat FSM key are serialized before reading state, while different keys remain concurrent. It registers `DbSessionMiddleware` at update scope, and registers `RateLimitMiddleware` before `MembershipMiddleware` for messages and callback queries. The rate-limit middleware is a per-process in-memory fixed window (D-10) that swallows blocked updates before the DB session opens; the membership middleware exempts configured admin IDs from the membership gate and records UTC daily interaction. The bot scopes `/admin` to admins and starts polling, separate reading/Mesbak reminder tasks, the streak-risk alert, and the durable broadcast worker.
- Book navigation is registered before other forms; book text inputs are registered after existing menus/commands. The inner `BookFlowNavigationMiddleware` clears an active book form when another handler takes over. Library routes reject non-private chats before querying books; only the active book-form input handlers preserve that form's state.
- Bot handlers live in `handlers/`; API routes are declared inside `api.create_app()`. Both paths call repositories directly and commit their own writes. `services/reading_registration.py` centralizes the existing reading-day side effects so the one-tap callback and personal-library page logs share freeze/comeback/badge behavior; `services/streak.py` contains date-based calculations. The reminder scheduler is asynchronous but depends on aiogram and repositories. `services/backup.py` runs `pg_dump`/`pg_restore` subprocesses against the database (installed as `postgresql-client` in the image) and owns backup naming, validation, and local rotation; the destructive-restore flow lives in the admin handler.
- `repositories/` contains SQLAlchemy queries and PostgreSQL upserts. `db/` contains the declarative base, models, and async session-pool factory.
- `texts.py` holds user-facing Persian bot messages; `keyboards.py` constructs inline keyboards.
- `scripts/backup.py` and `scripts/restore.py` are stdlib-only host-side tools (not part of the image): the daily cron backup with optional Google Drive upload via `rclone`, and restore rehearsal against a temporary database. They share the backup-folder contract with the in-app service but do not import application code.

## Data and State

- SQLAlchemy async models persist users, local reading dates, personal books/page logs, reminders, and the optional social/habit data in PostgreSQL. Exact columns, constraints, and externally visible limits are listed in [BOT_GUIDE.md](BOT_GUIDE.md).
- Alembic revisions `0001`–`0017` evolve the schema through personal books/page logs; revisions `0011` and `0012` add hashed, expiring study-buddy invitations and allow multiple active study buddies per user. Revisions `0013` and `0014` add Mesbak data, `0015` renames those tables, `0016` adds anonymous Mesbak buddy matching, and `0017` adds the personal library. Do not edit an applied revision; add a new migration for schema changes.
- Freeze events remain separate from reading logs. A positive personal-book page log creates the same daily reading row transactionally; multiple sessions in one local day still count as one reading day. Mesbak entries, goals, reminders, badges, challenges, league membership, buddy pairs, and the anonymous matching queue are separate from reading data and do not affect reading streaks. Analytics read UTC activity, reading/page data, and Mesbak completion data; broadcast campaigns snapshot per-recipient durable deliveries for all users or active Mesbak members.
- Buddy invitations store only token hashes, expire after seven days, and cascade when the inviter's account is deleted.
- Account deletion removes the `users` row (cascading to all related tables) and records a tombstone in `deleted_accounts`. The bot membership middleware and the API `_load_user` helper check that tombstone before any user upsert, so deleted accounts are never silently re-registered; the `account_restore` callback clears the tombstone for explicit re-registration.
- Conversation state and membership cache are process-local; exact bot state and cache behavior are documented in [BOT_GUIDE.md](BOT_GUIDE.md).

## Operational Limits

- `reminder_loop`, the Mesbak reminder loop, and `risk_alert_loop` run in the same process as the bot and may perform additional database queries per candidate. Detailed timing and retry behavior are in [BOT_GUIDE.md](BOT_GUIDE.md); the observed query hot path is in [docs/PERFORMANCE.md](docs/PERFORMANCE.md).
- Polling, reminder/broadcast tasks, FSM state, membership cache, rate-limit windows, and the broadcast start lock are process-local. The current deployment is designed for one application instance; replicas would duplicate polling and background work and would not share FSM/cache/lock state.
- The API health endpoint reports process-level `{"status":"ok"}` and does not verify database or Telegram availability.

## Local and Production

Production Compose runs PostgreSQL and the API/bot application together as containers. The host publishes PostgreSQL on `127.0.0.1:5433` and the application on `127.0.0.1:8000`. The Docker image runs as UID 10001 and copies only requirements, `src/`, `migrations/`, and `alembic.ini`. Compose leaves the aiogram session at its default, with no Telegram proxy. The bot container also bind-mounts `BOOKZMA_BACKUP_DIR` at `/backups` for database backups; the folder must exist on the host, be outside the repository, and be writable by UID 10001.

For local development, Compose can run only PostgreSQL while the tracked `dev_run.py` starts the same FastAPI/bot app on the host. The launcher reads optional `TELEGRAM_PROXY` from `Settings` and injects an aiogram session; configure `DATABASE_URL` to use the host-published database port and use a separate test bot token. Stop the Compose bot first to avoid two pollers. See [docs/LOCAL_DEV.md](docs/LOCAL_DEV.md) before changing entrypoints, configuration, or deployment.

For interface details, environment variables, commands, callbacks, and constraints, see [BOT_GUIDE.md](BOT_GUIDE.md). For current decisions and future ideas, see [docs/DECISIONS.md](docs/DECISIONS.md) and [docs/ROADMAP.md](docs/ROADMAP.md).
