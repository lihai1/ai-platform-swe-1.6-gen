"""E2E test configuration"""
import pytest
import asyncio
import os
import subprocess
from httpx import AsyncClient


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_client():
    """Create test HTTP client"""
    base_url = os.getenv("TEST_BASE_URL", "http://localhost:8001")
    async with AsyncClient(base_url=base_url) as client:
        yield client


@pytest.fixture(autouse=True)
async def cleanup_runs(test_client):
    """Clean up test runs after each test"""
    yield
    
    # Clean up any test runs created during the test
    # In production, this would query for test runs and delete them
    pass


@pytest.fixture(scope="session")
async def docker_compose_test():
    """Start test Docker Compose environment for ChatKit E2E tests"""
    compose_file = os.path.join(
        os.path.dirname(__file__), 
        "../../../", 
        "docker-compose.test.yml"
    )
    
    # Start Docker Compose
    try:
        subprocess.run(
            ["docker-compose", "-f", compose_file, "up", "-d"],
            check=True,
            capture_output=True,
            timeout=120
        )
    except subprocess.CalledProcessError as e:
        pytest.skip(f"Failed to start docker-compose: {e}")
    except subprocess.TimeoutExpired:
        pytest.skip("Docker compose startup timed out")
    
    # Wait for services to be healthy
    await asyncio.sleep(15)
    
    yield
    
    # Stop Docker Compose (without -v to preserve volumes)
    try:
        subprocess.run(
            ["docker-compose", "-f", compose_file, "down"],
            check=True,
            capture_output=True,
            timeout=60
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass  # Best effort cleanup


@pytest.fixture(scope="session")
async def nats_helper(docker_compose_test):
    """NATS test helper for event validation"""
    from tests.e2e.fixtures.nats_helper import NATSTestHelper
    
    helper = NATSTestHelper(nats_url="nats://localhost:4222")
    await helper.connect()
    yield helper
    await helper.cleanup()


@pytest.fixture
async def mock_worker(nats_helper):
    """Mock agent worker for simulating responses"""
    from tests.e2e.fixtures.mock_agent_runner import MockAgentRunner
    
    worker = MockAgentRunner(nats_helper)
    yield worker
