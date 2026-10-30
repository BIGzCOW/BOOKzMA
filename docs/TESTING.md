# Testing

The current suite has pure tests for streak/date calculations and freezes, book-input/progress calculations, admin configuration/callback parsing, time parsing, Persian digits, and API auth/helpers/routes. PostgreSQL integration tests cover same-day reading-registration concurrency, concurrent personal-book limits, multi-session page logging/idempotency/progress/ownership/archive, reminder limits, account deletion and restoration (including personal books), streak-freeze persistence, broadcast confirmation/cancellation, badges, onboarding, comeback analytics, study buddies, and Mesbak persistence/social limits. Database tests are skipped unless `TEST_DATABASE_URL` points to a disposable PostgreSQL database. Do not use production data or credentials.

## Environment and isolation

Use Python 3.12, matching `pyproject.toml` and CI. Do not infer the interpreter version from an old local snapshot: check `python --version`. `tests/conftest.py` disables automatic `.env` loading before collection so synthetic tests do not read private developer settings. PostgreSQL tests opt in through an explicitly exported `TEST_DATABASE_URL`; they skip otherwise. CI runs migrations and tests on Python 3.12 with PostgreSQL, which remains the authoritative migration check.

Personal-library bot regressions use fabricated aiogram updates through the real dispatcher/router, with Telegram methods and repositories mocked. They cover private-chat enforcement, menu precedence, form cancellation on navigation, concurrent/replayed final submission, optional author, invalid totals, rollback/retry, and multiple page sessions. Run them without Docker or a bot token:

```sh
ruff check .
pytest tests/test_books.py tests/test_books_flow.py tests/test_bot.py -q
pytest -q
```

Repository concurrency, progress/ownership/archive, KPI and cascade tests still need a disposable PostgreSQL database. See the feature-specific [handoff and smoke checklist](specs/personal-library-pages.md#تحویل-و-بررسی-قبل-از-انتشار).

| Change | Minimum verification |
| --- | --- |
| Pure date/time logic | Unit tests for boundaries, timezone changes, DST, missed days, duplicates, and current-day behavior as applicable |
| Repository or transaction behavior | Integration test against disposable PostgreSQL; include duplicate/concurrent writes and relevant constraints |
| Durable broadcast worker | Fake Telegram responses for pacing, RetryAfter, bounded retry, blocked recipients, cancel/restart recovery and the duplicate-delivery failure window |
| Bot handler or callback | Pure parsing/validation tests where practical; manual smoke test with the separate test bot, including invalid input and Telegram failures |
| API route or authentication | Unit/helper and route tests for authorization, invalid/expired input, ownership, validation, and response contract |
| Alembic migration | Compare migration with models; apply to an empty disposable PostgreSQL DB and verify schema. Never target production |
| Docker, Compose, or entrypoint | `docker compose up -d --build` only in a safe local environment; check startup and logs |
| Local launcher, config, or proxy workflow | Owner-run check with `dev_run.py`; the file must not be opened or changed by the agent |

Tests must be deterministic and use synthetic identities/data. Avoid dependence on today's real date, network availability, bot tokens, or live Telegram. Write a failing regression test before fixing a reproducible bug. Do not delete or weaken tests to get a pass. For concurrency, rely on database constraints/locking and verify the outcome with the integration test.

When shared streak logic changes, also review reading registration, weekly summaries, reminders, and API responses. Current CI starts PostgreSQL and sets `TEST_DATABASE_URL`; database tests use it for persistence, constraints, idempotency, and concurrent-write contracts. The initial F-03 slice adds a concurrent same-day `mark_read` contract test; broader repository/migration coverage should be based on separately identified gaps rather than duplicating existing tests. Fabricated aiogram updates now cover the personal-library flows described above; broader bot-flow coverage and backup restoration rehearsals remain future work.

Before finishing, run `ruff check . && pytest` and report the exact command and observed summary. “Should pass” is not a test result. If an environment mismatch, missing dependency, database, Docker, or Telegram access prevents a check, report it as not run or blocked.
