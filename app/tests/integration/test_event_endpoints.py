from datetime import datetime, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient


class TestEventEndpoints:

    @pytest.mark.asyncio
    async def test_create_events_success(self, authenticated_client: AsyncClient):
        event_data = {
            "events": [
                {
                    "event_id": str(uuid4()),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "user_id": "user123",
                    "event_type": "page_view",
                    "properties": {"page": "/home"},
                }
            ]
        }

        response = await authenticated_client.post("/events", json=event_data)

        assert response.status_code == 202
        data = response.json()
        assert data["created"] == 1
        assert data["duplicates"] == 0
        assert "enqueued" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_create_events_batch(self, authenticated_client: AsyncClient):
        event_data = {
            "events": [
                {
                    "event_id": str(uuid4()),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "user_id": f"user{i}",
                    "event_type": "login",
                    "properties": {},
                }
                for i in range(5)
            ]
        }

        response = await authenticated_client.post("/events", json=event_data)

        assert response.status_code == 202
        data = response.json()
        assert data["created"] == 5
        assert data["duplicates"] == 0

    @pytest.mark.asyncio
    async def test_create_events_unauthorized(self, client: AsyncClient):
        event_data = {
            "events": [
                {
                    "event_id": str(uuid4()),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "user_id": "user123",
                    "event_type": "click",
                    "properties": {},
                }
            ]
        }

        response = await client.post("/events", json=event_data)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_events_validation_error(self, authenticated_client: AsyncClient):
        event_data = {
            "events": [
                {
                    "event_id": str(uuid4()),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "event_type": "page_view",
                    "properties": {},
                }
            ]
        }

        response = await authenticated_client.post("/events", json=event_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_events_empty_batch(self, authenticated_client: AsyncClient):
        event_data = {"events": []}

        response = await authenticated_client.post("/events", json=event_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_events_too_many(self, authenticated_client: AsyncClient):
        event_data = {
            "events": [
                {
                    "event_id": str(uuid4()),
                    "occurred_at": datetime.now(timezone.utc).isoformat(),
                    "user_id": f"user{i}",
                    "event_type": "spam",
                    "properties": {},
                }
                for i in range(1001)
            ]
        }

        response = await authenticated_client.post("/events", json=event_data)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_queue_status(self, authenticated_client: AsyncClient):
        response = await authenticated_client.get("/events/queue-status")

        assert response.status_code == 200
        data = response.json()

        assert "main_queue_size" in data
        assert "retry_queue_size" in data
        assert "dead_letter_queue_size" in data

        assert isinstance(data["main_queue_size"], int)
        assert isinstance(data["retry_queue_size"], int)
        assert isinstance(data["dead_letter_queue_size"], int)

    @pytest.mark.asyncio
    async def test_get_queue_status_unauthorized(self, client: AsyncClient):
        response = await client.get("/events/queue-status")

        assert response.status_code == 401
