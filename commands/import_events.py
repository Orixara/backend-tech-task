#!/usr/bin/env python3

import asyncio
import json
import logging
import sys
from pathlib import Path
from uuid import UUID

import pandas as pd

from config.settings import settings
from database import get_db_contextmanager
from repositories import EventRepository
from schemas import EventCreateRequestSchema


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

async def import_events_from_csv(csv_file_path: Path) -> None:
    logger.info(f"Reading CSV file: {csv_file_path}")

    if not csv_file_path.exists():
        logger.error(f"File not found: {csv_file_path}")
        raise FileNotFoundError(f"CSV file not found: {csv_file_path}")

    dataframe = pd.read_csv(csv_file_path)
    total_rows = len(dataframe)
    logger.info(f"Found {total_rows} rows in CSV")

    valid_events = []
    skipped_rows = 0

    for row_index, row in dataframe.iterrows():
        try:
            properties_dict = {}
            if pd.notna(row.get("properties_json")):
                properties_dict = json.loads(row["properties_json"])

            event_schema = EventCreateRequestSchema(
                event_id=UUID(str(row["event_id"])),
                occurred_at=pd.to_datetime(row["occurred_at"]),
                user_id=str(row["user_id"]),
                event_type=str(row["event_type"]),
                properties=properties_dict
            )
            valid_events.append(event_schema)
        except Exception as error:
            logger.warning(f"Skipping row {row_index}: {error}")
            skipped_rows += 1
            continue

    if not valid_events:
        logger.error("No valid events found in CSV")
        raise ValueError("No valid events to import")

    logger.info(f"Parsed {len(valid_events)} valid events ({skipped_rows} skipped)")

    batch_size = 1000
    total_created = 0
    total_duplicates = 0
    num_batches = (len(valid_events) + batch_size - 1) // batch_size

    logger.info(f"Starting import in {num_batches} batches of {batch_size} events")

    async with get_db_contextmanager() as database_session:
        event_repository = EventRepository(database_session)

        for batch_index in range(0, len(valid_events), batch_size):
            current_batch = valid_events[batch_index: batch_index + batch_size]
            created_count, duplicates_count = await event_repository.create_batch(current_batch)

            total_created += created_count
            total_duplicates += duplicates_count

            current_batch_number = batch_index // batch_size + 1
            logger.info(
                f"Batch {current_batch_number}/{num_batches}: "
                f"created={created_count}, duplicates={duplicates_count}"
            )

    logger.info("-" * 60)
    logger.info("Import completed successfully")
    logger.info(f"Total events processed: {len(valid_events)}")
    logger.info(f"Created: {total_created}")
    logger.info(f"Duplicates: {total_duplicates}")
    logger.info("-" * 60)

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    csv_file_path = Path(sys.argv[1])

    logger.info("Starting CSV import process")
    try:
        asyncio.run(import_events_from_csv(csv_file_path))
        logger.info("Import process finished successfully")
        sys.exit(0)

    except KeyboardInterrupt:
        logger.warning("Import cancelled by user")
        sys.exit(1)

    except Exception as error:
        logger.error(f"Import failed: {error}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()