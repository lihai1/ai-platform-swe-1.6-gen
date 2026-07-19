"""LangGraph node implementations for the CrewAI expert worker."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from agent_worker.events import (
    chat_final,
    state_cancelled,
    state_completed,
    state_failed,
    state_output,
    state_waiting_input,
)
from agent_worker.runner import ProcessRunner
from crewai_expert.approvals import (
    prepare_patch_approval,
    prepare_project_selection_approval,
    request_patch_approval,
    request_project_selection,
    validate_patch_approval,
    validate_project_selection,
)
from crewai_expert.config import ExpertConfig
from crewai_expert.dependency_tools import inspect_dependencies, sync_dependencies, verify_project
from crewai_expert.models import CommandSpec
from crewai_expert.patch_tools import apply_patch
from crewai_expert.project_tools import resolve_command_spec, resolve_project, summarize_project
from crewai_expert.state import ExpertStatus

logger = logging.getLogger(__name__)


async def created_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Initial graph node."""
    logger.info("[created_node] status -> RESOLVE_PROJECT")
    return {"status": ExpertStatus.RESOLVE_PROJECT.value}


async def resolve_project_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Resolve a runnable project or surface multiple candidates for approval."""
    logger.info("[resolve_project_node] workspace=%s", state.get("workspace_path") or str(cfg.workspace_path))
    workspace = Path(state.get("workspace_path") or str(cfg.workspace_path))
    resolved, candidates = resolve_project(
        workspace,
        state.get("requested_project_path") or cfg.command,
        cfg,
    )

    if resolved:
        logger.info("[resolve_project_node] resolved=%s", resolved)
        return {
            "resolved_folder": resolved,
            "selected_project": resolved,
            "projects": None,
            "status": ExpertStatus.SUMMARIZE_PROJECT.value,
            "error_message": None,
            "error_code": None,
        }

    if candidates:
        logger.info("[resolve_project_node] candidates=%s", [c.name for c in candidates])
        approval = prepare_project_selection_approval(state, candidates)
        return {
            "projects": approval["projects"],
            **approval,
            "selection_attempts": state.get("selection_attempts", 0),
            "max_selection_attempts": state.get(
                "max_selection_attempts", cfg.max_selection_attempts
            ),
            "status": ExpertStatus.PREPARE_PROJECT_SELECTION.value,
        }

    logger.error("[resolve_project_node] no runnable project found")
    return {
        "status": ExpertStatus.FAILED.value,
        "error_code": "no_runnable_project",
        "error_message": "No runnable CrewAI project found in workspace",
    }


async def prepare_project_selection_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Transition to waiting for project selection."""
    logger.info("[prepare_project_selection_node] status -> WAITING_PROJECT_SELECTION")
    return {"status": ExpertStatus.WAITING_PROJECT_SELECTION.value}


async def waiting_project_selection_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Publish the selection request and block on user input."""
    logger.info("[waiting_project_selection_node] publishing selection request")
    payload = {
        "approval_type": "project_selection",
        "approval_request_id": state.get("approval_request_id"),
        "message": "Multiple CrewAI projects found. Please select one.",
        "options": [c.get("name") or c.get("id") for c in state.get("projects") or []],
    }
    await nats.publish_state(
        "waiting_input",
        state_waiting_input(
            nats.run_id,
            nats.uid,
            prompt=json.dumps(payload),
            reason="project_selection",
        )["payload"],
    )
    logger.info("[waiting_project_selection_node] waiting for user selection")
    result = request_project_selection(state)
    logger.info("[waiting_project_selection_node] selection result=%s", result)
    return result


async def receive_project_selection_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Validate the resumed project selection value."""
    logger.info("[receive_project_selection_node] decision=%s", state.get("approval_decision"))
    workspace = Path(state.get("workspace_path") or str(cfg.workspace_path))
    return validate_project_selection(state, workspace)


async def summarize_project_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Summarize the selected project and derive the run command."""
    logger.info("[summarize_project_node] folder=%s", state.get("selected_project"))
    folder = Path(state["selected_project"])
    command_spec = resolve_command_spec(folder, cfg.command, cfg)
    summary = summarize_project(folder, command_spec)
    logger.info("[summarize_project_node] summary=%s", summary)

    await nats.publish_state(
        "output",
        state_output(nats.run_id, nats.uid, data=summary["description"], stream="stdout")[
            "payload"
        ],
    )
    await nats.publish_chat(
        "progress_update",
        {
            "message": f"Selected project: {folder.name}\nCommand: {command_spec.display}",
            "project_summary": summary,
        },
    )

    return {
        "project_summary": summary,
        "command_spec": command_spec.model_dump(),
        "status": ExpertStatus.INSPECT_DEPENDENCIES.value,
    }


async def inspect_dependencies_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Inspect project dependencies and decide whether patching is needed."""
    logger.info("[inspect_dependencies_node] folder=%s", state.get("selected_project"))
    folder = Path(state["selected_project"])
    report = inspect_dependencies(folder, cfg)
    logger.info("[inspect_dependencies_node] report=%s", report.model_dump())

    await nats.publish_state(
        "output",
        state_output(
            nats.run_id,
            nats.uid,
            data=f"Dependency check: compatible={report.compatible}, patch_required={report.patch_required}",
            stream="stdout",
        )["payload"],
    )

    if not report.compatible and not report.patchable:
        logger.error("[inspect_dependencies_node] unresolvable dependency issues")
        return {
            "dependency_report": report.model_dump(),
            "status": ExpertStatus.FAILED.value,
            "error_code": "unsupported_dependencies",
            "error_message": "Project has unresolvable dependency issues",
        }

    if report.patch_required:
        logger.info("[inspect_dependencies_node] patch required, repair=%s", cfg.repair)
        if not cfg.repair:
            return {
                "dependency_report": report.model_dump(),
                "status": ExpertStatus.FAILED.value,
                "error_code": "patch_required_but_disabled",
                "error_message": "Project requires patches but repair is disabled",
            }
        if cfg.require_patch_approval:
            logger.info("[inspect_dependencies_node] preparing patch approval")
            approval = prepare_patch_approval(state, report)
            return {
                "dependency_report": report.model_dump(),
                **approval,
                "status": ExpertStatus.PREPARE_PATCH_APPROVAL.value,
            }
        logger.info("[inspect_dependencies_node] patching without approval")
        return {
            "dependency_report": report.model_dump(),
            "patch_plan_fingerprint": report.patch_plan_fingerprint,
            "status": ExpertStatus.PATCH_DEPENDENCIES.value,
        }

    logger.info("[inspect_dependencies_node] compatible, proceeding to sync")
    return {
        "dependency_report": report.model_dump(),
        "status": ExpertStatus.SYNC_DEPENDENCIES.value,
    }


async def prepare_patch_approval_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Transition to waiting for patch approval."""
    logger.info("[prepare_patch_approval_node] status -> WAITING_PATCH_APPROVAL")
    return {"status": ExpertStatus.WAITING_PATCH_APPROVAL.value}


async def waiting_patch_approval_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Publish the patch approval request and block on user input."""
    logger.info("[waiting_patch_approval_node] publishing patch approval request")
    report = state.get("dependency_report") or {}
    payload = {
        "approval_type": "patch_approval",
        "approval_request_id": state.get("approval_request_id"),
        "message": "The project requires compatibility patches before it can run.",
        "summary": report.get("recommended_changes", []),
        "affected_files_count": len(report.get("issues") or []),
        "options": ["approved", "rejected"],
    }
    await nats.publish_state(
        "waiting_input",
        state_waiting_input(
            nats.run_id,
            nats.uid,
            prompt=json.dumps(payload),
            reason="patch_approval",
        )["payload"],
    )
    logger.info("[waiting_patch_approval_node] waiting for patch approval")
    result = request_patch_approval(state)
    logger.info("[waiting_patch_approval_node] patch approval result=%s", result)
    return result


async def receive_patch_approval_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Validate the resumed patch approval decision."""
    logger.info("[receive_patch_approval_node] decision=%s", state.get("approval_decision"))
    return validate_patch_approval(state)


async def patch_dependencies_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Apply compatibility patches to the project."""
    logger.info("[patch_dependencies_node] folder=%s fingerprint=%s", state.get("selected_project"), state.get("patch_plan_fingerprint"))
    folder = Path(state["selected_project"])
    fingerprint = state.get("patch_plan_fingerprint") or "default"
    result = await apply_patch(folder, fingerprint, cfg)
    logger.info("[patch_dependencies_node] result=%s", result.model_dump())

    await nats.publish_state(
        "output",
        state_output(
            nats.run_id,
            nats.uid,
            data=f"Patched {len(result.patched_files)} files",
            stream="stdout",
        )["payload"],
    )

    if not result.success:
        logger.error("[patch_dependencies_node] patch failed: %s", result.error)
        return {
            "patch_result": result.model_dump(),
            "status": ExpertStatus.FAILED.value,
            "error_code": "patch_failed",
            "error_message": result.error or "Patching failed",
        }

    logger.info("[patch_dependencies_node] patch succeeded, proceeding to sync")
    return {
        "patch_result": result.model_dump(),
        "patch_attempts": state.get("patch_attempts", 0) + 1,
        "status": ExpertStatus.SYNC_DEPENDENCIES.value,
    }


async def sync_dependencies_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Install project-local dependencies with uv."""
    logger.info("[sync_dependencies_node] folder=%s", state.get("selected_project"))
    folder = Path(state["selected_project"])
    rc, stdout, stderr = await sync_dependencies(folder, cfg)
    logger.info("[sync_dependencies_node] rc=%s stdout_len=%s stderr_len=%s", rc, len(stdout or ""), len(stderr or ""))

    await nats.publish_state(
        "output",
        state_output(
            nats.run_id,
            nats.uid,
            data=f"uv sync exit code: {rc}\n{stderr}",
            stream="stdout",
        )["payload"],
    )

    if rc != 0:
        logger.error("[sync_dependencies_node] sync failed rc=%s", rc)
        return {
            "sync_succeeded": False,
            "status": ExpertStatus.FAILED.value,
            "error_code": "sync_failed",
            "error_message": f"Dependency synchronization failed: {stderr}",
            "stderr_tail": stderr,
        }

    logger.info("[sync_dependencies_node] sync succeeded, proceeding to verify")
    return {"sync_succeeded": True, "status": ExpertStatus.VERIFY_PROJECT.value}


async def verify_project_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Compile, import, and smoke-test the CLI. Re-inspect if a new patchable issue appears."""
    logger.info("[verify_project_node] folder=%s", state.get("selected_project"))
    folder = Path(state["selected_project"])
    command_spec = CommandSpec.model_validate(state.get("command_spec") or {})
    verification = await verify_project(folder, command_spec, cfg)
    logger.info("[verify_project_node] verification=%s", verification)

    await nats.publish_state(
        "output",
        state_output(
            nats.run_id,
            nats.uid,
            data=f"Verification: compile={verification['compile']['ok']}, import={verification['import_test']['ok']}, cli_help={verification['cli_help']['ok']}",
            stream="stdout",
        )["payload"],
    )

    compile_ok = verification["compile"]["ok"]
    import_ok = verification["import_test"]["ok"]
    cli_help_ok = verification["cli_help"]["ok"]

    # Compile and import are required; CLI --help is a best-effort smoke test
    # because many real-world project scripts do not expose --help.
    if compile_ok and import_ok:
        logger.info("[verify_project_node] compile/import ok, cli_help=%s", cli_help_ok)
        return {
            "verify_succeeded": cli_help_ok,
            "verify_error": (
                None
                if cli_help_ok
                else verification["cli_help"].get("stderr", "cli_help failed")
            ),
            "status": ExpertStatus.RUN_CREWAI_CLI.value,
        }

    # Re-inspect to detect new patchable issues after dependency sync.
    report = inspect_dependencies(folder, cfg)
    current_fingerprint = report.patch_plan_fingerprint
    previous_fingerprint = state.get("patch_plan_fingerprint")
    attempts = state.get("patch_attempts", 0)

    if (
        report.patchable
        and current_fingerprint
        and current_fingerprint != previous_fingerprint
        and attempts < state.get("max_patch_attempts", cfg.max_patch_attempts)
    ):
        logger.info("[verify_project_node] re-inspecting dependencies (attempt=%s)", attempts)
        return {
            "dependency_report": report.model_dump(),
            "patch_plan_fingerprint": current_fingerprint,
            "patch_required": True,
            "status": ExpertStatus.INSPECT_DEPENDENCIES.value,
        }

    errors = []
    for key, value in verification.items():
        if not value.get("ok"):
            errors.append(f"{key}: {value.get('error') or value.get('stderr', '')}")
    logger.error("[verify_project_node] verification failed: %s", errors)
    return {
        "verify_succeeded": False,
        "verify_error": "; ".join(errors),
        "status": ExpertStatus.FAILED.value,
        "error_code": "verify_failed",
        "error_message": "Project verification failed: " + "; ".join(errors),
    }


async def run_crewai_cli_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Execute the CrewAI CLI through the existing ProcessRunner."""
    logger.info("[run_crewai_cli_node] command_spec=%s", state.get("command_spec"))
    command_spec = CommandSpec.model_validate(state.get("command_spec") or {})
    env = os.environ.copy()
    env["OLLAMA_BASE_URL"] = cfg.ollama_url
    env["OLLAMA_MODEL"] = cfg.ollama_model
    if command_spec.env:
        env.update(command_spec.env)

    runner = ProcessRunner(
        nats=nats,
        command=command_spec.display,
        command_args=command_spec.argv,
        cwd=Path(command_spec.cwd),
        input_idle_seconds=cfg.input_idle_seconds,
        output_max_buffer_chars=cfg.output_max_buffer_chars,
        command_timeout=cfg.command_timeout_seconds,
        env=env,
        cancel_event=cfg.cancel_event,
    )
    cfg.active_runner = runner

    try:
        result = await runner.run()
    finally:
        cfg.active_runner = None

    logger.info("[run_crewai_cli_node] process result=%s", result)
    state["stdout_tail"] = result.stdout_tail
    state["stderr_tail"] = result.stderr_tail
    state["exit_code"] = result.exit_code

    if result.cancelled:
        logger.info("[run_crewai_cli_node] cancelled")
        state["status"] = ExpertStatus.CANCELLED.value
    elif result.timed_out or result.exit_code != 0:
        logger.error("[run_crewai_cli_node] failed exit_code=%s timed_out=%s", result.exit_code, result.timed_out)
        state["status"] = ExpertStatus.FAILED.value
        state["error_message"] = f"CrewAI CLI exited with code {result.exit_code}"
        if result.timed_out:
            state["error_message"] = f"CrewAI CLI timed out: {result.exit_code}"
    else:
        logger.info("[run_crewai_cli_node] completed")
        state["status"] = ExpertStatus.COMPLETED.value

    return state


async def completed_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Publish final completed state if ProcessRunner has not already done so."""
    logger.info("[completed_node]")
    if state.get("exit_code") is not None:
        # ProcessRunner already published completed/final_answer for CLI success.
        return state

    await nats.publish_state(
        "completed",
        state_completed(nats.run_id, nats.uid, exit_code=0)["payload"],
    )
    await nats.publish_chat(
        "final_answer",
        chat_final(
            nats.run_id,
            nats.uid,
            content="CrewAI expert run completed.",
            status="completed",
        )["payload"],
    )
    return state


async def failed_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Publish final failed state if ProcessRunner has not already done so."""
    logger.error("[failed_node] error=%s", state.get("error_message"))
    if state.get("exit_code") is not None:
        # ProcessRunner already published failed/final_answer for CLI failure.
        return state

    error = state.get("error_message") or "CrewAI expert run failed"
    await nats.publish_state(
        "failed",
        state_failed(
            nats.run_id,
            nats.uid,
            error=error,
            reason=state.get("error_code") or "graph_error",
        )["payload"],
    )
    await nats.publish_chat(
        "final_answer",
        chat_final(
            nats.run_id,
            nats.uid,
            content=error,
            status="failed",
            error=True,
        )["payload"],
    )
    return state


async def cancelled_node(state: dict, nats: Any, cfg: ExpertConfig) -> dict:
    """Publish final cancelled state if ProcessRunner has not already done so."""
    logger.info("[cancelled_node]")
    if state.get("exit_code") is not None:
        # ProcessRunner already published cancelled/final_answer for CLI cancellation.
        return state

    error = state.get("error_message") or "CrewAI expert run was cancelled"
    await nats.publish_state(
        "cancelled",
        state_cancelled(nats.run_id, nats.uid, reason="user_cancelled")["payload"],
    )
    await nats.publish_chat(
        "final_answer",
        chat_final(
            nats.run_id,
            nats.uid,
            content=error,
            status="cancelled",
            error=True,
        )["payload"],
    )
    return state
