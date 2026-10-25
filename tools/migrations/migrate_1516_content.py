"""Move the 1516 faithful page bodies behind semantic content-block records.

This is a one-time source migration. The resulting JSON is authored source;
the generated TeX body files remain ignored build products. Page files remain
as thin physical-layout adapters and retain their original paths as
provenance, but no longer own the document prose.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from pydantic import JsonValue

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import _latex_text, load_document_model
from hla_lab.paths import RESOURCES, DocumentResources

PAGE_PATTERN = re.compile(r"page-(?P<number>\d+)\.tex$")
CLAUSE_PATTERNS = (
    re.compile(r"\\HLAContentMarker\{(?P<id>clause-[^}]+)\}"),
    re.compile(r"\\HLA(?:Sub)?clauseHeading(?:\[[^]]*\])?\{(?P<id>clause-[^}]+)\}"),
)


def _page_files(root: Path) -> tuple[Path, ...]:
    pages: list[tuple[int, Path]] = []
    for path in (root / "sections" / "semantic").rglob("page-*.tex"):
        match = PAGE_PATTERN.search(path.name)
        if match is not None:
            pages.append((int(match.group("number")), path))
    return tuple(path for _, path in sorted(pages, key=lambda item: (item[0], item[1].as_posix())))


def _clause_ids(text: str) -> tuple[str, ...]:
    values: list[str] = []
    for pattern in CLAUSE_PATTERNS:
        values.extend(match.group("id") for match in pattern.finditer(text))
    return tuple(dict.fromkeys(values))


def _semantic_text(text: str) -> str:
    without_inputs = re.sub(r"(?m)^\s*\\input\{output/semantic/[^}]+\}\s*$", "", text)
    without_layout_markers = re.sub(
        r"\\(?:HLAStart|HLAEnd|HLAContentMarker|HLAInstall)[A-Za-z]*\{[^{}]*\}",
        " ",
        without_inputs,
    )
    return re.sub(r"\s+", " ", _latex_text(without_layout_markers, HLA_SOURCE)).strip()


def migrate(root: Path) -> tuple[Path, Path]:
    """Write authored content blocks, canonical navigation, and page adapters."""
    model = load_document_model(root, HLA_SOURCE)
    pages = _page_files(root)
    counts: Counter[str] = Counter()
    records: list[dict[str, JsonValue]] = []

    for sequence, path in enumerate(pages, start=1):
        raw = path.read_text(encoding="utf-8")
        clauses = _clause_ids(raw)
        owner = clauses[0] if clauses else "front-matter"
        kind = "normative" if re.search(r"\bshall\b", raw, re.IGNORECASE) else "context"
        counter_key = f"{owner}-{kind}"
        counts[counter_key] += 1
        block_id = (
            f"content-{owner.removeprefix('clause-').replace('.', '-')}-"
            f"{kind}-{counts[counter_key]:03d}"
        )
        relative = path.relative_to(root).as_posix()
        records.append(
            {
                "id": block_id,
                "kind": kind,
                "text": _semantic_text(raw),
                "clause_id": clauses[0] if clauses else None,
                "record_ids": list(clauses),
                "source": {"path": relative, "line": 1, "end_line": raw.count("\n") + 1},
                "sequence": sequence,
                "layout_body": raw,
            }
        )
        adapter = (
            "% Semantic content adapter; prose is authored in semantic/content-blocks.json.\n"
            f"\\input{{output/semantic/content-block-{block_id}}}\n"
        )
        path.write_text(adapter, encoding="utf-8")

    semantic_path = DocumentResources(root).semantic_file("content-blocks.json")
    semantic_path.write_text(
        json.dumps({"schema_version": 2, "content_blocks": records}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )

    outline: list[JsonValue] = [item.model_dump(mode="json") for item in model.ordered_clauses()]
    for annex in model.annexes:
        outline.append(
            [
                0,
                f"Annex {annex.letter} ({annex.status}) {annex.title}",
            ]
        )
    navigation_path = DocumentResources(root).canonical_file("source-navigation.json")
    navigation_path.parent.mkdir(parents=True, exist_ok=True)
    navigation_path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "document": model.document_id,
                "outline": outline,
                "notes": "Canonical clause order and ownership for the data-driven 1516 build.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return semantic_path, navigation_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=RESOURCES.document("hla-1516-2025").root)
    args = parser.parse_args()
    semantic_path, navigation_path = migrate(args.root)
    print(semantic_path)
    print(navigation_path)


if __name__ == "__main__":
    main()
