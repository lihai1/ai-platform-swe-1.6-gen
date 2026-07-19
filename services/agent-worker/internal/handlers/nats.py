"""NATS message handlers for agent worker"""
import logging
import json
import uuid
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


async def _get_graph_for_run(payload, worker, checkpointer, agent_type=None):
    """Return the compiled graph for this run, preferring the worker's stored graph."""
    if worker and getattr(worker, "graph", None):
        return worker.graph
    if worker and getattr(worker, "agent_type", None):
        agent_type = worker.agent_type
    elif payload and payload.get("agent_type"):
        agent_type = payload.get("agent_type")
    if not agent_type:
        agent_type = os.environ.get("AGENT_TYPE", "specialist")
    if agent_type == "single-agent":
        from internal.agents.single_agent.graph import create_single_agent_graph
        return create_single_agent_graph(checkpointer)
    from internal.agents.specialist.graph import create_specialist_agent_graph
    return create_specialist_agent_graph(checkpointer)


async def handle_command(command: dict, handle_run_start_func) -> None:
    """Handle incoming command"""
    command_type = command.get("command_type")
    run_id = command.get("run_id")
    payload = command.get("payload", {})

    logger.info(f"[WORKER] Received command {command_type} for run {run_id}")
    logger.info(f"[WORKER] Command payload: {command}")

    try:
        if command_type == "run.start":
            await handle_run_start_func(run_id, payload)
        else:
            logger.warning(f"[WORKER] Unknown command type: {command_type}")
    except Exception as e:
        logger.error(f"[WORKER] Error handling command: {e}")


async def handle_run_start(run_id: str, payload: dict, create_run_func, get_checkpointer_func, worker=None) -> None:
    """Handle run start command"""
    logger.info(f"[WORKER] Starting run for run {run_id}")
    logger.info(f"[WORKER] Run payload: {payload}")
    
    try:
        # Get checkpointer
        checkpointer = await get_checkpointer_func()
        
        # Check for mock mode (from payload or environment)
        import os
        mock_mode = payload.get("mock_mode", os.getenv("MOCK_MODE", "false").lower() == "true")
        llm_provider = payload.get("llm_provider") or os.getenv("LLM_PROVIDER")
        logger.info(f"[WORKER] Mock mode: {mock_mode}, LLM provider: {llm_provider}")

        # Determine agent type from worker, payload, or environment
        agent_type = "specialist"
        if worker and getattr(worker, "agent_type", None):
            agent_type = worker.agent_type
        elif payload and payload.get("agent_type"):
            agent_type = payload.get("agent_type")
        elif os.environ.get("AGENT_TYPE"):
            agent_type = os.environ.get("AGENT_TYPE")

        # Create and store graph in worker if worker instance provided
        if worker:
            worker.graph = await _get_graph_for_run(payload, worker, checkpointer, agent_type=agent_type)
            logger.info(f"[WORKER] Graph instance stored in worker for run {run_id}")

        # Execute the workflow
        result = await create_run_func({
            "run_id": run_id,
            "user_id": payload.get("user_id"),
            "project_id": payload.get("project_id"),
            "repository_id": payload.get("repository_id"),
            "task": payload.get("task"),
            "max_tokens": payload.get("max_tokens"),
            "max_cost": payload.get("max_cost"),
            "max_repair_count": payload.get("max_repair_count", 2),
            "mock_mode": mock_mode,
            "llm_provider": llm_provider,
            "agent_type": agent_type,
        }, checkpointer)
        
        logger.info(f"[WORKER] Run for run {run_id} completed with status {result.get('status')}")
        
    except Exception as e:
        logger.error(f"[WORKER] Run for run {run_id} failed: {e}")


async def handle_user_event(event: dict, worker=None) -> None:
    """Handle user events from agent-service and trigger appropriate agent actions"""
    event_type = event.get("event_type")
    run_id = event.get("run_id")
    payload = event.get("payload", {})
    
    logger.info(f"[WORKER] Received user event {event_type} for run {run_id}")
    logger.info(f"[WORKER] User event payload: {event}")
    
    try:
        # Handle tool approval events
        if event_type in {"tool.allowed", "agent.tool.allowed", "agent.run.tool.allowed"}:
            logger.info(f"[WORKER] Tool allowed: {payload.get('tool_name', 'unknown')}")
            await resume_workflow_with_approval(run_id, "approved", payload, worker)
        elif event_type in {"tool.denied", "agent.tool.denied", "agent.run.tool.denied"}:
            logger.info(f"[WORKER] Tool denied: {payload.get('tool_name', 'unknown')}")
            await resume_workflow_with_approval(run_id, "denied", payload, worker)
        # Handle prompt events - trigger LangGraph agent with new prompt
        elif event_type in {"prompt", "agent.prompt", "agent.run.prompt", "user_input"}:
            logger.info(f"[WORKER] Prompt received: {payload.get('content', 'unknown')}")
            await trigger_agent_with_prompt(run_id, payload, worker)
        else:
            logger.warning(f"[WORKER] Unknown user event type: {event_type}")
    except Exception as e:
        logger.error(f"[WORKER] Error handling user event: {e}")


async def resume_workflow_with_approval(run_id: str, decision: str, payload: dict, worker=None) -> None:
    """Resume workflow with approval decision using existing graph instance.
    
    Args:
        run_id: The run identifier
        decision: The approval decision ("approved" or "denied")
        payload: The payload containing tool approval details
        worker: Optional worker instance with stored graph
    """
    from internal.workflow.checkpointer import get_checkpointer
    
    logger.info(f"[WORKER] Resuming workflow for run {run_id} with decision: {decision}")
    
    try:
        # Use stored graph instance if available
        if worker and getattr(worker, "graph", None):
            graph = worker.graph
            logger.info(f"[WORKER] Using stored graph instance for run {run_id}")
        else:
            checkpointer = await get_checkpointer()
            graph = await _get_graph_for_run(payload, worker, checkpointer)
            logger.info(f"[WORKER] Created new graph instance for run {run_id}")
        
        # Get current state from checkpointer
        config = {"configurable": {"thread_id": run_id}}
        checkpointer = await get_checkpointer()
        current_state = await checkpointer.aget(config)
        
        if not current_state:
            logger.error(f"[WORKER] No state found for run {run_id}")
            return
        
        # Update state with approval decision
        state_values = current_state.values if hasattr(current_state, 'values') else current_state
        approval_decisions = state_values.get("approval_decisions", {})
        approval_decisions["last"] = decision
        approval_decisions[payload.get("tool_name", "unknown")] = decision
        
        # Create updated state dict
        updated_state = dict(state_values)
        updated_state["approval_decisions"] = approval_decisions
        
        logger.info(f"[WORKER] Resuming workflow with updated approval decisions: {approval_decisions}")
        
        # Resume execution using existing graph
        result = await graph.ainvoke(updated_state, config)
        
        logger.info(f"[WORKER] Workflow resumed successfully for run {run_id}")
        
    except Exception as e:
        logger.error(f"[WORKER] Failed to resume workflow: {e}")
        import traceback
        logger.error(traceback.format_exc())


async def trigger_agent_with_prompt(run_id: str, payload: dict, worker=None) -> None:
    """Trigger LangGraph agent with new prompt content using existing graph instance.
    
    Args:
        run_id: The run identifier
        payload: The payload containing user input and metadata. May include:
            - content/input: The user message text
        worker: Optional worker instance with stored graph
    """
    from internal.workflow.checkpointer import get_checkpointer
    from internal.messaging.nats import get_nats_client
    
    logger.info(f"[WORKER] Triggering agent with prompt for run {run_id}")
    
    try:
        # Publish progress update to notify UI that agent is processing
        nats = get_nats_client()
        if nats:
            await nats.publish_chat_event(
                event_type="progress_update",
                run_id=run_id,
                user_id=payload.get("user_id", ""),
                payload={"content": "Processing your input..."}
            )
            logger.info(f"[WORKER] Published progress_update for user input")
        
        # Get current state from checkpointer first (to determine agent type and update state)
        config = {"configurable": {"thread_id": run_id}}
        checkpointer = await get_checkpointer()
        current_state = await checkpointer.aget(config)
        
        if not current_state:
            logger.warning(f"[WORKER] No state found for run {run_id}, treating as new conversation")
            # Treat as new conversation - reinitialize the workflow
            await handle_run_start(
                run_id,
                payload,
                create_run,
                get_checkpointer,
                worker,
            )
            return
        
        # Update state with new prompt content
        state_values = current_state.values if hasattr(current_state, 'values') else current_state
        updated_state = dict(state_values)
        
        # Add new prompt to messages and update the active task
        prompt_content = payload.get("content") or payload.get("input", "")
        if prompt_content:
            messages = updated_state.get("messages", [])
            messages.append({"role": "user", "content": prompt_content})
            updated_state["messages"] = messages
            previous_task = updated_state.get("task", "")
            updated_state["task"] = previous_task + "\n\nUser: " + prompt_content if previous_task else prompt_content
            logger.info(f"[WORKER] Added new prompt to messages: {prompt_content}")
        
        # Get the right graph for this run
        agent_type = updated_state.get("agent_type")
        if worker and getattr(worker, "graph", None):
            graph = worker.graph
            logger.info(f"[WORKER] Using stored graph instance for run {run_id}")
        else:
            graph = await _get_graph_for_run(payload, worker, checkpointer, agent_type=agent_type)
            logger.info(f"[WORKER] Created new graph instance for run {run_id}")
        
        # Trigger execution using existing graph
        result = await graph.ainvoke(updated_state, config)
        
        logger.info(f"[WORKER] Agent triggered successfully with prompt for run {run_id}")
        
    except Exception as e:
        logger.error(f"[WORKER] Failed to trigger agent with prompt: {e}")
        import traceback
        logger.error(traceback.format_exc())


