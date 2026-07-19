from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from internal.config import settings
from internal.db import connect, disconnect, get_session
from internal.chatkit import chatkit_router
from internal.agent.router import router as agent_router
from internal.messaging.nats import NATSMessaging
from internal.event_streams import push_event
from internal.handlers.nats import handle_agent_state_event, handle_worker_user_event, handle_worker_ready, handle_agent_error
from internal.chatkit.router import nats_client, get_nats_client
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import logging
import asyncio
import time
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    global nats_client
    # Startup
    try:
        await connect()
    except Exception as e:
        print(f"Warning: Failed to connect to database: {e}")
        print("Continuing without database connection (mock mode)")
    
    # Connect to NATS
    try:
        logger.info(f"Attempting to connect to NATS at {settings.nats_url}")
        nats_client = NATSMessaging(nats_url=settings.nats_url, service_id=settings.service_id)
        logger.info("NATSMessaging instance created")
        await nats_client.connect()
        logger.info("NATS connection established")
        
        # Subscribe to all agent events for state updates
        # Using subscribe_to_events to listen to agent.user.*.events.> pattern
        await nats_client.subscribe_to_events(
            event_handler=lambda event: handle_agent_state_event(event, push_event),
            user_id=None,  # Subscribe to all users
            run_id=None  # Subscribe to all runs
        )
        
        # Subscribe to worker output events (final_answer, progress_update)
        # Using subscribe_to_chat_events to listen to agent.user.*.chat.> pattern
        await nats_client.subscribe_to_chat_events(
            event_handler=lambda event: handle_worker_user_event(event, push_event),
            user_id=None,  # Subscribe to all users
            run_id=None  # Subscribe to all runs
        )
        
        # Subscribe to error messages from agent-worker
        await nats_client.subscribe_to_errors(
            event_handler=lambda event: handle_agent_error(event, push_event),
        )

        # Subscribe to worker ready signals
        await nats_client.subscribe_to_worker_ready(
            event_handler=lambda event: handle_worker_ready(event, push_event),
        )

        logger.info("Connected to NATS and subscribed to agent state events")
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
        print(f"Warning: Failed to disconnect from database: {e}")

app = FastAPI(
    title="Agent Service",
    description="AI agent service with ChatKit integration",
    version="0.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    logger.info(f"HTTP {request.method} {request.url.path}")
    response = await call_next(request)
    process_time = time.time() - start_time
    logger.info(f"HTTP {request.method} {request.url.path} - Status: {response.status_code} - Time: {process_time:.3f}s")
    return response

app.include_router(chatkit_router, prefix="/api/chatkit", tags=["chatkit"])
app.include_router(agent_router)


async def proxy_request(
    method: str,
    path: str,
    request: Request,
    body: Optional[bytes] = None
) -> Response:
    """
    Generic proxy function to forward requests to control-plane.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Path to proxy to (e.g., /api/v1/projects)
        request: Original FastAPI request
        body: Optional request body for POST/PUT requests
    
    Returns:
        Response from control-plane
    
    Raises:
        HTTPException: If proxy request fails
    """
    try:
        url = f"{settings.control_plane_url}{path}"
        headers = _sanitize_headers(dict(request.headers))
        params = dict(request.query_params) if request.query_params else None
        
        async with httpx.AsyncClient(timeout=settings.proxy_timeout) as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, params=params)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, content=body, params=params)
            elif method.upper() == "PUT":
                response = await client.put(url, headers=headers, content=body, params=params)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers, params=params)
            else:
                raise HTTPException(status_code=405, detail=f"Method {method} not supported")
            
            logger.info(f"Proxied {method} {path} -> {response.status_code}")
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=_sanitize_response_headers(dict(response.headers))
            )
            
    except httpx.TimeoutException:
        logger.error(f"Proxy request timeout: {method} {path}")
        raise HTTPException(status_code=504, detail="Control-plane request timeout")
    except httpx.HTTPError as e:
        logger.error(f"HTTP error proxying {method} {path}: {e}")
        raise HTTPException(status_code=502, detail="Control-plane communication error")
    except Exception as e:
        logger.error(f"Unexpected error proxying {method} {path}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal proxy error")


def _sanitize_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Remove headers that shouldn't be forwarded."""
    headers_to_remove = {"host", "content-length", "transfer-encoding"}
    return {k: v for k, v in headers.items() if k.lower() not in headers_to_remove}


def _sanitize_response_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Remove response headers that shouldn't be forwarded."""
    headers_to_remove = {"content-encoding", "content-length", "transfer-encoding"}
    return {k: v for k, v in headers.items() if k.lower() not in headers_to_remove}


def _create_proxy_endpoint(method: str, path: str):
    """
    Factory function to create proxy endpoint handlers.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Path to proxy to
    
    Returns:
        Async function that handles the proxy request
    """
    async def proxy_handler(request: Request):
        if method.upper() in ["POST", "PUT", "PATCH"]:
            body = await request.body()
            return await proxy_request(method, path, request, body)
        else:
            return await proxy_request(method, path, request)
    
    proxy_handler.__name__ = f"proxy_{method.lower()}_{path.replace('/', '_').replace('-', '_')}"
    return proxy_handler


# Control-plane proxy endpoints (no versioning in new API design)
app.get("/api/projects")(_create_proxy_endpoint("GET", "/api/v1/projects"))
app.post("/api/projects")(_create_proxy_endpoint("POST", "/api/v1/projects"))
app.get("/api/repositories")(_create_proxy_endpoint("GET", "/api/v1/repositories"))
app.post("/api/repositories")(_create_proxy_endpoint("POST", "/api/v1/repositories"))

# Auth proxy endpoints (no versioning in new API design)
app.post("/api/auth/login")(_create_proxy_endpoint("POST", "/api/v1/auth/login"))
app.post("/api/auth/register")(_create_proxy_endpoint("POST", "/api/v1/auth/register"))
app.get("/api/auth/me")(_create_proxy_endpoint("GET", "/api/v1/auth/me"))

# LLM proxy endpoint (no versioning in new API design)
app.get("/api/llm/models")(_create_proxy_endpoint("GET", "/api/v1/ollama/models"))


@app.get("/healthz")
async def health():
    return {"status": "healthy"}

@app.get("/readyz")
async def ready():
    return {"status": "ready"}
