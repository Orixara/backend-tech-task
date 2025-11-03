from fastapi import APIRouter, Depends, HTTPException, status

from database import get_redis
from event_queue import EventQueueProducer
from schemas import EventsBatchCreateRequestSchema, EventsBatchResponseSchema
from security.permissions import get_current_user
from database.models import User


router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Ingest events",
    description="Accepts array of events and resending event"
)
async def create_events(
    batch: EventsBatchCreateRequestSchema,
    current_user: User = Depends(get_current_user),
    redis = Depends(get_redis)
) -> EventsBatchResponseSchema:
    try:
        producer = EventQueueProducer(redis)
        enqueued = await producer.enqueue_events(batch.events)

        return EventsBatchResponseSchema(
            created=enqueued,
            duplicates=0,
            message=f"Successfully enqueued {enqueued} events for processing",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error enqueuing events: {str(e)}"
        )

@router.get(
    "/queue-status",
    summary="Get queue status",
    description="Returns current status of event queues",
)
async def get_queue_status(
        current_user: User = Depends(get_current_user),
        redis=Depends(get_redis),
):
    producer = EventQueueProducer(redis)

    return {
        "main_queue_size": await producer.get_queue_size(),
        "retry_queue_size": await producer.get_retry_queue_size(),
        "dead_letter_queue_size": await producer.get_dlq_size(),
    }