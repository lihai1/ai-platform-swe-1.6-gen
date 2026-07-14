"""pexpect-based process runner for the CrewAI worker."""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
import signal
import time
from pathlib import Path
from typing import Callable, Optional

import pexpect

from agent_worker.events import (
    state_cancelled,
    state_completed,
    state_failed,
    state_output,
    state_waiting_input,
    chat_final,
    chat_progress,
)
from agent_worker.nats_client import CrewAINatsClient
from agent_worker.prompt_detection import extract_prompt_text, looks_like_input_prompt

logger = logging.getLogger(__name__)


class RunnerError(Exception):
    """Error from the process runner."""

    def __init__(self, message: str, reason: str = "runner_error"):
        super().__init__(message)
        self.reason = reason
        self.message = message


class ProcessRunner:
    """Run a child process with pexpect, stream output, and handle input."""

    def __init__(
        self,
        nats: CrewAINatsClient,
        command: str,
        cwd: Path,
        input_idle_seconds: float = 30.0,
        output_max_buffer_chars: int = 8000,
        command_timeout: Optional[int] = None,
    ):
        self.nats = nats
        self.command = command
        self.cwd = cwd
        self.input_idle_seconds = input_idle_seconds
        self.output_max_buffer_chars = output_max_buffer_chars
        self.command_timeout = command_timeout
        self.child: Optional[pexpect.spawn] = None
        self._cancelled = False
        self._waiting_input = False
        self._input_event: Optional[asyncio.Event] = None
        self._pending_input: Optional[str] = None
        self._full_output: list[str] = []
        self._process_started: bool = False

    async def run(self) -> None:
        """Run the command and stream events until completion."""
        logger.info("Running command: %s in %s", self.command, self.cwd)
        args = ["bash", "-lc", self.command]
        env = os.environ.copy()
        env.setdefault("PYTHONUNBUFFERED", "1")
        env.setdefault("FORCE_COLOR", "0")

        try:
            self.child = pexpect.spawn(
                args[0],
                args[1:],
                cwd=str(self.cwd),
                env=env,
                encoding="utf-8",
                codec_errors="replace",
                timeout=self.input_idle_seconds,
                maxread=65536,
                searchwindowsize=200,
                echo=False,
            )
        except Exception as e:
            await self._publish_failure(f"Failed to spawn process: {e}")
            return

        await self.nats.publish_state(
            "started",
            {
                "status": "started",
                "command": self.command,
                "cwd": str(self.cwd),
            },
        )
        self._process_started = True

        try:
            await self._read_loop()
        except Exception as e:
            logger.exception("Runner loop failed")
            await self._publish_failure(f"Runner loop error: {e}")
        finally:
            await self._cleanup()

    async def _read_loop(self) -> None:
        """Read child output until EOF or timeout."""
        buffer = ""
        last_output_time = time.monotonic()

        while self.child and self.child.isalive():
            try:
                index = await self.child.expect(
                    ["\n", "\r", pexpect.EOF, pexpect.TIMEOUT],
                    timeout=0.1,
                    async_=True,
                )
            except pexpect.exceptions.TIMEOUT:
                index = 3
            except pexpect.exceptions.EOF:
                index = 2

            if index in (0, 1):
                chunk = self.child.before
                if chunk is None:
                    chunk = ""
                chunk += self.child.match.group(0) if self.child.match else ""
                buffer, last_output_time = await self._process_chunk(
                    buffer + chunk, last_output_time
                )
            elif index == 2:
                # EOF
                if buffer:
                    await self._flush_buffer(buffer)
                break
            elif index == 3:
                # Timeout: check for pending input and idle prompt detection
                if buffer:
                    idle = time.monotonic() - last_output_time
                    if idle >= self.input_idle_seconds:
                        if looks_like_input_prompt(buffer):
                            await self._handle_input_prompt(buffer)
                            buffer = ""
                        else:
                            await self._flush_buffer(buffer)
                            buffer = ""

        # Collect remaining output
        try:
            remaining = self.child.read()
            if remaining:
                await self._flush_buffer(remaining)
        except Exception:
            pass

        # Final output from remaining buffer
        if buffer:
            await self._flush_buffer(buffer)

        if self._cancelled:
            await self._publish_cancelled()
            return

        exit_code = self.child.exitstatus
        if exit_code is None:
            try:
                exit_code = self.child.wait() or 0
            except Exception:
                exit_code = 1

        if exit_code == 0:
            final_content = "\n".join(self._full_output).strip()
            if not final_content:
                final_content = "CrewAI run completed successfully."
            await self.nats.publish_state(
                "completed",
                state_completed(self.nats.run_id, self.nats.uid, exit_code=0)["payload"],
            )
            await self.nats.publish_chat(
                "final_answer",
                chat_final(
                    self.nats.run_id,
                    self.nats.uid,
                    content=final_content,
                    status="completed",
                )["payload"],
            )
        else:
            await self._publish_failure(
                f"Process exited with code {exit_code}",
                exit_code=exit_code,
            )

    async def _process_chunk(self, text: str, last_output_time: float) -> tuple[str, float]:
        """Accumulate and possibly flush output."""
        if len(text) >= self.output_max_buffer_chars:
            await self._flush_buffer(text)
            return "", time.monotonic()
        return text, last_output_time

    async def _flush_buffer(self, text: str) -> None:
        """Publish buffered output as state and chat events."""
        if not text:
            return
        clean_text = text.replace("\r", "")
        self._full_output.append(clean_text)
        await self.nats.publish_state(
            "output",
            state_output(
                self.nats.run_id,
                self.nats.uid,
                data=clean_text,
                stream="stdout",
            )["payload"],
        )
        await self.nats.publish_chat(
            "progress_update",
            chat_progress(
                self.nats.run_id,
                self.nats.uid,
                message=clean_text,
            )["payload"],
        )

    async def _handle_input_prompt(self, text: str) -> None:
        """Publish a waiting_input state and wait for user input."""
        prompt = extract_prompt_text(text)
        logger.info("Detected input prompt: %s", prompt)
        await self.nats.publish_state(
            "waiting_input",
            state_waiting_input(
                self.nats.run_id,
                self.nats.uid,
                prompt=prompt,
                reason="process_idle",
            )["payload"],
        )
        await self.nats.publish_chat(
            "progress_update",
            chat_progress(
                self.nats.run_id,
                self.nats.uid,
                message=f"Waiting for input: {prompt}",
            )["payload"],
        )
        self._waiting_input = True

    async def _send_input(self, user_input: str) -> None:
        """Send user input to the child process and echo it."""
        if not self.child or not self.child.isalive():
            return
        line = user_input.rstrip("\n") + "\n"
        self.child.sendline(line)
        await self.nats.publish_state(
            "output",
            state_output(
                self.nats.run_id,
                self.nats.uid,
                data=f"{line}",
                stream="stdin",
            )["payload"],
        )
        self._waiting_input = False

    async def handle_user_input(self, data: dict) -> None:
        """Handle a user input event from NATS."""
        user_input = data.get("input") or data.get("text") or data.get("content")
        if not user_input:
            logger.warning("Received user_input event without text: %s", data)
            return
        logger.info("Received user input for run %s", self.nats.run_id)
        
        # Check if process is still running
        if not self.child or not self.child.isalive():
            if self._process_started:
                # Process already ran and completed
                logger.warning("Process already completed, cannot send more input")
                await self.nats.publish_chat(
                    "final_answer",
                    {"message": "The agent has completed its task. Please start a new conversation."}
                )
                return
            else:
                # Process never started, start it now
                logger.info("Process not started yet, starting...")
                await self.run()
                return
        
        # Process is running, send input directly
        self.child.sendline(user_input)
        await self.nats.publish_state(
            "output",
            {"data": f"{user_input}\n", "stream": "stdin"},
        )

    async def cancel(self) -> None:
        """Cancel the running process."""
        self._cancelled = True
        if self.child and self.child.isalive():
            try:
                self.child.sendintr()  # SIGINT
                await asyncio.sleep(1.0)
                if self.child.isalive():
                    self.child.sendeof()
                    await asyncio.sleep(1.0)
                if self.child.isalive():
                    self.child.kill(9)
            except Exception as e:
                logger.warning("Failed to terminate process: %s", e)

    async def _publish_failure(self, error: str, exit_code: Optional[int] = None) -> None:
        """Publish failed state and final answer error."""
        await self.nats.publish_state(
            "failed",
            state_failed(
                self.nats.run_id,
                self.nats.uid,
                error=error,
                reason="process_error",
                exit_code=exit_code,
            )["payload"],
        )
        await self.nats.publish_chat(
            "final_answer",
            chat_final(
                self.nats.run_id,
                self.nats.uid,
                content=error,
                status="failed",
                error=True,
            )["payload"],
        )

    async def _publish_cancelled(self) -> None:
        """Publish cancelled state and final answer."""
        await self.nats.publish_state(
            "cancelled",
            state_cancelled(
                self.nats.run_id,
                self.nats.uid,
                reason="control_close_received",
            )["payload"],
        )
        await self.nats.publish_chat(
            "final_answer",
            chat_final(
                self.nats.run_id,
                self.nats.uid,
                content="CrewAI run was cancelled.",
                status="cancelled",
                error=True,
            )["payload"],
        )

    async def _cleanup(self) -> None:
        """Close the child process."""
        if self.child and self.child.isalive():
            try:
                self.child.close(force=True)
            except Exception:
                pass

    @property
    def waiting_input(self) -> bool:
        return self._waiting_input
