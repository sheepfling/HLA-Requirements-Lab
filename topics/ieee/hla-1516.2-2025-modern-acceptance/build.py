"""Build the 1516.2-2025 modern interior acceptance slice."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
OUTPUT = DIST / "hla-requirements-lab-1516.2-2025-modern-acceptance-slice.pdf"


def build() -> None:
    BUILD.mkdir(exist_ok=True)
    DIST.mkdir(exist_ok=True)
    subprocess.run(
        ["latexmk", "-xelatex", "-interaction=nonstopmode", "main.tex"],
        cwd=ROOT,
        check=True,
    )
    shutil.copy2(BUILD / "main.pdf", OUTPUT)
    print(OUTPUT)


def clean() -> None:
    if BUILD.exists():
        shutil.rmtree(BUILD)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "clean"))
    args = parser.parse_args()
    (build if args.action == "build" else clean)()
