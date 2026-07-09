from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from internal.db import get_session
from internal.models import AgentRun
from internal.messaging.nats import NATSMessaging
from internal.chatkit.context import context_from_request
from internal.chatkit.server import AegisChatKitServer
from internal.chatkit.store import PostgreSQLStore
from internal.chatkit.nats_bridge import NatsBridge
from typing import Optional
import os
import uuid
import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

chatkit_router = APIRouter()

CONTROL_PLANE_URL = os.getenv("CONTROL_PLANE_URL", "http://localhost:8080")
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")

# Global NATS client
nats_client: Optional[NATSMessaging] = None
chatkit_server: Optional[AegisChatKitServer] = None

async def get_nats_client() -> NATSMessaging:
    """Get or create NATS client"""
    global nats_client
    if nats_client is None:
        nats_client = NATSMessaging(nats_url=NATS_URL)
        await nats_client.connect()
    return nats_client

async def get_chatkit_server() -> AegisChatKitServer:
    """Get or create ChatKit server"""
    global chatkit_server
    if chatkit_server is None:
        from internal.db import get_session
        # Ensure NATS client is initialized
        if nats_client is None:
            await get_nats_client()
        store = PostgreSQLStore(get_session)
        nats_bridge = NatsBridge(nats_client)
        chatkit_server = AegisChatKitServer(store=store, nats_bridge=nats_bridge)
    return chatkit_server


@chatkit_router.post("/")
async def chatkit_endpoint(request: Request):
    """ChatKit endpoint for streaming responses"""
    context = context_from_request(request)
    body = await request.body()

    logger.info("ChatKit endpoint called (%d bytes)", len(body))

    # Convert UI format to ChatKit protocol format
    from chatkit.types import ThreadMetadata, UserMessageItem
    
    try:
        ui_request = json.loads(body)
        
        # Extract thread_id and message
        thread_id = ui_request.get("thread_id") or f"thread-{uuid.uuid4()}"
        message = ui_request.get("message", "")

        logger.info("ChatKit request thread_id=%s", thread_id)

        # Create thread metadata
        thread = ThreadMetadata(
            id=thread_id,
            title=message[:50] if message else "New Chat",
            created_at=datetime.now(timezone.utc),
        )
        
        # Create user message item with correct content format
        user_message = UserMessageItem(
            thread_id=thread_id,
            id=str(uuid.uuid4()),
            created_at=datetime.now(timezone.utc),
            content=[{"type": "input_text", "text": message}],
            inference_options={},
        )

        # Get ChatKit server and call respond()
        server = await get_chatkit_server()
        event_stream = server.respond(thread, user_message, context)

        logger.info("Returning ChatKit streaming response for thread_id=%s", thread_id)
        return StreamingResponse(
            event_stream,
            media_type="text/event-stream",
        )
        
    except Exception as e:
        logger.exception("ChatKit server error")
        raise HTTPException(status_code=500, detail=f"ChatKit server error: {str(e)}")


@chatkit_router.get("/threads/{run_id}")
async def get_thread(
    run_id: str,
    session: AsyncSession = Depends(get_session)
):
    """Get thread and messages from PostgreSQL store"""
    try:
        from internal.chatkit.store import PostgreSQLStore
        store = PostgreSQLStore(get_session)
        
        thread = await store.get_thread(run_id)
        if not thread:
            raise HTTPException(status_code=404, detail=f"Thread not found: {run_id}")
        
        messages = await store.get_messages(run_id)
        
        return {
            "thread": thread,
            "items": messages
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get thread: {str(e)}")


@chatkit_router.post("/close/{run_id}")
async def close_chat(
    run_id: str,
):
    """Close a chat and terminate its container"""
    try:
        # Publish chat close via NATS for workflow orchestration
        nats = await get_nats_client()
        await nats.publish_chat_close(run_id=run_id)
        
        return {"status": "closed", "run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to close chat: {str(e)}")
