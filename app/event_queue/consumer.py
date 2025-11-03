import asyncio
import json
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from database import get_db_contextmanager
from redis.asyncio import Redis
from repositories.event_repository import EventRepository
from schemas.event import EventCreateRequestSchema
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class EventQueueConsumer:
    QUEUE_NAME = "events:queue"
    RETRY_QUEUE_NAME = "events:retry"
    DLQ_NAME = "events:dlq"
    MAX_RETRIES = 3
    RETRY_DELAY_BASE = 2

    def __init__(self, redis: Redis):
        self.redis = redis

    async def process_event(self, event_data: dict, db: AsyncSession) -> bool:
        try:
            event = EventCreateRequestSchema(
                event_id=UUID(event_data["event_id"]),
                occurred_at=datetime.fromisoformat(event_data["occurred_at"]),
                user_id=event_data["user_id"],
                event_type=event_data["event_type"],
                properties=event_data.get("properties", {}),
            )

            repo = EventRepository(db)
            created, duplicates = await repo.create_batch([event])

            if created == 1:
                logger.info(f"Event {event.event_id} processed successfully")
            else:
                logger.info(f"Event {event.event_id} was duplicate, skipped")

            return True
        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
            return False

    async def handle_failed_event(self, event_data: dict) -> None:
        retry_count = event_data.get("retry_count", 0)
        if retry_count < self.MAX_RETRIES:
            event_data["retry_count"] = retry_count + 1
            delay = self.RETRY_DELAY_BASE**retry_count
            logger.warning(
                f"Event {event_data.get('event_id')} failed, " f"retry {retry_count + 1}/{self.MAX_RETRIES} in {delay}s"
            )
            await self.redis.rpush(self.RETRY_QUEUE_NAME, json.dumps(event_data))
        else:
            logger.error(
                f"Event {event_data.get('event_id')} failed after " f"{self.MAX_RETRIES} retries, moving to DLQ"
            )
            await self.redis.rpush(self.DLQ_NAME, json.dumps(event_data))

    async def consume_events(self, batch_size: int = 10) -> int:
        processed = 0

        async with get_db_contextmanager() as db:
            for _ in range(batch_size):
                result = await self.redis.blpop(self.QUEUE_NAME, timeout=1)

                if not result:
                    break

                _, event_json = result
                event_data = json.loads(event_json)

                success = await self.process_event(event_data, db)

                if success:
                    processed += 1
                else:
                    await self.handle_failed_event(event_data)
        return processed

    async def process_retry_queue(self, batch_size: int = 5) -> int:
        processed = 0

        async with get_db_contextmanager() as db:
            for _ in range(batch_size):
                result = await self.redis.lpop(self.RETRY_QUEUE_NAME)

                if not result:
                    break

                event_data = json.loads(result)
                retry_count = event_data.get("retry_count", 0)

                delay = self.RETRY_DELAY_BASE ** (retry_count - 1)
                await asyncio.sleep(delay)

                success = await self.process_event(event_data, db)

                if success:
                    processed += 1
                else:
                    await self.handle_failed_event(event_data)
        return processed
