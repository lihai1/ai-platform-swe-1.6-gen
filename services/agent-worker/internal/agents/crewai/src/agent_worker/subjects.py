"""NATS subject template rendering."""
from __future__ import annotations

import os
from dataclasses import dataclass
from agentic_shared.nats_subjects import (
    CONTROL_START_SUBJECT_TEMPLATE,
    CONTROL_CLOSE_SUBJECT_TEMPLATE,
    CONTROL_RESUME_SUBJECT_TEMPLATE,
    CHAT_USER_EVENTS_SUBJECT_TEMPLATE,
    EVENT_STATE_WILDCARD_SUBJECT_TEMPLATE,
    CHAT_WORKER_EVENTS_SUBJECT_TEMPLATE,
)


@dataclass(frozen=True)
class SubjectTemplates:
    """Hold subject templates from environment variables."""

    control_start: str = CONTROL_START_SUBJECT_TEMPLATE
    control_close: str = CONTROL_CLOSE_SUBJECT_TEMPLATE
    control_resume: str = CONTROL_RESUME_SUBJECT_TEMPLATE
    user_events: str = CHAT_USER_EVENTS_SUBJECT_TEMPLATE
    state_events: str = EVENT_STATE_WILDCARD_SUBJECT_TEMPLATE
    chat_events: str = CHAT_WORKER_EVENTS_SUBJECT_TEMPLATE

    @classmethod
    def from_env(cls) -> "SubjectTemplates":
        return cls(
            control_start=os.getenv(
                "CONTROL_START_SUBJECT_TEMPLATE", CONTROL_START_SUBJECT_TEMPLATE
            ),
            control_close=os.getenv(
                "CONTROL_CLOSE_SUBJECT_TEMPLATE", CONTROL_CLOSE_SUBJECT_TEMPLATE
            ),
            control_resume=os.getenv(
                "CONTROL_RESUME_SUBJECT_TEMPLATE", CONTROL_RESUME_SUBJECT_TEMPLATE
            ),
            user_events=os.getenv(
                "USER_EVENTS_SUBJECT_TEMPLATE", CHAT_USER_EVENTS_SUBJECT_TEMPLATE
            ),
            state_events=os.getenv(
                "STATE_EVENTS_SUBJECT_TEMPLATE", EVENT_STATE_WILDCARD_SUBJECT_TEMPLATE
            ),
            chat_events=os.getenv(
                "CHAT_EVENTS_SUBJECT_TEMPLATE", CHAT_WORKER_EVENTS_SUBJECT_TEMPLATE
            ),
        )


@dataclass(frozen=True)
class Subjects:
    """Rendered NATS subjects for a run."""

    control_start: str
    control_close: str
    control_resume: str
    user_events: str
    state_events: str
    chat_events: str

    def state(self, event_type: str) -> str:
        """Render a state event subject."""
        return self.state_events.format(event_type=event_type)

    @classmethod
    def from_templates(cls, templates: SubjectTemplates, uid: str, run_id: str) -> "Subjects":
        return cls(
            control_start=templates.control_start.format(run_id=run_id),
            control_close=templates.control_close.format(run_id=run_id),
            control_resume=templates.control_resume.format(run_id=run_id),
            user_events=templates.user_events.format(uid=uid, run_id=run_id),
            state_events=templates.state_events.format(uid=uid, run_id=run_id),
            chat_events=templates.chat_events.format(uid=uid, run_id=run_id),
        )
