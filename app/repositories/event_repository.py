from datetime import datetime, timedelta
from typing import List
from uuid import UUID

from database.models import Event
from schemas.event import EventCreateRequestSchema
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


class EventRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_batch(self, events: List[EventCreateRequestSchema]) -> tuple[int, int]:
        if not events:
            return 0, 0

        values = [
            {
                "event_id": event.event_id,
                "occurred_at": event.occurred_at,
                "user_id": event.user_id,
                "event_type": event.event_type,
                "properties": event.properties,
            }
            for event in events
        ]

        stmt = insert(Event).values(values).on_conflict_do_nothing(index_elements=["event_id"]).returning(Event.id)

        result = await self.db.execute(stmt)
        created_ids = result.scalars().all()
        created_count = len(created_ids)
        duplicates_count = len(events) - created_count

        await self.db.commit()

        return created_count, duplicates_count

    async def get_by_event_id(self, event_id: UUID) -> Event | None:
        result = await self.db.execute(select(Event).where(Event.event_id == event_id))
        return result.scalar_one_or_none()

    async def get_dau(self, start_date: datetime, end_date: datetime) -> List[dict]:
        stmt = (
            select(
                func.date(Event.occurred_at).label("date"),
                func.count(func.distinct(Event.user_id)).label("unique_users"),
            )
            .where(and_(Event.occurred_at >= start_date, Event.occurred_at <= end_date, Event.is_archived == False))
            .group_by(func.date(Event.occurred_at))
            .order_by(func.date(Event.occurred_at))
        )

        result = await self.db.execute(stmt)
        return [
            {"date": row.date if isinstance(row.date, str) else row.date.isoformat(), "unique_users": row.unique_users}
            for row in result
        ]

    async def get_top_events(self, start_date: datetime, end_date: datetime, limit: int = 10) -> List[dict]:
        stmt = (
            select(Event.event_type, func.count().label("count"))
            .where(and_(Event.occurred_at >= start_date, Event.occurred_at <= end_date, Event.is_archived == False))
            .group_by(Event.event_type)
            .order_by(func.count().desc())
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        return [{"event_type": row.event_type, "count": row.count} for row in result]

    async def get_retention(self, start_date: datetime, windows: int = 3, period_type: str = "daily") -> List[dict]:
        if period_type == "weekly":
            period_delta = timedelta(weeks=1)
        else:
            period_delta = timedelta(days=1)

        user_first_event = (
            select(Event.user_id, func.date(func.min(Event.occurred_at)).label("cohort_date"))
            .where(Event.occurred_at >= start_date)
            .group_by(Event.user_id)
        ).subquery()

        cohorts = []
        current_cohort_date = start_date.date()
        end_date = datetime.now().date()

        while current_cohort_date <= end_date:
            next_cohort_date = current_cohort_date + period_delta
            cohort_users_stmt = select(user_first_event.c.user_id).where(
                and_(
                    user_first_event.c.cohort_date >= current_cohort_date,
                    user_first_event.c.cohort_date < next_cohort_date,
                )
            )
            cohort_users_result = await self.db.execute(cohort_users_stmt)
            cohort_user_ids = [row[0] for row in cohort_users_result]

            if not cohort_user_ids:
                current_cohort_date = next_cohort_date
                continue

            cohort_size = len(cohort_user_ids)
            periods = {"period_0": 100.0}
            for period_num in range(1, windows + 1):
                period_start = current_cohort_date + (period_delta * period_num)
                period_end = period_start + period_delta
                returned_users_stmt = select(func.count(func.distinct(Event.user_id))).where(
                    and_(
                        Event.user_id.in_(cohort_user_ids),
                        Event.occurred_at >= period_start,
                        Event.occurred_at < period_end,
                    )
                )

                returned_result = await self.db.execute(returned_users_stmt)
                returned_count = returned_result.scalar() or 0

                retention_pct = (returned_count / cohort_size * 100) if cohort_size > 0 else 0
                periods[f"period_{period_num}"] = round(retention_pct, 2)

            cohorts.append({"cohort_date": current_cohort_date.isoformat(), "users": cohort_size, **periods})

            current_cohort_date = next_cohort_date

            if len(cohorts) >= 10:
                break

        return cohorts
