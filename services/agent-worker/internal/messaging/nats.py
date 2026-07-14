"""NATS JetStream messaging for worker separation"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional, Dict, Any, Callable
from nats.aio.client import Client as NATSClient
from nats.errors import Error as NATSError
from datetime import datetime, timedelta
import uuid
from internal.messaging.nats_streams import get_default_stream_configs

logger = logging.getLogger(__name__)

# Module-level NATS client singleton for event publishing
_nats_client: Optional[NATSMessaging] = None

def get_nats_client() -> NATSMessaging:
    """Get or create the global NATS client singleton"""
    global _nats_client
    if _nats_client is None:
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        service_id = os.getenv("SERVICE_ID", "agent-worker")
        worker_id = os.getenv("WORKER_ID", str(uuid.uuid4()))
        _nats_client = NATSMessaging(nats_url=nats_url, service_id=service_id, worker_id=worker_id)
    return _nats_client

def set_nats_client(client: NATSMessaging) -> None:
    """Set the global NATS client singleton (for testing or manual setup)"""
    global _nats_client
    _nats_client = client


class NATSMessaging:
    """NATS JetStream messaging for agent command and event streaming"""
    
    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        stream_name: str = "AGENT_COMMANDS",
        event_stream_name: str = "AGENT_EVENTS",
        orchestration_stream_name: str = "AGENT_ORCHESTRATION",
        service_id: str = "agent-worker",
        worker_id: str = "default-worker",
    ):
        self.nats_url = nats_url
        self.stream_name = stream_name
        self.event_stream_name = event_stream_name
        self.orchestration_stream_name = orchestration_stream_name
        self.service_id = service_id
        self.worker_id = worker_id
        self.nc: Optional[NATSClient] = None
        self.js = None
        
        # Track processed message IDs for idempotency
        self.processed_messages: Dict[str, datetime] = {}
    
    async def connect(self) -> None:
        """Connect to NATS server"""
        try:
            nc = NATSClient()
            await nc.connect(self.nats_url)
            self.nc = nc
            self.js = self.nc.jetstream()
            
            if self.js is None:
                raise RuntimeError("Failed to initialize JetStream")
            
            # Create streams
            await self._create_streams()
            
            logger.info(f"Connected to NATS at {self.nats_url} with JetStream enabled")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
    
    async def _create_streams(self) -> None:
        """Create JetStream streams if they don't exist"""
        stream_configs = get_default_stream_configs()

        for config in stream_configs:
            try:
                await self.js.add_stream(
                    name=config["name"],
                    subjects=config["subjects"],
                    description=config["description"],
                    retention=config["retention"],
                    max_age=config["max_age"],
                    storage=config["storage"],
                    republish=None,
                    allow_direct=True,
                )
                logger.info("Created/verified stream %s with subjects %s", config["name"], config["subjects"][0])
            except Exception as e:
                logger.warning("%s stream may already exist: %s", config["name"], e)
    
    async def _publish_message(
        self,
        subject: str,
        event_type: str,
        run_id: str,
        payload: Dict[str, Any],
        message_id: Optional[str] = None,
        label: str = "event",
    ) -> str:
        """Publish a JSON message to a JetStream subject."""
        if not self.js:
            raise RuntimeError("NATS not connected")

        message_id = message_id or str(uuid.uuid4())
        message = {
            "message_id": message_id,
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
        }

        try:
            logger.info(f"[NATS PUBLISH] Publishing {label} {message_id} to subject: {subject}")
            logger.info(f"[NATS PUBLISH] {label.capitalize()} payload: {json.dumps(message, indent=2)}")
            ack = await self.js.publish(
                subject=subject,
                payload=json.dumps(message).encode(),
                headers={
                    "message_id": message_id,
                    "run_id": run_id,
                }
            )
            logger.info(f"[NATS PUBLISH] Successfully published {label} {message_id} to {subject}")
            return message_id
        except Exception as e:
            logger.error(f"[NATS PUBLISH] Failed to publish {label} to {subject}: {e}")
            raise

    async def publish_event(
        self,
        event_type: str,
        run_id: str,
        payload: Dict[str, Any],
        user_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish an event to the event stream"""
        subject = f"agent.user.{user_id}.events.{run_id}.state.{event_type}"
        return await self._publish_message(
            subject=subject,
            event_type=event_type,
            run_id=run_id,
            payload=payload,
            message_id=message_id,
            label="event",
        )
    
    async def close(self) -> None:
        """Close NATS connection"""
        if self.nc:
            await self.nc.close()
            logger.info("NATS connection closed")

    async def subscribe_to_user_events(
        self,
        run_id: str,
        user_id: str,
        user_event_handler: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to user events (tool approvals, etc.) for a specific run"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        subject = f"agent.user.{user_id}.chat.{run_id}.user.events"
        consumer_name = f"{self.service_id}-{self.worker_id}-user-{user_id}-{run_id}-consumer"
        
        try:
            # Create subscription with JetStream
            await self.js.subscribe(
                subject=subject,
                cb=await self._create_user_event_handler(user_event_handler),
                manual_ack=True,
            )
            logger.info(f"Subscribed to user events for run {run_id}")
        except Exception as e:
            logger.error(f"Failed to subscribe to user events: {e}")
            raise

    async def _create_user_event_handler(
        self,
        handler: Callable[[Dict[str, Any]], None],
    ) -> Callable:
        """Create async handler for user event messages"""
        async def user_event_handler_wrapper(msg):
            try:
                data = json.loads(msg.data.decode())
                subject = msg.subject
                
                logger.info(f"[NATS RECEIVE] Received user event on subject: {subject}")
                logger.info(f"[NATS RECEIVE] User event payload: {json.dumps(data, indent=2)}")
                
                # Extract user_id from subject: agent.user.{user_id}.chat.{run_id}.user.events
                subject_parts = subject.split(".")
                if len(subject_parts) >= 3:
                    data["user_id"] = subject_parts[2]
                
                await handler(data)
                await msg.ack()
                logger.info(f"[NATS RECEIVE] Successfully processed and acked user event on subject: {subject}")
            except Exception as e:
                logger.error(f"[NATS RECEIVE] Error processing user event: {e}")
                await msg.nak()
        
        return user_event_handler_wrapper
    async def publish_chat_event(
        self,
        event_type: str,
        run_id: str,
        payload: Dict[str, Any],
        user_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a chat event to the chat stream for UI updates"""
        subject = f"agent.user.{user_id}.chat.{run_id}.worker.events"
        return await self._publish_message(
            subject=subject,
            event_type=event_type,
            run_id=run_id,
            payload=payload,
            message_id=message_id,
            label="chat event",
        )

    async def publish_control_ready(
        self,
        run_id: str,
        user_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish worker ready signal to the control stream"""
        subject = f"agent.control.worker.{run_id}.ready"
        return await self._publish_message(
            subject=subject,
            event_type="worker_ready",
            run_id=run_id,
            payload={"status": "ready"},
            message_id=message_id,
            label="ready signal",
        )
    
    def cleanup_old_messages(self, max_age_hours: int = 24) -> None:
        """Clean up old processed message IDs"""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        self.processed_messages = {
            msg_id: timestamp
            for msg_id, timestamp in self.processed_messages.items()
            if timestamp > cutoff
        }
