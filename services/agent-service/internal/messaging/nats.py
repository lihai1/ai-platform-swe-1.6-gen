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
    ):
        self.nats_url = nats_url
        self.stream_name = stream_name
        self.event_stream_name = event_stream_name
        self.orchestration_stream_name = orchestration_stream_name
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
        try:
            # Command stream - covers agent.chat.{run_id}.{command} and agent.chat.user.events.{run_id}
            await self.js.add_stream(
                name=self.stream_name,
                subjects=["agent.chat.>"],
                description="Agent command stream",
                retention="limits",
                max_age=86400,  # 24 hours
                storage="file",
                republish=None,
                allow_direct=True,
            )
            logger.info(f"Created/verified stream {self.stream_name} with subjects agent.chat.>")
        except Exception as e:
            logger.warning(f"Command stream may already exist: {e}")
        
        try:
            # Event stream - also uses agent.chat.{run_id}.{event}
            # We can use the same stream for both commands and events
            # Or create separate streams with different retention policies
            await self.js.add_stream(
                name=self.event_stream_name,
                subjects=["agent.events.>"],
                description="Agent event stream",
                retention="limits",
                max_age=86400,  # 24 hours
                storage="file",
                republish=None,
                allow_direct=True,
            )
            logger.info(f"Created/verified stream {self.event_stream_name} with subjects agent.events.>")
        except Exception as e:
            logger.warning(f"Event stream may already exist: {e}")
    
    async def publish_command(
        self,
        command_type: str,
        run_id: str,
        payload: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a command to the command stream"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        message_id = message_id or str(uuid.uuid4())
        
        # Use run_id in subject for per-run routing
        subject = f"agent.chat.{run_id}.{command_type}"
        
        message = {
            "message_id": message_id,
            "command_type": command_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
        }
        
        try:
            logger.info(f"[NATS PUBLISH] Publishing command {message_id} to subject: {subject}")
            logger.info(f"[NATS PUBLISH] Command payload: {json.dumps(message, indent=2)}")
            ack = await self.js.publish(
                subject=subject,
                payload=json.dumps(message).encode(),
                headers={
                    "message_id": message_id,
                    "run_id": run_id,
                }
            )
            logger.info(f"[NATS PUBLISH] Successfully published command {message_id} to {subject}")
            return message_id
        except Exception as e:
            logger.error(f"[NATS PUBLISH] Failed to publish command to {subject}: {e}")
            raise
    
    async def publish_event(
        self,
        event_type: str,
        run_id: str,
        payload: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> str:
        """Publish an event to the event stream"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        message_id = message_id or str(uuid.uuid4())
        
        # Use agent.events.> pattern for events to avoid conflict with commands
        subject = f"agent.events.{run_id}.{event_type}"
        
        message = {
            "message_id": message_id,
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
        }
        
        try:
            logger.info(f"[NATS PUBLISH] Publishing event {message_id} to subject: {subject}")
            logger.info(f"[NATS PUBLISH] Event payload: {json.dumps(message, indent=2)}")
            ack = await self.js.publish(
                subject=subject,
                payload=json.dumps(message).encode(),
                headers={
                    "message_id": message_id,
                    "run_id": run_id,
                }
            )
            logger.info(f"[NATS PUBLISH] Successfully published event {message_id} to {subject}")
            return message_id
        except Exception as e:
            logger.error(f"[NATS PUBLISH] Failed to publish event to {subject}: {e}")
            raise
    
    async def subscribe_to_commands(
        self,
        command_handler: Callable[[Dict[str, Any]], None],
        queue_group: str = "agent-workers",
        run_id: Optional[str] = None,
    ) -> None:
        """Subscribe to command stream with durable consumer"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        consumer_name = f"{queue_group}-consumer"
        
        # Subscribe to run-specific subject if run_id provided
        if run_id:
            subject = f"agent.chat.{run_id}.>"
            consumer_name = f"{queue_group}-{run_id}-consumer"
        else:
            subject = f"agent.chat.>"
        
        try:
            # Create consumer
            await self.js.subscribe(
                subject=subject,
                cb=await self._create_command_handler(command_handler),
                manual_ack=True,
            )
            logger.info(f"Subscribed to commands on {subject}")
        except Exception as e:
            logger.error(f"Failed to subscribe to commands: {e}")
            raise
    
    async def _create_command_handler(
        self,
        handler: Callable[[Dict[str, Any]], None],
    ) -> Callable:
        """Create async handler for command messages"""
        async def command_handler_wrapper(msg):
            try:
                # Parse message
                data = json.loads(msg.data.decode())
                message_id = data.get("message_id")
                subject = msg.subject
                
                logger.info(f"[NATS RECEIVE] Received command on subject: {subject}")
                logger.info(f"[NATS RECEIVE] Command payload: {json.dumps(data, indent=2)}")
                
                # Check idempotency
                if message_id in self.processed_messages:
                    logger.debug(f"[NATS RECEIVE] Message {message_id} already processed, skipping")
                    await msg.ack()
                    return
                
                # Process message
                await handler(data)
                
                # Mark as processed
                self.processed_messages[message_id] = datetime.utcnow()
                
                # Acknowledge message
                await msg.ack()
                logger.info(f"[NATS RECEIVE] Successfully processed and acked command {message_id}")
                
            except Exception as e:
                logger.error(f"[NATS RECEIVE] Error processing command: {e}")
                # Negative acknowledge to retry
                await msg.nak()
        
        return command_handler_wrapper
    
    async def subscribe_to_events(
        self,
        event_handler: Callable[[Dict[str, Any]], None],
        run_id: Optional[str] = None,
    ) -> None:
        """Subscribe to events for a specific run or all runs"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        if run_id:
            subject = f"agent.events.{run_id}.>"
        else:
            subject = "agent.events.>"
        
        try:
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
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a chat start message to trigger container creation"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        message_id = message_id or str(uuid.uuid4())
        subject = "chat.start"
        
        message = {
            "message_id": message_id,
            "run_id": run_id,
            "repository_id": repository_id,
            "project_id": project_id,
            "mock_mode": mock_mode,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
        }
        
        try:
            logger.info(f"[NATS PUBLISH] Publishing chat start {message_id} to subject: {subject}")
            logger.info(f"[NATS PUBLISH] Chat start payload: {json.dumps(message, indent=2)}")
            # Use plain NATS for chat.start to match control plane subscription
            await self.nc.publish(
                subject=subject,
                payload=json.dumps(message).encode(),
            )
            logger.info(f"[NATS PUBLISH] Successfully published chat start {message_id} to {subject}")
            return message_id
        except Exception as e:
            logger.error(f"[NATS PUBLISH] Failed to publish chat start to {subject}: {e}")
            raise
    
    async def publish_chat_close(
        self,
        run_id: str,
        message_id: Optional[str] = None,
    ) -> str:
        """Publish a chat close message to trigger container termination"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        message_id = message_id or str(uuid.uuid4())
        subject = "chat.close"
        
        message = {
            "message_id": message_id,
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
        }
        
        try:
            logger.info(f"[NATS PUBLISH] Publishing chat close {message_id} to subject: {subject}")
            logger.info(f"[NATS PUBLISH] Chat close payload: {json.dumps(message, indent=2)}")
            # Use plain NATS for chat.close to match control plane subscription
            await self.nc.publish(
                subject=subject,
                payload=json.dumps(message).encode(),
            )
            logger.info(f"[NATS PUBLISH] Successfully published chat close {message_id} to {subject}")
            return message_id
        except Exception as e:
            logger.error(f"[NATS PUBLISH] Failed to publish chat close to {subject}: {e}")
            raise
    
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
        run_id: str,
        event_handler: Callable[[Dict[str, Any]], None],
    ) -> None:
        """Subscribe to all events for a specific run"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        subject = f"agent.chat.{run_id}.>"
        
        try:
            await self.js.subscribe(
                subject=subject,
                cb=await self._create_event_handler(event_handler),
                manual_ack=True,
            )
            logger.info(f"Subscribed to chat events for run {run_id}")
        except Exception as e:
            logger.error(f"Failed to subscribe to chat events: {e}")
            raise
    
    async def publish_orchestration_command(
        self,
        command_type: str,
        run_id: str,
        payload: Dict[str, Any],
        message_id: Optional[str] = None,
    ) -> str:
        """Publish an orchestration command to the user events stream"""
        if not self.js:
            raise RuntimeError("NATS not connected")
        
        message_id = message_id or str(uuid.uuid4())
        subject = f"agent.chat.{run_id}.user.events"
        
        message = {
            "message_id": message_id,
            "command_type": command_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
        }
        
        try:
            logger.info(f"[NATS PUBLISH] Publishing orchestration command {message_id} to subject: {subject}")
            logger.info(f"[NATS PUBLISH] Orchestration command payload: {json.dumps(message, indent=2)}")
            ack = await self.js.publish(
                subject=subject,
                payload=json.dumps(message).encode(),
                headers={
                    "message_id": message_id,
                    "run_id": run_id,
                }
            )
            logger.info(f"[NATS PUBLISH] Successfully published orchestration command {message_id} to {subject}")
            return message_id
        except Exception as e:
            logger.error(f"[NATS PUBLISH] Failed to publish orchestration command to {subject}: {e}")
            raise
    
    def cleanup_old_messages(self, max_age_hours: int = 24) -> None:
        """Clean up old processed message IDs"""
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        self.processed_messages = {
            msg_id: timestamp
            for msg_id, timestamp in self.processed_messages.items()
            if timestamp > cutoff
        }
