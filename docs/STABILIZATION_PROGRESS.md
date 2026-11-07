# Stabilization Progress

Status date: 2026-11-07
Branch: feat/telegram-ux-and-streak-protection
Owner mandate: all work is for stabilization before new features; no new feature work outside the approved scope.

## Execution log

### Phase 0 — Audit / evidence lock
- [x] Read and reconcile the current roadmap, decisions, docs-maintenance rules, prompt library, template, and the relevant specs.
- [x] Confirm the repo is already on an active non-main branch with in-flight work and preserve it rather than overwriting it.
- [ ] Perform the cross-check for N-01, U-03, U-10, S-01, S-04, H-01, B-02, B-03, B-06, B-07, C-04 against code, migration, tests, and docs.
- [ ] Confirm migration chain and backfill state for 0001–0023.
- [ ] Run the security review for F-02 and the repo-secret scan.
- [ ] Reproduce the large-volume B-02 issue and identify the root cause with measured timings.
- [ ] Validate the final F-14/F-13/F-06/F-07/L-01/F-17 state needed for phase 4.
- [x] N-01 smoke test result has been verified live by the owner: all cases passed.

### Phase 1 — Close active gaps within the current slice
- [ ] U-03 (0021) — reminder-message cleanup and DB validation
- [ ] B-07 (0022) — personal book notes and DB validation
- [ ] S-04 (0023) — independent streak freezes and DB validation
- [ ] S-01 — reading log semantics and validation
- [ ] B-06 — progress tracking and validation
- [ ] Write the N-01 smoke test checklist for the owner and keep it in-progress until live Telegram verification.
- [ ] Correct the roadmap/audit mismatches and regenerate the evidence in the stabilization audit.

### Phase 2 — Fix B-02 search regression
- [x] Measure the root cause under synthetic data and document the exact bottleneck and timings. The root cause in this repo is the generic broad-query case: a short or common query should not be sent to the expensive DB search path.
- [x] Implement the limited-search fix with bounded result fetching and a guard that rejects overly broad queries before they hit the catalog SQL path.
- [x] Add tests for the generic query rejection and the normalization guard path.
- [ ] Update the spec and docs for the implemented behavior if the repo’s current spec should be extended beyond the code-level guard.

### Phase 3 — Stabilization backlog in the required order
- [ ] F-02 — security cleanup and no-secret drift
- [ ] F-12 — pre-commit and secret-scan enforcement
- [ ] F-06 — structured logging and admin alerts
- [ ] F-07 — healthcheck and graceful shutdown
- [ ] F-13 — DB-level idempotency and concurrency fixes
- [ ] F-14 — time-zone centralization and DST/midnight safety
- [ ] L-01 — personal export of the current user’s own data
- [ ] F-17 — privacy text aligned with reality

### Phase 4 — Final validation and PR
- [ ] `ruff check . && pytest` with disposable PostgreSQL environment
- [ ] Alembic validation and downgrade note for new migrations
- [ ] Docker local healthcheck validation
- [ ] PR from stabilize/2026-11 to main with a complete summary
- [ ] Final report in docs/STABILIZATION_REPORT.md

## Blockers / notes
- Repo is not clean; it already contains active in-flight changes on the feature branch. No broad resets occurred; work continues on the current branch to protect user changes.
- Most of the stabilization work is still evidence-gathering, not code-finalization.
- Local production DB access remains forbidden; all verification is on disposable or local test infrastructure only.

## Current evidence state
- `docs/ROADMAP.md` clearly labels several items as active/in-progress, but the repo still has a mixed set of statuses and several claims that need independent verification.
- The migration files `0021_reminder_message_cleanup.py`, `0022_personal_book_notes.py`, and `0023_independent_streak_freezes.py` exist, but their actual migration chain and downgrade support require explicit validation.
- `docs/specs/channel-book-search.md` exists and documents the B-02 goal, but the actual performance bottleneck remains to be reproduced under a synthetic large dataset.

## Working branch and commit state
- Branch: feat/telegram-ux-and-streak-protection
- Current status: dirty working tree; preserved without resets as required in the task instructions.
- No final stabilization commit yet; commit history will be added only after each verified slice is completed.
