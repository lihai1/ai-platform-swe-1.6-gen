from typing import Any
from chatkit.types import ProgressUpdateEvent


def get_event_type(event: dict[str, Any]) -> str:
    return str(
        event.get("event_type")
        or event.get("type")
        or event.get("name")
        or ""
    )


def is_completed_event(event: dict[str, Any]) -> bool:
    event_type = get_event_type(event)
    return event_type in {
        "agent.completed",
        "agent.run.completed",
        "completed",
        "run.completed",
    }


def is_failed_event(event: dict[str, Any]) -> bool:
    event_type = get_event_type(event)
    return event_type in {
        "agent.failed",
        "agent.run.failed",
        "failed",
        "run.failed",
    }


def is_cancelled_event(event: dict[str, Any]) -> bool:
    event_type = get_event_type(event)
    return event_type in {
        "agent.cancelled",
        "agent.run.cancelled",
        "cancelled",
        "run.cancelled",
    }


def final_answer_from_event(event: dict[str, Any]) -> str:
    return (
        event.get("final_answer")
        or event.get("answer")
        or event.get("content")
        or event.get("message")
        or "Agent run completed."
    )


def progress_from_event(event: dict[str, Any]) -> ProgressUpdateEvent:
    event_type = get_event_type(event)

    if event_type in {"agent.accepted", "accepted", "run.accepted"}:
        return ProgressUpdateEvent(
            icon="check",
            text="Agent run accepted.",
        )

    if event_type in {"agent.scheduled", "scheduled", "run.scheduled"}:
        return ProgressUpdateEvent(
            icon="server",
            text="Agent runner scheduled.",
        )

    if event_type in {"agent.started", "agent.run.started", "started", "run.started"}:
        return ProgressUpdateEvent(
            icon="play",
            text="Agent runner started.",
        )

    if event_type in {"agent.progress", "progress", "run.progress"}:
        return ProgressUpdateEvent(
            icon="agent",
            text=event.get("message", "Agent is working..."),
        )

    if event_type in {"tool.requested", "agent.tool.requested", "agent.run.tool.requested"}:
        return ProgressUpdateEvent(
            icon="wrench",
            text=(
                f"Tool requested: {event.get('tool', 'unknown')} "
                f"on {event.get('resource', 'unknown')}"
            ),
        )

    if event_type in {"tool.allowed", "agent.tool.allowed", "agent.run.tool.allowed"}:
        return ProgressUpdateEvent(
            icon="check",
            text=f"Aegis allowed: {event.get('tool', 'unknown')}",
        )

    if event_type in {"tool.denied", "agent.tool.denied", "agent.run.tool.denied"}:
        return ProgressUpdateEvent(
            icon="shield",
            text=(
                f"Aegis denied: {event.get('tool', 'unknown')}. "
                f"Reason: {event.get('reason', 'policy_denied')}"
            ),
        )

    if event_type in {
        "approval.required",
        "agent.approval.required",
        "agent.run.approval.required",
    }:
        return ProgressUpdateEvent(
            icon="alert-triangle",
            text=(
                f"Approval required: {event.get('action', 'unknown')} "
                f"on {event.get('resource', 'unknown')}"
            ),
        )

    return ProgressUpdateEvent(
        icon="info",
        text=event.get("message", f"Event received: {event_type}"),
    )
