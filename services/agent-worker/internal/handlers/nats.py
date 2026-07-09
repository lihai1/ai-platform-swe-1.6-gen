"""NATS message handlers for agent worker"""
import logging
import json
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


async def handle_command(command: dict, handle_run_start_func, handle_run_cancel_func, handle_run_resume_func) -> None:
    """Handle incoming command"""
    command_type = command.get("command_type")
    run_id = command.get("run_id")
    payload = command.get("payload", {})

    logger.info(f"[WORKER] Received command {command_type} for run {run_id}")
    logger.info(f"[WORKER] Command payload: {command}")

    try:
        if command_type == "run.start":
            await handle_run_start_func(run_id, payload)
        elif command_type == "run.cancel":
            await handle_run_cancel_func(run_id, payload)
        elif command_type == "run.resume":
            await handle_run_resume_func(run_id, payload)
        else:
            logger.warning(f"[WORKER] Unknown command type: {command_type}")
    except Exception as e:
        logger.error(f"[WORKER] Error handling command: {e}")


async def handle_run_start(run_id: str, payload: dict, create_run_func, get_checkpointer_func) -> None:
    """Handle run start command"""
    logger.info(f"[WORKER] Starting run for run {run_id}")
    logger.info(f"[WORKER] Run payload: {payload}")
    
    try:
        # Get checkpointer
        checkpointer = await get_checkpointer_func()
        
        # Check for mock mode
        import os
        mock_mode = os.getenv("MOCK_MODE", "false").lower() == "true"
        logger.info(f"[WORKER] Mock mode: {mock_mode}")
        
        # Execute the workflow
        result = await create_run_func({
            "run_id": run_id,
            "user_id": payload.get("user_id"),
            "project_id": payload.get("project_id"),
            "repository_id": payload.get("repository_id"),
            "chatkit_thread_id": payload.get("chatkit_thread_id"),
            "task": payload.get("task"),
            "max_tokens": payload.get("max_tokens"),
            "max_cost": payload.get("max_cost"),
            "max_repair_count": payload.get("max_repair_count", 2),
            "mock_mode": mock_mode,
        }, checkpointer)
        
        logger.info(f"[WORKER] Run for run {run_id} completed with status {result.get('status')}")
        
    except Exception as e:
        logger.error(f"[WORKER] Run for run {run_id} failed: {e}")


async def handle_run_cancel(run_id: str, payload: dict) -> None:
    """Handle run cancel command"""
    logger.info(f"[WORKER] Cancelling run for run {run_id}")
    
    # In production, this would update the run state and notify the workflow
    # For now, this is a placeholder


async def handle_run_resume(run_id: str, payload: dict) -> None:
    """Handle run resume command (for approval)"""
    logger.info(f"[WORKER] Resuming run for run {run_id}")
    
    # In production, this would resume the workflow from checkpoint
    # For now, this is a placeholder


async def publish_final_answer(run_id: str, content: str, nats_client) -> None:
    """Publish final answer to agent.chat.{run_id}.user.events"""
    if not nats_client or not nats_client.js:
        logger.warning(f"[WORKER] NATS not connected, cannot publish final answer for run {run_id}")
        return
    
    message = {
        "message_id": str(uuid.uuid4()),
        "event_type": "final_answer",
        "run_id": run_id,
        "payload": {
            "content": content,
        },
        "timestamp": datetime.utcnow().isoformat(),
        "schema_version": "1.0",
    }
    
    subject = f"agent.chat.{run_id}.user.events"
    try:
        await nats_client.js.publish(
            subject=subject,
            payload=json.dumps(message).encode(),
            headers={
                "message_id": message["message_id"],
                "run_id": run_id,
            }
        )
        logger.info(f"[WORKER] Published final answer for run {run_id}")
    except Exception as e:
        logger.error(f"[WORKER] Failed to publish final answer: {e}")


async def publish_progress_update(run_id: str, content: str, nats_client) -> None:
    """Publish progress update to agent.chat.{run_id}.user.events"""
    if not nats_client or not nats_client.js:
        logger.warning(f"[WORKER] NATS not connected, cannot publish progress update for run {run_id}")
        return
    
    message = {
        "message_id": str(uuid.uuid4()),
        "event_type": "progress_update",
        "run_id": run_id,
        "payload": {
            "content": content,
        },
        "timestamp": datetime.utcnow().isoformat(),
        "schema_version": "1.0",
    }
    
    subject = f"agent.chat.{run_id}.user.events"
    try:
        await nats_client.js.publish(
            subject=subject,
            payload=json.dumps(message).encode(),
            headers={
                "message_id": message["message_id"],
                "run_id": run_id,
            }
        )
        logger.info(f"[WORKER] Published progress update for run {run_id}")
    except Exception as e:
        logger.error(f"[WORKER] Failed to publish progress update: {e}")


async def publish_worker_ready(run_id: str, nats_client) -> None:
    """Publish worker ready signal using plain NATS"""
    if not nats_client or not nats_client.nc:
        logger.warning(f"[WORKER] NATS not connected, cannot publish worker ready for run {run_id}")
        return
    
    message = {
        "message_id": str(uuid.uuid4()),
        "run_id": run_id,
        "status": "ready",
        "timestamp": datetime.utcnow().isoformat(),
        "schema_version": "1.0",
    }
    
    subject = f"agent.chat.{run_id}.worker.ready"
    try:
        await nats_client.nc.publish(subject, json.dumps(message).encode())
        logger.info(f"[WORKER] Published worker ready signal for run {run_id}")
    except Exception as e:
        logger.error(f"[WORKER] Failed to publish worker ready: {e}")
