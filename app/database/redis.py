from typing import Optional

import redis.asyncio as aioredis
from config.settings import settings
from redis.asyncio import Redis

_redis_pool: Optional[Redis] = None


async def get_redis_pool() -> Redis:
    global _redis_pool

    if _redis_pool is None:
        _redis_pool = await aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            max_connections=10,
        )

    return _redis_pool


async def close_redis_pool() -> None:
    global _redis_pool

    if _redis_pool is not None:
        await _redis_pool.close()
        _redis_pool = None


async def get_redis() -> Redis:
    return await get_redis_pool()
