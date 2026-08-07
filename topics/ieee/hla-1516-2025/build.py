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
from scripts.faithful_renderer import load_faithful_layout_profile  # noqa: E402
from scripts.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE  # noqa: E402
from scripts.semantic_generation import generate as generate_semantic  # noqa: E402
from scripts.semantic_model import load_document_model  # noqa: E402

ROOT = Path(__file__).resolve().parent


def generate_blocks() -> object:
    model = load_document_model(ROOT, HLA_SOURCE)
    return generate_semantic(
        ROOT,
        ROOT / "output" / "semantic",
        source=HLA_SOURCE,
        dialect=HLA_LATEX_DIALECT,
        definition_ids=tuple(item.id for item in model.ordered_definitions()),
        requirement_ids=tuple(item.id for item in model.ordered_requirements()),
        content_block_ids=tuple(item.id for item in model.content_blocks),
        content_element_ids=tuple(item.id for item in model.content_elements),
        include_faithful_body=True,
        faithful_layout_profile=load_faithful_layout_profile(
            ROOT / "semantic" / "faithful-layout.json"
        ),
    )


CONFIG = BuildConfig(
    root=ROOT,
    clean_before_build=True,
    output_pdf=ROOT / "dist" / "ieee-std-1516-2025-framework-and-rules-recreation.pdf",
    semantic_generator=generate_blocks,
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
