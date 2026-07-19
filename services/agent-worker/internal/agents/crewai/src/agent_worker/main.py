"""Entry point for the CrewAI agent worker."""
from __future__ import annotations

import asyncio
import logging
import sys

from agent_worker.worker import CrewAIWorker

logger = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point."""
    worker = CrewAIWorker()
    try:
        await worker.start()
    except Exception as e:
        logger.exception("CrewAI worker failed: %s", e)
        if worker.nats:
            await worker.nats.close()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
