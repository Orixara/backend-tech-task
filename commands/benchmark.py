import asyncio
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent / "app"))


log_file = Path(__file__).parent.parent / "benchmark_results.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_file, mode="w", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class BenchmarkRunner:
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.access_token = None

    async def setup(self):
        logger.info("Setting up benchmark")
        async with httpx.AsyncClient() as client:
            username = f"benchmark_user_{int(time.time())}"
            email = f"benchmark_{int(time.time())}@test.com"

            register_response = await client.post(
                f"{self.base_url}/auth/register",
                json={
                    "username": username,
                    "email": email,
                    "password": "BenchTest123!",
                },
            )

            if register_response.status_code == 201:
                logger.info("Test user registered successfully")
            elif register_response.status_code == 409:
                logger.warning("User already exists")
                username = "benchmark_user"
            else:
                logger.error(f"Registration failed: {register_response.status_code}")
                logger.error(f"Response: {register_response.text}")
                return False

            login_response = await client.post(
                f"{self.base_url}/auth/login",
                json={
                    "username": username,
                    "password": "BenchTest123!",
                },
            )

            if login_response.status_code == 200:
                self.access_token = login_response.json()["access_token"]
                logger.info("Authentication successful")
                return True
            else:
                logger.error(f"Login failed: {login_response.status_code}")
                return False

    def generate_events(self, count: int, start_date: datetime) -> list[dict]:
        logger.info(f"Generating {count:,} test events")

        events = []
        event_types = ["page_view", "button_click", "purchase", "signup", "logout"]

        for i in range(count):
            event_date = start_date + timedelta(seconds=i % 86400)

            events.append(
                {
                    "event_id": str(uuid4()),
                    "occurred_at": event_date.isoformat(),
                    "user_id": f"bench_user_{i % 1000}",
                    "event_type": event_types[i % len(event_types)],
                    "properties": {
                        "benchmark": True,
                        "batch": i // 1000,
                        "index": i,
                    },
                }
            )

        logger.info(f"Generated {len(events):,} events")
        return events

    async def benchmark_ingestion(self, total_events: int = 100_000, batch_size: int = 1000):
        logger.info(f"BENCHMARK 1: Event ingestion ({total_events:,} " f"events, batch size: {batch_size})")

        start_date = datetime.now() - timedelta(days=15)
        all_events = self.generate_events(total_events, start_date)

        logger.info("Sending events to API")

        batches = [all_events[i : i + batch_size] for i in range(0, len(all_events), batch_size)]
        successful = 0
        failed = 0
        latencies = []

        headers = {"Authorization": f"Bearer {self.access_token}"}

        start_time = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            for i, batch in enumerate(batches):
                batch_start = time.time()

                try:
                    response = await client.post(
                        f"{self.base_url}/events",
                        json={"events": batch},
                        headers=headers,
                    )

                    batch_latency = time.time() - batch_start
                    latencies.append(batch_latency)

                    if response.status_code in [200, 201, 202]:
                        successful += len(batch)
                        if (i + 1) % 10 == 0 or i == 0:
                            logger.info(
                                f"Batch {i + 1}/{len(batches)}: "
                                f"{len(batch)} events sent ({batch_latency:.2f}s, "
                                f"total: {successful:,})"
                            )
                    else:
                        failed += len(batch)
                        logger.error(f"Batch {i + 1}/{len(batches)} failed: {response.status_code}")
                except Exception as e:
                    failed += len(batch)
                    logger.error(f"Batch {i + 1}/{len(batches)} error: {e}")

        end_time = time.time()
        total_time = end_time - start_time

        throughput = successful / total_time if total_time > 0 else 0
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        min_latency = min(latencies) if latencies else 0
        max_latency = max(latencies) if latencies else 0

        logger.info("Waiting for worker to process queue")
        await asyncio.sleep(10)

        async with httpx.AsyncClient() as client:
            try:
                queue_response = await client.get(
                    f"{self.base_url}/events/queue-status",
                    headers=headers,
                )
                if queue_response.status_code == 200:
                    queue_data = queue_response.json()
                    logger.info(f"Queue status: {queue_data}")
            except Exception as e:
                logger.warning(f"Could not fetch queue status: {e}")

        logger.info("INGESTION RESULTS")
        logger.info(f"Total events: {total_events:,}")
        logger.info(f"Successful: {successful:,} ({successful / total_events * 100:.1f}%)")
        logger.info(f"Failed: {failed:,} ({failed / total_events * 100:.1f}%)")
        logger.info(f"Total time: {total_time:.2f} seconds")
        logger.info(f"Throughput: {throughput:.0f} events/sec")
        logger.info(f"Avg latency: {avg_latency * 1000:.0f}ms per batch")
        logger.info(f"Min latency: {min_latency * 1000:.0f}ms")
        logger.info(f"Max latency: {max_latency * 1000:.0f}ms")
        logger.info(f"Batch size: {batch_size} events")

        return {
            "total_events": total_events,
            "successful": successful,
            "failed": failed,
            "total_time": total_time,
            "throughput": throughput,
            "avg_latency": avg_latency,
            "min_latency": min_latency,
            "max_latency": max_latency,
        }

    async def benchmark_analytics(self):
        logger.info("BENCHMARK 2: Analytics queries")

        headers = {"Authorization": f"Bearer {self.access_token}"}

        results = {}
        logger.info("Testing DAU query")
        start_time = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/stats/dau",
                    params={
                        "from_date": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                        "to_date": datetime.now().strftime("%Y-%m-%d"),
                    },
                    headers=headers,
                )

                dau_time = time.time() - start_time

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"DAU query completed: {dau_time * 1000:.0f}ms " f"({len(data.get('data', []))} days returned)"
                    )
                    results["dau_time"] = dau_time
                else:
                    logger.error(f"DAU query failed: {response.status_code}")

            except Exception as e:
                logger.error(f"DAU query error: {e}")

        logger.info("Testing top events query")
        start_time = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/stats/top-events",
                    params={
                        "from_date": (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
                        "to_date": datetime.now().strftime("%Y-%m-%d"),
                        "limit": 10,
                    },
                    headers=headers,
                )

                top_events_time = time.time() - start_time

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"Top Events query completed: {top_events_time * 1000:.0f}ms "
                        f"({len(data.get('data', []))} event types returned)"
                    )
                    results["top_events_time"] = top_events_time
                else:
                    logger.error(f"Top Events query failed: {response.status_code}")

            except Exception as e:
                logger.error(f"Top Events query error: {e}")

        logger.info("Testing retention query")
        start_time = time.time()

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.get(
                    f"{self.base_url}/stats/retention",
                    params={
                        "start_date": (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d"),
                        "windows": 3,
                        "period_type": "daily",
                    },
                    headers=headers,
                )

                retention_time = time.time() - start_time

                if response.status_code == 200:
                    data = response.json()
                    logger.info(
                        f"Retention query completed: {retention_time * 1000:.0f}ms "
                        f"({len(data.get('cohorts', []))} cohorts returned)"
                    )
                    results["retention_time"] = retention_time
                else:
                    logger.error(f"Retention query failed: {response.status_code}")

            except Exception as e:
                logger.error(f"Retention query error: {e}")

        logger.info("ANALYTICS RESULTS")
        logger.info(f"DAU query: {results.get('dau_time', 0) * 1000:.0f}ms")
        logger.info(f"Top Events query: {results.get('top_events_time', 0) * 1000:.0f}ms")
        logger.info(f"Retention query: {results.get('retention_time', 0) * 1000:.0f}ms")

        return results

    async def cleanup_benchmark_data(self):
        logger.info("Triggering cleanup service")

        try:
            result = subprocess.run(
                ["docker", "exec", "-i", "events_api", "python", "/services/benchmark_cleanup_service.py"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                logger.info("Cleanup completed successfully")
                return True
            else:
                logger.error(f"Cleanup failed with exit code {result.returncode}")
                if result.stderr:
                    logger.error(result.stderr)
                return False

        except subprocess.TimeoutExpired:
            logger.error("Cleanup timed out after 30 seconds")
            return False
        except FileNotFoundError:
            logger.warning(
                "Docker command not found. Run cleanup manually: docker exec -it events_api python /services/benchmark_cleanup_service.py"
            )
            return False
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
            return False


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run event analytics benchmark")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip cleanup after benchmark (keep test data)")
    parser.add_argument("--events", type=int, default=100_000, help="Number of events to generate (default: 100,000)")
    parser.add_argument("--batch-size", type=int, default=1000, help="Batch size for event ingestion (default: 1000)")
    args = parser.parse_args()

    logger.info("EVENT ANALYTICS BENCHMARK")
    logger.info(f"Results will be saved to: {log_file}")
    logger.info(f"Configuration: {args.events:,} events, batch size {args.batch_size}")

    runner = BenchmarkRunner()

    if not await runner.setup():
        logger.error("Setup failed")
        return

    ingestion_results = await runner.benchmark_ingestion(
        total_events=args.events,
        batch_size=args.batch_size,
    )

    analytics_results = await runner.benchmark_analytics()

    logger.info("BENCHMARK SUMMARY")
    logger.info(f"Successfully tested event analytics system")
    logger.info(f"Ingested: {ingestion_results['successful']:,} events")
    logger.info(f"Throughput: {ingestion_results['throughput']:.0f} events/sec")
    logger.info(f"DAU query: {analytics_results.get('dau_time', 0) * 1000:.0f}ms")
    logger.info(f"Top Events: {analytics_results.get('top_events_time', 0) * 1000:.0f}ms")
    logger.info(f"Retention: {analytics_results.get('retention_time', 0) * 1000:.0f}ms")
    logger.info(f"Full results saved to: {log_file.absolute()}")

    if not args.no_cleanup:
        await runner.cleanup_benchmark_data()
    else:
        logger.info("")
        logger.info("Cleanup skipped (--no-cleanup flag).")


if __name__ == "__main__":
    asyncio.run(main())
