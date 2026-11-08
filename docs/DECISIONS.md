# Technical Decisions

Each entry records current intent, not a claim that future work is implemented.

## Temporary execution decision: stabilization-first mode

**Status:** Active during the 2026-11 stabilization pass.

**Context:** The repository includes multiple partially complete feature slices and several status mismatches in the docs. The owner explicitly requires a stabilization-first pass before any new feature work begins.

**Decision:** Continue on the active branch, preserve all current local work, and treat the stabilization audit as the authoritative source of truth for what remains in progress. No new feature work should be started while the stabilization checklist and audit are still open.

**Why:** This keeps the repo aligned with the owner’s safety-first rule and avoids broad feature drift while incomplete slices are still being validated.

**Revisit when:** The stabilization audit and progress log are completed, the main verification pass is green, and the repo is ready for the next feature proposal.

## D-01 — Existing API; Bot and Current Clients First

**Status:** Existing FastAPI implementation; further API expansion deferred.

**Context:** `src/BOOKzMA/api.py`, `requirements.txt`, `Dockerfile`, and `__main__.py` confirm an existing FastAPI app that runs alongside the Telegram bot. This is not a decision to add FastAPI from scratch.

**Decision:** Prioritize reliability and quality of the existing bot and API. Do not add endpoints, another client, or architecture layers for a hypothetical future. Keep shared business rules out of handlers/routes where practical; repositories remain independent of aiogram. Current API handlers are inside `api.py`, and some route logic is not yet extracted into services.

**Why:** New HTTP clients require maintained authentication, schemas, versioning, tests, and deployment. No evidence of a second live client was found in the repository; whether one exists outside this workspace is unverified.

**Alternatives:** Remove the current API (breaking existing behavior); expand the API in anticipation of clients (more maintenance); defer expansion while maintaining the existing interface (chosen).

**Revisit when:** A second client is actively being built, an existing API consumer needs a change, or measured requirements justify architectural work. Write a spec and review compatibility before changing routes.

## D-02 — Shared Local Launcher, Private Configuration

**Status:** The launcher is tracked, as required by the current `AGENTS.md` and confirmed by Git's tracked-file list. Credentials and machine-specific proxy values remain in private environment configuration.

**Context:** The local launcher runs the shared app on the host with an optional aiogram proxy session and a separate test bot token while PostgreSQL remains in Compose.

**Decision:** Keep the shared launcher tracked and preserve its local-development contract. Never embed credentials in it or put proxy construction in `src/`. The app accepts an optional injected aiogram session; Docker leaves it unset. Local development uses a host-reachable `DATABASE_URL` and must stop the Compose bot before polling with the same token. This feature does not inspect or change the launcher.

**Why:** Contributors need a shared entrypoint while secrets and machine-specific settings remain outside Git.

**Alternatives:** Put proxy logic in the application (rejected); maintain separate private launchers (superseded by the current shared-launcher rule).

**Revisit when:** The owner changes local setup or the shared entrypoint contract.

## D-03 — Streak Is Derived From Reads and Freeze Events

**Status:** Implemented; extended by the comeback bonus (S-07).

**Context:** `ReadingLog` stores one row per user and local calendar date; `StreakFreeze` stores separate earned/used events. `services/streak.py` derives current and longest streaks from both.

**Decision:** Keep streak counters derived rather than mutable. A used freeze date participates in streak continuity but never counts as a reading day or freeze-earning progress.

**Comeback extension (S-07):** When a displayed streak of three or more days breaks, the next reading day opens a comeback window stored on `users` (`broken_streak_days`, `comeback_base_day`). After three consecutive reading days, half of the broken streak (floor, capped at 30) is added as `comeback_bonus_days`. The bonus is displayed (`displayed_streak`) only while the chain that earned it remains unbroken, and it never affects `longest_streak`, freeze earning, or analytics, which keep using the raw derived streak.

**Why:** The date log is the source of truth and uniqueness makes same-day recording idempotent.

**Alternatives:** Store a mutable streak counter (adds consistency and concurrency risks).

**Revisit when:** A product requirement needs target-day/rest-day semantics or changes the approved freeze cap/reward/use rule.

## D-04 — Long Polling, Single Application Instance

**Status:** Implemented deployment assumption.

**Context:** `bot.py` starts aiogram polling; FSM storage and membership cache are process-local; the reminder loop scans reminders in the same app process.

**Decision:** Operate one application instance. Do not add replicas or webhook mode without first designing shared FSM/cache state and single-delivery ownership for reminders.

**Why:** Multiple instances could conflict on polling, lose cross-instance state, and send duplicate reminders.

**Alternatives:** Shared FSM/cache and distributed reminder claiming (more infrastructure and coordination); one process (current).

**Revisit when:** Measured load or availability requirements require multiple instances.

**Personal-library correctness:** Use aiogram's in-process `SimpleEventIsolation` to serialize updates for each user/chat FSM key before loading state. Together with clearing successful/abandoned forms, this prevents overlapping final form messages from creating duplicate books. This does not add Redis or persistent FSM storage and is not a general durable update-deduplication system. Page logging additionally uses database row locks and unique message IDs.

## D-05 — Telegram Admin Allowlist

**Status:** Implemented.

**Decision:** Admin Telegram IDs come from `ADMIN_TELEGRAM_IDS`; every privileged handler checks the allowlist server-side. Admins bypass the required-channel gate. Adding another admin requires an environment update and restart.

## D-06 — Separate, Bounded Streak Freezes

**Status:** Implemented for reading; expanded for Mesbak and admin gifts (S-04).

**Decision:** Reading and Mesbak have independent Freeze inventories, each starting at zero with a cap of three. Reading earns one after seven consecutive real reading days; Mesbak earns one after seven consecutive days with its daily goal completed. Each habit may automatically protect exactly one missed local day when activity resumes the next day and the preceding day was real activity. Protected days preserve streak continuity but never create reading/completion records or count toward another Freeze reward. Admin gifts are separate auditable events, share the matching habit balance, top up only to the cap, and require a cohort preview plus confirmation. A reading gift targets current users; a Mesbak gift targets active Mesbak members. Gifts send no user broadcast.

## D-07 — Durable Single-Process Broadcast

**Status:** Implemented for text and single-media campaigns.

**Decision:** Admins preview and confirm campaigns containing text or one photo/video, with an optional HTTPS button. The DB stores selected audience and per-recipient states; a single worker sends at 5/s, rechecks cohort eligibility before delivery, handles bounded retry and Telegram `RetryAfter`, and resumes inflight deliveries after restart. Since Telegram send and DB commit cannot be atomic, a crash in between may duplicate one message. Only one active campaign is allowed in the current single-process deployment.

## D-08 — Analytics Observation Window

**Status:** Implemented.

**Decision:** Record first `/start` and UTC daily interaction from deployment onward. Daily active counts use successful bot updates; reading activity is reported separately. Do not infer historical starts or retention from `users.created_at`.

## D-09 — Database Backup and Restore (N-05)

**Status:** Implemented (2026-10-25).

**Decision:** Daily logical backup with `pg_dump -Fc`. Host cron runs `scripts/backup.py` daily at 03:30; the admin panel can also take an on-demand backup and run a two-step-confirmed restore. Local retention keeps only the newest backup on the small server (`BACKUP_KEEP_LOCAL=1`); Google Drive (via host-side `rclone`) keeps 14 daily generations. Backups live in `BOOKZMA_BACKUP_DIR` outside the repository and are bind-mounted into the bot container at `/backups`. File encryption and other off-site mechanisms remain future work under L-02. Periodic restore rehearsal is an owner task; `scripts/restore.py` supports rehearsing against a temporary database.

## D-10 — In-Process Rate Limiting (F-08)

**Status:** Implemented (2026-10-25).

**Decision:** Bot anti-spam is a per-process in-memory middleware (`middlewares/rate_limit.py`) using a fixed window per user across messages and callback queries (`RATE_LIMIT_MAX_UPDATES`, default 20 per `RATE_LIMIT_WINDOW_SECONDS`, default 10). Admins are exempt; blocked updates never reach handlers or the DB session; the warning text is sent at most once per window. No Redis and no shared store.

**Why:** The deployment is a single application instance (D-04), so process-local state is correct and keeps the feature dependency-free. Rate-limit hits are operational events, not user engagement, so they are logged with `log.warning` and deliberately excluded from admin KPIs and `activity_days`.

**Alternatives considered:** Redis-based token bucket (rejected: new infrastructure for a single-process deployment); Telegram-side `reply_markup` only (rejected: does not stop handler floods); per-chat limits (rejected: group chats are not part of current flows).

**Revisit when:** More than one application instance runs, or a heavy feature needs finer-grained quotas per command/callback.

## D-11 — Known-Friend and Anonymous Study-Buddy Paths

**Status:** Implemented as an opt-in extension of C-06.

**Decision:** Keep anonymous FIFO matching as a separate choice. A user may instead create a random, one-time Telegram deep link, valid for seven days; persist only its SHA-256 hash and consume it after successful pairing or when the recipient is already paired with that inviter. Users may have multiple active buddies, including a mix of invited and anonymous matches. Invitation creation or acceptance never replaces an existing pair or anonymous queue entry. If either user is queued, leave both states and the invitation unchanged. Bulk nudges target only buddies who have not read on their local day and have not already received a nudge that day; after a user's successful new read, show an optional bulk-nudge prompt only if eligible buddies remain. Existing active/total buddy-pair analytics include both match types; do not add a separate invitation or nudge KPI or retain invite history. Share-text spaces use `%20` encoding rather than literal plus signs.

**Why:** The invite path is for a known person, while anonymous matching remains useful and must not be silently conflated with friend selection. Expiry, single use, hashed storage, and no automatic replacement reduce accidental or unwanted pairing. Multiple pairs are allowed without duplicating a relationship or making per-pair nudge/end controls ambiguous.

**Revisit when:** The owner requests reusable/group invitations, invitation analytics, or pairing behavior that replaces an existing buddy.

## D-12 — Independent Mesbak Habit and Cohort

**Status:** Implementing as an opt-in Telegram feature.

**Decision:** Keep goals, occurrence logs, streaks, reminders, badges, challenges, league membership, buddy pairs, and the anonymous matching queue separate from reading tables and streak calculations. A day is complete only after reaching the user's 1–5 occurrence goal. Goal changes take effect on the next local date. Each occurrence is unique per user/local day/slot. Buddy relationships may be created by one-time invite or anonymous FIFO matching; anonymous matches do not reveal display names in lists or notifications and each member has at most one active random match. Joining the section explicitly opts into possible education campaigns from the admin; leaving disables reminders and future campaign eligibility but preserves history and removes the user from the anonymous queue. Admin campaigns snapshot their selected cohort and recheck active membership before each send. No API endpoints are added.

**Why:** The feature serves users who may not use book tracking and gives the owner an explicit, auditable education cohort without conflating unrelated activity or exposing social data publicly.

**Revisit when:** Owners request a separate education preference, shared/group challenges, or a second client requiring API support.

## D-13 — Main-Channel Book Catalog Mirror

**Status:** Superseded for search behavior by D-14; PostgreSQL catalog metadata and private delivery decisions remain active.

**Context:** The external Telethon worker continuously writes a 1.88GB SQLite database in `DELETE` journal mode. Its `messages` table holds about 674K rows across channels; `channel_id` is an internal SQLite ID. The owner wants search only for the public main `BOOKzMA` channel and has authorized the bot to deliver its files.

**Decision:** Mount the source directory into the bot container read-only, with host path and in-container DB path configured through environment variables. A background task performs daily synchronization at a configured UTC hour. It reads short batches off the event loop, selects only the configured channel with `in_main=1`, excludes rows flagged as duplicates, and copies searchable metadata only into PostgreSQL. It never reads `raw_data`, other channels, SQLite settings, or file bytes. User searches do not query the active SQLite writer. Private delivery uses `copyMessage`; the search engine and Inline behavior are superseded by D-14.

**Why:** SQLite DELETE journaling makes long-lived readers a risk to the separate writer. A metadata mirror isolates search latency and avoids file download/re-upload. D-14 extends the mirror with a derived Meilisearch index and reconciliation.

**Alternatives considered:** Query the live SQLite database on every search (rejected: couples user latency and DB locks to the writer); copy the full SQLite DB or file payloads (rejected: duplicates large data and adds storage/transfer cost); use only channel links (rejected for private bot search because the owner wants direct retrieval).

**Revisit when:** Multiple channels are required or source sync volume/latency changes materially.

## D-14 — Meilisearch Catalog Search

**Status:** Implementing (owner-approved B-02 reprioritization, 2026-11-07).

**Context:** The catalog contains about 674K records according to the existing B-02 investigation. PostgreSQL FTS rejected broad queries and required AND-like term matching; users need typo tolerance, reordered query terms, and useful single-word results. The actual SQLite source is external and is not present in the current workspace.

**Decision:** Keep PostgreSQL as the authoritative metadata mirror for result details, private `copyMessage`, and personal-library linkage. Use pinned Meilisearch v1.56.1 as a derived search index keyed by Telegram `message_id`; never store file bytes or Telethon `raw_data`. Searchable fields are normalized title, filename, and caption, with conservative Persian stop words, typo tolerance, empty synonyms, `frequency` matching, and `posted_at:desc` as a final ranking tie-breaker. The bot uses an index-scoped API key; the Meilisearch master key is not passed to the bot process. Index writes go through a PostgreSQL outbox so DB commits and Meili task completion are recoverable independently.

**Sync and operations:** The source SQLite is opened read-only and scanned in bounded batches once daily at a configured UTC hour; source changes and deletions are reconciled by comparing source row IDs and document hashes. No catalog sync begins at bot startup. A standalone `python -m BOOKzMA.reindex_catalog` command builds the index in 10K-document batches and validates counts. Inline always returns Article links; private copy and add-to-library flows remain unchanged. A missing/unavailable Meilisearch produces a friendly search error and does not stop bot startup.

**Why:** Meilisearch provides prefix matching and typo tolerance while preserving relevance-first ranking and bounded paging. PostgreSQL remains the source of truth, so the external engine can be rebuilt without losing catalog metadata or user-library relationships.

**Alternatives considered:** Continue PostgreSQL FTS alone (does not meet typo/flexible matching behavior); query live SQLite (couples user latency and file locking to the external writer); use Telegram cached documents in Inline (not permitted for this flow; share only the channel post link).

**Operational notes:** The search index is derived and can be rebuilt. Its persistent Docker volume is not part of PostgreSQL `pg_dump`; follow the new search runbook for recovery. Synthetic relevance/latency results do not replace a benchmark on the real source and production-sized index.

**Revisit when:** The real catalog benchmark shows quality/performance gaps, source schema gains a reliable change log, or multi-channel search is approved.

## Open Decisions (Owner Only)

- Exact rules for weekly reading targets and rest days.
- Calendar basis: Persian (Jalali) dates and Saturday-start weeks (S-06), and the day boundary for readers who log after midnight (S-10).
- Definition of an "active user" for analytics and admin KPIs (A-05).
- Book-search sources and copyright/licensing constraints for future external sources (B-01).
- Social privacy defaults: what friends may see and whether visibility is opt-in (C-02, L-03).
- Reward model, anti-abuse rules, and whether payments (for example Telegram Stars) will exist and for which digital goods, under a free-core principle (G-08, C-05, M-01, M-02).
- Backup file encryption and further off-site/retention policy beyond D-09 (L-02).
- Whether to add a `MenuButton` beyond scoped commands and the persistent reply keyboard, and the final combination of command menu and reply keyboard at `/start` (N-01, U-01).
- Whether a web admin panel is built and up to which tier (W-01..W-03), tied to revisiting the FastAPI decision D-01.
- Brand tone of voice: how casual versus formal (N-07).
- Exact policy for what a non-existent local reminder time does during DST: current implementation skips that occurrence on that date.
- Host path for the channel SQLite directory and daily UTC sync hour.
