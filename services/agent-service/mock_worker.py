"""Simple mock worker for testing ChatKit integration"""
import asyncio
import json
import logging
from internal.messaging.nats import NATSMessaging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    """Mock worker that listens for agent.start events and responds with mock progress"""
    nats = NATSMessaging(nats_url="nats://nats:4222")
    await nats.connect()
    logger.info("Mock worker connected to NATS")
    
    # Subscribe to agent.start messages
    async def handle_chat_start(msg):
        try:
            data = json.loads(msg.data.decode())
            run_id = data.get("run_id")
            logger.info(f"Received chat.start for run_id: {run_id}")
            
            # Simulate worker lifecycle
            await asyncio.sleep(1)
            
            # Publish started event
            await nats.publish_event("started", run_id, {"status": "started"})
            logger.info(f"Published started event for {run_id}")
            
            # Simulate progress
            await asyncio.sleep(1)
            await nats.publish_event("progress", run_id, {"message": "Processing request..."})
            logger.info(f"Published progress event for {run_id}")
            
            await asyncio.sleep(1)
            await nats.publish_event("progress", run_id, {"message": "Analyzing task..."})
            logger.info(f"Published progress event for {run_id}")
            
            await asyncio.sleep(1)
            
            # Publish completed event
            await nats.publish_event("completed", run_id, {
                "final_answer": f"Mock response for run {run_id}: Task completed successfully"
            })
            logger.info(f"Published completed event for {run_id}")
            
        except Exception as e:
            logger.error(f"Error handling chat.start: {e}")
    
    # Subscribe to chat.start subject
    await nats.nc.subscribe("chat.start", cb=handle_chat_start)
    logger.info("Mock worker listening for chat.start messages")
    
    # Keep running
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
