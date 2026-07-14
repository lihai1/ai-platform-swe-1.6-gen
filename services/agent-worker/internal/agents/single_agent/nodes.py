"""Single-agent workflow nodes"""
import asyncio
from datetime import datetime
from typing import Dict, Any
from internal.workflow.state import EngineeringState
from internal.messaging.nats import get_nats_client
from internal.tools.workspace import WorkspaceTools
from .agent import SingleAgent
import logging

logger = logging.getLogger(__name__)


def _workspace_tools(state: EngineeringState) -> WorkspaceTools:
    """Create a WorkspaceTools instance for the current run"""
    return WorkspaceTools(
        run_id=state.get("run_id"),
        user_id=state.get("user_id"),
        workspace_path=state.get("workspace_id") or "/workspace",
    )


async def publish_state_event(run_id: str, user_id: str, event_type: str, payload: dict = None):
    """Publish state change event to NATS"""
    try:
        nats = get_nats_client()
        if nats is None:
            logger.warning("NATS client not available, skipping state event")
            return
        if nats.js is None:
            await nats.connect()
        await nats.publish_event(
            event_type=event_type,
            run_id=run_id,
            user_id=user_id,
            payload=payload or {}
        )
        logger.info(f"Published state event: {event_type} for run {run_id}")
    except Exception as e:
        logger.error(f"Failed to publish state event: {e}")


async def publish_chat_event(run_id: str, user_id: str, event_type: str, payload: dict = None):
    """Publish progress/final event to agent.user.{user_id}.chat.{run_id}.events"""
    try:
        nats = get_nats_client()
        if nats is None:
            logger.warning("NATS client not available, skipping chat event")
            return
        if nats.js is None:
            await nats.connect()

        await nats.publish_chat_event(
            event_type=event_type,
            run_id=run_id,
            user_id=user_id,
            payload=payload or {}
        )
        logger.info(f"Published chat event: {event_type} for run {run_id}")
    except Exception as e:
        logger.error(f"Failed to publish chat event: {e}")


def _pydantic_to_dict(value):
    """Convert a Pydantic model or dict to a plain dict"""
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


async def reasoning_node(state: EngineeringState) -> EngineeringState:
    """Reasoning node for single-agent mode - performs the entire task in one step"""
    state["status"] = "REASONING"
    state["current_phase"] = "REASONING"
    
    await publish_state_event(state["run_id"], state["user_id"], "reasoning", {"status": "REASONING"})

    mock_mode = state.get("mock_mode", False)
    llm_provider = state.get("llm_provider")
    task = state.get("task", "")
    repository_summary = state.get("repository_summary") or {}
    workspace_id = state.get("workspace_id") or "/workspace"
    workspace_tools = _workspace_tools(state)

    logger.info("Using single-agent reasoning mode")

    try:
        agent = SingleAgent(mock_mode=mock_mode, llm_provider=llm_provider or "ollama")
        result = await agent.reason(
            task=task,
            repository_summary=repository_summary,
            workspace_id=workspace_id,
            workspace_tools=workspace_tools,
            run_id=state["run_id"],
        )
        state["reasoning_results"] = _pydantic_to_dict(result)
    except Exception as e:
        logger.error(f"Single-agent reasoning failed: {e}")
        state["reasoning_results"] = {
            "answer": f"Failed to complete task: {str(e)}",
            "success": False,
            "errors": [str(e)],
        }

    # Send completion event with the reasoning result
    reasoning_results = state.get("reasoning_results", {})
    success = reasoning_results.get("success", True)
    
    if success:
        final_text = reasoning_results.get("answer", "Task completed.")
        await publish_chat_event(state["run_id"], state["user_id"], "final_answer", {"content": final_text, "status": "completed"})
    else:
        errors = reasoning_results.get("errors", [])
        first_error = errors[0] if errors else "Unknown error"
        error_text = reasoning_results.get("answer", f"Task failed: {first_error}")
        await publish_chat_event(state["run_id"], state["user_id"], "final_answer", {"content": error_text, "error": True, "errors": errors, "status": "failed"})

    state["status"] = "COMPLETED"
    state["current_phase"] = "COMPLETED"
    return state
