"""Integration test configuration for agent-service"""
import pytest
import asyncio
import sys
import os

# Add shared test tools to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../../shared/test-tools"))

# Try to import test helpers, but don't fail if they're not available
nats_client = None
postgres_client = None
wait_for_postgres = None

try:
    import importlib
    nats_helpers = importlib.import_module("nats_helpers")
    nats_client = nats_helpers.nats_client
except (ImportError, AttributeError):
    pass

try:
    import importlib
    postgres_helpers = importlib.import_module("postgres_helpers")
    postgres_client = postgres_helpers.postgres_client
    wait_for_postgres = postgres_helpers.wait_for_postgres
except (ImportError, AttributeError):
    pass


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def nats_test_client():
    """Provide NATS test client for tests"""
    if nats_client is None:
        # Don't skip - return None instead
        yield None
    else:
        async with nats_client() as client:
            yield client


@pytest.fixture(scope="session")
async def postgres_test_client():
    """Provide PostgreSQL test client for tests"""
    if postgres_client is None or wait_for_postgres is None:
        # Don't skip - return None instead
        yield None
    else:
        # Wait for PostgreSQL to be ready
        await wait_for_postgres()
        
        async with postgres_client() as client:
            yield client


@pytest.fixture(autouse=True)
async def cleanup_postgres(postgres_test_client):
    """Clean up database after each test"""
    if postgres_client is None:
        yield
        return
    
    yield
    
    # Clean up test data
    try:
        await postgres_test_client.execute("TRUNCATE TABLE agent.agent_runs CASCADE")
        await postgres_test_client.execute("TRUNCATE TABLE agent.agent_events CASCADE")
        await postgres_test_client.execute("TRUNCATE TABLE agent.agent_approvals CASCADE")
    except Exception as e:
        print(f"Cleanup failed: {e}")


@pytest.fixture
def sample_run_id():
    """Provide a sample run ID for tests"""
    return "test-run-123"


@pytest.fixture
def sample_repository_id():
    """Provide a sample repository ID for tests"""
    return "test-repo-123"


@pytest.fixture
def sample_project_id():
    """Provide a sample project ID for tests"""
    return "test-project-123"


@pytest.fixture
def sample_user_id():
    """Provide a sample user ID for tests"""
    return "test-user-123"
