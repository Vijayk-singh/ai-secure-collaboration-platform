import asyncio
import logging
import signal
import sys
import os

# Ensure project root directory is inside Python search paths
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.logging import setup_logging
from app.core.redis import redis_service
from app.workers.worker import AsyncWorker
from app.workers.scheduler import TaskScheduler

logger = logging.getLogger(__name__)

async def main() -> None:
    """
    Main runner booting the concurrent Worker and Scheduler processes.
    Handles SIGINT / SIGTERM signals for clean distributed shutdowns.
    """
    setup_logging()
    logger.info("Booting async worker process daemon...")

    # Connect to Redis
    redis_service.init_redis()
    redis_healthy = await redis_service.ping()
    if not redis_healthy:
        logger.error("Redis server is not reachable. Exiting worker process.")
        sys.exit(1)

    cache = redis_service.client
    assert cache is not None

    # Instantiate services
    worker = AsyncWorker(cache)
    scheduler = TaskScheduler(cache)

    # Start concurrent loops
    worker.start()
    scheduler.start()

    logger.info("Worker and Scheduler daemons successfully initialized.")

    # Graceful shutdown event loop register
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def handle_shutdown() -> None:
        logger.info("Termination signal received. Coordinating graceful shutdown...")
        stop_event.set()

    # Register OS signal traps
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, handle_shutdown)
        except NotImplementedError:
            # Handles platforms where signal handlers are restricted
            pass

    # Block thread until signal fires
    await stop_event.wait()

    # Coordinate shutdown sequence
    logger.info("De-registering Scheduler polling...")
    await scheduler.stop()

    logger.info("De-registering Worker loops...")
    await worker.stop()

    logger.info("Releasing Redis pool resources...")
    await redis_service.close()

    logger.info("Worker process terminated gracefully. Exit.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Worker process aborted.")
