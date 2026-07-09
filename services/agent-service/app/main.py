from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from internal.config import settings
from internal.db import connect, disconnect, get_session
from internal.chatkit import chatkit_router
from internal.workflow.router import router as workflow_router
from internal.messaging.nats import NATSMessaging
from internal.workflow.event_streams import push_event
from internal.handlers.nats import handle_agent_state_event, handle_worker_user_event
from internal.chatkit.router import nats_client, get_nats_client
from datetime import datetime, timezone
import os
import logging
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global nats_client
    # Startup
    try:
        await connect()
    except Exception as e:
        logger.warning("Failed to connect to database: %s", e)
        logger.warning("Continuing without database connection (mock mode)")
    
    # Connect to NATS
    try:
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        logger.info(f"Attempting to connect to NATS at {nats_url}")
        nats_client = NATSMessaging(nats_url=nats_url)
        logger.info("NATSMessaging instance created")
        await nats_client.connect()
        logger.info("NATS connection established")
        
        # Subscribe to all agent chat events for state updates
        # Using subscribe_to_events to listen to agent.events.> pattern
        await nats_client.subscribe_to_events(
            event_handler=lambda event: handle_agent_state_event(event, push_event),
            run_id=None  # Subscribe to all runs
        )
        
        # Subscribe to worker user events for final answers and progress
        # Using subscribe_plain to listen to agent.chat.{run_id}.user.events
        await nats_client.subscribe_plain(
            subject="agent.chat.>.user.events",
            handler=lambda event: handle_worker_user_event(event, push_event)
        )
        
        logger.info("Connected to NATS and subscribed to agent state events and worker user events")
    except Exception as e:
        logger.error(f"Failed to connect to NATS: {e}")
        import traceback
        logger.error(traceback.format_exc())
        logger.warning("Continuing without NATS connection")
        nats_client = None
    
    yield
    # Shutdown
    try:
        if nats_client:
            await nats_client.close()
    except Exception as e:
        logger.warning(f"Failed to close NATS connection: {e}")
    
    try:
        await disconnect()
    except Exception as e:
        logger.warning("Failed to disconnect from database: %s", e)

app = FastAPI(
    title="Agent Service",
    description="AI agent service with ChatKit integration",
    version="0.1.0",
    lifespan=lifespan
)

# CORS: a wildcard origin cannot be combined with credentials per the Fetch spec.
# Allowed origins are configurable via CORS_ALLOW_ORIGINS (comma-separated).
_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", "*").split(",")
    if origin.strip()
]
_allow_credentials = _cors_origins != ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chatkit_router, prefix="/api/chatkit", tags=["chatkit"])
app.include_router(workflow_router, tags=["workflow"])

@app.get("/healthz")
async def health():
    return {"status": "healthy"}

@app.get("/readyz")
async def ready():
    return {"status": "ready"}
