"""Entry point for the CrewAI expert worker."""

from __future__ import annotations

import asyncio
import logging
import sys

from crewai_expert.worker import CrewAIExpertWorker

logger = logging.getLogger(__name__)


async def main() -> None:
    worker = CrewAIExpertWorker()
    try:
        await worker.start()
    except Exception as exc:
        logger.exception("CrewAI expert worker failed: %s", exc)
        if worker.nats:
            await worker.nats.close()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
