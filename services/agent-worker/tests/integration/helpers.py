"""Readable helpers for agent-worker integration tests."""
import asyncio
import json
import os
import uuid
from functools import partial
from typing import Any, Dict, Optional

from nats.aio.client import Client as NATSClient
from agentic_shared.nats_subjects import (
    format_control_start,
    format_control_worker_ready,
    format_chat_user_events,
    format_event_state_wildcard,
    format_chat_worker_events,
)


class WorkerTestHarness:
    """Collects NATS events the worker publishes and provides wait helpers."""

    def __init__(self, nc: NATSClient, run_id: str, user_id: str):
        self.nc = nc
        self.run_id = run_id
        self.user_id = user_id
        self.events: Dict[str, list] = {"ready": [], "state": [], "chat": [], "user": []}
        self._subs = []
        self._events = {k: asyncio.Event() for k in self.events}

    async def _handler(self, kind: str, msg):
        try:
            data = json.loads(msg.data.decode())
        except json.JSONDecodeError:
            return
        if data.get("run_id") != self.run_id:
            return
        self.events[kind].append({"subject": msg.subject, "data": data})
        self._events[kind].set()

    async def subscribe(self) -> None:
        """Subscribe to the subjects the worker publishes to.

        - `agent.control.worker.{run_id}.ready` (kind: "ready")
        - `agent.user.{uid}.events.{run_id}.state.>` (kind: "state")
        - `agent.user.{uid}.chat.{run_id}.worker.events` (kind: "chat")
        """
        patterns = [
            ("ready", format_control_worker_ready(self.run_id)),
            ("state", format_event_state_wildcard(self.user_id, self.run_id)),
            ("chat", format_chat_worker_events(self.user_id, self.run_id)),
        ]
        for kind, subject in patterns:
            sub = await self.nc.subscribe(subject, cb=partial(self._handler, kind))
            self._subs.append(sub)

    async def wait_for(self, kind: str, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Wait for any event of the given kind."""
        try:
            await asyncio.wait_for(self._events[kind].wait(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        return self.events[kind][-1] if self.events[kind] else None

    async def cleanup(self) -> None:
        """Unsubscribe from all NATS subjects."""
        for sub in self._subs:
            await sub.unsubscribe()
        self._subs.clear()


async def sendNatsAgentStartMessage(
    nc: NATSClient,
    run_id: str,
    user_id: str,
    task: str = "Write a greeting function and verify it works",
    agent_type: str = "specialist",
    publish_to_nats: bool = True,
) -> None:
    """Set worker environment and optionally publish the start command.

    Publishes to: `agent.control.{run_id}.start`
    The worker itself auto-starts from environment variables. The NATS message
    is consumed by the control-plane; publishing it here is for completeness.
    """
    os.environ.update({
        "RUN_ID": run_id,
        "USER_ID": user_id,
        "TASK": task,
        "PROJECT_ID": "test-project-001",
        "REPOSITORY_ID": "test-repo-001",
        "AGENT_TYPE": agent_type,
        "LLM_PROVIDER": "fake",
        "MODEL_NAME": "test-model",
        "MOCK_MODE": "true",
        "WORKSPACE_PATH": "tests/integration/output",
    })
    if not publish_to_nats:
        return
    payload = {
        "run_id": run_id,
        "user_id": user_id,
        "project_id": "test-project-001",
        "repository_id": "test-repo-001",
        "task": task,
        "mock_mode": True,
        "agent_type": agent_type,
        "llm_provider": "fake",
        "model_name": "test-model",
    }
    await nc.publish(format_control_start(run_id), json.dumps(payload).encode())


async def sendNatsUserMessage(
    nc: NATSClient,
    run_id: str,
    user_id: str,
    test_input: Dict[str, Any],
) -> None:
    """Publish a user event for the worker to consume.

    Publishes to: `agent.user.{uid}.chat.{run_id}.user.events`
    """
    subject = format_chat_user_events(user_id, run_id)
    inner_payload = test_input.get("payload", test_input)
    if isinstance(inner_payload, dict):
        inner_payload = {**inner_payload, "user_id": user_id}

    payload = {
        "message_id": str(uuid.uuid4()),
        "event_type": test_input.get("type", "user_input"),
        "run_id": run_id,
        "payload": inner_payload,
        "timestamp": "2026-07-10T10:19:53.178810",
        "schema_version": "1.0",
    }
    await nc.publish(subject, json.dumps(payload).encode())


async def ExpectNatsWorkerResponse(
    harness: WorkerTestHarness,
    test_output: Dict[str, Any],
    timeout: float = 5.0,
) -> Dict[str, Any]:
    """Wait for the worker to publish the expected response.

    Listens on:
    - `agent.control.worker.{run_id}.ready` (kind: "ready")
    - `agent.user.{uid}.events.{run_id}.state.{event_type}` (kind: "state")
    - `agent.user.{uid}.chat.{run_id}.worker.events` (kind: "chat")
    """
    expected_kind = test_output.get("kind", "chat")
    expected_type = test_output.get("event_type")
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        for ev in harness.events[expected_kind]:
            if not expected_type or ev["data"].get("event_type") == expected_type:
                return ev
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"Expected worker response {test_output!r} not received within {timeout}s"
    )
