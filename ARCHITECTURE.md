# Architecture (Current)

This repository contains a Persian Telegram reading bot and a FastAPI HTTP API. The API authenticates Telegram Web App `initData`, issues one-hour bearer tokens, and exposes account, reading, and reminder endpoints. The Docker application runs Uvicorn; its default lifespan also starts Telegram long polling and the reminder task in the same process.

## Runtime Flow

- `src/BOOKzMA/__main__.py` starts `BOOKzMA.api:create_app` through Uvicorn. `Dockerfile` uses the same factory and binds port 8000 inside the container.
- `create_app()` runs Alembic upgrades at startup by default, creates an async SQLAlchemy engine/session pool, and starts the bot unless its factory options disable those behaviors.
- `bot.py` creates an aiogram `Dispatcher`, registers `DbSessionMiddleware` at update scope, and registers `RateLimitMiddleware` before `MembershipMiddleware` for messages and callbacks. Rate limiting is a per-process fixed window that blocks updates before a DB session opens; membership middleware exempts configured admins and records UTC daily interaction. The bot scopes `/admin` to admins and starts polling, reading and miswak reminder tasks, the streak-risk alert, and durable broadcast delivery.
- Bot handlers live in `handlers/`; API routes are declared inside `api.create_app()`. Both paths call repositories directly and commit their own writes. `services/streak.py` contains date-based calculations; `services/backup.py` owns database dump/restore subprocesses and backup validation/rotation. The reminder scheduler is asynchronous and depends on aiogram and repositories.
- `repositories/` contains SQLAlchemy queries and PostgreSQL upserts. `db/` contains the declarative base, models, and async session-pool factory.
- `texts.py` holds user-facing Persian bot messages; `keyboards.py` constructs inline keyboards.
- `scripts/backup.py` and `scripts/restore.py` are stdlib-only host-side tools (not part of the image): the daily cron backup with optional Google Drive upload via `rclone`, and restore rehearsal against a temporary database. They share the backup-folder contract with the in-app service but do not import application code.

## Data and State

- SQLAlchemy async models persist users, local reading dates, and reminders in PostgreSQL. Exact columns, constraints, and externally visible limits are listed in [BOT_GUIDE.md](BOT_GUIDE.md).
- Alembic revisions `0001`–`0012` add the core schema, account deletion, badges, and study-buddy invitations. Revisions `0011` and `0012` add hashed, expiring invitations and allow multiple active buddies per user. Revisions `0013` and `0014` add separate miswak tables and campaign fields; miswak does not affect reading streaks. Do not edit an applied revision; add a new migration for schema changes.
- Freeze events remain separate from reading logs. Miswak entries, goals, reminders, badges, challenges, league membership, and buddy pairs are separate tables. Analytics read UTC activity, reading, and miswak completion data; broadcast campaigns use durable per-recipient delivery records.
- Study-buddy and miswak invitations store token hashes, expire, and cascade when the inviter's account is deleted.
- Account deletion removes the `users` row (cascading to all related tables) and records a tombstone in `deleted_accounts`. The bot membership middleware and the API `_load_user` helper check that tombstone before any user upsert, so deleted accounts are never silently re-registered; the `account_restore` callback clears the tombstone for explicit re-registration.
- Conversation state and membership cache are process-local; exact bot state and cache behavior are documented in [BOT_GUIDE.md](BOT_GUIDE.md).

## Operational Limits

- `reminder_loop`, `miswak_reminder_loop`, and `risk_alert_loop` run in the same process as the bot and may perform additional database queries per candidate. Detailed timing and retry behavior are in [BOT_GUIDE.md](BOT_GUIDE.md); the observed query hot path is in [docs/PERFORMANCE.md](docs/PERFORMANCE.md).
- Polling, reminder/broadcast tasks, FSM state, membership cache, rate-limit windows, and the broadcast start lock are process-local. The current deployment is designed for one application instance; replicas would duplicate polling and background work and would not share FSM/cache/lock state.
- The API health endpoint reports process-level `{"status":"ok"}` and does not verify database or Telegram availability.

## Local and Production

Production Compose runs PostgreSQL and the API/bot application together as containers. The host publishes PostgreSQL on `127.0.0.1:5433` and the application on `127.0.0.1:8000`. The Docker image runs as UID 10001 and copies only requirements, `src/`, `migrations/`, and `alembic.ini`. The bot container bind-mounts `BOOKZMA_BACKUP_DIR` at `/backups`; the folder must exist outside the repository and be writable by UID 10001. Compose does not configure a Telegram proxy.

For local development, Compose can run only PostgreSQL while the ignored `dev_run.py` starts the same FastAPI/bot app on the host. The launcher reads optional `TELEGRAM_PROXY` from `Settings` and injects an aiogram session; configure `DATABASE_URL` to use the host-published database port and use a separate test bot token. Stop the Compose bot first to avoid two pollers. See [docs/LOCAL_DEV.md](docs/LOCAL_DEV.md) before changing entrypoints, configuration, or deployment.

For interface details, environment variables, commands, callbacks, and constraints, see [BOT_GUIDE.md](BOT_GUIDE.md). For current decisions and future ideas, see [docs/DECISIONS.md](docs/DECISIONS.md) and [docs/ROADMAP.md](docs/ROADMAP.md).