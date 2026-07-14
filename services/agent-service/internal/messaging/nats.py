"""NATS JetStream messaging for worker separation"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable
from nats.aio.client import Client as NATSClient
from nats.errors import Error as NATSError
from datetime import datetime, timedelta
import uuid

logger = logging.getLogger(__name__)


class NATSMessaging:
    """NATS JetStream messaging for agent command and event streaming"""
    
    def __init__(
        self,
        nats_url: str = "nats://localhost:4222",
        stream_name: str = "AGENT_COMMANDS",
        event_stream_name: str = "AGENT_EVENTS",
        orchestration_stream_name: str = "AGENT_ORCHESTRATION",
        service_id: str = "agent-service",
    ):
        self.nats_url = nats_url
        self.stream_name = stream_name
        self.event_stream_name = event_stream_name
        self.orchestration_stream_name = orchestration_stream_name
        self.service_id = service_id
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
        stream_configs = [
            {
                "name": "AGENT_CHAT",
                "subjects": ["agent.user.*.chat.>"],
                "description": "Agent chat stream for user events",
                "label": "Chat",
            },
            {
                "name": "AGENT_CONTROL",
                "subjects": ["agent.control.>"],
                "description": "Agent control stream",
                "label": "Command",
            },
            {
                "name": self.event_stream_name,
                "subjects": ["agent.user.*.events.>"],
                "description": "Agent event stream",
                "label": "Event",
            },
            {
                "name": "AGENT_ERRORS",
                "subjects": ["agent.user.*.chat.errors"],
                "description": "Agent error stream",
                "label": "Error",
            },
        ]

        for config in stream_configs:
            try:
                await self.js.add_stream(
                    name=config["name"],
                    subjects=config["subjects"],
                    description=config["description"],
                    retention="limits",
                    max_age=86400,  # 24 hours
                    storage="file",
                    republish=None,
                    allow_direct=True,
                )
                logger.info("Created/verified stream %s with subjects %s", config["name"], config["subjects"][0])
            except Exception as e:
                logger.warning("%s stream may already exist: %s", config["label"], e)
    
    async def _publish_message(
        self,
        subject: str,
        label: str,
        message_id: Optional[str] = None,
        *,
        use_jetstream: bool = True,
        include_headers: bool = True,
        **message_fields: Any,
    ) -> str:
        """Build and publish a JSON message to a NATS subject."""
        if use_jetstream and not self.js:
            raise RuntimeError("NATS not connected")
        if not use_jetstream and not self.nc:
            raise RuntimeError("NATS not connected")

        message_id = message_id or str(uuid.uuid4())
        message = {
            "message_id": message_id,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
            **message_fields,
        }
        data = json.dumps(message).encode()

        try:
            logger.info(f"[NATS PUBLISH] Publishing {label} {message_id} to subject: {subject}")
            logger.info(f"[NATS PUBLISH] {label.capitalize()} payload: {json.dumps(message, indent=2)}")
            if use_jetstream:
                if include_headers:
                    await self.js.publish(
                        subject,
                        data,
                        headers={
                            "message_id": message_id,
                            "run_id": message.get("run_id", ""),
                        },
                    )
                else:
                    await self.js.publish(subject, data)
            else:
                await self.nc.publish(subject, data)
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
            label="event",
            message_id=message_id,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
        )
    
    async def subscribe_to_events(
        self,
        event_handler: Callable[[Dict[str, Any]], None],
        user_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """Subscribe to events for a specific user/run or all users/runs"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        # Create unique durable consumer name with service_id, user_id and run_id
        if user_id and run_id:
            subject = f"agent.user.{user_id}.events.{run_id}.state.>"
            consumer_name = f"{self.service_id}-events-{user_id}-{run_id}-consumer"
        elif user_id:
            subject = f"agent.user.{user_id}.events.>"
            consumer_name = f"{self.service_id}-events-{user_id}-consumer"
        elif run_id:
            subject = f"agent.user.*.events.{run_id}.state.>"
            consumer_name = f"{self.service_id}-events-{run_id}-consumer"
        else:
            subject = "agent.user.*.events.>"
            consumer_name = f"{self.service_id}-events-consumer"
        
        try:
            # Create subscription with JetStream
            await self.js.subscribe(
                subject=subject,
                cb=await self._create_event_handler(event_handler),
                manual_ack=True,
            )
            logger.info(f"Subscribed to events on subject: {subject}")
        except Exception as e:
            logger.error(f"Failed to subscribe to events: {e}")
            raise
    
    async def _create_event_handler(
        self,
        handler: Callable[[Dict[str, Any]], None],
    ) -> Callable:
        """Create async handler for event messages"""
        async def event_handler_wrapper(msg):
            try:
                data = json.loads(msg.data.decode())
                subject = msg.subject
                
                logger.info(f"[NATS RECEIVE] Received event on subject: {subject}")
                logger.info(f"[NATS RECEIVE] Event payload: {json.dumps(data, indent=2)}")
                
                # Support both sync and async handlers
                result = handler(data)
                if asyncio.iscoroutine(result):
                    await result
                
                await msg.ack()
                logger.info(f"[NATS RECEIVE] Successfully processed and acked event")
            except Exception as e:
                logger.error(f"[NATS RECEIVE] Error processing event: {e}")
                await msg.nak()
        
        return event_handler_wrapper
    
    async def close(self) -> None:
        """Close NATS connection"""
        if self.nc:
            await self.nc.close()
            logger.info("NATS connection closed")
    
    async def publish_chat_start(
        self,
        run_id: str,
        repository_id: str,
        project_id: str,
        mock_mode: bool = False,
        agent_type: str = "specialist",
        llm_provider: str = "ollama",
        model_name: str = "qwen3.5:9b",
        api_key: str = "",
        user_id: str = "",
        task: str = "",
        max_tokens: int = 0,
        max_cost: float = 0.0,
        max_repair_count: int = 2,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a chat start message to trigger container creation"""
        # Use plain NATS for agent.control.{run_id}.start to match control plane subscription
        subject = f"agent.control.{run_id}.start"
        return await self._publish_message(
            subject=subject,
            label="chat start",
            message_id=message_id,
            use_jetstream=False,
            include_headers=False,
            run_id=run_id,
            repository_id=repository_id,
            project_id=project_id,
            user_id=user_id,
            task=task,
            mock_mode=mock_mode,
            agent_type=agent_type,
            llm_provider=llm_provider,
            model_name=model_name,
            api_key=api_key,
            max_tokens=max_tokens,
            max_cost=max_cost,
            max_repair_count=max_repair_count,
        )
    
    
    async def subscribe_plain(
        self,
        subject: str,
        handler: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to a subject using plain NATS (not JetStream)"""
        if not self.nc:
            raise RuntimeError("NATS not connected")
        
        try:
            async def plain_handler(msg):
                try:
                    data = json.loads(msg.data.decode())
                    logger.info(f"[NATS PLAIN] Received message on subject: {subject}")
                    logger.info(f"[NATS PLAIN] Message payload: {json.dumps(data, indent=2)}")
                    await handler(data)
                except Exception as e:
                    logger.error(f"[NATS PLAIN] Error processing message: {e}")
            
            await self.nc.subscribe(subject, cb=plain_handler)
            logger.info(f"Subscribed to plain NATS subject: {subject}")
        except Exception as e:
            logger.error(f"Failed to subscribe to plain NATS subject: {e}")
            raise

    async def subscribe_to_chat_events(
        self,
        event_handler: Callable[[Dict[str, Any]], None],
        user_id: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """Subscribe to worker output events for a specific user/run or all users/runs"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        # Create unique durable consumer name with service_id, user_id and run_id
        if user_id and run_id:
            subject = f"agent.user.{user_id}.chat.{run_id}.worker.events"
            consumer_name = f"{self.service_id}-chat-{user_id}-{run_id}-consumer"
        elif user_id:
            subject = f"agent.user.{user_id}.chat.*.worker.events"
            consumer_name = f"{self.service_id}-chat-{user_id}-consumer"
        elif run_id:
            subject = f"agent.user.*.chat.{run_id}.worker.events"
            consumer_name = f"{self.service_id}-chat-{run_id}-consumer"
        else:
            subject = "agent.user.*.chat.*.worker.events"
            consumer_name = f"{self.service_id}-chat-consumer"
        
        try:
            # Create subscription with JetStream, explicitly specifying the stream
            await self.js.subscribe(
                subject=subject,
                stream="AGENT_CHAT",
                cb=await self._create_event_handler(event_handler),
                manual_ack=True,
            )
            logger.info(f"Subscribed to chat events for run {run_id} on {subject} with stream AGENT_CHAT")
        except Exception as e:
            logger.error(f"Failed to subscribe to chat events: {e}")
            raise
    
    async def publish_chat_event(
        self,
        event_type: str,
        run_id: str,
        payload: Dict[str, Any],
        user_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a chat event to the chat stream (user events like tool approvals)"""
        subject = f"agent.user.{user_id}.chat.{run_id}.user.events"
        return await self._publish_message(
            subject=subject,
            label="chat event",
            message_id=message_id,
            include_headers=False,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
        )
    
    async def publish_chat_close(
        self,
        run_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a chat close command to the control stream"""
        subject = f"agent.control.{run_id}.close"
        return await self._publish_message(
            subject=subject,
            label="chat close",
            message_id=message_id,
            include_headers=False,
            run_id=run_id,
        )
    
    async def publish_chat_resume(
        self,
        run_id: str,
        repository_id: str,
        project_id: str,
        mock_mode: bool,
        agent_type: str,
        llm_provider: str,
        api_key: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a chat resume command to the control stream"""
        subject = f"agent.control.{run_id}.resume"
        return await self._publish_message(
            subject=subject,
            label="chat resume",
            message_id=message_id,
            include_headers=False,
            run_id=run_id,
            repository_id=repository_id,
            project_id=project_id,
            mock_mode=mock_mode,
            agent_type=agent_type,
            llm_provider=llm_provider,
            api_key=api_key,
        )
    
    async def subscribe_to_errors(
        self,
        event_handler: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to error messages from agent-worker"""
        if not self.js:
            raise RuntimeError("NATS not connected")

        subject = "agent.user.*.chat.errors"
        consumer_name = f"{self.service_id}-errors-consumer"

        try:
            # Reuse existing event handler pattern
            await self.js.subscribe(
                subject=subject,
                cb=await self._create_event_handler(event_handler),
                manual_ack=True,
            )
            logger.info(f"Subscribed to errors on subject: {subject}")
        except Exception as e:
            logger.error(f"Failed to subscribe to errors: {e}")
            raise

    async def subscribe_to_worker_ready(
        self,
        event_handler: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to worker ready signals from agent workers"""
        if not self.nc:
            raise RuntimeError("NATS not connected")

        subject = "agent.control.worker.*.ready"

        try:
            # Use plain NATS subscription since worker publishes to plain NATS
            async def wrapped(msg):
                try:
                    data = json.loads(msg.data.decode())
                    await event_handler(data)
                except Exception as e:
                    logger.error(f"Error handling worker ready event: {e}")

            sub = await self.nc.subscribe(subject, cb=wrapped)
            logger.info(f"Subscribed to worker ready signals on subject: {subject}")
        except Exception as e:
            logger.error(f"Failed to subscribe to worker ready signals: {e}")
            raise
    
    def cleanup_old_messages(self, max_age_hours: int = 24) -> None:
        """Clean up old processed message IDs"""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        self.processed_messages = {
            msg_id: timestamp
            for msg_id, timestamp in self.processed_messages.items()
            if timestamp > cutoff
        }
