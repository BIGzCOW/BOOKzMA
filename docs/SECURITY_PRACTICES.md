# Security Practices

The root [SECURITY.md](../SECURITY.md) is the vulnerability-reporting policy; do not replace it with this engineering checklist.

## Never Store or Share

Do not commit or paste real bot/API tokens, passwords, DSNs, private keys, server connection details, `.env`, private launcher configuration, production user data, or real database backups into Git, issues, PRs, tests, docs, prompts, logs, or screenshots. Keep `.env` ignored; the shared `dev_run.py` is tracked and must use environment configuration for credentials. `.env.sample` may contain placeholders only. Use synthetic test identities and data.

Before publishing, inspect changed files and staged names for secrets. If a real secret was committed, treat it as compromised: revoke the bot token through BotFather or rotate the affected credential, then coordinate history cleanup with the repository owner. Deleting it in a later commit is not sufficient. Do not rewrite Git history without owner approval.

## Input, Authorization, and Errors

- Validate callback payload format, allowed values, length, and Telegram's 64-byte limit before acting. Parse free text strictly and impose length bounds.
- Escape user- or external-controlled values inserted into Telegram HTML messages.
- Every admin action checks the `ADMIN_TELEGRAM_IDS` allowlist server-side; hiding a button is not authorization. Authorization logs contain the Telegram actor ID, action, and allow/deny result, but never the campaign text. Bulk sends require a preview and explicit confirmation. Keep admin IDs and support handles in runtime configuration, not source control.
- Apply rate limits before expensive work. Use SQLAlchemy expressions and bound parameters; do not concatenate untrusted input into SQL.
- Show users a generic, localized error where appropriate; keep diagnostics in logs without secrets or unnecessary personal data.
- Never log bot tokens or raw Telegram `initData`/bearer tokens. Avoid logging usernames or IDs unless operationally necessary and documented.

## External Data and Dependencies

Check license and attribution obligations before copying external code, text, or images. Ask before adding dependencies. For future external APIs, set timeouts, bound/cache responses, validate data, and escape values before display. Respect book copyright and source terms.

## Privacy and Deletion

Personal-library routes enforce private chats on the server. Group menus/callbacks and callbacks without an accessible chat receive only a generic notice; no book title or progress is rendered. Book queries also constrain owner ID. Navigation clears pending book input so a later page count cannot be applied to a previously selected book. `SimpleEventIsolation` serializes each user/chat's FSM updates within the approved single-instance deployment; page logs additionally have a database idempotency constraint.

Before adding a user-data feature, inventory data in tables, caches, FSM state, files, logs, and backups. Account deletion must use an explicit service operation or verified cascades and a test that confirms deletion. Set a backup retention period and tell users that previously deleted data may remain in old backups until expiry. After restoring a backup, reapply deletions recorded since that backup.

## Docker and Operations

Keep PostgreSQL bound to loopback unless a reviewed deployment design requires otherwise. Avoid privileged containers and unnecessary mounts. Do not put credentials in Dockerfile or Compose literals. Keep secrets in runtime environment configuration. Never run migrations or commands against production from an agent session.

## Repository Findings (Current Audit)

- `.env` is ignored. The shared `dev_run.py` is tracked, confirmed from Git metadata; neither file's contents were inspected for the personal-library change.
- Compose publishes PostgreSQL on `127.0.0.1:5433`; the app is published on `127.0.0.1:8000`. The Docker image runs as UID 10001 and copies only selected source/build inputs.
- `.gitignore` and `.dockerignore` now exclude backup dumps, SQL exports, logs, and Python cache directories in addition to their existing rules.
- `src/BOOKzMA/config.py` has a fixed local fallback database URL with a development username/password. Compose overrides the URL for the app container, but deployments outside Compose must provide a secure `DATABASE_URL`; never treat that default as production-safe.
- No `create_all()` call, raw SQL string concatenation, token logging, or synchronous sleep was found in the scanned application. User-controlled leaderboard names and admin previews are escaped or sent as plain text. The API accepts a `ZoneInfo`-validated timezone string, stores it, and the bot may render it as a fallback label in HTML-mode text; exploitability was not tested, so treat this as a defensive escaping risk, not a confirmed exploit.
- The reminder scheduler logs Telegram user IDs for send failures and blocked-bot cleanup; assess whether the identifiers are operationally necessary and restrict log access/retention. API routes have no rate limiter in the inspected code. Telegram membership failures are logged and fail closed. Some expected Telegram edit failures are intentionally suppressed.
- Broadcast campaigns store message text and per-user delivery state in PostgreSQL. Restrict database/log access and define a retention period before production. Delivery is at-least-once across the Telegram-send/DB-commit failure window; one duplicate after a crash is possible.
- History scan covered nine reachable commits using high-confidence patterns and reported no Telegram-token pattern, private-key marker, or historical `.env`/`dev_run.py` addition. This is not a complete secret-detection guarantee.
