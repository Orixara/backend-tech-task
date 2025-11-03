import json
from typing import List
from uuid import UUID

from redis.asyncio import Redis
from schemas.event import EventCreateRequestSchema


class EventQueueProducer:
    QUEUE_NAME = "events:queue"
    RETRY_QUEUE_NAME = "events:retry"
    DLQ_NAME = "events:dlq"

    def __init__(self, redis: Redis):
        self.redis = redis

    async def enqueue_events(self, events: List[EventCreateRequestSchema]) -> int:
        if not events:
            return 0

        async with self.redis.pipeline(transaction=False) as pipe:
            for event in events:
                event_data = {
                    "event_id": str(event.event_id),
                    "occurred_at": event.occurred_at.isoformat(),
                    "user_id": event.user_id,
                    "event_type": event.event_type,
                    "properties": event.properties,
                    "retry_count": 0,
                }

                pipe.rpush(self.QUEUE_NAME, json.dumps(event_data))
            await pipe.execute()
        return len(events)

    async def get_queue_size(self) -> int:
        return await self.redis.llen(self.QUEUE_NAME)

    async def get_retry_queue_size(self) -> int:
        return await self.redis.llen(self.RETRY_QUEUE_NAME)

    async def get_dlq_size(self) -> int:
        return await self.redis.llen(self.DLQ_NAME)
