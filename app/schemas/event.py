from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventCreateRequestSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID
    occurred_at: datetime
    user_id: str
    event_type: str
    properties: dict = Field(default_factory=dict)

    @field_validator("properties")
    @classmethod
    def validate_properties(cls, v):
        if not isinstance(v, dict):
            raise ValueError("properties have to be object")
        return v


class EventsBatchResponseSchema(BaseModel):
    created: int
    duplicates: int
    message: str


class EventsBatchCreateRequestSchema(BaseModel):
    events: list[EventCreateRequestSchema] = Field(..., min_length=1, max_length=1000)


class DAUItemSchema(BaseModel):
    date: str
    unique_users: int


class DAUResponseSchema(BaseModel):
    data: list[DAUItemSchema]
    from_date: str
    to_date: str


class TopEventItemSchema(BaseModel):
    event_type: str
    count: int


class TopEventsResponseSchema(BaseModel):
    data: list[TopEventItemSchema]
    from_date: str
    to_date: str
    limit: int


class RetentionCohortSchema(BaseModel):
    cohort_date: str
    users: int
    period_0: float
    period_1: float | None = None
    period_2: float | None = None
    period_3: float | None = None


class RetentionResponseSchema(BaseModel):
    cohorts: list[RetentionCohortSchema]
    start_date: str
    windows: int
    period_type: str