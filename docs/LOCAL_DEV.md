# Local Development

The local workflow keeps PostgreSQL in Compose and runs the application from the host with the ignored `dev_run.py`. The launcher uses `TELEGRAM_PROXY` to configure aiogram's HTTP/SOCKS session; the proxy value and bot token remain local.

| Concern | Local owner workflow (reported) | Production Compose (verified) |
| --- | --- | --- |
| Application process | `python dev_run.py`; host Uvicorn runs the shared FastAPI factory with an optional proxy session | Uvicorn runs the FastAPI factory; its lifespan starts bot polling and reminders |
| Database | Compose `db` service, host port `5433` | Compose `db` service and named `pgdata` volume |
| Telegram access | Separate test bot token and optional `TELEGRAM_PROXY` from `.env` | Direct Telegram access; no proxy is configured in Compose |
| Migrations | FastAPI lifespan runs Alembic `upgrade head` at startup against the configured local database | FastAPI lifespan runs Alembic `upgrade head` at application startup |
| Entrypoint | Ignored local-only launcher; do not commit it | `uvicorn BOOKzMA.api:create_app --factory ...` from `Dockerfile` |

## Owner-Reported Setup

Use Python 3.12, matching `pyproject.toml` and CI. The reported command sequence is:

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
cp .env.sample .env
docker compose up -d db
docker compose stop bot
PYTHONPATH=src python dev_run.py
```

در `.env` از bot token جداگانهٔ تست استفاده کن، `TELEGRAM_PROXY` را با آدرس proxy خودت تنظیم کن، و `DATABASE_URL` را به `127.0.0.1:5433` وصل کن؛ hostname `db` فقط داخل شبکهٔ Docker resolve می‌شود. سپس با فرمان‌های بالا فقط PostgreSQL را در Docker بالا بیاور، کانتینر bot را متوقف کن و برنامه را از میزبان اجرا کن. launcher همان app را اجرا می‌کند و migration را هنگام startup انجام می‌دهد. اگر `.env` هنوز placeholderهای `.env.sample` را دارد، پیش از اجرا آن‌ها را با مقادیر local/test جایگزین کن.

Before starting, ensure `DATABASE_URL` targets the local Compose database and `POSTGRES_PASSWORD` matches that database. Never use the production bot token locally. Do not run the Compose bot and local launcher simultaneously with the same token; Telegram permits only one long-polling consumer per bot. Do not inspect, commit, or publish the ignored `dev_run.py`.

Use a separate test bot. Do not poll the same token from both local and production instances. The test bot must have the channel permissions required by the configured membership gate. Do not expose private token or proxy values in logs or issue reports.

Local (non-Docker) backups: the backup service writes to `BACKUP_DIR` (default `/backups`, meant for the container mount). Locally set `BACKUP_DIR` in `.env` to a writable folder outside the repository; the service refuses a destination inside the source tree, and `*.dump` files are git-ignored anyway. The Compose variable `BOOKZMA_BACKUP_DIR` is only needed for `docker compose up` of the full stack.

## Compatibility Boundary

Changes must preserve Docker execution and the local workflow. The optional `bot_session` is unset in Compose, so Docker keeps its existing direct session. Local `dev_run.py` builds an aiogram session from `TELEGRAM_PROXY` and runs the same app on the host. Update this file, `BOT_GUIDE.md`, and `.env.sample` when changing settings or entrypoints.

Committed `src/BOOKzMA/__main__.py` starts Uvicorn without a proxy. The ignored local launcher creates an optional aiogram `AiohttpSession` and injects it into the shared app; run it with a test token and local DB only.

## Local Launcher Boundary

`dev_run.py` only loads `Settings`, creates the aiogram session from the optional `TELEGRAM_PROXY` value, and starts the shared app. It must not contain a literal bot token, duplicate business logic, or be committed.

Keep the launcher outside Git. If the owner later requests a public example, propose a separate script with placeholders and obtain approval first. Never put real tokens or proxy credentials in a tracked example.

برای روال اجباری branch، تست، PR، tag و deploy هر feature، [docs/WORKFLOW.md](WORKFLOW.md) را ببین.