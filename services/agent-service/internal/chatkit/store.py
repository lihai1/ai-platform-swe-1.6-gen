from typing import Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from internal.models import AgentRun
import uuid


class PostgreSQLStore:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def create_thread(self, metadata: dict) -> str:
        thread_id = str(uuid.uuid4())
        # Create AgentRun record
        async with self.session_factory() as session:
            run = AgentRun(
                id=thread_id,
                user_id=metadata.get("user_subject", "user:local-dev"),
                project_id=metadata.get("project_id", ""),
                repository_id=metadata.get("repository_id", ""),
                task=metadata.get("task", ""),
                status="CREATED",
            )
            session.add(run)
            await session.commit()
        return thread_id

    async def get_thread(self, thread_id: str) -> Optional[dict]:
        async with self.session_factory() as session:
            result = await session.execute(
                select(AgentRun).where(AgentRun.id == thread_id)
            )
            run = result.scalar_one_or_none()
            if run:
                return {
                    "id": run.id,
                    "title": run.task[:100],
                    "created_at": run.created_at,
                }
        return None

    async def add_message(self, thread_id: str, role: str, content: str) -> str:
        message_id = str(uuid.uuid4())
        # Store in AgentEvent or create ChatMessage model
        async with self.session_factory() as session:
            from internal.models import AgentEvent
            event = AgentEvent(
                id=message_id,
                chat_id=thread_id,
                event_type="message",
                event_data={"role": role, "content": content},
                sequence_number=0,
            )
            session.add(event)
            await session.commit()
        return message_id

    async def get_messages(self, thread_id: str) -> list[dict]:
        async with self.session_factory() as session:
            from internal.models import AgentEvent
            result = await session.execute(
                select(AgentEvent).where(
                    AgentEvent.chat_id == thread_id,
                    AgentEvent.event_type == "message"
                )
            )
            events = result.scalars().all()
            return [
                {
                    "id": e.id,
                    "role": e.event_data.get("role"),
                    "content": e.event_data.get("content"),
                    "created_at": e.created_at,
                }
                for e in events
            ]

    def generate_item_id(self, item_type: str, thread: dict, context: Any) -> str:
        return str(uuid.uuid4())
