"""NATS message handlers for agent service"""
import logging
import os

logger = logging.getLogger(__name__)

# Global OpenAI ChatKit client
chatkit_client = None

try:
    from openai import OpenAI
    chatkit_client_type = OpenAI
except ImportError:
    chatkit_client_type = None
    logger.warning("OpenAI module not available, ChatKit functionality will be disabled")


def get_chatkit_client():
    """Get or create ChatKit client"""
    global chatkit_client
    if chatkit_client is None and chatkit_client_type is not None:
        openai_api_key = os.getenv("OPENAI_API_KEY", "")
        chatkit_client = chatkit_client_type(api_key=openai_api_key)
    return chatkit_client


async def handle_agent_state_event(event: dict, push_event_func) -> None:
    """Handle agent state events and push to SSE streams"""
    run_id = event.get("run_id")
    event_type = event.get("event_type")
    payload = event.get("payload", {})
    
    logger.info(f"Received agent state event for run {run_id}: {event_type}")
    
    # Push to SSE stream queue for real-time delivery
    if run_id:
        await push_event_func(run_id, {
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": event.get("timestamp")
        })
        logger.info(f"Pushed event to SSE stream for run {run_id}")
    
    # Create ChatKit message based on event type using ChatKit library
    if run_id and event_type in ["created", "preparing_workspace", "scouting", "planning", "designing", "implementing", "testing", "reviewing", "verifying", "completed", "failed"]:
        try:
            client = get_chatkit_client()
            
            # Map event types to user-friendly messages
            message_map = {
                "created": "Agent run started",
                "preparing_workspace": "Preparing workspace...",
                "scouting": "Scouting repository...",
                "planning": "Planning approach...",
                "designing": "Designing solution...",
                "implementing": "Implementing changes...",
                "testing": "Testing implementation...",
                "reviewing": "Reviewing changes...",
                "verifying": "Verifying solution...",
                "completed": "Task completed successfully",
                "failed": f"Task failed: {payload.get('error_message', 'Unknown error')}"
            }
            
            message_content = message_map.get(event_type, f"Agent event: {event_type}")
            
            # Create ChatKit message via library (messaging infrastructure only)
            client.chatkit.messages.create(
                thread_id=run_id,
                content=message_content,
                role="assistant"
            )
            
            logger.info(f"Created ChatKit message for run {run_id}: {message_content}")
            
        except Exception as e:
            logger.error(f"Failed to create ChatKit message: {e}")
    
    logger.info(f"Run {run_id} state: {event_type}, payload: {payload}")


async def handle_worker_user_event(event: dict, push_event_func) -> None:
    """Handle worker user events (final answers, progress) from agent.chat.{run_id}.user.events"""
    run_id = event.get("run_id")
    event_type = event.get("event_type")
    payload = event.get("payload", {})
    
    logger.info(f"Received worker user event for run {run_id}: {event_type}")
    
    # Push to SSE stream queue for real-time delivery
    if run_id:
        await push_event_func(run_id, {
            "event_type": event_type,
            "run_id": run_id,
            "payload": payload,
            "timestamp": event.get("timestamp")
        })
        logger.info(f"Pushed worker user event to SSE stream for run {run_id}")
    
    # Create ChatKit message for worker user events using ChatKit library
    if run_id and event_type in ["final_answer", "progress_update"]:
        try:
            client = get_chatkit_client()
            
            message_content = payload.get("content", "")
            
            # Create ChatKit message via library (messaging infrastructure only)
            client.chatkit.messages.create(
                thread_id=run_id,
                content=message_content,
                role="assistant"
            )
            
            logger.info(f"Created ChatKit message for run {run_id} from worker: {message_content}")
            
        except Exception as e:
            logger.error(f"Failed to create ChatKit message from worker: {e}")
