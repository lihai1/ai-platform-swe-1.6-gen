"""Integration test for the specialist worker."""
import asyncio

import pytest
from unittest.mock import patch
from langgraph.checkpoint.memory import MemorySaver

from internal.agents.specialist.main import SpecialistWorker
from helpers import (
    ExpectNatsWorkerResponse,
    WorkerTestHarness,
    sendNatsAgentStartMessage,
    sendNatsUserMessage,
)


@pytest.mark.integration
async def test_specialist_worker_flow(nats_client, run_id, user_id):
    """Specialist worker publishes ready signal.

    Flow:
    1. sendNatsAgentStartMessage(...)     -> agent.control.{run_id}.start
    2. specialistWorker.start()           -> subscribes user events,
                                             publishes agent.control.worker.{run_id}.ready
    3. ExpectNatsWorkerResponse(testData.output) -> agent.control.worker.{run_id}.ready
    """
    test_data = {
        "output": {
            "kind": "ready",
            "event_type": "worker_ready",
        },
    }

    harness = WorkerTestHarness(nats_client, run_id, user_id)
    await harness.subscribe()

    specialistWorker = SpecialistWorker(nats_url="nats://localhost:4222", run_id=run_id)
    worker_task = None
    checkpointer = MemorySaver()

    try:
        with patch("internal.workflow.checkpointer.get_checkpointer", return_value=checkpointer):
            await sendNatsAgentStartMessage(
                nats_client, run_id, user_id, agent_type="specialist"
            )
            worker_task = asyncio.create_task(specialistWorker.start())
            response = await ExpectNatsWorkerResponse(harness, test_data["output"])
            assert response["data"]["event_type"] == test_data["output"]["event_type"]
    finally:
        await specialistWorker.stop()
        if worker_task and not worker_task.done():
            worker_task.cancel()
        await harness.cleanup()
