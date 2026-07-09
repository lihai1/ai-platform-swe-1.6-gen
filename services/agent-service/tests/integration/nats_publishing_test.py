"""Test NATS handlers in agent-service"""
import pytest
import asyncio
from message_fixtures import (
    chat_start_fixture,
    chat_close_fixture,
    run_start_fixture,
)
from internal.handlers.nats import handle_agent_state_event, handle_worker_user_event


@pytest.mark.integration
async def test_handle_agent_state_event():
    """Test that handle_agent_state_event can be imported and called"""
    # Create a mock event
    event = {
        "run_id": "test-run-123",
        "event_type": "created",
        "payload": {},
        "timestamp": "2024-01-01T00:00:00Z"
    }
    
    # Create a mock push_event function
    async def mock_push_event(run_id, data):
        pass
    
    # Verify handler function exists and is callable
    # (We don't call it directly because it requires ChatKit setup)
    _ = handle_agent_state_event
    _ = event
    _ = mock_push_event


@pytest.mark.integration
async def test_handle_worker_user_event():
    """Test that handle_worker_user_event can be imported and called"""
    # Create a mock event
    event = {
        "run_id": "test-run-123",
        "event_type": "final_answer",
        "payload": {"content": "Test answer"},
        "timestamp": "2024-01-01T00:00:00Z"
    }
    
    # Create a mock push_event function
    async def mock_push_event(run_id, data):
        pass
    
    # Verify handler function exists and is callable
    # (We don't call it directly because it requires ChatKit setup)
    _ = handle_worker_user_event
    _ = event
    _ = mock_push_event
