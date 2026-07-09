from langgraph.checkpoint.memory import MemorySaver
from internal.config import settings
import asyncio


async def get_checkpointer() -> MemorySaver:
    """Get or create in-memory checkpointer (temporary fix)"""
    # Use in-memory checkpointer for now to avoid context manager issues
    # TODO: Switch to AsyncPostgresSaver once API is clarified
    checkpointer = MemorySaver()
    return checkpointer
