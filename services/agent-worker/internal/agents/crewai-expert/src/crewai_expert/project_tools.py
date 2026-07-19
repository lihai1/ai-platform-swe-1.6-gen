"""Project resolution, summarization, and command derivation for CrewAI projects."""

from __future__ import annotations

import logging
import re
import shlex
import tomllib
from pathlib import Path
from typing import Any, Optional

from agent_worker.bootstrap import (
    ensure_inside_workspace,
    find_crewai_projects_recursive,
    is_runnable_folder,
    read_pyproject_entrypoint,
)
from crewai_expert.config import ExpertConfig
from crewai_expert.models import CommandSpec, ProjectCandidate
from final_patch_crewai import detect_package_name, is_src_layout

logger = logging.getLogger(__name__)


def resolve_project(
    workspace: Path,
    requested_project_path: Optional[str],
    config: ExpertConfig,
) -> tuple[Optional[str], list[ProjectCandidate]]:
    """Resolve a single runnable project or a list of candidates under the workspace."""
    logger.info("[resolve_project] workspace=%s requested=%s", workspace, requested_project_path)
    if requested_project_path:
        try:
            resolved = ensure_inside_workspace(workspace / requested_project_path)
            if is_runnable_folder(resolved):
                logger.info("[resolve_project] found requested project=%s", resolved)
                return str(resolved), []
        except Exception as exc:
            logger.warning("Requested project path invalid: %s", exc)

    if is_runnable_folder(workspace):
        return str(workspace), []

    raw_projects = find_crewai_projects_recursive(workspace)
    candidates = _to_candidates(raw_projects, workspace)
    logger.info("[resolve_project] found %s candidates", len(candidates))

    if not candidates:
        logger.warning("[resolve_project] no runnable project found")
        return None, []
    if len(candidates) == 1:
        logger.info("[resolve_project] single candidate=%s", candidates[0].absolute_path)
        return candidates[0].absolute_path, []

    return None, candidates


def _to_candidates(raw_projects: list[dict], workspace: Path) -> list[ProjectCandidate]:
    candidates = []
    workspace_resolved = workspace.resolve()
    for p in raw_projects:
        abs_path = Path(p["full_path"]).resolve()
        try:
            rel_path = abs_path.relative_to(workspace_resolved)
        except ValueError:
            rel_path = abs_path.name
        candidates.append(
            ProjectCandidate(
                id=abs_path.name,
                name=p.get("name") or abs_path.name,
                relative_path=str(rel_path),
                absolute_path=str(abs_path),
                detected_command=p.get("main_file"),
            )
        )
    return candidates


def resolve_command_spec(
    folder: Path, user_command: Optional[str], config: ExpertConfig
) -> CommandSpec:
    """Build a safe argv list for running the project."""
    logger.info("[resolve_command_spec] folder=%s user_command=%s", folder, user_command)
    if user_command:
        argv = _safe_split(user_command)
        logger.info("[resolve_command_spec] user argv=%s", argv)
        return CommandSpec(
            argv=argv,
            cwd=str(folder),
            env={},
            display=shlex.join(argv),
            source="user_request",
        )

    if (folder / "pyproject.toml").exists():
        script = read_pyproject_entrypoint(folder)
        if script:
            # Prefer running the package main module directly so it works even when
            # the project has not been installed as an editable package.
            package_name = _safe_detect_package_name(folder)
            main_module = None
            if package_name:
                main_file = (
                    folder / "src" / package_name / "main.py"
                    if is_src_layout(folder)
                    else folder / package_name / "main.py"
                )
                if main_file.exists():
                    main_module = f"{package_name}.main"
            if main_module:
                env: dict[str, str] = {}
                if is_src_layout(folder):
                    env["PYTHONPATH"] = str(folder / "src")
                argv = [config.uv_path, "run", "python", "-m", main_module]
                logger.info("[resolve_command_spec] pyproject main module argv=%s", argv)
                return CommandSpec(
                    argv=argv,
                    cwd=str(folder),
                    env=env,
                    display=shlex.join(argv),
                    source="pyproject_main_module",
                )
            argv = [config.uv_path, "run", script]
            logger.info("[resolve_command_spec] pyproject script argv=%s", argv)
            return CommandSpec(
                argv=argv,
                cwd=str(folder),
                env={},
                display=shlex.join(argv),
                source="pyproject_scripts",
            )
        argv = [config.uv_path, "run", "crewai", "run"]
        logger.info("[resolve_command_spec] default crewai argv=%s", argv)
        return CommandSpec(
            argv=argv,
            cwd=str(folder),
            env={},
            display=shlex.join(argv),
            source="crewai_default",
        )

    main = folder / "main.py"
    src_main = folder / "src" / "main.py"
    python = (
        str(folder / ".venv" / "bin" / "python")
        if (folder / ".venv").exists()
        else "python"
    )
    if main.exists():
        argv = [python, "main.py"]
    elif src_main.exists():
        argv = [python, "src/main.py"]
    else:
        logger.error("[resolve_command_spec] no runnable entrypoint in %s", folder)
        raise ValueError("No runnable entrypoint found")
    logger.info("[resolve_command_spec] main argv=%s", argv)

    return CommandSpec(
        argv=argv,
        cwd=str(folder),
        env={},
        display=shlex.join(argv),
        source="main_file",
    )


def _safe_detect_package_name(folder: Path) -> Optional[str]:
    """Return the package name if detectable, otherwise None."""
    try:
        return detect_package_name(folder)
    except Exception as exc:
        logger.warning("[resolve_command_spec] package name detection failed: %s", exc)
        return None


def _safe_split(command: str) -> list[str]:
    """Split a command into argv, rejecting shell metacharacters."""
    disallowed = {"|", "&", ";", "$", "`", "\n", "\r"}
    if any(op in command for op in disallowed):
        raise ValueError(f"Shell operators are not allowed in command: {command!r}")
    return shlex.split(command)


def summarize_project(folder: Path, command_spec: CommandSpec) -> dict[str, Any]:
    """Produce a structured summary of a CrewAI project."""
    logger.info("[summarize_project] folder=%s", folder)
    readme = _read_readme(folder)
    pyproject = _read_pyproject(folder)
    detected = _detect_crewai_elements(folder)
    logger.info("[summarize_project] detected agents=%s tasks=%s", detected["agents"], detected["tasks"])

    return {
        "project_name": folder.name,
        "description": pyproject.get("description") or readme.get("first_line", ""),
        "installation": pyproject.get("installation", ""),
        "usage": pyproject.get("usage", ""),
        "command": command_spec.display,
        "required_env_vars": _extract_env_vars(folder),
        "detected_agents": detected["agents"],
        "detected_tasks": detected["tasks"],
    }


def _read_pyproject(folder: Path) -> dict:
    path = folder / "pyproject.toml"
    if not path.exists():
        return {}
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}
    project = data.get("project", {})
    return {
        "name": project.get("name"),
        "description": project.get("description"),
        "scripts": list((project.get("scripts") or {}).keys()),
    }


def _read_readme(folder: Path) -> dict:
    for name in ("README.md", "README.rst", "README.txt"):
        path = folder / name
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
                return {
                    "first_line": text.splitlines()[0].strip().lstrip("# "),
                    "content": text[:4000],
                }
            except Exception:
                pass
    return {}


def _detect_crewai_elements(folder: Path) -> dict[str, list[str]]:
    agents: list[str] = []
    tasks: list[str] = []
    pattern = re.compile(r"@\s*(agent|task|crew)\b")
    for py_file in folder.rglob("*.py"):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        lines = text.splitlines()
        for i, line in enumerate(lines):
            match = pattern.search(line)
            if match:
                # The decorated object usually follows on the next non-empty line.
                kind = match.group(1)
                name_match = None
                for j in range(i + 1, min(i + 5, len(lines))):
                    if lines[j].strip():
                        name_match = re.search(r"def\s+(\w+)", lines[j])
                        break
                if name_match:
                    if kind in ("agent", "crew"):
                        agents.append(name_match.group(1))
                    else:
                        tasks.append(name_match.group(1))
    return {"agents": agents, "tasks": tasks}


def _extract_env_vars(folder: Path) -> list[str]:
    names: set[str] = set()
    pattern = re.compile(r"os\.environ(?:\.get\(|\[)\s*['\"]([A-Z][A-Z0-9_]*)['\"]")
    for py_file in folder.rglob("*.py"):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        try:
            names.update(pattern.findall(py_file.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            pass
    return sorted(names)
