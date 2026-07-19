"""Typed Pydantic models for the CrewAI expert worker."""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Optional


class ProjectCandidate(BaseModel):
    id: str
    name: str
    relative_path: str
    absolute_path: str
    detected_command: Optional[str] = None


class DependencyIssue(BaseModel):
    code: str
    message: str
    file_path: Optional[str] = None
    patchable: bool = False


class DependencyReport(BaseModel):
    compatible: bool
    patch_required: bool
    patchable: bool
    issues: list[DependencyIssue] = Field(default_factory=list)
    detected_versions: dict[str, str] = Field(default_factory=dict)
    recommended_changes: list[str] = Field(default_factory=list)
    patch_plan_fingerprint: Optional[str] = None


class PatchResult(BaseModel):
    success: bool
    patched_files: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: Optional[str] = None
    patch_plan_fingerprint: str


class CommandSpec(BaseModel):
    argv: list[str]
    cwd: str
    env: dict[str, str] = Field(default_factory=dict)
    display: str
    source: str


class ProcessResult(BaseModel):
    exit_code: int
    cancelled: bool
    timed_out: bool
    stdout_tail: str
    stderr_tail: str
