import sys
from pathlib import Path

repo_root = Path(__file__).parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

import asyncio
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from uuid import uuid4

import pytest
import pytest_asyncio
from fakeredis import aioredis as fakeredis
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.database import get_db, get_duckdb, get_redis
from app.database.duckdb_session import DuckDBConnection
from app.database.models.base import Base
from app.database.models.user import User
from app.main import app
from app.security.passwords import hash_password
from app.security.permissions import get_current_user as app_get_current_user
from app.security.token_manager import get_jwt_manager

TEST_DATABASE_URL_ASYNC = "sqlite+aiosqlite:///:memory:"
TEST_DATABASE_URL_SYNC = "sqlite:///:memory:"

test_async_engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False, future=True)
test_sync_engine = create_engine(TEST_DATABASE_URL_SYNC, echo=False, future=True)

TestAsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    test_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

@pytest_asyncio.fixture(scope="function")
async def async_db_session(test_db_session: AsyncSession) -> AsyncSession:
    return test_db_session


@pytest.fixture(scope="function")
def sync_db_session():
    Base.metadata.create_all(test_sync_engine)
    session = Session(test_sync_engine)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(test_sync_engine)


@pytest_asyncio.fixture
async def fake_redis() -> AsyncGenerator[Redis, None]:
    redis = fakeredis.FakeRedis(decode_responses=False)
    try:
        yield redis
    finally:
        await redis.flushall()
        await redis.aclose()


@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def test_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = TestAsyncSessionLocal()

    try:
        yield async_session
    finally:
        await async_session.close()
        async with test_async_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(
    test_db_session: AsyncSession,
    fake_redis: Redis,
) -> AsyncGenerator[AsyncClient, None]:

    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("TestPassword123!"),
        is_active=True,
    )
    test_db_session.add(user)
    await test_db_session.commit()
    await test_db_session.refresh(user)

    jwt_manager = get_jwt_manager()
    access_token = jwt_manager.create_access_token(data={"sub": user.username}, expires_delta=timedelta(minutes=60))

    async def override_get_db():
        async_session = TestAsyncSessionLocal()
        try:
            yield async_session
            await async_session.commit()
        except Exception:
            await async_session.rollback()
            raise
        finally:
            await async_session.close()

    async def override_get_redis():
        yield fake_redis

    async def override_get_current_user():
        return user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis
    app.dependency_overrides[app_get_current_user] = override_get_current_user

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        yield client

    app.dependency_overrides.clear()


def create_event_data(
    event_id: str = None,
    occurred_at: str = None,
    user_id: str = "user123",
    event_type: str = "page_view",
    properties: dict = None,
) -> dict:
    return {
        "event_id": event_id or str(uuid4()),
        "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
        "event_type": event_type,
        "properties": properties or {"page": "/home"},
    }


@pytest.fixture
def sample_event_data() -> dict:
    return create_event_data()


@pytest.fixture(scope="function")
def duckdb_tmp_path(tmp_path):
    return str(tmp_path / "events.duckdb")


@pytest.fixture(scope="function")
def duckdb_write_session(duckdb_tmp_path):
    conn = DuckDBConnection(db_path=duckdb_tmp_path, read_only=False)
    session = conn.get_session()
    try:
        yield session
    finally:
        session.close()
        conn.close()


@pytest_asyncio.fixture(scope="function")
async def analytics_client(authenticated_client, duckdb_tmp_path, duckdb_write_session):

    def override_get_duckdb():
        route = DuckDBConnection(db_path=duckdb_tmp_path, read_only=False)
        session = route.get_session()
        try:
            session.execute(text("LOAD json"))
        except Exception:
            try:
                session.execute(text("INSTALL json"))
                session.execute(text("LOAD json"))
            except Exception:
                pass
        try:
            yield session
        finally:
            session.close()
            route.close()

    app.dependency_overrides[get_duckdb] = override_get_duckdb
    try:
        yield authenticated_client
    finally:
        app.dependency_overrides.pop(get_duckdb, None)


@pytest.fixture
def sample_events_batch() -> list[dict]:
    return [
        create_event_data(user_id="user1", event_type="login"),
        create_event_data(user_id="user2", event_type="page_view"),
        create_event_data(user_id="user3", event_type="purchase"),
        create_event_data(user_id="user1", event_type="page_view"),
        create_event_data(user_id="user2", event_type="logout"),
    ]


def pytest_configure(config):
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "e2e: End-to-end tests")
