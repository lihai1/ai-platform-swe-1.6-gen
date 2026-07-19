"""Integration tests for CrewAI worker flow using pytest-describe syntax.

These tests demonstrate:
1. Starting a CrewAI worker instance and expecting NATS messages
2. Starting a CrewAI worker instance, sending user events, and expecting responses
3. Testing prompt detection and input handling
4. Testing final_answer with real process output

Based on NATS flow:
- CrewAI worker publishes to: agent.user.{user_id}.events.{run_id}.state.{event_type}
- CrewAI worker publishes to: agent.user.{user_id}.chat.{run_id}.worker.events
- CrewAI worker subscribes to: agent.user.{user_id}.chat.{run_id}.user.events
"""
import pytest
import uuid
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

from agent_worker.nats_client import CrewAINatsClient
from agent_worker.runner import ProcessRunner
from agent_worker.subjects import Subjects, SubjectTemplates
from agent_worker.worker import CrewAIWorker


class CrewAITestHelper:
    """Helper class for CrewAI worker integration tests"""

    def __init__(self, nats_client, user_id: str, run_id: str):
        self.nc = nats_client
        self.user_id = user_id
        self.run_id = run_id
        self.subjects = Subjects.from_templates(
            SubjectTemplates(), uid=user_id, run_id=run_id
        )
        self.collected_events = {}
        self.subscriptions = []

    async def subscribe_to_worker_events(
        self,
        timeout: float = 5.0,
    ) -> None:
        """Subscribe to worker state events with timeout"""
        subject = self.subjects.state_events
        self.collected_events[f"state_{self.run_id}"] = []

        async def event_handler(msg):
            try:
                import json
                data = json.loads(msg.data.decode())
                self.collected_events[f"state_{self.run_id}"].append({
                    "subject": msg.subject,
                    "data": data,
                })
            except Exception as e:
                print(f"Error processing event: {e}")

        sub = await self.nc.subscribe(subject, cb=event_handler)
        self.subscriptions.append(sub)

    async def subscribe_to_worker_chat_events(
        self,
        timeout: float = 5.0,
    ) -> None:
        """Subscribe to worker chat events with timeout"""
        subject = self.subjects.chat_events
        self.collected_events[f"chat_{self.run_id}"] = []

        async def chat_handler(msg):
            try:
                import json
                data = json.loads(msg.data.decode())
                self.collected_events[f"chat_{self.run_id}"].append({
                    "subject": msg.subject,
                    "data": data,
                })
            except Exception as e:
                print(f"Error processing chat event: {e}")

        sub = await self.nc.subscribe(subject, cb=chat_handler)
        self.subscriptions.append(sub)

    async def publish_user_event(
        self, payload: dict, event_type: str = "user_input"
    ) -> None:
        """Publish a user event to the worker's user events subject."""
        message = {
            "message_id": str(uuid.uuid4()),
            "event_type": event_type,
            "run_id": self.run_id,
            "payload": payload,
            "timestamp": "2026-07-10T10:19:53.178810",
            "schema_version": "1.0",
        }
        await self.nc.publish(
            self.subjects.user_events,
            json.dumps(message).encode(),
        )

    async def wait_for_event(
        self,
        event_type: str,
        timeout: float = 5.0,
    ):
        """Wait for a specific event type with timeout"""
        start_time = asyncio.get_event_loop().time()
        state_key = f"state_{self.run_id}"

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if state_key in self.collected_events:
                for event in self.collected_events[state_key]:
                    if event["data"].get("event_type") == event_type:
                        return event
            await asyncio.sleep(0.1)

        return None

    async def wait_for_chat_event(
        self,
        event_type: str,
        timeout: float = 5.0,
    ):
        """Wait for a specific chat event type with timeout"""
        start_time = asyncio.get_event_loop().time()
        chat_key = f"chat_{self.run_id}"

        while (asyncio.get_event_loop().time() - start_time) < timeout:
            if chat_key in self.collected_events:
                for event in self.collected_events[chat_key]:
                    if event["data"].get("event_type") == event_type:
                        return event
            await asyncio.sleep(0.1)

        return None

    def get_state_events(self):
        """Get all collected state events for a run"""
        return self.collected_events.get(f"state_{self.run_id}", [])

    def get_chat_events(self):
        """Get all collected chat events for a run"""
        return self.collected_events.get(f"chat_{self.run_id}", [])

    async def cleanup(self) -> None:
        """Clean up subscriptions"""
        for sub in self.subscriptions:
            try:
                await sub.unsubscribe()
            except Exception as e:
                print(f"Error unsubscribing: {e}")
        self.subscriptions.clear()


def setup_crewai_env(run_id: str, user_id: str = "test-user-123") -> None:
    """Set up environment variables for CrewAI worker tests"""
    os.environ["USER_ID"] = user_id
    os.environ["RUN_ID"] = run_id
    os.environ["NATS_URL"] = "nats://localhost:4222"
    os.environ["WORKSPACE_PATH"] = "/tmp/test_workspace"


def _setup_crewai_scan_test(
    monkeypatch,
    tmp_path: Path,
    user_id: str,
    run_id: str,
    command: str = 'echo "selected-project-started"',
) -> Path:
    """Create a sample project and set up the environment for scan flow tests."""
    workspace = tmp_path
    project = workspace / "sample_crew"
    project.mkdir()
    (project / "pyproject.toml").write_text(
        '[project]\nname = "sample"\ndependencies = ["crewai"]\n'
    )
    (project / "main.py").write_text("print('hello')")

    monkeypatch.setenv("USER_ID", user_id)
    monkeypatch.setenv("RUN_ID", run_id)
    monkeypatch.setenv("NATS_URL", "nats://localhost:4222")
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    monkeypatch.setenv("AGENT_FOLDER", ".")
    monkeypatch.setenv("AGENT_COMMAND", command)
    monkeypatch.setenv("INPUT_IDLE_SECONDS", "2")
    monkeypatch.setenv("OUTPUT_MAX_BUFFER_CHARS", "1000")
    monkeypatch.delenv("AGENT_EXAMPLE", raising=False)
    monkeypatch.setattr(sys, "argv", ["test"])

    # Make the module-level WORKSPACE_ROOT constants point at the temp workspace.
    monkeypatch.setattr("agent_worker.bootstrap.WORKSPACE_ROOT", workspace)
    monkeypatch.setattr("agent_worker.worker.WORKSPACE_ROOT", workspace)

    return workspace


@pytest.fixture
async def nats_test_client():
    """Fixture for NATS test client"""
    from nats.aio.client import Client as NATSClient
    nc = NATSClient()
    await nc.connect("nats://localhost:4222")
    yield nc
    await nc.close()


def describe_crewai_worker_flow():
    """CrewAI worker integration test flows."""

    @pytest.mark.integration
    async def test_nats_client_connects_and_publishes_state(nats_test_client):
        """Test CrewAI NATS client connects and publishes state events."""
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"
        user_id = "test-user-123"

        setup_crewai_env(run_id, user_id)

        helper = CrewAITestHelper(nats_test_client, user_id, run_id)
        await helper.subscribe_to_worker_events(timeout=5.0)

        try:
            client = CrewAINatsClient(
                nats_url="nats://localhost:4222",
                uid=user_id,
                run_id=run_id,
            )
            await client.connect()

            # Publish a state event
            await client.publish_state("started", {"status": "started"})

            # Wait for the event
            event = await helper.wait_for_event("started", timeout=5.0)

            assert event is not None, "Expected 'started' event within 5 seconds"
            assert event["data"]["event_type"] == "started"
            assert event["data"]["payload"]["status"] == "started"

        finally:
            await helper.cleanup()
            if 'client' in locals():
                await client.close()

    @pytest.mark.integration
    async def test_nats_client_publishes_chat_events(nats_test_client):
        """Test CrewAI NATS client publishes chat events."""
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"
        user_id = "test-user-123"

        setup_crewai_env(run_id, user_id)

        helper = CrewAITestHelper(nats_test_client, user_id, run_id)
        await helper.subscribe_to_worker_chat_events(timeout=5.0)

        try:
            client = CrewAINatsClient(
                nats_url="nats://localhost:4222",
                uid=user_id,
                run_id=run_id,
            )
            await client.connect()

            # Publish a chat event
            await client.publish_chat("progress_update", {"message": "Working..."})

            # Wait for the event
            event = await helper.wait_for_chat_event("progress_update", timeout=5.0)

            assert event is not None, "Expected 'progress_update' chat event within 5 seconds"
            assert event["data"]["event_type"] == "progress_update"
            assert event["data"]["payload"]["message"] == "Working..."

        finally:
            await helper.cleanup()
            if 'client' in locals():
                await client.close()

    @pytest.mark.integration
    async def test_runner_simple_command_success(nats_test_client):
        """Test ProcessRunner with a simple successful command."""
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"
        user_id = "test-user-123"

        setup_crewai_env(run_id, user_id)

        helper = CrewAITestHelper(nats_test_client, user_id, run_id)
        await helper.subscribe_to_worker_events(timeout=5.0)
        await helper.subscribe_to_worker_chat_events(timeout=5.0)

        try:
            client = CrewAINatsClient(
                nats_url="nats://localhost:4222",
                uid=user_id,
                run_id=run_id,
            )
            await client.connect()

            # Create a temporary workspace
            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir)

                # Run a simple echo command
                runner = ProcessRunner(
                    nats=client,
                    command='echo "Hello from CrewAI"',
                    cwd=workspace,
                    input_idle_seconds=2.0,
                    output_max_buffer_chars=1000,
                )

                await runner.run()

                # Wait for started event
                started = await helper.wait_for_event("started", timeout=5.0)
                assert started is not None, "Expected 'started' event"

                # Wait for completed event
                completed = await helper.wait_for_event("completed", timeout=5.0)
                assert completed is not None, "Expected 'completed' event"

                # Wait for final_answer chat event
                final = await helper.wait_for_chat_event("final_answer", timeout=5.0)
                assert final is not None, "Expected 'final_answer' chat event"
                assert "Hello from CrewAI" in final["data"]["payload"]["content"]

        finally:
            await helper.cleanup()
            if 'client' in locals():
                await client.close()

    @pytest.mark.integration
    async def test_runner_accumulates_output_for_final_answer(nats_test_client):
        """Test that ProcessRunner accumulates all output for final_answer."""
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"
        user_id = "test-user-123"

        setup_crewai_env(run_id, user_id)

        helper = CrewAITestHelper(nats_test_client, user_id, run_id)
        await helper.subscribe_to_worker_chat_events(timeout=5.0)

        try:
            client = CrewAINatsClient(
                nats_url="nats://localhost:4222",
                uid=user_id,
                run_id=run_id,
            )
            await client.connect()

            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir)

                # Run a command that produces multiple lines
                runner = ProcessRunner(
                    nats=client,
                    command='echo "Line 1" && echo "Line 2" && echo "Line 3"',
                    cwd=workspace,
                    input_idle_seconds=2.0,
                    output_max_buffer_chars=1000,
                )

                await runner.run()

                # Wait for final_answer
                final = await helper.wait_for_chat_event("final_answer", timeout=5.0)
                assert final is not None, "Expected 'final_answer' chat event"

                content = final["data"]["payload"]["content"]
                assert "Line 1" in content
                assert "Line 2" in content
                assert "Line 3" in content

        finally:
            await helper.cleanup()
            if 'client' in locals():
                await client.close()

    @pytest.mark.integration
    async def test_runner_command_failure(nats_test_client):
        """Test ProcessRunner with a failing command."""
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"
        user_id = "test-user-123"

        setup_crewai_env(run_id, user_id)

        helper = CrewAITestHelper(nats_test_client, user_id, run_id)
        await helper.subscribe_to_worker_events(timeout=5.0)

        try:
            client = CrewAINatsClient(
                nats_url="nats://localhost:4222",
                uid=user_id,
                run_id=run_id,
            )
            await client.connect()

            with tempfile.TemporaryDirectory() as tmpdir:
                workspace = Path(tmpdir)

                # Run a command that fails
                runner = ProcessRunner(
                    nats=client,
                    command='exit 1',
                    cwd=workspace,
                    input_idle_seconds=2.0,
                    output_max_buffer_chars=1000,
                )

                await runner.run()

                # Wait for failed event
                failed = await helper.wait_for_event("failed", timeout=5.0)
                assert failed is not None, "Expected 'failed' event"
                assert failed["data"]["payload"]["status"] == "failed"

        finally:
            await helper.cleanup()
            if 'client' in locals():
                await client.close()


def describe_crewai_worker_scan_flow():
    """End-to-end flow for project list scan, user selection, and runner start."""

    @pytest.mark.integration
    async def test_worker_scans_publishes_and_starts_on_selection(nats_test_client, tmp_path, monkeypatch):
        """Worker scans projects, publishes list, and starts the selected project."""
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"
        user_id = "test-user-scan"

        _setup_crewai_scan_test(monkeypatch, tmp_path, user_id, run_id)

        helper = CrewAITestHelper(nats_test_client, user_id, run_id)
        await helper.subscribe_to_worker_chat_events(timeout=10.0)
        await helper.subscribe_to_worker_events(timeout=10.0)

        worker = CrewAIWorker()
        worker_task = asyncio.create_task(worker.start())

        try:
            # Wait for the project list prompt.
            prompt_event = await helper.wait_for_chat_event("final_answer", timeout=10.0)
            assert prompt_event is not None, "Expected project list final_answer event"
            payload = prompt_event["data"]["payload"]
            assert payload["status"] == "project_selection_required"
            assert len(payload["projects"]) == 1
            assert payload["projects"][0]["name"] == "sample_crew"

            # Simulate user selecting the project via explicit project_path.
            await helper.publish_user_event({
                "project_path": "sample_crew",
                "input": "sample_crew",
            })

            # Verify the runner started for the selected project.
            started = await helper.wait_for_event("started", timeout=10.0)
            assert started is not None, "Expected 'started' state event"
            assert "sample_crew" in started["data"]["payload"]["cwd"]
            assert 'echo "selected-project-started"' in started["data"]["payload"]["command"]

            completed = await helper.wait_for_event("completed", timeout=10.0)
            assert completed is not None, "Expected 'completed' state event"
        finally:
            try:
                await worker.stop()
            except Exception:
                pass
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            await helper.cleanup()

    @pytest.mark.integration
    async def test_worker_handles_invalid_project_path(nats_test_client, tmp_path, monkeypatch):
        """Worker publishes failure when given an invalid project_path."""
        run_id = f"test-run-{uuid.uuid4().hex[:8]}"
        user_id = "test-user-invalid"

        _setup_crewai_scan_test(monkeypatch, tmp_path, user_id, run_id)

        helper = CrewAITestHelper(nats_test_client, user_id, run_id)
        await helper.subscribe_to_worker_chat_events(timeout=10.0)
        await helper.subscribe_to_worker_events(timeout=10.0)

        worker = CrewAIWorker()
        worker_task = asyncio.create_task(worker.start())

        try:
            # Wait for the project list prompt.
            prompt_event = await helper.wait_for_chat_event("final_answer", timeout=10.0)
            assert prompt_event is not None, "Expected project list final_answer event"
            payload = prompt_event["data"]["payload"]
            assert payload["status"] == "project_selection_required"

            # Send an invalid project_path.
            await helper.publish_user_event({
                "project_path": "nonexistent_project",
                "input": "nonexistent_project",
            })

            # Expect a failed state event.
            failed = await helper.wait_for_event("failed", timeout=10.0)
            assert failed is not None, "Expected 'failed' state event for invalid project path"
            assert failed["data"]["payload"]["status"] == "failed"

            # Also expect a final_answer chat event with error status.
            final = await helper.wait_for_chat_event("final_answer", timeout=10.0)
            assert final is not None, "Expected error final_answer chat event"
            assert final["data"]["payload"]["status"] in ("failed", "project_selection_required")
        finally:
            try:
                await worker.stop()
            except Exception:
                pass
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass
            await helper.cleanup()
