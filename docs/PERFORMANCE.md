# Performance Guidance

Target scale is roughly 500–1,000 daily active users: keep the system simple, but correct. Measure a real bottleneck before optimizing. Do not trade readability, privacy, data integrity, or security for speculative speed.

## Change Checklist

- Avoid unnecessary queries per update/request and query loops; filter and aggregate in SQL when appropriate.
- Check indexes and unique constraints against real query/write patterns.
- Keep blocking or CPU-heavy work off the async event loop; use a worker thread or a bounded background job where justified.
- Make duplicate taps and concurrent writes safe with primary/unique constraints and idempotent operations.
- Handle expected failures so a background task does not silently stop. Retry only idempotent operations with bounded attempts/backoff.
- Respect Telegram limits (about 30 messages/second globally and about one message/second per chat); handle `RetryAfter` and pace bulk sends.
- Bound caches by TTL and size; retain Docker compatibility.

## Observed Hot Path

`services/scheduler.py` wakes every 30 seconds and loads every reminder with its user. It then iterates in Python and may query reading status and all reading dates for each due candidate while holding the session. This is an N+1-style hot path as reminder volume grows. Do not optimize without measuring; a future change could select the due time window in SQL and add a supporting index after checking timezone semantics and the query plan.

## Current Broadcast Limits

- Text broadcasts use a durable DB queue, one active campaign, per-recipient status, 5 messages/second pacing, bounded retries, and restart recovery. The process is single-instance only; replicas require DB-level worker claiming/locking and a global rate limiter.
- Telegram send and DB commit cannot be atomic, so a crash after Telegram accepts a message but before the delivery state is committed can duplicate one message after recovery.
- Campaigns are text-only and target all users not marked unavailable after a permanent Telegram failure. Media, segmentation, user opt-out, and campaign/report retention controls need a separate reviewed spec.

## Future Work That Needs Design
- Analytics may need pre-aggregation after measuring the cost of raw queries and defining “active user.”
- Image generation is CPU-bound: keep it off the event loop, bound per-user work, and cache reusable assets.
- Multiple instances or webhook mode require shared FSM state, membership cache strategy, and exclusive reminder/broadcast claiming before scaling out.

## Optimization Method

Record the measured symptom, identify the cause, make the smallest change, rerun the same measurement and relevant tests, and document the result. Do not claim a speedup without comparable measurements.
