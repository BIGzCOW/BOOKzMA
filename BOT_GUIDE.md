Admin analytics count starts and UTC daily interactions from deployment onward, and report reading logs separately. A user who enters through `/mesbak` without `/start` is also recorded as a starter. The dashboard also reports onboarding completions, streak-at-risk alerts, comeback users, badge holders, active/total study-buddy pairs, deleted accounts, active/finished/archived personal books, books added/archived and page-count changes in seven days, page sessions/pages logged in seven days, open/new support tickets, user messages/admin replies and blocked users, plus D1/D7/D30 return rates for sufficiently observed cohorts.
# Bot and API Guide (Current)

This guide records behavior verified in `src/BOOKzMA/`, migrations, and configuration. See [ARCHITECTURE.md](ARCHITECTURE.md) for runtime topology and [docs/LOCAL_DEV.md](docs/LOCAL_DEV.md) for the local developer launcher.

## Commands and Bot Interface

`bot.py` exposes only `/start` in the public Telegram command menu; other existing commands remain callable for compatibility and the reply keyboard is the primary navigation. Configured admins see `/start` and `/admin` in their private command scope. The primary Persian reply keyboard contains Home, Profile, Personal Library, Mesbak, Study Buddy, and More. Profile opens a reply-keyboard submenu; profile settings contain Reminders and Timezone. More contains Weekly Summary, Leaderboard, Support, project support, and the admin entry for allowlisted admins. Mesbak opens its own reply-keyboard submenu with Today, Mesbak Buddies, Reports, Settings, Challenges, League, and Home. Reports opens 7-day/30-day choices; Settings contains Daily Goal, Reminder Times, Exit Mesbak, Back to Mesbak, and Home. Exit from either the reply keyboard or the inline settings callback disables Mesbak and restores the primary reply keyboard. Each submenu has a Home action. Home's inline keyboard contains only the primary reading action, avoiding duplicates for destinations already on the reply keyboard. Contextual flows continue to use inline keyboards. Existing `📚 کتابخانهٔ من` messages remain accepted for compatibility. Callback buttons use Telegram's success, danger, and primary styles; URL buttons omit `style` and use the Telegram client's default link appearance. Admin entry points are checked against `ADMIN_TELEGRAM_IDS` in handlers, independently of menu visibility.

`/start` retains the optional onboarding, returning-reader welcome, and study-buddy invite flow. Its first-run screen has a direct button to the independent Mesbak section. Buddy invitations use one-time `mesbakbuddy_<token>` deep links. Users can also open the section through `/mesbak` or the reply keyboard without completing reading onboarding.

Callback payloads implemented in handlers/keyboards:

| Payload | Behavior |
| --- | --- |
| `onb:<HHMM>` | Onboarding: add the chosen preset reminder and mark the intro complete (validated against `PRESET_TIMES`) |
| `onb:skip` | Onboarding: skip the first reminder and mark the intro complete |
| `home` | Clear FSM state and render home |
| `check_join` | Recheck required channel membership |
| `read` | Record today's reading idempotently; after a new reading, offer an optional nudge only when an eligible buddy has not read today |
| `weekly` | Show seven-day summary |
| `books` / `books:p:<page>` | Open or paginate the current user's non-archived personal books |
| `books:archive` / `books:archive:p:<page>` | View and paginate the current user's archived books |
| `catalog:search` / `catalog:p:<offset>` | Search the main-channel book catalog privately and paginate results |
| `catalog:open:<message_id>` / `catalog:back` | Show a catalog result or return to the last search |
| `catalog:add:<message_id>` / `catalog:download:<message_id>` | Add a result to the personal library or copy its channel post to the user |
| `book:add` / `book:author_skip` | Start manual book creation or skip its optional author |
| `book:open:<id>` | Show an owned book's page progress |
| `book:note:<id>` / `book:note:edit:<id>` / `book:note:clear:<id>` | View, edit, or clear the current user's private note for an owned book |
| `book:log:<id>` | Request pages read for an owned active book |
| `book:set_pages:<id>` | Set the page count of an active catalog book that was added without one |
| `book:archive:<id>` / `book:archive_go:<id>` | Confirm and archive an owned book without deleting its history |
| `book:restore:<id>` | Restore an owned archived book to its previous inferred status |
| `support:ticket` | Start a private support message; the bot forwards it to configured admins |
| `support:continue:<ticket_id>` | Continue the user's open support ticket |
| `support:reply:<ticket_id>` | Admin-only reply flow for an open ticket |
| `support:block:<ticket_id>` | Admin-only toggle to block/unblock that ticket's user |
| `rem` | Open reminder management |
| `rem_add:<HHMM>` | Add one of the configured preset times |
| `rem_del:<id>` | Delete the current user's reminder |
| `rem_custom` | Request a custom reminder time |
| `tz` | Show timezone choices |
| `tz_set:<index>` | Set one of the configured timezone choices |
| `leaderboard:toggle` | Toggle the user's public leaderboard presence |
| `leaderboard` | Show the top 25 current reading streaks (display names only) |
| `mesbak:open` | Open the optional independent Mesbak section |
| `mesbak:join:<goal>` | Join with a daily goal from 1 to 5 and default reminder times |
| `mesbak:exit` | Leave the section, stop reminders and future cohort delivery, close social opt-ins, and restore the primary reply keyboard |
| `mesbak:done:<YYYYMMDD>:<slot>` | Record one dated occurrence; stale-day and duplicate callbacks are rejected |
| `mesbak:goal:<goal>` | Schedule a new daily goal for the next local day |
| `mesbak:time:<slot>` / `mesbak:settime:<slot>:<HHMM>` | View or change one occurrence reminder |
| `mesbak:weekly` / `mesbak:monthly` | Show 7-day or 30-day completion and streak reports |
| `mesbak:challenge:start:<7|30>` | Start one personal consecutive-day challenge |
| `mesbak:league` / `mesbak:league:toggle` | View the top 25 members or opt in/out of the Mesbak-only weekly league |
| `mesbak:buddy:invite` / `mesbak:buddy:open:<id>` / `mesbak:buddy:nudge:all` / `mesbak:buddy:nudge:<id>` / `mesbak:buddy:end:<id>` | Invite, open one buddy's screen, nudge all incomplete buddies, nudge, or end a separate Mesbak buddy pair |
| `mesbak:buddy:random:join` / `mesbak:buddy:random:leave` | Join or leave the anonymous FIFO Mesbak matching queue; users may hold several buddies at once, and matching never pairs two users who already have an active pair |
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
| `broadcast:audience:<all|mesbak>` | Select all reachable users or active Mesbak members for a campaign |
| `admin:backup` | Open the backup menu (latest backup, on-demand backup, restore); server-side admin check required |
| `admin:backup_now` | Run an on-demand `pg_dump` through `services/backup.py`; server-side admin check required |
| `admin:backup_restore` | List local backup files; server-side admin check required |
| `admin:restore_ask:<index>` | Show the destructive-restore warning for the listed backup (index into the current `list_backups` order, never free text) |
| `admin:restore_ready:<index>` | Ask for the typed confirmation word and arm the restore FSM state |
| `broadcast:start:<id>` | Confirm an owned campaign |
| `broadcast:status:<id>` | Show counts for an owned campaign |
| `broadcast:cancel:<id>` | Cancel an owned campaign |

FSM states include `handlers.books.AddBook.waiting_for_title/waiting_for_author/waiting_for_total_pages`, `handlers.books.LogPages.waiting_for_pages`, `handlers.books.SetBookPages.waiting_for_total_pages`, `handlers.books.EditBookNote.waiting_for_note`, `handlers.catalog.SearchCatalog.waiting_for_query`, `handlers.reminders.AddTime.waiting`, the Mesbak reminder-time state, `handlers.admin.NewBroadcast.waiting_for_content/waiting_for_link`, `handlers.admin.BackupRestore.waiting_for_confirm`, and `handlers.account.DeleteAccount.waiting_word`; FSM storage remains in-memory. A restart discards an unfinished book form without persisting partial data. The existing onboarding flow remains stateless callback-driven and needs no FSM state. Arbitrary reminder times are parsed as 24-hour `HH[:MM]` with Persian or Arabic digits accepted.

Personal-library menus, forms, and personal-book callbacks are private-chat only. The shelf paginates at eight books per page and summarizes total, reading, finished, planned, unstarted, and archived counts; a book counts as reading in that summary only after at least one page is logged. Up to five started-book titles are shown. Archived books remain available from the paginated archive shelf; restore returns finished books to `finished`, catalog-planned books with no page count to `planned`, and other books to `reading`, preserving page logs and `archived_at` history. Each book may have one private, owner-only note up to 3,500 characters; note text is HTML-escaped and excluded from admin analytics. There is no cap on a user's total or active books. Catalog Inline Mode is a separate group-capable sharing flow and always returns an Article linking to the channel post, never the file itself. Catalog text search uses Meilisearch and remains separate from the personal shelf. Existing menu buttons and commands take precedence over book inputs; navigating to another screen discards the pending book form, including its selected book ID. Unknown slash commands are not accepted as book titles or authors. Per-user/chat FSM event isolation ensures a concurrent or replayed final form message cannot create a second book after successful submission; a restart loses the form rather than resubmitting it. This is a single-process FSM guarantee, not durable deduplication for arbitrary future clients.

Support messages use the configured `ADMIN_TELEGRAM_IDS` allowlist: private user messages are copied to admins, admin replies may contain text or media, and each user reply button continues the same open ticket. Admins can block/unblock the ticket owner. PostgreSQL stores ticket status and event metadata (actor ID, direction, timestamp) but never message text, file IDs, or media; account deletion cascades ticket metadata and blocks. Replies require the bot to be able to message that user.

The channel catalog is a PostgreSQL metadata mirror plus a derived Meilisearch index. The SQLite source is opened read-only in a worker thread and scanned in short batches once daily at the configured UTC hour; the bot does not sync on startup. Only valid main-channel rows are mirrored. Filename/caption-derived documents are hashed so unchanged rows do not generate PostgreSQL or Meilisearch writes; source removals and edits are reconciled. PostgreSQL commits each mirror change and a deduplicated `book_catalog_index_outbox` operation atomically, then Meilisearch task completion is awaited before the outbox row is acknowledged. `raw_data`, file contents, and other source channels are excluded. Search reads Meilisearch; PostgreSQL remains the source for result details, private actions, and `user_books.catalog_message_id`. Run `python -m BOOKzMA.reindex_catalog` manually for initial indexing or recovery; it uses 10K-document batches and validates counts without blocking app startup. `/setinline` must be enabled in BotFather. Inline always returns Article links to the original post, never cached documents. Private result delivery remains `copyMessage` and does not download/re-upload the file.

Catalog queries require at least two characters; generic one-word queries are allowed. Private search shows six results per page; Inline shows 20 and uses a bounded numeric offset. The PostgreSQL `search_text`/GIN vector remains as legacy rollback data but is not used by the search handlers.

Catalog books are added to the user's `user_books` with `total_pages = NULL`. The user may set the page count later using `book:set_pages:<id>`; page logging is rejected until then. Manual book creation still asks for the page count during its existing form. A unique `(user_id, catalog_message_id)` constraint makes repeated catalog additions idempotent.

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
| `user_books` | User-owned books with title, optional author, optional private note (up to 3,500 characters), optional total pages (1–100,000 when set), optional source `catalog_message_id`, `reading`/`finished`/`archived` status, page-count-set and lifecycle timestamps; no per-user book-count cap; a unique `(user_id, catalog_message_id)` prevents duplicate catalog additions |
| `support_tickets` | Open/closed ticket metadata for a user; message contents and attachments are not stored |
| `support_events` | Ticket ID, actor ID, event kind (`user_message`/`admin_reply`) and timestamp only; cascades with ticket deletion |
| `support_blocks` | User ID and blocking admin ID; account deletion cascades the block |
| `page_logs` | Page increments for a book and local day; positive bounded pages and unique `(user_book_id, source_message_id)` make Telegram message retries idempotent; cascades through the owned book |
| `book_catalog_entries` | PostgreSQL mirror of main `BOOKzMA` channel metadata only; message ID primary key, source-row ID, filename/caption/media metadata, optional legacy Bot API file ID, indexed-document hash and dormant `search_text`/GIN vector for rollback; no file bytes or raw Telethon payload |
| `book_catalog_sync_state` | Singleton `main` high-water source row, last successful full reconcile time, and last exception class |
| `book_catalog_index_outbox` | One deduplicated pending upsert/delete per Telegram message ID; stores only the Meilisearch metadata document, revision, attempts and last exception class |
| `streak_freezes` | Habit-specific (`reading`/`mesbak`) earned/used/gifted quantities; real events are unique by user/habit/kind/day; gifts link to an audited operation; cascades with user deletion |
| `freeze_gift_operations` | Admin, habit, audience, requested amount, preview/result totals, status and timestamps; no user names or message content |
| `freeze_gift_recipients` | Per-operation user snapshot, preview/credited amounts and result; user and operation FKs cascade |
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
| `reminder_messages` | Delivered reminder IDs by user, habit, schedule and local date; cleanup-pending/retry state; message text is not stored; cascades with user deletion; tracking rows expire after 48 hours |
| `mesbak_profiles` | One opt-in profile per user; active flag, goal 1–5, next-day goal change, and separate league opt-in |
| `mesbak_entries` | `(user_id, local day, occurrence slot)` primary key; goal snapshot; unique slot writes make duplicate callbacks idempotent |
| `mesbak_reminders` | Up to five independent local times, one per goal slot; unique per user/time with separate send/retry state |
| `mesbak_badges` | Independent 7/30/100-day streak badges; unique `(user_id, code)` |
| `mesbak_challenges` | One active personal 7- or 30-day consecutive completion challenge per user; canceled after a missed, closed local day |
| `mesbak_buddy_invites` / `mesbak_buddy_pairs` | Hashed, one-time, seven-day invite tokens; independent opt-in pairs (several simultaneous buddies allowed) and once-per-day nudges |
| `mesbak_buddy_queue` | One waiting row per active Mesbak member; removed on match, leaving the queue, Mesbak opt-out, or account deletion |

Reading streak is computed from read dates plus explicitly used reading Freeze dates; Freeze days are not reported as reading. Reading starts with zero freezes, earns one per seven consecutive real reading days, and holds at most three. Mesbak has a separate zero-starting balance, earns one per seven consecutive real completed-goal days, and also caps at three. Each habit may protect one missed local day when activity resumes the next day and the preceding day was real; protected days preserve only that habit's streak and never count as activity or reward progress. Admin gifts are previewed and confirmed, target all current users for reading or active Mesbak members for Mesbak, top up only to three, create no activity rows, and send no user broadcast. Weekly reading summaries cover today and the preceding six local dates. Reading reminders are capped at five per user; presets are `08:00`, `13:00`, `18:00`, `21:00`, and `23:00`. Successful reading reminder sends store their Telegram message ID; after a same-day reading is recorded, other reading reminders are deleted, while the callback message being used for registration is retained and updated. Cleanup failures retry from the durable delivery table; old tracking rows expire after 48 hours.

Personal-library progress is derived from page-log sums rather than a mutable counter. Users may log several reading sessions for the same book/local day; every distinct Telegram message is counted once. The book row is locked while checking remaining pages, and reaching the declared total automatically marks it finished. Only a successful positive page log creates the existing idempotent `reading_logs` row in the same transaction and runs the same freeze, comeback, badge, reminder-suppression, and buddy-nudge behavior as the `read` callback; adding a book, setting its total pages, or archiving it does not register a reading day. Archiving retains the book and page logs and moves it to a separate paginated archive shelf; unarchiving archived books and correcting page logs are not implemented. Catalog-added books show direct post and file-download buttons in their details.

The displayed progress percentage is rounded down: 199/200 pages shows 99%, and 100% is shown only once the declared total has been reached.

Comeback streak (`S-07`): when a displayed streak of three or more days breaks, the next reading day opens a comeback window on `users` (`broken_streak_days`, `comeback_base_day`, `comeback_bonus_days`). Three consecutive reading days award half of the broken streak (floor, capped at 30) as a bonus. Surfaces that display the streak (home, profile, weekly summary, leaderboard, reminder pushes, read toast) show the raw streak plus the bonus via `displayed_streak`; the bonus becomes inert once the chain that earned it breaks and never affects `longest_streak`, freeze earning, or admin analytics (which use the raw streak). A frozen day covering the break keeps the streak alive, so no comeback window opens.

Streak-at-risk alerts (`S-08`): a third background loop (`services/risk_alert.py`, 60-second interval) messages users at 21:00–21:10 local time when their raw streak is at least two days, the chain is intact through yesterday, and today is unread. Sends are deduplicated per user and local day in `streak_alerts`; a send failure marks the day as alerted anyway, and a downtime window longer than ten minutes skips that day entirely.

Admin analytics count starts and UTC daily interactions from deployment onward, and report reading logs separately. A user who enters through `/mesbak` without `/start` is also recorded as a starter. The dashboard also reports onboarding completions, streak-at-risk alerts, comeback users, badge holders, active/total study-buddy pairs, deleted accounts, active/finished personal books, pages logged in the last seven local dates, and D1/D7/D30 return rates for sufficiently observed cohorts. Study-buddy nudges skip friends who have read or already received a nudge that day; eligible readers may see an optional prompt after reading. Streak KPIs use raw reading streaks. Broadcast campaigns snapshot recipients, require admin confirmation, allow one active campaign, send at 5 messages per second with bounded retries, and resume after restart. The mesbak cohort can receive text or one photo/video with an optional HTTPS button; membership is checked again before each queued delivery. A crash after Telegram accepts a message but before the database update may cause one duplicate.
mesbak is an optional, separate habit. Active users choose 1–5 daily occurrences; defaults are `06:30`, `13:00`, `16:00`, `19:00`, and `22:00`. For goals smaller than five, the latest N times are selected (one occurrence defaults to `22:00`; two default to `19:00` and `22:00`); all are editable. Each occurrence is recorded once per local date and the day counts toward the streak only when its goal is complete. Goal changes take effect the next local day. Current streak remains alive through today if yesterday was complete; a Mesbak Freeze can preserve a single missed day, but it does not complete the goal or advance challenge progress. Its reminder loop scans every 30 seconds, skips sends over ten minutes late and after the goal is complete, and caps retries at three per slot/day. Successful sends store message IDs; after the daily goal completes, same-day Mesbak reminder messages are deleted, with the clicked callback message retained and updated. Cleanup is retried durably and delivery IDs expire after 48 hours. At spring DST gaps, a nonexistent wall-clock time is skipped; an ambiguous fall-back time is sent once. A challenge is canceled after any previous local day closes without a completed goal; today remains open until its day ends.

Leaving the mesbak section disables reminders, clears league consent, ends active challenges and buddy pairs, removes outgoing invites, and removes the user from future education campaign deliveries while retaining habit history; account deletion cascades all feature data. Active members are told they can receive admin education messages; there is no separate education opt-out. Campaigns support text or one photo/video, optional HTTPS button, preview/recipient count, and confirmation. Audience membership is snapshotted at draft time and rechecked immediately before sending. The dashboard reports only the current active cohort's 7/30-day activity and completion rate. The 7/30-day challenges, weekly league, and one-time buddy links are opt-in and isolated from reading social data.

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
| `TELEGRAM_PROXY` | `Settings` / local `dev_run.py` | Optional aiogram proxy URL; used only by the tracked host launcher, not Docker |
| `BOOKZMA_BACKUP_DIR` | Compose | Required by Compose; host folder bind-mounted into the bot at `/backups`; must be outside the repository |
| `BACKUP_DIR` | `Settings` / backup service | Backup folder inside the container; defaults to `/backups` |
| `BACKUP_KEEP_LOCAL` | `Settings` / backup service | Number of newest local backups to keep after rotation; defaults to 1 |
| `RATE_LIMIT_MAX_UPDATES` | `Settings` / rate-limit middleware | Optional; max updates per user per window across messages and callbacks; defaults to 20 |
| `RATE_LIMIT_WINDOW_SECONDS` | `Settings` / rate-limit middleware | Optional; fixed window length in seconds; defaults to 10 |
| `BOOKZMA_CATALOG_DB_HOST_DIR` | Compose | Host directory containing the external SQLite file; mounted read-only at `/catalog` |
| `CHANNEL_CATALOG_DB_PATH` | `Settings` / catalog sync | Optional SQLite path inside the container (for example `/catalog/channel_data.db`); unset disables source sync, not search of an existing Meilisearch index |
| `CHANNEL_CATALOG_CHANNEL_USERNAME` | `Settings` / catalog sync | Main-channel allowlist; defaults to `BOOKzMA` and must match SQLite `channels.is_main=1` |
| `CHANNEL_CATALOG_SYNC_HOUR_UTC` | `Settings` / catalog sync | UTC hour for the daily full reconcile; defaults to 3; no sync runs at startup |
| `MEILI_URL` | `Settings` / search client | Optional Meilisearch URL; Compose overrides it to `http://meilisearch:7700`, local host runs use `http://127.0.0.1:7700` |
| `MEILI_API_KEY` | `Settings` / search client | Optional index-scoped Meilisearch API key; needed for search and indexing; leave unset to disable catalog search |
| `MEILI_EVAL_API_KEY` | Search evaluation tool | Optional separate scoped key for temporary evaluation indexes; never passed to the bot |
| `MEILI_INDEX_NAME` | `Settings` / search client | Meilisearch index UID; defaults to `book_catalog` |
| `MEILI_MATCHING_STRATEGY` | `Settings` / search client | `frequency` (default) or `last`; evaluated on the synthetic relevance corpus |
| `MEILI_TIMEOUT_SECONDS` | `Settings` / search client | HTTP timeout; defaults to 2 seconds |
| `MEILI_MASTER_KEY` | Compose / Meilisearch only | Required in production mode and at least 16 bytes; Compose explicitly clears it in the bot container |
| `MEILI_MAX_INDEXING_MEMORY` | Compose / Meilisearch | Maximum indexer memory; defaults to `1Gb` and should be sized to the host |
| `LOG_LEVEL` | `Settings` | Defaults to `INFO`; no logging configuration consuming it was found |

`.env.sample` documents the variables above and an optional placeholder `DATABASE_URL` for local tools. Set the real owner ID and support destinations in the runtime environment; do not commit them. Code supplies a default database URL and Compose overrides it for the bot container. The local launcher uses `TELEGRAM_PROXY` to create an aiogram session; `requirements-dev.txt` includes the optional SOCKS support dependency. Docker leaves the session unset and connects directly.

## Verified Caveats

- The application runs migrations automatically during API lifespan startup by default.
- Telegram polling, reminder work, FSM storage, membership cache, and rate-limit windows are process-local; use one application instance.
- Reminder delivery holds a DB session while scanning and sending. Each candidate may cause additional reads; consult [docs/PERFORMANCE.md](docs/PERFORMANCE.md) before changing this path.
- Bot updates are rate-limited per user (D-10); no rate limiter for HTTP endpoints was found. Callback handlers validate preset values, numeric IDs, and timezone indexes, but changes must continue to enforce payload parsing and Telegram's 64-byte callback-data limit.
