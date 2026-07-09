import uuid
import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any
from chatkit.server import ChatKitServer
from chatkit.types import (
    AssistantMessageContent,
    AssistantMessageItem,
    ProgressUpdateEvent,
    ThreadItemDoneEvent,
    ThreadMetadata,
    ThreadStreamEvent,
    UserMessageItem,
)
from internal.chatkit.context import RequestContext
from internal.chatkit.event_mapper import (
    final_answer_from_event,
    is_cancelled_event,
    is_completed_event,
    is_failed_event,
    progress_from_event,
)
from internal.chatkit.nats_bridge import NatsBridge


def extract_text(input_message: UserMessageItem | None) -> str:
    if input_message is None:
        return ""

    content = getattr(input_message, "content", None)

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []

        for part in content:
            if isinstance(part, dict):
                text = part.get("text")
            else:
                text = getattr(part, "text", None)

            if text:
                parts.append(str(text))

        return "\n".join(parts).strip()

    return str(content or "").strip()


class AegisChatKitServer(ChatKitServer[RequestContext]):
    def __init__(self, store: Any, nats_bridge: NatsBridge):
        super().__init__(store=store)
        self.nats = nats_bridge

    async def respond(
        self,
        thread: ThreadMetadata,
        input: UserMessageItem | None,
        context: RequestContext,
    ) -> AsyncIterator[str]:
        print("CHATKIT respond called - START")
        print(f"Thread: {thread.id}, Input: {input}, Context: {context}")

        prompt = extract_text(input)

        if not prompt:
            event = self._assistant_message(
                thread=thread,
                context=context,
                text="Please enter a request.",
            )
            yield self._event_to_sse(event)
            return

        run_id = f"run-{uuid.uuid4()}"
        conversation_id = thread.id

        print("CHATKIT created run", run_id)

        # Important: Subscribe before publishing agent.start
        events = self.nats.subscribe_run_events(run_id)

        await self.nats.publish_agent_start(
            run_id=run_id,
            conversation_id=conversation_id,
            user_subject=context.user_subject,
            prompt=prompt,
            metadata={
                "org_id": context.org_id,
                "request_id": context.request_id,
                "source": "chatkit",
            },
        )

        print("NATS agent.start published", run_id)

        progress_event = ProgressUpdateEvent(
            icon="agent",
            text=f"Agent started: {run_id}",
        )
        yield self._event_to_sse(progress_event)

        async for event in events:
            print("NATS event received", event)

            if is_completed_event(event):
                final_text = final_answer_from_event(event)
                print("YIELDING final assistant message")
                event = self._assistant_message(
                    thread=thread,
                    context=context,
                    text=final_text,
                )
                yield self._event_to_sse(event)
                break

            if is_failed_event(event):
                print("YIELDING failed assistant message")
                event = self._assistant_message(
                    thread=thread,
                    context=context,
                    text=f"Agent failed: {event.get('message', 'unknown error')}",
                )
                yield self._event_to_sse(event)
                break

            if is_cancelled_event(event):
                print("YIELDING cancelled assistant message")
                event = self._assistant_message(
                    thread=thread,
                    context=context,
                    text="Agent run was cancelled.",
                )
                yield self._event_to_sse(event)
                break

            print("YIELDING progress update")
            event = progress_from_event(event)
            yield self._event_to_sse(event)

    def _event_to_sse(self, event: ThreadStreamEvent) -> str:
        """Convert a ChatKit event to SSE format"""
        # Serialize event to JSON
        event_json = event.model_dump_json()
        # Return in SSE format
        return f"data: {event_json}\n\n"

    def _assistant_message(
        self,
        *,
        thread: ThreadMetadata,
        context: RequestContext,
        text: str,
    ) -> ThreadItemDoneEvent:
        return ThreadItemDoneEvent(
            item=AssistantMessageItem(
                thread_id=thread.id,
                id=self.store.generate_item_id("message", thread, context),
                created_at=datetime.now(timezone.utc),
                content=[
                    AssistantMessageContent(text=text),
                ],
            )
        )
