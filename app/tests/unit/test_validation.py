from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.event import EventCreateRequestSchema


class TestEventValidation:
    """Тести валідації даних івентів"""

    def test_valid_event_creation(self):
        event = EventCreateRequestSchema(
            event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            user_id="user123",
            event_type="page_view",
            properties={"page": "/home", "referrer": "google"},
        )

        assert event.event_id is not None
        assert event.user_id == "user123"
        assert event.event_type == "page_view"
        assert isinstance(event.properties, dict)

    def test_invalid_occurred_at_format(self):
        with pytest.raises(ValidationError) as exc_info:
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at="not-a-valid-date",
                user_id="user123",
                event_type="login",
                properties={},
            )

        errors = exc_info.value.errors()
        assert any("occurred_at" in str(error) for error in errors)

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError) as exc_info:
            EventCreateRequestSchema(
                occurred_at=datetime.now(timezone.utc),
                user_id="user123",
                event_type="login",
                properties={},
            )

        errors = exc_info.value.errors()
        assert any("event_id" in error["loc"] for error in errors)

        with pytest.raises(ValidationError) as exc_info:
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=datetime.now(timezone.utc),
                event_type="login",
                properties={},
            )

        errors = exc_info.value.errors()
        assert any("user_id" in error["loc"] for error in errors)

    def test_user_id_too_long(self):
        long_user_id = "u" * 101

        with pytest.raises(ValidationError) as exc_info:
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=datetime.now(timezone.utc),
                user_id=long_user_id,
                event_type="login",
                properties={},
            )

        errors = exc_info.value.errors()
        assert any("user_id" in error["loc"] for error in errors)

    def test_event_type_too_long(self):
        long_event_type = "e" * 101

        with pytest.raises(ValidationError) as exc_info:
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=datetime.now(timezone.utc),
                user_id="user123",
                event_type=long_event_type,
                properties={},
            )

        errors = exc_info.value.errors()
        assert any("event_type" in error["loc"] for error in errors)

    def test_invalid_properties_type(self):
        with pytest.raises(ValidationError) as exc_info:
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=datetime.now(timezone.utc),
                user_id="user123",
                event_type="login",
                properties="not-a-dict",
            )

        errors = exc_info.value.errors()
        assert any("properties" in error["loc"] for error in errors)

    def test_empty_user_id(self):
        with pytest.raises(ValidationError) as exc_info:
            EventCreateRequestSchema(
                event_id=uuid4(),
                occurred_at=datetime.now(timezone.utc),
                user_id="",
                event_type="login",
                properties={},
            )

        errors = exc_info.value.errors()
        assert any("user_id" in error["loc"] for error in errors)