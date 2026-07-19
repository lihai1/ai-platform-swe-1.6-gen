"""Async NATS client for the CrewAI worker."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any, Callable, Optional

from nats.aio.client import Client as NATSClient
from nats.aio.subscription import Subscription

from agent_worker.events import base_event
from agent_worker.subjects import Subjects, SubjectTemplates
from agentic_shared import get_crewai_stream_configs
from agentic_shared.nats_subjects import (
    format_control_worker_ready,
    STREAM_AGENT_CHAT,
)

logger = logging.getLogger(__name__)


class CrewAINatsClient:
    """NATS client tailored for the CrewAI worker."""

    def __init__(self, nats_url: str, uid: str, run_id: str, session_id: str = ""):
        self.nats_url = nats_url
        self.uid = uid
        self.run_id = run_id
        self.session_id = session_id
        self._nc: Optional[NATSClient] = None
        self._js = None
        self._subscriptions: list[Subscription] = []
        self._subjects = Subjects.from_templates(
            SubjectTemplates.from_env(), uid=uid, run_id=run_id
        )

    @property
    def subjects(self) -> Subjects:
        return self._subjects

    async def connect(self) -> None:
        """Connect to NATS and create streams if needed."""
        self._nc = NATSClient()
        await self._nc.connect(self.nats_url)
        self._js = self._nc.jetstream()
        logger.info("Connected to NATS at %s", self.nats_url)
        await self._ensure_streams()

    async def _ensure_streams(self) -> None:
        """Create streams if they do not exist."""
        stream_configs = get_crewai_stream_configs()
        for config in stream_configs:
            try:
                await self._js.add_stream(**config)
                logger.info("Created stream %s", config["name"])
            except Exception as e:
                logger.debug("Stream %s may already exist: %s", config["name"], e)

    async def close(self) -> None:
        """Unsubscribe and close the NATS connection."""
        for sub in self._subscriptions:
            try:
                await sub.unsubscribe()
            except Exception as e:
                logger.warning("Failed to unsubscribe: %s", e)
        if self._nc:
            await self._nc.close()
            self._nc = None

    async def publish_state(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish a state event to NATS."""
        subject = self._subjects.state(event_type)
        message = base_event(
            event_type=event_type,
            run_id=self.run_id,
            payload=payload,
            user_id=self.uid,
            session_id=self.session_id,
        )
        await self._publish(subject, message)

    async def publish_chat(self, event_type: str, payload: dict[str, Any]) -> None:
        """Publish a chat event to NATS."""
        subject = self._subjects.chat_events
        message = base_event(
            event_type=event_type,
            run_id=self.run_id,
            payload=payload,
            user_id=self.uid,
            session_id=self.session_id,
        )
        await self._publish(subject, message)

    async def publish_control_ready(self) -> None:
        """Publish worker ready signal to NATS."""
        subject = format_control_worker_ready(self.run_id)
        message = base_event(
            event_type="worker_ready",
            run_id=self.run_id,
            payload={"status": "ready"},
            user_id=self.uid,
            session_id=self.session_id,
        )
        await self._publish(subject, message)

    async def _publish(self, subject: str, message: dict[str, Any]) -> None:
        """Publish a JSON message to a JetStream subject."""
        if not self._js:
            raise RuntimeError("NATS not connected")
        data = json.dumps(message).encode()
        headers = {"message_id": message["message_id"], "run_id": self.run_id}
        try:
            await self._js.publish(subject, data, headers=headers)
            logger.info("Published %s to %s", message["event_type"], subject)
        except Exception as e:
            logger.error("Failed to publish to %s: %s", subject, e)
            raise

    async def subscribe_user_events(
        self, handler: Callable[[dict[str, Any]], None]
    ) -> None:
        """Subscribe to user events for this run."""
        subject = self._subjects.user_events

        async def wrapped(msg):
            try:
                data = json.loads(msg.data.decode())
                logger.info("Received user event on %s: %s", subject, data)
                await handler(data)
                await msg.ack()
            except Exception as e:
                logger.error("Error handling user event: %s", e)
                await msg.nak()

        sub = await self._js.subscribe(subject, cb=wrapped, stream=STREAM_AGENT_CHAT)
        self._subscriptions.append(sub)
        logger.info("Subscribed to user events on %s", subject)

    async def subscribe_control_close(
        self, handler: Callable[[], None]
    ) -> None:
        """Subscribe to control close for this run."""
        # Use plain NATS for control close to avoid stream consumer setup
        if not self._nc:
            raise RuntimeError("NATS not connected")

        async def wrapped(msg):
            try:
                logger.info("Received control close on %s", msg.subject)
                await handler()
            except Exception as e:
                logger.error("Error handling control close: %s", e)

        sub = await self._nc.subscribe(self._subjects.control_close, cb=wrapped)
        self._subscriptions.append(sub)
        logger.info("Subscribed to control close on %s", self._subjects.control_close)

    async def flush(self) -> None:
        """Flush pending NATS messages."""
        if self._nc:
            await self._nc.flush()
