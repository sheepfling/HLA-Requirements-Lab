"""Close source-owned requirement links for the 2010 semantic catalogs.

The 2010 requirement catalogs are authoritative records, while the content
block and content element files are the source-owned consumers.  This repair
connects each requirement to the block and element that owns its source file.
It is idempotent and deliberately uses source paths, not generated page order,
so later layout changes do not silently break semantic ownership.
"""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from hla_lab.core.semantic_model import (
    ContentBlockFile,
    ContentElementFile,
    RequirementFile,
)
from tools.migrations.workspace import document_root

FALLBACK_SOURCE_PATHS = MappingProxyType(
    {
        "hla-1516.2-2010": {
            "clauses/clause03_definitions_continuation.tex": "clauses/clause03_definitions.tex",
        }
    }
)


def repair(root: Path) -> int:
    semantic = root / "semantic"
    requirement_file = RequirementFile.model_validate_json(
        (semantic / "requirements.json").read_text(encoding="utf-8")
    )
    blocks_path = semantic / "content-blocks.json"
    elements_path = semantic / "content-elements.json"
    blocks_payload = ContentBlockFile.model_validate_json(blocks_path.read_text(encoding="utf-8"))
    elements_payload = ContentElementFile.model_validate_json(
        elements_path.read_text(encoding="utf-8")
    )
    blocks = list(blocks_payload.content_blocks)
    elements = list(elements_payload.content_elements)

    block_by_source = {item.source.path: index for index, item in enumerate(blocks)}
    element_by_source = {item.source.path: index for index, item in enumerate(elements)}
    fallback = FALLBACK_SOURCE_PATHS.get(root.name, {})
    changed = 0

    for requirement in requirement_file.requirements:
        requirement_id = requirement.id
        source_path = requirement.source.path
        owner_path = fallback.get(source_path, source_path)
        block_index = block_by_source.get(owner_path)
        element_index = element_by_source.get(owner_path)
        if block_index is None or element_index is None:
            message = f"{root.name}: no content owner for {requirement_id} at {source_path}"
            raise ValueError(message)
        block = blocks[block_index]
        if requirement_id not in block.record_ids:
            blocks[block_index] = block.model_copy(
                update={"record_ids": (*block.record_ids, requirement_id)}
            )
            changed += 1
        element = elements[element_index]
        if requirement_id not in element.record_ids:
            elements[element_index] = element.model_copy(
                update={"record_ids": (*element.record_ids, requirement_id)}
            )
            changed += 1

    updated_blocks = ContentBlockFile(
        schema_version=blocks_payload.schema_version,
        content_blocks=tuple(blocks),
    )
    updated_elements = ContentElementFile(
        schema_version=elements_payload.schema_version,
        content_elements=tuple(elements),
    )
    blocks_path.write_text(
        updated_blocks.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )
    elements_path.write_text(
        updated_elements.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8"
    )
    return changed


def main() -> None:
    for document_id in ("hla-1516.1-2010", "hla-1516.2-2010"):
        root = document_root(document_id)
        print(f"{root.name}: added {repair(root)} requirement-owner links")


if __name__ == "__main__":
    main()
