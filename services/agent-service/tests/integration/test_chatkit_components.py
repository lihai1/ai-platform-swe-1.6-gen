"""Integration tests for custom ChatKit server components"""
import pytest
import asyncio
import sys
import os
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../app"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))


@pytest.mark.integration
async def test_context_from_request():
    """Test context extraction from request"""
    from internal.chatkit.context import context_from_request
    from unittest.mock import Mock
    
    # Create mock request
    request = Mock()
    request.headers = {
        "X-User-Subject": "user:test",
        "X-Org-Id": "org:test",
        "X-Request-Id": "req-123",
    }
    
    # Extract context
    context = context_from_request(request)
    
    # Verify context
    assert context.user_subject == "user:test"
    assert context.org_id == "org:test"
    assert context.request_id == "req-123"


@pytest.mark.integration
async def test_context_from_request_missing_headers():
    """Test context extraction with missing headers"""
    from internal.chatkit.context import context_from_request
    from unittest.mock import Mock
    
    # Create mock request without headers
    request = Mock()
    request.headers = {}
    
    # Extract context
    context = context_from_request(request)
    
    # Verify context has defaults
    assert context.user_subject == "user:local-dev"
    assert context.org_id == "org:aegis-demo"
    assert context.request_id is None


@pytest.mark.integration
async def test_extract_text_from_user_message():
    """Test text extraction from user message"""
    from internal.chatkit.server import extract_text
    
    # Test with dict content
    message = Mock()
    message.content = [{"type": "input_text", "text": "Hello world"}]
    
    text = extract_text(message)
    assert text == "Hello world"
    
    # Test with empty content
    message_empty = Mock()
    message_empty.content = [{"type": "input_text", "text": ""}]
    
    text = extract_text(message_empty)
    assert text == ""
    
    # Test with None
    text = extract_text(None)
    assert text == ""


@pytest.mark.integration
async def test_event_mapper_functions():
    """Test event mapper functions can be imported and called"""
    from internal.chatkit.event_mapper import (
        get_event_type,
        is_completed_event,
        is_failed_event,
        is_cancelled_event,
        final_answer_from_event,
        progress_from_event,
    )
    
    # Test get_event_type
    event = {"event_type": "created"}
    assert get_event_type(event) == "created"
    
    # Test is_completed_event
    completed_event = {"event_type": "completed"}
    assert is_completed_event(completed_event) == True
    
    # Test is_failed_event
    failed_event = {"event_type": "failed"}
    assert is_failed_event(failed_event) == True
    
    # Test is_cancelled_event
    cancelled_event = {"event_type": "cancelled"}
    assert is_cancelled_event(cancelled_event) == True
    
    # Test final_answer_from_event
    event_with_answer = {"event_type": "completed", "final_answer": "test answer"}
    assert final_answer_from_event(event_with_answer) == "test answer"
    
    # Test progress_from_event
    progress_event = {"event_type": "step_started", "payload": {"step": "test step"}}
    progress = progress_from_event(progress_event)
    assert progress is not None


@pytest.mark.integration
async def test_nats_bridge_class():
    """Test NatsBridge class can be instantiated"""
    from internal.chatkit.nats_bridge import NatsBridge
    from unittest.mock import Mock
    
    # Create mock NATS client
    mock_nats = Mock()
    
    # Create NatsBridge
    bridge = NatsBridge(mock_nats)
    
    # Verify bridge was created
    assert bridge is not None
    assert bridge.nats == mock_nats


@pytest.mark.integration
async def test_postgresql_store_class():
    """Test PostgreSQLStore class can be instantiated"""
    from internal.chatkit.store import PostgreSQLStore
    from unittest.mock import Mock
    
    # Create mock database session factory
    mock_session_factory = Mock()
    
    # Create PostgreSQLStore
    store = PostgreSQLStore(mock_session_factory)
    
    # Verify store was created
    assert store is not None
    assert store.session_factory == mock_session_factory


# Standalone entry point to run without conftest
if __name__ == "__main__":
    import sys
    pytest.main([__file__, "-v", "-s"])
