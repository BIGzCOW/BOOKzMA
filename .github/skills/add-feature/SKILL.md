---
name: add-feature
description: Plan and implement an approved BOOKzMA feature from a spec, preserving existing bot/API behavior and local-owner constraints.
---

# Add Feature

1. Read `AGENTS.md`, the relevant guides, `docs/DECISIONS.md`, and the approved spec. Confirm the ROADMAP item is approved; an idea is not authorization.
2. Before edits, map the feature end to end: affected user flows, Telegram menus/commands/callbacks, API, admin controls and analytics, data/events/migrations, authorization/privacy/deletion, errors/retries/background jobs, config/deployment, tests, docs, Docker, and local `dev_run.py` compatibility. Explicitly decide which admin KPIs/actions must change; implement those together or record why none apply. Present options with pros/cons and get owner approval for the plan.
3. Implement reusable logic and tests first, then repository work, bot text in `texts.py`, keyboards in `keyboards.py`, and the handler/router or API route. Validate and bound external input; escape values in Telegram HTML; enforce authorization server-side.
4. Add a new migration if schema changes; never edit an applied revision. Do not add dependencies or expand architecture without owner approval.
5. Run `ruff check . && pytest`, report actual output, update current-behavior docs and ROADMAP, and report any local/Docker check not performed. Never inspect or change `dev_run.py`.

## Feature Completeness Gate

- Trace every way the behavior is entered, displayed, stored, scheduled, and reported; include existing users and failure/retry paths.
- Keep user and admin surfaces consistent. Any feature that generates measurable events must update admin analytics, filters, and reports in the same change; add tests for those metrics.
- Review profiles, weekly summaries, reminders, API responses, leaderboard, and data deletion when they consume the affected domain data. Do not change unrelated contracts without justification.
- Update the spec acceptance checklist so every applicable surface is either implemented and tested or explicitly marked out of scope with a reason.
