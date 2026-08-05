"""Build the programmatic HLA semantic derivative document."""

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
from scripts.generate_derivative import generate_from_hla  # noqa: E402

ROOT = Path(__file__).resolve().parent
SOURCE_ROOTS = tuple(
    REPO_ROOT / "topics" / "ieee" / name
    for name in ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025")
)


def generate_blocks() -> object:
    return generate_from_hla(SOURCE_ROOTS, ROOT / "output" / "semantic")


CONFIG = BuildConfig(
    root=ROOT,
    clean_before_build=True,
    output_pdf=ROOT / "dist" / "hla-semantic-derivative-2025.pdf",
    semantic_generator=generate_blocks,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "clean"))
    args = parser.parse_args()
    if args.action == "build":
        print(build_document(CONFIG))
    else:
        clean_document(ROOT)


if __name__ == "__main__":
    main()
