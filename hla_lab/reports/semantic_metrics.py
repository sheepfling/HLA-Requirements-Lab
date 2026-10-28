"""Measure source-shape progress for the HLA document migrations."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from pathlib import Path
from types import MappingProxyType
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

from hla_lab.core.semantic_types import (
    ContentBlock,
    ContentBlockFile,
    ContentElement,
    ContentElementFile,
    TableFamily,
    TableFamilyFile,
)
from hla_lab.paths import DocumentResources, repository_root, resources
from hla_lab.publication.publication_registry import load_release_manifest

EXCLUDED_PARTS = frozenset({".trash", "build", "dist", "output"})
PAGE_FRAGMENT_PATTERN = re.compile(r"(?:^|-)page-\d+\.tex$", re.IGNORECASE)
CONTENT_BLOCK_INPUT_PATTERN = re.compile(r"\\input\{output/semantic/content-block-[^}]+\}")
DATA_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".yaml", ".yml"})
Record = TypeVar("Record", ContentBlock, ContentElement, TableFamily)
FileModel = TypeVar("FileModel", ContentBlockFile, ContentElementFile, TableFamilyFile)
RecordReader = Callable[[FileModel], tuple[Record, ...]]


class SemanticMetrics(BaseModel):
    """Typed source-shape metrics for one document root."""

    model_config = ConfigDict(frozen=True)

    document: str
    tex_files: int
    page_fragments: int
    page_fragment_ratio: float
    content_block_page_adapters: int
    content_block_page_coverage: float
    data_files: int
    content_blocks: int
    content_elements: int
    content_element_block_coverage: float
    table_families: int
    stable_id_markers: int
    fixed_coordinate_markers: int
    heading_markers: int
    definition_markers: int
    requirement_markers: int
    coordinate_share: float


MARKERS = MappingProxyType(
    {
        "stable_id_markers": re.compile(r"\\HLAStableID\b"),
        "fixed_coordinate_markers": re.compile(
            r"\\(?:HLA(?:Fixed|ClausePlaced|RulePlaced|Coordinate)[A-Za-z]*|HLAPlaced[A-Za-z]*)\b"
        ),
        "heading_markers": re.compile(
            r"\\(?:HLAClauseHeading|HLASubclauseHeading|HLADetailedRuleHeading|"
            r"HLASummaryRule|HLANormativeRuleStatement|pdfbookmark)\b"
        ),
        "definition_markers": re.compile(r"(?:\\begin\{hladefinition\}|\\HLADefinitionAt)"),
        "requirement_markers": re.compile(
            r"\\(?:HLANormativeRuleStatement|HLAFixedRule|HLASummaryRule|HLADetailedRuleHeading)\b"
        ),
    }
)


def _source_files(root: Path, suffix: str) -> tuple[Path, ...]:
    return tuple(
        path
        for path in root.rglob(f"*{suffix}")
        if not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
    )


def _marker_count(text: str, pattern: re.Pattern[str]) -> int:
    return len(pattern.findall(text))


def _authored_records(
    root: Path,
    model_type: type[FileModel],
    records: RecordReader[FileModel, Record],
) -> tuple[Record, ...]:
    """Load a known authored-record file through its Pydantic contract."""
    semantic_root = DocumentResources(root).semantic
    found: list[Record] = []
    for path in semantic_root.glob("*.json"):
        try:
            model = model_type.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError):
            continue
        found.extend(records(model))
    return tuple(found)


def _authored_record_count(
    root: Path,
    model_type: type[FileModel],
    records: RecordReader[FileModel, Record],
) -> int:
    """Count records from files of one known authored semantic type."""
    return len(_authored_records(root, model_type, records))


def _content_element_block_coverage(root: Path) -> float:
    """Return the fraction of authored content blocks linked to elements."""
    blocks_path = DocumentResources(root).semantic_file("content-blocks.json")
    if not blocks_path.is_file():
        return 0.0
    try:
        content_file = ContentBlockFile.model_validate_json(blocks_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return 0
    if not content_file.content_blocks:
        return 0
    covered = sum(bool(block.element_ids) for block in content_file.content_blocks)
    return round(covered / len(content_file.content_blocks), 4)


def measure_document(root: Path) -> SemanticMetrics:
    """Return source-shape metrics without writing an audit or report file."""
    tex_files = _source_files(root, ".tex")
    tex_text = [path.read_text(encoding="utf-8") for path in tex_files]
    page_fragments = tuple(
        path for path in tex_files if PAGE_FRAGMENT_PATTERN.search(path.name) is not None
    )
    page_adapters = tuple(
        path
        for path in page_fragments
        if CONTENT_BLOCK_INPUT_PATTERN.search(path.read_text(encoding="utf-8")) is not None
    )
    data_files = tuple(path for suffix in DATA_SUFFIXES for path in _source_files(root, suffix))
    marker_counts = {
        name: sum(_marker_count(text, pattern) for text in tex_text)
        for name, pattern in MARKERS.items()
    }
    return SemanticMetrics(
        document=root.as_posix(),
        tex_files=len(tex_files),
        page_fragments=len(page_fragments),
        page_fragment_ratio=round(len(page_fragments) / len(tex_files), 4) if tex_files else 0.0,
        content_block_page_adapters=len(page_adapters),
        content_block_page_coverage=round(len(page_adapters) / len(page_fragments), 4)
        if page_fragments
        else 0.0,
        data_files=len(data_files),
        content_blocks=_authored_record_count(
            root, ContentBlockFile, lambda file: file.content_blocks
        ),
        content_elements=_authored_record_count(
            root, ContentElementFile, lambda file: file.content_elements
        ),
        content_element_block_coverage=_content_element_block_coverage(root),
        table_families=_authored_record_count(
            root, TableFamilyFile, lambda file: file.table_families
        ),
        stable_id_markers=marker_counts["stable_id_markers"],
        fixed_coordinate_markers=marker_counts["fixed_coordinate_markers"],
        heading_markers=marker_counts["heading_markers"],
        definition_markers=marker_counts["definition_markers"],
        requirement_markers=marker_counts["requirement_markers"],
        coordinate_share=round(
            marker_counts["fixed_coordinate_markers"] / max(marker_counts["stable_id_markers"], 1),
            4,
        ),
    )


def discover_documents(repo_root: Path) -> tuple[Path, ...]:
    """Resolve all release-document roots from the source-controlled manifest."""
    manifest = load_release_manifest(resources(repo_root).release_manifest)
    return tuple(repo_root / project.root for project in manifest.projects)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "roots",
        nargs="*",
        type=Path,
        help="Document roots; defaults to all document-local build.py projects",
    )
    parser.add_argument("--root", type=Path, help="explicit corpus workspace root")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a compact table",
    )
    args = parser.parse_args()
    roots = tuple(path.resolve() for path in args.roots)
    if not roots:
        roots = discover_documents(repository_root(args.root))
    metrics = [measure_document(root).model_dump(mode="json") for root in roots]
    if args.json:
        print(json.dumps(metrics, indent=2))
        return
    columns = (
        "document",
        "tex_files",
        "page_fragments",
        "page_fragment_ratio",
        "stable_id_markers",
        "fixed_coordinate_markers",
        "heading_markers",
        "definition_markers",
        "requirement_markers",
        "data_files",
        "content_blocks",
        "content_elements",
        "content_element_block_coverage",
        "table_families",
    )
    print("\t".join(columns))
    for item in metrics:
        print("\t".join(str(item[column]) for column in columns))


if __name__ == "__main__":
    main()
