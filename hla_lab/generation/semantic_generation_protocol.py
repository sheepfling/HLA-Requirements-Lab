"""Protocol table rendering helpers for modern semantic pages."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    Mapping,
    Sequence,
)

from hla_lab.adapters.latex_renderer import (
    tex_escape,
)
from hla_lab.core.semantic_model import (
    Table,
)
from hla_lab.generation.semantic_generation_mom import _modern_mom_cell, _modern_mom_fixed_text
from hla_lab.generation.semantic_generation_tables import _modern_table_text


def _protocol_cells_by_row(table: Table) -> dict[int, dict[int, list[str]]]:
    by_row: dict[int, dict[int, list[str]]] = {}
    cells = []
    for cell in table.cells:
        if cell.row is None or cell.column is None:
            continue
        cells.append((cell.row, cell.column, cell))
    for row, column, cell in sorted(cells, key=lambda item: (item[0], item[1], item[2].id)):
        # In fixed-layout captures, a trailing ``-%`` marks a word split at
        # the end of a visual line (``mes-%`` + ``sage``). The shared table
        # normalizer removes that layout hyphen, which is right for standalone
        # cells but loses the evidence needed to rejoin this protocol cell.
        # Preserve it here; ``_join_protocol_wrapped`` removes it only when
        # the following fragment starts with a lowercase letter.
        value = cell.text.replace("-%", "-")
        by_row.setdefault(row, {}).setdefault(column, []).append(_modern_table_text(value))
    return by_row


def _join_protocol_wrapped(values: Sequence[str]) -> str:
    text = " ".join(value.strip() for value in values if value.strip())
    return re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", text)


_PROTOCOL_GROUP_LABELS = frozenset(
    {"session management", "reconnection", "hla calls and callbacks"}
)


def _protocol_header_row(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
    first: str,
    second: str,
    third: str | None = None,
) -> int | None:
    expected = {first.casefold(), second.casefold()}
    if third is not None:
        expected.add(third.casefold())
    for row, cells in sorted(by_row.items()):
        values = {
            re.sub(r"\s*\([^)]*\)", "", " ".join(parts)).strip().casefold()
            for parts in cells.values()
        }
        if expected.issubset(values):
            return row
    return None


def _protocol_cell(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
    row: int,
    column: int,
) -> str:
    return _join_protocol_wrapped(by_row.get(row, {}).get(column, ()))


def _protocol_registry_31_32(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    header = _protocol_header_row(by_row, "Name", "Description", "Default")
    if header is None:
        return ["Name", "Description", "Default (s)"], []
    rows: list[list[str]] = []
    for row_number, cells in sorted(by_row.items()):
        if row_number <= header:
            continue
        name = _protocol_cell(by_row, row_number, 0)
        description = _protocol_cell(by_row, row_number, 1)
        default = _protocol_cell(by_row, row_number, 2)
        if name and name.casefold() != "name":
            rows.append([name, description, default])
            continue
        if not rows:
            continue
        if description:
            rows[-1][1] = _join_protocol_wrapped((rows[-1][1], description))
        if default and default.casefold() != "(s)":
            rows[-1][2] = _join_protocol_wrapped((rows[-1][2], default))
    return ["Name", "Description", "Default (s)"], rows


def _protocol_registry_33(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    header = _protocol_header_row(by_row, "Byte", "Name", "Interpretation")
    if header is None:
        return ["Bytes", "Field", "Interpretation"], []
    rows = [
        [_protocol_cell(by_row, row, 0), _protocol_cell(by_row, row, 1), _protocol_cell(by_row, row, 2)]
        for row in sorted(by_row)
        if row > header and any(_protocol_cell(by_row, row, column) for column in range(3))
    ]
    return ["Bytes", "Field", "Interpretation"], rows


def _protocol_registry_34(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    rows: list[list[str]] = []
    current_group = ""
    header = _protocol_header_row(by_row, "Value", "Type")
    if header is None:
        return ["Value", "Message", "Group", "Direction"], []
    for row in sorted(by_row):
        if row <= header:
            continue
        value = _protocol_cell(by_row, row, 0)
        message = _protocol_cell(by_row, row, 1)
        if not value and message.casefold() in _PROTOCOL_GROUP_LABELS:
            current_group = message
            rows.append(["", "", current_group, ""])
            continue
        if value and message:
            rows.append([value, message, current_group, _protocol_message_direction(message)])
    return ["Value", "Message", "Group", "Direction"], rows


def _protocol_registry_default(
    table: Table,
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    header = _protocol_header_row(by_row, "Byte", "Name", "Description")
    message_number = table.number or ""
    has_derived_direction = message_number not in {"37", "39"}
    headers = (
        ["Bytes", "Field", "Direction", "Description"]
        if has_derived_direction
        else ["Bytes", "Field", "Description"]
    )
    if header is None:
        return headers, []

    rows: list[list[str]] = []
    for row_number, cells in sorted(by_row.items()):
        if row_number <= header:
            continue
        byte_range = _protocol_cell(by_row, row_number, 0)
        name = _protocol_cell(by_row, row_number, 1)
        description = _protocol_cell(by_row, row_number, 2)
        if byte_range:
            row = [byte_range, name]
            if has_derived_direction:
                row.append(_protocol_message_direction(table.title or name))
            row.append(description)
            rows.append(row)
            continue
        if not rows:
            continue
        if name:
            previous_name = rows[-1][1]
            rows[-1][1] = _join_protocol_wrapped((previous_name, name))
        if description:
            description_index = 3 if has_derived_direction else 2
            rows[-1][description_index] = _join_protocol_wrapped(
                (rows[-1][description_index], description)
            )
    return headers, rows


def _modern_protocol_rows(table: Table) -> tuple[list[str], list[list[str]]]:
    """Project protocol tables into stable registry rows."""
    by_row = _protocol_cells_by_row(table)
    number = table.number or ""
    if number in {"31", "32"}:
        return _protocol_registry_31_32(by_row)
    if number == "33":
        return _protocol_registry_33(by_row)
    if number == "34":
        return _protocol_registry_34(by_row)
    return _protocol_registry_default(table, by_row)


def _protocol_message_direction(value: str) -> str:
    name = _modern_table_text(value)
    if "---" in name:
        name = name.split("---", 1)[1].strip()
    name = name.split()[0] if name else ""
    if name.startswith(
        (
            "CTRL_NEW_SESSION_STATUS",
            "CTRL_HEARTBEAT_RESPONSE",
            "CTRL_SESSION_TERMINATED",
            "CTRL_RESUME_STATUS",
            "HLA_CALL_RESPONSE",
            "HLA_CALLBACK_REQUEST",
        )
    ):
        return "RTI -> FEDERATE"
    if name.startswith(
        (
            "CTRL_NEW_SESSION",
            "CTRL_HEARTBEAT",
            "CTRL_TERMINATE_SESSION",
            "CTRL_RESUME_REQUEST",
            "HLA_CALL_REQUEST",
            "HLA_CALLBACK_RESPONSE",
        )
    ):
        return "FEDERATE -> RTI"
    return ""


def _modern_protocol_table(table: Table) -> str:
    headers, rows = _modern_protocol_rows(table)
    number = tex_escape(_modern_table_text(table.number or ""))
    title = tex_escape(_modern_table_text(table.title or table.caption or "Protocol table"))
    if "---" in title:
        title = title.split("---", 1)[1].strip()
    if len(headers) == 3 and headers[0] == "Name":
        spec = r"@{}L{0.25\linewidth}YL{0.12\linewidth}@{}"
    elif headers[0] == "Bytes" and headers[1] == "Field" and len(headers) == 3:
        spec = r"@{}L{0.14\linewidth}L{0.25\linewidth}Y@{}"
    elif number == "34":
        spec = r"@{}L{0.08\linewidth}L{0.31\linewidth}L{0.22\linewidth}Y@{}"
    else:
        spec = r"@{}L{0.13\linewidth}L{0.22\linewidth}L{0.18\linewidth}Y@{}"
    header = " & ".join(f"\\RLTableHeaderCell{{{tex_escape(value)}}}" for value in headers) + r" \\"
    rendered = "\n".join(
        " & ".join(
            _modern_mom_cell(
                value,
                technical=index < 2 or headers[index] in {"Name", "Field", "Message", "Bytes"},
            )
            for index, value in enumerate(row)
        )
        + r" \\"
        + (r"\RLProductionRowRule" if index + 1 < len(rows) else "")
        for index, row in enumerate(rows)
    )
    return f"""\\RLInlineTableCaption{{{number}}}{{{title}}}
\\begingroup
\\setlength{{\\tabcolsep}}{{3.2pt}}
\\renewcommand{{\\arraystretch}}{{0.86}}
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


def _modern_protocol_page(
    tables: Sequence[Table],
    *,
    sequence: int,
    source_body: str,
) -> str:
    blocks: list[str] = []
    fragments = _modern_mom_fixed_text(source_body)
    context: list[str] = []
    if sequence == 402:
        context = [
            value
            for value in fragments
            if value.startswith(("The following parameters", "Protocol messages shall"))
        ]
    elif sequence == 404:
        context = [
            value
            for value in fragments
            if value.startswith(
                ("12.13.4.5.", "This message shall be sent", "Note that the Session ID")
            )
        ][:5]
    if context:
        blocks.append(
            r"\begin{minipage}{\linewidth}\RaggedRight\rmfamily\fontsize{7pt}{8.2pt}\selectfont "
            + " ".join(tex_escape(value) for value in context)
            + r"\end{minipage}\par\vspace{4pt}"
        )
    blocks.extend(_modern_protocol_table(table) for table in tables)
    return """\\HLASourcePage{{{source}}}{{{sequence}}}
\\begin{{RLLandscapePage}}
\\thispagestyle{{rl}}
{body}
\\end{{RLLandscapePage}}
""".format(source=sequence + 1, sequence=sequence, body="\n".join(blocks))
