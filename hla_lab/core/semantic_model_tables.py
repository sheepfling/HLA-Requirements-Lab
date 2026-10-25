"""Extraction and assembly of semantic table records."""

from __future__ import (
    annotations,
)

import re
from collections import (
    defaultdict,
)
from collections.abc import (
    Iterable,
    Mapping,
    Sequence,
)
from collections.abc import (
    Set as AbstractSet,
)
from dataclasses import (
    dataclass,
)
from pathlib import (
    Path,
)
from typing import (
    Literal,
)

from hla_lab.core.semantic_model_authored import _load_authored_content_blocks
from hla_lab.core.semantic_model_resources import (
    _files,
    _source,
)
from hla_lab.core.semantic_text import (
    _command_events,
    _commands,
)
from hla_lab.core.semantic_types import (
    CommandEvent,
    ContentBlock,
    Definition,
    Requirement,
    SourceRef,
    Table,
    TableBounds,
    TableCaption,
    TableCell,
    TableFamily,
    TableHeading,
    TableLabel,
    TablePrimitive,
)
from hla_lab.core.source_adapter import (
    LatexSourceProfile,
)
from hla_lab.core.source_paths import (
    normalized_source_path,
)


@dataclass(frozen=True, slots=True)
class _TableGridCell:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True, slots=True)
class _TableCellCandidate:
    id: str
    table_id: str
    text: str
    x: float
    y: float
    width: float
    height: float
    source: SourceRef


def _table_number(caption: str) -> str | None:
    match = re.search(r"\bTable\s+(\d+)", caption, re.IGNORECASE)
    return match.group(1) if match else None


def _omt_kind(caption: str) -> str | None:
    value = caption.casefold()
    kinds = (
        "object model identification",
        "object class structure",
        "interaction class structure",
        "directed interaction",
        "attribute",
        "parameter",
        "dimension",
        "time representation",
        "user-supplied tag",
        "synchronization",
        "transportation type",
        "update rate",
        "switches",
        "basic data representation",
        "simple data type",
        "enumerated data type",
        "array data type",
        "fixed record data type",
        "variant record data type",
        "reference data type",
        "notes",
        "interface specification services usage",
        "fom and som module merge results",
    )
    return next((kind for kind in kinds if kind in value), None)


def _table_text(value: str) -> str:
    """Remove layout-only TeX wrappers while retaining cell text."""
    value = re.sub(r"(?m)^\s*%.*$", "", value)
    value = value.replace(r"\newline", " ").replace(r"\linebreak", " ")
    value = value.replace(r"\space{}", " ")
    value = re.sub(r"\\(?:hspace|vspace)\*?\{[^{}]*\}", "", value)
    for _ in range(6):
        previous = value
        value = re.sub(
            r"\\(?:mbox|textbf|textit|texttt|emph|textnormal|textsf|textrm)\{([^{}]*)\}",
            r"\1",
            value,
        )
        value = re.sub(r"\\resizebox\{[^{}]*\}\{[^{}]*\}\{([^{}]*)\}", r"\1", value)
        value = re.sub(r"\\makebox(?:\[[^]]*\]){1,2}\{([^{}]*)\}", r"\1", value)
        if value == previous:
            break
    value = re.sub(r"\\[a-zA-Z]+(?:\[[^]]*\])?", "", value)
    value = value.replace("{", "").replace("}", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


@dataclass(frozen=True, slots=True)
class _TableLayoutText:
    """A visible text primitive recovered from a faithful table layout."""

    offset: int
    text: str
    first: float
    second: float
    source: SourceRef


def _table_heading(value: str, source: LatexSourceProfile) -> tuple[str, str] | None:
    """Return a normalized table number/title from a visible layout primitive."""
    normalized = _table_text(value).replace("%", "").strip()
    match = re.search(
        r"\bTable\s+(?P<number>\d+)\s*(?:---|—|-)\s*(?P<title>.+)$",
        normalized,
        re.IGNORECASE,
    )
    if not match:
        return None
    return match.group("number"), normalized


def _cluster_index(value: float, values: Sequence[float], tolerance: float) -> int:
    """Assign a coordinate to a stable ordered cluster."""
    centers: list[float] = []
    for candidate in sorted(values):
        if not centers or abs(candidate - centers[-1]) > tolerance:
            centers.append(candidate)
        else:
            centers[-1] = (centers[-1] + candidate) / 2
    return min(range(len(centers)), key=lambda index: abs(centers[index] - value))


def _layout_table_primitives(
    text: str, source: LatexSourceProfile
) -> list[tuple[int, str, tuple[str, ...]]]:
    primitives = [
        (offset, "fixed", args)
        for offset, args, _end in _command_events(text, source.fixed_text_block, 7)
    ]
    rotated_name = getattr(source, "table_text_line", "")
    if rotated_name:
        primitives.extend(
            (offset, "rotated", args)
            for offset, args, _end in _command_events(text, rotated_name, 5)
        )
    primitives.sort(key=lambda item: item[0])
    return primitives


def _layout_table_headings(
    root: Path,
    path: Path,
    text: str,
    primitives: Sequence[TablePrimitive],
    source: LatexSourceProfile,
) -> list[tuple[int, str, str, str, float, SourceRef]]:
    headings: list[tuple[int, str, str, str, float, SourceRef]] = []
    for offset, kind, args in primitives:
        heading = _table_heading(args[-1], source)
        if heading is None:
            continue
        number, title = heading
        headings.append(
            (offset, kind, number, title, float(args[0]), _source(root, path, text, offset))
        )
    return headings


def _layout_table_position(args: Sequence[str], kind: str) -> tuple[float, float] | None:
    first = float(args[0])
    if kind == "fixed":
        try:
            font_size = float(args[4])
        except ValueError:
            return None
        # Body prose uses 9.96pt; table cells and headers are 9pt or smaller.
        if font_size > 9.2:
            return None
    return first, float(args[1])


def _layout_table_candidates(
    root: Path,
    path: Path,
    text: str,
    primitives: Sequence[TablePrimitive],
    source: LatexSourceProfile,
    *,
    kind: str,
    offset: int,
    next_offset: int,
    heading_first: float,
) -> list[_TableLayoutText]:
    candidates: list[_TableLayoutText] = []
    for primitive_offset, primitive_kind, args in primitives:
        if primitive_kind != kind:
            continue
        in_source_segment = offset < primitive_offset < next_offset
        # Rotated pages can draw rows before the heading; use the visible table band.
        first = float(args[0])
        in_rotated_table_band = kind == "rotated" and heading_first + 20.0 <= first <= 500.0
        if not in_source_segment and not in_rotated_table_band:
            continue
        value = _table_text(args[-1])
        if not value or _table_heading(value, source) is not None:
            continue
        position = _layout_table_position(args, kind)
        if position is None:
            continue
        first, second = position
        candidates.append(
            _TableLayoutText(
                offset=primitive_offset,
                text=value,
                first=first,
                second=second,
                source=_source(root, path, text, primitive_offset),
            )
        )
    return candidates


def _layout_table_record(
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
    primitives: Sequence[TablePrimitive],
    headings: Sequence[TableHeading],
    heading_index: int,
    existing_ids: AbstractSet[str],
) -> Table | None:
    offset, kind, number, title, heading_first, heading_source = headings[heading_index]
    next_offset = headings[heading_index + 1][0] if heading_index + 1 < len(headings) else len(text)
    candidates = _layout_table_candidates(
        root,
        path,
        text,
        primitives,
        source,
        kind=kind,
        offset=offset,
        next_offset=next_offset,
        heading_first=heading_first,
    )
    if not candidates:
        return None
    first_tolerance, second_tolerance = (4.0, 22.0) if kind == "fixed" else (3.0, 4.0)
    rows = [item.first for item in candidates]
    columns = [item.second for item in candidates]
    page_match = re.search(r"page-(\d+)", path.stem.casefold())
    page_label = page_match.group(1) if page_match else str(heading_source.line)
    table_id = f"table-{number}-p{page_label}"
    if table_id in existing_ids:
        table_id = f"{table_id}-f{heading_index + 1}"
    cells = tuple(
        TableCell(
            id=f"{table_id}.c{ordinal:04d}",
            table_id=table_id,
            text=item.text,
            row=_cluster_index(item.first, rows, first_tolerance),
            column=_cluster_index(item.second, columns, second_tolerance),
            source=item.source,
        )
        for ordinal, item in enumerate(candidates, 1)
    )
    domain: Literal["generic", "omt"] = "omt" if _omt_kind(title) else "generic"
    return Table(
        id=table_id,
        title=title,
        caption=title,
        number=number,
        continuation=False,
        cells=cells,
        source=heading_source,
        logical_id=f"table-{number}",
        domain=domain,
        omt_kind=_omt_kind(title),
    )


def _load_layout_tables_from_file(
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> tuple[Table, ...]:
    """Recover tables that were faithfully drawn without semantic cell macros.

    Older HLA faithful pages use ``HLAFixedBlock`` for portrait tables and
    ``HLARotatedLine`` for landscape tables. Their coordinates remain layout
    data; the title, visible cell text, logical number, and source provenance
    become the reusable semantic projection.
    """
    primitives = _layout_table_primitives(text, source)
    headings = _layout_table_headings(root, path, text, primitives, source)
    tables: list[Table] = []
    for heading_index in range(len(headings)):
        existing_ids = {item.id for item in tables}
        table = _layout_table_record(
            root,
            path,
            text,
            source,
            primitives,
            headings,
            heading_index,
            existing_ids,
        )
        if table is not None:
            tables.append(table)
    return tuple(tables)


def _table_position(
    candidate: _TableCellCandidate, grid: Sequence[_TableGridCell]
) -> tuple[int | None, int | None]:
    """Infer row/column from the layout grid without storing coordinates."""
    center_x = candidate.x + candidate.width / 2
    center_y = candidate.y + candidate.height / 2
    containing = [
        item
        for item in grid
        if item.x <= center_x <= item.x + item.width and item.y <= center_y <= item.y + item.height
    ]
    if not containing:
        return None, None
    target = min(
        containing,
        key=lambda item: (
            abs((item.x + item.width / 2) - center_x) + abs((item.y + item.height / 2) - center_y)
        ),
    )
    columns = sorted({item.x for item in grid})
    rows = sorted({item.y for item in grid})
    return rows.index(target.y), columns.index(target.x)


@dataclass(slots=True)
class _TableFileState:
    table_sources: dict[str, SourceRef]
    grids: dict[str, list[_TableGridCell]]
    candidates: dict[str, list[_TableCellCandidate]]
    current_table: str | None = None
    current_cell: str | None = None


def _table_semantic_events(
    text: str, source: LatexSourceProfile
) -> list[tuple[int, str, tuple[str, ...]]]:
    events: list[tuple[int, str, tuple[str, ...]]] = []
    for name, count, kind in (
        (source.stable_id, 1, "stable"),
        (source.table_grid_cell, 4, "grid"),
        (source.table_cell_text, 7, "cell"),
    ):
        events.extend((offset, kind, args) for offset, args in _commands(text, name, count))
    events.sort(key=lambda item: item[0])
    return events


def _consume_stable_table_id(
    state: _TableFileState,
    root: Path,
    path: Path,
    text: str,
    offset: int,
    identifier: str,
) -> None:
    table_match = re.match(r"^(?P<table>.+\.t\d+)$", identifier)
    cell_match = re.match(r"^(?P<table>.+\.t\d+)\.c\d+$", identifier)
    if table_match:
        table_id = table_match.group("table")
        if table_id is None:
            return
        state.current_table = table_id
        state.current_cell = None
        state.table_sources.setdefault(table_id, _source(root, path, text, offset))
    elif cell_match:
        table_id = cell_match.group("table")
        if table_id is None:
            return
        state.current_table = table_id
        state.current_cell = identifier


def _consume_table_event(
    state: _TableFileState,
    root: Path,
    path: Path,
    text: str,
    offset: int,
    kind: str,
    args: Sequence[str],
) -> None:
    if kind == "stable":
        _consume_stable_table_id(state, root, path, text, offset, args[0])
        return
    table_key = state.current_table
    if table_key is None:
        return
    if kind == "grid":
        state.grids.setdefault(table_key, []).append(
            _TableGridCell(*(float(value) for value in args))
        )
    elif kind == "cell" and state.current_cell is not None:
        state.candidates.setdefault(table_key, []).append(
            _TableCellCandidate(
                state.current_cell,
                table_key,
                _table_text(args[6]),
                float(args[0]),
                float(args[1]),
                float(args[2]),
                float(args[3]),
                _source(root, path, text, offset),
            )
        )


def _read_table_semantics(
    root: Path,
    path: Path,
    text: str,
    events: Sequence[CommandEvent],
) -> _TableFileState:
    state = _TableFileState(table_sources={}, grids={}, candidates={})
    for offset, kind, args in events:
        _consume_table_event(state, root, path, text, offset, kind, args)
    return state


def _collect_table_captions(
    root: Path, path: Path, text: str, source: LatexSourceProfile
) -> list[tuple[str, float, float, float, SourceRef]]:
    captions: list[tuple[str, float, float, float, SourceRef]] = []
    for offset, args in _commands(text, source.placed_block, 4):
        for caption_offset, caption_args in _commands(args[3], source.table_caption, 1):
            captions.append(
                (
                    _table_text(caption_args[0]),
                    float(args[0]),
                    float(args[1]),
                    float(args[2]),
                    _source(root, path, text, offset + caption_offset),
                )
            )
    return captions


def _collect_table_labels(
    root: Path, path: Path, text: str, source: LatexSourceProfile
) -> list[tuple[str, float, float, float, SourceRef]]:
    labels: list[tuple[str, float, float, float, SourceRef]] = []
    for offset, args in _commands(text, source.placed_block, 4):
        for name, count, title_index in source.table_heading_commands:
            for label_offset, label_args in _commands(args[3], name, count):
                labels.append(
                    (
                        _table_text(label_args[title_index]),
                        float(args[0]),
                        float(args[1]),
                        float(args[2]),
                        _source(root, path, text, offset + label_offset),
                    )
                )
    return labels


def _table_layout_bounds(
    grids: Mapping[str, Sequence[_TableGridCell]],
) -> list[tuple[str, float, float, float, float]]:
    bounds: list[tuple[str, float, float, float, float]] = []
    for table_id, grid in grids.items():
        if not grid:
            continue
        left = min(item.x for item in grid)
        top = min(item.y for item in grid)
        right = max(item.x + item.width for item in grid)
        bottom = max(item.y + item.height for item in grid)
        bounds.append((table_id, left, top, right, bottom))
    return bounds


def _caption_table_map(
    captions: Sequence[TableCaption],
    table_layout: Sequence[TableBounds],
) -> dict[str, tuple[str, SourceRef]]:
    caption_by_table: dict[str, tuple[str, SourceRef]] = {}
    for caption, x, y, width, source_ref in captions:
        if not table_layout:
            continue
        caption_x = float(x)
        caption_y = float(y)
        caption_right = caption_x + width
        following = [item for item in table_layout if item[2] >= caption_y]
        candidates_for_caption = following or table_layout
        table_id = min(
            candidates_for_caption,
            key=lambda item: (
                abs(item[2] - caption_y),
                abs(item[1] - caption_x) + abs(item[3] - caption_right),
            ),
        )[0]
        caption_by_table[table_id] = (caption, source_ref)
    return caption_by_table


def _title_table_map(
    labels: Sequence[TableCaption],
    table_layout: Sequence[TableBounds],
) -> dict[str, tuple[str, SourceRef]]:
    title_by_table: dict[str, tuple[str, SourceRef]] = {}
    for table_id, left, top, right, _ in table_layout:
        preceding = [
            label
            for label in labels
            if float(label[2]) <= top
            and float(label[1]) <= right
            and float(label[1]) + float(label[3]) >= left
        ]
        if preceding:
            label = max(preceding, key=lambda item: float(item[2]))
            title_by_table[table_id] = (label[0], label[4])
    return title_by_table


def _materialize_semantic_tables(
    state: _TableFileState,
    caption_by_table: Mapping[str, TableLabel],
    title_by_table: Mapping[str, TableLabel],
    table_domain: Literal["generic", "omt"],
) -> list[Table]:
    tables: list[Table] = []
    for table_id in sorted(state.table_sources):
        caption_info = caption_by_table.get(table_id)
        title_info = title_by_table.get(table_id)
        caption = caption_info[0] if caption_info else None
        title = title_info[0] if title_info else None
        table_source = (
            caption_info[1]
            if caption_info
            else title_info[1]
            if title_info
            else state.table_sources[table_id]
        )
        grid = tuple(state.grids.get(table_id, ()))
        cells = tuple(
            TableCell(
                id=candidate.id,
                table_id=table_id,
                text=candidate.text,
                row=_table_position(candidate, grid)[0],
                column=_table_position(candidate, grid)[1],
                source=candidate.source,
            )
            for candidate in state.candidates.get(table_id, ())
        )
        number = _table_number(caption or title or "")
        tables.append(
            Table(
                id=table_id,
                title=title,
                caption=caption,
                number=number,
                continuation="continued" in (caption or "").casefold(),
                cells=tuple(sorted(cells, key=lambda item: item.id)),
                source=table_source,
                logical_id=f"table-{number}" if number else table_id,
                domain=table_domain,
                omt_kind=_omt_kind(caption or title or "") if table_domain == "omt" else None,
            )
        )
    return tables


def _load_tables_from_file(
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> tuple[Table, ...]:
    """Extract semantic table captions/cells while ignoring layout geometry."""
    events = _table_semantic_events(text, source)
    state = _read_table_semantics(root, path, text, events)
    captions = _collect_table_captions(root, path, text, source)
    labels = _collect_table_labels(root, path, text, source)
    table_layout = _table_layout_bounds(state.grids)
    caption_by_table = _caption_table_map(captions, table_layout)
    title_by_table = _title_table_map(labels, table_layout)
    tables = _materialize_semantic_tables(
        state, caption_by_table, title_by_table, source.table_domain
    )
    if tables:
        return tuple(tables)
    return _load_layout_tables_from_file(root, path, text, source)


def _authored_layout_units(
    root: Path,
) -> tuple[tuple[Path, str], ...]:
    """Return reachable source plus semantic layout bodies exactly once.

    Page adapters are intentionally empty of visible prose.  Their Pydantic
    ``ContentBlock`` records retain the fidelity layout body, so semantic
    surface loaders must inspect that body rather than the adapter itself.
    """
    authored_blocks = _load_authored_content_blocks(root)
    authored_by_path = {
        item.source.path: item for item in authored_blocks if item.layout_body is not None
    }
    adapter_paths = {
        path
        for path in authored_by_path
        if (root / path).is_file()
        and "\\input{output/semantic/content-block-" in (root / path).read_text(encoding="utf-8")
    }
    units: list[tuple[Path, str]] = []
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        if relative in adapter_paths:
            continue
        units.append((path, path.read_text(encoding="utf-8")))
    units.extend(
        (root / item.source.path, item.layout_body)
        for item in authored_blocks
        if item.layout_body is not None
    )
    seen_units: set[tuple[str, str]] = set()
    result: list[tuple[Path, str]] = []
    for path, text in units:
        unit_key = (path.relative_to(root).as_posix(), text)
        if unit_key in seen_units:
            continue
        seen_units.add(unit_key)
        result.append((path, text))
    return tuple(result)


def _load_tables(root: Path, source: LatexSourceProfile) -> tuple[Table, ...]:
    tables: list[Table] = []
    for path, text in _authored_layout_units(root):
        tables.extend(_load_tables_from_file(root, path, text, source))
    ordered = sorted(tables, key=lambda item: (item.source.path, item.source.line, item.id))
    previous_by_logical_id: dict[str, Table] = {}
    normalized: list[Table] = []
    for table in ordered:
        previous = previous_by_logical_id.get(table.logical_id or table.id)
        continued = table.continuation or previous is not None
        normalized.append(
            table.model_copy(
                update={
                    "continuation": continued,
                    "continued_from": previous.id
                    if continued and previous is not None
                    else table.continued_from,
                }
            )
        )
        previous_by_logical_id[table.logical_id or table.id] = normalized[-1]
    return tuple(normalized)


def _derive_table_families(
    document_id: str,
    tables: Iterable[Table],
    authored_families: Iterable[TableFamily],
    content_blocks: Iterable[ContentBlock],
) -> tuple[TableFamily, ...]:
    """Complete table-family projections for layout-only table surfaces."""
    families = list(authored_families)
    assigned = {table_id for family in families for table_id in family.table_ids}
    grouped: dict[str, list[Table]] = {}
    for table in tables:
        if table.id in assigned:
            continue
        grouped.setdefault(table.logical_id or table.id, []).append(table)
    block_clause_by_path = {
        normalized_source_path(block.source.path): block.clause_id
        for block in content_blocks
        if block.clause_id is not None
    }
    used_ids = {family.id for family in families}
    for logical_id, fragments in sorted(grouped.items()):
        slug = re.sub(r"[^a-z0-9]+", "-", logical_id.casefold()).strip("-")
        family_id = f"table-family-{slug}"
        if family_id in used_ids:
            family_id = f"{family_id}-{document_id}"
        used_ids.add(family_id)
        first = fragments[0]
        source_path = normalized_source_path(first.source.path)
        families.append(
            TableFamily(
                id=family_id,
                title=first.title or first.caption or logical_id,
                table_ids=tuple(item.id for item in fragments),
                clause_id=block_clause_by_path.get(source_path),
                source=first.source,
            )
        )
    return tuple(
        sorted(
            families,
            key=lambda item: (item.source.path, item.source.line, item.id),
        )
    )


def _table_definition_key(value: str) -> str:
    """Normalize a table label for exact definition-term matching."""
    value = re.sub(r"\\[a-zA-Z]+(?:\{[^{}]*\})?", " ", value)
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def _link_table_cells_to_definitions(
    tables: Iterable[Table],
    definitions: Iterable[Definition],
) -> tuple[Table, ...]:
    """Attach only exact, source-visible definition-term matches to cells.

    This deliberately avoids substring matching: a cell containing prose
    about a federate should not acquire a dependency merely because
    ``federate`` is a defined term.  Exact normalized labels are the
    source-supported dependency boundary; unresolved cells remain queryable
    through their table/family ownership edges.
    """
    candidates: dict[str, list[str]] = {}
    for definition in definitions:
        key = _table_definition_key(definition.term)
        if len(key) < 6:
            continue
        candidates.setdefault(key, []).append(definition.id)
    unique_terms = {key: values[0] for key, values in candidates.items() if len(values) == 1}
    linked: list[Table] = []
    for table in tables:
        cells: list[TableCell] = []
        for cell in table.cells:
            definition_id = unique_terms.get(_table_definition_key(cell.text))
            record_ids = list(cell.record_ids)
            if definition_id is not None and definition_id not in record_ids:
                record_ids.append(definition_id)
            cells.append(cell.model_copy(update={"record_ids": tuple(record_ids)}))
        linked.append(table.model_copy(update={"cells": tuple(cells)}))
    return tuple(linked)


def _link_table_cells_to_requirements(
    tables: Iterable[Table],
    requirements: Iterable[Requirement],
) -> tuple[Table, ...]:
    """Attach source-overlapping explicit requirements to table cells.

    Table rows promoted from a rotated or continuation layout are semantic
    records in their own right.  Their source spans often cover several
    cells, so interval overlap is the correct provenance test; exact text
    matching would reintroduce the extraction loss this link is meant to
    prevent.
    """
    by_path: dict[str, list[Requirement]] = defaultdict(list)
    for requirement in requirements:
        if not requirement.id.startswith("requirement-candidate-table-"):
            continue
        by_path[normalized_source_path(requirement.source.path)].append(requirement)
    linked: list[Table] = []
    for table in tables:
        cells: list[TableCell] = []
        for cell in table.cells:
            cell_path = normalized_source_path(cell.source.path)
            cell_start = cell.source.line
            cell_end = cell.source.end_line or cell_start
            record_ids = list(cell.record_ids)
            for requirement in by_path.get(cell_path, ()):
                requirement_start = requirement.source.line
                requirement_end = requirement.source.end_line or requirement_start
                if (
                    requirement_start <= cell_end
                    and cell_start <= requirement_end
                    and requirement.id not in record_ids
                ):
                    record_ids.append(requirement.id)
            cells.append(cell.model_copy(update={"record_ids": tuple(record_ids)}))
        linked.append(table.model_copy(update={"cells": tuple(cells)}))
    return tuple(linked)
