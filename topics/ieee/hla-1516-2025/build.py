"""Repository-standard build entry point for IEEE Std 1516-2025."""

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

ROOT = Path(__file__).resolve().parent
CONFIG = BuildConfig(
    root=ROOT,
    clean_before_build=True,
    output_pdf=ROOT / "dist" / "ieee-std-1516-2025-framework-and-rules-recreation.pdf",
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "clean"))
    args = parser.parse_args()
    if args.command == "build":
        print(build_document(CONFIG))
    else:
        clean_document(ROOT)


if __name__ == "__main__":
    main()
