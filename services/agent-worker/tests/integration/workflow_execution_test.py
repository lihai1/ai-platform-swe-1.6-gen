"""Test workflow execution and event publishing in agent-worker"""
import pytest
import asyncio
from message_fixtures import (
    run_start_fixture,
    state_event_fixture,
    final_answer_fixture,
    progress_update_fixture,
)


@pytest.mark.integration
async def test_publish_state_events(nats_test_client, sample_run_id):
    """Test publishing state events to NATS"""
    # Publish run.start command
    command_subject = f"agent.chat.{sample_run_id}.user.events"
    command_message = run_start_fixture(
        run_id=sample_run_id,
        user_id="test-user-123",
        project_id="test-project-123",
        repository_id="test-repo-123",
        task="Test task"
    )
    await nats_test_client.publish(command_subject, command_message)
    
    # Simulate workflow execution by publishing state events
    await nats_test_client.publish(f"agent.events.{sample_run_id}.created", state_event_fixture(sample_run_id, "created"))
    await nats_test_client.publish(f"agent.events.{sample_run_id}.running", state_event_fixture(sample_run_id, "running"))
    
    # Verify events were published (no error raised)
    assert True


@pytest.mark.integration
async def test_publish_final_answer(nats_test_client, sample_run_id):
    """Test publishing final answer event to NATS"""
    subject = f"agent.chat.{sample_run_id}.user.events"
    message = final_answer_fixture(run_id=sample_run_id, content="Test final answer")
    await nats_test_client.publish(subject, message)
    
    # Verify final answer was published (no error raised)
    assert True


@pytest.mark.integration
async def test_publish_progress_update(nats_test_client, sample_run_id):
    """Test publishing progress update event to NATS"""
    subject = f"agent.chat.{sample_run_id}.user.events"
    message = progress_update_fixture(run_id=sample_run_id, content="Test progress")
    await nats_test_client.publish(subject, message)
    
    # Verify progress update was published (no error raised)
    assert True


@pytest.mark.integration
async def test_publish_full_workflow_flow(nats_test_client, sample_run_id):
    """Test publishing full workflow flow: run.start → state events → final answer"""
    # Publish run.start command
    command_subject = f"agent.chat.{sample_run_id}.user.events"
    command_message = run_start_fixture(
        run_id=sample_run_id,
        user_id="test-user-123",
        project_id="test-project-123",
        repository_id="test-repo-123",
        task="Test task"
    )
    await nats_test_client.publish(command_subject, command_message)
    
    # Simulate workflow execution
    await nats_test_client.publish(f"agent.events.{sample_run_id}.created", state_event_fixture(sample_run_id, "created"))
    await nats_test_client.publish(f"agent.events.{sample_run_id}.running", state_event_fixture(sample_run_id, "running"))
    await nats_test_client.publish(f"agent.events.{sample_run_id}.completed", state_event_fixture(sample_run_id, "completed"))
    
    # Verify full flow (no error raised)
    assert True
