"""Unit tests for ProcessRunner extensions used by the CrewAI expert worker."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from agent_worker.runner import ProcessResult, ProcessRunner


def _fake_nats(run_id: str = "r", uid: str = "u"):
    nats = AsyncMock()
    nats.run_id = run_id
    nats.uid = uid
    return nats


async def test_process_runner_runs_argv_list_and_returns_result(tmp_path: Path):
    nats = _fake_nats()
    runner = ProcessRunner(
        nats=nats,
        command="",
        command_args=[sys.executable, "-c", "print('hello from argv')"],
        cwd=tmp_path,
    )
    result = await runner.run()
    assert result.exit_code == 0
    assert result.cancelled is False
    assert result.timed_out is False
    assert "hello from argv" in result.stdout_tail
    assert nats.publish_state.call_args_list[0].args[0] == "started"


async def test_process_runner_publishes_output_and_completed(tmp_path: Path):
    nats = _fake_nats()
    runner = ProcessRunner(
        nats=nats,
        command="",
        command_args=[sys.executable, "-c", "print('line1'); print('line2')"],
        cwd=tmp_path,
        publish_started=True,
    )
    result = await runner.run()
    assert result.exit_code == 0

    event_types = [call.args[0] for call in nats.publish_state.call_args_list]
    assert "started" in event_types
    assert "output" in event_types
    assert "completed" in event_types


async def test_process_runner_respects_cancel_event(tmp_path: Path):
    nats = _fake_nats()
    cancel_event = asyncio.Event()
    runner = ProcessRunner(
        nats=nats,
        command="",
        command_args=[sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        cancel_event=cancel_event,
    )

    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.3)
    cancel_event.set()
    result = await task

    assert result.cancelled is True
    assert result.exit_code != 0


async def test_process_runner_respects_command_timeout(tmp_path: Path):
    nats = _fake_nats()
    runner = ProcessRunner(
        nats=nats,
        command="",
        command_args=[sys.executable, "-c", "import time; time.sleep(10)"],
        cwd=tmp_path,
        command_timeout=1,
    )
    result = await runner.run()
    assert result.timed_out is True
    assert result.exit_code != 0


async def test_process_runner_propagates_env_variables(tmp_path: Path):
    nats = _fake_nats()
    runner = ProcessRunner(
        nats=nats,
        command="",
        command_args=[sys.executable, "-c", "import os; print(os.environ.get('CREWAI_TEST_VAR'))"],
        cwd=tmp_path,
        env={"CREWAI_TEST_VAR": "42"},
    )
    result = await runner.run()
    assert result.exit_code == 0
    assert "42" in result.stdout_tail


async def test_process_runner_handle_user_input_accepts_payload_wrapper(tmp_path: Path):
    nats = _fake_nats()
    runner = ProcessRunner(
        nats=nats,
        command="",
        command_args=[sys.executable, "-c", "x = input(); print('echo:', x)"],
        cwd=tmp_path,
    )

    task = asyncio.create_task(runner.run())
    await asyncio.sleep(0.3)
    await runner.handle_user_input(
        {"event_type": "user_input", "payload": {"input": "world"}}
    )
    result = await asyncio.wait_for(task, timeout=5)

    assert result.exit_code == 0
    assert "echo: world" in result.stdout_tail


async def test_process_runner_bounded_output_tail(tmp_path: Path):
    nats = _fake_nats()
    runner = ProcessRunner(
        nats=nats,
        command="",
        command_args=[sys.executable, "-c", "print('x' * 5000)"],
        cwd=tmp_path,
    )
    result = await runner.run()
    assert result.exit_code == 0
    assert len(result.stdout_tail) <= 2003  # '...' + 2000 tail chars
