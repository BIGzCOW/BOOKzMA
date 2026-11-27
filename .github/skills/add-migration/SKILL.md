---
name: add-migration
description: Create and review an Alembic migration for BOOKzMA without touching production or private local files.
---

# Add Migration

1. Read `AGENTS.md`, `BOT_GUIDE.md`, the current models, migration history, and the approved spec. Compare the target schema and data impact.
2. Propose the upgrade/downgrade, locking/runtime impact, compatibility window, tests, and rollback before editing; obtain owner approval for the plan.
3. Add a new revision only. Never rewrite an applied migration or use `create_all()`.
4. If a migration deletes, rewrites, or irreversibly transforms data, stop and ask the owner before proceeding. Tell the owner to take and verify a backup before applying any migration on a server.
5. Test upgrade on an empty disposable PostgreSQL database and run `ruff check . && pytest`. Never apply Alembic to production or connect to a production database. Update `BOT_GUIDE.md`, `ARCHITECTURE.md`, and the spec as applicable.
