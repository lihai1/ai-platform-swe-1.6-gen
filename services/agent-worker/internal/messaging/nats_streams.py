"""Shared NATS JetStream stream configurations."""
from __future__ import annotations

from typing import List, Dict, Any
from agentic_shared.nats_subjects import (
    CHAT_WILDCARD_SUBJECT,
    CONTROL_WILDCARD_SUBJECT,
    EVENT_WILDCARD_SUBJECT,
    CHAT_ERRORS_SUBJECT,
    STREAM_AGENT_CHAT,
    STREAM_AGENT_CONTROL,
    STREAM_AGENT_EVENTS,
    STREAM_AGENT_ERRORS,
)


def get_default_stream_configs() -> List[Dict[str, Any]]:
    """Get default NATS JetStream stream configurations."""
    return [
        {
            "name": STREAM_AGENT_CHAT,
            "subjects": [CHAT_WILDCARD_SUBJECT],
            "description": "Agent chat stream for user events",
            "retention": "limits",
            "max_age": 86400,
            "storage": "file",
        },
        {
            "name": STREAM_AGENT_CONTROL,
            "subjects": [CONTROL_WILDCARD_SUBJECT],
            "description": "Agent control stream",
            "retention": "limits",
            "max_age": 86400,
            "storage": "file",
        },
        {
            "name": STREAM_AGENT_EVENTS,
            "subjects": [EVENT_WILDCARD_SUBJECT],
            "description": "Agent event stream",
            "retention": "limits",
            "max_age": 86400,
            "storage": "file",
        },
        {
            "name": STREAM_AGENT_ERRORS,
            "subjects": [CHAT_ERRORS_SUBJECT],
            "description": "Agent error stream",
            "retention": "limits",
            "max_age": 86400,
            "storage": "file",
        },
    ]


def get_crewai_stream_configs() -> List[Dict[str, Any]]:
    """Get CrewAI-specific NATS JetStream stream configurations."""
    return [
        {
            "name": STREAM_AGENT_CHAT,
            "subjects": [CHAT_WILDCARD_SUBJECT],
            "description": "Agent chat stream for user events",
            "retention": "limits",
            "max_age": 86400,
            "storage": "file",
        },
        {
            "name": STREAM_AGENT_CONTROL,
            "subjects": [CONTROL_WILDCARD_SUBJECT],
            "description": "Agent control stream",
            "retention": "limits",
            "max_age": 86400,
            "storage": "file",
        },
        {
            "name": STREAM_AGENT_EVENTS,
            "subjects": [EVENT_WILDCARD_SUBJECT],
            "description": "Agent event stream",
            "retention": "limits",
            "max_age": 86400,
            "storage": "file",
        },
    ]
