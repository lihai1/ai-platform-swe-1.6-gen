"""NATS message handlers for agent service"""
import ast
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def _normalize_waiting_input_payload(payload: dict) -> dict:
    prompt = payload.get("prompt")
    if not isinstance(prompt, str):
        return payload

    try:
        request = json.loads(prompt)
    except json.JSONDecodeError:
        try:
            request = ast.literal_eval(prompt)
        except (SyntaxError, ValueError):
            return payload

    if not isinstance(request, dict):
        return payload

    return {
        **payload,
        "approval_request_id": request.get("approval_request_id"),
        "approval_type": request.get("approval_type"),
        "description": request.get("message"),
        "message": request.get("message"),
        "options": request.get("options"),
        "affected_files_count": request.get("affected_files_count"),
        "summary": request.get("summary"),
    }


async def handle_agent_state_event(event: dict, push_event_func) -> None:
    """Handle agent state events and push to SSE streams"""
    run_id = event.get("run_id")
    event_type = event.get("event_type")
    payload = event.get("payload", {})
    if event_type == "waiting_input":
        payload = _normalize_waiting_input_payload(payload)

    logger.info(f"Received agent state event for run {run_id}: {event_type}")
    
    # Manage AgentStep lifecycle based on state events
    await _manage_agent_step_lifecycle(run_id, event_type, payload)
    
    # Push to SSE stream queue for real-time delivery
    if run_id:
        await push_event_func(run_id, {
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": event.get("timestamp")
        })
        logger.info(f"Pushed event to SSE stream for run {run_id}")
    
    logger.info(f"Run {run_id} state: {event_type}, payload: {payload}")


async def handle_worker_user_event(event: dict, push_event_func) -> None:
    """Handle worker user events (final answers, progress) from agent.chat.{run_id}.user.events"""
    run_id = event.get("run_id")
    event_type = event.get("event_type")
    payload = event.get("payload", {})
    
    logger.info(f"Received worker user event for run {run_id}: {event_type}, payload: {payload}")
    
    # Push to SSE stream queue for real-time delivery
    if run_id:
        await push_event_func(run_id, {
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": event.get("timestamp")
        })
        logger.info(f"Pushed worker user event to SSE stream for run {run_id}")
    


async def handle_agent_error(event: dict, push_event_func) -> None:
    """Handle error messages from agent-worker"""
    error_type = event.get("error_type")
    error_message = event.get("error_message")
    payload = event.get("payload", {})
    
    logger.error(f"Received agent error: {error_type} - {error_message}")
    
    # Push to SSE stream for real-time delivery (similar to handle_agent_state_event)
    await push_event_func("system", {
        "event_type": "error",
        "error_type": error_type,
        "error_message": error_message,
        "payload": payload,
        "timestamp": event.get("timestamp")
    })
    logger.info("Pushed error event to SSE stream")


async def _manage_agent_step_lifecycle(run_id: str, event_type: str, payload: dict) -> None:
    """Manage AgentStep lifecycle based on state events from agent-worker"""
    from internal.db import AsyncSessionLocal
    from internal.models import AgentStep
    from sqlalchemy import select
    
    # Map event types to phases and agent names
    phase_agent_map = {
        "preparing_workspace": ("PREPARING_WORKSPACE", "workspace-preparer"),
        "scouting": ("SCOUTING", "repo-scout"),
        "planning": ("PLANNING", "skills-lead"),
        "designing": ("DESIGNING", "solution-planner"),
        "implementing": ("IMPLEMENTING", "specialist-agents"),
        "testing": ("TESTING", "test-engineer"),
        "reviewing": ("REVIEWING", "code-reviewer"),
        "verifying": ("VERIFYING", "completion-verifier"),
        "repairing": ("REPAIRING", "repair-agent"),
        "waiting_approval": ("WAITING_APPROVAL", "approval-handler"),
        "waiting_input": ("WAITING_INPUT", "input-handler"),
        "reasoning": ("REASONING", "single-agent"),
    }
    
    if event_type not in phase_agent_map:
        return
    
    phase, agent_name = phase_agent_map[event_type]
    
    async with AsyncSessionLocal() as session:
        # Check if there's an existing step for this phase
        result = await session.execute(
            select(AgentStep).where(
                AgentStep.run_id == run_id,
                AgentStep.phase == phase
            ).order_by(AgentStep.started_at.desc())
        )
        existing_step = result.scalar_one_or_none()
        
        if existing_step and existing_step.status == "started":
            # Complete the existing step
            existing_step.status = "completed"
            existing_step.output_data = payload
            existing_step.completed_at = datetime.now()
            await session.commit()
            logger.info(f"Completed AgentStep for run {run_id}, phase {phase}")
        elif not existing_step:
            # Create a new step
            step = AgentStep(
                run_id=run_id,
                phase=phase,
                agent_name=agent_name,
                status="started",
                input_data=payload,
                started_at=datetime.now()
            )
            session.add(step)
            await session.commit()
            logger.info(f"Created AgentStep for run {run_id}, phase {phase}")


async def handle_worker_ready(event: dict, push_event_func) -> None:
    """Handle worker ready signals and push progress update to SSE streams"""
    run_id = event.get("run_id")
    event_type = event.get("event_type")
    payload = event.get("payload", {})

    logger.info(f"Received worker ready signal for run {run_id}: {event_type}")

    # Push progress update to SSE stream
    if run_id:
        await push_event_func(run_id, {
            "type": "progress_update",
            "icon": "agent",
            "text": f"Agent started: {run_id}"
        })
        logger.info(f"Pushed progress update for worker ready: {run_id}")
