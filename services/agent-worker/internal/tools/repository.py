from typing import List, Optional, Dict, Any
from pathlib import Path
import os


class ReadOnlyRepositoryTools:
    """Read-only tools for repository operations"""
    
    def __init__(self, repository_path: Path):
        self.repository_path = repository_path
    
    def list_files(self, pattern: str = "*", recursive: bool = True) -> List[str]:
        """List files in the repository matching a pattern"""
        if recursive:
            files = list(self.repository_path.rglob(pattern))
        else:
            files = list(self.repository_path.glob(pattern))
        
        # Return relative paths
        return [str(f.relative_to(self.repository_path)) for f in files if f.is_file()]
    
    def read_file(self, file_path: str) -> str:
        """Read a file's contents"""
        full_path = self.repository_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not full_path.is_file():
            raise ValueError(f"Path is not a file: {file_path}")
        
        return full_path.read_text()
    
    def search_files(self, pattern: str, file_pattern: str = "*") -> List[Dict[str, Any]]:
        """Search for a pattern in files"""
        results = []
        
        for file_path in self.list_files(file_pattern, recursive=True):
            try:
                content = self.read_file(file_path)
                lines = content.split('\n')
                
                for line_num, line in enumerate(lines, 1):
                    if pattern.lower() in line.lower():
                        results.append({
                            "file": file_path,
                            "line": line_num,
                            "content": line.strip()
                        })
            except Exception:
                # Skip files that can't be read
                continue
        
        return results
    
    def get_directory_structure(self, max_depth: int = 3) -> Dict[str, Any]:
        """Get simplified directory structure"""
        def build_structure(path: Path, current_depth: int) -> Dict[str, Any]:
            if current_depth > max_depth:
                return {"type": "directory", "truncated": True}
            
            structure = {"type": "directory", "children": {}}
            
            try:
                for item in sorted(path.iterdir()):
                    if item.name.startswith('.'):
                        continue
                    
                    relative_name = item.name
                    if item.is_file():
                        structure["children"][relative_name] = {"type": "file"}
                    elif item.is_dir():
                        structure["children"][relative_name] = build_structure(item, current_depth + 1)
            except PermissionError:
                structure["error"] = "permission_denied"
            
            return structure
        
        return build_structure(self.repository_path, 0)
    
    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """Get information about a file"""
        full_path = self.repository_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        stat = full_path.stat()
        
        return {
            "path": file_path,
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "is_file": full_path.is_file(),
            "is_dir": full_path.is_dir(),
        }


class RepositoryMetadataTools:
    """Tools for fetching repository metadata from Go control plane API"""
    
    def __init__(self, control_plane_base_url: str, http_client):
        self.control_plane_base_url = control_plane_base_url
        self.http_client = http_client
    
    async def get_repository_metadata(self, repository_id: str) -> Dict[str, Any]:
        """Get repository metadata from control plane"""
        url = f"{self.control_plane_base_url}/api/v1/repositories/{repository_id}"
        
        response = await self.http_client.get(url)
        response.raise_for_status()
        
        return response.json()
    
    async def get_project_metadata(self, project_id: str) -> Dict[str, Any]:
        """Get project metadata from control plane"""
        url = f"{self.control_plane_base_url}/api/v1/projects/{project_id}"
        
        response = await self.http_client.get(url)
        response.raise_for_status()
        
        return response.json()
    
    async def get_repository_clone_url(self, repository_id: str) -> str:
        """Get clone URL for repository"""
        metadata = await self.get_repository_metadata(repository_id)
        return metadata.get("clone_url")
