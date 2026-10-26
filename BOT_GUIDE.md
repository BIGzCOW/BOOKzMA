# Bot and API Guide (Current)

This guide records behavior verified in `src/BOOKzMA/`, migrations, and configuration. See [ARCHITECTURE.md](ARCHITECTURE.md) for runtime topology and [docs/LOCAL_DEV.md](docs/LOCAL_DEV.md) for the owner-specific launcher; `dev_run.py` was not read.

## Commands and Bot Interface

`bot.py` registers `/start`, `/reminders`, `/timezone`, `/profile`, `/miswak`, and `/support` for all users. Configured admins also receive `/admin` in their chat command scope. The persistent Persian reply keyboard includes `🤝 رفیق مطالعه` and `🪥 مسباک`; contextual flows continue to use inline keyboards. Admin entry points are checked against `ADMIN_TELEGRAM_IDS` in handlers, independently of menu visibility.

`/start` branches by onboarding state (`users.onboarded_at`, U-01): new users get a short welcome and first-reminder choice; existing users were backfilled in migration `0007`. Returning readers whose last local reading day is more than seven days old (U-02) get a welcome-back line. `buddy_<token>` and `miswakbuddy_<token>` payloads accept separate study-buddy and miswak invitations before the usual onboarding/home flow continues. The intro links to miswak, which is also available through `/miswak` and the reply keyboard.

Callback payloads implemented in handlers/keyboards:

| Payload | Behavior |
| --- | --- |
| `onb:<HHMM>` | Onboarding: add the chosen preset reminder and mark the intro complete (validated against `PRESET_TIMES`) |
| `onb:skip` | Onboarding: skip the first reminder and mark the intro complete |
| `home` | Clear FSM state and render home |
| `check_join` | Recheck required channel membership |
| `read` | Record today's reading idempotently; after a new reading, offer an optional nudge only when an eligible buddy has not read today |
| `weekly` | Show seven-day summary |
| `rem` | Open reminder management |
| `rem_add:<HHMM>` | Add one of the configured preset times |
| `rem_del:<id>` | Delete the current user's reminder |
| `rem_custom` | Request a custom reminder time |
| `tz` | Show timezone choices |
| `tz_set:<index>` | Set one of the configured timezone choices |
| `leaderboard:toggle` | Toggle the user's public leaderboard presence |
| `leaderboard` | Show the current-streak leaderboard (display names only) |
| `miswak:open` | Open the optional independent miswak section |
| `miswak:join:<goal>` | Join with a daily goal from 1 to 5 and default reminder times |
| `miswak:exit` | Leave the section, stop reminders and future cohort delivery, and close social opt-ins |
| `miswak:done:<YYYYMMDD>:<slot>` | Record one dated occurrence; stale-day and duplicate callbacks are rejected |
| `miswak:goal:<goal>` | Schedule a new daily goal for the next local day |
| `miswak:time:<slot>` / `miswak:settime:<slot>:<HHMM>` | View or change one occurrence reminder |
| `miswak:weekly` / `miswak:monthly` | Show 7-day or 30-day completion and streak reports |
| `miswak:challenge:start:<7|30>` | Start one personal consecutive-day challenge |
| `miswak:league` / `miswak:league:toggle` | View or opt in/out of the miswak-only weekly league |
| `miswak:buddy:invite` / `miswak:buddy:nudge:<id>` / `miswak:buddy:end:<id>` | Invite, nudge, or end a separate miswak buddy pair |
| `account_del:start` | Start the account-deletion wizard from the profile |
| `account_del:why` | Show the deletion-reason choices |
| `account_del:reason:<index>` | Record a reason (validated against `DELETE_REASONS`) and ask for the typed confirmation word |
| `account_del:go` | Final confirmation: delete the account and all of its data |
| `account_del:cancel` | Cancel the deletion flow at any step and return to the profile |
| `account_restore` | Explicit re-registration: clear the deletion tombstone and start fresh |
| `buddy:invite` | Create a seven-day, one-time link for a known friend; neither user may be in the anonymous queue when pairing |
| `buddy:join` | Join the study-buddy FIFO queue and match with the oldest waiting user inside a locked transaction |
| `buddy:leave` | Leave the buddy queue |
| `buddy:list` | Return to the list of the user's active study buddies |
| `buddy:open:<pair_id>` | Open a pair owned by the current user |
| `buddy:nudge:all` | Nudge all active buddies who have not read today and have not already been nudged today; show sent/skipped counts |
| `buddy:nudge:dismiss` | Dismiss the optional post-reading nudge prompt |
| `buddy:nudge:<pair_id>` | Send that buddy a nudge; capped at one per pair per local day |
| `buddy:end:<pair_id>` | End that pair; other buddy relationships remain active |
| `admin:stats` | Show admin analytics; server-side admin check required |
| `admin:broadcast` | Start a text or media campaign draft; server-side admin check required |
| `admin:backup` | Open the backup menu (latest backup, on-demand backup, restore); server-side admin check required |
| `admin:backup_now` | Run an on-demand `pg_dump` through `services/backup.py`; server-side admin check required |
| `admin:backup_restore` | List local backup files; server-side admin check required |
| `admin:restore_ask:<index>` | Show the destructive-restore warning for the listed backup (index into the current `list_backups` order, never free text) |
| `admin:restore_ready:<index>` | Ask for the typed confirmation word and arm the restore FSM state |
| `broadcast:audience:<all|miswak>` | Select all reachable users or active miswak members for a campaign |
| `broadcast:start:<id>` | Confirm an owned campaign |
| `broadcast:status:<id>` | Show counts for an owned campaign |
| `broadcast:cancel:<id>` | Cancel an owned campaign |

FSM states are `handlers.reminders.AddTime.waiting`, `handlers.miswak.SetReminderTime.waiting`, `handlers.admin.NewBroadcast.waiting_for_content`, `handlers.admin.NewBroadcast.waiting_for_link`, `handlers.admin.BackupRestore.waiting_for_confirm`, and `handlers.account.DeleteAccount.waiting_word`; FSM storage remains in-memory. Onboarding is stateless and callback-driven. Arbitrary reminder times are parsed as 24-hour `HH[:MM]` with Persian or Arabic digits accepted.

Account deletion (`N-04`) is a four-step wizard started from the profile: a warning screen, a deletion-reason choice, a typed confirmation word (`حذف`), and a final button. Deletion removes the `users` row (cascading to all related tables) and inserts a `deleted_accounts` tombstone in the same transaction. The membership middleware intercepts tombstoned users before handlers run — they get a neutral start prompt (no mention of a previous account) and no activity or start is recorded for them; the `account_restore` callback clears the tombstone. The API exposes the same behavior through `DELETE /api/v1/me`, and authenticated requests for tombstoned users return 401 until they re-register via the bot.

Database backup and restore (`N-05`, decision D-09): the admin panel's backup section runs `pg_dump -Fc` over TCP to the database from inside the bot container (the image installs `postgresql-client`) into `BACKUP_DIR` (`/backups` in Compose, bind-mounted from `BOOKZMA_BACKUP_DIR` on the host), keeping only `BACKUP_KEEP_LOCAL` (default 1) newest dumps named `bookzma-YYYY-MM-DD-HHMMSS.dump`. Restore is destructive: warning screen, typed confirmation word (`بازیابی`), then `pg_restore --clean --no-owner --no-acl` against the current database; a restart (`docker compose restart bot`) is recommended afterwards and stated in the completion message. Restore file names are validated against the backup-name pattern (no path traversal) and can only be selected by index from the real file listing. All backup callbacks re-check the admin allowlist server-side. Daily scheduling and Google Drive upload are host-side (`scripts/backup.py`); see [docs/BACKUP.md](docs/BACKUP.md) for the runbook.

## HTTP API

The existing FastAPI app is in `api.py`; the container runs it through Uvicorn. Authentication validates Telegram Web App `initData`, then returns an HS256 bearer token derived from the bot token with a one-hour lifetime. Protected routes identify users from that token.

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Process-level status response |
| `POST /api/v1/auth/telegram` | Exchange signed Telegram `initData` for a bearer token |
| `GET /api/v1/me` | Read/create the authenticated user profile |
| `PUT /api/v1/me/timezone` | Update timezone |
| `DELETE /api/v1/me` | Delete the authenticated account and all of its data; later requests return 401 |
| `GET /api/v1/me/weekly-summary` | Read the seven-day summary |
| `POST /api/v1/me/read` | Record today's reading |
| `GET /api/v1/me/reminders` | List the authenticated user's reminders |
| `POST /api/v1/me/reminders` | Add a reminder; returns conflict for duplicate/limit |
| `DELETE /api/v1/me/reminders/{reminder_id}` | Delete the authenticated user's reminder |

`WEB_ORIGINS` is a comma-separated CORS allowlist; CORS middleware is only installed when it contains an origin. `/docs` is FastAPI's interactive schema UI. The health route does not check database or Telegram health. The API routes do not use the bot's channel-membership middleware.

## Data and Limits

| Table | Current shape and invariant |
| --- | --- |
| `users` | Telegram ID primary key; optional display name/username; timezone defaults to `Asia/Tehran`; first-start and onboarding-completion timestamps; comeback state (`broken_streak_days`, `comeback_bonus_days`, `comeback_base_day`); leaderboard opt-out and permanent broadcast-unavailable flags |
| `reading_logs` | `(user_id, day)` composite primary key; user foreign key cascades on delete |
| `streak_freezes` | Earned/used freeze events, separate from reading logs; unique `(user_id, kind, day)` |
| `activity_days` | One row per user and UTC date; cascades with user deletion |
| `streak_alerts` | Daily dedup for streak-at-risk alerts; composite `(user_id, day)` primary key; cascades with user deletion |
| `badges` | Awarded achievement badges: integer id, user foreign key, `code` from `services/badges.py`, local awarded day; unique `(user_id, code)`; cascades with user deletion |
| `buddy_queue` | Study-buddy FIFO waiting list: user primary key, join timestamp; cascades with user deletion |
| `buddy_pairs` | Buddy pairs with `active`/`ended` status, ended-by metadata, and the last nudge date used for the one-nudge-per-day cap. A partial unique index on `(user_a, user_b)` prevents duplicate active relationships while allowing each user to have multiple buddies; rows cascade on user deletion, which silently frees the surviving partner. |
| `buddy_invites` | One active link per inviter; stores a SHA-256 token hash and seven-day expiry only. Successful pairing consumes the link; existing buddy pairs remain active, users in the anonymous queue do not change state, and account deletion cascades invitations. |
| `deleted_accounts` | Deletion tombstone: Telegram ID primary key (no foreign key), deletion timestamp, optional reason code from `DELETE_REASONS`; prevents silent re-registration |
| `broadcast_campaigns` | Admin-owned campaign with audience, optional photo/video and HTTPS button, and delivery state |
| `broadcast_deliveries` | Per-campaign/per-user state, attempt count and last error; cascades on user/campaign deletion. Users with permanent Telegram delivery failures are excluded from later broadcasts. |
| `reminders` | Integer primary key; user foreign key; time; last-sent date; retry date/count/deadline; unique `(user_id, remind_at)` |
| `miswak_profiles` | One opt-in profile per user; active flag, goal 1–5, next-day goal change, and separate league opt-in |
| `miswak_entries` | `(user_id, local day, occurrence slot)` primary key; goal snapshot; unique slot writes make duplicate callbacks idempotent |
| `miswak_reminders` | Up to five independent local times, one per goal slot; unique per user/time with separate send/retry state |
| `miswak_badges` | Independent 7/30/100-day streak badges; unique `(user_id, code)` |
| `miswak_challenges` | One active personal 7- or 30-day consecutive completion challenge per user; canceled after a missed, closed local day |
| `miswak_buddy_invites` / `miswak_buddy_pairs` | Hashed, one-time, seven-day invite tokens; independent opt-in pairs and once-per-day nudges |

Reading streak is computed from read dates plus explicitly used freeze dates; freeze days are not reported as reading. Users start with zero freezes, earn one per seven consecutive real reading days, and hold at most two. One missed day is automatically protected when reading resumes the next day; freezes cannot cover consecutive missed days. Weekly summaries cover today and the preceding six local dates. Reading reminders are capped at five per user; presets are `08:00`, `13:00`, `18:00`, `21:00`, and `23:00`.

Comeback streak (`S-07`): when a displayed streak of three or more days breaks, the next reading day opens a comeback window on `users` (`broken_streak_days`, `comeback_base_day`, `comeback_bonus_days`). Three consecutive reading days award half of the broken streak (floor, capped at 30) as a bonus. Surfaces that display the streak (home, profile, weekly summary, leaderboard, reminder pushes, read toast) show the raw streak plus the bonus via `displayed_streak`; the bonus becomes inert once the chain that earned it breaks and never affects `longest_streak`, freeze earning, or admin analytics (which use the raw streak). A frozen day covering the break keeps the streak alive, so no comeback window opens.

Streak-at-risk alerts (`S-08`): a third background loop (`services/risk_alert.py`, 60-second interval) messages users at 21:00–21:10 local time when their raw streak is at least two days, the chain is intact through yesterday, and today is unread. Sends are deduplicated per user and local day in `streak_alerts`; a send failure marks the day as alerted anyway, and a downtime window longer than ten minutes skips that day entirely.

Admin analytics count starts, UTC daily interactions, reading activity, onboarding completions, streak-at-risk alerts, comeback bonuses, badge awards, study-buddy pairs, deleted accounts, and D1/D7/D30 return rates for sufficiently observed cohorts. Miswak entry also records a starter. Buddy nudges skip friends who have read or already received a nudge that day; bulk-nudge prompts appear only when eligible buddies remain. Nudge counts are shown to the user but are not separate admin KPIs. Streak KPIs use raw reading streaks.

Broadcast campaigns snapshot recipients, require admin confirmation, allow one active campaign, send at 5 messages per second with bounded retries, and resume after restart. Campaigns can target all users or active miswak members and support text or one photo/video with an optional HTTPS button; membership is rechecked before each queued delivery. A crash after Telegram accepts a message but before the database update may cause one duplicate. Deleting an account mid-campaign or reminder sweep is safe; updates to deleted rows are no-ops.

Miswak is a separate, opt-in habit with 1–5 daily occurrences. Each occurrence is recorded once per local date, and a day counts only when its goal is complete. Goal changes take effect the next local day; miswak streaks do not use reading freezes or comeback bonuses. Its reminder loop scans every 30 seconds, skips sends over ten minutes late and after the goal is complete, and caps retries at three per slot/day. DST gaps are skipped and ambiguous fall-back times are sent once. Challenges, the weekly league, and one-time buddy links are opt-in and isolated from reading social data. Leaving miswak disables reminders, clears league consent, ends active challenges and buddy pairs, removes outgoing invites, and removes the user from future cohort campaigns while retaining habit history.

Membership checks run for bot messages and callbacks, except the `check_join` callback itself and the `account_restore` callback. Required channels come from `REQUIRED_CHANNELS`, defaulting to an empty list if unset. Only successful checks are cached, per process, for 300 seconds. A membership-check Telegram error is treated as not joined. Every update also performs one indexed tombstone lookup (`deleted_accounts`) before handlers run, so deleted users never reach `get_or_create`.

A per-process rate-limit middleware (`middlewares/rate_limit.py`, decision D-10) runs before the membership middleware for messages and callbacks: a user may send at most `RATE_LIMIT_MAX_UPDATES` updates (default 20) per `RATE_LIMIT_WINDOW_SECONDS` (default 10). Admins are exempt. A blocked update never reaches a handler or the DB session; the user gets the rate-limit text at most once per window and the event is logged (`log.warning`), not counted in admin analytics. The window state is in-memory and resets on restart.

## Environment

| Variable | Read by | Current behavior |
| --- | --- | --- |
| `BOT_TOKEN` | `Settings` | Required; stored as `SecretStr` |
| `POSTGRES_PASSWORD` | Compose | Required to configure the PostgreSQL container and bot `DATABASE_URL` |
| `DATABASE_URL` | `DatabaseSettings` / Compose | Optional in local settings (default points to local PostgreSQL); Compose constructs the bot URL from the password |
| `REQUIRED_CHANNELS` | `constants.py` | Optional comma-separated channel identifiers; defaults to none |
| `WEB_ORIGINS` | `Settings` / API | Optional comma-separated CORS origins |
| `ADMIN_TELEGRAM_IDS` | `Settings` / bot | Optional comma-separated numeric Telegram IDs; empty means no admins |
| `GITHUB_URL` | `Settings` / support menu | Optional GitHub project URL; only GitHub repository URLs are shown |
| `SUPPORT_TELEGRAM_USERNAME` | `Settings` / support menu | Optional Telegram username for private financial-support contact |
| `BOOKZMA_BACKUP_DIR` | Compose | Required by Compose; host folder bind-mounted into the bot at `/backups`; must be outside the repository |
| `BACKUP_DIR` | `Settings` / backup service | Backup folder inside the container; defaults to `/backups` |
| `BACKUP_KEEP_LOCAL` | `Settings` / backup service | Number of newest local backups to keep after rotation; defaults to 1 |
| `RATE_LIMIT_MAX_UPDATES` | `Settings` / rate-limit middleware | Optional; max updates per user per window across messages and callbacks; defaults to 20 |
| `RATE_LIMIT_WINDOW_SECONDS` | `Settings` / rate-limit middleware | Optional; fixed window length in seconds; defaults to 10 |
| `TELEGRAM_PROXY` | `Settings` / local `dev_run.py` | Optional aiogram proxy URL; used only by the ignored host launcher, not Docker |
| `LOG_LEVEL` | `Settings` | Defaults to `INFO`; no logging configuration consuming it was found |

`.env.sample` documents the variables above and an optional placeholder `DATABASE_URL` for local tools. Set the real owner ID and support destinations in the runtime environment; do not commit them. Code supplies a default database URL and Compose overrides it for the bot container. The local launcher uses `TELEGRAM_PROXY` to create an aiogram session; `requirements-dev.txt` includes the optional SOCKS support dependency. Docker leaves the session unset and connects directly.

## Verified Caveats

- The application runs migrations automatically during API lifespan startup by default.
- Telegram polling, reminder work, FSM storage, membership cache, and rate-limit windows are process-local; use one application instance.
- Reminder delivery holds a DB session while scanning and sending. Each candidate may cause additional reads; consult [docs/PERFORMANCE.md](docs/PERFORMANCE.md) before changing this path.
- Bot updates are rate-limited per user (D-10); no rate limiter for HTTP endpoints was found. Callback handlers validate preset values, numeric IDs, and timezone indexes, but changes must continue to enforce payload parsing and Telegram's 64-byte callback-data limit.