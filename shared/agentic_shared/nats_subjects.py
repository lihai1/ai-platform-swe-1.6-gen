"""Shared NATS subject constants for all services."""
from __future__ import annotations


# Control stream subjects
CONTROL_START_SUBJECT_TEMPLATE = "agent.control.{run_id}.start"
CONTROL_CLOSE_SUBJECT_TEMPLATE = "agent.control.{run_id}.close"
CONTROL_RESUME_SUBJECT_TEMPLATE = "agent.control.{run_id}.resume"
CONTROL_WORKER_READY_SUBJECT_TEMPLATE = "agent.control.worker.{run_id}.ready"
CONTROL_WILDCARD_SUBJECT = "agent.control.>"

# Chat stream subjects
CHAT_USER_EVENTS_SUBJECT_TEMPLATE = "agent.user.{uid}.chat.{run_id}.user.events"
CHAT_WORKER_EVENTS_SUBJECT_TEMPLATE = "agent.user.{uid}.chat.{run_id}.worker.events"
CHAT_WILDCARD_SUBJECT = "agent.user.*.chat.>"
CHAT_ERRORS_SUBJECT = "agent.user.*.chat.errors"

# Event stream subjects
EVENT_STATE_SUBJECT_TEMPLATE = "agent.user.{uid}.events.{run_id}.state.{event_type}"
EVENT_STATE_WILDCARD_SUBJECT_TEMPLATE = "agent.user.{uid}.events.{run_id}.state.>"
EVENT_WILDCARD_SUBJECT = "agent.user.*.events.>"

# Stream names
STREAM_AGENT_CHAT = "AGENT_CHAT"
STREAM_AGENT_CONTROL = "AGENT_CONTROL"
STREAM_AGENT_EVENTS = "AGENT_EVENTS"
STREAM_AGENT_ERRORS = "AGENT_ERRORS"


def format_control_start(run_id: str) -> str:
    """Format control start subject."""
    return CONTROL_START_SUBJECT_TEMPLATE.format(run_id=run_id)


def format_control_close(run_id: str) -> str:
    """Format control close subject."""
    return CONTROL_CLOSE_SUBJECT_TEMPLATE.format(run_id=run_id)


def format_control_resume(run_id: str) -> str:
    """Format control resume subject."""
    return CONTROL_RESUME_SUBJECT_TEMPLATE.format(run_id=run_id)


def format_control_worker_ready(run_id: str) -> str:
    """Format control worker ready subject."""
    return CONTROL_WORKER_READY_SUBJECT_TEMPLATE.format(run_id=run_id)


def format_chat_user_events(user_id: str, run_id: str) -> str:
    """Format chat user events subject."""
    return CHAT_USER_EVENTS_SUBJECT_TEMPLATE.format(uid=user_id, run_id=run_id)


def format_chat_worker_events(user_id: str, run_id: str) -> str:
    """Format chat worker events subject."""
    return CHAT_WORKER_EVENTS_SUBJECT_TEMPLATE.format(uid=user_id, run_id=run_id)


def format_event_state(user_id: str, run_id: str, event_type: str) -> str:
    """Format event state subject."""
    return EVENT_STATE_SUBJECT_TEMPLATE.format(uid=user_id, run_id=run_id, event_type=event_type)


def format_event_state_wildcard(user_id: str, run_id: str) -> str:
    """Format event state wildcard subject."""
    return EVENT_STATE_WILDCARD_SUBJECT_TEMPLATE.format(uid=user_id, run_id=run_id)
