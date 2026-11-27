# BOOKzMA Agent Rules

BOOKzMA is a Python 3.12 Persian Telegram reading bot with an existing FastAPI API, SQLAlchemy async persistence, PostgreSQL, Alembic, and Docker Compose. The container runs the API, Telegram long polling, and reminder loop in one Uvicorn process.

## Read First

1. Read [ARCHITECTURE.md](ARCHITECTURE.md) before changing runtime structure.
2. Read [BOT_GUIDE.md](BOT_GUIDE.md) before changing commands, callbacks, FSM state, API routes, tables, or environment variables.
3. Read [docs/DECISIONS.md](docs/DECISIONS.md) before proposing a different technology or architecture.
4. Read [docs/ROADMAP.md](docs/ROADMAP.md); an idea is not authorization to implement it. The roadmap's top section names the current **priority-1 task**; that task must be completed first, before any new feature work.
5. Read the relevant topic guide: [LOCAL_DEV](docs/LOCAL_DEV.md), [TESTING](docs/TESTING.md), [SECURITY_PRACTICES](docs/SECURITY_PRACTICES.md), [PERFORMANCE](docs/PERFORMANCE.md), [BACKUP](docs/BACKUP.md), [DOCS_MAINTENANCE](docs/DOCS_MAINTENANCE.md), and [spec template](docs/specs/TEMPLATE.md). For owner workflows, see [vibe guide](docs/vibe/GUIDE.md) and [prompt library](docs/vibe/PROMPTS.md).

Never assume: open the actual file and verify the behavior before documenting or changing it.

## Commands

- Lint and tests: `ruff check . && pytest`. Run them before finishing and report actual output; never claim an unrun check passed.
- Docker build/start: `docker compose up -d --build`. This starts the configured application and database; do not use it against an owner's production host.
- Migration on a disposable/local database only: `alembic upgrade head`. The application also runs migrations at startup by default. Never run Alembic against production.
- CI uses Python 3.12, Ruff, Alembic, pytest, and a PostgreSQL service; see `.github/workflows/ci.yml`.

## Branch and Release Workflow

- Before every task, inspect `git branch --show-current` and `git status --short`. Work on a new task branch based on up-to-date `main`; never edit `main` directly. Follow [docs/WORKFLOW.md](docs/WORKFLOW.md).
- **Agent sessions (mandatory):** every agent, at the very start of a session/task, must create its own separate branch from up-to-date `main` and do all of its work on that branch. Never work on, edit, or commit to the main branch — no exceptions.
- Preserve dirty user changes. Do not discard, stash, or switch away from unclear changes; ask before mixing unrelated work. If the current non-main branch already contains the same in-progress task, continue it rather than moving its changes.
- Do not commit, push, merge, or tag unless explicitly asked. At the end of every feature, provide branch, test/local-run, Docker/database, PR/merge/tag, and post-merge server deployment guidance.
- `dev_run.py` is the shared local developer launcher and is tracked. Keep credentials in environment configuration; never hardcode tokens or proxy credentials.

## Current Layout and Change Boundaries

- Bot handlers are in `src/BOOKzMA/handlers/`; they orchestrate repositories and services. Keep SQL in repositories. Register a new bot router in `src/BOOKzMA/handlers/__init__.py`.
- API routes are currently declared inside `src/BOOKzMA/api.py`. The API and bot share repositories and the application lifespan.
- `repositories/` has SQLAlchemy queries and no aiogram imports. `services/streak.py` contains reusable date calculations; `services/scheduler.py` is an asynchronous Telegram delivery loop, not a framework-independent service.
- User-facing bot text belongs in `texts.py`; inline keyboards belong in `keyboards.py`. `utils.py` contains parsing, digit conversion, and timezone helpers.
- Bot middleware provides one async DB session per update; handlers commit their writes. API routes manage commits explicitly.

## Feature Completeness

- Treat each approved feature as an end-to-end product change, not only its primary handler. Before editing, trace all affected user flows, admin controls and analytics, persistence/migrations, authorization/privacy, errors/retries, config/deployment, tests, and documentation.
- For every feature, explicitly decide whether the admin panel needs a new action, KPI, activity event, filter, or report. If yes, implement and test it in the same feature; if no, record why in its spec/PR summary. Never leave admin analytics silently stale when adding a measurable feature.
- Check all clients and paths that share the behavior (Telegram menu/commands/callbacks, API, scheduler/background jobs, profile/weekly summaries, admin dashboard, and leaderboard as applicable). Update the relevant surfaces together or document a justified non-applicability.
- Update current-behavior docs, ROADMAP/spec, tests, and operational handoff in the same task. Use the completeness checklist in `.github/skills/add-feature/SKILL.md` and `docs/DOCS_MAINTENANCE.md`.

## Hard Rules

- Preserve the `BOOKzMA` package name and Python 3.12 compatibility. Ruff line length is 100.
- Keep proxy code out of `src/`. `dev_run.py` is the shared local launcher; maintain it alongside Docker execution and follow [docs/LOCAL_DEV.md](docs/LOCAL_DEV.md).
- Never put real tokens, passwords, keys, DSNs, server details, user data, or database backups in source, tests, docs, issues, prompts, or Git. Never log bot tokens. Do not read `.env`.
- Escape user/external values before inserting them into HTML-mode Telegram messages. Validate callback payloads, including Telegram's 64-byte limit. Any future privileged action must authorize on the server, not merely hide a button.
- Schema changes require a new Alembic revision; never edit an applied migration. Do not use `Base.metadata.create_all()`.
- Avoid blocking work and avoid repeated per-item queries in handlers or request loops. Keep database writes safe under duplicate/concurrent requests.
- Do not add dependencies, expand the API, add Redis/webhooks/admin panels, or implement roadmap items without an approved spec and owner approval.
- Never connect to production, inspect private configuration, run the bot with a real token, or run destructive data commands. Never run `docker compose down -v` unless the owner confirms the data is disposable.

## Minimal Diff and Change Scope

This rule applies to all tasks in this project from now on:

1. **Minimal Diff:** Only change files directly necessary to complete the task. Avoid modifying unrelated files.

2. **No Unnecessary Rewrites:** Do not regenerate files solely for cleanup, standardization, rewriting, structural changes, or cosmetic improvements.

3. **Preserve Formatting:** Preserve existing line endings (LF/CRLF), encoding, spacing, and formatting of files. Do not run formatters on the entire project; only check files directly related to the task.

4. **Preserve Existing Architecture:** Before implementing, review the project's existing structure and patterns. Use existing patterns where possible. Do not change unrelated architecture or conventions for a scoped task.

5. **Protect User Changes:** Do not delete or rewrite prior user changes. Do not use destructive Git commands without explicit confirmation.

6. **Diff Review:** Before completing any task, run `git status --short`, `git diff --stat`, and `git diff --check` and review changes. Ensure all changes directly relate to the task.

7. **Unexpected Diff:** If the number of changed files or diff size is unexpectedly large, stop, investigate the cause, and report it without deleting user changes.

8. **Final Report:** In the final report, list new, modified, and deleted files with the reason for each change.

## Stop and Ask

Ask before adding a dependency, changing schema or deployment configuration, changing streak/reminder semantics or membership/access behavior, deleting data/files, sending messages at scale, or requiring a secret. Bug fixes within an existing layer, focused tests, copy edits, behavior-preserving refactors, and documentation updates may proceed.

## Keep Docs in Sync

Update [ARCHITECTURE.md](ARCHITECTURE.md) and/or [BOT_GUIDE.md](BOT_GUIDE.md) in the same change when structure, commands, callbacks, state, tables, or environment variables change. Follow [docs/DOCS_MAINTENANCE.md](docs/DOCS_MAINTENANCE.md) for other triggers. A change is incomplete while its docs contradict the code.

Mandatory doc updates with every code change:
- Handler change → update `BOT_GUIDE.md` (commands, callbacks, FSM)
- Model/migration change → update `ARCHITECTURE.md` (Data and State)
- New feature → update `docs/ROADMAP.md` status + spec in `docs/specs/`
- Env var change → update `.env.sample` and `BOT_GUIDE.md` Environment table
- API change → update `BOT_GUIDE.md` HTTP API section
- No PR is complete without doc updates; use `docs/DOCS_MAINTENANCE.md` checklist.

Bot text should be natural, clear, modern Persian: neither stiff nor AI-sounding.

## End-of-Task Report

At the end of **every** task, always give the owner a complete handoff — never end with the work alone:

1. Exact commands to run the code locally (including any DB start, migration, and whether Docker rebuild is needed).
2. How to test the change (checks actually run and their real results, plus what to verify manually).
3. Once verified, exact commands to commit, push, and open a PR (with the real branch name), how to merge it, and how to delete the branch locally and remotely afterwards.
4. Any post-merge/deployment steps (backup, migration, tag) that apply.
5. List changed files, checks actually run and their results, unverified areas, updated docs, and owner decisions still needed.

Do not commit or push unless explicitly asked.
