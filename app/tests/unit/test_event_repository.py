from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.event_repository import EventRepository
from app.schemas.event import EventCreateRequestSchema


class TestEventRepository:

    @pytest.mark.asyncio
    async def test_get_by_event_id_found(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)
        event_id = uuid4()

        event = EventCreateRequestSchema(
            event_id=event_id,
            occurred_at=datetime.now(timezone.utc),
            user_id="user123",
            event_type="login",
            properties={"device": "mobile"},
        )
        await repo.create_batch([event])

        found_event = await repo.get_by_event_id(event_id)

        assert found_event is not None
        assert found_event.event_id == event_id
        assert found_event.user_id == "user123"
        assert found_event.event_type == "login"

    @pytest.mark.asyncio
    async def test_get_by_event_id_not_found(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)
        non_existent_id = uuid4()

        found_event = await repo.get_by_event_id(non_existent_id)

        assert found_event is None

    @pytest.mark.asyncio
    async def test_get_dau_single_day(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        events = [
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today,
                user_id="user1",
                event_type="page_view",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=1),
                user_id="user2",
                event_type="login",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=2),
                user_id="user3",
                event_type="click",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=3),
                user_id="user1",
                event_type="logout",
                properties={},
            ),
        ]
        await repo.create_batch(events)

        start_date = today.replace(hour=0, minute=0, second=0)
        end_date = today.replace(hour=23, minute=59, second=59)
        dau_data = await repo.get_dau(start_date, end_date)

        assert len(dau_data) == 1
        assert dau_data[0]["unique_users"] == 3

    @pytest.mark.asyncio
    async def test_get_dau_multiple_days(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        yesterday = today - timedelta(days=1)

        events = [
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=yesterday,
                user_id="user1",
                event_type="login",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=yesterday + timedelta(hours=1),
                user_id="user2",
                event_type="page_view",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today,
                user_id="user1",
                event_type="click",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=1),
                user_id="user3",
                event_type="purchase",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=2),
                user_id="user4",
                event_type="logout",
                properties={},
            ),
        ]
        await repo.create_batch(events)

        start_date = yesterday.replace(hour=0, minute=0, second=0)
        end_date = today.replace(hour=23, minute=59, second=59)
        dau_data = await repo.get_dau(start_date, end_date)

        assert len(dau_data) == 2
        dau_data.sort(key=lambda x: x["date"])
        assert dau_data[0]["unique_users"] == 2
        assert dau_data[1]["unique_users"] == 3

    @pytest.mark.asyncio
    async def test_get_dau_excludes_archived(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

        event = EventCreateRequestSchema(
            event_id=uuid4(),
            occurred_at=today,
            user_id="user1",
            event_type="login",
            properties={},
        )
        await repo.create_batch([event])

        db_event = await repo.get_by_event_id(event.event_id)
        db_event.is_archived = True
        await async_db_session.commit()

        start_date = today.replace(hour=0, minute=0, second=0)
        end_date = today.replace(hour=23, minute=59, second=59)
        dau_data = await repo.get_dau(start_date, end_date)

        assert len(dau_data) == 0

    @pytest.mark.asyncio
    async def test_get_top_events_basic(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

        events = [
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today,
                user_id="user1",
                event_type="page_view",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=1),
                user_id="user2",
                event_type="page_view",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=2),
                user_id="user3",
                event_type="page_view",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=3),
                user_id="user1",
                event_type="login",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=4),
                user_id="user2",
                event_type="login",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=today + timedelta(hours=5),
                user_id="user1",
                event_type="purchase",
                properties={},
            ),
        ]
        await repo.create_batch(events)

        start_date = today.replace(hour=0, minute=0, second=0)
        end_date = today.replace(hour=23, minute=59, second=59)
        top_events = await repo.get_top_events(start_date, end_date, limit=10)

        assert len(top_events) == 3
        assert top_events[0]["event_type"] == "page_view"
        assert top_events[0]["count"] == 3
        assert top_events[1]["event_type"] == "login"
        assert top_events[1]["count"] == 2
        assert top_events[2]["event_type"] == "purchase"
        assert top_events[2]["count"] == 1

    @pytest.mark.asyncio
    async def test_get_top_events_with_limit(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)

        event_types = ["type1", "type2", "type3", "type4", "type5"]
        events = []
        for i, event_type in enumerate(event_types):
            for j in range(5 - i):
                events.append(
                    EventCreateRequestSchema(
                        event_id=uuid4(),
                        occurred_at=today + timedelta(hours=i, minutes=j),
                        user_id=f"user{j}",
                        event_type=event_type,
                        properties={},
                    )
                )

        await repo.create_batch(events)

        start_date = today.replace(hour=0, minute=0, second=0)
        end_date = today.replace(hour=23, minute=59, second=59)

        # Запрашиваем только топ 3
        top_events = await repo.get_top_events(start_date, end_date, limit=3)

        assert len(top_events) == 3
        assert top_events[0]["event_type"] == "type1"
        assert top_events[0]["count"] == 5
        assert top_events[1]["event_type"] == "type2"
        assert top_events[1]["count"] == 4
        assert top_events[2]["event_type"] == "type3"
        assert top_events[2]["count"] == 3

    @pytest.mark.asyncio
    async def test_get_retention_basic(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        start_date = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0) - timedelta(days=3)

        events = [
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=start_date,
                user_id="user1",
                event_type="login",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=start_date + timedelta(hours=1),
                user_id="user2",
                event_type="login",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=start_date + timedelta(days=1),
                user_id="user1",
                event_type="page_view",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=start_date + timedelta(days=2),
                user_id="user1",
                event_type="click",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=start_date + timedelta(days=2, hours=1),
                user_id="user2",
                event_type="purchase",
                properties={},
            ),
        ]
        await repo.create_batch(events)

        retention_data = await repo.get_retention(start_date, windows=2, period_type="daily")

        assert len(retention_data) > 0
        first_cohort = retention_data[0]
        assert first_cohort["users"] == 2
        assert first_cohort["period_0"] == 100.0
        assert first_cohort["period_1"] == 50.0
        assert first_cohort["period_2"] == 100.0
