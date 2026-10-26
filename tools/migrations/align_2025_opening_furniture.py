"""Align the remaining 2025 opening pages with the shared Lab furniture."""

from __future__ import annotations

from pathlib import Path

from hla_lab.core.semantic_model import ContentBlock, ContentBlockFile
from tools.migrations.workspace import migration_root


def _load(name: str) -> tuple[Path, ContentBlockFile]:
    path = migration_root() / "topics" / "ieee" / name / "semantic" / "content-blocks.json"
    return path, ContentBlockFile.model_validate_json(path.read_text(encoding="utf-8"))


def _write_opening_furniture_json(path: Path, payload: ContentBlockFile) -> None:
    path.write_text(payload.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8")


def _replace_block(payload: ContentBlockFile, block_id: str, body: str) -> ContentBlockFile:
    blocks = list(payload.content_blocks)
    index = next(index for index, item in enumerate(blocks) if item.id == block_id)
    blocks[index] = ContentBlock.model_validate(
        blocks[index]
        .model_copy(update={"layout_body": body})
        .model_dump(mode="python", exclude_unset=True)
    )
    return ContentBlockFile(schema_version=payload.schema_version, content_blocks=tuple(blocks))


def main() -> None:
    path, payload = _load("hla-1516-2025")
    block = next(item for item in payload.content_blocks if item.id == "content-1-normative-001")
    old = r"\HLAStartSemanticOpenerPage{12}{11}"
    new = r"\HLAStartSemanticPage{12}{11}"
    if block.layout_body is None or block.layout_body.count(old) != 1:
        raise ValueError("hla-1516-2025 opener furniture marker is not unique")
    payload = _replace_block(payload, block.id, block.layout_body.replace(old, new, 1))
    _write_opening_furniture_json(path, payload)

    path, payload = _load("hla-1516.1-2025")
    block = next(item for item in payload.content_blocks if item.id == "content-15161-page-016")
    old = r"\thispagestyle{hla-opening}"
    new = r"\thispagestyle{RLHLA}"
    if block.layout_body is None or block.layout_body.count(old) != 1:
        raise ValueError("hla-1516.1-2025 opener furniture marker is not unique")
    payload = _replace_block(payload, block.id, block.layout_body.replace(old, new, 1))
    _write_opening_furniture_json(path, payload)


if __name__ == "__main__":
    main()
