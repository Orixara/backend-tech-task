import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import duckdb
import redis
from database import get_db_contextmanager
from database.models import Event, User
from sqlalchemy import delete
from config.settings import settings


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def cleanup_benchmark_data():
    logger.info("Starting cleanup")
    try:
        logger.info("Cleanup PostgreSQL")
        async with get_db_contextmanager() as db:
            result = await db.execute(
                delete(Event).where(Event.user_id.like('bench_user_%'))
            )
            await db.commit()
            deleted_events = result.rowcount
            logger.info(f"Deleted {deleted_events:,} benchmark events")

            result = await db.execute(
                delete(User).where(User.username.like('benchmark_user%'))
            )
            await db.commit()
            deleted_users = result.rowcount
            logger.info(f"Deleted {deleted_users} benchmark users")

        try:
            logger.info("Cleaning DuckDB")
            conn = duckdb.connect('/usr/src/data/analytics.duckdb')
            conn.execute("DELETE FROM events WHERE user_id LIKE 'bench_user_%'")
            conn.close()
            logger.info("Cleaned DuckDB archive")
        except Exception as e:
            logger.warning(f"DuckDB cleanup skipped: {e}")

        try:
            logger.info("Cleaning Redis")
            r = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                decode_responses=True
            )

            queues = [
                'event_queue:main',
                'event_queue:retry',
                'event_queue:dead_letter'
            ]

            total_cleared = 0
            for queue in queues:
                size = r.llen(queue)
                if size > 0:
                    r.delete(queue)
                    total_cleared += size

            if total_cleared > 0:
                logger.info(f"Cleared {total_cleared:,} items")
            else:
                logger.info("Redis already empty")

        except Exception as e:
            logger.warning(f"Redis cleanup skipped: {e}")

        logger.info("Cleanup completed successfully!")
        return True

    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = asyncio.run(cleanup_benchmark_data())
    sys.exit(0 if success else 1)