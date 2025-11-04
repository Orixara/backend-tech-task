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
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session
from sqlalchemy import create_engine

from app.main import app
from app.database.models.base import Base
from app.database.models.user import User
from app.database import get_db, get_redis
from app.security.passwords import hash_password
from app.security.token_manager import get_jwt_manager
from fakeredis import aioredis as fakeredis
from redis.asyncio import Redis


TEST_DATABASE_URL_ASYNC = "sqlite+aiosqlite:///:memory:"
TEST_DATABASE_URL_SYNC = "sqlite:///:memory:"

test_async_engine = create_async_engine(TEST_DATABASE_URL_ASYNC, echo=False, future=True)
test_sync_engine = create_engine(TEST_DATABASE_URL_SYNC, echo=False, future=True)

TestAsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    test_async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture(scope="function")
async def async_db_session() -> AsyncGenerator[AsyncSession, None]:
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestAsyncSessionLocal() as session:
        yield session
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

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

@pytest_asyncio.fixture
async def test_user(async_db_session: AsyncSession) -> User:
    user = User(
        username="testuser",
        email="test@example.com",
        hashed_password=hash_password("TestPassword123!"),
        is_active=True,
    )
    async_db_session.add(user)
    await async_db_session.commit()
    await async_db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def auth_token(test_user: User) -> str:
    jwt_manager = get_jwt_manager()

    token_data = {"sub": test_user.username}
    access_token = jwt_manager.create_access_token(
        data=token_data,
        expires_delta=timedelta(minutes=60)
    )
    return access_token

@pytest_asyncio.fixture(scope="function")
async def client():
    async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
    ) as async_client:
        yield async_client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def authenticated_client(
        async_db_session: AsyncSession,
        fake_redis: Redis,
        auth_token: str
) -> AsyncGenerator[AsyncClient, None]:

    async def override_get_db():
        yield async_db_session

    async def override_get_redis():
        yield fake_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {auth_token}"},
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