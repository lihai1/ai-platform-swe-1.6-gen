"""End-to-end tests for ChatKit server integration"""
import pytest
import asyncio
import json
from httpx import AsyncClient


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chatkit_basic_flow(test_client, nats_helper, mock_worker):
    """Test basic ChatKit flow: HTTP → NATS → events without control plane"""
    # Subscribe to events for the run that will be created
    await nats_helper.subscribe_to_chat_start()
    
    # Give subscription time to activate
    await asyncio.sleep(0.5)
    
    # Send ChatKit request
    response = await test_client.post(
        "/chatkit",
        json={"message": "test message"},
        headers={
            "X-User-Subject": "user:test",
            "X-Org-Id": "org:test"
        }
    )
    
    # Verify response is streaming
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    
    # Wait for chat.start message
    chat_start = await nats_helper.wait_for_chat_start(timeout=10)
    assert chat_start is not None, "chat.start message not received"
    
    # Extract run_id from chat.start
    run_id = chat_start["data"].get("run_id")
    assert run_id is not None, "run_id not found in chat.start"
    
    # Subscribe to events for this run
    await nats_helper.subscribe_to_events(run_id)
    
    # Simulate worker lifecycle
    await mock_worker.simulate_worker_lifecycle(
        run_id=run_id,
        prompt="test message",
        progress_steps=["Processing request...", "Generating response..."],
        final_answer="Test completed successfully"
    )
    
    # Verify events were received
    events = nats_helper.get_events(run_id)
    assert len(events) >= 2, f"Expected at least 2 events, got {len(events)}"
    
    # Verify started event
    started_event = next((e for e in events if e["data"].get("event_type") == "started"), None)
    assert started_event is not None, "started event not received"
    
    # Verify completed event
    completed_event = next((e for e in events if e["data"].get("event_type") == "completed"), None)
    assert completed_event is not None, "completed event not received"
    assert completed_event["data"].get("final_answer") == "Test completed successfully"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chatkit_with_thread_id(test_client, nats_helper, mock_worker):
    """Test ChatKit flow with explicit thread_id"""
    await nats_helper.subscribe_to_chat_start()
    
    thread_id = "test-thread-123"
    
    response = await test_client.post(
        "/chatkit",
        json={
            "message": "test message with thread",
            "thread_id": thread_id
        },
        headers={
            "X-User-Subject": "user:test",
            "X-Org-Id": "org:test"
        }
    )
    
    assert response.status_code == 200
    
    chat_start = await nats_helper.wait_for_chat_start(timeout=10)
    assert chat_start is not None
    
    run_id = chat_start["data"].get("run_id")
    assert run_id is not None
    
    await nats_helper.subscribe_to_events(run_id)
    
    await mock_worker.simulate_worker_lifecycle(
        run_id=run_id,
        prompt="test message with thread",
        final_answer="Thread test completed"
    )
    
    events = nats_helper.get_events(run_id)
    assert len(events) >= 2


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chatkit_empty_message(test_client, nats_helper):
    """Test ChatKit with empty message"""
    response = await test_client.post(
        "/chatkit",
        json={"message": ""},
        headers={
            "X-User-Subject": "user:test",
            "X-Org-Id": "org:test"
        }
    )
    
    # Should still respond with error message
    assert response.status_code == 200


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chatkit_missing_headers(test_client, nats_helper):
    """Test ChatKit without required headers"""
    response = await test_client.post(
        "/chatkit",
        json={"message": "test message"}
    )
    
    # Should still respond with defaults
    assert response.status_code == 200


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chatkit_worker_failure(test_client, nats_helper, mock_worker):
    """Test ChatKit flow when worker fails"""
    await nats_helper.subscribe_to_chat_start()
    
    response = await test_client.post(
        "/chatkit",
        json={"message": "test failure"},
        headers={
            "X-User-Subject": "user:test",
            "X-Org-Id": "org:test"
        }
    )
    
    assert response.status_code == 200
    
    chat_start = await nats_helper.wait_for_chat_start(timeout=10)
    assert chat_start is not None
    
    run_id = chat_start["data"].get("run_id")
    assert run_id is not None
    
    await nats_helper.subscribe_to_events(run_id)
    
    # Simulate worker failure
    await mock_worker.simulate_failure("Worker encountered an error")
    
    events = nats_helper.get_events(run_id)
    assert len(events) >= 1
    
    # Verify failed event
    failed_event = next((e for e in events if e["data"].get("event_type") == "failed"), None)
    assert failed_event is not None, "failed event not received"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chatkit_worker_cancellation(test_client, nats_helper, mock_worker):
    """Test ChatKit flow when worker is cancelled"""
    await nats_helper.subscribe_to_chat_start()
    
    response = await test_client.post(
        "/chatkit",
        json={"message": "test cancellation"},
        headers={
            "X-User-Subject": "user:test",
            "X-Org-Id": "org:test"
        }
    )
    
    assert response.status_code == 200
    
    chat_start = await nats_helper.wait_for_chat_start(timeout=10)
    assert chat_start is not None
    
    run_id = chat_start["data"].get("run_id")
    assert run_id is not None
    
    await nats_helper.subscribe_to_events(run_id)
    
    # Simulate worker cancellation
    await mock_worker.simulate_cancellation()
    
    events = nats_helper.get_events(run_id)
    assert len(events) >= 1
    
    # Verify cancelled event
    cancelled_event = next((e for e in events if e["data"].get("event_type") == "cancelled"), None)
    assert cancelled_event is not None, "cancelled event not received"


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_chatkit_progress_events(test_client, nats_helper, mock_worker):
    """Test ChatKit progress event streaming"""
    await nats_helper.subscribe_to_chat_start()
    
    response = await test_client.post(
        "/chatkit",
        json={"message": "test progress"},
        headers={
            "X-User-Subject": "user:test",
            "X-Org-Id": "org:test"
        }
    )
    
    assert response.status_code == 200
    
    chat_start = await nats_helper.wait_for_chat_start(timeout=10)
    assert chat_start is not None
    
    run_id = chat_start["data"].get("run_id")
    assert run_id is not None
    
    await nats_helper.subscribe_to_events(run_id)
    
    # Simulate worker with multiple progress steps
    progress_steps = [
        "Step 1: Analyzing...",
        "Step 2: Processing...",
        "Step 3: Finalizing..."
    ]
    
    await mock_worker.simulate_worker_lifecycle(
        run_id=run_id,
        prompt="test progress",
        progress_steps=progress_steps,
        final_answer="Progress test completed"
    )
    
    events = nats_helper.get_events(run_id)
    
    # Count progress events
    progress_events = [e for e in events if e["data"].get("event_type") == "progress"]
    assert len(progress_events) == len(progress_steps), f"Expected {len(progress_steps)} progress events, got {len(progress_events)}"
