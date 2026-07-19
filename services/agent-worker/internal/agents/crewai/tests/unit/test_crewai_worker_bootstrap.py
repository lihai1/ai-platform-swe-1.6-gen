"""Unit tests for CrewAI worker startup scan behavior."""

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from agent_worker.bootstrap import is_runnable_folder
from agent_worker.main import CrewAIWorker


def _make_crewai_project(workspace: Path, name: str) -> Path:
    """Create a minimal CrewAI project under workspace for testing."""
    project = workspace / name
    project.mkdir()
    pyproject = project / "pyproject.toml"
    pyproject.write_text('[project]\nname = "sample"\ndependencies = ["crewai"]\n')
    (project / "main.py").write_text("print('hello')")
    return project


def _set_required_env(workspace: Path, monkeypatch) -> str:
    """Set environment variables required by WorkerConfig."""
    run_id = f"test-run-{uuid.uuid4().hex[:8]}"
    monkeypatch.setenv("USER_ID", "test-user")
    monkeypatch.setenv("RUN_ID", run_id)
    monkeypatch.setenv("NATS_URL", "nats://localhost:4222")
    monkeypatch.setenv("AGENT_FOLDER", str(workspace))
    monkeypatch.setenv("WORKSPACE_PATH", str(workspace))
    monkeypatch.delenv("AGENT_EXAMPLE", raising=False)
    monkeypatch.delenv("AGENT_COMMAND", raising=False)
    return run_id


def describe_crewai_worker_bootstrap():
    """Regression tests for the scan-first startup flow."""

    async def test_is_runnable_folder_rejects_stray_python_files(tmp_path):
        """A directory with only a stray app.py should not look runnable."""
        (tmp_path / "app.py").write_text("print('stray')")
        assert is_runnable_folder(tmp_path) is False

        (tmp_path / "main.py").write_text("print('main')")
        assert is_runnable_folder(tmp_path) is True

    async def test_worker_scans_projects_and_waits_for_selection(tmp_path, monkeypatch):
        """Startup without AGENT_EXAMPLE publishes the project list and waits."""
        workspace = tmp_path
        run_id = _set_required_env(workspace, monkeypatch)
        monkeypatch.setattr(sys, "argv", ["test"])

        # Stray Python file at workspace root should not be treated as a project.
        (workspace / "app.py").write_text("print('stray')")
        project = _make_crewai_project(workspace, "sample_crew")

        worker = CrewAIWorker()
        worker.nats = AsyncMock()

        with patch("agent_worker.bootstrap.WORKSPACE_ROOT", workspace), \
             patch("agent_worker.main.WORKSPACE_ROOT", workspace):
            await worker._scan_for_project_selection()

        assert worker._awaiting_project_selection is True
        worker.nats.publish_chat.assert_awaited_once()

        call_args = worker.nats.publish_chat.call_args
        assert call_args.args[0] == "final_answer"
        payload = call_args.args[1]
        assert payload["status"] == "project_selection_required"
        assert payload["error"] is False
        assert len(payload["projects"]) == 1
        assert payload["projects"][0]["name"] == "sample_crew"

    async def test_worker_starts_project_after_user_selection(tmp_path, monkeypatch):
        """A user event with the selected project path starts the runner."""
        workspace = tmp_path
        run_id = _set_required_env(workspace, monkeypatch)
        monkeypatch.setattr(sys, "argv", ["test"])

        project = _make_crewai_project(workspace, "sample_crew")

        worker = CrewAIWorker()
        worker.nats = AsyncMock()
        worker._awaiting_project_selection = True

        user_event = {
            "type": "user_input",
            "payload": {"input": "sample_crew"},
        }

        with patch("agent_worker.bootstrap.WORKSPACE_ROOT", workspace), \
             patch("agent_worker.main.WORKSPACE_ROOT", workspace), \
             patch("agent_worker.main.ProcessRunner") as mock_runner, \
             patch("agent_worker.main.detect_command", return_value="python main.py"):
            mock_runner.return_value = AsyncMock()
            await worker._handle_user_event(user_event)

        assert worker._awaiting_project_selection is False
        assert worker._resolved_folder == project
        assert worker._command == "python main.py"

        mock_runner.assert_called_once()
        call_kwargs = mock_runner.call_args.kwargs
        assert call_kwargs["cwd"] == project
        mock_runner.return_value.run.assert_awaited_once()
