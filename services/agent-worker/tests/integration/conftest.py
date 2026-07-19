"""Shared integration test fixtures for agent-worker."""
import asyncio
import os
import sys
import uuid
from typing import AsyncGenerator

import pytest
from nats.aio.client import Client as NATSClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../"))


@pytest.fixture
async def nats_client() -> AsyncGenerator[NATSClient, None]:
    """Provide a fresh NATS client for each test."""
    nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
    nc = NATSClient()
    await nc.connect(nats_url)
    try:
        yield nc
    finally:
        await nc.close()


@pytest.fixture
def run_id() -> str:
    """Unique run id for test isolation."""
    return f"test-run-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def user_id() -> str:
    """Shared test user id."""
    return "test-user-001"


@pytest.fixture
def worker_env(run_id: str, user_id: str) -> None:
    """Set worker environment variables and restore them after the test."""
    keys = [
        "RUN_ID",
        "USER_ID",
        "TASK",
        "PROJECT_ID",
        "REPOSITORY_ID",
        "MAX_TOKENS",
        "MAX_COST",
        "MAX_REPAIR_COUNT",
        "AGENT_TYPE",
        "LLM_PROVIDER",
        "MODEL_NAME",
        "MOCK_MODE",
        "DATABASE_URL",
        "WORKSPACE_PATH",
    ]
    old = {k: os.environ.get(k) for k in keys}
    os.environ.update({
        "RUN_ID": run_id,
        "USER_ID": user_id,
        "TASK": "Write a greeting function and verify it works",
        "PROJECT_ID": "test-project-001",
        "REPOSITORY_ID": "test-repo-001",
        "MAX_TOKENS": "1000",
        "MAX_COST": "0.1",
        "MAX_REPAIR_COUNT": "2",
        "AGENT_TYPE": "specialist",
        "LLM_PROVIDER": "fake",
        "MODEL_NAME": "test-model",
        "MOCK_MODE": "true",
        "DATABASE_URL": "postgresql+asyncpg://agentic:agentic@localhost:5433/agentic",
        "WORKSPACE_PATH": "tests/integration/output",
    })
    yield
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
