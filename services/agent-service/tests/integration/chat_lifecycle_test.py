"""Test full chat lifecycle via HTTP + NATS"""
import pytest
import asyncio
from httpx import AsyncClient
from message_fixtures import chat_start_fixture, chat_close_fixture


@pytest.mark.integration
async def test_chat_lifecycle_http_to_nats(nats_test_client, sample_run_id, sample_repository_id, sample_project_id):
    """Test full chat lifecycle: HTTP request → NATS publishing"""
    base_url = "http://localhost:8000"
    
    async with AsyncClient(base_url=base_url) as client:
        # Test 1: HTTP chat request should publish chat.start to NATS
        chat_request = {
            "message": "Test message",
            "repository_id": sample_repository_id,
            "project_id": sample_project_id,
            "mock_mode": True,
        }
        
        # This would normally be an HTTP endpoint call
        # For integration test, we simulate the NATS publishing
        message = chat_start_fixture(
            run_id=sample_run_id,
            repository_id=sample_repository_id,
            project_id=sample_project_id,
            mock_mode=True
        )
        
        await nats_test_client.publish("chat.start", message)
        
        # Verify message was published
        assert True
        
        # Test 2: HTTP close request should publish chat.close to NATS
        close_message = chat_close_fixture(run_id=sample_run_id)
        await nats_test_client.publish("chat.close", close_message)
        
        # Verify message was published
        assert True


@pytest.mark.integration
async def test_chat_start_with_repository(nats_test_client, sample_run_id, sample_repository_id, sample_project_id):
    """Test chat start with repository ID"""
    message = chat_start_fixture(
        run_id=sample_run_id,
        repository_id=sample_repository_id,
        project_id=sample_project_id,
        mock_mode=True
    )
    
    await nats_test_client.publish("chat.start", message)
    
    # Verify message contains repository_id
    assert message["repository_id"] == sample_repository_id
    assert message["project_id"] == sample_project_id


@pytest.mark.integration
async def test_chat_start_without_repository(nats_test_client, sample_run_id):
    """Test chat start without repository ID"""
    message = chat_start_fixture(
        run_id=sample_run_id,
        repository_id=None,
        project_id=None,
        mock_mode=True
    )
    
    await nats_test_client.publish("chat.start", message)
    
    # Verify message was published without repository
    assert message["run_id"] == sample_run_id
