# Agent instructions

@AGENTS.md

Read and follow `AGENTS.md`; it is the source of truth. Keep bot text in `texts.py`, keep proxy code out of `src/`, never read or commit `.env` or `dev_run.py`, use a new migration for schema changes, run `ruff check . && pytest` and report actual results, and update docs with behavior changes.
