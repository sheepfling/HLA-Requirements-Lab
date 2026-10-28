"""Move remaining HLA page sources behind typed content records."""

from __future__ import annotations

import argparse
import re
from collections.abc import Mapping, MutableMapping, MutableSequence, Sequence
from collections.abc import Set as AbstractSet
from pathlib import Path
from typing import Literal

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    ContentBlock,
    ContentBlockFile,
    ContentElement,
    ContentElementFile,
    SourceRef,
    load_document_model,
)
from hla_lab.paths import DocumentResources, repository_root, resources
from tools.migrations.migrate_1516_elements import _extract_block, _MutableContentBlock


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


def _kind(body: str) -> Literal["context", "normative"]:
    return (
        "normative"
        if re.search(r"\\(?:HLANormativeRuleStatement|HLARequirement)", body)
        or re.search(r"\bshall\b", body, re.IGNORECASE)
        else "context"
    )


def _annex_clause_by_path(
    root: Path,
    blocks: Sequence[_MutableContentBlock],
    clause_ids: AbstractSet[str],
) -> dict[str, str]:
    """Assign continuation pages to their current Annex owner."""
    if root.name != "hla-1516.2-2025":
        return {}
    current: str | None = None
    result: dict[str, str] = {}
    for item in sorted(blocks, key=lambda entry: entry.sequence):
        path = item.source.path
        body = item.layout_body or ""
        match = re.search(r"\\HLAAnnexHeading\{Annex\s+([A-I])\}", body)
        if match:
            candidate = f"clause-{match.group(1)}"
            current = candidate if candidate in clause_ids else None
        if current and "/annexes-d-h/" in f"/{path}":
            result[path] = current
    return result


def _source(path: Path, root: Path, body: str) -> SourceRef:
    return SourceRef(
        path=path.relative_to(root).as_posix(),
        line=1,
        end_line=max(1, body.count("\n") + 1),
    )


def _load_existing_blocks(path: Path) -> list[_MutableContentBlock]:
    if not path.is_file():
        return []
    payload = ContentBlockFile.model_validate_json(path.read_text(encoding="utf-8"))
    return [
        _MutableContentBlock.model_validate(item.model_dump(mode="python", exclude_unset=True))
        for item in payload.content_blocks
    ]


def _index_blocks(
    existing: Sequence[_MutableContentBlock],
    prefix: str,
) -> tuple[dict[str, _MutableContentBlock], dict[str, _MutableContentBlock]]:
    by_source: dict[str, _MutableContentBlock] = {}
    blocks_by_id: dict[str, _MutableContentBlock] = {}
    for item in existing:
        if item.id.startswith("prose-"):
            # Pre-M17 prose records remain semantic even when sourced from page adapters.
            item.layout_body = None
        if item.id.startswith(prefix):
            by_source[item.source.path] = item
        blocks_by_id[item.id] = item
    return by_source, blocks_by_id


def _page_block(
    root: Path,
    path: Path,
    prefix: str,
    clause_ids: AbstractSet[str],
    annex_clauses: Mapping[str, str],
    by_source: MutableMapping[str, _MutableContentBlock],
    blocks_by_id: MutableMapping[str, _MutableContentBlock],
    existing: MutableSequence[_MutableContentBlock],
) -> _MutableContentBlock:
    relative = path.relative_to(root).as_posix()
    item = by_source.get(relative)
    if item is None:
        body = path.read_text(encoding="utf-8")
        item = _MutableContentBlock(
            id=f"{prefix}-page-{_page_number(path):03d}",
            kind=_kind(body),
            text="",
            clause_id=_default_clause(root, path, clause_ids),
            record_ids=(),
            element_ids=(),
            source=_source(path, root, body),
            sequence=_page_number(path),
            layout_body=body,
        )
        existing.append(item)
        blocks_by_id[item.id] = item
        by_source[relative] = item
    else:
        body = item.layout_body or path.read_text(encoding="utf-8")
        item.layout_body = body
    if relative in annex_clauses:
        item.clause_id = annex_clauses[relative]
    return item


def _write_page_adapter(path: Path, block: ContentBlock) -> None:
    adapter = (
        "% M17 generated content adapter; semantic prose remains in "
        "semantic/content-blocks.json.\n"
        f"\\input{{output/semantic/content-block-{block.id}}}\n"
    )
    path.write_text(adapter, encoding="utf-8")


def _adapt_pages(
    root: Path,
    page_files: Sequence[Path],
    prefix: str,
    clause_ids: AbstractSet[str],
    annex_clauses: Mapping[str, str],
    by_source: MutableMapping[str, _MutableContentBlock],
    blocks_by_id: MutableMapping[str, _MutableContentBlock],
    existing: MutableSequence[_MutableContentBlock],
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
    existing: Sequence[_MutableContentBlock],
    clause_ids: AbstractSet[str],
    known_ids: AbstractSet[str],
) -> list[ContentElement]:
    elements: list[ContentElement] = []
    for item in existing:
        elements.extend(_extract_block(item, clause_ids=clause_ids, known_ids=known_ids))
    return elements


def _set_block_prose(
    existing: Sequence[_MutableContentBlock],
    elements: Sequence[ContentElement],
) -> None:
    prose_by_block: dict[str, list[str]] = {}
    for element in elements:
        if element.kind in {"paragraph", "note", "footnote", "list-item"}:
            prose_by_block.setdefault(element.block_id, []).append(element.text)
    for item in existing:
        item.text = "\n\n".join(prose_by_block.get(item.id, ()))


def _write_content_records(
    root: Path,
    blocks_path: Path,
    existing: Sequence[_MutableContentBlock],
    elements: Sequence[ContentElement],
) -> None:
    blocks_path.parent.mkdir(parents=True, exist_ok=True)
    content_blocks = ContentBlockFile(
        schema_version=2,
        content_blocks=tuple(
            ContentBlock.model_validate(item.model_dump(mode="python", exclude_unset=True))
            for item in existing
        ),
    )
    blocks_path.write_text(
        content_blocks.model_dump_json(indent=2, exclude_unset=True) + "\n",
        encoding="utf-8",
    )
    elements_path = DocumentResources(root).semantic_file("content-elements.json")
    elements_path.write_text(
        ContentElementFile(schema_version=1, content_elements=tuple(elements)).model_dump_json(
            indent=2, exclude_unset=True
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
    parser.add_argument("--workspace-root", type=Path, help="workspace for default document roots")
    args = parser.parse_args()
    roots = tuple(args.roots) or tuple(
        resources(repository_root(args.workspace_root)).document(name).root
        for name in ("hla-1516.1-2025", "hla-1516.2-2025")
    )
    for root in roots:
        migrate(root)


if __name__ == "__main__":
    main()
