"""Test script to simulate conversation with worker via NATS."""
import asyncio
import json
from nats.aio.client import Client as NATSClient

NATS_URL = "nats://localhost:4222"
USER_ID = "d7fb506c-109c-442a-a0d1-6e7cf1d83a89"
RUN_ID = "test-run-nats-001"  # New run ID for testing


async def test_worker_conversation():
    """Test worker conversation by sending NATS messages."""
    nc = NATSClient()
    
    try:
        # Connect to NATS
        await nc.connect(NATS_URL)
        print(f"✓ Connected to NATS at {NATS_URL}")
        
        # Subscribe to worker events
        worker_events = []
        
        async def worker_event_handler(msg):
            data = json.loads(msg.data.decode())
            worker_events.append(data)
            print(f"📥 Worker event: {msg.subject}")
            print(f"   Type: {data.get('event_type')}")
            print(f"   Payload: {json.dumps(data.get('payload'), indent=2)}")
        
        # Subscribe to chat worker events
        chat_sub = await nc.subscribe(
            f"agent.user.{USER_ID}.chat.{RUN_ID}.worker.events",
            cb=worker_event_handler
        )
        print(f"✓ Subscribed to worker events")
        
        # Subscribe to state events
        state_sub = await nc.subscribe(
            f"agent.user.{USER_ID}.events.{RUN_ID}.state.>",
            cb=worker_event_handler
        )
        print(f"✓ Subscribed to state events")
        
        # Publish control start message to trigger worker creation
        control_start = {
            "message_id": "test-control-001",
            "timestamp": "2026-07-16T00:00:00.000000",
            "schema_version": "1.0",
            "run_id": RUN_ID,
            "repository_id": None,
            "project_id": "e644b2b1-6e9d-477b-a9df-e2a3283ac556",
            "user_id": USER_ID,
            "task": "Hello, can you help me?",
            "mock_mode": False,
            "agent_type": "single-agent",
            "llm_provider": "ollama",
            "model_name": "qwen3.5:9b",
            "api_key": "",
            "max_tokens": 0,
            "max_cost": 0.0,
            "max_repair_count": 2
        }
        
        await nc.publish(
            f"agent.control.{RUN_ID}.start",
            json.dumps(control_start).encode()
        )
        print(f"✓ Sent control start message to create worker")
        
        # Wait for worker to start
        print("⏳ Waiting 10 seconds for worker to start...")
        await asyncio.sleep(10)
        
        # Send user input message
        user_input = {
            "message_id": "test-msg-001",
            "timestamp": "2026-07-16T00:00:00.000000",
            "schema_version": "1.0",
            "run_id": RUN_ID,
            "event_type": "user_input",
            "payload": {
                "type": "user_input",
                "input": "Hello, can you help me?"
            }
        }
        
        await nc.publish(
            f"agent.user.{USER_ID}.chat.{RUN_ID}.user.events",
            json.dumps(user_input).encode()
        )
        print(f"✓ Sent user input: 'Hello, can you help me?'")
        
        # Wait a bit for worker to start processing, then send second message
        print("\n⏳ Waiting 5 seconds for worker to start processing...")
        await asyncio.sleep(5)
        
        # Send another user input message while worker is still active
        print("\n🔄 Sending second user input (while worker is active)...")
        user_input_2 = {
            "message_id": "test-msg-002",
            "timestamp": "2026-07-16T00:00:00.000000",
            "schema_version": "1.0",
            "run_id": RUN_ID,
            "event_type": "user_input",
            "payload": {
                "type": "user_input",
                "input": "What files are in the current directory?"
            }
        }
        
        await nc.publish(
            f"agent.user.{USER_ID}.chat.{RUN_ID}.user.events",
            json.dumps(user_input_2).encode()
        )
        print(f"✓ Sent second user input: 'What files are in the current directory?'")
        
        # Wait for responses
        print("\n⏳ Waiting for worker responses (40 seconds)...")
        await asyncio.sleep(40)
        
        # Summary
        print(f"\n📊 Received {len(worker_events)} events from worker")
        
        # Cleanup
        await chat_sub.unsubscribe()
        await state_sub.unsubscribe()
        
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        await nc.close()
        print("✓ Disconnected from NATS")


if __name__ == "__main__":
    asyncio.run(test_worker_conversation())
