import uuid
import json
import asyncio
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
    _payload,
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
        is_new_thread: bool = False,
    ) -> AsyncIterator[str]:
        print("CHATKIT respond called - START")
        print(f"Thread: {thread.id}, Input: {input}, Context: {context}")

        prompt = extract_text(input)

        # Handle empty prompt
        if not prompt:
            for sse_event in self._handle_empty_prompt(thread, context):
                yield sse_event
            return

        # Use run_id from context (set by router for new threads, retrieved from store for existing threads)
        run_id = context.run_id or f"run-{uuid.uuid4()}"

        print("CHATKIT using run", run_id)

        # Create event stream
        from internal.event_streams import get_event_stream
        event_stream = await get_event_stream(run_id)
        print(f"ChatKit server: Created event stream for run_id: {run_id}, queue size: {event_stream.qsize()}")

        # Persist user message
        await self._persist_message(thread.id, "user", prompt)


        # Drain initial queue
        terminal_event, progress_events = await self._drain_initial_queue(
            event_stream=event_stream,
            thread=thread,
            context=context,
        )

        # Notify user if resuming existing session (before yielding other events)
        if not is_new_thread:
            yield self._event_to_sse(ProgressUpdateEvent(
                icon="info",
                text="Continuing conversation...",
            ))
            # Send user input to existing agent via NATS
            await self.nats.nats.publish_chat_event(
                event_type="user_input",
                run_id=run_id,
                payload={"type": "user_input", "input": prompt},
                user_id=context.user_subject,
            )
            print(f"Published user_input to existing agent run {run_id}")
        else:
            # Yield initial progress event only for new threads
            yield self._event_to_sse(ProgressUpdateEvent(
                icon="agent",
                text=f"Agent started: {run_id}",
            ))

        # Yield any progress events from the drain
        for progress_event in progress_events:
            yield progress_event
        
        # If a terminal event was found, yield it and return
        if terminal_event is not None:
            yield terminal_event
            return

        # Process events from stream
        while True:
            print(f"ChatKit server: Waiting for event from stream, queue size: {event_stream.qsize()}")
            event = await event_stream.get()
            print(f"ChatKit server: Received event from global stream: {event.get('event_type')}, full event: {event}")

            result = await self._process_event(
                event=event,
                thread=thread,
                context=context,
            )
            if result is not None:
                yield result["sse_event"]
                if result["should_break"]:
                    break

    def _event_to_sse(self, event: ThreadStreamEvent) -> str:
        """Convert a ChatKit event to SSE format"""
        event_json = event.model_dump_json()
        if isinstance(event_json, dict):
            event_json = json.dumps(event_json)
        return f"data: {event_json}\n\n"

    async def _handle_empty_prompt(
        self,
        thread: ThreadMetadata,
        context: RequestContext,
    ) -> AsyncIterator[str]:
        """Handle the case when the user provides an empty prompt."""
        event = self._assistant_message(
            thread=thread,
            context=context,
            text="Please enter a request.",
        )
        yield self._event_to_sse(event)

    async def _persist_message(self, thread_id: str, role: str, content: str) -> None:
        """Persist a message to the store."""
        try:
            await self.store.add_message(
                run_id=thread_id,
                role=role,
                content=content,
            )
            print(f"Persisted {role} message for thread {thread_id}")
        except Exception as e:
            print(f"Failed to persist {role} message: {e}")

    async def _publish_agent_start(
        self,
        run_id: str,
        user_subject: str,
        prompt: str,
        context: RequestContext,
    ) -> None:
        """Publish the agent start event to NATS."""
        await self.nats.publish_agent_start(
            run_id=run_id,
            conversation_id=run_id,
            user_subject=user_subject,
            prompt=prompt,
            metadata={
                "org_id": context.org_id,
                "request_id": context.request_id,
                "source": "chatkit",
                "project_id": context.project_id,
                "repository_id": context.repository_id,
                "mock_mode": context.mock_mode,
                "llm_provider": context.llm_provider,
                "model_name": context.model_name,
                "agent_type": context.agent_type,
                "api_key": context.api_key,
            },
        )
        print("NATS agent.start published", run_id)

    async def _drain_initial_queue(
        self,
        event_stream: asyncio.Queue,
        thread: ThreadMetadata,
        context: RequestContext,
    ) -> tuple[str | None, list[str]]:
        """Drain events that were queued before we started waiting.
        
        Returns a tuple of (terminal_event_sse, progress_events_list).
        If a terminal event (completed/failed/cancelled) was found, terminal_event_sse contains it.
        progress_events_list contains any non-terminal events that should be yielded.
        """
        try:
            print("ChatKit server: About to sleep for 0.3s")
            await asyncio.sleep(0.3)
            print("ChatKit server: Sleep completed")
        except Exception as e:
            print(f"ERROR during sleep: {e}")
            import traceback
            traceback.print_exc()

        progress_events = []
        terminal_event = None
        
        try:
            print(f"ChatKit server: Draining initial queue, size: {event_stream.qsize()}")
            drained_count = 0
            while not event_stream.empty():
                try:
                    event = event_stream.get_nowait()
                    drained_count += 1
                    print(f"ChatKit server: Drained event {drained_count}: {event.get('event_type')}")
                    
                    result = await self._process_event(
                        event=event,
                        thread=thread,
                        context=context,
                    )
                    if result is not None and result["should_break"]:
                        print(f"ChatKit server: Drained {drained_count} events from initial queue (terminal event found)")
                        terminal_event = result["sse_event"]
                        break
                    
                    if result is not None and result["sse_event"]:
                        progress_events.append(result["sse_event"])
                except asyncio.QueueEmpty:
                    break
            print(f"ChatKit server: Drained {drained_count} events from initial queue")
        except Exception as e:
            print(f"ERROR during drain: {e}")
            import traceback
            traceback.print_exc()
        
        return (terminal_event, progress_events)

    async def _process_event(
        self,
        event: dict,
        thread: ThreadMetadata,
        context: RequestContext,
    ) -> dict | None:
        """Process a single event from the stream.
        
        Returns a dict with 'sse_event' and 'should_break' keys if the event should be yielded,
        otherwise returns None.
        """
        if is_completed_event(event):
            return await self._handle_completed_event(event, thread, context)
        
        if is_failed_event(event):
            return await self._handle_failed_event(event, thread, context)
        
        if is_cancelled_event(event):
            return await self._handle_cancelled_event(event, thread, context)
        
        return await self._handle_progress_event(event)

    async def _handle_completed_event(
        self,
        event: dict,
        thread: ThreadMetadata,
        context: RequestContext,
    ) -> dict:
        """Handle a completed event."""
        final_text = final_answer_from_event(event)
        payload = _payload(event)
        projects = payload.get("projects")
        print("YIELDING final assistant message")
        return await self._build_terminal_assistant_result(
            thread=thread,
            context=context,
            text=final_text,
            projects=projects,
        )

    async def _handle_failed_event(
        self,
        event: dict,
        thread: ThreadMetadata,
        context: RequestContext,
    ) -> dict:
        """Handle a failed event."""
        payload = _payload(event)
        error_message = (
            payload.get("error")
            or payload.get("message")
            or event.get("message")
            or "unknown error"
        )
        error_text = f"Agent failed: {error_message}"
        print("YIELDING failed assistant message")
        return await self._build_terminal_assistant_result(
            thread=thread,
            context=context,
            text=error_text,
        )

    async def _handle_cancelled_event(
        self,
        event: dict,
        thread: ThreadMetadata,
        context: RequestContext,
    ) -> dict:
        """Handle a cancelled event."""
        cancelled_text = "Agent run was cancelled."
        print("YIELDING cancelled assistant message")
        return await self._build_terminal_assistant_result(
            thread=thread,
            context=context,
            text=cancelled_text,
        )

    async def _handle_progress_event(self, event: dict) -> dict | None:
        """Handle a progress event."""
        print("YIELDING progress update")
        progress_event = progress_from_event(event)
        if progress_event.text:
            return {
                "sse_event": self._event_to_sse(progress_event),
                "should_break": False,
            }
        else:
            print(f"ignoring progress update: {event}")
            return None

    async def _build_terminal_assistant_result(
        self,
        *,
        thread: ThreadMetadata,
        context: RequestContext,
        text: str,
        projects: list | None = None,
    ) -> dict:
        """Build a terminal SSE result, persist the assistant message, and return it."""
        assistant_event = self._assistant_message(
            thread=thread,
            context=context,
            text=text,
            projects=projects,
        )
        await self._persist_message(thread.id, "assistant", text)
        return {
            "sse_event": self._event_to_sse(assistant_event),
            "should_break": True,
        }

    def _assistant_message(
        self,
        *,
        thread: ThreadMetadata,
        context: RequestContext,
        text: str,
        projects: list | None = None,
    ) -> ThreadItemDoneEvent:
        item = AssistantMessageItem(
            thread_id=thread.id,
            id=self.store.generate_item_id("message", thread, context),
            created_at=datetime.now(timezone.utc),
            content=[
                AssistantMessageContent(text=text),
            ],
        )
        
        # Note: projects are handled separately via event payload, not on the ChatKit item
        # ChatKit's AssistantMessageItem doesn't support dynamic fields
        event = ThreadItemDoneEvent(item=item)
        # Add thread_id to the event for UI to capture
        event_dict = event.model_dump()
        event_dict["thread_id"] = thread.id
        if projects:
            event_dict["projects"] = projects
        return ThreadItemDoneEvent(**event_dict)
