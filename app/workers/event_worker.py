import asyncio
import logging
import signal
import sys

from database import get_redis
from event_queue import EventQueueConsumer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class EventWorker:
    def __init__(self):
        self.running = False
        self.consumer: EventQueueConsumer | None = None

    async def start(self):
        logger.info("Starting worker")

        redis = await get_redis()
        self.consumer = EventQueueConsumer(redis)

        self.running = True

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info("Event Worker started successfully")

        await self._process_loop()

    def _signal_handler(self, signum, frame):
        logger.info(f"Signal {signum}, shutting down...")
        self.running = False

    async def _process_loop(self):
        while self.running:
            try:
                processed = await self.consumer.consume_events(batch_size=100)
                if processed > 0:
                    logger.info(f"Processed {processed} events from main queue")

                retried = await self.consumer.process_retry_queue(batch_size=10)

                if retried > 0:
                    logger.info(f"Processed {retried} events from retry queue")

                if processed == 0 and retried == 0:
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error in loop: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info("Event Worker stopped")


async def main():
    worker = EventWorker()
    await worker.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
        sys.exit(0)
