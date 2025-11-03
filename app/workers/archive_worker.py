import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

import duckdb
from database import get_db_contextmanager, get_duckdb
from database.models import Event
from sqlalchemy import and_, select, update
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
        self.duckdb_conn: duckdb.DuckDBPyConnection | None = None

    async def start(self):
        logger.info("Starting Archive Worker")
        self.duckdb_conn = get_duckdb()
        self.running = True
        logger.info("Archive Worker started")
        await self._archive_loop()

    async def _archive_loop(self):
        while self.running:
            try:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.ARCHIVE_THRESHOLD_DAYS)

                total_archived = await self._archive_old_events(cutoff_date)

                logger.info(f"Archived {total_archived} events to DuckDB")
                logger.info(f"Archived complete.")
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

                logger.info(f"Archived {len(events)} events " f"Total: {total_archived}")
        return total_archived

    async def _write_to_duckdb(self, events: list[Event]):
        if not events:
            return

        values = [
            (
                str(event.event_id),
                event.occurred_at.isoformat(),
                event.user_id,
                event.event_type,
                json.dumps(event.properties),
                event.created_at.isoformat(),
                datetime.now(timezone.utc).isoformat(),
            )
            for event in events
        ]

        self.duckdb_conn.executemany(
            """
            INSERT OR IGNORE INTO events (
                event_id, occurred_at, user_id, event_type,
                properties, created_at, archived_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )

    async def _mark_as_archived(self, db: AsyncSession, event_ids: list[int]):
        stmt = update(Event).where(Event.id.in_(event_ids)).values(is_archived=True)

        await db.execute(stmt)
        await db.commit()


async def main():
    worker = ArchiveWorker()
    await worker.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Archive worker interrupted")
