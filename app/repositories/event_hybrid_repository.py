import logging
from datetime import datetime, timedelta
from typing import List

from database.duckdb_session import get_duckdb_read_session
from database.models import Event
from sqlalchemy import Date, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class EventHybridRepository:
    def __init__(self, db: AsyncSession, duckdb_session: Session = None):
        self.db = db
        self.duckdb_session = duckdb_session or get_duckdb_read_session()

    async def get_dau(self, start_date: datetime, end_date: datetime) -> List[dict]:
        try:
            logger.info(f"Querying hot storage for DAU: {start_date} to {end_date}")

            hot_stmt = select(func.date(Event.occurred_at).label("date"), Event.user_id).where(
                and_(Event.occurred_at >= start_date, Event.occurred_at < end_date, Event.is_archived == False)
            )
            hot_result = await self.db.execute(hot_stmt)

            hot_data = {}
            for row in hot_result:
                date_str = str(row.date)
                if date_str not in hot_data:
                    hot_data[date_str] = set()
                hot_data[date_str].add(row.user_id)

            logger.info(f"Hot storage returned {len(hot_data)} dates")

            logger.info(f"Querying cold storage (DuckDB) for DAU")

            cold_stmt = select(func.strftime(Event.occurred_at, "%Y-%m-%d").label("date"), Event.user_id).where(
                and_(Event.occurred_at >= start_date, Event.occurred_at < end_date)
            )
            cold_result = self.duckdb_session.execute(cold_stmt)

            cold_data = {}
            for row in cold_result:
                if row.date not in cold_data:
                    cold_data[row.date] = set()
                cold_data[row.date].add(row.user_id)

            logger.info(f"Cold storage returned {len(cold_data)} dates")

            all_dates = set(hot_data.keys()) | set(cold_data.keys())
            merged_data = []

            for date_str in sorted(all_dates):
                hot_users = hot_data.get(date_str, set())
                cold_users = cold_data.get(date_str, set())
                unique_users = len(hot_users | cold_users)

                merged_data.append({"date": date_str, "unique_users": unique_users})

            logger.info(f"Merged data: {len(merged_data)} dates total")
            return merged_data
        except Exception as e:
            logger.error(
                f"Error in get_dau: {type(e).__name__}: {str(e)}",
                exc_info=True,
            )
            raise

    async def get_top_events(self, start_date: datetime, end_date: datetime, limit: int = 10) -> List[dict]:
        hot_stmt = (
            select(Event.event_type, func.count().label("count"))
            .where(and_(Event.occurred_at >= start_date, Event.occurred_at < end_date, Event.is_archived == False))
            .group_by(Event.event_type)
        )

        hot_result = await self.db.execute(hot_stmt)
        hot_data = {row.event_type: row.count for row in hot_result}

        cold_stmt = (
            select(Event.event_type, func.count().label("count"))
            .where(and_(Event.occurred_at >= start_date, Event.occurred_at < end_date))
            .group_by(Event.event_type)
        )

        cold_result = self.duckdb_session.execute(cold_stmt)
        cold_data = {row.event_type: row.count for row in cold_result}

        all_event_types = set(hot_data.keys()) | set(cold_data.keys())
        merged_data = []

        for event_type in all_event_types:
            total_count = hot_data.get(event_type, 0) + cold_data.get(event_type, 0)
            merged_data.append({"event_type": event_type, "count": total_count})

        merged_data.sort(key=lambda x: x["count"], reverse=True)
        return merged_data[:limit]

    async def get_retention(self, start_date: datetime, windows: int = 3, period_type: str = "daily") -> List[dict]:
        try:
            logger.info(f"Calculating retention: start={start_date}, " f"windows={windows}, period={period_type}")

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

                    returned_users = await self._get_returned_users_set(list(cohort_user_ids), period_start, period_end)
                    returned_count = len(returned_users)

                    retention_pct = (returned_count / cohort_size * 100) if cohort_size > 0 else 0
                    periods[f"period_{period_num}"] = round(retention_pct, 2)

                cohorts.append({"cohort_date": current_cohort_date.isoformat(), "users": cohort_size, **periods})

                current_cohort_date = next_cohort_date

                if len(cohorts) >= 10:
                    break

            logger.info(f"Retention calculation complete: {len(cohorts)} cohorts found")
            return cohorts

        except Exception as e:
            logger.error(f"Error in get_retention: {type(e).__name__}: {str(e)}", exc_info=True)
            raise

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
        hot_users = set(hot_result.scalars())

        cold_stmt = (
            select(Event.user_id)
            .where(
                and_(
                    func.cast(Event.occurred_at, Date) >= cohort_start,
                    func.cast(Event.occurred_at, Date) < cohort_end,
                )
            )
            .distinct()
        )

        cold_result = self.duckdb_session.execute(cold_stmt)
        cold_users = set(cold_result.scalars())

        return hot_users | cold_users

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
        hot_users = set(hot_result.scalars())

        cold_stmt = (
            select(Event.user_id)
            .where(
                and_(
                    Event.user_id.in_(cohort_user_ids),
                    Event.occurred_at >= period_start,
                    Event.occurred_at < period_end,
                )
            )
            .distinct()
        )

        cold_result = self.duckdb_session.execute(cold_stmt)
        cold_users = set(cold_result.scalars())

        return hot_users | cold_users
