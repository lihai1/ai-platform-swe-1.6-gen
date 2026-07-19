"""Dependency inspection, synchronization, and verification for CrewAI projects."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import tomllib
from pathlib import Path
from typing import Optional

from packaging.requirements import Requirement

from final_patch_crewai import detect_package_name, is_src_layout
from crewai_expert.config import ExpertConfig
from crewai_expert.models import CommandSpec, DependencyIssue, DependencyReport

logger = logging.getLogger(__name__)


def inspect_dependencies(folder: Path, config: ExpertConfig) -> DependencyReport:
    """Inspect a project and produce a dependency/compatibility report."""
    issues: list[DependencyIssue] = []
    detected_versions: dict[str, str] = {}
    recommended_changes: list[str] = []

    pyproject = folder / "pyproject.toml"
    requirements = folder / "requirements.txt"

    if pyproject.exists():
        _inspect_pyproject(pyproject, issues, detected_versions, recommended_changes)
    elif requirements.exists():
        _inspect_requirements(requirements, issues, detected_versions, recommended_changes)
    else:
        issues.append(
            DependencyIssue(
                code="no_dependency_file",
                message="No pyproject.toml or requirements.txt found",
                patchable=True,
            )
        )

    _inspect_layout(folder, issues, recommended_changes)
    _inspect_crewai_pins(folder, issues, detected_versions, recommended_changes)

    patch_required = any(i.patchable for i in issues)
    patchable = any(i.patchable for i in issues)
    compatible = not issues or all(i.patchable for i in issues)

    return DependencyReport(
        compatible=compatible,
        patch_required=patch_required,
        patchable=patchable,
        issues=issues,
        detected_versions=detected_versions,
        recommended_changes=recommended_changes,
        patch_plan_fingerprint=_fingerprint(recommended_changes),
    )


def _inspect_pyproject(
    path: Path,
    issues: list[DependencyIssue],
    detected_versions: dict[str, str],
    recommended_changes: list[str],
) -> None:
    try:
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        issues.append(
            DependencyIssue(code="pyproject_unparseable", message=str(exc), patchable=False)
        )
        return

    project = data.get("project", {})
    for dep in project.get("dependencies", []):
        _check_requirement(dep, issues, detected_versions, recommended_changes)
    requires_python = project.get("requires-python")
    if requires_python and "<3.13" in requires_python:
        issues.append(
            DependencyIssue(
                code="python_version_too_low",
                message=f"requires-python {requires_python} may block crewai>=1.6",
                patchable=True,
            )
        )


def _check_requirement(
    dep: str,
    issues: list[DependencyIssue],
    detected_versions: dict[str, str],
    recommended_changes: list[str],
) -> None:
    try:
        req = Requirement(dep)
    except Exception:
        return
    name = req.name.lower()
    if name == "crewai" and any(str(req.specifier).startswith(op) for op in ("<1", "==0")):
        issues.append(DependencyIssue(code="old_crewai", message=str(dep), patchable=True))
    if name == "crewai-tools" and any(str(req.specifier).startswith(op) for op in ("<1", "==0")):
        issues.append(DependencyIssue(code="old_crewai_tools", message=str(dep), patchable=True))
    detected_versions[name] = str(req.specifier)


def _inspect_layout(folder: Path, issues: list[DependencyIssue], recommended_changes: list[str]) -> None:
    try:
        package = detect_package_name(folder)
        src = is_src_layout(folder)
    except Exception:
        package = None
        src = False
    if not package:
        issues.append(
            DependencyIssue(
                code="missing_package_name",
                message="Could not detect package name",
                patchable=True,
            )
        )
        return
    init = folder / ("src" if src else "") / package / "__init__.py"
    if not init.exists():
        issues.append(
            DependencyIssue(
                code="missing_package_init",
                message=f"Missing {init}",
                file_path=str(init),
                patchable=True,
            )
        )


def _inspect_crewai_pins(
    folder: Path,
    issues: list[DependencyIssue],
    detected_versions: dict[str, str],
    recommended_changes: list[str],
) -> None:
    for py_file in folder.rglob("*.py"):
        if ".venv" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if "from langchain" in text or "import langchain" in text:
            issues.append(
                DependencyIssue(
                    code="langchain_import",
                    message=f"Legacy langchain import in {py_file}",
                    file_path=str(py_file),
                    patchable=True,
                )
            )
        if "verbose=2" in text:
            issues.append(
                DependencyIssue(
                    code="verbose_int",
                    message=f"verbose=2 (int) in {py_file}",
                    file_path=str(py_file),
                    patchable=True,
                )
            )


def _fingerprint(changes: list[str]) -> str:
    return hashlib.sha1("\n".join(sorted(changes)).encode()).hexdigest()[:12]


def _inspect_requirements(
    path: Path,
    issues: list[DependencyIssue],
    detected_versions: dict[str, str],
    recommended_changes: list[str],
) -> None:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            _check_requirement(line, issues, detected_versions, recommended_changes)
    except Exception as exc:
        issues.append(
            DependencyIssue(code="requirements_unparseable", message=str(exc), patchable=False)
        )


async def sync_dependencies(folder: Path, config: ExpertConfig) -> tuple[int, str, str]:
    """Synchronize target project dependencies into a local .venv using uv."""
    logger.info("[sync_dependencies] folder=%s uv_path=%s", folder, config.uv_path)
    if not shutil.which(config.uv_path):
        logger.error("[sync_dependencies] '%s' not found in PATH", config.uv_path)
        return 1, "", f"'{config.uv_path}' not found in PATH"

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["FORCE_COLOR"] = "0"

    if (folder / "pyproject.toml").exists():
        argv = [config.uv_path, "sync", "--no-dev"]
    elif (folder / "requirements.txt").exists():
        venv = folder / ".venv"
        if not venv.exists():
            create_venv = await asyncio.create_subprocess_exec(
                config.uv_path,
                "venv",
                ".venv",
                cwd=str(folder),
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await _communicate_with_timeout(create_venv, config.sync_timeout_seconds or 600)
        argv = [
            config.uv_path,
            "pip",
            "install",
            "--python",
            str(venv / "bin" / "python"),
            "-r",
            "requirements.txt",
        ]
    else:
        return 0, "", "No dependency files found; skipping sync"

    logger.info("[sync_dependencies] running: %s", " ".join(argv))
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(folder),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await _communicate_with_timeout(proc, config.sync_timeout_seconds or 600)
    rc = proc.returncode or 0
    logger.info("[sync_dependencies] rc=%s", rc)
    return rc, _tail(stdout.decode()), _tail(stderr.decode())


async def verify_project(folder: Path, command_spec: CommandSpec, config: ExpertConfig) -> dict:
    """Verify the project compiles, imports, and its CLI supports --help."""
    logger.info("[verify_project] folder=%s command=%s", folder, command_spec.display)
    package_name = detect_package_name(folder)
    src_layout = is_src_layout(folder)
    python = _project_python(folder)
    logger.info("[verify_project] package_name=%s python=%s", package_name, python)

    return {
        "compile": await _run_compile(folder, python, config),
        "import_test": await _run_import(folder, python, package_name, src_layout, config),
        "cli_help": await _run_cli_help(folder, command_spec, config),
    }


def _project_python(folder: Path) -> str:
    venv_bin = folder / ".venv" / "bin" / "python"
    return str(venv_bin) if venv_bin.exists() else "python"


async def _run_compile(folder: Path, python: str, config: ExpertConfig) -> dict:
    # Exclude virtual environments and caches so we only compile project source.
    if shutil.which(python):
        argv = [python, "-m", "compileall", "-q", "-x", r"(\.venv|__pycache__|site-packages)", "."]
    else:
        argv = [config.uv_path, "run", "python", "-m", "compileall", "-q", "-x", r"(\.venv|__pycache__|site-packages)", "."]
    logger.info("[_run_compile] argv=%s", argv)
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(folder),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await _communicate_with_timeout(proc, config.command_timeout_seconds or 60)
    logger.info("[_run_compile] ok=%s rc=%s", proc.returncode == 0, proc.returncode)
    return {
        "ok": proc.returncode == 0,
        "stdout": _tail(stdout.decode()),
        "stderr": _tail(stderr.decode()),
    }


async def _run_import(
    folder: Path,
    python: str,
    package_name: str,
    src_layout: bool,
    config: ExpertConfig,
) -> dict:
    if not package_name:
        return {"ok": True, "skipped": True}
    module = package_name
    if src_layout:
        module = (
            f"{package_name}.main"
            if (folder / "src" / package_name / "main.py").exists()
            else package_name
        )
    elif (folder / "main.py").exists():
        module = "main"
    argv = (
        [python, "-c", f"import {module}"]
        if shutil.which(python)
        else [config.uv_path, "run", "python", "-c", f"import {module}"]
    )
    env = os.environ.copy()
    if src_layout:
        src_path = str(folder / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")
    logger.info("[_run_import] argv=%s module=%s pythonpath=%s", argv, module, env.get("PYTHONPATH"))
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(folder),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await _communicate_with_timeout(proc, config.command_timeout_seconds or 60)
    rc = proc.returncode
    logger.info("[_run_import] ok=%s rc=%s", rc == 0, rc)
    return {"ok": rc == 0, "error": _tail(stderr.decode())}


async def _run_cli_help(folder: Path, command_spec: CommandSpec, config: ExpertConfig) -> dict:
    # Run the resolved entrypoint with --help appended to verify the CLI is importable.
    argv = list(command_spec.argv) + ["--help"]

    env = os.environ.copy()
    env["OLLAMA_BASE_URL"] = config.ollama_url
    env["OLLAMA_MODEL"] = config.ollama_model
    if is_src_layout(folder):
        src_path = str(folder / "src")
        env["PYTHONPATH"] = src_path + os.pathsep + env.get("PYTHONPATH", "")

    local_binary = folder / ".venv" / "bin" / argv[0]
    if local_binary.exists():
        logger.info("[_run_cli_help] local_binary=%s args=%s", local_binary, argv[1:])
        proc = await asyncio.create_subprocess_exec(
            str(local_binary),
            *argv[1:],
            cwd=str(folder),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    else:
        # argv already begins with uv, so execute it directly rather than re-prefixing.
        logger.info("[_run_cli_help] uv args=%s", argv)
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(folder),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    stdout, stderr = await _communicate_with_timeout(proc, config.command_timeout_seconds or 60)
    rc = proc.returncode
    logger.info("[_run_cli_help] ok=%s rc=%s", rc == 0, rc)
    return {"ok": rc == 0, "stderr": _tail(stderr.decode())}


async def _communicate_with_timeout(
    proc: asyncio.subprocess.Process, timeout: Optional[float]
) -> tuple[bytes, bytes]:
    """Wait for a subprocess with an optional timeout; kill it on expiry."""
    if timeout is None or timeout <= 0:
        return await proc.communicate()
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try:
            proc.kill()
            await proc.wait()
        except ProcessLookupError:
            pass
        return b"", f"Subprocess timed out after {timeout}s".encode()


def _tail(text: str, limit: int = 2000) -> str:
    if len(text) <= limit:
        return text
    return "..." + text[-limit:]
