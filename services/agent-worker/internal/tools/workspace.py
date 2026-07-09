"""Workspace tools for file operations in container workspace"""
from typing import Dict, Any, List, Optional
import logging
import os
import subprocess
import asyncio

logger = logging.getLogger(__name__)


class WorkspaceTools:
    """Tools for interacting with the container workspace (local file system)"""
    
    def __init__(self, workspace_path: str = "/workspace"):
        self.workspace_path = workspace_path
    
    async def write_file(
        self,
        workspace_id: str,
        file_path: str,
        content: str,
    ) -> Dict[str, Any]:
        """Write a file to the workspace"""
        try:
            full_path = os.path.join(self.workspace_path, file_path.lstrip("/"))
            os.makedirs(os.path.dirname(full_path), exist_ok=True)
            
            with open(full_path, "w") as f:
                f.write(content)
            
            return {
                "success": True,
                "file_path": file_path,
                "message": f"Successfully wrote {file_path}"
            }
        except Exception as e:
            logger.error(f"Failed to write file: {e}")
            return {
                "success": False,
                "file_path": file_path,
                "error": str(e)
            }
    
    async def read_file(
        self,
        workspace_id: str,
        file_path: str,
    ) -> Dict[str, Any]:
        """Read a file from the workspace"""
        try:
            full_path = os.path.join(self.workspace_path, file_path.lstrip("/"))
            
            with open(full_path, "r") as f:
                content = f.read()
            
            return {
                "success": True,
                "file_path": file_path,
                "content": content
            }
        except Exception as e:
            logger.error(f"Failed to read file: {e}")
            return {
                "success": False,
                "file_path": file_path,
                "error": str(e)
            }
    
    async def apply_patch(
        self,
        workspace_id: str,
        patch_content: str,
    ) -> Dict[str, Any]:
        """Apply a patch to the workspace"""
        try:
            # Write patch to temp file
            patch_path = "/tmp/changes.patch"
            with open(patch_path, "w") as f:
                f.write(patch_content)
            
            # Apply patch using subprocess
            proc = await asyncio.create_subprocess_exec(
                "git", "apply", patch_path,
                cwd=self.workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "output": stdout.decode(),
                "error": stderr.decode()
            }
        except Exception as e:
            logger.error(f"Failed to apply patch: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def git_status(
        self,
        workspace_id: str,
    ) -> Dict[str, Any]:
        """Get git status from workspace"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "status", "--porcelain",
                cwd=self.workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            return {
                "success": True,
                "status": stdout.decode()
            }
        except Exception as e:
            logger.error(f"Failed to get git status: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def git_diff(
        self,
        workspace_id: str,
    ) -> Dict[str, Any]:
        """Get git diff from workspace"""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "diff",
                cwd=self.workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            return {
                "success": True,
                "diff": stdout.decode()
            }
        except Exception as e:
            logger.error(f"Failed to get git diff: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def run_tests(
        self,
        workspace_id: str,
        test_command: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run tests in the workspace"""
        try:
            if test_command is None:
                # Auto-detect test command based on repository
                test_command = await self._detect_test_command()
            
            proc = await asyncio.create_subprocess_exec(
                *test_command,
                cwd=self.workspace_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "output": stdout.decode(),
                "error": stderr.decode(),
            }
        except Exception as e:
            logger.error(f"Failed to run tests: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def _detect_test_command(self) -> List[str]:
        """Auto-detect appropriate test command"""
        # Check for common test files
        if os.path.exists(os.path.join(self.workspace_path, "go.mod")):
            return ["go", "test", "./..."]
        elif os.path.exists(os.path.join(self.workspace_path, "package.json")):
            return ["npm", "test"]
        elif os.path.exists(os.path.join(self.workspace_path, "Makefile")):
            return ["make", "test"]
        else:
            return ["echo", "No test command detected"]
