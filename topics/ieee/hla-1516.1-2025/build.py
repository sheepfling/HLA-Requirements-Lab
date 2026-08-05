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
from scripts.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE  # noqa: E402
from scripts.semantic_generation import generate as generate_semantic  # noqa: E402

ROOT = Path(__file__).parent


def generate_blocks() -> object:
    return generate_semantic(
        ROOT,
        ROOT / "output" / "semantic",
        source=HLA_SOURCE,
        dialect=HLA_LATEX_DIALECT,
        requirement_ids=(
            "req-federate-connect-before-rti-work",
            "req-federate-connection-lost",
            "req-federate-disconnect-after-resign",
            "req-connect-service-establishes-connection",
            "req-disconnect-service-terminates-connection",
            "req-connection-lost-service-behavior",
            "req-federate-resigned-callback-behavior",
        ),
        content_block_ids=(
            "prose-federate-lifetime-initial-state",
            "prose-connect-service-infrastructure",
            "prose-federate-lifetime-parallel-machines",
        ),
    )


CONFIG = BuildConfig(
    root=ROOT,
    clean_before_build=True,
    output_pdf=ROOT
    / "dist"
    / "ieee-std-1516.1-2025-federate-interface-specification-recreation.pdf",
    semantic_generator=generate_blocks,
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
