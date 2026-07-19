"""Integration test for the single-agent worker."""
import asyncio

import pytest
from unittest.mock import patch
from langgraph.checkpoint.memory import MemorySaver

from internal.agents.single_agent.main import SingleAgentWorker
from helpers import (
    ExpectNatsWorkerResponse,
    WorkerTestHarness,
    sendNatsAgentStartMessage,
    sendNatsUserMessage,
)


@pytest.mark.integration
async def test_single_agent_worker_flow(nats_client, run_id, user_id):
    """Single-agent worker publishes ready and responds to a user message.

    Flow:
    1. sendNatsAgentStartMessage(...)     -> agent.control.{run_id}.start
    2. singleWorker.start()               -> subscribes user events,
                                             publishes agent.control.worker.{run_id}.ready
    3. sendNatsUserMessage(testData.input) -> agent.user.{uid}.chat.{run_id}.user.events
    4. ExpectNatsWorkerResponse(testData.output) -> agent.user.{uid}.chat.{run_id}.worker.events
    """
    test_data = {
        "input": {
            "type": "user_input",
            "payload": {"content": "continue"},
        },
        "output": {
            "kind": "chat",
            "event_type": "progress_update",
        },
    }

    harness = WorkerTestHarness(nats_client, run_id, user_id)
    await harness.subscribe()

    singleWorker = SingleAgentWorker(nats_url="nats://localhost:4222", run_id=run_id)
    worker_task = None

    try:
        with patch("internal.workflow.checkpointer.get_checkpointer", return_value=MemorySaver()):
            await sendNatsAgentStartMessage(
                nats_client, run_id, user_id, agent_type="single-agent"
            )
            worker_task = asyncio.create_task(singleWorker.start())
            await sendNatsUserMessage(nats_client, run_id, user_id, test_data["input"])
            response = await ExpectNatsWorkerResponse(harness, test_data["output"])
            assert response["data"]["event_type"] == test_data["output"]["event_type"]
    finally:
        await singleWorker.stop()
        if worker_task and not worker_task.done():
            worker_task.cancel()
        await harness.cleanup()


@pytest.mark.integration
async def test_single_agent_conversation_flow(nats_client, run_id, user_id):
    """Single-agent worker handles multi-turn conversation.

    Flow:
    1. sendNatsAgentStartMessage(...)     -> agent.control.{run_id}.start
    2. singleWorker.start()               -> subscribes user events,
                                             publishes agent.control.worker.{run_id}.ready
    3. sendNatsUserMessage("what is the weather") -> agent.user.{uid}.chat.{run_id}.user.events
    4. ExpectNatsWorkerResponse("progress_update") -> agent.user.{uid}.chat.{run_id}.worker.events
    5. sendNatsUserMessage("thank you") -> agent.user.{uid}.chat.{run_id}.user.events
    6. ExpectNatsWorkerResponse("progress_update") -> agent.user.{uid}.chat.{run_id}.worker.events
    7. sendNatsUserMessage("bye") -> agent.user.{uid}.chat.{run_id}.user.events
    8. ExpectNatsWorkerResponse("progress_update") -> agent.user.{uid}.chat.{run_id}.worker.events
    """
    harness = WorkerTestHarness(nats_client, run_id, user_id)
    await harness.subscribe()

    singleWorker = SingleAgentWorker(nats_url="nats://localhost:4222", run_id=run_id)
    worker_task = None

    try:
        with patch("internal.workflow.checkpointer.get_checkpointer", return_value=MemorySaver()):
            await sendNatsAgentStartMessage(
                nats_client, run_id, user_id, agent_type="single-agent"
            )
            worker_task = asyncio.create_task(singleWorker.start())

            # First message: weather query
            await sendNatsUserMessage(
                nats_client, run_id, user_id,
                {"type": "user_input", "payload": {"content": "what is the weather"}}
            )
            response1 = await ExpectNatsWorkerResponse(
                harness, {"kind": "chat", "event_type": "progress_update"}
            )
            assert response1["data"]["event_type"] == "progress_update"

            # Second message: thank you
            await sendNatsUserMessage(
                nats_client, run_id, user_id,
                {"type": "user_input", "payload": {"content": "thank you"}}
            )
            response2 = await ExpectNatsWorkerResponse(
                harness, {"kind": "chat", "event_type": "progress_update"}
            )
            assert response2["data"]["event_type"] == "progress_update"

            # Third message: bye
            await sendNatsUserMessage(
                nats_client, run_id, user_id,
                {"type": "user_input", "payload": {"content": "bye"}}
            )
            response3 = await ExpectNatsWorkerResponse(
                harness, {"kind": "chat", "event_type": "progress_update"}
            )
            assert response3["data"]["event_type"] == "progress_update"
    finally:
        await singleWorker.stop()
        if worker_task and not worker_task.done():
            worker_task.cancel()
        await harness.cleanup()
