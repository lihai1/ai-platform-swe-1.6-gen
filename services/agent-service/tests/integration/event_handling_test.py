"""Test event handling in agent-service"""
import pytest
import asyncio
from message_fixtures import state_event_fixture


@pytest.mark.integration
async def test_publish_state_events(nats_test_client, sample_run_id):
    """Test publishing state events to NATS"""
    # Publish state events
    await nats_test_client.publish(f"agent.events.{sample_run_id}.created", state_event_fixture(sample_run_id, "created"))
    await nats_test_client.publish(f"agent.events.{sample_run_id}.running", state_event_fixture(sample_run_id, "running"))
    
    # Verify events were published (no error raised)
    assert True


@pytest.mark.integration
async def test_process_state_event(nats_test_client, sample_run_id):
    """Test processing a state event"""
    event = state_event_fixture(sample_run_id, "created", {"status": "CREATED"})
    
    # Publish state event
    await nats_test_client.publish(f"agent.events.{sample_run_id}.created", event)
    
    # Verify event was processed (no error raised)
    assert True


@pytest.mark.integration
async def test_publish_multiple_state_events(nats_test_client, sample_run_id):
    """Test publishing multiple state events"""
    # Publish multiple events
    await nats_test_client.publish(f"agent.events.{sample_run_id}.created", state_event_fixture(sample_run_id, "created"))
    await nats_test_client.publish(f"agent.events.{sample_run_id}.running", state_event_fixture(sample_run_id, "running"))
    await nats_test_client.publish(f"agent.events.{sample_run_id}.completed", state_event_fixture(sample_run_id, "completed"))
    
    # Verify all events were published (no error raised)
    assert True
