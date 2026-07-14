"""Shared utility for loading code quality guidelines."""
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


def load_code_guidelines(workspace_path: str = "/workspace") -> str:
    """Load code quality guidelines from agents.md file.
    
    Args:
        workspace_path: Path to the workspace directory containing agents.md
        
    Returns:
        Formatted string with code quality guidelines, or empty string if not found
    """
    agents_md_path = Path(workspace_path) / "agents.md"
    if agents_md_path.exists():
        try:
            with open(agents_md_path, 'r') as f:
                content = f.read()
                return f"\n\n## Code Quality Guidelines\n{content}"
        except Exception as e:
            logger.warning(f"Failed to load agents.md: {e}")
    return ""
