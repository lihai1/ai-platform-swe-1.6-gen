"""Shared pytest fixtures for integration testing"""
import pytest
import asyncio
from typing import AsyncGenerator
from test_tools.nats_helpers import nats_client, NATSTestClient
from test_tools.postgres_helpers import postgres_client, PostgresTestClient, wait_for_postgres


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def nats_test_client() -> AsyncGenerator[NATSTestClient, None]:
    """Provide NATS test client for tests"""
    async with nats_client() as client:
        yield client


@pytest.fixture(scope="session")
async def postgres_test_client() -> AsyncGenerator[PostgresTestClient, None]:
    """Provide PostgreSQL test client for tests"""
    # Wait for PostgreSQL to be ready
    await wait_for_postgres()
    
    async with postgres_client() as client:
        yield client


@pytest.fixture(autouse=True)
async def cleanup_postgres(postgres_test_client: PostgresTestClient):
    """Clean up database after each test"""
    yield
    
    # Clean up test data
    try:
        await postgres_test_client.execute("TRUNCATE TABLE app.chat_containers CASCADE")
    except Exception as e:
        print(f"Cleanup failed: {e}")


@pytest.fixture
def sample_run_id() -> str:
    """Provide a sample run ID for tests"""
    return "test-run-123"


@pytest.fixture
def sample_repository_id() -> str:
    """Provide a sample repository ID for tests"""
    return "test-repo-123"


@pytest.fixture
def sample_project_id() -> str:
    """Provide a sample project ID for tests"""
    return "test-project-123"


@pytest.fixture
def sample_user_id() -> str:
    """Provide a sample user ID for tests"""
    return "test-user-123"
