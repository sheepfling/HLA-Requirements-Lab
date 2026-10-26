"""Replace inherited OMT example glyph artwork with live vector marks."""

from __future__ import annotations

from pathlib import Path

from hla_lab.core.semantic_model import ContentBlock, ContentBlockFile
from tools.migrations.workspace import migration_root


def _replacements() -> tuple[tuple[Path, str, str], ...]:
    root = migration_root()
    return (
        (
            root / "topics" / "ieee" / "hla-1516.2-2010" / "semantic" / "content-blocks.json",
            r"\restaurantglyph",
            r"\omtcategoryglyph",
        ),
        (
            root / "topics" / "ieee" / "hla-1516.2-2025" / "semantic" / "content-blocks.json",
            r"\HLAPlacedImage{369.000}{601.320}{24.000}{24.000}{assets/semantic/page-038-image-01.png}",
            r"\HLAObjectModelGlyphAt{369.000}{601.320}{24.000}{24.000}",
        ),
    )


def _replace(path: Path, old: str, new: str) -> int:
    payload = ContentBlockFile.model_validate_json(path.read_text(encoding="utf-8"))
    blocks = list(payload.content_blocks)
    count = 0
    for index, block in enumerate(blocks):
        updates: dict[str, str] = {}
        for field in ("text", "layout_body"):
            value = getattr(block, field)
            if value is not None:
                count += value.count(old)
                updates[field] = value.replace(old, new)
        if updates:
            blocks[index] = block.model_copy(update=updates)
    if count != 1:
        raise SystemExit(f"expected one {old!r} occurrence in {path}, found {count}")
    updated_payload = ContentBlockFile(
        schema_version=payload.schema_version,
        content_blocks=tuple(
            ContentBlock.model_validate(block.model_dump(mode="python", exclude_unset=True))
            for block in blocks
        ),
    )
    path.write_text(
        updated_payload.model_dump_json(indent=2, exclude_unset=True) + "\n",
        encoding="utf-8",
    )
    return count


def main() -> None:
    for path, old, new in _replacements():
        _replace(path, old, new)
        print(f"migrated OMT glyph source in {path}")


if __name__ == "__main__":
    main()
