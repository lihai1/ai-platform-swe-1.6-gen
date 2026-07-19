"""CrewAI worker class for managing CrewAI project execution."""
from __future__ import annotations

import asyncio
import json
import logging
import signal
from pathlib import Path
from typing import Optional

from agent_worker.bootstrap import (
    BootstrapError,
    detect_command,
    resolve_runnable_folder,
    find_crewai_projects_recursive,
    WORKSPACE_ROOT,
)
from agent_worker.config import resolve_config
from agent_worker.nats_client import CrewAINatsClient
from agent_worker.runner import ProcessRunner

logger = logging.getLogger(__name__)


class CrewAIWorker:
    """High-level worker that bootstraps and runs a CrewAI project."""

    def __init__(self):
        self.config = resolve_config()
        self.nats: Optional[CrewAINatsClient] = None
        self.runner: Optional[ProcessRunner] = None
        self._shutting_down = False
        self._awaiting_project_selection = False
        self._resolved_folder: Optional[Path] = None
        self._command: Optional[str] = None

    async def start(self) -> None:
        """Connect to NATS and start the run."""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        logger.info("Starting CrewAI worker for run %s", self.config.run_id)

        self.nats = CrewAINatsClient(
            nats_url=self.config.nats_url,
            uid=self.config.uid,
            run_id=self.config.run_id,
            session_id=self.config.session_id,
        )
        await self.nats.connect()

        # Subscribe to user input and control close
        await self.nats.subscribe_user_events(self._handle_user_event)
        await self.nats.subscribe_control_close(self._handle_control_close)

        # Publish ready signal
        await self.nats.publish_control_ready()

        # Set up signal handlers once before any work begins.
        self._setup_signal_handlers()

        if self.config.example:
            # An explicit example path was provided; bootstrap and run it.
            bootstrap_success = await self._attempt_bootstrap()
            if bootstrap_success:
                await self._start_runner()
        else:
            # No example provided yet: scan for CrewAI projects, publish
            # the list, and wait for the user to select one.
            await self._scan_for_project_selection()

        # Keep the worker alive to receive user events and control close.
        while not self._shutting_down:
            await asyncio.sleep(1)

    async def _handle_user_event(self, data: dict) -> None:
        """Dispatch user input events to project selection or runner."""
        event_type = data.get("type") or data.get("event_type")
        if event_type in ("user_input", "prompt"):
            payload = data.get("payload", {})
            project_path = payload.get("project_path", "")
            user_input = payload.get("input", "")

            if project_path:
                logger.info("Received project path: %s", project_path)
                await self.handle_project_selection(project_path)
            elif self._awaiting_project_selection:
                logger.info("Received project selection: %s", user_input)
                await self.handle_project_selection(user_input)
            elif self.runner:
                await self.runner.handle_user_input(data)
        else:
            logger.info("Ignoring user event type: %s", event_type)

    async def _handle_control_close(self) -> None:
        """Handle control close by cancelling the runner and stopping the worker."""
        logger.info("Received control close, cancelling run")
        if self.runner:
            await self.runner.cancel()
        await self.stop()

    async def _publish_bootstrap_error(self, exc: BootstrapError) -> None:
        """Publish bootstrap failure as failed state and final answer."""
        if not self.nats:
            return
        from agent_worker.events import state_failed, chat_final

        await self.nats.publish_state(
            "failed",
            state_failed(
                self.config.run_id,
                self.config.uid,
                error=exc.message,
                reason=exc.reason,
                candidates=exc.candidates,
            )["payload"],
        )
        await self.nats.publish_chat(
            "final_answer",
            chat_final(
                self.config.run_id,
                self.config.uid,
                content=exc.message,
                status="failed",
                error=True,
            )["payload"],
        )

    async def _publish_crewai_projects(self, projects: list) -> None:
        """Publish discovered CrewAI projects as a chat event for user selection."""
        if not self.nats:
            return
        from agent_worker.events import chat_final

        projects_json = json.dumps(projects)

        await self.nats.publish_chat(
            "final_answer",
            chat_final(
                self.config.run_id,
                self.config.uid,
                content=projects_json,
                status="project_selection_required",
                error=False,
                projects=projects,
            )["payload"],
        )

    async def _scan_for_project_selection(self) -> None:
        """Scan for CrewAI projects and publish the list for user selection."""
        logger.info("Scanning workspace for CrewAI projects...")
        crewai_projects = find_crewai_projects_recursive(WORKSPACE_ROOT)

        if crewai_projects:
            logger.info("Found %d CrewAI projects", len(crewai_projects))
            await self._publish_crewai_projects(crewai_projects)
            self._awaiting_project_selection = True
            logger.info("Waiting for user to select a project...")
        else:
            logger.info("No CrewAI projects found in workspace")
            error = BootstrapError(
                "no_runnable_folder",
                "No CrewAI projects found in workspace",
            )
            await self._publish_bootstrap_error(error)

    async def _attempt_bootstrap(self) -> bool:
        """Attempt to bootstrap the worker. Returns True if successful."""
        try:
            self._resolved_folder = resolve_runnable_folder(
                self.config.folder,
                self.config.example,
            )
            self._command = self.config.command or detect_command(self._resolved_folder)
            logger.info("Resolved folder: %s", self._resolved_folder)
            logger.info("Resolved command: %s", self._command)
            return True
        except BootstrapError as e:
            logger.error("Bootstrap failed: %s", e.message)
            return await self._handle_bootstrap_failure(e)

    async def _handle_bootstrap_failure(self, error: BootstrapError) -> bool:
        """Handle bootstrap failure. Returns True if should retry."""
        if error.reason == "no_runnable_folder":
            await self._scan_for_project_selection()
            return False
        else:
            await self._publish_bootstrap_error(error)
            return False
    
    async def _start_runner(self) -> None:
        """Initialize and start the process runner."""
        if not self._resolved_folder or not self._command:
            logger.error("Cannot start runner: folder or command not resolved")
            return

        self.runner = ProcessRunner(
            nats=self.nats,
            command=self._command,
            cwd=self._resolved_folder,
            input_idle_seconds=self.config.input_idle_seconds,
            output_max_buffer_chars=self.config.output_max_buffer_chars,
            command_timeout=self.config.command_timeout_seconds,
        )

        try:
            await self.runner.run()
        finally:
            self.runner = None
    
    def _setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown."""
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
            except Exception:
                pass

    async def handle_project_selection(self, project_path: str) -> None:
        """Public handler to start a CrewAI project from a user-provided path."""
        logger.info("Handling project selection: %s", project_path)

        try:
            self._resolved_folder = resolve_runnable_folder(
                self.config.folder,
                project_path,
            )
            self._command = self.config.command or detect_command(self._resolved_folder)

            logger.info("Successfully resolved folder: %s", self._resolved_folder)
            logger.info("Resolved command: %s", self._command)

            # Clear awaiting state
            self._awaiting_project_selection = False
            
            # Start the runner
            await self._start_runner()

        except BootstrapError as e:
            logger.error("Project selection failed: %s", e.message)
            await self._publish_bootstrap_error(e)
            # Keep awaiting state true to allow another selection attempt
            self._awaiting_project_selection = True

    async def stop(self) -> None:
        """Stop the worker and close NATS."""
        if self._shutting_down:
            return
        self._shutting_down = True
        logger.info("Stopping CrewAI worker")
        if self.runner:
            await self.runner.cancel()
        if self.nats:
            await self.nats.close()

    @staticmethod
    async def start_worker(
        nats_url: str,
        uid: str,
        run_id: str,
        session_id: str,
        folder: str,
        example: Optional[str] = None,
        command: Optional[str] = None,
        input_idle_seconds: float = 30.0,
        output_max_buffer_chars: int = 8000,
        command_timeout_seconds: Optional[int] = None,
    ) -> "CrewAIWorker":
        """Static method to start a CrewAI worker with specific parameters.
        
        Args:
            nats_url: NATS server URL
            uid: User identifier
            run_id: Run identifier
            session_id: Session identifier
            folder: Base folder path
            example: Optional example/project path
            command: Optional command to run
            input_idle_seconds: Input idle timeout in seconds
            output_max_buffer_chars: Maximum output buffer size
            command_timeout_seconds: Optional command timeout
            
        Returns:
            CrewAIWorker instance
        """
        from agent_worker.config import WorkerConfig
        
        # Sanitize user_id for NATS subject compatibility
        sanitized_uid = uid.replace(":", "-")
        
        # Create worker with custom config
        worker = CrewAIWorker()
        worker.config = WorkerConfig(
            nats_url=nats_url,
            uid=sanitized_uid,
            run_id=run_id,
            session_id=session_id,
            folder=folder,
            example=example,
            command=command,
            input_idle_seconds=input_idle_seconds,
            output_max_buffer_chars=output_max_buffer_chars,
            command_timeout_seconds=command_timeout_seconds,
        )
        
        # Start the worker in background
        asyncio.create_task(worker.start())
        
        return worker
