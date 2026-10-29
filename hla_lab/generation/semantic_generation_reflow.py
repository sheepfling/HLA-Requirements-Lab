"""Reflow and fixed-layout helpers for semantic generation."""

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
from hla_lab.core.parsing import (
    balanced_span,
)
from hla_lab.core.semantic_text import (
    _command_events,
)


def _fixed_text_blocks_for_reflow(
    body: str,
    *,
    minimum_y: float | None = None,
    maximum_y: float | None = None,
) -> list[tuple[float, str]]:
    """Extract readable text from a fixed source page in reading order.

    The 2025 interface source stores a few figure pages as absolute-positioned
    blocks.  Reusing those coordinates defeats the purpose of a modern chart
    page, so this small adapter keeps the authored words but lets LaTeX flow
    them around the generated vector figure.  It deliberately reads only
    ``HLAFixedBlock`` text and never imports the source page image or furniture.
    """

    records: list[tuple[float, str]] = []
    for _offset, args, _end in _command_events(body, "HLAFixedBlock", 7):
        try:
            y = float(args[1])
        except (IndexError, ValueError):
            continue
        if minimum_y is not None and y < minimum_y:
            continue
        if maximum_y is not None and y > maximum_y:
            continue
        text = args[6]
        # Fixed source lines use an explicit break and a comment terminator;
        # both are layout instructions, not publication content.
        text = re.sub(r"\\linebreak\s*%?", " ", text)
        text = text.replace("%", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if text and not re.match(r"\\draw(?:\b|\\)", text):
            records.append((y, text))
    return sorted(records, key=lambda item: item[0])


def _render_reflowed_fixed_text(records: Sequence[tuple[float, str]]) -> tuple[str, str]:
    """Turn fixed text records into natural-flow paragraphs and a footnote."""

    paragraphs: list[str] = []
    current: list[str] = []
    previous_y: float | None = None
    footnote = ""

    def flush() -> None:
        if current:
            paragraphs.append(" ".join(current).strip())
            current.clear()

    for y, text in records:
        if y >= 700:
            flush()
            marker = re.match(r".*?\\HLASupMark\{([^}]*)\}(.*)", text)
            if marker:
                footnote = rf"\HLACompactFootnote{{{marker.group(1)}}}{{{marker.group(2).strip()}}}"
            else:
                footnote = text
            previous_y = y
            continue
        heading = re.fullmatch(r"\\textbf\{4\.1\.1 Federate lifetime\}", text)
        if heading:
            flush()
            # This page is reflowed outside the normal sectioning stream. A
            # numbered subsubsection would therefore inherit the document
            # class counters and render as ``0.0.1`` even though the semantic
            # anchor/bookmark is 4.1.1. Keep the authoritative clause number
            # visible without touching counters.
            paragraphs.append(
                r"\par\noindent{\sffamily\bfseries\fontsize{10.5pt}{12pt}\selectfont "
                r"4.1.1 Federate lifetime\par}"
            )
            previous_y = y
            continue
        # A 12 pt fixed-line gap is a line wrap; a 24 pt gap is a paragraph
        # break. Requirement statements get their own readable block even
        # when the source coordinates used only one line of vertical space.
        paragraph_break = (previous_y is not None and y - previous_y > 18.0) or re.match(
            r"\\SemanticRequirement\b", text.lstrip()
        ) is not None
        if paragraph_break:
            flush()
        current.append(text)
        previous_y = y
    flush()
    prose = "\n\n".join(paragraphs)
    # TeX consumes the space following a control word.  This particular
    # source capture ends a semantic sentence macro immediately before the
    # word ``After``; emit an explicit space so the searchable/rendered text
    # cannot collapse into ``infrastructure.After``.
    prose = prose.replace(
        r"\SemanticContentBlockProseConnectServiceInfrastructureText After",
        r"\SemanticContentBlockProseConnectServiceInfrastructureText\ After",
    )
    return prose, footnote


def _modern_statechart_reflow_page(
    body: str,
    *,
    sequence: int,
    figure_number: int,
    caption: str,
    input_name: str,
) -> str:
    """Reflow the 2025 Figure 3/4 source pages around PlantUML artwork.

    Figures 3 and 4 share a source page with normative prose, so they cannot
    be handled by replacing the whole block with a figure-only landscape
    page.  Extracting the fixed text into ordinary paragraphs keeps the
    source order and lets the chart occupy a real landscape page with one
    generated caption.
    """

    if sequence == 42:
        records = _fixed_text_blocks_for_reflow(body, minimum_y=60, maximum_y=730)
        prose, footnote = _render_reflowed_fixed_text(records)
        if footnote:
            raise ValueError(
                f"unexpected footnote in Figure 4 continuation for sequence {sequence}"
            )
        return "\n".join(
            (
                r"\thispagestyle{hla-body}",
                r"\RaggedRight",
                prose,
                r"\clearpage",
                "",
            )
        )
    if not input_name.endswith(".pdf") or sequence not in {40, 41}:
        return body
    if sequence == 40:
        records = _fixed_text_blocks_for_reflow(body, minimum_y=350, maximum_y=730)
        prose, footnote = _render_reflowed_fixed_text(records)
        return "\n".join(
            (
                rf"\HLALandscapeFigurePDFPage{{{figure_number}}}"
                rf"{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
                r"\thispagestyle{hla-body}",
                r"\HLAAnchor{clause:4.1.1}",
                r"\pdfbookmark[2]{4.1.1 Federate lifetime}{bookmark:clause:4.1.1}",
                r"\RaggedRight",
                prose,
                footnote,
                r"\clearpage",
                "",
            )
        )

    before = _fixed_text_blocks_for_reflow(body, minimum_y=60, maximum_y=260)
    trailing = _fixed_text_blocks_for_reflow(body, minimum_y=600, maximum_y=699)
    prose, footnote = _render_reflowed_fixed_text(before + trailing)
    if footnote:
        raise ValueError(f"unexpected footnote in Figure 4 reflow for sequence {sequence}")
    return "\n".join(
        (
            r"\thispagestyle{hla-body}",
            r"\RaggedRight",
            prose,
            rf"\HLALandscapeFigurePDFPage{{{figure_number}}}"
            rf"{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
            r"\clearpage",
            "",
        )
    )


def _modern_2025_statechart_reflow_page(
    body: str,
    *,
    sequence: int,
    figures: Sequence[tuple[int, str, str]],
) -> str:
    """Promote dense 2025 synchronization charts to figure-only pages.

    Figures 6--9 were captured from source pages that either mixed a chart
    with prose or placed two charts on one portrait page. The semantic
    records already provide the authoritative artwork and captions; this
    adapter preserves nearby prose/anchors while giving every dense chart its
    own true-landscape publication page.
    """

    if sequence == 45:
        records = _fixed_text_blocks_for_reflow(body, minimum_y=60, maximum_y=110)
        prose, footnote = _render_reflowed_fixed_text(records)
        if footnote:
            raise ValueError(f"unexpected footnote in Figure 6 reflow for sequence {sequence}")
        figure_number, input_name, caption = figures[0]
        return "\n".join(
            (
                r"\thispagestyle{hla-body}",
                r"\RaggedRight",
                prose,
                r"\clearpage",
                rf"\HLALandscapeFigurePDFPage{{{figure_number}}}"
                rf"{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
                "",
            )
        )

    if sequence == 46:
        return (
            "\n".join(
                rf"\HLALandscapeFigurePDFPage{{{figure_number}}}"
                rf"{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}"
                for figure_number, input_name, caption in figures
            )
            + "\n"
        )

    if sequence == 47:
        figure_number, input_name, caption = figures[0]
        # The FDD opening follows Figure 9 on the source page. Reflow its
        # short heading, prose, and registry list rather than retaining the
        # source image or absolute y-coordinates (the latter put the list
        # through the modern footer).
        lines = body.splitlines()
        prefix = []
        for line in lines:
            if r"\begin{hlafixedpage}" in line:
                break
            prefix.append(line)
        records = _fixed_text_blocks_for_reflow(body, minimum_y=465, maximum_y=690)

        def clean(value: str) -> str:
            value = re.sub(r"\\textbf\{([^{}]*)\}", r"\1", value)
            value = value.replace(r"\emph{", "").replace("}", "")
            return value.strip()

        cleaned = [(y, clean(value)) for y, value in records if clean(value)]
        heading = next(
            (value for _y, value in cleaned if value.startswith("4.1.4 FOM Document Data")),
            "4.1.4 FOM Document Data (FDD)",
        )
        narrative = " ".join(
            value for y, value in cleaned if 490 <= y < 545 and not value.startswith("4.1.4")
        )
        bullets = [value for y, value in cleaned if 545 <= y < 670 and value != "---"]
        tail = next(
            (value for y, value in cleaned if y >= 670 and value != "---"),
            "All the names within an FDD shall be case sensitive.",
        )
        natural = "\n".join(
            (
                r"\RaggedRight",
                rf"{{\sffamily\bfseries\fontsize{{10.5pt}}{{12pt}}\selectfont "
                rf"\HLAAsciiPunctuationText{{{heading}}}\par}}",
                narrative,
                r"\begin{itemize}[leftmargin=1.5em,itemsep=2pt,topsep=4pt]",
                *(rf"\item {value}" for value in bullets),
                r"\end{itemize}",
                tail,
                r"\clearpage",
            )
        )
        return "\n".join(
            (
                rf"\HLALandscapeFigurePDFPage{{{figure_number}}}"
                rf"{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
                "\n".join(prefix),
                natural,
                "",
            )
        )

    return body


def _wrapped_macro(name: str, values: tuple[str, ...]) -> list[str]:
    """Render a long comma-separated macro without oversized TeX input lines."""
    if not values:
        return [f"\\providecommand{{\\Semantic{name}}}{{}}"]
    chunks: list[str] = []
    current = ""
    for value in values:
        item = value if not current else f",{value}"
        if current and len(current) + len(item) > 96:
            chunks.append(current)
            current = value
        else:
            current += item
    if current:
        chunks.append(current)
    return [
        f"\\providecommand{{\\Semantic{name}}}{{%",
        *(f"{tex_escape(chunk)}%" for chunk in chunks),
        "}",
    ]


def _argument_spans(text: str, start: int, count: int) -> tuple[tuple[int, int], ...]:
    """Return balanced-brace argument spans for a LaTeX command."""
    command = re.match(r"\\[A-Za-z@]+", text[start:])
    if command is None:
        return ()
    cursor = start + command.end()
    spans: list[tuple[int, int]] = []
    for _ in range(count):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            return ()
        span = balanced_span(text, cursor)
        if span is None:
            return ()
        spans.append(span)
        cursor = span[1] + 1
    return tuple(spans)


def _fit_fixed_page_makeboxes(body: str) -> str:
    """Fit numeric fixed-page ``makebox`` lines without changing source data.

    The faithful HLA page adapters contain a small number of authored
    ``makebox[...bp][l]`` lines whose measured width came from the source
    document's original font. The Requirements Lab role font is intentionally
    different, so those lines can protrude past the adapter's content frame.
    Keep the authored width and alignment, but make the generated adapter
    conditionally scale only when the visible line is wider than its box.
    """
    if "\\begin{HLAClauseSemanticPage}" not in body:
        return body

    replacements: list[tuple[int, int, str]] = []
    cursor = 0
    pattern = re.compile(r"\\makebox\[([0-9]+(?:\.[0-9]+)?)bp\]\[l\]\{")
    while match := pattern.search(body, cursor):
        span = balanced_span(body, match.end() - 1)
        if span is None:
            cursor = match.end()
            continue
        start, end = span
        width = match.group(1)
        content = body[start:end]
        replacements.append(
            (match.start(), end + 1, f"\\HLAConditionalMakeBox{{{width}}}{{{content}}}")
        )
        cursor = end + 1

    for start, end, replacement in reversed(replacements):
        body = body[:start] + replacement + body[end:]
    return body


def _replace_command_arguments(
    body: str,
    events: Sequence[tuple[int, tuple[str, ...], int]],
    replacements: tuple[tuple[int, int, str], ...],
) -> str:
    """Replace selected balanced command arguments without disturbing geometry."""
    changes: list[tuple[int, int, str]] = []
    for event_index, argument_index, value in replacements:
        if event_index >= len(events):
            continue
        start, args, _end = events[event_index]
        spans = _argument_spans(body, start, len(args))
        if argument_index < len(spans):
            left, right = spans[argument_index]
            changes.append((left, right, value))
    for left, right, value in sorted(changes, reverse=True):
        body = body[:left] + value + body[right:]
    return body
