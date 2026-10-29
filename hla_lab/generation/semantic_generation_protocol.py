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
        by_row.setdefault(row, {}).setdefault(column, []).append(_modern_table_text(cell.text))
    return by_row


def _join_protocol_wrapped(values: Sequence[str]) -> str:
    text = " ".join(values)
    return re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", text)


_PROTOCOL_GROUP_LABELS = frozenset(
    {"session management", "reconnection", "hla calls and callbacks"}
)


def _protocol_row_values(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
    row: int,
) -> list[str]:
    return [
        value for column in sorted(by_row.get(row, {})) for value in by_row[row][column] if value
    ]


def _protocol_registry_31_32(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    names_by_column = by_row.get(0, {})
    descriptions = by_row.get(1, {})
    defaults = by_row.get(2, {})
    rows: list[list[str]] = []
    for column in sorted(names_by_column):
        names = [value for value in names_by_column[column] if value.casefold() != "name"]
        if not names:
            continue
        description = [
            value for value in descriptions.get(column, ()) if value.casefold() != "description"
        ]
        default = [
            value
            for value in defaults.get(column, ())
            if not value.casefold().startswith("default") and value.casefold() != "(s)"
        ]
        rows.append(
            [names[-1], _join_protocol_wrapped(description), _join_protocol_wrapped(default)]
        )
    return ["Name", "Description", "Default (s)"], rows


def _protocol_registry_33(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    byte_ranges = [value for value in _protocol_row_values(by_row, 0) if value.casefold() != "byte"]
    names = [value for value in _protocol_row_values(by_row, 1) if value.casefold() != "name"]
    interpretations = [
        value for value in _protocol_row_values(by_row, 2) if value.casefold() != "interpretation"
    ]
    rows = [
        [byte_range, name, interpretation]
        for byte_range, name, interpretation in zip(
            byte_ranges, names, interpretations, strict=False
        )
    ]
    return ["Bytes", "Field", "Interpretation"], rows


def _protocol_registry_34(
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    rows: list[list[str]] = []
    current_group = ""
    columns = sorted(set(by_row.get(0, {})) | set(by_row.get(1, {})))
    for column in columns:
        values = [
            value for value in by_row.get(0, {}).get(column, ()) if value.casefold() != "value"
        ]
        types = [value for value in by_row.get(1, {}).get(column, ()) if value.casefold() != "type"]
        messages: list[str] = []
        for value in types:
            if value.casefold() in _PROTOCOL_GROUP_LABELS:
                current_group = value
            else:
                messages.append(value)
        rows.extend(
            [value, message, current_group, _protocol_message_direction(message)]
            for value, message in zip(values, messages, strict=False)
        )
    return ["Value", "Message", "Group", "Direction"], rows


def _protocol_registry_default(
    table: Table,
    by_row: Mapping[int, Mapping[int, Sequence[str]]],
) -> tuple[list[str], list[list[str]]]:
    byte_ranges = [value for value in _protocol_row_values(by_row, 0) if value.casefold() != "byte"]
    names = [value for value in _protocol_row_values(by_row, 1) if value.casefold() != "name"]
    descriptions = [
        value for value in _protocol_row_values(by_row, 2) if value.casefold() != "description"
    ]
    if len(descriptions) > len(names) and names:
        descriptions = [
            *descriptions[: len(names) - 1],
            _join_protocol_wrapped(descriptions[len(names) - 1 :]),
        ]
    descriptions.extend([""] * max(0, len(names) - len(descriptions)))
    rows = [
        [byte_range, name, _protocol_message_direction(table.title or name), description]
        for byte_range, name, description in zip(byte_ranges, names, descriptions, strict=False)
    ]
    return ["Bytes", "Field", "Direction", "Description"], rows


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
