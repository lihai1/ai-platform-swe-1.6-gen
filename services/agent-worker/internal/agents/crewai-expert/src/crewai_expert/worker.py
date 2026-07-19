"""CrewAI expert worker lifecycle, NATS subscriptions, and graph interrupt handling."""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Any, Optional

from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from agent_worker.events import chat_final, state_failed
from agent_worker.nats_client import CrewAINatsClient
from agent_worker.worker import CrewAIWorker
from crewai_expert.config import ExpertConfig
from crewai_expert.graph import create_expert_graph
from crewai_expert.state import ExpertState

logger = logging.getLogger(__name__)


class CrewAIExpertWorker(CrewAIWorker):
    """Runs the durable sequential LangGraph expert workflow."""

    def __init__(self):
        super().__init__()
        self.config = ExpertConfig.from_base(self.config)
        self.graph: Optional[Any] = None
        self._graph_task: Optional[asyncio.Task] = None
        self._shutdown_event = asyncio.Event()
        self._input_queue: asyncio.Queue = asyncio.Queue()

    async def start(self) -> None:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
        logger.info("Starting CrewAI expert worker for run %s", self.config.run_id)

        self.nats = CrewAINatsClient(
            nats_url=self.config.nats_url,
            uid=self.config.uid,
            run_id=self.config.run_id,
            session_id=self.config.session_id,
        )
        await self.nats.connect()
        await self.nats.subscribe_user_events(self._handle_user_event)
        await self.nats.subscribe_control_close(self._handle_control_close)
        await self.nats.publish_control_ready()
        self._setup_signal_handlers()

        from internal.workflow.checkpointer import get_checkpointer

        checkpointer = await get_checkpointer()
        self.graph = create_expert_graph(self.nats, self.config, checkpointer=checkpointer)

        initial_state: ExpertState = {
            "run_id": self.config.run_id,
            "user_id": self.config.uid,
            "workspace_path": str(self.config.workspace_path),
            "requested_project_path": self.config.command or None,
            "resolved_folder": None,
            "projects": None,
            "selected_project": None,
            "selection_attempts": 0,
            "max_selection_attempts": self.config.max_selection_attempts,
            "project_summary": None,
            "approval_request_id": None,
            "approval_type": None,
            "allowed_approval_values": None,
            "approval_decision": None,
            "dependency_report": None,
            "patch_required": False,
            "patch_approved": False,
            "patch_plan_fingerprint": None,
            "patch_attempts": 0,
            "max_patch_attempts": self.config.max_patch_attempts,
            "patch_result": None,
            "command_spec": None,
            "sync_succeeded": False,
            "verify_succeeded": False,
            "verify_error": None,
            "cancel_requested": False,
            "exit_code": None,
            "stdout_tail": None,
            "stderr_tail": None,
            "status": "created",
            "error_code": None,
            "error_message": None,
        }
        graph_config = {"configurable": {"thread_id": self.config.run_id}}
        self._graph_task = asyncio.create_task(self._graph_loop(initial_state, graph_config))

        shutdown_task = asyncio.create_task(self._shutdown_event.wait())
        done, pending = await asyncio.wait(
            [self._graph_task, shutdown_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()

        if self._graph_task in done:
            try:
                await self._graph_task
            except Exception as exc:
                logger.exception("Graph run failed: %s", exc)
                await self._publish_failed(str(exc))

    async def _graph_loop(self, state: ExpertState, config: dict) -> None:
        next_input: Any = state
        while True:
            logger.info("[_graph_loop] invoking graph with input type=%s", type(next_input).__name__)
            try:
                result = await self.graph.ainvoke(next_input, config)
            except GraphInterrupt:
                resume_value = await self._input_queue.get()
                logger.info("[_graph_loop] resuming from GraphInterrupt with value=%s", resume_value)
                next_input = Command(resume=resume_value)
                continue
            except Exception as exc:
                logger.exception("Graph loop error")
                await self._publish_failed(str(exc))
                break

            if not isinstance(result, dict):
                logger.warning("[_graph_loop] graph result is not a dict: %s", result)
                break
            logger.info("[_graph_loop] graph result keys=%s status=%s", list(result.keys()), result.get("status"))
            # LangGraph returns an __interrupt__ sentinel when a node calls interrupt().
            if result.get("__interrupt__"):
                resume_value = await self._input_queue.get()
                logger.info("[_graph_loop] resuming from __interrupt__ with value=%s", resume_value)
                next_input = Command(resume=resume_value)
                continue
            status = result.get("status")
            if status in ("completed", "failed", "cancelled"):
                logger.info("[_graph_loop] terminal status=%s", status)
                break
            # The sequential graph should always terminate after one successful ainvoke.
            break

    async def _handle_user_event(self, data: dict) -> None:
        """Forward approval/process input into the graph or active ProcessRunner."""
        logger.info("[_handle_user_event] data=%s", data)
        event_type = data.get("type") or data.get("event_type")
        if event_type not in ("user_input", "prompt"):
            logger.info("[_handle_user_event] ignoring event_type=%s", event_type)
            return

        payload = data.get("payload", {})
        user_input = payload.get("input", "")
        project_path = payload.get("project_path", "")

        active = self._active_interrupt()
        approval_id = self._approval_request_id_from_interrupt(active) or payload.get("approval_request_id")
        logger.info("[_handle_user_event] active_interrupt=%s approval_id=%s", active, approval_id)

        value: dict[str, Any] = {"value": project_path or user_input}
        if approval_id:
            value["approval_request_id"] = approval_id

        logger.info("[_handle_user_event] queueing value=%s", value)
        self._input_queue.put_nowait(value)

        if self.config.active_runner and not active:
            await self.config.active_runner.handle_user_input(data)

    def _approval_request_id_from_interrupt(self, active: Any) -> Any:
        """Extract the approval_request_id stored in the original interrupt payload."""
        if not isinstance(active, dict):
            return None
        value = active.get("value")
        if isinstance(value, dict):
            return value.get("approval_request_id")
        return None

    def _active_interrupt(self) -> Any:
        """Return the first active LangGraph interrupt, if any."""
        if not self.graph:
            return None
        try:
            snapshot = self.graph.get_state({"configurable": {"thread_id": self.config.run_id}})
            for task in getattr(snapshot, "tasks", []) or []:
                interrupts = getattr(task, "interrupts", []) or []
                if interrupts:
                    return interrupts[0]
        except Exception:
            pass
        return None

    async def _handle_control_close(self) -> None:
        logger.info("Received control close")
        self.config.cancel_event.set()
        if self.config.active_runner:
            await self.config.active_runner.cancel()
        self._input_queue.put_nowait({"decision": "cancel"})
        self._shutdown_event.set()

    def _setup_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except Exception:
                pass

    async def stop(self) -> None:
        if self.config.cancel_event.is_set():
            return
        self.config.cancel_event.set()
        self._shutdown_event.set()
        logger.info("Stopping CrewAI expert worker")
        if self.config.active_runner:
            await self.config.active_runner.cancel()
        if self._graph_task and not self._graph_task.done():
            self._graph_task.cancel()
        if self.nats:
            await self.nats.close()

    async def _publish_failed(self, error: str) -> None:
        if not self.nats:
            return
        await self.nats.publish_state(
            "failed",
            state_failed(
                run_id=self.config.run_id,
                user_id=self.config.uid,
                error=error,
                reason="graph_error",
            )["payload"],
        )
        await self.nats.publish_chat(
            "final_answer",
            chat_final(
                run_id=self.config.run_id,
                user_id=self.config.uid,
                content=error,
                status="failed",
                error=True,
            )["payload"],
        )
