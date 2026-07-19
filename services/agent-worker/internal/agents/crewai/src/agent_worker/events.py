"""Event payload builders for the CrewAI worker."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _message_id() -> str:
    return str(uuid.uuid4())


def base_event(
    event_type: str,
    run_id: str,
    payload: dict[str, Any],
    user_id: str,
    session_id: Optional[str] = None,
    message_id: Optional[str] = None,
) -> dict[str, Any]:
    """Build a message using the existing platform envelope."""
    return {
        "message_id": message_id or _message_id(),
        "event_type": event_type,
        "run_id": run_id,
        "payload": payload,
        "timestamp": _now(),
        "schema_version": "1.0",
    }


def state_started(
    run_id: str,
    user_id: str,
    folder: str,
    resolved_folder: str,
    command: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    return base_event(
        event_type="started",
        run_id=run_id,
        payload={
            "status": "started",
            "folder": folder,
            "resolved_folder": resolved_folder,
            "command": command,
        },
        user_id=user_id,
        session_id=session_id,
    )


def state_output(
    run_id: str,
    user_id: str,
    data: str,
    stream: str = "stdout",
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    return base_event(
        event_type="output",
        run_id=run_id,
        payload={
            "status": "output",
            "stream": stream,
            "data": data,
        },
        user_id=user_id,
        session_id=session_id,
    )


def state_waiting_input(
    run_id: str,
    user_id: str,
    prompt: str,
    reason: str = "process_idle",
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    return base_event(
        event_type="waiting_input",
        run_id=run_id,
        payload={
            "status": "waiting_input",
            "reason": reason,
            "prompt": prompt,
        },
        user_id=user_id,
        session_id=session_id,
    )


def state_completed(
    run_id: str,
    user_id: str,
    exit_code: int = 0,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    return base_event(
        event_type="completed",
        run_id=run_id,
        payload={
            "status": "completed",
            "exit_code": exit_code,
        },
        user_id=user_id,
        session_id=session_id,
    )


def state_failed(
    run_id: str,
    user_id: str,
    error: str,
    reason: str = "process_error",
    exit_code: Optional[int] = None,
    candidates: Optional[list[str]] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failed",
        "reason": reason,
        "error": error,
    }
    if exit_code is not None:
        payload["exit_code"] = exit_code
    if candidates is not None:
        payload["candidates"] = candidates
    return base_event(
        event_type="failed",
        run_id=run_id,
        payload=payload,
        user_id=user_id,
        session_id=session_id,
    )


def state_cancelled(
    run_id: str,
    user_id: str,
    reason: str = "control_close_received",
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    return base_event(
        event_type="cancelled",
        run_id=run_id,
        payload={
            "status": "cancelled",
            "reason": reason,
        },
        user_id=user_id,
        session_id=session_id,
    )


def chat_progress(
    run_id: str,
    user_id: str,
    message: str,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    return base_event(
        event_type="progress_update",
        run_id=run_id,
        payload={"message": message},
        user_id=user_id,
        session_id=session_id,
    )


def chat_final(
    run_id: str,
    user_id: str,
    content: str,
    status: str = "completed",
    error: bool = False,
    session_id: Optional[str] = None,
    projects: Optional[list] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "content": content,
        "status": status,
        "error": error,
    }
    if projects is not None:
        payload["projects"] = projects
    return base_event(
        event_type="final_answer",
        run_id=run_id,
        payload=payload,
        user_id=user_id,
        session_id=session_id,
    )
