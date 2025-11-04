from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.event import Event
from app.repositories.event_repository import EventRepository
from app.schemas.event import EventCreateRequestSchema


class TestIdempotency:
    """Тести ідемпотентності створення подій"""

    @pytest.mark.asyncio
    async def test_duplicate_event_id_not_created(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)
        event_id = uuid4()
        event = EventCreateRequestSchema(
            event_id=event_id,
            occurred_at="2025-01-15T10:00:00",
            user_id="user123",
            event_type="login",
            properties={"device": "mobile"},
        )

        created1, duplicates1 = await repo.create_batch([event])
        assert created1 == 1
        assert duplicates1 == 0

        created2, duplicates2 = await repo.create_batch([event])
        assert created2 == 0
        assert duplicates2 == 1

        result = await async_db_session.execute(select(Event).where(Event.event_id == event_id))
        events = result.scalars().all()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_batch_with_internal_duplicates(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        duplicate_event_id = uuid4()
        events = [
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at="2025-01-15T10:00:00",
                user_id="user1",
                event_type="page_view",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at="2025-01-15T10:01:00",
                user_id="user2",
                event_type="click",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=duplicate_event_id,
                occurred_at="2025-01-15T10:02:00",
                user_id="user3",
                event_type="purchase",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at="2025-01-15T10:03:00",
                user_id="user4",
                event_type="logout",
                properties={},
            ),
            EventCreateRequestSchema(
                event_id=duplicate_event_id,
                occurred_at="2025-01-15T10:04:00",
                user_id="user5",
                event_type="login",
                properties={},
            ),
        ]

        created, duplicates = await repo.create_batch(events)

        assert created == 4
        assert duplicates == 1

        result = await async_db_session.execute(select(Event))
        all_events = result.scalars().all()
        assert len(all_events) == 4

    @pytest.mark.asyncio
    async def test_sequential_duplicate_submissions(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)
        event_id = uuid4()

        event = EventCreateRequestSchema(
            event_id=event_id,
            occurred_at="2025-01-15T10:00:00",
            user_id="user123",
            event_type="page_view",
            properties={"page": "/home"},
        )

        results = []
        for _ in range(5):
            created, duplicates = await repo.create_batch([event])
            results.append((created, duplicates))

        assert results[0] == (1, 0)
        for result in results[1:]:
            assert result == (0, 1)

        result = await async_db_session.execute(select(Event).where(Event.event_id == event_id))
        events = result.scalars().all()
        assert len(events) == 1

    @pytest.mark.asyncio
    async def test_concurrent_duplicate_handling(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)
        event_id = uuid4()

        event = EventCreateRequestSchema(
            event_id=event_id,
            occurred_at="2025-01-15T10:00:00",
            user_id="user123",
            event_type="login",
            properties={},
        )

        created1, _ = await repo.create_batch([event])
        assert created1 == 1

        created2, duplicates2 = await repo.create_batch([event])
        assert created2 == 0
        assert duplicates2 == 1

    @pytest.mark.asyncio
    async def test_different_data_same_event_id(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)
        event_id = uuid4()

        event1 = EventCreateRequestSchema(
            event_id=event_id,
            occurred_at="2025-01-15T10:00:00",
            user_id="user1",
            event_type="login",
            properties={"device": "mobile"},
        )

        event2 = EventCreateRequestSchema(
            event_id=event_id,
            occurred_at="2025-01-15T11:00:00",
            user_id="user2",
            event_type="logout",
            properties={"device": "desktop"},
        )

        created1, _ = await repo.create_batch([event1])
        assert created1 == 1

        created2, duplicates2 = await repo.create_batch([event2])
        assert created2 == 0
        assert duplicates2 == 1

        result = await async_db_session.execute(select(Event).where(Event.event_id == event_id))
        saved_event = result.scalar_one()

        assert saved_event.user_id == "user1"
        assert saved_event.event_type == "login"
        assert saved_event.properties["device"] == "mobile"

    @pytest.mark.asyncio
    async def test_empty_batch_idempotency(self, async_db_session: AsyncSession):
        repo = EventRepository(async_db_session)

        created, duplicates = await repo.create_batch([])

        assert created == 0
        assert duplicates == 0

        result = await async_db_session.execute(select(Event))
        events = result.scalars().all()
        assert len(events) == 0
