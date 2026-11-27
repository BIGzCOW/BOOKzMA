---
name: pre-release-check
description: Run a safe, evidence-based BOOKzMA pre-release review without pushing, tagging, or accessing production.
---

# Pre-release Check

1. Review the proposed diff. Run `ruff check . && pytest`; compare models with Alembic revisions and env usage with `.env.sample`/`BOT_GUIDE.md`.
2. Build with `docker compose up -d --build` only in an approved local environment; if unavailable or unsafe, report not run. Never execute migrations against production.
3. Scan changed files for credentials without printing any matched values. Check compatibility with the owner's local launcher without opening `dev_run.py`; ask the owner to run that check.
4. Confirm docs and release notes match the code. Report manual server steps in order: verified backup, planned migration, deployment, log observation, and rollback procedure.
5. Do not push or tag. Report exact commands/results, blockers, risks, and owner decisions.
