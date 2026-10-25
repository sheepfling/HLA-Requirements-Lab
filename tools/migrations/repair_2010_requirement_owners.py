"""Close source-owned requirement links for the 2010 semantic catalogs.

The 2010 requirement catalogs are authoritative records, while the content
block and content element files are the source-owned consumers.  This repair
connects each requirement to the block and element that owns its source file.
It is idempotent and deliberately uses source paths, not generated page order,
so later layout changes do not silently break semantic ownership.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import MappingProxyType

from hla_lab.core.json_types import JsonObject
from tools.migrations.workspace import document_root

FALLBACK_SOURCE_PATHS = MappingProxyType(
    {
        "hla-1516.2-2010": {
            "clauses/clause03_definitions_continuation.tex": "clauses/clause03_definitions.tex",
        }
    }
)


def _load(path: Path) -> JsonObject:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_requirement_owner_json(path: Path, payload: JsonObject) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repair(root: Path) -> int:
    semantic = root / "semantic"
    requirements = _load(semantic / "requirements.json")["requirements"]
    blocks_path = semantic / "content-blocks.json"
    elements_path = semantic / "content-elements.json"
    blocks_payload = _load(blocks_path)
    elements_payload = _load(elements_path)
    blocks = blocks_payload["content_blocks"]
    elements = elements_payload["content_elements"]

    block_by_source = {item["source"]["path"]: item for item in blocks}
    element_by_source = {item["source"]["path"]: item for item in elements}
    fallback = FALLBACK_SOURCE_PATHS.get(root.name, {})
    changed = 0

    for requirement in requirements:
        requirement_id = requirement["id"]
        source_path = requirement["source"]["path"]
        owner_path = fallback.get(source_path, source_path)
        block = block_by_source.get(owner_path)
        element = element_by_source.get(owner_path)
        if block is None or element is None:
            message = f"{root.name}: no content owner for {requirement_id} at {source_path}"
            raise ValueError(message)
        for owner in (block, element):
            record_ids = owner.setdefault("record_ids", [])
            if requirement_id not in record_ids:
                record_ids.append(requirement_id)
                changed += 1

    _write_requirement_owner_json(blocks_path, blocks_payload)
    _write_requirement_owner_json(elements_path, elements_payload)
    return changed


def main() -> None:
    for document_id in ("hla-1516.1-2010", "hla-1516.2-2010"):
        root = document_root(document_id)
        print(f"{root.name}: added {repair(root)} requirement-owner links")


if __name__ == "__main__":
    main()
