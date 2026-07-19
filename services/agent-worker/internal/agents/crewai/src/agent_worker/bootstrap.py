"""Workspace resolution, command detection, and runnable folder bootstrap."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, List, Dict
import re

import tomllib

logger = logging.getLogger(__name__)


WORKSPACE_ROOT = Path("/workspace")


class BootstrapError(Exception):
    """Error raised when the workspace or command cannot be resolved."""

    def __init__(
        self,
        reason: str,
        message: str,
        candidates: Optional[list[str]] = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.message = message
        self.candidates = candidates or []

    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "error": self.message,
            "candidates": self.candidates,
        }


def ensure_inside_workspace(path: Path) -> Path:
    """Resolve and validate that a path is inside the workspace."""
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        raise BootstrapError(
            "folder_not_found",
            f"Resolved folder does not exist: {path}",
        )
    try:
        resolved.relative_to(WORKSPACE_ROOT.resolve())
    except ValueError:
        raise BootstrapError(
            "outside_workspace",
            f"Resolved folder {resolved} is outside workspace {WORKSPACE_ROOT}",
        )
    return resolved


def is_runnable_folder(path: Path) -> bool:
    """Return True if a folder contains an identifiable entrypoint."""
    if not path.is_dir():
        return False
    if (path / "pyproject.toml").exists():
        return True
    if (path / "requirements.txt").exists():
        return True
    if (path / "main.py").exists():
        return True
    if (path / "src" / "main.py").exists():
        return True
    return False


def is_crewai_project(path: Path) -> bool:
    """Return True if a folder appears to be a CrewAI project."""
    if not path.is_dir():
        return False
    # Check for CrewAI-specific indicators
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            with pyproject.open("rb") as f:
                data = tomllib.load(f)
            # Check for crewai in dependencies or project name
            dependencies = data.get("project", {}).get("dependencies", [])
            for dep in dependencies:
                if "crewai" in str(dep).lower():
                    return True
        except Exception:
            pass
    # Check for crewai-specific files
    if (path / "crewai").exists() or (path / "src" / "crew").exists():
        return True
    return False


def find_crewai_projects_recursive(base: Path, max_depth: int = 5) -> List[Dict[str, str]]:
    """Recursively find all CrewAI projects under a base path.
    
    Returns a list of dicts with keys: name, path, main_file, description
    """
    projects = []
    
    def scan_directory(current: Path, depth: int):
        if depth > max_depth:
            return
        
        try:
            for child in current.iterdir():
                if child.is_dir() and not child.name.startswith('.'):
                    # Check if this is a CrewAI project
                    if is_crewai_project(child):
                        project_info = {
                            "name": child.name,
                            "path": str(child.relative_to(WORKSPACE_ROOT)),
                            "full_path": str(child),
                            "main_file": _detect_main_file(child),
                            "description": _extract_description(child)
                        }
                        projects.append(project_info)
                    else:
                        # Recursively scan subdirectories
                        scan_directory(child, depth + 1)
        except PermissionError:
            logger.warning("Permission denied scanning %s", current)
    
    scan_directory(base, 0)
    return projects


def _detect_main_file(folder: Path) -> str:
    """Detect the main Python file for a CrewAI project."""
    # Check for common main file patterns
    for main_file in ["main.py", "app.py", "crew.py", "run.py"]:
        if (folder / main_file).exists():
            return main_file
    # Check src directory
    if (folder / "src" / "main.py").exists():
        return "src/main.py"
    if (folder / "src" / "crew.py").exists():
        return "src/crew.py"
    # Default to main.py
    return "main.py"


def _extract_description(folder: Path) -> str:
    """Extract project description from README or pyproject.toml."""
    # Try README first
    for readme_name in ["README.md", "README.rst", "README.txt"]:
        readme = folder / readme_name
        if readme.exists():
            try:
                with readme.open() as f:
                    first_line = f.readline().strip()
                    # Remove markdown heading markers
                    return re.sub(r'^#+\s*', '', first_line)
            except Exception:
                pass
    
    # Try pyproject.toml
    pyproject = folder / "pyproject.toml"
    if pyproject.exists():
        try:
            with pyproject.open("rb") as f:
                data = tomllib.load(f)
            return data.get("project", {}).get("description", "")
        except Exception:
            pass
    
    return ""


def _find_runnable_folders(base: Path) -> list[Path]:
    """Find all runnable sub-folders under a base path."""
    candidates = []
    for child in base.iterdir():
        if child.is_dir() and is_runnable_folder(child):
            candidates.append(child)
    return candidates


def _resolve_folder_argument(folder: str) -> Path:
    """Resolve a folder argument to a path inside the workspace."""
    path = Path(folder)
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    return ensure_inside_workspace(path)


def resolve_runnable_folder(
    base_folder: str,
    example: Optional[str] = None,
) -> Path:
    """Resolve the actual runnable folder based on --folder and --example."""
    base = _resolve_folder_argument(base_folder)

    if example:
        target = base / example
        if not target.exists():
            raise BootstrapError(
                "example_not_found",
                f"Example folder '{example}' not found under {base}",
            )
        if not target.is_dir():
            raise BootstrapError(
                "example_not_folder",
                f"Example path '{example}' is not a folder: {target}",
            )
        return ensure_inside_workspace(target)

    if is_runnable_folder(base):
        return base

    runnable = _find_runnable_folders(base)
    if not runnable:
        raise BootstrapError(
            "no_runnable_folder",
            f"No runnable folder found under {base}",
        )
    if len(runnable) == 1:
        return runnable[0]

    names = [str(r.relative_to(WORKSPACE_ROOT)) for r in runnable]
    raise BootstrapError(
        "multiple_runnable_folders",
        f"Multiple runnable examples found under {base}; use --example to choose one",
        candidates=names,
    )


def read_pyproject_entrypoint(folder: Path) -> Optional[str]:
    """Check pyproject.toml for a [project.scripts] or [project] entry."""
    pyproject = folder / "pyproject.toml"
    if not pyproject.exists():
        return None
    try:
        with pyproject.open("rb") as f:
            data = tomllib.load(f)
    except Exception as e:
        logger.warning("Failed to parse pyproject.toml in %s: %s", folder, e)
        return None

    project = data.get("project", {})
    scripts = project.get("scripts", {})
    if scripts:
        # Prefer a script named "run" or the first one
        for name in ["run", "start", "main"]:
            if name in scripts:
                return name
        return next(iter(scripts.keys()))
    return None


def detect_command(folder: Path) -> str:
    """Detect the appropriate command to run a project."""
    folder_str = str(folder)
    pyproject = folder / "pyproject.toml"
    if pyproject.exists():
        entry_script = read_pyproject_entrypoint(folder)
        if entry_script:
            return f"bash -lc 'cd {folder_str} && pip install --break-system-packages -e . && {entry_script}'"
        # Default crewai pyproject pattern
        return f"bash -lc 'cd {folder_str} && pip install --break-system-packages -e . && crewai run'"

    requirements = folder / "requirements.txt"
    main = folder / "main.py"
    src_main = folder / "src" / "main.py"

    if requirements.exists() and main.exists():
        return f"bash -lc 'cd {folder_str} && pip install --break-system-packages -r requirements.txt && python main.py'"
    if main.exists():
        return f"bash -lc 'cd {folder_str} && python main.py'"
    if src_main.exists():
        return f"bash -lc 'cd {folder_str} && python src/main.py'"

    raise BootstrapError(
        "no_runnable_entrypoint",
        f"No runnable entrypoint found in {folder}",
    )
