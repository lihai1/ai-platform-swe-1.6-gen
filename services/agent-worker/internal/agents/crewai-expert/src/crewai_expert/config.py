"""Runtime configuration for the CrewAI expert worker."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent_worker.config import WorkerConfig


@dataclass
class ExpertConfig:
    nats_url: str
    uid: str
    run_id: str
    session_id: str
    folder: str
    command: Optional[str]
    command_timeout_seconds: Optional[int]
    input_idle_seconds: float
    output_max_buffer_chars: int

    workspace_path: Path
    repair: bool
    require_patch_approval: bool
    max_selection_attempts: int
    max_patch_attempts: int
    ollama_url: str
    ollama_model: str
    uv_path: str
    sync_timeout_seconds: int

    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    active_runner: Optional[Any] = field(default=None, repr=False)

    @classmethod
    def from_base(cls, base: WorkerConfig) -> "ExpertConfig":
        return cls(
            nats_url=base.nats_url,
            uid=base.uid,
            run_id=base.run_id,
            session_id=base.session_id,
            folder=base.folder,
            command=base.command,
            command_timeout_seconds=base.command_timeout_seconds,
            input_idle_seconds=base.input_idle_seconds,
            output_max_buffer_chars=base.output_max_buffer_chars,
            workspace_path=Path(os.getenv("WORKSPACE_PATH", "/workspace")),
            repair=_bool_env("CREWAI_EXPERT_REPAIR", True),
            require_patch_approval=_bool_env("CREWAI_EXPERT_REQUIRE_PATCH_APPROVAL", True),
            max_selection_attempts=int(os.getenv("CREWAI_EXPERT_MAX_SELECTION_ATTEMPTS", "3")),
            max_patch_attempts=int(os.getenv("CREWAI_EXPERT_MAX_PATCH_ATTEMPTS", "2")),
            ollama_url=os.getenv("OLLAMA_BASE_URL", "http://ollama:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3.5:9b"),
            uv_path=os.getenv("CREWAI_EXPERT_UV_PATH", "uv"),
            sync_timeout_seconds=int(os.getenv("CREWAI_EXPERT_SYNC_TIMEOUT_SECONDS", "600")),
        )


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")
