"""Normalize self-references for the independent HLA Requirements Lab edition."""

from __future__ import annotations

from pathlib import Path

from hla_lab.core.semantic_model import ContentBlock, ContentBlockFile
from tools.migrations.workspace import document_root

OLD = "IEEE Std 1516.2-2025"
NEW = "this specification"
TITLE_REPLACEMENTS = (
    (r"\mbox{\textbf{IEEE Standard for}}", r"\mbox{\textbf{HLA Requirements Lab}}"),
    (
        r"\mbox{\textbf{Modeling and Simulation (M\&S)}}",
        r"\mbox{\textbf{HLA 1516.2 family}}",
    ),
    (
        r"\mbox{\textbf{High Level Architecture (HLA)—}}",
        r"\mbox{\textbf{2025-source compilation}}",
    ),
)


def _load_blocks(target: Path) -> ContentBlockFile:
    return ContentBlockFile.model_validate_json(target.read_text(encoding="utf-8"))


def _normalize_block(block: ContentBlock) -> tuple[ContentBlock, int, int]:
    count = 0
    title_count = 0
    updates: dict[str, str] = {}
    for field in ("text", "layout_body"):
        value = getattr(block, field)
        if value is not None:
            count += value.count(OLD)
            updates[field] = value.replace(OLD, NEW)
    if block.id == "content-15162-page-013":
        for old, new in TITLE_REPLACEMENTS:
            layout_body = updates.get("layout_body", block.layout_body)
            if layout_body is None:
                raise ValueError("content block layout_body must be text")
            occurrences = layout_body.count(old)
            title_count += occurrences
            updates["layout_body"] = layout_body.replace(old, new)
    updated = block.model_copy(update=updates) if updates else block
    return updated, count, title_count


def main() -> None:
    target = document_root("hla-1516.2-2025") / "semantic" / "content-blocks.json"
    payload = _load_blocks(target)
    count = 0
    title_count = 0
    blocks: list[ContentBlock] = []
    for block in payload.content_blocks:
        updated_block, block_count, block_title_count = _normalize_block(block)
        blocks.append(updated_block)
        count += block_count
        title_count += block_title_count
    if count not in (0, 6):
        raise SystemExit(f"expected 0 or 6 self-references, found {count}")
    if title_count not in (0, len(TITLE_REPLACEMENTS)):
        raise SystemExit(
            f"expected 0 or {len(TITLE_REPLACEMENTS)} title replacements, found {title_count}"
        )
    updated_payload = ContentBlockFile(
        schema_version=payload.schema_version,
        content_blocks=tuple(
            ContentBlock.model_validate(block.model_dump(mode="python", exclude_unset=True))
            for block in blocks
        ),
    )
    target.write_text(
        updated_payload.model_dump_json(indent=2, exclude_unset=True) + "\n",
        encoding="utf-8",
    )
    print(f"normalized {count} self-references and {title_count} title fragments in {target}")


if __name__ == "__main__":
    main()
