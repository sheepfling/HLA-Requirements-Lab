"""Align the remaining 2025 opening pages with the shared Lab furniture."""

from __future__ import annotations

import json
from pathlib import Path

from hla_lab.core.json_types import JsonObject
from tools.migrations.workspace import migration_root


def _load(name: str) -> tuple[Path, JsonObject]:
    path = migration_root() / "topics" / "ieee" / name / "semantic" / "content-blocks.json"
    return path, json.loads(path.read_text(encoding="utf-8"))


def _write_opening_furniture_json(path: Path, payload: JsonObject) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _block(payload: JsonObject, block_id: str) -> JsonObject:
    return next(item for item in payload["content_blocks"] if item["id"] == block_id)


def main() -> None:
    path, payload = _load("hla-1516-2025")
    block = _block(payload, "content-1-normative-001")
    old = r"\HLAStartSemanticOpenerPage{12}{11}"
    new = r"\HLAStartSemanticPage{12}{11}"
    if block["layout_body"].count(old) != 1:
        raise ValueError("hla-1516-2025 opener furniture marker is not unique")
    block["layout_body"] = block["layout_body"].replace(old, new, 1)
    _write_opening_furniture_json(path, payload)

    path, payload = _load("hla-1516.1-2025")
    block = _block(payload, "content-15161-page-016")
    old = r"\thispagestyle{hla-opening}"
    new = r"\thispagestyle{RLHLA}"
    if block["layout_body"].count(old) != 1:
        raise ValueError("hla-1516.1-2025 opener furniture marker is not unique")
    block["layout_body"] = block["layout_body"].replace(old, new, 1)
    _write_opening_furniture_json(path, payload)


if __name__ == "__main__":
    main()
