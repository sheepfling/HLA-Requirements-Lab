"""Modern management-object-model table rendering helpers."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    Mapping,
    Sequence,
)
from collections.abc import (
    Set as AbstractSet,
)
from dataclasses import dataclass
from types import MappingProxyType

from hla_lab.adapters.latex_renderer import (
    tex_escape,
)
from hla_lab.core.semantic_model import (
    Table,
    TableCell,
)
from hla_lab.generation.semantic_generation_reflow import _argument_spans
from hla_lab.generation.semantic_generation_tables import _modern_table_text


def _modern_mom_anchor(
    cells: Sequence[object],
    aliases: Sequence[str],
    *,
    occurrence: int = 0,
) -> tuple[int, int] | None:
    """Find a source-table header anchor without trusting page coordinates."""

    wanted = tuple(alias.casefold() for alias in aliases)
    matches: list[tuple[int, int]] = []
    for cell in cells:
        row = getattr(cell, "row", None)
        column = getattr(cell, "column", None)
        if row is None or column is None or row > 4:
            continue
        text = _modern_table_text(getattr(cell, "text", "")).casefold()
        if any(text == alias or text.startswith(alias) for alias in wanted):
            matches.append((row, column))
    matches.sort()
    if occurrence >= len(matches):
        return None
    return matches[occurrence]


def _modern_mom_cell(value: str, *, technical: bool = False) -> str:
    """Render a variable-height MOM cell with the shared family grammar."""

    text = _modern_table_text(value)
    if not text:
        return r"\mbox{}"
    escaped = (
        tex_escape(text)
        .replace(r"\_", r"\_\hspace{0pt}\penalty0 ")
        .replace(",", r",\hspace{0pt}\penalty0 ")
        .replace(".", r".\hspace{0pt}\penalty0 ")
    )
    if technical:
        # Permit a line break at semantic token boundaries without inserting
        # a visible separator or changing the searchable identifier.
        escaped = re.sub(
            r"(?<=HLA)(?=[a-z])",
            lambda _match: r"\hspace{0pt}",
            escaped,
        )
        escaped = re.sub(
            r"(?<=[a-z0-9])(?=[A-Z])",
            lambda _match: r"\hspace{0pt}",
            escaped,
        )
    if technical:
        size = ("7.0pt", "7.8pt")
    elif len(text) > 250:
        size = ("6.1pt", "6.9pt")
    else:
        size = ("6.9pt", "7.8pt")
    family = r"\RLMono" if technical else r"\rmfamily"
    return (
        r"\begin{minipage}[t]{\linewidth}\setlength{\parskip}{0pt}"
        r"\setlength{\parindent}{0pt}\RaggedRight"
        + family
        + rf"\fontsize{{{size[0]}}}{{{size[1]}}}\selectfont "
        + escaped
        + r"\end{minipage}"
    )


_MOM_NUMBER_FIELD_PLANS: Mapping[str, tuple[list[tuple[str, tuple[str, ...]]], str]] = (
    MappingProxyType(
        {
            "8": (
                [
                    ("transport / order", ("Order",)),
                    ("availability", ("Available",)),
                    ("update", ("Update",)),
                    ("data type", ("Data type",)),
                    ("attribute", ("Attribute",)),
                    ("object", ("Object",)),
                ],
                "attribute",
            ),
            "9": (
                [
                    ("transport / order", ("Order",)),
                    ("availability", ("Available",)),
                    ("data type", ("Data type",)),
                    ("parameter", ("Parameter",)),
                    ("interaction", ("Interaction",)),
                ],
                "parameter",
            ),
            "17": ([("semantics", ("Semantics",)), ("object", ("Object",))], "object"),
            "18": (
                [("semantics", ("Semantics",)), ("interaction", ("Interaction",))],
                "interaction",
            ),
            "19": (
                [
                    ("semantics", ("Semantics",)),
                    ("attribute", ("Attribute",)),
                    ("class", ("Class",)),
                ],
                "attribute",
            ),
            "20": (
                [
                    ("semantics", ("Semantics",)),
                    ("parameter", ("Parameter",)),
                    ("class", ("Class",)),
                ],
                "parameter",
            ),
        }
    )
)
_MOM_KIND_FIELD_PLANS: Mapping[str, tuple[list[tuple[str, tuple[str, ...]]], str]] = (
    MappingProxyType(
        {
            "dimension": (
                [
                    ("value when unspecified", ("Value when",)),
                    ("normalization function", ("Normalization function",)),
                    ("dimension", ("Dimension",)),
                    ("data type", ("Data type",)),
                    ("name", ("Name",)),
                ],
                "name",
            ),
            "basic data representation": (
                [
                    ("encoding", ("Encoding",)),
                    ("endian", ("Endian",)),
                    ("interpretation", ("Interpretation",)),
                    ("size in bits", ("Size in",)),
                    ("name", ("Name",)),
                ],
                "name",
            ),
            "simple data type": (
                [
                    ("semantics", ("Semantics",)),
                    ("accuracy", ("Accuracy",)),
                    ("resolution", ("Resolution",)),
                    ("units", ("Units",)),
                    ("representation", ("Representation",)),
                    ("name", ("Name",)),
                ],
                "name",
            ),
            "reference data type": (
                [
                    ("semantics", ("Semantics",)),
                    ("referenced attribute", ("Referenced Attribute",)),
                    ("referenced class", ("Referenced class",)),
                    ("representation", ("Representation",)),
                    ("name", ("Name",)),
                ],
                "name",
            ),
            "enumerated data type": (
                [
                    ("semantics", ("Semantics",)),
                    ("values", ("Values",)),
                    ("enumerator", ("Enumerator",)),
                    ("representation", ("Representation",)),
                    ("name", ("Name",)),
                ],
                "name",
            ),
            "array data type": (
                [
                    ("semantics", ("Semantics",)),
                    ("encoding", ("Encoding",)),
                    ("cardinality", ("Cardinality",)),
                    ("element type", ("Element Type",)),
                    ("name", ("Name",)),
                ],
                "name",
            ),
            "fixed record data type": (
                [
                    ("semantics", ("Semantics",)),
                    ("encoding", ("Encoding",)),
                    ("field semantics", ("Semantics",)),
                    ("type", ("Type",)),
                    ("field", ("Name",)),
                    ("record", ("Record name",)),
                ],
                "field",
            ),
        }
    )
)


def _modern_mom_field_plan(table: Table) -> tuple[list[tuple[str, tuple[str, ...]]], str]:
    """Return output fields and the field that starts a logical MOM record."""
    number_plan = _MOM_NUMBER_FIELD_PLANS.get(table.number or "")
    if number_plan is not None:
        return list(number_plan[0]), number_plan[1]
    kind_plan = _MOM_KIND_FIELD_PLANS.get(table.omt_kind or "")
    if kind_plan is not None:
        return list(kind_plan[0]), kind_plan[1]
    return [("content", ("Content",))], "content"


def _modern_mom_cells_by_row(table: Table) -> dict[int, list[TableCell]]:
    rows: dict[int, list[TableCell]] = {}
    for cell in table.cells:
        if cell.row is None or cell.column is None:
            continue
        rows.setdefault(cell.row, []).append(cell)
    for values in rows.values():
        values.sort(key=lambda cell: (cell.column, cell.id))

    # A fixed-page extractor may put the continuation of a technical token in
    # the next physical row, for example ``HLAFOMmoduleDesigna-%`` followed by
    # ``torList%``.  Fold that source line break before row detection so the
    # modern registry receives one identifier and does not treat the
    # continuation as a new logical record.
    consumed: set[str] = set()
    for row_number in sorted(rows):
        for cell in rows[row_number]:
            if cell.id in consumed:
                continue
            raw = str(cell.text).strip()
            if not re.search(r"-%\s*$", raw):
                continue
            continuation = next(
                (
                    candidate
                    for candidate in rows.get(row_number + 1, ())
                    if candidate.column == cell.column and candidate.id not in consumed
                ),
                None,
            )
            if continuation is None:
                continue
            merged = re.sub(r"-%\s*$", "", raw) + str(continuation.text).strip()
            if hasattr(cell, "model_copy"):
                replacement = cell.model_copy(update={"text": merged})
                values = rows[row_number]
                values[values.index(cell)] = replacement
            consumed.add(continuation.id)
        rows[row_number + 1] = [
            cell for cell in rows.get(row_number + 1, ()) if cell.id not in consumed
        ]
    rows = {row: values for row, values in rows.items() if values}
    return rows


def _mom_registry_anchors(
    cells: Sequence[TableCell],
    plan: Sequence[tuple[str, tuple[str, ...]]],
) -> tuple[dict[str, int], list[int]]:
    anchor_positions: dict[str, int] = {}
    header_rows: list[int] = []
    for key, aliases in plan:
        found = _modern_mom_anchor(cells, aliases)
        if found is not None:
            row, column = found
            anchor_positions[key] = column
            header_rows.append(row)
    return anchor_positions, header_rows


def _mom_content_fallback(cells: Sequence[TableCell]) -> tuple[list[str], list[list[str]]]:
    content = [_modern_table_text(cell.text) for cell in cells if _modern_table_text(cell.text)]
    return ["Content"], [[value] for value in content]


def _mom_registry_header_boundary(
    number: str,
    cells: Sequence[TableCell],
    rows: Mapping[int, Sequence[TableCell]],
    header_rows: Sequence[int],
) -> tuple[Mapping[int, Sequence[TableCell]], int]:
    header_end = max(header_rows, default=0)
    if number not in {"17", "18"}:
        return rows, header_end
    semantic_rows = sorted(
        {
            cell.row
            for cell in cells
            if cell.row is not None and _modern_table_text(cell.text).casefold() == "semantics"
        }
    )
    if not semantic_rows:
        return rows, header_end
    header_end = semantic_rows[0]
    row_cutoff = next((row for row in semantic_rows if row > header_end), None)
    if row_cutoff is not None:
        rows = {row: row_cells for row, row_cells in rows.items() if row < row_cutoff}
    return rows, header_end


def _mom_registry_start_columns(number: str, start_anchor: int) -> set[int]:
    if number in {"17", "18"}:
        return {start_anchor - 1, start_anchor, start_anchor + 1}
    if number in {"8", "9", "19", "20"}:
        return {start_anchor, start_anchor + 1}
    return {start_anchor + offset for offset in range(4)}


def _mom_row_starts(row_cells: Sequence[TableCell], candidates: AbstractSet[int]) -> bool:
    return any(
        cell.column in candidates
        and _modern_table_text(cell.text).casefold() not in {"", "(continued)"}
        and "(cont.)" not in _modern_table_text(cell.text).casefold()
        for cell in row_cells
    )


def _mom_registry_start_rows(
    rows: Mapping[int, Sequence[TableCell]],
    header_end: int,
    candidates: AbstractSet[int],
) -> list[int]:
    start_rows = sorted(
        {
            row
            for row, row_cells in rows.items()
            if row > header_end and _mom_row_starts(row_cells, candidates)
        }
    )
    return start_rows or [header_end + 1]


def _mom_registry_field_key(
    number: str,
    cell: TableCell,
    source_order: Sequence[str],
    anchors: Mapping[str, int],
    start_anchor: int,
) -> str:
    column = cell.column if cell.column is not None else -1
    if number in {"17", "18"}:
        target = "object" if number == "17" else "interaction"
        return target if column >= start_anchor - 1 else "semantics"
    if len(source_order) == 1:
        return source_order[0]
    key = min(source_order, key=lambda item: abs(column - anchors[item]))
    for index, candidate in enumerate(source_order[:-1]):
        next_key = source_order[index + 1]
        if anchors[candidate] <= column < anchors[next_key]:
            return candidate
    return key


def _mom_registry_group_cells(
    rows: Mapping[int, Sequence[TableCell]],
    start_row: int,
    end_row: int | None,
) -> list[TableCell]:
    return [
        cell
        for row, row_cells in rows.items()
        if row >= start_row and (end_row is None or row < end_row)
        for cell in row_cells
    ]


def _mom_registry_values(
    group_cells: Sequence[TableCell],
    plan: Sequence[tuple[str, tuple[str, ...]]],
    number: str,
    source_order: Sequence[str],
    anchors: Mapping[str, int],
    start_anchor: int,
) -> dict[str, list[str]]:
    values = {key: [] for key, _aliases in plan}
    for cell in sorted(group_cells, key=lambda item: (item.row, item.column, item.id)):
        text = _modern_table_text(cell.text)
        if not text or text.casefold() == "(continued)":
            continue
        key = _mom_registry_field_key(number, cell, source_order, anchors, start_anchor)
        text = re.sub(r"\s*\(cont\.\)\s*$", "", text, flags=re.IGNORECASE)
        if text and text not in values[key]:
            values[key].append(text)
    return values


def _reorder_mom_registry_fields(
    labels: Sequence[str],
    rows: Sequence[Sequence[str]],
    start_key: str,
) -> tuple[list[str], list[list[str]]]:
    if start_key not in labels:
        return list(labels), [list(row) for row in rows]
    start_index = labels.index(start_key)
    order = [start_index] + [index for index in range(len(labels)) if index != start_index]
    return (
        [labels[index] for index in order],
        [[row[index] for index in order] for row in rows],
    )


def _split_mom_interaction_prose(rows: Sequence[Sequence[str]]) -> list[list[str]]:
    markers = (". It shall ", ". Cause the RTI ", ". The interaction ")
    split_rows: list[list[str]] = []
    for source_row in rows:
        row = list(source_row)
        interaction = row[0]
        for marker in markers:
            split_at = interaction.find(marker)
            if split_at <= 0:
                continue
            tail = interaction[split_at + 2 :].strip()
            row[0] = interaction[: split_at + 1].strip()
            row[1] = f"{tail} {row[1]}".strip().replace("the The interaction", "the interaction")
            break
        split_rows.append(row)
    return split_rows


def _modern_mom_registry_rows(table: Table) -> tuple[list[str], list[list[str]]]:
    """Build semantic rows from source-cell anchors and continuation ranges."""
    plan, start_key = _modern_mom_field_plan(table)
    cells = tuple(table.cells)
    anchors, header_rows = _mom_registry_anchors(cells, plan)
    if not anchors:
        return _mom_content_fallback(cells)
    source_order = sorted(anchors, key=lambda key: (anchors[key], key))
    start_anchor = anchors.get(start_key, max(anchors.values()))
    number = table.number or ""
    source_rows, header_end = _mom_registry_header_boundary(
        number, cells, _modern_mom_cells_by_row(table), header_rows
    )
    candidates = _mom_registry_start_columns(number, start_anchor)
    start_rows = _mom_registry_start_rows(source_rows, header_end, candidates)
    labels = [key for key, _aliases in plan]
    output_rows: list[list[str]] = []
    for index, start_row in enumerate(start_rows):
        end_row = start_rows[index + 1] if index + 1 < len(start_rows) else None
        group_cells = _mom_registry_group_cells(source_rows, start_row, end_row)
        values = _mom_registry_values(
            group_cells, plan, number, source_order, anchors, start_anchor
        )
        if any(values.values()):
            output_rows.append([" ".join(values[key]) for key, _aliases in plan])
    labels, output_rows = _reorder_mom_registry_fields(labels, output_rows, start_key)
    if number == "18" and len(labels) >= 2:
        output_rows = _split_mom_interaction_prose(output_rows)
    return labels, output_rows


def _modern_mom_hierarchy_names(table: Table) -> list[str]:
    # The PDF extractor records the horizontal branch position as a table
    # column, but the source table sometimes places sibling branches on one
    # physical row.  Treating that column as the printed depth produced
    # misleading values such as 0, 1, 7 and 10.  The MOM hierarchy has a
    # stable semantic grammar, so recover depth from the class role instead
    # of exposing extraction coordinates.
    names: list[str] = []
    for _row_number, cells in sorted(_modern_mom_cells_by_row(table).items()):
        for cell in cells:
            text = _modern_table_text(cell.text)
            if not text or text.casefold() == "(continued)":
                continue
            marker = ""
            if text in {"(N)", "(P)", "(S)"}:
                marker = f" {text}"
                if names:
                    names[-1] = f"{names[-1]}{marker}"
                continue
            # Keep one logical node per extracted identifier.  Siblings that
            # share a source row must not be joined with a slash.
            if text not in names:
                names.append(text)
    return names


def _modern_mom_hierarchy_rows(table: Table) -> list[tuple[str, str]]:
    """Turn the two MOM class-structure tables into a compact tree registry."""
    names = _modern_mom_hierarchy_names(table)
    number = table.number or ""
    if number == "6":
        depth_by_name = {
            "HLAobjectRoot (N)": "0",
            "HLAmanager (N)": "1",
            "HLAfederate (P)": "2",
            "HLAfederation (P)": "2",
        }
        return [(depth_by_name.get(name, "0"), name) for name in names]

    if number == "7":
        return [(_modern_mom_interaction_depth(name), name) for name in names]

    return [("0", name) for name in names]


def _modern_mom_interaction_depth(value: str) -> str:
    """Return the semantic depth for a MOM interaction-class node."""

    name = value.strip()
    if name.startswith("HLAinteractionRoot"):
        return "0"
    if name == "HLAmanager (N)":
        return "1"
    if name == "HLAfederate (N)":
        return "2"
    if name in {"HLAadjust (N)", "HLArequest (N)", "HLAreport (N)", "HLAservice (N)"}:
        return "3"
    return "4"


_MOM_SERVICE_INTERACTIONS = frozenset(
    {
        "HLAresignFederationExecution",
        "HLAsynchronizationPointAchieved",
        "HLAfederateSaveBegun",
        "HLAfederateSaveComplete",
        "HLAfederateRestoreComplete",
        "HLApublishObjectClassAttributes",
        "HLAunpublishObjectClassAttributes",
        "HLApublishInteractionClass",
        "HLAunpublishInteractionClass",
        "HLApublishObjectClassDirectedInteractions",
        "HLAunpublishObjectClassDirectedInteractions",
        "HLAsubscribeObjectClassAttributes",
        "HLAunsubscribeObjectClassAttributes",
        "HLAsubscribeInteractionClass",
        "HLAunsubscribeInteractionClass",
        "HLAsubscribeObjectClassDirectedInteractions",
        "HLAunsubscribeObjectClassDirectedInteractions",
        "HLAdeleteObjectInstance",
        "HLAlocalDeleteObjectInstance",
        "HLArequestAttributeTransportationTypeChange",
        "HLArequestInteractionTransportationTypeChange",
        "HLAunconditionalAttributeOwnershipDivestiture",
        "HLAenableTimeRegulation",
        "HLAdisableTimeRegulation",
        "HLAenableTimeConstrained",
        "HLAdisableTimeConstrained",
        "HLAtimeAdvanceRequest",
        "HLAtimeAdvanceRequestAvailable",
        "HLAnextMessageRequest",
        "HLAnextMessageRequestAvailable",
        "HLAflushQueueRequest",
        "HLAenableAsynchronousDelivery",
        "HLAdisableAsynchronousDelivery",
        "HLAmodifyLookahead",
        "HLAchangeAttributeOrderType",
        "HLAchangeInteractionOrderType",
    }
)


def _inferred_mom_parent(number: str, target: str) -> str:
    """Fill source-table continuation gaps from the MOM hierarchy grammar."""
    if number != "18" or "." in target:
        return ""
    if target == "HLAfederate":
        return "HLAmanager"
    if target in {"HLAadjust", "HLArequest", "HLAreport", "HLAservice"}:
        return "HLAmanager.HLAfederate"
    if target in {"HLAsetTiming", "HLAmodifyAttributeState", "HLAsetSwitches"}:
        return "HLAmanager.HLAfederate.HLAadjust"
    if target.startswith("HLArequest"):
        return "HLAmanager.HLAfederate.HLArequest"
    if target.startswith("HLAreport"):
        return "HLAmanager.HLAfederate.HLAreport"
    if target in _MOM_SERVICE_INTERACTIONS:
        return "HLAmanager.HLAfederate.HLAservice"
    return ""


def _mom_definition_identifiers(
    number: str,
    identifiers: Sequence[tuple[str, int]],
) -> tuple[list[tuple[str, int]], list[str]]:
    if number == "17":
        return [item for item in identifiers if item[1] >= 8][-1:], []
    hierarchy = [item for item in identifiers if item[1] >= 5]
    return hierarchy[:1], [value for value, _column in hierarchy[1:]]


def _mom_definition_prose(
    values: Sequence[tuple[str, int]],
    identifiers: Sequence[tuple[str, int]],
    number: str,
) -> list[str]:
    minimum_identifier_column = 8 if number == "17" else 5
    identifier_columns = {
        column for _value, column in identifiers if column >= minimum_identifier_column
    }
    ignored = {"object", "interaction", "semantics", "(continued)"}
    return [
        value
        for value, column in values
        if not (
            re.fullmatch(r"(?:HLA|HL)[A-Za-z0-9_.]+(?: \(cont\.\))?", value)
            and column in identifier_columns
        )
        and value.casefold() not in ignored
    ]


@dataclass(frozen=True, slots=True)
class _MomRowUpdate:
    row: tuple[str, ...]
    append: bool


def _append_mom_definition_row(
    number: str,
    values: Sequence[tuple[str, int]],
    previous_row: Sequence[str] | None,
) -> _MomRowUpdate | None:
    if not values:
        return None
    pattern = re.compile(r"(?:HLA|HL)[A-Za-z0-9_.]+(?: \(cont\.\))?")
    identifiers = [(value, column) for value, column in values if pattern.fullmatch(value)]
    targets, parents = _mom_definition_identifiers(number, identifiers)
    prose = _mom_definition_prose(values, identifiers, number)
    if targets:
        target = re.sub(r" \(cont\.\)$", "", targets[0][0]).replace("HLmanager.", "HLAmanager.")
        if previous_row is not None and previous_row[0] == target:
            updated = list(previous_row)
            prose_column = 2 if len(updated) > 2 else -1
            updated[prose_column] = f"{updated[prose_column]} {' '.join(prose)}".strip()
            return _MomRowUpdate(row=tuple(updated), append=False)
        elif number == "17":
            return _MomRowUpdate(row=(target, " ".join(prose)), append=True)
        else:
            parent = " ".join(parents) or _inferred_mom_parent(number, target)
            return _MomRowUpdate(row=(target, parent, " ".join(prose)), append=True)
    elif previous_row is not None:
        updated = list(previous_row)
        updated[-1] = f"{updated[-1]} {' '.join(prose)}".strip()
        return _MomRowUpdate(row=tuple(updated), append=False)
    return None


def _modern_mom_definition_rows(table: Table) -> tuple[list[str], list[list[str]]]:
    """Recover definition records as identifier, parent, and prose fields.

    Tables 17 and 18 are long two-column source tables. Their wrapped lines
    are captured in several physical columns, which made the old anchor
    heuristic put semantic sentences into the identifier column. Start a
    record from the exact HLA identifier cells and append all following
    source fragments until the next identifier.
    """
    number = table.number or ""
    rows: list[list[str]] = []
    for _row_number, cells in sorted(_modern_mom_cells_by_row(table).items()):
        values = [
            (_modern_table_text(cell.text), cell.column if cell.column is not None else -1)
            for cell in cells
            if _modern_table_text(cell.text)
        ]
        update = _append_mom_definition_row(
            number,
            values,
            previous_row=rows[-1] if rows else None,
        )
        if update is not None:
            if update.append:
                rows.append(list(update.row))
            else:
                rows[-1] = list(update.row)
    label = "Object class" if number == "17" else "Interaction class"
    headers = [label, "Semantics"] if number == "17" else [label, "Parent class", "Semantics"]
    return headers, rows


def _is_mom_hierarchy_source_heading(text: str) -> bool:
    return (
        not text
        or text.startswith(("IEEE Std", "IEEE Standard", "Federate Interface Specification"))
        or text.startswith("Table 7---")
        or text.casefold() == "(continued)"
    )


def _modern_mom_fixed_source_row(
    body: str,
    match: re.Match[str],
) -> tuple[float, str] | None:
    spans = _argument_spans(body, match.start(), 7)
    if not spans:
        return None
    try:
        x = float(body[spans[0][0] : spans[0][1]])
    except ValueError:
        return None
    raw = body[spans[-1][0] : spans[-1][1]]
    for _ in range(4):
        updated = re.sub(r"\\(?:textbf|textit|emph)\{([^{}]*)\}", r"\1", raw)
        if updated == raw:
            break
        raw = updated
    text = _modern_table_text(raw)
    if text.startswith("%"):
        text = text.lstrip("%").strip()
    return None if _is_mom_hierarchy_source_heading(text) else (x, text)


def _merge_mom_hierarchy_source_rows(
    raw_rows: Sequence[tuple[float, str]],
) -> list[tuple[float, str]]:
    rows: list[tuple[float, str]] = []
    for x, text in raw_rows:
        if text.casefold() == "(cont.)":
            continue
        if re.fullmatch(r"\([NPS]\)(?: \(cont\.\))?", text):
            if rows:
                rows[-1] = (rows[-1][0], f"{rows[-1][1]} {text.split()[0]}")
            continue
        rows.append((x, text))
    return rows


def _modern_mom_hierarchy_fixed_rows(body: str) -> list[tuple[str, str]]:
    """Recover continuation-page hierarchy rows from their semantic x-levels."""
    raw_rows = [
        row
        for match in re.finditer(r"\\HLAFixedBlock", body)
        if (row := _modern_mom_fixed_source_row(body, match)) is not None
    ]
    rows = _merge_mom_hierarchy_source_rows(raw_rows)
    return [(_modern_mom_interaction_depth(text), text) for _x, text in rows]


def _modern_mom_hierarchy_continuation(body: str) -> str | None:
    rows = _modern_mom_hierarchy_fixed_rows(body)
    if not rows:
        return None

    def render_table(chunk: Sequence[tuple[str, str]], width: str) -> str:
        rendered = "\n".join(
            " & ".join(
                (
                    _modern_mom_cell(depth, technical=True),
                    _modern_mom_cell("  " * int(depth) + value, technical=True),
                )
            )
            + r" \\"
            + (r"\RLProductionRowRule" if index + 1 < len(chunk) else "")
            for index, (depth, value) in enumerate(chunk)
        )
        return rf"""\begin{{minipage}}[t]{{{width}}}
\begingroup
\setlength{{\tabcolsep}}{{2.4pt}}
\renewcommand{{\arraystretch}}{{0.78}}
\begin{{tabularx}}{{\linewidth}}{{@{{}}L{{0.13\linewidth}}Y@{{}}}}
\RLProductionTopRule
\RLProductionHeaderBand
\RLTableHeaderCell{{Depth}} & \RLTableHeaderCell{{Class structure}} \\
\RLProductionHeaderRule
{rendered}
\RLProductionBottomRule
\end{{tabularx}}
\endgroup
\end{{minipage}}"""

    if len(rows) > 24:
        midpoint = (len(rows) + 1) // 2
        body = (
            r"\noindent "
            + render_table(rows[:midpoint], r"0.49\linewidth")
            + r"\hfill "
            + render_table(rows[midpoint:], r"0.49\linewidth")
        )
    else:
        body = render_table(rows, r"\linewidth")
    caption = (
        r"\RLInlineTableCaption{7}{MOM interaction class structure "
        r"table\quad\textit{(continued)}}"
    )
    return f"{caption}\n{body}\n"


def _modern_mom_table(table: Table) -> str:
    number = table.number or "MOM"
    title = _modern_table_text(table.title or table.caption or "MOM table")
    if "---" in title:
        title = title.split("---", 1)[1].strip()
    continuation = r"\quad\textit{(continued)}" if table.continuation else ""
    if number in {"17", "18"}:
        headers, rows = _modern_mom_definition_rows(table)
        spec = (
            r"@{}L{0.23\linewidth}p{0.75\linewidth}@{}"
            if number == "17"
            else r"@{}L{0.20\linewidth}L{0.27\linewidth}X@{}"
        )
        rendered = "\n".join(
            " & ".join(
                _modern_mom_cell(
                    value,
                    technical=index < (2 if number == "18" else 1),
                )
                for index, value in enumerate(row)
            )
            + r" \\"
            + (r"\RLProductionRowRule" if index + 1 < len(rows) else "")
            for index, row in enumerate(rows)
        )
        header = (
            " & ".join(f"\\RLTableHeaderCell{{{tex_escape(value)}}}" for value in headers) + r" \\"
        )
        if number == "17":
            table_body = f"""\\begin{{longtable}}{{{spec}}}
\\RLProductionTopRule
\\RLProductionHeaderBand
{header}
\\RLProductionHeaderRule
\\endfirsthead
\\RLProductionTopRule
\\RLProductionHeaderBand
\\RLTableHeaderCell{{Object class}} & \\RLTableHeaderCell{{Semantics (continued)}} \\\\
\\RLProductionHeaderRule
\\endhead
\\RLProductionBottomRule
\\endfoot
\\RLProductionBottomRule
\\endlastfoot
{rendered}
\\end{{longtable}}"""
        else:
            table_body = f"""\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}
\\RLProductionTopRule
\\RLProductionHeaderBand
{header}
\\RLProductionHeaderRule
{rendered}
\\RLProductionBottomRule
\\end{{tabularx}}"""
        caption = (
            rf"\RLInlineTableCaption{{{tex_escape(number)}}}"
            rf"{{{tex_escape(title)}{continuation}}}"
        )
        return (
            f"{caption}\n"
            "\\begingroup\n"
            "\\setlength{\\tabcolsep}{3.2pt}\n"
            "\\renewcommand{\\arraystretch}{0.96}\n"
            f"{table_body}\n"
            "\\endgroup\n"
        )
    if number in {"6", "7"}:
        headers = ["Depth", "Class structure"]
        rows = _modern_mom_hierarchy_rows(table)
        spec = r"@{}L{0.10\linewidth}Y@{}"
        rendered = "\n".join(
            " & ".join(
                (
                    _modern_mom_cell(depth, technical=True),
                    _modern_mom_cell("  " * int(depth) + value, technical=True),
                )
            )
            + r" \\"
            + (r"\RLProductionRowRule" if index + 1 < len(rows) else "")
            for index, (depth, value) in enumerate(rows)
        )
    else:
        headers, rows = _modern_mom_registry_rows(table)
        if not rows:
            rows = [[""] * len(headers)]
        spec = "@{}" + "".join([r"L{0.18\linewidth}"] + ["Y"] * (len(headers) - 1)) + "@{}"
        technical_keys = {
            "data type",
            "representation",
            "encoding",
            "type",
            "name",
            "attribute",
            "parameter",
            "object",
            "interaction",
            "class",
            "record",
            "field",
            "enumerator",
            "values",
        }
        rendered = "\n".join(
            " & ".join(
                _modern_mom_cell(value, technical=index == 0 or headers[index] in technical_keys)
                for index, value in enumerate(row)
            )
            + r" \\"
            + (r"\RLProductionRowRule" if index + 1 < len(rows) else "")
            for index, row in enumerate(rows)
        )
    header = " & ".join(f"\\RLTableHeaderCell{{{tex_escape(value)}}}" for value in headers) + r" \\"
    return f"""\\RLInlineTableCaption{{{tex_escape(number)}}}{{{tex_escape(title)}{continuation}}}
\\begingroup
\\setlength{{\\tabcolsep}}{{3.2pt}}
\\renewcommand{{\\arraystretch}}{{0.88}}
\\begin{{tabularx}}{{\\linewidth}}{{{spec}}}
\\RLProductionTopRule
\\RLProductionHeaderBand
{header}
\\RLProductionHeaderRule
{rendered}
\\RLProductionBottomRule
\\end{{tabularx}}
\\endgroup
"""


def _modern_mom_fixed_text(body: str) -> list[str]:
    """Extract visible source fragments without importing source furniture."""

    fragments: list[str] = []
    for match in re.finditer(r"\\HLAFixedBlock|\\HLARotatedLine", body):
        argument_count = 7 if match.group(0) == r"\HLAFixedBlock" else 5
        spans = _argument_spans(body, match.start(), argument_count)
        if not spans:
            continue
        raw = body[spans[-1][0] : spans[-1][1]]
        for _ in range(4):
            updated = re.sub(r"\\(?:textbf|textit|emph)\{([^{}]*)\}", r"\1", raw)
            if updated == raw:
                break
            raw = updated
        text = _modern_table_text(raw)
        if text.startswith("%"):
            text = text.lstrip("%").strip()
        if not text or text.startswith(
            ("IEEE Std", "IEEE Standard", "Federate Interface Specification")
        ):
            continue
        if re.fullmatch(r"\d+", text) or text in fragments:
            continue
        fragments.append(text)
    return fragments


def _modern_mom_page(
    tables: Sequence[Table],
    *,
    sequence: int,
    source_body: str,
) -> str:
    """Render one MOM source page through the Requirements Lab landscape system."""

    if tables:
        blocks: list[str] = []
        if sequence == 305:
            intro: list[str] = []
            for fragment in _modern_mom_fixed_text(source_body):
                if "Table 6" in fragment or "Table 7" in fragment:
                    break
                if "MOM OMT tables" not in fragment:
                    intro.append(fragment)
            if intro:
                blocks.append(
                    r"\begin{minipage}{\linewidth}\RaggedRight\rmfamily"
                    r"\fontsize{7pt}{8.4pt}\selectfont "
                    + " ".join(tex_escape(value) for value in intro)
                    + r"\end{minipage}\par\vspace{4pt}"
                )
        blocks.extend(_modern_mom_table(table) for table in tables)
    else:
        hierarchy_continuation = _modern_mom_hierarchy_continuation(source_body)
        if hierarchy_continuation is not None:
            blocks = [hierarchy_continuation]
        else:
            fragments = _modern_mom_fixed_text(source_body) or ["MOM table continuation"]
            blocks = [
                r"\RLInlineTableCaption{MOM}{MOM OMT table continuation}",
                r"\begin{minipage}{\linewidth}\RaggedRight"
                r"\ttfamily\fontsize{4.7pt}{5.25pt}\selectfont",
                "\\par ".join(tex_escape(text) for text in fragments),
                r"\end{minipage}",
            ]
    return """\\HLASourcePage{{{source}}}{{{sequence}}}
\\begin{{RLLandscapePage}}
\\thispagestyle{{rl}}
{body}
\\end{{RLLandscapePage}}
""".format(source=sequence + 1, sequence=sequence, body="\n".join(blocks))
