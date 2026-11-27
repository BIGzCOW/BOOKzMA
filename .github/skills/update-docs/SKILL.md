---
name: update-docs
description: Reconcile BOOKzMA documentation with the current code and roadmap without inventing behavior.
---

# Update Documentation

1. Read `AGENTS.md` and `docs/DOCS_MAINTENANCE.md`. Inspect the current code, configuration, migration history, and tests; never open `.env` or `dev_run.py`.
2. Compare `COMMANDS`, callback payloads, FSM states, API routes, models/migrations, environment variables, middleware, limits, and runtime entrypoints with `BOT_GUIDE.md` and `ARCHITECTURE.md`.
3. List discrepancies first, then correct the canonical docs. Keep future plans in `docs/ROADMAP.md`/`docs/DECISIONS.md`; do not document unimplemented behavior as current.
4. Verify local links, ROADMAP statuses, and that tool-specific files remain pointers. Run the P-12 checks in `docs/vibe/PROMPTS.md`; report anything unavailable or unverified.
