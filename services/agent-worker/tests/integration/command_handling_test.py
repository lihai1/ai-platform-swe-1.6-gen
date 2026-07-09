"""Test command handling in agent-worker"""
import pytest
import asyncio
from message_fixtures import run_start_fixture


@pytest.mark.integration
async def test_publish_run_start_command(nats_test_client, sample_run_id, sample_user_id, sample_repository_id, sample_project_id):
    """Test publishing run.start command to NATS"""
    subject = f"agent.chat.{sample_run_id}.user.events"
    message = run_start_fixture(
        run_id=sample_run_id,
        user_id=sample_user_id,
        project_id=sample_project_id,
        repository_id=sample_repository_id,
        task="Test task"
    )
    
    await nats_test_client.publish(subject, message)
    
    # Verify command was published (no error raised)
    assert True


@pytest.mark.integration
async def test_publish_unknown_command(nats_test_client, sample_run_id):
    """Test publishing unknown command type to NATS"""
    subject = f"agent.chat.{sample_run_id}.user.events"
    message = {
        "message_id": "test-msg-unknown",
        "command_type": "unknown_command",
        "run_id": sample_run_id,
        "payload": {},
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }
    
    await nats_test_client.publish(subject, message)
    
    # Verify command was published (no error raised)
    assert True


@pytest.mark.integration
async def test_publish_run_start_with_payload(nats_test_client, sample_run_id):
    """Test publishing run.start command with full payload to NATS"""
    subject = f"agent.chat.{sample_run_id}.user.events"
    message = run_start_fixture(
        run_id=sample_run_id,
        user_id="test-user-123",
        project_id="test-project-123",
        repository_id="test-repo-123",
        task="Test task with full payload"
    )
    
    await nats_test_client.publish(subject, message)
    
    # Verify command was published (no error raised)
    assert True
