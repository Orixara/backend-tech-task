from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from repositories import EventRepository
from schemas import EventsBatchCreateRequestSchema, EventsBatchResponseSchema


router = APIRouter(prefix="/events", tags=["Events"])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Ingest events",
    description=
    """
    Accepts array of events and resending event 
    with same event_id does not create duplicate.
    """
)
async def create_events(
    batch: EventsBatchCreateRequestSchema,
    db: AsyncSession = Depends(get_db)
) -> EventsBatchResponseSchema:
    try:
        repo = EventRepository(db)
        created, duplicates = await repo.create_batch(batch.events)

        if created == 0 and duplicates > 0:
            message = f"All {duplicates} events already exist (duplicates)"
        elif duplicates == 0:
            message = f"Successfully created {created} events"
        else:
            message = f"Created {created} events, skipped {duplicates} duplicates"

        return EventsBatchResponseSchema(
            created=created,
            duplicates=duplicates,
            message=message,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error creating events: {str(e)}"
        )