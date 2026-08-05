"""Shared build runner for document recreation projects."""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BuildConfig:
    """Document-specific settings for the common builder."""

    root: Path
    clean_before_build: bool = False
    navigation_manifest: Path | None = None
    output_pdf: Path | None = None


def _run(command: list[str], *, cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def build(config: BuildConfig) -> Path:
    """Build the document and return its final PDF path."""
    if config.clean_before_build:
        _run(["latexmk", "-C", "main.tex"], cwd=config.root)

    _run(["latexmk", "-xelatex", "main.tex"], cwd=config.root)
    built_pdf = config.root / "build" / "main.pdf"
    if not built_pdf.is_file() or built_pdf.stat().st_size == 0:
        raise RuntimeError(f"Expected build output was not created: {built_pdf}")

    if config.navigation_manifest is None:
        if config.output_pdf is not None:
            config.output_pdf.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(built_pdf, config.output_pdf)
            return config.output_pdf
        return built_pdf

    if config.output_pdf is None:
        raise ValueError("output_pdf is required when navigation_manifest is configured")
    config.output_pdf.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            sys.executable,
            "tools/apply_pdf_navigation.py",
            str(built_pdf),
            str(config.navigation_manifest),
            str(config.output_pdf),
        ],
        cwd=config.root,
    )
    return config.output_pdf


def clean(root: Path) -> None:
    """Remove generated document output directories."""
    for name in ("build", "dist"):
        shutil.rmtree(root / name, ignore_errors=True)
