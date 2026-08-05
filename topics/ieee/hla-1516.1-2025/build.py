"""Repository-level build entry point for IEEE HLA 1516.1-2025."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.document_builder import (  # noqa: E402, I001
    BuildConfig,
    build as build_document,
    clean as clean_document,
)

ROOT = Path(__file__).parent
CONFIG = BuildConfig(
    root=ROOT,
    clean_before_build=True,
    output_pdf=ROOT
    / "dist"
    / "ieee-std-1516.1-2025-federate-interface-specification-recreation.pdf",
)


def build() -> None:
    print(build_document(CONFIG))


def clean() -> None:
    clean_document(ROOT)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("build", "clean"))
    args = parser.parse_args()
    (build if args.action == "build" else clean)()
