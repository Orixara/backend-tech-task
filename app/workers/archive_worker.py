import asyncio
import logging
from datetime import datetime, timedelta, timezone

from database import get_db_contextmanager
from database.duckdb_session import get_duckdb_session
from database.models import Event
from sqlalchemy import and_, select, update
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ArchiveWorker:
    ARCHIVE_THRESHOLD_DAYS = 30
    BATCH_SIZE = 1000

    def __init__(self):
        self.running = False

    async def start(self):
        logger.info("Starting Archive Worker")
        self._ensure_duckdb_initialized()
        self.running = True
        logger.info("Archive Worker started")
        await self._archive_loop()

    def _ensure_duckdb_initialized(self):
        try:
            with get_duckdb_session() as session:
                result = session.execute(select(Event).limit(1))
                result.fetchone()

            logger.info("DuckDB connection and schema verified")
        except Exception as e:
            logger.error(f"Failed to initialize DuckDB: {e}", exc_info=True)
            raise

    async def _archive_loop(self):
        while self.running:
            try:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.ARCHIVE_THRESHOLD_DAYS)

                total_archived = await self._archive_old_events(cutoff_date)

                logger.info(f"Archived {total_archived} events to DuckDB")
                logger.info(f"Archive complete.")
                await asyncio.sleep(24 * 60 * 60)
            except Exception as e:
                logger.error(f"Error in archive loop: {e}", exc_info=True)
                await asyncio.sleep(60 * 60)

    async def _archive_old_events(self, cutoff_date: datetime) -> int:
        total_archived = 0

        async with get_db_contextmanager() as db:
            while True:
                stmt = (
                    select(Event)
                    .where(and_(Event.occurred_at < cutoff_date, Event.is_archived == False))
                    .limit(self.BATCH_SIZE)
                )

                result = await db.execute(stmt)
                events = result.scalars().all()

                if not events:
                    break

                await self._write_to_duckdb(events)

                event_ids = [event.id for event in events]
                await self._mark_as_archived(db, event_ids)

                total_archived += len(events)

                logger.info(f"Archived {len(events)} events. Total: {total_archived}")
        return total_archived

    async def _write_to_duckdb(self, events: list[Event]):
        if not events:
            return

        try:
            with get_duckdb_session() as duck_session:
                events_data = [
                    {
                        "id": event.id,
                        "event_id": event.event_id,
                        "occurred_at": event.occurred_at,
                        "user_id": event.user_id,
                        "event_type": event.event_type,
                        "properties": event.properties,
                        "created_at": event.created_at,
                        "is_archived": True,
                    }
                    for event in events
                ]

                stmt = sqlite_insert(Event).values(events_data)
                stmt = stmt.prefix_with("OR IGNORE")
                duck_session.execute(stmt)
                duck_session.commit()
                logger.debug(f"Successfully wrote {len(events)} events to DuckDB")
        except Exception as e:
            logger.error(f"Error writing to DuckDB: {e}", exc_info=True)
            raise

    async def _mark_as_archived(self, db: AsyncSession, event_ids: list[int]):
        stmt = update(Event).where(Event.id.in_(event_ids)).values(is_archived=True)

        await db.execute(stmt)
        await db.commit()

        logger.debug(f"Marked {len(event_ids)} events as archived in PostgreSQL")


async def main():
    worker = ArchiveWorker()
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("Archive worker interrupted by user")
        worker.running = False
    except Exception as e:
        logger.error(f"Archive worker failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    asyncio.run(main())
