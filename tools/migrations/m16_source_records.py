"""Source candidate helpers for the IEEE 1516.1-2025 M16 migration."""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    ContentBlockFile,
    Requirement,
    TableCell,
    _load_requirement_candidates,
)
from hla_lab.paths import DocumentResources


def _m16_candidates(root: Path) -> tuple[Requirement, ...]:
    candidates = _load_requirement_candidates(root, HLA_SOURCE)
    blocks = ContentBlockFile.model_validate_json(
        DocumentResources(root).semantic_file("content-blocks.json").read_text(encoding="utf-8")
    ).content_blocks
    annex_by_path = {}
    for block in blocks:
        match = re.search(r"\\textbf\{Annex ([A-I])\}", block.layout_body or "")
        if match:
            annex_by_path[block.source.path] = match.group(1)
    return tuple(
        candidate.model_copy(
            update={
                "clause": annex_by_path.get(candidate.source.path, candidate.clause),
                "clause_id": (
                    f"clause-{annex_by_path[candidate.source.path]}"
                    if candidate.source.path in annex_by_path
                    else candidate.clause_id
                ),
            }
        )
        for candidate in candidates
    )


def _table_row_text(value: str) -> str:
    """Normalize a Table 5 cell without turning layout punctuation into prose."""
    value = re.sub(r"\\[a-zA-Z]+(?:\{[^{}]*\})?", " ", value)
    value = value.replace("%", " ").replace("\\", " ")
    return re.sub(r"\s+", " ", value).strip(" ,")


def _table_5_rows(table: object) -> dict[int, list[TableCell]]:
    by_row: dict[int, list[TableCell]] = defaultdict(list)
    for cell in getattr(table, "cells", ()):
        if cell.row is not None:
            by_row[cell.row].append(cell)
    return by_row


def _table_5_start_rows(by_row: Mapping[int, Sequence[TableCell]]) -> list[int]:
    start_rows = []
    for row, cells in sorted(by_row.items()):
        type_cell = max(cells, key=lambda item: item.column if item.column is not None else -1)
        type_text = _table_row_text(type_cell.text)
        if type_text.casefold() in {"type", "(continued)", ""} or type_text in {"\\", ",", "]"}:
            continue
        if type_cell.column is None or type_cell.column < 6:
            continue
        start_rows.append(row)
    return start_rows


def _table_5_row_cells(
    by_row: Mapping[int, Sequence[TableCell]],
    start_rows: Sequence[int],
    ordinal: int,
    start_row: int,
) -> list[TableCell]:
    end_row = start_rows[ordinal] if ordinal < len(start_rows) else max(by_row) + 1
    return [cell for row in range(start_row, end_row) for cell in by_row.get(row, ())]


def _table_5_column_values(row_cells: Sequence[TableCell]) -> dict[int, list[str]]:
    values_by_column: dict[int, list[str]] = defaultdict(list)
    for cell in row_cells:
        if cell.column is None:
            continue
        value = _table_row_text(cell.text)
        if value and value not in {"\\", ",", "]"}:
            values_by_column[cell.column].append(value)
    return values_by_column


def _table_5_requirement(
    table: object,
    ordinal: int,
    row_cells: Sequence[TableCell],
    values_by_column: Mapping[int, Sequence[str]],
) -> Requirement | None:
    columns = sorted(values_by_column, reverse=True)
    if not columns:
        return None
    type_value = " ".join(dict.fromkeys(values_by_column[columns[0]]))
    encoding_value = (
        " ".join(dict.fromkeys(values_by_column[columns[1]])) if len(columns) > 1 else ""
    )
    example_value = (
        " ".join(dict.fromkeys(values_by_column[columns[-1]])) if len(columns) > 2 else ""
    )
    first_cell = min(row_cells, key=lambda item: item.source.line)
    last_line = max(cell.source.end_line or cell.source.line for cell in row_cells)
    page = table.id.rsplit("-p", 1)[-1]
    return Requirement(
        id=f"requirement-candidate-table-5-p{page}-r{ordinal:03d}",
        title=f"Table 5 row: {type_value}",
        statement=(
            f"Table 5 defines the {type_value} row with encoding "
            f"{encoding_value or 'unspecified'} and example {example_value or 'unspecified'}."
        ),
        kind="detailed",
        clause="11.5.1",
        machine_statement=(
            f"Table 5 type {type_value}; encoding {encoding_value or 'unspecified'}; "
            f"example {example_value or 'unspecified'}."
        ),
        coverage_kind="cross-cutting",
        coverage_note=(
            "Structured Table 5 row candidate; it records the wire-shape source "
            "without promoting the example to a normative lexical rule."
        ),
        api_surface_scope="cross-cutting",
        api_surface_note="Table structure is not itself a callable API mapping.",
        extraction="explicit",
        semantic_group_id="m16.table-5",
        source=first_cell.source.model_copy(update={"end_line": last_line}),
    )


def _table_5_requirements(table: object) -> tuple[Requirement, ...]:
    by_row = _table_5_rows(table)
    start_rows = _table_5_start_rows(by_row)
    records = []
    for ordinal, start_row in enumerate(start_rows, start=1):
        row_cells = _table_5_row_cells(by_row, start_rows, ordinal, start_row)
        if not row_cells:
            continue
        values_by_column = _table_5_column_values(row_cells)
        record = _table_5_requirement(table, ordinal, row_cells, values_by_column)
        if record is not None:
            records.append(record)
    return tuple(records)


def _table_5_row_requirements(model: object) -> tuple[Requirement, ...]:
    """Promote Table 5's typed rows as explicit, source-addressable candidates."""
    records = []
    for table in getattr(model, "tables", ()):
        if getattr(table, "number", None) == "5":
            records.extend(_table_5_requirements(table))
    return tuple(records)
