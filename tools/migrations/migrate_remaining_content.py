"""Move remaining HLA page sources behind typed content records."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.paths import RESOURCES, DocumentResources
from tools.migrations.migrate_1516_elements import _extract_block


def _page_files(root: Path) -> tuple[Path, ...]:
    if root.name == "hla-1516.1-2025":
        pattern = root / "content"
        glob = "*-page-*.tex"
    elif root.name == "hla-1516.2-2025":
        pattern = root / "sections" / "semantic"
        glob = "page-*.tex"
    else:
        raise ValueError(f"M17 has no page-source profile for {root.name}")
    return tuple(
        sorted(
            path for path in pattern.rglob(glob) if "generated" not in path.relative_to(root).parts
        )
    )


def _page_number(path: Path) -> int:
    match = re.search(r"page-(\d+)", path.name)
    return int(match.group(1)) if match else 0


def _default_clause(root: Path, path: Path, clause_ids: set[str]) -> str | None:
    relative = path.relative_to(root).as_posix()
    match = re.search(r"(?:^|/)(\d+)[-_]", relative)
    if match:
        candidate = f"clause-{int(match.group(1))}"
        if candidate in clause_ids:
            return candidate
    match = re.search(r"(?:^|/)clauses?-(\d+)", relative)
    if match:
        candidate = f"clause-{match.group(1)}"
        if candidate in clause_ids:
            return candidate
    return None


def _kind(body: str) -> str:
    return (
        "normative"
        if re.search(r"\\(?:HLANormativeRuleStatement|HLARequirement)", body)
        or re.search(r"\bshall\b", body, re.IGNORECASE)
        else "context"
    )


def _annex_clause_by_path(
    root: Path,
    blocks: list[dict[str, object]],
    clause_ids: set[str],
) -> dict[str, str]:
    """Assign continuation pages to their current Annex owner."""
    if root.name != "hla-1516.2-2025":
        return {}
    current: str | None = None
    result: dict[str, str] = {}
    for item in sorted(
        (item for item in blocks if isinstance(item.get("source"), dict)),
        key=lambda item: int(item.get("sequence") or 0),
    ):
        path = str(item["source"]["path"])
        body = str(item.get("layout_body") or "")
        match = re.search(r"\\HLAAnnexHeading\{Annex\s+([A-I])\}", body)
        if match:
            candidate = f"clause-{match.group(1)}"
            current = candidate if candidate in clause_ids else None
        if current and "/annexes-d-h/" in f"/{path}":
            result[path] = current
    return result


def _source(path: Path, root: Path, body: str) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "line": 1,
        "end_line": max(1, body.count("\n") + 1),
    }


def migrate(root: Path) -> tuple[int, int]:
    model = load_document_model(root, HLA_SOURCE)
    blocks_path = DocumentResources(root).semantic_file("content-blocks.json")
    if blocks_path.is_file():
        payload = json.loads(blocks_path.read_text(encoding="utf-8"))
        existing = list(payload.get("content_blocks", []))
    else:
        existing = []
    prefix = "content-15161" if root.name == "hla-1516.1-2025" else "content-15162"
    for item in existing:
        if isinstance(item, dict) and str(item.get("id", "")).startswith("prose-"):
            # These pre-M17 records are semantic prose, not faithful page
            # layouts, even when their source path is a page adapter.
            item.pop("layout_body", None)
    # Legacy semantic blocks may deliberately share a page source path.  They
    # remain standalone records and must not be mistaken for page adapters.
    # Only blocks created by this migration own a page source by path.
    by_source = {
        str(item["source"]["path"]): item
        for item in existing
        if (
            isinstance(item, dict)
            and isinstance(item.get("source"), dict)
            and str(item.get("id", "")).startswith(prefix)
        )
    }
    clause_ids = {item.id for item in model.clauses}
    annex_clauses = _annex_clause_by_path(root, existing, clause_ids)
    page_files = _page_files(root)
    blocks_by_id = {str(item["id"]): item for item in existing}
    for path in page_files:
        relative = path.relative_to(root).as_posix()
        item = by_source.get(relative)
        if item is None:
            body = path.read_text(encoding="utf-8")
            item = {
                "id": f"{prefix}-page-{_page_number(path):03d}",
                "kind": _kind(body),
                "text": "",
                "clause_id": _default_clause(root, path, clause_ids),
                "record_ids": [],
                "element_ids": [],
                "source": _source(path, root, body),
                "sequence": _page_number(path),
                "layout_body": body,
            }
            existing.append(item)
            blocks_by_id[str(item["id"])] = item
            by_source[relative] = item
        else:
            body = str(item.get("layout_body") or path.read_text(encoding="utf-8"))
            item["layout_body"] = body
            item.setdefault("element_ids", [])
        if relative in annex_clauses:
            item["clause_id"] = annex_clauses[relative]

        adapter = (
            "% M17 generated content adapter; semantic prose remains in "
            "semantic/content-blocks.json.\n"
            f"\\input{{output/semantic/content-block-{item['id']}}}\n"
        )
        path.write_text(adapter, encoding="utf-8")

    known_ids = set(model.semantic_record_ids()) | set(blocks_by_id)
    elements: list[dict[str, object]] = []
    for item in existing:
        item.setdefault("element_ids", [])
        elements.extend(_extract_block(item, clause_ids=clause_ids, known_ids=known_ids))

    # Keep a compact, readable prose projection on each page-owned block. The
    # layout body remains available for faithful rendering, while consumers
    # can use this field without parsing TikZ/LaTeX geometry.
    prose_by_block: dict[str, list[str]] = {}
    for element in elements:
        if element["kind"] in {"paragraph", "note", "footnote", "list-item"}:
            prose_by_block.setdefault(str(element["block_id"]), []).append(str(element["text"]))
    for item in existing:
        item["text"] = "\n\n".join(prose_by_block.get(str(item["id"]), ()))

    blocks_path.parent.mkdir(parents=True, exist_ok=True)
    blocks_path.write_text(
        json.dumps({"schema_version": 2, "content_blocks": existing}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    elements_path = DocumentResources(root).semantic_file("content-elements.json")
    elements_path.write_text(
        json.dumps(
            {"schema_version": 1, "content_elements": elements},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"{root.name}: page adapters={len(page_files)}, "
        f"content blocks={len(existing)}, content elements={len(elements)}"
    )
    return len(existing), len(elements)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path)
    args = parser.parse_args()
    roots = tuple(args.roots) or tuple(
        RESOURCES.document(name).root for name in ("hla-1516.1-2025", "hla-1516.2-2025")
    )
    for root in roots:
        migrate(root)


if __name__ == "__main__":
    main()
