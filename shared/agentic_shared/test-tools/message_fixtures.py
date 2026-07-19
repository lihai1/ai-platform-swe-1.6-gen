"""Standard test message fixtures for NATS messaging"""
from typing import Dict, Any
import uuid


def chat_start_fixture(run_id: str = "test-run-123", repository_id: str = "test-repo-123", project_id: str = "test-project-123", mock_mode: bool = True, llm_provider: str = None) -> Dict[str, Any]:
    """Standard chat.start message fixture"""
    data = {
        "message_id": str(uuid.uuid4()),
        "run_id": run_id,
        "repository_id": repository_id,
        "project_id": project_id,
        "mock_mode": mock_mode,
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }
    if llm_provider:
        data["llm_provider"] = llm_provider
    return data


def chat_close_fixture(run_id: str = "test-run-123") -> Dict[str, Any]:
    """Standard chat.close message fixture"""
    return {
        "message_id": str(uuid.uuid4()),
        "run_id": run_id,
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }


def run_start_fixture(run_id: str = "test-run-123", user_id: str = "test-user-123", project_id: str = "test-project-123", repository_id: str = "test-repo-123", task: str = "Test task", llm_provider: str = "fake") -> Dict[str, Any]:
    """Standard run.start message fixture"""
    return {
        "message_id": str(uuid.uuid4()),
        "command_type": "run.start",
        "run_id": run_id,
        "payload": {
            "user_id": user_id,
            "project_id": project_id,
            "repository_id": repository_id,
            "task": task,
            "run_id": run_id,
            "llm_provider": llm_provider,
        },
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }


def state_event_fixture(run_id: str = "test-run-123", event_type: str = "created", payload: Dict[str, Any] = None) -> Dict[str, Any]:
    """Standard state event message fixture"""
    if payload is None:
        payload = {"status": "CREATED"}
    
    return {
        "message_id": str(uuid.uuid4()),
        "event_type": event_type,
        "run_id": run_id,
        "payload": payload,
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }


def worker_ready_fixture(run_id: str = "test-run-123") -> Dict[str, Any]:
    """Standard worker ready message fixture"""
    return {
        "message_id": str(uuid.uuid4()),
        "run_id": run_id,
        "status": "ready",
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }


def final_answer_fixture(run_id: str = "test-run-123", content: str = "Test final answer") -> Dict[str, Any]:
    """Standard final answer message fixture"""
    return {
        "message_id": str(uuid.uuid4()),
        "event_type": "final_answer",
        "run_id": run_id,
        "payload": {
            "content": content,
        },
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }


def progress_update_fixture(run_id: str = "test-run-123", content: str = "Test progress") -> Dict[str, Any]:
    """Standard progress update message fixture"""
    return {
        "message_id": str(uuid.uuid4()),
        "event_type": "progress_update",
        "run_id": run_id,
        "payload": {
            "content": content,
        },
        "timestamp": "2024-01-01T00:00:00Z",
        "schema_version": "1.0",
    }
