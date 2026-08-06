"""Measure source-shape progress for the HLA document migrations."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

EXCLUDED_PARTS = {".trash", "build", "dist", "output"}
PAGE_FRAGMENT_PATTERN = re.compile(r"(?:^|-)page-\d+\.tex$", re.IGNORECASE)
CONTENT_BLOCK_INPUT_PATTERN = re.compile(r"\\input\{output/semantic/content-block-[^}]+\}")
DATA_SUFFIXES = {".csv", ".json", ".jsonl", ".yaml", ".yml"}

MARKERS = {
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


def _source_files(root: Path, suffix: str) -> tuple[Path, ...]:
    return tuple(
        path
        for path in root.rglob(f"*{suffix}")
        if not EXCLUDED_PARTS.intersection(path.relative_to(root).parts)
    )


def _marker_count(text: str, pattern: re.Pattern[str]) -> int:
    return len(pattern.findall(text))


def _authored_record_count(root: Path, field: str) -> int:
    """Count text-based authored records without reading generated output."""
    semantic_root = root / "semantic"
    total = 0
    for path in semantic_root.glob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        values = payload.get(field, ()) if isinstance(payload, dict) else ()
        if isinstance(values, list):
            total += len(values)
    return total


def measure_document(root: Path) -> dict[str, object]:
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
    metrics: dict[str, object] = {
        "document": root.as_posix(),
        "tex_files": len(tex_files),
        "page_fragments": len(page_fragments),
        "page_fragment_ratio": round(len(page_fragments) / len(tex_files), 4) if tex_files else 0.0,
        "content_block_page_adapters": len(page_adapters),
        "content_block_page_coverage": round(len(page_adapters) / len(page_fragments), 4)
        if page_fragments
        else 0.0,
        "data_files": len(data_files),
        "content_blocks": _authored_record_count(root, "content_blocks"),
        "content_elements": _authored_record_count(root, "content_elements"),
        "content_element_block_coverage": _content_element_block_coverage(root),
        "table_families": _authored_record_count(root, "table_families"),
    }
    for name, pattern in MARKERS.items():
        metrics[name] = sum(_marker_count(text, pattern) for text in tex_text)
    metrics["coordinate_share"] = round(
        metrics["fixed_coordinate_markers"] / max(metrics["stable_id_markers"], 1), 4
    )
    return metrics


def _content_element_block_coverage(root: Path) -> float:
    """Return the fraction of authored content blocks linked to elements."""
    blocks_path = root / "semantic" / "content-blocks.json"
    if not blocks_path.is_file():
        return 0.0
    try:
        payload = json.loads(blocks_path.read_text(encoding="utf-8"))
        blocks = payload.get("content_blocks", [])
    except (OSError, json.JSONDecodeError):
        return 0.0
    if not blocks:
        return 0.0
    covered = sum(bool(item.get("element_ids")) for item in blocks if isinstance(item, dict))
    return round(covered / len(blocks), 4)


def discover_documents(repo_root: Path) -> tuple[Path, ...]:
    """Find document roots that expose a document-local build entry point."""
    return tuple(sorted(path.parent for path in repo_root.glob("topics/*/*/build.py")))


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
    repo_root = Path(__file__).resolve().parent.parent
    roots = tuple(path.resolve() for path in args.roots) or discover_documents(repo_root)
    metrics = [measure_document(root) for root in roots]
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
