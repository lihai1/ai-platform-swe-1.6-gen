"""Unit tests for crewai_expert graph and helper functions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from crewai_expert.config import ExpertConfig
from agent_worker import bootstrap as bootstrap_module
from crewai_expert.graph import create_test_expert_graph
from crewai_expert.models import CommandSpec
from crewai_expert.project_tools import resolve_command_spec, resolve_project, summarize_project


def _test_config(tmp_path: Path) -> ExpertConfig:
    return ExpertConfig(
        nats_url="nats://localhost:4222",
        uid="u",
        run_id="r",
        session_id="s",
        folder="",
        command=None,
        command_timeout_seconds=10,
        input_idle_seconds=30,
        output_max_buffer_chars=8000,
        workspace_path=tmp_path,
        repair=False,
        require_patch_approval=False,
        max_selection_attempts=3,
        max_patch_attempts=2,
        ollama_url="http://ollama:11434",
        ollama_model="qwen3.5:9b",
        uv_path="uv",
        sync_timeout_seconds=600,
    )


async def test_resolve_project_single(tmp_path: Path, monkeypatch):
    project = tmp_path / "sample_crew"
    project.mkdir()
    (project / "main.py").write_text("print('hi')")
    (project / "pyproject.toml").write_text(
        '[project]\nname = "sample"\ndependencies = ["crewai"]\n'
    )

    monkeypatch.setattr(bootstrap_module, "WORKSPACE_ROOT", tmp_path)
    config = _test_config(tmp_path)
    resolved, candidates = resolve_project(tmp_path, None, config)
    assert resolved and Path(resolved) == project
    assert not candidates


async def test_resolve_project_multiple(tmp_path: Path, monkeypatch):
    for name in ("crew_a", "crew_b"):
        project = tmp_path / name
        project.mkdir()
        (project / "main.py").write_text("print('hi')")
        (project / "pyproject.toml").write_text(
            f'[project]\nname = "{name}"\ndependencies = ["crewai"]\n'
        )

    monkeypatch.setattr(bootstrap_module, "WORKSPACE_ROOT", tmp_path)
    config = _test_config(tmp_path)
    resolved, candidates = resolve_project(tmp_path, None, config)
    assert resolved is None
    assert len(candidates) == 2


async def test_resolve_command_spec_rejects_shell_operators(tmp_path: Path):
    config = _test_config(tmp_path)
    with pytest.raises(ValueError):
        resolve_command_spec(tmp_path, "python main.py; rm -rf /", config)


async def test_resolve_command_spec_reads_pyproject_script(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "sample"\n[project.scripts]\nrun = "sample.main:main"\n'
    )
    config = _test_config(tmp_path)
    spec = resolve_command_spec(tmp_path, None, config)
    assert spec.argv == ["uv", "run", "run"]


async def test_summarize_project_detects_elements(tmp_path: Path):
    (tmp_path / "main.py").write_text(
        "from crewai import Agent, Task, Crew\n"
        "@agent\ndef a(): pass\n"
        "@task\ndef t(): pass\n"
        "@crew\ndef c(): pass\n"
    )
    (tmp_path / "README.md").write_text("# My Crew\n")
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "mycrew"\ndescription = "A crew"\n'
    )

    spec = CommandSpec(argv=["uv", "run", "crewai", "run"], cwd=str(tmp_path), display="uv run crewai run", source="default")
    summary = summarize_project(tmp_path, spec)
    assert summary["project_name"] == tmp_path.name
    assert "A crew" in summary["description"]
    assert summary["command"] == "uv run crewai run"
    assert "a" in summary["detected_agents"]
    assert "t" in summary["detected_tasks"]


async def test_graph_compiles(tmp_path: Path):
    nats = AsyncMock()
    nats.run_id = "r"
    nats.uid = "u"
    config = _test_config(tmp_path)
    graph = create_test_expert_graph(nats, config)
    assert graph is not None
    assert hasattr(graph, "ainvoke")
