"""Workspace manager for Docker-based isolated workspaces"""
import asyncio
import docker
from docker.errors import DockerException, APIError
from typing import Optional, Dict, Any, List
import uuid
import tempfile
import shutil
import os
from datetime import datetime
import signal
import logging

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """Manages isolated Docker workspaces for agent execution"""
    
    def __init__(
        self,
        docker_client: Optional[docker.DockerClient] = None,
        default_image: str = "python:3.12-slim",
        cpu_limit: Optional[int] = None,
        memory_limit: Optional[str] = "2g",
        network_disabled: bool = True,
        command_timeout: int = 300,
        total_timeout: int = 3600,
    ):
        self.docker_client = docker_client or docker.from_env()
        self.default_image = default_image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.network_disabled = network_disabled
        self.command_timeout = command_timeout
        self.total_timeout = total_timeout
        
        # Command allowlist for safe execution
        self.command_allowlist = {
            "go": ["build", "test", "run", "fmt", "vet", "mod"],
            "npm": ["test", "build", "install", "run"],
            "pytest": [],
            "ginkgo": [],
            "make": ["build", "test", "run", "lint", "fmt"],
            "git": ["status", "diff", "log", "checkout", "branch", "add"],
            "python": ["-m", "pytest"],
        }
    
    async def create_workspace(
        self,
        chat_id: str,
        repository_url: str,
        repository_credentials: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create an isolated workspace for a chat"""
        workspace_id = f"workspace-{chat_id}"
        volume_name = f"workspace-volume-{chat_id}"
        branch_name = f"run-{chat_id}"
        
        try:
            # Create volume for workspace
            volume = self.docker_client.volumes.create(
                name=volume_name,
                driver="local",
            )
            
            # Create container with resource limits
            container = self.docker_client.containers.create(
                image=self.default_image,
                name=workspace_id,
                volumes={volume_name: {"bind": "/workspace", "mode": "rw"}},
                network_mode="none" if self.network_disabled else "bridge",
                mem_limit=self.memory_limit,
                cpu_quota=self.cpu_limit * 100000 if self.cpu_limit else None,
                cpu_period=100000 if self.cpu_limit else None,
                user="1000:1000",  # Non-root user
                detach=True,
                tty=True,
                working_dir="/workspace",
            )
            
            # Start container
            container.start()
            
            # Clone repository into workspace
            await self._clone_repository(
                container,
                repository_url,
                repository_credentials,
                branch_name,
            )
            
            return {
                "workspace_id": workspace_id,
                "volume_name": volume_name,
                "container_id": container.id,
                "branch_name": branch_name,
                "status": "created",
                "created_at": datetime.utcnow().isoformat(),
            }
            
        except (DockerException, APIError) as e:
            logger.error(f"Failed to create workspace: {e}")
            # Cleanup on failure
            await self.cleanup_workspace(workspace_id, volume_name)
            raise
    
    async def _clone_repository(
        self,
        container,
        repository_url: str,
        credentials: Optional[Dict[str, str]],
        branch_name: str,
    ) -> None:
        """Clone repository into the workspace container"""
        # Install git in container
        container.exec_run("apt-get update && apt-get install -y git", workdir="/")
        
        # Clone repository
        if credentials:
            # Use credentials for private repos
            clone_url = repository_url.replace(
                "https://",
                f"https://{credentials.get('username')}:{credentials.get('token')}@"
            )
        else:
            clone_url = repository_url
        
        exit_code, output = container.exec_run(
            f"git clone {clone_url} /workspace/repo",
            workdir="/workspace"
        )
        
        if exit_code != 0:
            raise RuntimeError(f"Failed to clone repository: {output.decode()}")
        
        # Create and checkout run-specific branch
        container.exec_run(
            f"cd /workspace/repo && git checkout -b {branch_name}",
            workdir="/workspace"
        )
    
    async def execute_command(
        self,
        workspace_id: str,
        command: List[str],
        workdir: str = "/workspace/repo",
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Execute a command in the workspace"""
        timeout = timeout or self.command_timeout
        
        # Validate command against allowlist
        if not self._is_command_allowed(command):
            raise ValueError(f"Command not allowed: {' '.join(command)}")
        
        try:
            container = self.docker_client.containers.get(workspace_id)
            
            # Execute command with timeout
            exec_id = container.client.api.exec_create(
                container.id,
                command,
                workdir=workdir,
                stdout=True,
                stderr=True,
            )
            
            # Wait for completion with timeout
            start_time = datetime.utcnow()
            output = container.client.api.exec_start(
                exec_id,
                timeout=timeout,
            )
            exec_info = container.client.api.exec_inspect(exec_id)
            
            duration = (datetime.utcnow() - start_time).total_seconds()
            
            return {
                "exit_code": exec_info["ExitCode"],
                "stdout": output.decode() if output else "",
                "stderr": exec_info.get("Stderr", ""),
                "duration": duration,
                "command": " ".join(command),
            }
            
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": str(e),
                "duration": 0,
                "command": " ".join(command),
            }
    
    def _is_command_allowed(self, command: List[str]) -> bool:
        """Check if command is in the allowlist"""
        if not command:
            return False
        
        base_command = command[0]
        
        # Check exact command match
        if base_command in self.command_allowlist:
            if not self.command_allowlist[base_command]:
                return True  # No subcommand restrictions
            
            # Check subcommand
            if len(command) > 1 and command[1] in self.command_allowlist[base_command]:
                return True
        
        return False
    
    async def get_file_contents(
        self,
        workspace_id: str,
        file_path: str,
    ) -> str:
        """Read file contents from workspace"""
        try:
            container = self.docker_client.containers.get(workspace_id)
            
            exit_code, output = container.exec_run(
                f"cat {file_path}",
                workdir="/workspace/repo"
            )
            
            if exit_code != 0:
                raise RuntimeError(f"Failed to read file: {output.decode()}")
            
            return output.decode()
            
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            raise
    
    async def write_file(
        self,
        workspace_id: str,
        file_path: str,
        content: str,
    ) -> None:
        """Write file contents to workspace"""
        try:
            container = self.docker_client.containers.get(workspace_id)
            
            # Create parent directories if needed
            exit_code, _ = container.exec_run(
                f"mkdir -p {os.path.dirname(file_path)}",
                workdir="/workspace/repo"
            )
            
            if exit_code != 0:
                raise RuntimeError("Failed to create directories")
            
            # Write file
            exit_code, output = container.exec_run(
                f"cat > {file_path} << 'EOF'\n{content}\nEOF",
                workdir="/workspace/repo"
            )
            
            if exit_code != 0:
                raise RuntimeError(f"Failed to write file: {output.decode()}")
            
        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            raise
    
    async def get_diff(
        self,
        workspace_id: str,
    ) -> str:
        """Get git diff from workspace"""
        try:
            container = self.docker_client.containers.get(workspace_id)
            
            exit_code, output = container.exec_run(
                "git diff",
                workdir="/workspace/repo"
            )
            
            if exit_code != 0:
                return ""
            
            return output.decode()
            
        except Exception as e:
            logger.error(f"Failed to get diff: {e}")
            return ""
    
    async def get_status(
        self,
        workspace_id: str,
    ) -> Dict[str, Any]:
        """Get git status from workspace"""
        try:
            container = self.docker_client.containers.get(workspace_id)
            
            exit_code, output = container.exec_run(
                "git status --porcelain",
                workdir="/workspace/repo"
            )
            
            if exit_code != 0:
                return {"modified": [], "added": [], "deleted": []}
            
            status_lines = output.decode().strip().split("\n")
            modified = []
            added = []
            deleted = []
            
            for line in status_lines:
                if not line:
                    continue
                status = line[:2]
                file_path = line[3:]
                
                if "M" in status:
                    modified.append(file_path)
                if "A" in status:
                    added.append(file_path)
                if "D" in status:
                    deleted.append(file_path)
            
            return {
                "modified": modified,
                "added": added,
                "deleted": deleted,
            }
            
        except Exception as e:
            logger.error(f"Failed to get status: {e}")
            return {"modified": [], "added": [], "deleted": []}
    
    async def cleanup_workspace(
        self,
        workspace_id: str,
        volume_name: str,
    ) -> None:
        """Clean up workspace resources"""
        try:
            # Stop and remove container
            try:
                container = self.docker_client.containers.get(workspace_id)
                container.stop(timeout=10)
                container.remove()
            except:
                pass
            
            # Remove volume
            try:
                volume = self.docker_client.volumes.get(volume_name)
                volume.remove()
            except:
                pass
            
            logger.info(f"Cleaned up workspace: {workspace_id}")
            
        except Exception as e:
            logger.error(f"Failed to cleanup workspace: {e}")
    
    async def cleanup_all_workspaces(self) -> None:
        """Clean up all agent workspaces"""
        try:
            # Get all containers with workspace- prefix
            containers = self.docker_client.containers.list(
                all=True,
                filters={"name": "workspace-"}
            )
            
            for container in containers:
                try:
                    container.stop(timeout=10)
                    container.remove()
                except:
                    pass
            
            # Get all volumes with workspace-volume- prefix
            volumes = self.docker_client.volumes.list(
                filters={"name": "workspace-volume-"}
            )
            
            for volume in volumes:
                try:
                    volume.remove()
                except:
                    pass
            
            logger.info("Cleaned up all workspaces")
            
        except Exception as e:
            logger.error(f"Failed to cleanup all workspaces: {e}")
