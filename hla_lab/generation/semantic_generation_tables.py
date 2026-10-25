"""Shared table-text and legacy table-page rendering helpers."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    Sequence,
)

from hla_lab.adapters.latex_renderer import (
    tex_escape,
)
from hla_lab.core.semantic_model import (
    Table,
)


def _modern_table_text(value: str) -> str:
    """Normalize source-table markup before applying the Lab text grammar."""

    text = str(value).strip()
    # A few source captures contain replacement characters where the source
    # PDF used typographic quotes/apostrophes. Keep released tables portable
    # and searchable by normalizing that encoding artefact.
    text = (
        text.replace("\ufffd", "'")
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    text = re.sub(r"\\textbackslash\{\}", r"\\", text)
    text = re.sub(r"\\([_%{}])", r"\1", text)
    text = text.replace(r"\,", " ")
    text = text.replace(r"\linebreak", " ")
    # The source-table extractor preserves a discretionary line-break marker
    # as ``-%``.  That marker is layout metadata, not part of technical
    # identifiers; leaving it in the modern registry creates visible tokens
    # such as ``HLAobjectClass-`` and ``HLAFOMmoduleDesigna-``.  Remove only
    # the marker form so ordinary hyphenated prose remains unchanged.
    text = re.sub(r"(?<=[A-Za-z0-9])-%", "", text)
    # Some fixed-page captures omit the percent marker and retain only the
    # visible break hyphen inside an HLA token (for example
    # ``HLAmanager.HLAfeder-ate``). Repair those token-local breaks while
    # leaving ordinary prose such as ``source-compilation`` untouched.
    text = re.sub(r"(HLA[A-Za-z][A-Za-z0-9.]*?)-(?=[A-Za-z])", r"\1", text)
    text = text.rstrip("%").strip()
    return re.sub(r"\s+", " ", text)


def _modern_table_code_cell(values: Sequence[str]) -> str:
    lines = [tex_escape(_modern_table_text(value)) for value in values]
    lines = [
        # ``\allowbreak`` is not provided by every minimal LaTeX profile used
        # by the family builds.  A zero penalty is the primitive equivalent we
        # need here: it preserves the token while allowing a break at natural
        # punctuation boundaries.
        line.replace(r"\_", r"\_\penalty0").replace(":", r":\penalty0").replace(",", r",\penalty0")
        for line in lines
    ]
    lines = [line for line in lines if line.strip() and line.strip() != r"\textbackslash{}"]
    if not lines:
        return r"\mbox{}"
    return (
        r"\begin{minipage}[t]{\linewidth}\setlength{\parskip}{0pt}"
        r"\setlength{\parindent}{0pt}\RaggedRight\RLMono"
        r"\fontsize{7.0pt}{7.8pt}\selectfont " + r"\par ".join(lines) + r"\end{minipage}"
    )


def _modern_table5_page(table: Table, *, sequence: int) -> str:
    """Render one source Table 5 page as a typed three-column registry."""

    cells = tuple(
        sorted(
            (cell for cell in table.cells if cell.row is not None and cell.column is not None),
            key=lambda cell: (cell.row, -cell.column, cell.id),
        )
    )
    type_start_column = max((cell.column for cell in cells), default=0)
    starts = [index for index, cell in enumerate(cells) if cell.column == type_start_column]
    rows: list[tuple[list[str], list[str], list[str]]] = []
    for index, start in enumerate(starts):
        group = cells[start : starts[index + 1] if index + 1 < len(starts) else None]
        if not group:
            continue
        type_column = group[0].column
        # Continuation lines in the source table can be indented one column
        # left of the first encoding line.  The table's three visual columns
        # occupy ranges of source-cell columns, not one coordinate each.
        encoding_left = type_column - 3
        type_values = [cell.text for cell in group if cell.column == type_column]
        encoding_values = [
            cell.text for cell in group if encoding_left <= cell.column < type_column
        ]
        example_values = [cell.text for cell in group if cell.column < encoding_left]
        if type_values and _modern_table_text(type_values[0]).casefold() == "type":
            continue
        rows.append((type_values, encoding_values, example_values))

    continuation = r"\quad\textit{(continued)}" if table.continuation else ""
    rendered_rows = "\n".join(
        " & ".join(
            (
                _modern_table_code_cell(type_values),
                _modern_table_code_cell(encoding_values),
                _modern_table_code_cell(example_values),
            )
        )
        + r" \\"
        + (r"\RLProductionRowRule" if index + 1 < len(rows) else "")
        for index, (type_values, encoding_values, example_values) in enumerate(rows)
    )
    return f"""\\HLASourcePage{{{sequence + 1}}}{{{sequence}}}
\\begin{{RLLandscapePage}}
\\thispagestyle{{rl}}
\\phantomsection\\label{{table-5-p{sequence}}}
\\RLInlineTableCaption{{5}}{{Encoding for HLA argument types{continuation}}}
\\begingroup
\\setlength{{\\tabcolsep}}{{4pt}}
\\renewcommand{{\\arraystretch}}{{0.92}}
\\begin{{tabularx}}{{\\linewidth}}{{@{{}}L{{0.21\\linewidth}}L{{0.34\\linewidth}}Y@{{}}}}
\\RLProductionTopRule
\\RLProductionHeaderBand
\\RLTableHeaderCell{{Type}} & \\RLTableHeaderCell{{Encoding}} & \\RLTableHeaderCell{{Example}} \\\\
\\RLProductionHeaderRule
{rendered_rows}
\\RLProductionBottomRule
\\end{{tabularx}}
\\endgroup
\\end{{RLLandscapePage}}
"""
