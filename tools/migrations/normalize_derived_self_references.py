"""Normalize self-references for the independent HLA Requirements Lab edition."""

from __future__ import annotations

import json
from collections.abc import MutableMapping
from pathlib import Path

from pydantic import JsonValue

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


def _load_blocks(target: Path) -> tuple[dict[str, JsonValue], list[JsonValue]]:
    payload: JsonValue = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected a JSON object in {target}")
    raw_blocks: JsonValue = payload.get("content_blocks", [])
    if not isinstance(raw_blocks, list):
        raise ValueError(f"expected content_blocks to be an array in {target}")
    return payload, raw_blocks


def _normalize_block(block: MutableMapping[str, JsonValue]) -> tuple[int, int]:
    count = 0
    title_count = 0
    for key in ("text", "layout_body"):
        value: JsonValue = block.get(key)
        if isinstance(value, str):
            count += value.count(OLD)
            block[key] = value.replace(OLD, NEW)
    if block.get("id") == "content-15162-page-013":
        for old, new in TITLE_REPLACEMENTS:
            layout_body: JsonValue = block["layout_body"]
            if not isinstance(layout_body, str):
                raise ValueError("content block layout_body must be text")
            occurrences = layout_body.count(old)
            title_count += occurrences
            block["layout_body"] = layout_body.replace(old, new)
    return count, title_count


def main() -> None:
    target = document_root("hla-1516.2-2025") / "semantic" / "content-blocks.json"
    payload, blocks = _load_blocks(target)
    count = 0
    title_count = 0
    for raw_block in blocks:
        if not isinstance(raw_block, dict):
            continue
        block: dict[str, JsonValue] = raw_block
        block_count, block_title_count = _normalize_block(block)
        count += block_count
        title_count += block_title_count
    if count not in (0, 6):
        raise SystemExit(f"expected 0 or 6 self-references, found {count}")
    if title_count not in (0, len(TITLE_REPLACEMENTS)):
        raise SystemExit(
            f"expected 0 or {len(TITLE_REPLACEMENTS)} title replacements, found {title_count}"
        )
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"normalized {count} self-references and {title_count} title fragments in {target}")


if __name__ == "__main__":
    main()
