from datetime import datetime, timedelta
from typing import List

import duckdb
from database.models import Event
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class EventHybridRepository:
    def __init__(self, db: AsyncSession, duckdb_conn: duckdb.DuckDBPyConnection):
        self.db = db
        self.duckdb_conn = duckdb_conn

    async def get_dau(self, start_date: datetime, end_date: datetime) -> List[dict]:
        hot_stmt = (
            select(
                func.date(Event.occurred_at).label("date"),
                func.count(func.distinct(Event.user_id)).label("unique_users"),
            )
            .where(and_(Event.occurred_at >= start_date, Event.occurred_at <= end_date, Event.is_archived == False))
            .group_by(func.date(Event.occurred_at))
        )

        hot_result = await self.db.execute(hot_stmt)
        hot_data = {row.date.isoformat(): row.unique_users for row in hot_result}

        cold_query = """
            SELECT 
                DATE(occurred_at) as date,
                COUNT(DISTINCT user_id) as unique_users
            FROM events
            WHERE occurred_at >= ? AND occurred_at <= ?
            GROUP BY DATE(occurred_at)
        """

        cold_result = self.duckdb_conn.execute(cold_query, [start_date.isoformat(), end_date.isoformat()]).fetchall()

        cold_data = {row[0].isoformat(): row[1] for row in cold_result}

        all_dates = set(hot_data.keys()) | set(cold_data.keys())
        merged_data = []

        for date_str in sorted(all_dates):
            unique_users = hot_data.get(date_str, 0) + cold_data.get(date_str, 0)
            merged_data.append({"date": date_str, "unique_users": unique_users})
        return merged_data

    async def get_top_events(self, start_date: datetime, end_date: datetime, limit: int = 10) -> List[dict]:
        hot_stmt = (
            select(Event.event_type, func.count().label("count"))
            .where(and_(Event.occurred_at >= start_date, Event.occurred_at <= end_date, Event.is_archived == False))
            .group_by(Event.event_type)
        )

        hot_result = await self.db.execute(hot_stmt)
        hot_data = {row.event_type: row.count for row in hot_result}

        cold_query = """
            SELECT
                event_type,
                COUNT(*) as count
            FROM events
            WHERE occurred_at >= ? AND occurred_at <= ?
            GROUP BY event_type
        """

        cold_result = self.duckdb_conn.execute(cold_query, [start_date.isoformat(), end_date.isoformat()]).fetchall()

        cold_data = {row[0]: row[1] for row in cold_result}

        all_event_types = set(hot_data.keys()) | set(cold_data.keys())
        merged_data = []

        for event_type in all_event_types:
            total_count = hot_data.get(event_type, 0) + cold_data.get(event_type, 0)
            merged_data.append({"event_type": event_type, "count": total_count})

        merged_data.sort(key=lambda x: x["count"], reverse=True)
        return merged_data[:limit]

    async def get_retention(self, start_date: datetime, windows: int = 3, period_type: str = "daily") -> List[dict]:
        if period_type == "weekly":
            period_delta = timedelta(weeks=1)
        else:
            period_delta = timedelta(days=1)

        cohorts = []
        current_cohort_date = start_date.date()
        end_date = datetime.now().date()

        while current_cohort_date <= end_date:
            next_cohort_date = current_cohort_date + period_delta

            cohort_user_ids = await self._get_cohort_users(current_cohort_date, next_cohort_date)

            if not cohort_user_ids:
                current_cohort_date = next_cohort_date
                continue

            cohort_size = len(cohort_user_ids)
            periods = {"period_0": 100.0}

            for period_num in range(1, windows + 1):
                period_start = current_cohort_date + (period_delta * period_num)
                period_end = period_start + period_delta

                returned_count = await self._get_returned_users_count(cohort_user_ids, period_start, period_end)

                retention_pct = (returned_count / cohort_size * 100) if cohort_size > 0 else 0
                periods[f"period_{period_num}"] = round(retention_pct, 2)

            cohorts.append({"cohort_date": current_cohort_date.isoformat(), "users": cohort_size, **periods})

            current_cohort_date = next_cohort_date

            if len(cohorts) >= 10:
                break

        return cohorts

    async def _get_cohort_users(self, cohort_start: datetime.date, cohort_end: datetime.date) -> set[str]:
        hot_stmt = (
            select(Event.user_id)
            .where(
                and_(
                    func.date(Event.occurred_at) >= cohort_start,
                    func.date(Event.occurred_at) < cohort_end,
                    Event.is_archived == False,
                )
            )
            .distinct()
        )

        hot_result = await self.db.execute(hot_stmt)
        hot_users = {row[0] for row in hot_result}

        cold_query = """
            SELECT DISTINCT user_id
            FROM events
            WHERE DATE(occurred_at) >= ? AND DATE(occurred_at) < ?
        """

        cold_result = self.duckdb_conn.execute(
            cold_query, [cohort_start.isoformat(), cohort_end.isoformat()]
        ).fetchall()

        cold_users = {row[0] for row in cold_result}

        return hot_users | cold_users

    async def _get_returned_users_count(
        self,
        cohort_user_ids: set[str],
        period_start: datetime.date,
        period_end: datetime.date,
    ) -> int:
        user_ids_list = list(cohort_user_ids)

        hot_stmt = select(func.count(func.distinct(Event.user_id))).where(
            and_(
                Event.user_id.in_(user_ids_list),
                Event.occurred_at >= period_start,
                Event.occurred_at < period_end,
                Event.is_archived == False,
            )
        )

        hot_result = await self.db.execute(hot_stmt)
        hot_count = hot_result.scalar() or 0

        placeholders = ",".join(["?" for _ in user_ids_list])

        cold_query = f"""
            SELECT COUNT(DISTINCT user_id)
            FROM events
            WHERE user_id IN ({placeholders})
            AND occurred_at >= ?
            AND occurred_at <= ?
        """

        params = user_ids_list + [period_start.isoformat(), period_end.isoformat()]
        cold_result = self.duckdb_conn.execute(cold_query, params).fetchone()
        cold_count = cold_result[0] if cold_result else 0

        all_returned_users = await self._get_returned_users_set(user_ids_list, period_start, period_end)

        return len(all_returned_users)

    async def _get_returned_users_set(
        self, cohort_user_ids: list[str], period_start: datetime.date, period_end: datetime.date
    ) -> set[str]:
        hot_stmt = (
            select(Event.user_id)
            .where(
                and_(
                    Event.user_id.in_(cohort_user_ids),
                    Event.occurred_at >= period_start,
                    Event.occurred_at < period_end,
                    Event.is_archived == False,
                )
            )
            .distinct()
        )

        hot_result = await self.db.execute(hot_stmt)
        hot_users = {row[0] for row in hot_result}

        placeholders = ",".join(["?" for _ in cohort_user_ids])
        cold_query = f"""
            SELECT DISTINCT user_id
            FROM events
            WHERE user_id IN ({placeholders})
            AND occurred_at >= ?
            AND occurred_at < ?
        """

        params = cohort_user_ids + [period_start.isoformat(), period_end.isoformat()]
        cold_result = self.duckdb_conn.execute(cold_query, params).fetchall()
        cold_users = {row[0] for row in cold_result}

        return hot_users | cold_users
