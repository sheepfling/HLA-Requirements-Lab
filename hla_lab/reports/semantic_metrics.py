"""Measure source-shape progress for the HLA document migrations."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict, JsonValue

from hla_lab.paths import REPO_ROOT, DocumentResources, resources
from hla_lab.publication.publication_registry import load_release_manifest

EXCLUDED_PARTS = frozenset({".trash", "build", "dist", "output"})
PAGE_FRAGMENT_PATTERN = re.compile(r"(?:^|-)page-\d+\.tex$", re.IGNORECASE)
CONTENT_BLOCK_INPUT_PATTERN = re.compile(r"\\input\{output/semantic/content-block-[^}]+\}")
DATA_SUFFIXES = frozenset({".csv", ".json", ".jsonl", ".yaml", ".yml"})


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


def _read_json(path: Path) -> JsonValue | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _authored_record_count(root: Path, field: str) -> int:
    """Count text-based authored records without reading generated output."""
    semantic_root = DocumentResources(root).semantic
    total = 0
    for path in semantic_root.glob("*.json"):
        payload = _read_json(path)
        if payload is None:
            continue
        if isinstance(payload, dict):
            values: JsonValue | tuple[()] = payload.get(field, ())
            if isinstance(values, list):
                total += len(values)
    return total


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
        content_blocks=_authored_record_count(root, "content_blocks"),
        content_elements=_authored_record_count(root, "content_elements"),
        content_element_block_coverage=_content_element_block_coverage(root),
        table_families=_authored_record_count(root, "table_families"),
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


def _content_element_block_coverage(root: Path) -> float:
    """Return the fraction of authored content blocks linked to elements."""
    blocks_path = DocumentResources(root).semantic_file("content-blocks.json")
    if not blocks_path.is_file():
        return 0.0
    payload = _read_json(blocks_path)
    if payload is None:
        return 0.0
    if not isinstance(payload, dict):
        return 0.0
    raw_blocks: JsonValue | list[JsonValue] = payload.get("content_blocks", [])
    if not isinstance(raw_blocks, list) or not raw_blocks:
        return 0.0
    blocks: list[JsonValue] = raw_blocks
    covered = 0
    for raw_item in blocks:
        item: JsonValue = raw_item
        if isinstance(item, dict) and item.get("element_ids"):
            covered += 1
    return round(covered / len(blocks), 4)


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
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print machine-readable JSON instead of a compact table",
    )
    args = parser.parse_args()
    repo_root = REPO_ROOT
    roots = tuple(path.resolve() for path in args.roots) or discover_documents(repo_root)
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
