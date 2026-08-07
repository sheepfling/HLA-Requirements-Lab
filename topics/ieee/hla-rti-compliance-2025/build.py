"""Build the generated HLA RTI compliance requirements publication."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from scripts.compliance_publication import (  # noqa: E402, I001
    load_compliance_publication_profile,
    write_compliance_publication,
)
from scripts.corpus_graph import build_corpus_graph, load_document_metadata  # noqa: E402
from scripts.document_builder import (  # noqa: E402
    BuildConfig,
    build as build_document,
    clean as clean_document,
)
from scripts.hla_semantic import load_hla_corpus  # noqa: E402

ROOT = Path(__file__).resolve().parent
SOURCE_ROOTS = tuple(
    REPO_ROOT / "topics" / "ieee" / name
    for name in ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025")
)


def generate_blocks() -> object:
    """Generate the human and machine-readable compliance projections."""
    corpus = load_hla_corpus(SOURCE_ROOTS)
    profile = load_compliance_publication_profile(ROOT / "semantic" / "publication.json")
    metadata = load_document_metadata(
        REPO_ROOT / "topics" / "ieee" / "hla-semantic-derivative-2025" / "semantic" / "corpus.json"
    )
    graph = build_corpus_graph(corpus, metadata=metadata)
    return write_compliance_publication(
        corpus,
        profile,
        ROOT / "output" / "compliance",
        graph=graph,
        csv_output=ROOT / "output" / "compliance" / "csv",
    )


CONFIG = BuildConfig(
    root=ROOT,
    clean_before_build=False,
    output_pdf=ROOT / "dist" / "hla-rti-compliance-requirements-2025.pdf",
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
