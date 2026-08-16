"""Complete the data-driven IEEE 1516.2 M17 semantic migration."""

from __future__ import annotations

import json
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.io import write_json
from hla_lab.core.semantic_model import (
    ContentBlockFile,
    ContentElementFile,
    Definition,
    DefinitionFile,
    Requirement,
    RequirementFile,
    RequirementReviewFile,
    _load_requirement_candidates,
    load_document_model,
)
from hla_lab.core.text import normalize_whitespace, slugify
from hla_lab.paths import RESOURCES
from tools.migrations.migrate_remaining_content import _annex_clause_by_path
from tools.migrations.migrate_remaining_content import migrate as migrate_content

ROOT = RESOURCES.document("hla-1516.2-2025").root

_write_json = write_json


def _normalized(value: str) -> str:
    return normalize_whitespace(value).casefold()


def _is_placeholder(value: str) -> bool:
    return _normalized(value) in {"", "na", "n/a", "<semantics>", "...", "…"}


def _table_semantic_definitions(model: object) -> tuple[Definition, ...]:
    """Derive reusable definition records from every populated Semantics column."""
    family_by_table = {
        table_id: family
        for family in model.table_families  # type: ignore[attr-defined]
        for table_id in family.table_ids
    }
    preferred_headers = {
        "name",
        "record name",
        "class",
        "label",
        "category",
        "object",
        "interaction",
        "parameter",
        "field",
        "enumerator",
        "alternative",
        "attribute",
        "switch",
    }
    definitions: list[Definition] = []
    for table in model.tables:  # type: ignore[attr-defined]
        headers = {
            cell.column: cell.text.strip()
            for cell in table.cells
            if cell.row == 0 and cell.column is not None and cell.text.strip()
        }
        semantics_column = next(
            (column for column, text in headers.items() if _normalized(text) == "semantics"),
            None,
        )
        if semantics_column is None:
            continue
        identifier_columns = tuple(
            column
            for column, text in sorted(headers.items())
            if _normalized(text) in preferred_headers
        )
        if not identifier_columns:
            identifier_columns = tuple(
                column for column in sorted(headers) if column != semantics_column
            )[:1]
        cells_by_position = {
            (cell.row, cell.column): cell
            for cell in table.cells
            if cell.row is not None and cell.column is not None
        }
        rows = sorted({row for row, column in cells_by_position if row and column is not None})
        family = family_by_table.get(table.id)
        if family is None:
            raise ValueError(f"table {table.id} has no owning table family")
        for row in rows:
            semantic_cell = cells_by_position.get((row, semantics_column))
            if semantic_cell is None or _is_placeholder(semantic_cell.text):
                continue
            term_parts = [
                cells_by_position[(row, column)].text.strip()
                for column in identifier_columns
                if (row, column) in cells_by_position
                and not _is_placeholder(cells_by_position[(row, column)].text)
            ]
            if not term_parts:
                continue
            term = " / ".join(term_parts)
            definitions.append(
                Definition(
                    id=f"def-omt-semantics-{slugify(table.id, fallback='')}-r{row}",
                    term=term,
                    text=semantic_cell.text.strip(),
                    source=semantic_cell.source,
                    clause_id=family.clause_id,
                )
            )
    return tuple(definitions)


def _promoted_requirements(model: object, annex_by_path: dict[str, str]) -> tuple[Requirement, ...]:
    candidates = _load_requirement_candidates(ROOT, HLA_SOURCE)
    if len(candidates) != 340:
        raise ValueError(
            f"expected 340 1516.2 candidates before promotion, found {len(candidates)}"
        )
    records: list[Requirement] = []
    for candidate in candidates:
        clause_id = candidate.clause_id or annex_by_path.get(candidate.source.path)
        if clause_id is None:
            raise ValueError(f"candidate has no clause owner: {candidate.id}")
        clause = clause_id.removeprefix("clause-")
        payload = candidate.model_dump(mode="json")
        payload.update(
            {
                "title": candidate.title.replace("Normative candidate", "Normative statement"),
                "clause": clause,
                "clause_id": clause_id,
                "coverage_kind": "cross-cutting",
                "coverage_note": (
                    f"Source-derived normative statement owned by {clause_id}. "
                    "IEEE 1516.2 defines the OMT document and data semantics without "
                    "a modeled RTI state machine, so this record is checked as "
                    "cross-cutting document content."
                ),
                "extraction": "explicit",
                "semantic_group_id": f"m17.{clause_id}",
                "transition_ids": [],
            }
        )
        records.append(Requirement.model_validate(payload))
    return tuple(records)


def _attach_requirement_ownership() -> None:
    semantic = ROOT / "semantic"
    block_path = semantic / "content-blocks.json"
    element_path = semantic / "content-elements.json"
    blocks = ContentBlockFile.model_validate_json(block_path.read_text(encoding="utf-8"))
    elements = ContentElementFile.model_validate_json(element_path.read_text(encoding="utf-8"))
    model = load_document_model(ROOT, HLA_SOURCE)
    requirement_ids_by_path: dict[str, list[str]] = {}
    for requirement in model.requirements:
        requirement_ids_by_path.setdefault(requirement.source.path, []).append(requirement.id)

    updated_blocks = []
    owned_by_block: dict[str, tuple[str, ...]] = {}
    for block in blocks.content_blocks:
        additions = tuple(requirement_ids_by_path.get(block.source.path, ()))
        record_ids = tuple(dict.fromkeys((*block.record_ids, *additions)))
        updated = block.model_copy(update={"record_ids": record_ids})
        updated_blocks.append(updated)
        owned_by_block[block.id] = record_ids
    updated_elements = [
        element.model_copy(
            update={
                "record_ids": tuple(
                    dict.fromkeys((*element.record_ids, *owned_by_block.get(element.block_id, ())))
                )
            }
        )
        for element in elements.content_elements
    ]
    _write_json(
        block_path,
        ContentBlockFile(
            schema_version=blocks.schema_version,
            content_blocks=tuple(updated_blocks),
        ).model_dump(mode="json"),
    )
    _write_json(
        element_path,
        ContentElementFile(
            schema_version=elements.schema_version,
            content_elements=tuple(updated_elements),
        ).model_dump(mode="json"),
    )


def _repair_intermediate_content() -> None:
    """Recover from an interrupted pre-M17 extraction before model loading."""
    path = ROOT / "semantic" / "content-elements.json"
    if not path.is_file():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for item in payload.get("content_elements", []):
        if item.get("kind") == "list-item" and not item.get("parent_id"):
            item["kind"] = "paragraph"
            changed = True
    if changed:
        _write_json(path, payload)


def complete(root: Path = ROOT) -> dict[str, int]:
    global ROOT
    ROOT = root.resolve()
    _repair_intermediate_content()
    model = load_document_model(ROOT, HLA_SOURCE)
    blocks_payload = json.loads(
        (ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
    )
    annex_by_path = _annex_clause_by_path(
        ROOT,
        list(blocks_payload.get("content_blocks", [])),
        {item.id for item in model.clauses},
    )
    definitions = _table_semantic_definitions(model)
    requirements = _promoted_requirements(model, annex_by_path)
    semantic = ROOT / "semantic"
    _write_json(
        semantic / "definitions.json",
        DefinitionFile(schema_version=1, definitions=definitions).model_dump(mode="json"),
    )
    _write_json(
        semantic / "requirements.json",
        RequirementFile(schema_version=1, requirements=requirements).model_dump(mode="json"),
    )
    _write_json(
        semantic / "requirement-review.json",
        RequirementReviewFile(schema_version=1, reviews=()).model_dump(mode="json"),
    )

    # Re-extract after authored promotion so the normal content migration sees
    # the complete semantic ID set and writes readable page projections.
    migrate_content(ROOT)
    _attach_requirement_ownership()
    closed = load_document_model(ROOT, HLA_SOURCE)
    if len(closed.requirements) != 340 or any(
        item.extraction != "explicit" or not item.clause_id for item in closed.requirements
    ):
        raise ValueError("1516.2 requirement promotion did not close all 340 records")
    if closed.requirement_reviews:
        raise ValueError("1516.2 requirement review queue is not empty")
    return {
        "definitions": len(closed.definitions),
        "requirements": len(closed.requirements),
        "tables": len(closed.tables),
        "table_cells": sum(len(table.cells) for table in closed.tables),
        "table_families": len(closed.table_families),
        "content_blocks": len(closed.content_blocks),
        "content_elements": len(closed.content_elements),
    }


if __name__ == "__main__":
    print(complete())
