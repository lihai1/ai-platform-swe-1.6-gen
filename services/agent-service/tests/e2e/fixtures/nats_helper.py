"""NATS test helper for event validation in E2E tests"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any, Callable
from nats.aio.client import Client as NATSClient
from nats.errors import Error as NATSError

logger = logging.getLogger(__name__)


class NATSTestHelper:
    """Helper class for NATS operations in E2E tests"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc: Optional[NATSClient] = None
        self.js = None
        self.collected_events: Dict[str, list] = {}
        self.subscriptions = []
    
    async def connect(self) -> None:
        """Connect to NATS server and create streams if needed"""
        try:
            self.nc = NATSClient()
            await self.nc.connect(self.nats_url)
            self.js = self.nc.jetstream()
            
            # Create streams if they don't exist
            try:
                await self.js.add_stream(
                    name="AGENT_COMMANDS",
                    subjects=["agent.chat.>"],
                    description="Agent command stream",
                    retention="limits",
                    max_age=86400,
                    storage="file",
                    allow_direct=True,
                )
            except Exception as e:
                logger.warning(f"Command stream may already exist: {e}")
            
            try:
                await self.js.add_stream(
                    name="AGENT_EVENTS",
                    subjects=["agent.events.>"],
                    description="Agent event stream",
                    retention="limits",
                    max_age=86400,
                    storage="file",
                    allow_direct=True,
                )
            except Exception as e:
                logger.warning(f"Event stream may already exist: {e}")
            
            logger.info(f"Connected to NATS at {self.nats_url}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise
    
    async def subscribe_to_events(self, run_id: str) -> None:
        """Subscribe to all events for a specific run"""
        if not self.nc:
            raise RuntimeError("NATS not connected")
        
        subject = f"agent.events.{run_id}.>"
        self.collected_events[run_id] = []
        
        async def event_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                logger.info(f"[NATS TEST] Received event on {msg.subject}: {data}")
                self.collected_events[run_id].append({
                    "subject": msg.subject,
                    "data": data,
                    "timestamp": asyncio.get_event_loop().time()
                })
            except Exception as e:
                logger.error(f"[NATS TEST] Error processing event: {e}")
        
        sub = await self.nc.subscribe(subject, cb=event_handler)
        self.subscriptions.append(sub)
        logger.info(f"Subscribed to events for run {run_id}")
    
    async def subscribe_to_chat_start(self) -> None:
        """Subscribe to chat.start messages"""
        if not self.nc:
            raise RuntimeError("NATS not connected")
        
        self.collected_events["chat_start"] = []
        
        async def chat_start_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                logger.info(f"[NATS TEST] Received chat.start: {data}")
                self.collected_events["chat_start"].append({
                    "subject": msg.subject,
                    "data": data,
                    "timestamp": asyncio.get_event_loop().time()
                })
            except Exception as e:
                logger.error(f"[NATS TEST] Error processing chat.start: {e}")
        
        sub = await self.nc.subscribe("chat.start", cb=chat_start_handler)
        self.subscriptions.append(sub)
        logger.info("Subscribed to chat.start messages")
    
    async def publish_agent_started(self, run_id: str) -> str:
        """Publish agent.started event"""
        if not self.js:
            raise RuntimeError("NATS JetStream not connected")
        
        subject = f"agent.events.{run_id}.started"
        message = {
            "event_type": "started",
            "run_id": run_id,
            "timestamp": "2024-01-01T00:00:00Z",
            "schema_version": "1.0",
        }
        
        await self.js.publish(subject, json.dumps(message).encode())
        logger.info(f"Published agent.started for run {run_id}")
        return run_id
    
    async def publish_agent_completed(self, run_id: str, answer: str) -> str:
        """Publish agent.completed event"""
        if not self.js:
            raise RuntimeError("NATS JetStream not connected")
        
        subject = f"agent.events.{run_id}.completed"
        message = {
            "event_type": "completed",
            "run_id": run_id,
            "final_answer": answer,
            "timestamp": "2024-01-01T00:00:00Z",
            "schema_version": "1.0",
        }
        
        await self.js.publish(subject, json.dumps(message).encode())
        logger.info(f"Published agent.completed for run {run_id}")
        return run_id
    
    async def publish_progress(self, run_id: str, message: str) -> str:
        """Publish progress event"""
        if not self.js:
            raise RuntimeError("NATS JetStream not connected")
        
        subject = f"agent.events.{run_id}.progress"
        event_message = {
            "event_type": "progress",
            "run_id": run_id,
            "message": message,
            "timestamp": "2024-01-01T00:00:00Z",
            "schema_version": "1.0",
        }
        
        await self.js.publish(subject, json.dumps(event_message).encode())
        logger.info(f"Published progress for run {run_id}: {message}")
        return run_id
    
    async def wait_for_event(self, run_id: str, event_type: str, timeout: int = 10) -> Optional[Dict]:
        """Wait for a specific event type"""
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if run_id in self.collected_events:
                for event in self.collected_events[run_id]:
                    if event["data"].get("event_type") == event_type:
                        return event
            await asyncio.sleep(0.1)
        
        logger.warning(f"Timeout waiting for event {event_type} for run {run_id}")
        return None
    
    async def wait_for_chat_start(self, timeout: int = 10) -> Optional[Dict]:
        """Wait for chat.start message"""
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if "chat_start" in self.collected_events and self.collected_events["chat_start"]:
                return self.collected_events["chat_start"][0]
            await asyncio.sleep(0.1)
        
        logger.warning("Timeout waiting for chat.start message")
        return None
    
    def get_events(self, run_id: str) -> list:
        """Get all collected events for a run"""
        return self.collected_events.get(run_id, [])
    
    def clear_events(self, run_id: str) -> None:
        """Clear collected events for a run"""
        if run_id in self.collected_events:
            self.collected_events[run_id] = []
    
    async def cleanup(self) -> None:
        """Clean up subscriptions and connection"""
        for sub in self.subscriptions:
            try:
                await sub.unsubscribe()
            except Exception as e:
                logger.warning(f"Error unsubscribing: {e}")
        
        self.subscriptions = []
        
        if self.nc:
            try:
                await self.nc.close()
                logger.info("NATS connection closed")
            except Exception as e:
                logger.warning(f"Error closing NATS connection: {e}")
