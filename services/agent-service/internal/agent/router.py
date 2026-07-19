"""Future agent API exposed under /api/agent by the agent-service.

This router is intentionally separate from the ChatKit endpoints so it can
house run/approval/event HTTP APIs that the UI already calls through the
/api/agent path. It reuses the existing AgentRun, AgentStep, AgentEvent,
AgentApproval models and the in-memory event_streams queue without changing
any other module.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from internal.db import get_session
from internal.event_streams import get_event_stream
from internal.models import AgentApproval, AgentEvent, AgentRun, AgentStep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/agent", tags=["agent"])

# Event types that should close the SSE stream for the UI.
TERMINAL_EVENT_TYPES = {
    "run_completed",
    "run_failed",
    "run_cancelled",
    "completed",
    "failed",
    "cancelled",
    "budget_exceeded",
    "final_answer",
}


class ApprovalDecision(BaseModel):
    decided_by: Optional[str] = None
    comments: Optional[str] = None


class ApprovalResponse(BaseModel):
    status: str
    run_id: str
    approval_id: str


def _user_id_from_request(request: Request) -> str:
    """Best-effort user identification from headers or query string.

    The chat component uses EventSource with a `token` query parameter and the
    approval endpoint is POSTed without an X-User-Subject header, so we fall
    back to anonymous when the header is missing.
    """
    user_id = request.headers.get("X-User-Subject")
    if not user_id:
        # EventSource is not allowed to set custom headers, but the chat
        # component appends the JWT token as a query parameter.
        token = request.query_params.get("token")
        if token:
            user_id = f"token:{token}"
    return user_id or "anonymous"


def _format_run(run: AgentRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "user_id": run.user_id,
        "project_id": run.project_id,
        "repository_id": run.repository_id,
        "chatkit_thread_id": run.chatkit_thread_id,
        "task": run.task,
        "status": run.status,
        "current_phase": run.current_phase,
        "error_message": run.error_message,
        "cancel_requested_at": run.cancel_requested_at.isoformat() if run.cancel_requested_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "updated_at": run.updated_at.isoformat() if run.updated_at else None,
        "max_tokens": run.max_tokens,
        "tokens_used": run.tokens_used,
        "max_cost": run.max_cost,
        "cost_incurred": run.cost_incurred,
        "repair_count": run.repair_count,
        "max_repair_count": run.max_repair_count,
    }


def _format_step(step: AgentStep) -> dict[str, Any]:
    # The activity panel expects `chat_id` (the run id) to be present.
    return {
        "id": step.id,
        "chat_id": step.run_id,
        "run_id": step.run_id,
        "phase": step.phase,
        "agent_name": step.agent_name,
        "status": step.status,
        "input_data": step.input_data,
        "output_data": step.output_data,
        "error_message": step.error_message,
        "started_at": step.started_at.isoformat() if step.started_at else None,
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
    }


def _format_event(event: AgentEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "chat_id": event.run_id,
        "run_id": event.run_id,
        "step_id": event.step_id,
        "event_type": event.event_type,
        "event_data": event.event_data,
        "sequence_number": event.sequence_number,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }


async def _event_sse_generator(run_id: str) -> AsyncGenerator[str, None]:
    """Yield Server-Sent Events from the in-memory event stream queue."""
    try:
        stream = await get_event_stream(run_id)
    except Exception as e:
        logger.error(f"Failed to get event stream for {run_id}: {e}")
        return

    while True:
        try:
            event = await stream.get()
        except Exception as e:
            logger.error(f"Error reading event stream for {run_id}: {e}")
            break

        event_type = event.get("event_type", "message")
        # Emit all events as the default "message" event type so the UI's
        # EventSource.onmessage handler receives every event and can dispatch
        # based on the event_type field inside the payload.
        sse_payload = f"event: message\ndata: {json.dumps(event)}\n\n"
        yield sse_payload

        if event_type in TERMINAL_EVENT_TYPES:
            break


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """Get a run by ID."""
    result = await session.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return _format_run(run)


@router.get("/runs/{run_id}/steps")
async def get_run_steps(
    run_id: str,
    session: AsyncSession = Depends(get_session),
):
    """List steps for a run."""
    result = await session.execute(
        select(AgentStep).where(AgentStep.run_id == run_id).order_by(AgentStep.started_at)
    )
    return [_format_step(step) for step in result.scalars().all()]


@router.get("/runs/{run_id}/events")
async def get_run_events(
    run_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    last_sequence: Optional[int] = None,
):
    """Stream or list events for a run.

    If the request Accept header is `text/event-stream`, returns an SSE stream
    backed by the in-memory event stream queue. Otherwise returns a JSON list
    of persisted AgentEvent records.
    """
    accept = request.headers.get("accept", "")
    wants_stream = "text/event-stream" in accept

    if wants_stream:
        return StreamingResponse(
            _event_sse_generator(run_id),
            media_type="text/event-stream",
        )

    query = select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(AgentEvent.sequence_number)
    if last_sequence is not None:
        query = query.where(AgentEvent.sequence_number > last_sequence)
    result = await session.execute(query)
    return [_format_event(event) for event in result.scalars().all()]


@router.post("/runs/{run_id}/approvals/{approval_id}/approve")
async def approve_approval(
    run_id: str,
    approval_id: str,
    request: Request,
    decision: ApprovalDecision = ApprovalDecision(),
    session: AsyncSession = Depends(get_session),
):
    """Approve a pending approval for a run."""
    user_id = decision.decided_by or _user_id_from_request(request)
    return await _update_approval(
        run_id=run_id,
        approval_id=approval_id,
        decision="approved",
        decided_by=user_id,
        comments=decision.comments,
        session=session,
    )


@router.post("/runs/{run_id}/approvals/{approval_id}/reject")
async def reject_approval(
    run_id: str,
    approval_id: str,
    request: Request,
    decision: ApprovalDecision = ApprovalDecision(),
    session: AsyncSession = Depends(get_session),
):
    """Reject a pending approval for a run."""
    user_id = decision.decided_by or _user_id_from_request(request)
    return await _update_approval(
        run_id=run_id,
        approval_id=approval_id,
        decision="rejected",
        decided_by=user_id,
        comments=decision.comments,
        session=session,
    )


async def _update_approval(
    run_id: str,
    approval_id: str,
    decision: str,
    decided_by: str,
    comments: Optional[str],
    session: AsyncSession,
) -> ApprovalResponse:
    """Update the approval decision, creating a placeholder record if needed."""
    run_result = await session.execute(select(AgentRun).where(AgentRun.id == run_id))
    run = run_result.scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    result = await session.execute(
        select(AgentApproval).where(
            AgentApproval.id == approval_id,
            AgentApproval.run_id == run_id,
        )
    )
    approval = result.scalar_one_or_none()

    if approval is None:
        # The worker may not have persisted an AgentApproval row yet. Create a
        # placeholder so the UI can still record the human decision.
        approval = AgentApproval(
            id=approval_id,
            run_id=run_id,
            approval_type="unknown",
            description="Approval created from UI decision",
            decision="pending",
        )
        session.add(approval)

    if approval.decision is not None and approval.decision != "pending":
        raise HTTPException(status_code=400, detail="Approval already decided")

    approval.decision = decision
    approval.decided_by = decided_by
    approval.decided_at = datetime.now(timezone.utc)
    if comments:
        # Store the comment in the existing metadata so no schema changes are needed.
        approval.description = f"{approval.description} | comment: {comments}"

    await session.commit()

    return ApprovalResponse(
        status=decision,
        run_id=run_id,
        approval_id=approval_id,
    )
