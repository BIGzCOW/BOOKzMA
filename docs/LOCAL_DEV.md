# Local Development

The local workflow keeps PostgreSQL and Meilisearch in Compose and runs the application from the host with the tracked `dev_run.py`. The launcher uses `TELEGRAM_PROXY` to configure aiogram's HTTP/SOCKS session; credentials and proxy values remain in local environment configuration. Meilisearch is exposed only on `127.0.0.1:7700`; the bot uses an index-scoped API key and never receives the master key.

| Concern | Local owner workflow (reported) | Production Compose (verified) |
| --- | --- | --- |
| Application process | `python dev_run.py`; host Uvicorn runs the shared FastAPI factory with an optional proxy session | Uvicorn runs the FastAPI factory; its lifespan starts bot polling and reminders |
| Data services | Compose `db` (`5433`) and `meilisearch` (`7700`, loopback only) | PostgreSQL and pinned Meilisearch `v1.56.1`, each with a named volume |
| Telegram access | Separate test bot token and optional `TELEGRAM_PROXY` from `.env` | Direct Telegram access; no proxy is configured in Compose |
| Migrations | FastAPI lifespan runs Alembic `upgrade head` at startup against the configured local database | FastAPI lifespan runs Alembic `upgrade head` at application startup |
| Entrypoint | Tracked developer launcher; graceful shutdown deadline is 5 seconds | `uvicorn BOOKzMA.api:create_app --factory ...` from `Dockerfile` |

## Owner-Reported Setup

Use Python 3.12, matching `pyproject.toml` and CI. The reported command sequence is:

Before Compose, set `MEILI_MASTER_KEY` to a unique random value of at least 16 bytes in the local `.env`, and set a separate `MEILI_API_KEY` scoped to the catalog indexes. Generate a local master key with `openssl rand -hex 32`; do not commit it. The bot container explicitly clears `MEILI_MASTER_KEY`. To create the runtime key after Meilisearch starts, use the master key locally:

```sh
curl -sS -X POST http://127.0.0.1:7700/keys \
	-H "Authorization: Bearer $MEILI_MASTER_KEY" \
	-H "Content-Type: application/json" \
	-d '{"name":"BOOKzMA catalog runtime","actions":["search","documents.add","documents.delete","indexes.create","indexes.get","tasks.get","settings.update","stats.get"],"indexes":["book_catalog","book_catalog_*"],"expiresAt":null}'
```

Store the returned key in `MEILI_API_KEY` in the local `.env`. For `MEILI_EVAL_API_KEY`, create a separate similarly scoped key with `indexes.delete` added; only the evaluation command uses it to remove its temporary index. The official Meilisearch master key is never needed by the running bot.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
test -f .env || cp .env.sample .env
docker compose up -d db meilisearch
docker compose stop bot
PYTHONPATH=src python dev_run.py
```

For a first catalog build or recovery, run `python -m BOOKzMA.reindex_catalog` with the bot stopped; it does not require `BOT_TOKEN`, uses 10K-document batches, waits for Meilisearch tasks, and validates indexed count against PostgreSQL. `python -m BOOKzMA.evaluate_catalog_search` loads the synthetic 51-query fixture into a temporary Meilisearch index, compares `frequency` and `last`, reports top-10 success plus p50/p95, then deletes that index. The synthetic timing is not a benchmark of the external 674K-row catalog. The real read-only SQLite file must be mounted at `CHANNEL_CATALOG_DB_PATH` before running the production-sized reindex.

The admin backup and restore actions also require the host PostgreSQL client tools. On Fedora, install them with `sudo dnf install postgresql`; on Debian/Ubuntu use `sudo apt install postgresql-client`. Docker images already include the client tools.

در `.env` از bot token جداگانهٔ تست استفاده کن، `TELEGRAM_PROXY` را با آدرس proxy خودت تنظیم کن، و `DATABASE_URL` را به `127.0.0.1:5433` وصل کن؛ hostname `db` فقط داخل شبکهٔ Docker resolve می‌شود. سپس با فرمان‌های بالا فقط PostgreSQL را در Docker بالا بیاور، کانتینر bot را متوقف کن و برنامه را از میزبان اجرا کن. launcher همان app را اجرا می‌کند و migration را هنگام startup انجام می‌دهد. اگر `.env` هنوز placeholderهای `.env.sample` را دارد، پیش از اجرا آن‌ها را با مقادیر local/test جایگزین کن.

If startup succeeds but book browsing raises `column user_books.restored_at does not exist`, restart the current app so Alembic can apply revision `0020`. Confirm the configured local database with `alembic current`; never point this check or migration at production. Revision `0020` repairs the `page_count_set_at` and `restored_at` columns even when the database was already stamped at `0019`.

Before starting, ensure `DATABASE_URL` targets the local Compose database and `POSTGRES_PASSWORD` matches that database. Never use the production bot token locally. Do not run the Compose bot and local launcher simultaneously with the same token; Telegram permits only one long-polling consumer per bot. `dev_run.py` has no embedded credentials; configure a test bot token and optional proxy through environment settings.

Use a separate test bot. Do not poll the same token from both local and production instances. The test bot must have the channel permissions required by the configured membership gate. Do not expose private token or proxy values in logs or issue reports.

Compose validates the entire configuration even when only one service is requested. Define non-empty `POSTGRES_PASSWORD`, `BOOKZMA_BACKUP_DIR`, and `MEILI_MASTER_KEY` in the local `.env` before running it; `docker compose config --quiet` checks interpolation without printing credentials. For local development, `BOOKZMA_BACKUP_DIR=./backups` is supported by `.env.sample`; create the folder with `mkdir -p backups` and `chmod 700 backups`. The host launcher needs a matching password in `DATABASE_URL`, using `127.0.0.1:5433`. A registry `403 Forbidden` during image download must be resolved at the Docker daemon/network layer before PostgreSQL or migrations can run; `TELEGRAM_PROXY` does not configure the Docker daemon.

Local (non-Docker) backups: the backup service writes to `BACKUP_DIR` (default `backups`, resolved relative to the project root). The default location is `<project-root>/backups`; absolute paths are also accepted. Compose requires `BOOKZMA_BACKUP_DIR` during configuration validation and mounts that host directory at `/backups` when the bot container runs. Server backup folders must be outside the repository and writable by UID 10001; see [BACKUP.md](BACKUP.md).

## Compatibility Boundary

Changes must preserve Docker execution and the local workflow. The optional `bot_session` is unset in Compose, so Docker keeps its existing direct session. Local `dev_run.py` builds an aiogram session from `TELEGRAM_PROXY` and runs the same app on the host. The local Uvicorn launcher allows five seconds for graceful shutdown; the application bounds background-task shutdown to the same interval. Update this file, `BOT_GUIDE.md`, and `.env.sample` when changing settings or entrypoints.

Committed `src/BOOKzMA/__main__.py` starts Uvicorn without a proxy. The local launcher creates an optional aiogram `AiohttpSession` and injects it into the shared app; run it with a test token and local DB only.

## Local Launcher Boundary

`dev_run.py` only loads `Settings`, creates the aiogram session from the optional `TELEGRAM_PROXY` value, and starts the shared app. It contains no literal bot token or duplicate business logic. Never put real tokens or proxy credentials in the launcher.

برای روال اجباری branch، تست، PR، tag و deploy هر feature، [docs/WORKFLOW.md](WORKFLOW.md) را ببین.
