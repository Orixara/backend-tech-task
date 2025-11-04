import datetime as dt
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.database.models.event import Event

UTC = dt.timezone.utc


class TestAnalyticsEndpoints:

    @staticmethod
    def _make_event(user_id, ts, etype="click", props=None, eid=None) -> Event:
        return Event(
            event_id=eid or uuid4(),
            occurred_at=ts,
            user_id=user_id,
            event_type=etype,
            properties=props or {},
            is_archived=False,
        )

    @staticmethod
    async def _insert_pg(session: AsyncSession, events: list[Event]) -> None:
        session.add_all(events)
        await session.commit()

    @staticmethod
    def _insert_duck(master_session: Session, events: list[Event]) -> None:
        master_session.add_all(events)
        master_session.commit()

    @pytest.mark.asyncio
    async def test_dau_hybrid_merge_no_double_count(
        self,
        analytics_client: AsyncClient,
        test_db_session: AsyncSession,
        duckdb_write_session: Session,
    ):
        d0 = dt.datetime(2025, 1, 1, 10, tzinfo=UTC)
        d1 = dt.datetime(2025, 1, 2, 12, tzinfo=UTC)
        d2 = dt.datetime(2025, 1, 3, 9, tzinfo=UTC)

        self._insert_duck(
            duckdb_write_session,
            [
                self._make_event("u1", d0),
                self._make_event("u2", d1),
                self._make_event("u2", d2),  # CHANGED FROM u3 TO u2
            ],
        )

        await self._insert_pg(
            test_db_session,
            [
                self._make_event("u1", d1, etype="view"),
                self._make_event("u3", d1, etype="view"),
                self._make_event("u2", d2, etype="click"),
                self._make_event("u2", d2, etype="purchase"),
            ],
        )

        response = await analytics_client.get("/stats/dau", params={"from_date": "2025-01-01", "to_date": "2025-01-03"})
        assert response.status_code == 200, response.text
        body = response.json()
        data = {row["date"][:10]: row["unique_users"] for row in body["data"]}
        assert data == {
            "2025-01-01": 1,
            "2025-01-02": 3,
            "2025-01-03": 1,
        }

    @pytest.mark.asyncio
    async def test_top_events_limit_and_merge(
        self,
        analytics_client: AsyncClient,
        test_db_session: AsyncSession,
        duckdb_write_session: Session,
    ):
        d = dt.datetime(2025, 2, 1, 8, tzinfo=UTC)

        self._insert_duck(
            duckdb_write_session,
            [
                self._make_event("u1", d, "click"),
                self._make_event("u2", d, "click"),
                self._make_event("u3", d, "view"),
            ],
        )
        await self._insert_pg(
            test_db_session,
            [
                self._make_event("u4", d, "click"),
                self._make_event("u5", d, "purchase"),
                self._make_event("u6", d, "view"),
                self._make_event("u7", d, "view"),
            ],
        )

        r = await analytics_client.get(
            "/stats/top-events", params={"from_date": "2025-02-01", "to_date": "2025-02-01", "limit": 2}
        )
        assert r.status_code == 200, r.text
        rows = r.json()["data"]
        assert len(rows) == 2
        kinds = {row["event_type"] for row in rows}
        assert kinds == {"click", "view"}
        counts = {row["event_type"]: row["count"] for row in rows}
        assert counts["click"] == 3
        assert counts["view"] == 3

    @pytest.mark.asyncio
    async def test_retention_daily(
        self,
        analytics_client: AsyncClient,
        test_db_session: AsyncSession,
        duckdb_write_session: Session,
    ):
        start = dt.date(2025, 3, 1)
        d0 = dt.datetime(2025, 3, 1, 10, tzinfo=UTC)
        d1 = dt.datetime(2025, 3, 2, 11, tzinfo=UTC)
        d2 = dt.datetime(2025, 3, 3, 9, tzinfo=UTC)

        self._insert_duck(
            duckdb_write_session,
            [
                self._make_event("u2", d0, "view"),
                self._make_event("u1", d1, "view"),
                self._make_event("u3", d1, "view"),
            ],
        )
        await self._insert_pg(
            test_db_session,
            [
                self._make_event("u1", d0, "click"),
                self._make_event("u1", d2, "click"),
                self._make_event("u2", d2, "purchase"),
            ],
        )

        r = await analytics_client.get(
            "/stats/retention",
            params={
                "start_date": start.isoformat(),
                "windows": 2,
                "period_type": "daily",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()

        assert len(body["cohorts"]) > 0, "Expected at least one cohort"

        cohort = body["cohorts"][0]
        assert cohort["cohort_date"].startswith(start.isoformat())
        assert cohort["users"] == 2

        assert cohort["period_1"] is not None
        assert cohort["period_2"] is not None

        assert cohort["period_1"] == 50.0
        assert cohort["period_2"] == 100.0

    @pytest.mark.asyncio
    async def test_validation_errors(self, analytics_client: AsyncClient):
        response = await analytics_client.get("/stats/dau", params={"from_date": "2025/01/01", "to_date": "2025-01-02"})
        assert response.status_code == 400

        response = await analytics_client.get("/stats/dau", params={"from_date": "2025-01-03", "to_date": "2025-01-01"})
        assert response.status_code == 400

        response = await analytics_client.get(
            "/stats/retention",
            params={"start_date": "2025-01-01", "windows": 2, "period_type": "monthly"},
        )
        assert response.status_code in (400, 422)
