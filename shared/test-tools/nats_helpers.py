"""NATS helpers for integration testing"""
import asyncio
import json
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, AsyncGenerator
from nats.aio.client import Client as NATSClient
from contextlib import asynccontextmanager


class NATSTestClient:
    """Test wrapper for NATS client with auto-cleanup"""
    
    def __init__(self, nats_url: str = "nats://localhost:4222"):
        self.nats_url = nats_url
        self.nc: Optional[NATSClient] = None
        self.subscriptions = []
    
    async def connect(self) -> None:
        """Connect to NATS server"""
        self.nc = NATSClient()
        await self.nc.connect(self.nats_url)
    
    async def close(self) -> None:
        """Close NATS connection and cleanup subscriptions"""
        for sub in self.subscriptions:
            await sub.unsubscribe()
        self.subscriptions.clear()
        
        if self.nc:
            await self.nc.close()
    
    async def publish(self, subject: str, payload: Dict[str, Any]) -> None:
        """Publish message to NATS subject"""
        if not self.nc:
            raise RuntimeError("NATS not connected")
        
        message = {
            "message_id": str(uuid.uuid4()),
            **payload,
            "timestamp": datetime.utcnow().isoformat(),
            "schema_version": "1.0",
        }
        
        await self.nc.publish(subject, json.dumps(message).encode())
    
    async def subscribe(self, subject: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Subscribe to NATS subject and yield messages"""
        if not self.nc:
            raise RuntimeError("NATS not connected")
        
        queue = asyncio.Queue()
        
        async def message_handler(msg):
            try:
                data = json.loads(msg.data.decode())
                await queue.put(data)
            except Exception as e:
                print(f"Error processing message: {e}")
        
        try:
            sub = await self.nc.subscribe(subject, cb=message_handler)
            self.subscriptions.append(sub)
        except Exception as e:
            print(f"Error subscribing to {subject}: {e}")
            raise
        
        try:
            while True:
                yield await queue.get()
        except asyncio.CancelledError:
            if sub:
                await sub.unsubscribe()
            raise


@asynccontextmanager
async def nats_client(nats_url: str = "nats://localhost:4222"):
    """Context manager for NATS test client"""
    client = NATSTestClient(nats_url)
    try:
        await client.connect()
        yield client
    finally:
        await client.close()


def build_chat_start_message(run_id: str, repository_id: str, project_id: str, mock_mode: bool = False) -> Dict[str, Any]:
    """Build chat.start message"""
    return {
        "run_id": run_id,
        "repository_id": repository_id,
        "project_id": project_id,
        "mock_mode": mock_mode,
    }


def build_chat_close_message(run_id: str) -> Dict[str, Any]:
    """Build chat.close message"""
    return {
        "run_id": run_id,
    }


def build_run_start_message(run_id: str, user_id: str, project_id: str, repository_id: str, task: str) -> Dict[str, Any]:
    """Build run.start message"""
    return {
        "run_id": run_id,
        "user_id": user_id,
        "project_id": project_id,
        "repository_id": repository_id,
        "task": task,
    }


def build_state_event(run_id: str, event_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Build state event message"""
    return {
        "run_id": run_id,
        "event_type": event_type,
        "payload": payload,
    }


def build_worker_ready_message(run_id: str) -> Dict[str, Any]:
    """Build worker ready message"""
    return {
        "run_id": run_id,
        "status": "ready",
    }
