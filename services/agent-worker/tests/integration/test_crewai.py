"""Integration test for the CrewAI worker."""
import asyncio
from unittest.mock import patch

import pytest

from internal.agents.crewai.src.agent_worker.config import WorkerConfig
from internal.agents.crewai.src.agent_worker.main import CrewAIWorker
from helpers import (
    ExpectNatsWorkerResponse,
    WorkerTestHarness,
    sendNatsAgentStartMessage,
    sendNatsUserMessage,
)


def _crew_config(nats_url: str, user_id: str, run_id: str) -> WorkerConfig:
    return WorkerConfig(
        nats_url=nats_url,
        uid=user_id,
        run_id=run_id,
        session_id=run_id,
        folder="/workspace",
        example=None,
        command=None,
        command_timeout_seconds=None,
        input_idle_seconds=30.0,
        output_max_buffer_chars=8000,
    )



@pytest.mark.integration
async def test_crewai_worker_flow(nats_client, run_id, user_id):
    """CrewAI worker publishes ready and receives a user message.

    Flow:
    1. sendNatsAgentStartMessage(..., publish_to_nats=False) -> sets env
    2. crewAIWorker.start()                 -> subscribes user/control events,
                                               publishes agent.control.worker.{run_id}.ready
    3. sendNatsUserMessage(testData.input)   -> agent.user.{uid}.chat.{run_id}.user.events
    4. ExpectNatsWorkerResponse(testData.output) -> agent.control.worker.{run_id}.ready
    """
    test_data = {
        "input": {
            "type": "user_input",
            "payload": {"content": "continue"},
        },
        "output": {
            "kind": "ready",
            "event_type": "worker_ready",
        },
    }

    harness = WorkerTestHarness(nats_client, run_id, user_id)
    await harness.subscribe()

    nats_url = "nats://localhost:4222"
    crewAIWorker = None
    worker_task = None

    try:
        with patch(
            "internal.agents.crewai.src.agent_worker.main.resolve_config",
            return_value=_crew_config(nats_url, user_id, run_id),
        ):
            crewAIWorker = CrewAIWorker()
            await sendNatsAgentStartMessage(
                nats_client,
                run_id,
                user_id,
                agent_type="crewai",
                publish_to_nats=False,
            )
            worker_task = asyncio.create_task(crewAIWorker.start())

            await sendNatsUserMessage(nats_client, run_id, user_id, test_data["input"])
            response = await ExpectNatsWorkerResponse(harness, test_data["output"])
            assert response["data"]["event_type"] == test_data["output"]["event_type"]
    finally:
        if crewAIWorker is not None:
            await crewAIWorker.stop()
        if worker_task and not worker_task.done():
            worker_task.cancel()
        await harness.cleanup()
