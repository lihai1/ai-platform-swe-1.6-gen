"""Typed async wrappers around the existing final_patch_crewai engine."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from final_patch_crewai import (
    create_package_init,
    detect_package_name,
    get_python_files,
    is_src_layout,
    patch_file,
    patch_pyproject,
)
from crewai_expert.config import ExpertConfig
from crewai_expert.models import PatchResult

logger = logging.getLogger(__name__)


async def apply_patch(folder: Path, fingerprint: str, config: ExpertConfig) -> PatchResult:
    """Apply compatibility patches to a CrewAI project asynchronously."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _sync_patch, folder, fingerprint, config)


def _sync_patch(folder: Path, fingerprint: str, config: ExpertConfig) -> PatchResult:
    logger.info("[_sync_patch] folder=%s fingerprint=%s", folder, fingerprint)
    patched_files: list[str] = []
    warnings: list[str] = []

    try:
        package_name = detect_package_name(folder)
        src_layout = is_src_layout(folder)
        logger.info("[_sync_patch] package_name=%s src_layout=%s", package_name, src_layout)
    except Exception as exc:
        logger.error("[_sync_patch] layout detection failed: %s", exc)
        return PatchResult(
            success=False,
            patched_files=[],
            warnings=[],
            error=f"Could not detect package layout: {exc}",
            patch_plan_fingerprint=fingerprint,
        )

    try:
        create_package_init(folder, package_name, src_layout)
        init_file = (
            folder / "src" / package_name / "__init__.py"
            if src_layout
            else folder / package_name / "__init__.py"
        )
        if init_file.exists():
            patched_files.append(str(init_file))
    except Exception as exc:
        warnings.append(f"Init creation skipped: {exc}")

    try:
        patch_pyproject(folder)
        pyproject = folder / "pyproject.toml"
        if pyproject.exists():
            patched_files.append(str(pyproject))
    except Exception as exc:
        warnings.append(f"pyproject patching skipped: {exc}")

    py_files = list(get_python_files(folder))
    logger.info("[_sync_patch] patching %s files", len(py_files))
    for py_file in py_files:
        try:
            original = py_file.read_text(encoding="utf-8", errors="ignore")
            patch_file(
                py_file,
                package_name=package_name,
                src_layout=src_layout,
                project_dir=folder,
                ollama_url=config.ollama_url,
                ollama_model=config.ollama_model,
            )
            if py_file.read_text(encoding="utf-8", errors="ignore") != original:
                patched_files.append(str(py_file))
        except Exception as exc:
            warnings.append(f"Failed to patch {py_file}: {exc}")

    logger.info("[_sync_patch] patched_files=%s warnings=%s", len(patched_files), len(warnings))
    return PatchResult(
        success=True,
        patched_files=patched_files,
        warnings=warnings,
        patch_plan_fingerprint=fingerprint,
    )
