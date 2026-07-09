"""Mock agent worker for simulating worker lifecycle in E2E tests"""
import asyncio
import json
import logging
from typing import Optional, List
from .nats_helper import NATSTestHelper

logger = logging.getLogger(__name__)


class MockAgentRunner:
    """Mock agent worker that simulates worker lifecycle events"""
    
    def __init__(self, nats_helper: NATSTestHelper):
        self.nats_helper = nats_helper
        self.run_id: Optional[str] = None
        self.prompt: Optional[str] = None
    
    async def simulate_worker_lifecycle(
        self,
        run_id: str,
        prompt: str,
        progress_steps: Optional[List[str]] = None,
        final_answer: str = "Task completed successfully"
    ) -> None:
        """Simulate complete worker lifecycle from start to completion"""
        self.run_id = run_id
        self.prompt = prompt
        
        if progress_steps is None:
            progress_steps = [
                "Analyzing request...",
                "Cloning repository...",
                "Executing workflow...",
                "Generating response..."
            ]
        
        # Simulate worker startup delay
        await asyncio.sleep(0.5)
        
        # Publish started event
        await self.publish_started()
        
        # Publish progress events
        for step in progress_steps:
            await asyncio.sleep(0.3)
            await self.publish_progress(step)
        
        # Simulate processing time
        await asyncio.sleep(0.5)
        
        # Publish completed event
        await self.publish_completed(final_answer)
        
        logger.info(f"Mock worker lifecycle completed for run {run_id}")
    
    async def publish_started(self) -> None:
        """Publish agent.started event"""
        if not self.run_id:
            raise RuntimeError("run_id not set")
        
        await self.nats_helper.publish_agent_started(self.run_id)
        logger.info(f"Mock worker published started for run {self.run_id}")
    
    async def publish_progress(self, message: str) -> None:
        """Publish progress event"""
        if not self.run_id:
            raise RuntimeError("run_id not set")
        
        await self.nats_helper.publish_progress(self.run_id, message)
        logger.info(f"Mock worker published progress for run {self.run_id}: {message}")
    
    async def publish_completed(self, answer: str) -> None:
        """Publish agent.completed event"""
        if not self.run_id:
            raise RuntimeError("run_id not set")
        
        await self.nats_helper.publish_agent_completed(self.run_id, answer)
        logger.info(f"Mock worker published completed for run {self.run_id}")
    
    async def simulate_failure(self, error_message: str = "Worker failed") -> None:
        """Simulate worker failure"""
        if not self.run_id:
            raise RuntimeError("run_id not set")
        
        await self.publish_started()
        await asyncio.sleep(0.3)
        
        # Publish failed event
        if self.nats_helper.js:
            subject = f"agent.events.{self.run_id}.failed"
            message = {
                "event_type": "failed",
                "run_id": self.run_id,
                "message": error_message,
                "timestamp": "2024-01-01T00:00:00Z",
                "schema_version": "1.0",
            }
            await self.nats_helper.js.publish(subject, json.dumps(message).encode())
            logger.info(f"Mock worker published failed for run {self.run_id}")
    
    async def simulate_cancellation(self) -> None:
        """Simulate worker cancellation"""
        if not self.run_id:
            raise RuntimeError("run_id not set")
        
        await self.publish_started()
        await asyncio.sleep(0.3)
        
        # Publish cancelled event
        if self.nats_helper.js:
            subject = f"agent.events.{self.run_id}.cancelled"
            message = {
                "event_type": "cancelled",
                "run_id": self.run_id,
                "timestamp": "2024-01-01T00:00:00Z",
                "schema_version": "1.0",
            }
            await self.nats_helper.js.publish(subject, json.dumps(message).encode())
            logger.info(f"Mock worker published cancelled for run {self.run_id}")
