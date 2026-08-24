"""Replace inherited OMT example glyph artwork with live vector marks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

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
    payload = json.loads(path.read_text(encoding="utf-8"))
    count = 0
    for block in payload["content_blocks"]:
        for key in ("text", "layout_body"):
            value = block.get(key)
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
