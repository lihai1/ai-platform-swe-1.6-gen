"""Per-chat asyncio queues for NATS-to-SSE event streaming"""
import asyncio
from typing import Dict
from collections import defaultdict

# Per-chat asyncio queues for real-time event streaming
# Key: chat_id, Value: asyncio.Queue
event_streams: Dict[str, asyncio.Queue] = {}
# Lock for thread-safe access to event_streams dict
streams_lock = asyncio.Lock()


async def get_event_stream(chat_id: str) -> asyncio.Queue:
    """Get or create an event queue for a specific chat"""
    async with streams_lock:
        if chat_id not in event_streams:
            event_streams[chat_id] = asyncio.Queue(maxsize=1000)
        return event_streams[chat_id]


async def push_event(chat_id: str, event: dict) -> None:
    """Push an event to the chat's event queue"""
    async with streams_lock:
        if chat_id in event_streams:
            try:
                # Non-blocking put, drop if queue is full
                event_streams[chat_id].put_nowait(event)
            except asyncio.QueueFull:
                # Queue is full, drop oldest event
                try:
                    event_streams[chat_id].get_nowait()
                    event_streams[chat_id].put_nowait(event)
                except asyncio.QueueEmpty:
                    pass


async def remove_event_stream(chat_id: str) -> None:
    """Remove the event queue for a chat (cleanup on disconnect)"""
    async with streams_lock:
        if chat_id in event_streams:
            del event_streams[chat_id]
