from collections.abc import AsyncIterator
from typing import Any
from internal.messaging.nats import NATSMessaging
import asyncio
import logging

logger = logging.getLogger(__name__)


class NatsBridge:
    def __init__(self, nats_client: NATSMessaging):
        self.nats = nats_client
        self._event_queue: asyncio.Queue = None

    async def publish_agent_start(
        self,
        *,
        run_id: str,
        conversation_id: str,
        user_subject: str,
        prompt: str,
        metadata: dict,
    ) -> None:
        # Publish to chat.start for container creation
        await self.nats.publish_chat_start(
            run_id=run_id,
            repository_id=metadata.get("repository_id", ""),
            project_id=metadata.get("project_id", ""),
            mock_mode=metadata.get("mock_mode", False),
        )

        # Publish to agent.chat.{run_id}.user.events for run request
        await self.nats.publish_orchestration_command(
            command_type="run.start",
            run_id=run_id,
            payload={
                "user_id": user_subject,
                "project_id": metadata.get("project_id", ""),
                "repository_id": metadata.get("repository_id", ""),
                "task": prompt,
                "run_id": run_id,
            },
        )

    async def subscribe_run_events(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        self._event_queue = asyncio.Queue()

        logger.info("NATS bridge: setting up subscriptions for run_id=%s", run_id)

        def enqueue(event: dict[str, Any]) -> None:
            logger.debug("NATS bridge: received event for run_id=%s: %s", run_id, event)
            self._event_queue.put_nowait(event)

        # Events published by the worker to agent.events.{run_id}.>
        await self.nats.subscribe_to_events(event_handler=enqueue, run_id=run_id)

        # Events published to agent.chat.{run_id}.>
        await self.nats.subscribe_to_chat_events(run_id=run_id, event_handler=enqueue)

        logger.info("NATS bridge: subscriptions ready for run_id=%s", run_id)

        while True:
            event = await self._event_queue.get()
            logger.debug("NATS bridge: yielding event for run_id=%s", run_id)
            yield event
