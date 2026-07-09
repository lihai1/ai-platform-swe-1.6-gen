from typing import AsyncGenerator, Optional
from fastapi import Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from internal.models import AgentEvent, AgentRun
from internal.messaging.nats import NATSMessaging
from internal.workflow.event_streams import get_event_stream, remove_event_stream
import json
import asyncio
import os

# Global NATS client for event publishing
_nats_client: Optional[NATSMessaging] = None

async def get_nats_client() -> NATSMessaging:
    """Get or create NATS client for event publishing"""
    global _nats_client
    if _nats_client is None:
        nats_url = os.getenv("NATS_URL", "nats://localhost:4222")
        _nats_client = NATSMessaging(nats_url=nats_url)
        await _nats_client.connect()
    return _nats_client


async def event_generator(
    run_id: str,
    session: AsyncSession,
    last_event_id: Optional[int] = None
) -> AsyncGenerator[dict, None]:
    """Generate SSE events for a run from both queue and database"""
    
    # Get or create event queue for this run
    event_queue = await get_event_stream(run_id)
    
    # If last_event_id is provided, start from that point
    start_sequence = last_event_id + 1 if last_event_id else 0
    
    try:
        while True:
            # First, check queue for real-time events from NATS
            try:
                # Non-blocking get with timeout
                event = await asyncio.wait_for(event_queue.get(), timeout=0.1)
                yield {
                    "id": start_sequence,
                    "event": event["event_type"],
                    "data": json.dumps({
                        "run_id": event["run_id"],
                        "event_type": event["event_type"],
                        "event_data": event["payload"],
                        "timestamp": event.get("timestamp")
                    })
                }
                start_sequence += 1
            except asyncio.TimeoutError:
                # No events in queue, check database
                pass
            
            # Then, query database for persisted events
            query = select(AgentEvent).where(
                AgentEvent.chat_id == run_id,
                AgentEvent.sequence_number >= start_sequence
            ).order_by(AgentEvent.sequence_number)
            
            result = await session.execute(query)
            events = result.scalars().all()
            
            for event in events:
                yield {
                    "id": event.sequence_number,
                    "event": event.event_type,
                    "data": json.dumps({
                        "run_id": event.chat_id,
                        "step_id": event.step_id,
                        "event_type": event.event_type,
                        "event_data": event.event_data,
                        "created_at": event.created_at.isoformat()
                    })
                }
                start_sequence = event.sequence_number + 1
            
            # Check if run is in terminal state
            run_query = select(AgentRun).where(AgentRun.id == run_id)
            run_result = await session.execute(run_query)
            run = run_result.scalar_one_or_none()
            
            if run and run.status in ["COMPLETED", "FAILED", "CANCELLED", "BUDGET_EXCEEDED"]:
                # Send final event and stop
                yield {
                    "id": start_sequence,
                    "event": "run_complete",
                    "data": json.dumps({
                        "run_id": run_id,
                        "status": run.status,
                        "error_message": run.error_message
                    })
                }
                break
            
            # Small sleep to prevent tight loop
            await asyncio.sleep(0.1)
    finally:
        # Cleanup queue when client disconnects
        await remove_event_stream(run_id)
        


async def stream_events(
    run_id: str,
    request: Request,
    session: AsyncSession
) -> EventSourceResponse:
    """Stream events via SSE"""
    
    # Get Last-Event-ID header for reconnection
    last_event_id = None
    if "last-event-id" in request.headers:
        try:
            last_event_id = int(request.headers["last-event-id"])
        except ValueError:
            pass
    
    return EventSourceResponse(
        event_generator(run_id, last_event_id, session),
        media_type="text/event-stream"
    )


async def publish_event(
    run_id: str,
    step_id: Optional[str],
    event_type: str,
    event_data: dict,
    session: AsyncSession
) -> AgentEvent:
    """Publish an event to the database and NATS"""

    # Get the next sequence number for this run
    query = select(AgentEvent).where(AgentEvent.chat_id == run_id).order_by(
        AgentEvent.sequence_number.desc()
    )
    result = await session.execute(query)
    last_event = result.scalar_one_or_none()

    next_sequence = (last_event.sequence_number + 1) if last_event else 0

    event = AgentEvent(
        chat_id=run_id,
        step_id=step_id,
        event_type=event_type,
        event_data=event_data,
        sequence_number=next_sequence
    )

    session.add(event)
    await session.commit()
    await session.refresh(event)

    # Publish to NATS for real-time updates
    try:
        nats = await get_nats_client()
        await nats.publish_event(
            event_type=event_type,
            run_id=run_id,
            payload={
                "event_type": event_type,
                "run_id": run_id,
                "step_id": step_id,
                "event_data": event_data,
                "sequence_number": next_sequence,
            }
        )
    except Exception as e:
        # Log but don't fail if NATS publishing fails
        print(f"Failed to publish event to NATS: {e}")

    return event
