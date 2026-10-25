"""Move remaining HLA page sources behind typed content records."""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path

from pydantic import JsonValue

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


def _default_clause(root: Path, path: Path, clause_ids: AbstractSet[str]) -> str | None:
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
    blocks: Sequence[Mapping[str, JsonValue]],
    clause_ids: AbstractSet[str],
) -> dict[str, str]:
    """Assign continuation pages to their current Annex owner."""
    if root.name != "hla-1516.2-2025":
        return {}
    current: str | None = None
    result: dict[str, str] = {}
    sourced_blocks: list[Mapping[str, JsonValue]] = []
    for item in blocks:
        source: JsonValue = item.get("source")
        if isinstance(source, dict):
            sourced_blocks.append(item)
    for item in sorted(sourced_blocks, key=lambda entry: int(entry.get("sequence") or 0)):
        source = item["source"]
        path = str(source["path"])
        body = str(item.get("layout_body") or "")
        match = re.search(r"\\HLAAnnexHeading\{Annex\s+([A-I])\}", body)
        if match:
            candidate = f"clause-{match.group(1)}"
            current = candidate if candidate in clause_ids else None
        if current and "/annexes-d-h/" in f"/{path}":
            result[path] = current
    return result


def _source(path: Path, root: Path, body: str) -> dict[str, JsonValue]:
    return {
        "path": path.relative_to(root).as_posix(),
        "line": 1,
        "end_line": max(1, body.count("\n") + 1),
    }


def _load_existing_blocks(path: Path) -> list[dict[str, JsonValue]]:
    if not path.is_file():
        return []
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    raw_blocks: JsonValue = payload.get("content_blocks", []) if isinstance(payload, dict) else []
    if not isinstance(raw_blocks, list):
        raise ValueError(f"content_blocks must be an array: {path}")
    existing: list[dict[str, JsonValue]] = []
    for raw_item in raw_blocks:
        item: JsonValue = raw_item
        if not isinstance(item, dict):
            raise ValueError(f"content block must be an object: {path}")
        existing.append(item)
    return existing


def _index_blocks(
    existing: Sequence[MutableMapping[str, JsonValue]],
    prefix: str,
) -> tuple[dict[str, MutableMapping[str, JsonValue]], dict[str, MutableMapping[str, JsonValue]]]:
    by_source: dict[str, MutableMapping[str, JsonValue]] = {}
    blocks_by_id: dict[str, MutableMapping[str, JsonValue]] = {}
    for item in existing:
        if str(item.get("id", "")).startswith("prose-"):
            # Pre-M17 prose records remain semantic even when sourced from page adapters.
            item.pop("layout_body", None)
        source: JsonValue = item.get("source")
        if isinstance(source, dict) and str(item.get("id", "")).startswith(prefix):
            by_source[str(source["path"])] = item
        blocks_by_id[str(item["id"])] = item
    return by_source, blocks_by_id


def _page_block(
    root: Path,
    path: Path,
    prefix: str,
    clause_ids: AbstractSet[str],
    annex_clauses: Mapping[str, str],
    by_source: MutableMapping[str, MutableMapping[str, JsonValue]],
    blocks_by_id: MutableMapping[str, MutableMapping[str, JsonValue]],
    existing: MutableSequence[MutableMapping[str, JsonValue]],
) -> MutableMapping[str, JsonValue]:
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
    return item


def _write_page_adapter(path: Path, block: Mapping[str, JsonValue]) -> None:
    adapter = (
        "% M17 generated content adapter; semantic prose remains in "
        "semantic/content-blocks.json.\n"
        f"\\input{{output/semantic/content-block-{block['id']}}}\n"
    )
    path.write_text(adapter, encoding="utf-8")


def _adapt_pages(
    root: Path,
    page_files: Sequence[Path],
    prefix: str,
    clause_ids: AbstractSet[str],
    annex_clauses: Mapping[str, str],
    by_source: MutableMapping[str, MutableMapping[str, JsonValue]],
    blocks_by_id: MutableMapping[str, MutableMapping[str, JsonValue]],
    existing: MutableSequence[MutableMapping[str, JsonValue]],
) -> None:
    for path in page_files:
        block = _page_block(
            root,
            path,
            prefix,
            clause_ids,
            annex_clauses,
            by_source,
            blocks_by_id,
            existing,
        )
        _write_page_adapter(path, block)


def _extract_elements(
    existing: Sequence[MutableMapping[str, JsonValue]],
    clause_ids: AbstractSet[str],
    known_ids: AbstractSet[str],
) -> list[dict[str, JsonValue]]:
    elements: list[dict[str, JsonValue]] = []
    for item in existing:
        item.setdefault("element_ids", [])
        elements.extend(_extract_block(item, clause_ids=clause_ids, known_ids=known_ids))
    return elements


def _set_block_prose(
    existing: Sequence[MutableMapping[str, JsonValue]],
    elements: Sequence[Mapping[str, JsonValue]],
) -> None:
    prose_by_block: dict[str, list[str]] = {}
    for element in elements:
        if element["kind"] in {"paragraph", "note", "footnote", "list-item"}:
            prose_by_block.setdefault(str(element["block_id"]), []).append(str(element["text"]))
    for item in existing:
        item["text"] = "\n\n".join(prose_by_block.get(str(item["id"]), ()))


def _write_content_records(
    root: Path,
    blocks_path: Path,
    existing: Sequence[Mapping[str, JsonValue]],
    elements: Sequence[Mapping[str, JsonValue]],
) -> None:
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


def migrate(root: Path) -> tuple[int, int]:
    model = load_document_model(root, HLA_SOURCE)
    blocks_path = DocumentResources(root).semantic_file("content-blocks.json")
    existing = _load_existing_blocks(blocks_path)
    prefix = "content-15161" if root.name == "hla-1516.1-2025" else "content-15162"
    by_source, blocks_by_id = _index_blocks(existing, prefix)
    clause_ids = {item.id for item in model.clauses}
    annex_clauses = _annex_clause_by_path(root, existing, clause_ids)
    page_files = _page_files(root)
    _adapt_pages(
        root, page_files, prefix, clause_ids, annex_clauses, by_source, blocks_by_id, existing
    )
    known_ids = set(model.semantic_record_ids()) | set(blocks_by_id)
    elements = _extract_elements(existing, clause_ids, known_ids)
    _set_block_prose(existing, elements)
    _write_content_records(root, blocks_path, existing, elements)
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
