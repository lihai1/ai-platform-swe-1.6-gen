"""Full NATS/Postgres integration test for the CrewAI expert worker.

This test:
1. Starts the crewai-expert worker in a Docker container.
2. Connects it to the development NATS and Postgres services.
3. Clones the crewAI stock-analysis example into the container workspace.
4. Drives the durable state machine through project selection and patch
   approval via NATS user events.
5. Verifies the graph reaches RUN_CREWAI_CLI and ends in a terminal state.

The example cannot fully execute without an LLM, so the assertion is that
*the flow reaches RUN_CREWAI_CLI and terminates* (completed, failed, or
cancelled) rather than that the stock crew itself succeeds.
"""

from __future__ import annotations

import asyncio
import ast
import subprocess
from pathlib import Path
from typing import Any, Optional

import pytest

from helpers import WorkerTestHarness, sendNatsUserMessage


IMAGE = "agentic-agents-platform-agent-worker-crewai-expert:latest"
NETWORK = "agent-worker_default"
REPOSITORY_URL = "https://github.com/crewAIInc/crewAI-examples.git"
PROJECT_NAME = "stock_analysis"


def _run(cmd: list[str], check: bool = False, capture: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return its result."""
    return subprocess.run(
        cmd,
        check=check,
        capture_output=capture,
        text=True,
    )


def _ensure_image() -> None:
    """Skip the test if the worker image has not been built."""
    result = _run(["docker", "image", "inspect", IMAGE], check=False)
    if result.returncode != 0:
        pytest.skip(f"Docker image {IMAGE} not found; run 'docker build' first")


def _start_container(run_id: str, user_id: str, container_name: str) -> str:
    """Start the crewai-expert worker container and return its id."""
    print(f"[test] starting container {container_name} for run {run_id}")
    _run(["docker", "rm", "-f", container_name], check=False)

    cmd = [
        "docker",
        "run",
        "-d",
        "--network",
        NETWORK,
        "--name",
        container_name,
        "-e",
        f"RUN_ID={run_id}",
        "-e",
        f"USER_ID={user_id}",
        "-e",
        "NATS_URL=nats://nats:4222",
        "-e",
        "DATABASE_URL=postgresql+asyncpg://agentic:agentic@postgres:5432/agentic",
        "-e",
        f"REPOSITORY_URL={REPOSITORY_URL}",
        "-e",
        "BRANCH=main",
        "-e",
        "MOCK_MODE=false",
        "-e",
        "CREWAI_EXPERT_REPAIR=true",
        "-e",
        "CREWAI_EXPERT_REQUIRE_PATCH_APPROVAL=true",
        "-e",
        "CREWAI_EXPERT_MAX_SELECTION_ATTEMPTS=3",
        "-e",
        "CREWAI_EXPERT_MAX_PATCH_ATTEMPTS=2",
        "-e",
        "COMMAND_TIMEOUT_SECONDS=180",
        "-e",
        "CREWAI_EXPERT_SYNC_TIMEOUT_SECONDS=600",
        "-e",
        "OLLAMA_BASE_URL=http://127.0.0.1:11434",
        "-e",
        "OLLAMA_MODEL=qwen3.5:9b",
        IMAGE,
    ]
    result = _run(cmd, check=True)
    container_id = result.stdout.strip()
    if not container_id:
        raise RuntimeError("docker run did not return a container id")
    print(f"[test] container id: {container_id}")
    return container_id


def _stop_container(container_name: str) -> None:
    """Stop the container, capture its logs, and then remove it."""
    print(f"[test] stopping container {container_name}")
    _run(["docker", "stop", "--time", "5", container_name], check=False)
    log_path = f"/tmp/crewai_int_{container_name}.log"
    try:
        logs = subprocess.run(
            ["docker", "logs", container_name],
            check=False,
            capture_output=True,
            text=True,
        )
        Path(log_path).write_text(logs.stdout + logs.stderr, encoding="utf-8", errors="ignore")
        print(f"[test] container logs written to {log_path}")
    except Exception as exc:
        print(f"[test] failed to capture container logs: {exc}")
    _run(["docker", "rm", "-f", container_name], check=False)


async def _wait_for_state_event(
    harness: WorkerTestHarness,
    *,
    event_type: Optional[str] = None,
    payload_status: Optional[str] = None,
    reason: Optional[str] = None,
    timeout: float = 120.0,
) -> Optional[dict[str, Any]]:
    """Poll the harness state events until a matching event arrives."""
    print(f"[test] waiting for state event type={event_type} status={payload_status} reason={reason} timeout={timeout}")
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for ev in harness.events["state"]:
            data = ev["data"]
            if event_type and data.get("event_type") != event_type:
                continue
            payload = data.get("payload", {})
            if payload_status and payload.get("status") != payload_status:
                continue
            if reason and payload.get("reason") != reason:
                continue
            print(f"[test] matched state event: {data}")
            return data
        await asyncio.sleep(0.2)
    print(f"[test] timed out waiting for state event type={event_type} status={payload_status} reason={reason}")
    return None


def _approval_payload(event: dict[str, Any]) -> dict[str, Any]:
    """Extract the approval dict serialized as a string in the prompt field."""
    payload = event.get("payload", {})
    prompt = payload.get("prompt", "")
    try:
        return ast.literal_eval(prompt)
    except (ValueError, SyntaxError):
        return {}


async def _wait_for_terminal(
    harness: WorkerTestHarness,
    timeout: float = 300.0,
) -> Optional[str]:
    """Wait for a completed/failed/cancelled state event and return its type."""
    print(f"[test] waiting for terminal state timeout={timeout}")
    terminal_types = {"completed", "failed", "cancelled"}
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for ev in harness.events["state"]:
            event_type = ev["data"].get("event_type")
            if event_type in terminal_types:
                print(f"[test] terminal state received: {event_type}")
                return str(event_type)
        await asyncio.sleep(0.2)
    print("[test] timed out waiting for terminal state")
    return None


async def _send_user_input(nats_client, run_id: str, user_id: str, text: str) -> None:
    """Publish a user_input event for the worker."""
    print(f"[test] sending user input: {text!r}")
    await sendNatsUserMessage(
        nats_client,
        run_id,
        user_id,
        {"type": "user_input", "payload": {"input": text}},
    )


@pytest.mark.integration
async def test_crewai_expert_stocks_flow(nats_client, run_id, user_id):
    """Run the full crewai-expert state flow on the stock analysis example."""
    print(f"[test] run_id={run_id} user_id={user_id}")
    _ensure_image()

    container_name = f"crewai-expert-test-{run_id.replace(':', '-')}".lower()
    harness = WorkerTestHarness(nats_client, run_id, user_id)
    await harness.subscribe()
    print("[test] subscribed to worker events")

    container_id = ""
    try:
        container_id = await asyncio.get_event_loop().run_in_executor(
            None, _start_container, run_id, user_id, container_name
        )

        # 1. Worker publishes ready.
        print("[test] waiting for worker_ready")
        ready = await harness.wait_for("ready", timeout=120.0)
        assert ready is not None, "worker_ready not received within 120s"
        assert ready["data"]["event_type"] == "worker_ready"

        # 2. Project selection approval.
        selection_event = await _wait_for_state_event(
            harness,
            event_type="waiting_input",
            reason="project_selection",
            timeout=120.0,
        )
        assert selection_event is not None, "project selection waiting_input not received"
        approval = _approval_payload(selection_event)
        assert "options" in approval
        assert PROJECT_NAME in approval["options"]

        await _send_user_input(nats_client, run_id, user_id, PROJECT_NAME)

        # 3. Patch approval.
        print("[test] waiting for patch approval")
        patch_event = await _wait_for_state_event(
            harness,
            event_type="waiting_input",
            reason="patch_approval",
            timeout=120.0,
        )
        assert patch_event is not None, "patch approval waiting_input not received"

        await _send_user_input(nats_client, run_id, user_id, "approved")

        # 4. Wait for ProcessRunner to publish that the CLI started.
        # This confirms the graph reached RUN_CREWAI_CLI.
        # Dependency sync for crewai[tools] can take several minutes on first run.
        started_event = await _wait_for_state_event(
            harness,
            event_type="started",
            timeout=600.0,
        )
        assert started_event is not None, (
            "ProcessRunner did not publish a 'started' event after patch approval"
        )

        # 5. Wait for the CLI to finish and the graph to terminate.
        terminal = await _wait_for_terminal(harness, timeout=240.0)
        assert terminal is not None, (
            "Graph did not reach a terminal state after RUN_CREWAI_CLI"
        )

        assert terminal in {"completed", "failed", "cancelled"}

        # 6. Sanity: the old UPDATE_START_CREWAI_CLI state should not appear.
        for ev in harness.events["state"]:
            payload = ev["data"].get("payload", {})
            assert payload.get("status") != "update_start_crewai_cli"
            assert payload.get("status") != "UPDATE_START_CREWAI_CLI"

    finally:
        await harness.cleanup()
        if container_id:
            await asyncio.get_event_loop().run_in_executor(
                None, _stop_container, container_name
            )
