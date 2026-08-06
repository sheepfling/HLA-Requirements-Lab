"""Build the non-HLA document-family fixture through the shared builder."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parents[2]
sys.path.insert(0, str(REPO_ROOT))

from fixture_profile import DEMO_LATEX_DIALECT, DEMO_SOURCE  # noqa: E402, I001
from scripts.document_builder import (  # noqa: E402
    BuildConfig,
    build as build_document,
    clean as clean_document,
)
from scripts.semantic_generation import generate as generate_semantic  # noqa: E402


def generate_blocks() -> object:
    """Generate fixture inputs from its source vocabulary and semantic model."""
    return generate_semantic(
        ROOT,
        ROOT / "output" / "semantic",
        source=DEMO_SOURCE,
        dialect=DEMO_LATEX_DIALECT,
        definition_ids=("definition-widget",),
        requirement_ids=("requirement-widget-ready",),
        table_family_ids=("demo-table-family",),
        include_outline=True,
    )


CONFIG = BuildConfig(
    root=ROOT,
    clean_before_build=True,
    output_pdf=ROOT / "dist" / "non-hla-demo-2025.pdf",
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
