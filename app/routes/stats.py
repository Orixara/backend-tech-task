from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from repositories import EventRepository
from schemas import (
    DAUResponseSchema,
    TopEventsResponseSchema,
    RetentionResponseSchema,
)


router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get(
    "/dau",
    summary="Daily Active Users",
    description="Get unique users count per day for date range",
)
async def get_dau(
    from_date: str = Query(
        ...,
        description="Start date (YYYY-MM-DD)",
        example="2025-01-01"
    ),
    to_date: str = Query(
        ...,
        description="End date (YYYY-MM-DD)",
        example="2025-01-31",
    ),
    db: AsyncSession = Depends(get_db),
) -> DAUResponseSchema:
    try:
        start_date = datetime.fromisoformat(from_date)
        end_date = datetime.fromisoformat(to_date)

        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="from_date must be before to_date",
            )

        repo = EventRepository(db)
        dau_date = await repo.get_dau(start_date, end_date)

        return DAUResponseSchema(
            data=dau_date,
            from_date=from_date,
            to_date=to_date,
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format. Use YYYY-MM-DD: {str(e)}",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting DAU: {str(e)}"
        )

@router.get(
    "/top-events",
    summary="Top Event Types",
    description="Get most frequent event types",
)
async def get_top_events(
    from_date: str = Query(
        ...,
        description="Start date (YYYY-MM-DD)",
        example="2025-01-01"
    ),
    to_date: str = Query(
        ...,
        description="End date (YYYY-MM-DD)",
        example="2025-01-31",
    ),
    limit: int = Query(
        10,
        ge=1,
        le=100,
        description="Number of top events to return"
    ),
    db: AsyncSession = Depends(get_db),
) -> TopEventsResponseSchema:
    try:
        start_date = datetime.fromisoformat(from_date)
        end_date = datetime.fromisoformat(to_date)

        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="from_date must be before to_date"
            )

        repo = EventRepository(db)
        top_events_data = await repo.get_top_events(start_date, end_date, limit)

        return TopEventsResponseSchema(
            data=top_events_data,
            from_date=from_date,
            to_date=to_date,
            limit=limit
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format. Use YYYY-MM-DD: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting top events: {str(e)}"
        )

@router.get(
    "/retention",
    summary="Retention analysis",
    description="Get retention analysis for users starting from specified date",
)
async def get_retention(
    start_date: str = Query(
        ...,
        description="Start date for cohorts (YYYY-MM-DD)",
        example="2025-01-01"
    ),
    windows: int = Query(
        3,
        ge=1,
        le=10,
        description="Number of periods to track"
    ),
    period_type: str = Query(
        "daily",
        regex="^(daily|weekly)$",
        description="Period type: daily or weekly"
    ),
    db: AsyncSession = Depends(get_db)
) -> RetentionResponseSchema:
    try:
        cohort_start_date = datetime.fromisoformat(start_date)
        repo = EventRepository(db)
        cohorts_data = await repo.get_retention(
            cohort_start_date,
            windows,
            period_type
        )

        return RetentionResponseSchema(
            cohorts=cohorts_data,
            start_date=start_date,
            windows=windows,
            period_type=period_type
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format. Use YYYY-MM-DD: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting retention: {str(e)}"
        )