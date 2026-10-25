"""Replace inherited OMT example glyph artwork with live vector marks."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import JsonValue

from hla_lab.paths import RESOURCES

ROOT = RESOURCES.root

REPLACEMENTS = (
    (
        ROOT / "topics" / "ieee" / "hla-1516.2-2010" / "semantic" / "content-blocks.json",
        r"\restaurantglyph",
        r"\omtcategoryglyph",
    ),
    (
        ROOT / "topics" / "ieee" / "hla-1516.2-2025" / "semantic" / "content-blocks.json",
        r"\HLAPlacedImage{369.000}{601.320}{24.000}{24.000}{assets/semantic/page-038-image-01.png}",
        r"\HLAObjectModelGlyphAt{369.000}{601.320}{24.000}{24.000}",
    ),
)


def _replace(path: Path, old: str, new: str) -> int:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {path}")
    raw_blocks: JsonValue = payload.get("content_blocks", [])
    if not isinstance(raw_blocks, list):
        raise ValueError(f"expected content_blocks to be an array in {path}")
    blocks: list[JsonValue] = raw_blocks
    count = 0
    for raw_block in blocks:
        if not isinstance(raw_block, dict):
            continue
        block: dict[str, JsonValue] = raw_block
        for key in ("text", "layout_body"):
            value: JsonValue = block.get(key)
            if isinstance(value, str):
                count += value.count(old)
                block[key] = value.replace(old, new)
    if count != 1:
        raise SystemExit(f"expected one {old!r} occurrence in {path}, found {count}")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return count


def main() -> None:
    for path, old, new in REPLACEMENTS:
        _replace(path, old, new)
        print(f"migrated OMT glyph source in {path}")


if __name__ == "__main__":
    main()
