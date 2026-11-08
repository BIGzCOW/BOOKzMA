import asyncio
from datetime import date

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import dialect

from BOOKzMA.db.models import CatalogUsageDay, ReadingLog
from BOOKzMA.repositories.analytics import _utc_day, activity_series, record_catalog_usage


def test_utc_day_expression_uses_sqlalchemy_date_type():
    statement = select(_utc_day(ReadingLog.created_at))

    compiled = str(statement.compile(dialect=dialect()))

    assert "CAST(timezone" in compiled
    assert "AS DATE" in compiled


def test_activity_series_converts_result_rows_to_daily_counts():
    today = date(2026, 10, 23)

    class Result:
        def all(self):
            return [(today, 3), (date(2026, 10, 21), 2)]

    class Session:
        async def execute(self, _statement):
            return Result()

    series = asyncio.run(activity_series(Session(), today, days=3))

    assert series == [
        (date(2026, 10, 21), 2),
        (date(2026, 10, 22), 0),
        (today, 3),
    ]


def test_catalog_usage_records_atomic_daily_increments_without_event_payloads():
    class Session:
        statement = None
        committed = False

        async def execute(self, statement):
            self.statement = statement

        async def commit(self):
            self.committed = True

    session = Session()
    asyncio.run(
        record_catalog_usage(session, searches=1, results_shown=4)
    )

    compiled = str(session.statement.compile(dialect=dialect()))
    assert "INSERT INTO catalog_usage_days" in compiled
    assert "ON CONFLICT (day) DO UPDATE" in compiled
    assert "catalog_usage_days.searches + excluded.searches" in compiled
    assert "catalog_usage_days.results_shown + excluded.results_shown" in compiled
    assert "user_id" not in CatalogUsageDay.__table__.columns
    assert session.committed is True


def test_catalog_usage_rejects_unknown_or_negative_metrics():
    class Session:
        async def execute(self, _statement):
            raise AssertionError("invalid metrics must not reach the database")

    async def run_test():
        for metrics in ({"query": 1}, {"searches": -1}, {"searches": True}):
            try:
                await record_catalog_usage(Session(), **metrics)
            except ValueError:
                continue
            raise AssertionError("invalid catalog metrics were accepted")

    asyncio.run(run_test())