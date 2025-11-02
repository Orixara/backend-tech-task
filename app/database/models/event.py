from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQL_UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_id: Mapped[UUID] = mapped_column(
        PostgreSQL_UUID(as_uuid=True),
        unique=True,
        nullable=False,
        default=uuid4,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    properties: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    __table_args__ = (
        Index("ix_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_events_type_occurred", "event_type", "occurred_at"),
        Index("ix_events_user_type_occurred", "user_id", "event_type", "occurred_at"),
        Index("ix_events_archived_occurred", "is_archived", "occurred_at"),
    )

    def __repr__(self):
        return f"Event(id={self.id}, type={self.event_type}, user={self.user_id})"
