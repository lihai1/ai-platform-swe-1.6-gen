"""Durable human-in-the-loop approval helpers using LangGraph interrupts."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import Any

from langgraph.types import interrupt

from crewai_expert.models import DependencyReport, ProjectCandidate

logger = logging.getLogger(__name__)


def prepare_project_selection_approval(
    state: dict, candidates: list[ProjectCandidate]
) -> dict:
    """Prepare a durable project-selection approval request."""
    request_id = str(uuid.uuid4())
    logger.info("[prepare_project_selection_approval] request_id=%s", request_id)
    return {
        "approval_request_id": request_id,
        "approval_type": "project_selection",
        "allowed_approval_values": [c.id for c in candidates],
        "approval_decision": None,
        "projects": [c.model_dump() for c in candidates],
    }


def request_project_selection(state: dict) -> dict:
    """Call LangGraph interrupt() for project selection."""
    request_id = state["approval_request_id"]
    candidates = state.get("projects", [])
    options = [c.get("name") or c.get("id") for c in candidates]
    payload = {
        "approval_type": "project_selection",
        "approval_request_id": request_id,
        "message": "Multiple CrewAI projects found. Please select one.",
        "options": options,
    }
    logger.info("[request_project_selection] interrupt payload options=%s", options)
    decision = interrupt(payload)
    logger.info("[request_project_selection] decision=%s", decision)
    return {"approval_decision": decision}


def _normalize_decision(decision: Any) -> dict:
    """Return a decision dict from a string or dict resume value."""
    if isinstance(decision, dict):
        return decision
    if isinstance(decision, str):
        return {"value": decision.strip()}
    return {}


def validate_project_selection(state: dict, workspace: Path) -> dict:
    """Validate the resumed project selection value."""
    logger.info("[validate_project_selection] decision=%s", state.get("approval_decision"))
    decision = _normalize_decision(state.get("approval_decision"))
    selected_id = decision.get("value") or decision.get("input")
    request_id = state.get("approval_request_id")
    supplied_request_id = decision.get("approval_request_id")

    if supplied_request_id and supplied_request_id != request_id:
        return {
            "status": "waiting_project_selection",
            "error_message": "Approval request ID mismatch",
        }

    allowed = set(state.get("allowed_approval_values") or [])
    if selected_id not in allowed:
        attempts = state.get("selection_attempts", 0) + 1
        if attempts >= state.get("max_selection_attempts", 3):
            return {
                "status": "failed",
                "error_code": "invalid_project_selection",
                "error_message": f"Invalid selection {selected_id!r}; retries exhausted",
                "selection_attempts": attempts,
            }
        return {
            "status": "prepare_project_selection",
            "selection_attempts": attempts,
            "error_message": f"Invalid selection {selected_id!r}; choose from {sorted(allowed)}",
        }

    for candidate in state.get("projects") or []:
        if candidate["id"] == selected_id or candidate["relative_path"] == selected_id:
            logger.info("[validate_project_selection] selected=%s", candidate["absolute_path"])
            return {"selected_project": candidate["absolute_path"], "status": "summarize_project"}

    logger.error("[validate_project_selection] selected_id=%s not found", selected_id)
    return {
        "status": "failed",
        "error_code": "selection_resolution_failed",
        "error_message": "Selected project could not be resolved",
    }


def prepare_patch_approval(state: dict, report: DependencyReport) -> dict:
    """Prepare a durable patch approval request."""
    request_id = str(uuid.uuid4())
    logger.info("[prepare_patch_approval] request_id=%s", request_id)
    return {
        "approval_request_id": request_id,
        "approval_type": "patch_approval",
        "allowed_approval_values": ["approved", "rejected"],
        "approval_decision": None,
        "patch_plan_fingerprint": report.patch_plan_fingerprint,
        "dependency_report": report.model_dump(),
    }


def request_patch_approval(state: dict) -> dict:
    """Call LangGraph interrupt() for patch approval."""
    request_id = state["approval_request_id"]
    report = state.get("dependency_report") or {}
    payload = {
        "approval_type": "patch_approval",
        "approval_request_id": request_id,
        "message": "The project requires compatibility patches before it can run.",
        "summary": report.get("recommended_changes", []),
        "affected_files_count": len(report.get("issues") or []),
        "options": ["approved", "rejected"],
    }
    logger.info("[request_patch_approval] interrupt payload options=%s", payload["options"])
    decision = interrupt(payload)
    logger.info("[request_patch_approval] decision=%s", decision)
    return {"approval_decision": decision}


def validate_patch_approval(state: dict) -> dict:
    """Validate the resumed patch approval decision."""
    logger.info("[validate_patch_approval] decision=%s", state.get("approval_decision"))
    decision = _normalize_decision(state.get("approval_decision"))
    value = decision.get("value") or decision.get("decision")
    request_id = state.get("approval_request_id")
    supplied_request_id = decision.get("approval_request_id")

    if supplied_request_id and supplied_request_id != request_id:
        return {"status": "waiting_patch_approval", "error_message": "Approval request ID mismatch"}

    allowed = set(state.get("allowed_approval_values") or [])
    if value not in allowed:
        logger.error("[validate_patch_approval] invalid value=%s", value)
        return {"status": "waiting_patch_approval", "error_message": f"Invalid decision {value!r}"}

    if value == "rejected":
        logger.info("[validate_patch_approval] rejected")
        return {"status": "cancelled", "error_message": "User rejected the patch"}

    logger.info("[validate_patch_approval] approved")
    return {"status": "patch_dependencies", "patch_approved": True}
