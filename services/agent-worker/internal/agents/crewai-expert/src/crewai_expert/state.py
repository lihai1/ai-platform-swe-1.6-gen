"""LangGraph state and status enum for the CrewAI expert worker."""

from __future__ import annotations

from enum import StrEnum
from typing import Optional, TypedDict


class ExpertStatus(StrEnum):
    CREATED = "created"
    RESOLVE_PROJECT = "resolve_project"
    PREPARE_PROJECT_SELECTION = "prepare_project_selection"
    WAITING_PROJECT_SELECTION = "waiting_project_selection"
    RECEIVE_PROJECT_SELECTION = "receive_project_selection"
    SUMMARIZE_PROJECT = "summarize_project"
    INSPECT_DEPENDENCIES = "inspect_dependencies"
    PREPARE_PATCH_APPROVAL = "prepare_patch_approval"
    WAITING_PATCH_APPROVAL = "waiting_patch_approval"
    RECEIVE_PATCH_APPROVAL = "receive_patch_approval"
    PATCH_DEPENDENCIES = "patch_dependencies"
    SYNC_DEPENDENCIES = "sync_dependencies"
    VERIFY_PROJECT = "verify_project"
    RUN_CREWAI_CLI = "run_crewai_cli"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExpertState(TypedDict, total=False):
    run_id: str
    user_id: str
    workspace_path: str
    requested_project_path: Optional[str]
    resolved_folder: Optional[str]

    projects: Optional[list[dict]]
    selected_project: Optional[str]
    selection_attempts: int
    max_selection_attempts: int

    project_summary: Optional[dict]

    approval_request_id: Optional[str]
    approval_type: Optional[str]
    allowed_approval_values: Optional[list[str]]
    approval_decision: Optional[str]

    dependency_report: Optional[dict]

    patch_required: bool
    patch_approved: bool
    patch_plan_fingerprint: Optional[str]
    patch_attempts: int
    max_patch_attempts: int
    patch_result: Optional[dict]

    command_spec: Optional[dict]

    sync_succeeded: bool
    verify_succeeded: bool
    verify_error: Optional[str]

    cancel_requested: bool

    exit_code: Optional[int]
    stdout_tail: Optional[str]
    stderr_tail: Optional[str]

    status: str
    error_code: Optional[str]
    error_message: Optional[str]
