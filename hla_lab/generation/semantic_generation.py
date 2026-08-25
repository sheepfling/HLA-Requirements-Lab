"""Generic semantic-to-LaTeX build generation."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from hla_lab.adapters.latex_renderer import (
    render_content_block,
    render_content_block_data,
    render_content_element_data,
    render_cross_reference_data,
    render_definition,
    render_definition_data,
    render_figure_data,
    render_note_data,
    render_reference_data,
    render_requirement,
    render_requirement_data,
    render_table_data,
    render_table_family_data,
    semantic_macro_name,
    tex_escape,
)
from hla_lab.core.io import write_text
from hla_lab.core.hla_profile import source_profile_for_document
from hla_lab.core.parsing import balanced_span
from hla_lab.core.semantic_model import (
    ContentBlock,
    DocumentModel,
    Table,
    _command_events,
    load_document_model,
)
from hla_lab.core.source_adapter import LatexSourceProfile
from hla_lab.core.text import safe_filename
from hla_lab.diagrams.export_graph_diagram import render_tikz as render_graph_tikz
from hla_lab.diagrams.export_plantuml import render as render_plantuml
from hla_lab.diagrams.export_sequence_diagram import render_tikz as render_sequence_tikz
from hla_lab.diagrams.render_state_machine import render as render_state_machine
from hla_lab.generation.contracts import GenerationRequest, GenerationResult
from hla_lab.generation.faithful_renderer import (
    FaithfulLayoutProjection,
    build_faithful_layout_projection,
    render_faithful_body,
)
from hla_lab.generation.hierarchy_compiler import (
    compile_hierarchy,
    render_block_bindings,
    render_hierarchy_index,
    render_hierarchy_outline,
)

_write = write_text
_GENERATED_FILENAME_LENGTH = 96


def _generated_filename(value: object) -> str:
    return safe_filename(value, max_length=_GENERATED_FILENAME_LENGTH)


def _figure_number(caption: str) -> int | None:
    match = re.search(r"\bFigure\s+(\d+)\b", caption)
    return int(match.group(1)) if match else None


def _remove_latex_macro_invocations(
    text: str,
    macro: str,
    argument_count: int,
) -> str:
    """Remove complete invocations of a generated-only LaTeX macro.

    Source-page adapters sometimes retain a text object whose PDF rendering
    is suppressed with a graphics-state trick.  That is still duplicate text
    in the released PDF's searchable layer.  Parse balanced arguments rather
    than using a regular expression so nested TeX groups remain safe.
    """

    marker = f"\\{macro}"
    pieces: list[str] = []
    cursor = 0
    while True:
        start = text.find(marker, cursor)
        if start < 0:
            pieces.append(text[cursor:])
            break
        pieces.append(text[cursor:start])
        argument_start = start + len(marker)
        complete = True
        for _ in range(argument_count):
            span = balanced_span(text, argument_start, skip_whitespace=True)
            if span is None:
                complete = False
                break
            argument_start = span[1] + 1
        if not complete:
            # Preserve malformed source rather than silently truncating it;
            # the normal LaTeX diagnostic should remain visible to the build.
            pieces.append(text[start : start + len(marker)])
            cursor = start + len(marker)
        else:
            cursor = argument_start
    return "".join(pieces)


def _plantuml_ready(machine: Mapping[str, object]) -> bool:
    """Return whether every asserted transition has renderable endpoints."""

    states = {
        str(item.get("id"))
        for item in machine.get("states", ())
        if isinstance(item, Mapping) and item.get("id")
    }
    transitions = tuple(
        item
        for item in machine.get("transitions", ())
        if isinstance(item, Mapping)
    )
    return bool(states) and all(
        transition.get("source_state") in states
        and transition.get("target_state") in states
        for transition in transitions
    )


def _plantuml_review(root: Path) -> tuple[set[str], set[str]] | None:
    """Return reviewed and landscape-approved PlantUML machine IDs.

    Endpoint completeness is a necessary semantic check, but it is not a
    layout approval.  A small, document-owned review manifest lets a release
    keep a semantically rich chart on its audited native surface until its
    generated layout has also passed visual review.  Documents without a
    manifest retain the historical endpoint-only behavior while they migrate.
    """

    path = root / "semantic" / "plantuml-review.json"
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    approved = payload.get("approved_machine_ids")
    if not isinstance(approved, list) or not all(isinstance(item, str) for item in approved):
        raise ValueError(f"{path}: approved_machine_ids must be a list of strings")
    landscape = payload.get("landscape_machine_ids", [])
    if not isinstance(landscape, list) or not all(isinstance(item, str) for item in landscape):
        raise ValueError(f"{path}: landscape_machine_ids must be a list of strings")
    approved_ids = set(approved)
    landscape_ids = set(landscape)
    if not landscape_ids <= approved_ids:
        raise ValueError(f"{path}: landscape_machine_ids must be a subset of approved_machine_ids")
    return approved_ids, landscape_ids


_2010_PLANTUML_CORROBORATION = {
    "figure-05": "normal-activity-permitted",
    "figure-06": "federation-execution-sync-overview",
    "figure-09": "local-synchronization-label",
    "figure-12": "class-attribute-privilege-to-delete-object",
    "figure-13": "interaction-class",
    "figure-14": "object-instance-known",
    "figure-15": "ownership-implications",
    "figure-16": "establishing-ownership",
    "figure-17": "temporal-state",
}


def _cross_edition_plantuml_payload(
    machine_payload: dict[str, object],
    *,
    document_id: str,
    canonical_payloads: Mapping[str, dict[str, object]],
) -> dict[str, object]:
    """Complete 2010 PlantUML projections from an explicit family crosswalk.

    The 2010 source records remain authoritative for the faithful document,
    captions, and provenance.  Several extracted 2010 chart records contain
    states but no endpoint mapping, while the corresponding 2025 Harel record
    provides the complete topology.  This adapter uses that corroborated
    topology only for the generated PlantUML artwork; it never overwrites the
    2010 semantic source record.
    """

    if document_id != "hla-1516.1-2010" or _plantuml_ready(machine_payload):
        return machine_payload
    machine_id = str(machine_payload.get("id", ""))
    figure_match = re.search(r"figure-(\d+)$", machine_id)
    if figure_match is None:
        return machine_payload
    canonical_id = _2010_PLANTUML_CORROBORATION.get(
        f"figure-{int(figure_match.group(1)):02d}"
    )
    canonical = canonical_payloads.get(canonical_id or "")
    if canonical is None:
        return machine_payload

    payload = json.loads(json.dumps(canonical))
    state_id_map = {
        str(state["id"]): f"{machine_id}.{str(state['id']).split('.', 1)[-1]}"
        for state in payload.get("states", ())
        if isinstance(state, Mapping) and state.get("id")
    }
    for state in payload.get("states", ()):
        if not isinstance(state, dict):
            continue
        old_id = str(state.get("id", ""))
        state["id"] = state_id_map.get(old_id, f"{machine_id}.{old_id}")
        if state.get("parent_id") in state_id_map:
            state["parent_id"] = state_id_map[str(state["parent_id"])]
    for transition in payload.get("transitions", ()):
        if not isinstance(transition, dict):
            continue
        transition["id"] = f"{machine_id}.{transition.get('id', 'transition')}"
        for key in ("source_state", "target_state"):
            if transition.get(key) in state_id_map:
                transition[key] = state_id_map[str(transition[key])]
    payload["id"] = machine_id
    payload["title"] = machine_payload.get("title", payload.get("title", ""))
    payload["clause_id"] = machine_payload.get("clause_id", payload.get("clause_id"))
    payload["source"] = machine_payload.get("source", payload.get("source"))
    payload["provenance"] = machine_payload.get("provenance", payload.get("provenance"))
    payload["initial_state_ids"] = [
        state_id_map.get(str(value), f"{machine_id}.{value}")
        for value in payload.get("initial_state_ids", ())
    ]
    payload["notes"] = (
        "PlantUML artwork projection corroborated against the corresponding "
        "2025 Harel state record; the 2010 source record remains the document authority."
    )
    return payload


def _embed_diagram(
    body: str,
    figure_number: int,
    input_name: str,
    layout: Mapping[int, tuple[float, float, float, float]],
    *,
    preserve_native: bool = False,
    caption: str | None = None,
    landscape: bool = False,
) -> str:
    """Insert generated TikZ before the native source caption block."""
    if preserve_native:
        return body
    geometry = layout.get(figure_number)
    macro = ""
    if geometry is not None:
        x, y, width, height = geometry
        embed_macro = "\\HLAEmbeddedGraphicAt" if input_name.endswith(".pdf") else "\\HLAEmbeddedTikZAt"
        embed_body = (
            f"  {embed_macro}{{{x:g}}}{{{y:g}}}{{{width:g}}}{{{height:g}}}{{"
            f"output/semantic/{input_name}}}"
        )
        macro = (
            embed_body + "%\n"
        )
    lines = body.splitlines()
    marker = f"Figure {figure_number}"
    caption_marker = f"\\HLAFigureCaptionAt{{{figure_number}}}"
    native_source_marker = f"figures/native/figure-{figure_number:02d}.tex"

    if landscape and input_name.endswith(".pdf"):
        replacement = (
            rf"\stdsemanticlandscapefigure{{{figure_number}}}"
            rf"{{{tex_escape(caption or marker)}}}"
            rf"{{output/semantic/{input_name}}}"
        )
        for index, line in enumerate(lines):
            # Some faithful source pages put the native chart inside a
            # makebox/resizebox rather than a named figure macro.  Replacing
            # only the PDF token would preserve the old absolute geometry and
            # can put a PlantUML chart over prose.  Promote the whole source
            # line to a standalone true-landscape figure page.
            if input_name in line and (r"\input" in line or r"\includegraphics" in line):
                lines[index] = replacement
                return "\n".join(lines)
            if (input_name in line or native_source_marker in line) and (
                "\\stdsemanticfigure" in line
                or "\\stdnativefigure" in line
            ):
                lines[index] = replacement
                return "\n".join(lines)
            if "\\begin{tikzpicture}" in line:
                end = next(
                    (candidate for candidate in range(index + 1, len(lines))
                     if "\\end{tikzpicture}" in lines[candidate]),
                    None,
                )
                if end is not None and any(
                    input_name in lines[candidate]
                    or native_source_marker in lines[candidate]
                    for candidate in range(index, end + 1)
                ):
                    lines[index : end + 1] = [replacement]
                    return "\n".join(lines)
    caption_index = next(
        (index for index, line in enumerate(lines) if caption_marker in line),
        None,
    )
    macro_line = macro.rstrip("\n")
    if caption_index is not None and geometry is not None:
        image_index = next(
            (
                candidate
                for candidate in range(caption_index - 1, -1, -1)
                if "\\HLAFigureImageAt{" in lines[candidate]
            ),
            None,
        )
        if image_index is not None:
            lines[image_index] = macro_line
        else:
            lines.insert(caption_index, macro_line)
        return "\n".join(lines)
    # Older faithful layouts keep the page geometry in a native TikZ wrapper
    # (``stdnativefigure`` or a hand-tuned resizebox) rather than in the
    # coordinate overlay used by the 2025 profile.  Replace only that input
    # path so the authored spacing and scale remain untouched while the
    # semantic record supplies the visible diagram.
    native_argument = f"{{figures/native/figure-{figure_number:02d}.tex}}"
    generated_argument = f"{{output/semantic/{input_name}}}"
    for index, line in enumerate(lines):
        if native_argument in line:
            stdnative_match = re.search(
                rf"\\stdnativefigure(?:\[([^\]]+)\])?{re.escape(native_argument)}",
                line,
            )
            if stdnative_match and caption:
                width = stdnative_match.group(1) or r"\linewidth"
                figure_caption = tex_escape(f"Figure {figure_number}---{caption}")
                replacement = (
                    rf"\stdsemanticfigure[{width}]{{output/semantic/{input_name}}}"
                    rf"{{{figure_caption}}}"
                )
                lines[index] = line.replace(stdnative_match.group(0), replacement)
                return "\n".join(lines)
            replacement = generated_argument
            # A legacy adapter may place the figure inside a resizebox or
            # rotatebox.  TeX's \input silently prefers the sibling .tex
            # file when handed a .pdf basename, so make PDF assets explicit
            # includegraphics inputs rather than accidentally falling back to
            # the TikZ source (and its embedded legacy caption).
            if input_name.endswith(".pdf"):
                lines[index] = line.replace(
                    f"\\input{native_argument}",
                    f"\\includegraphics{generated_argument}",
                )
                lines[index] = lines[index].replace(
                    f"\\input{generated_argument}",
                    f"\\includegraphics{generated_argument}",
                )
                if lines[index] == line:
                    lines[index] = line.replace(native_argument, generated_argument)
                if caption:
                    figure_caption = tex_escape(f"Figure {figure_number}---{caption}")
                    lines.insert(index + 1, rf"\stdsemanticcaption{{{figure_caption}}}")
            else:
                lines[index] = line.replace(native_argument, replacement)
            return "\n".join(lines)
    native_input = re.compile(rf"(\\input\{{)figures/native/figure-{figure_number:02d}\.tex(\}})")
    for index, line in enumerate(lines):
        if native_input.search(line):
            replacement = rf"\1output/semantic/{input_name}\2"
            lines[index] = native_input.sub(replacement, line)
            if input_name.endswith(".pdf"):
                lines[index] = lines[index].replace(
                    f"\\input{{output/semantic/{input_name}}}",
                    f"\\includegraphics{{output/semantic/{input_name}}}",
                )
                if caption:
                    figure_caption = tex_escape(f"Figure {figure_number}---{caption}")
                    lines.insert(index + 1, rf"\stdsemanticcaption{{{figure_caption}}}")
            return "\n".join(lines)
    image_indices = [index for index, line in enumerate(lines) if "\\HLAFigureImageAt{" in line]
    if geometry is not None and len(image_indices) == 1:
        lines[image_indices[0]] = macro_line
        return "\n".join(lines)
    for index, line in enumerate(lines):
        if marker not in line:
            continue
        caption_start = next(
            (
                candidate
                for candidate in range(index, -1, -1)
                if "\\HLAFixedBlock{" in lines[candidate]
            ),
            None,
        )
        if caption_start is None:
            image_index = next(
                (
                    candidate
                    for candidate, line in enumerate(lines)
                    if "\\HLAFigureImageAt{" in line
                ),
                None,
            )
            if image_index is None:
                return body
            lines[image_index] = macro_line
            return "\n".join(lines)
        image_index = next(
            (
                candidate
                for candidate in range(caption_start - 1, -1, -1)
                if "\\HLAFigureImageAt{" in lines[candidate]
            ),
            None,
        )
        if image_index is not None:
            lines[image_index] = macro_line
        else:
            lines.insert(caption_start, macro_line)
        return "\n".join(lines)
    return body


def _promote_remaining_landscape_asset(
    body: str,
    *,
    figure_number: int,
    input_name: str,
    caption: str,
) -> str:
    """Replace a legacy center/makebox wrapper with one figure page.

    A few 2010 source captures were normalized to ``includegraphics`` before
    the diagram-binding pass runs.  They therefore no longer contain the
    original ``input`` or ``stdnativefigure`` marker, but still retain the
    source center/makebox wrapper.  This final asset-based pass removes that
    wrapper without touching neighboring prose.
    """

    marker = f"output/semantic/{input_name}"
    if rf"\stdsemanticlandscapefigure{{{figure_number}}}" in body:
        return body
    lines = body.splitlines()
    replacement = (
        rf"\stdsemanticlandscapefigure{{{figure_number}}}"
        rf"{{{tex_escape(caption)}}}"
        rf"{{{marker}}}"
    )
    for index, line in enumerate(lines):
        if marker not in line:
            continue
        start = next(
            (
                candidate
                for candidate in range(index, -1, -1)
                if r"\begin{center}" in lines[candidate]
                or r"\begin{tikzpicture}" in lines[candidate]
            ),
            index,
        )
        if r"\begin{center}" in lines[start]:
            end = next(
                (
                    candidate
                    for candidate in range(index, len(lines))
                    if r"\end{center}" in lines[candidate]
                ),
                index,
            )
            # Consume the small source-page glue immediately following the
            # centered figure, but stop before any authored paragraph.
            after = end + 1
            while after < len(lines) and (
                not lines[after].strip()
                or r"\vspace" in lines[after]
                or r"\par" == lines[after].strip()
            ):
                after += 1
            lines[start:after] = [replacement]
            return "\n".join(lines)
        if r"\begin{tikzpicture}" in lines[start]:
            end = next(
                (
                    candidate
                    for candidate in range(index, len(lines))
                    if r"\end{tikzpicture}" in lines[candidate]
                ),
                index,
            )
            lines[start : end + 1] = [replacement]
            return "\n".join(lines)
    return body


def _landscape_figure_page_body(
    *,
    figure_number: int,
    record_id: str,
    caption: str,
    input_name: str,
) -> str:
    """Render a figure-only source page through the modern landscape grammar."""

    macro = "\\HLALandscapeFigurePDFPage" if input_name.endswith(".pdf") else "\\HLALandscapeFigurePage"
    return "\n".join(
        (
            (
                f"{macro}{{{figure_number}}}"
                f"{{{tex_escape(caption)}}}"
                f"{{output/semantic/{input_name}}}"
            ),
            "% The typed diagram record is selected by the source profile:",
            f"% Figure {figure_number} -> {record_id}",
            "",
        )
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
        if text and not text.startswith(r"\draw"):
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
        paragraph_break = (
            previous_y is not None and y - previous_y > 18.0
        ) or text.lstrip().startswith(r"\SemanticRequirement")
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
            raise ValueError(f"unexpected footnote in Figure 4 continuation for sequence {sequence}")
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
                rf"\HLALandscapeFigurePDFPage{{{figure_number}}}{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
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
            rf"\HLALandscapeFigurePDFPage{{{figure_number}}}{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
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
                rf"\HLALandscapeFigurePDFPage{{{figure_number}}}{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
                "",
            )
        )

    if sequence == 46:
        return "\n".join(
            rf"\HLALandscapeFigurePDFPage{{{figure_number}}}{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}"
            for figure_number, input_name, caption in figures
        ) + "\n"

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
            value
            for y, value in cleaned
            if 490 <= y < 545 and not value.startswith("4.1.4")
        )
        bullets = [
            value
            for y, value in cleaned
            if 545 <= y < 670 and value != "---"
        ]
        tail = next(
            (value for y, value in cleaned if y >= 670 and value != "---"),
            "All the names within an FDD shall be case sensitive.",
        )
        natural = "\n".join(
            (
                r"\RaggedRight",
                rf"{{\sffamily\bfseries\fontsize{{10.5pt}}{{12pt}}\selectfont \HLAAsciiPunctuationText{{{heading}}}\par}}",
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
                rf"\HLALandscapeFigurePDFPage{{{figure_number}}}{{{tex_escape(caption)}}}{{output/semantic/{input_name}}}",
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


def _semanticize_visible_surfaces(
    body: str,
    block: ContentBlock,
    model: DocumentModel,
    source: LatexSourceProfile,
) -> str:
    """Replace visible semantic payloads with generated-record macros.

    Coordinates, wrappers, and line-break hints remain in the fidelity body;
    the words that carry semantic identity are emitted by typed records.
    """
    block_path = block.source.path
    references = tuple(item for item in model.references if item.source.path == block_path)
    reference_events = _command_events(body, source.bibliography_entry, 3)
    reference_replacements: list[tuple[int, int, str]] = []
    for index, reference in enumerate(references):
        if index >= len(reference_events):
            break
        reference_replacements.extend(
            (
                (index, 1, f"\\{semantic_macro_name('Reference', reference.id, 'Label')}"),
                (index, 2, f"\\{semantic_macro_name('Reference', reference.id, 'Text')}"),
            )
        )
    if reference_replacements:
        body = _replace_command_arguments(
            body,
            reference_events,
            tuple(reference_replacements),
        )

    figures = tuple(item for item in model.figures if item.source.path == block_path)
    figure_events = _command_events(body, source.figure_caption, 3)
    figure_replacements: list[tuple[int, int, str]] = []
    figure_caption_text_replacements: list[tuple[str, str]] = []
    for index, figure in enumerate(figures):
        if index >= len(figure_events):
            break
        figure_replacements.append(
            (
                index,
                2,
                f"\\{semantic_macro_name('Figure', figure.id, 'Caption')}",
            )
        )
        if figure.caption:
            figure_caption_text_replacements.append(
                (
                    f"Figure {figure.number}---{figure.caption}",
                    f"Figure {figure.number}---"
                    f"\\{semantic_macro_name('Figure', figure.id, 'Caption')}",
                )
            )
    if figure_replacements:
        body = _replace_command_arguments(body, figure_events, tuple(figure_replacements))
    for old, new in figure_caption_text_replacements:
        body = body.replace(old, new)

    tables = tuple(item for item in model.tables if item.source.path == block_path)
    table_events = _command_events(body, source.table_caption, 1)
    table_replacements: list[tuple[int, int, str]] = []
    table_index = 0
    for event_index in range(len(table_events)):
        while table_index < len(tables) and not (
            tables[table_index].caption or tables[table_index].title
        ):
            table_index += 1
        if table_index >= len(tables):
            break
        table = tables[table_index]
        table_replacements.append(
            (
                event_index,
                0,
                f"\\{semantic_macro_name('Table', table.id, 'Caption')}",
            )
        )
        table_index += 1
    if table_replacements:
        body = _replace_command_arguments(body, table_events, tuple(table_replacements))

    # Faithful 1516.1 pages draw captions directly inside fixed text
    # primitives rather than using ``HLATableCaption``. Replace only those
    # title primitives; their coordinates and surrounding table geometry stay
    # in the page adapter while the visible caption comes from the table
    # record/family projection.
    tables_by_number: dict[str, list[Table]] = {}
    for table in tables:
        if table.number is not None:
            tables_by_number.setdefault(table.number, []).append(table)
    for command_name, argument_count in (
        (source.fixed_text_block, 7),
        (getattr(source, "table_text_line", ""), 5),
    ):
        if not command_name:
            continue
        events = _command_events(body, command_name, argument_count)
        replacements: list[tuple[int, int, str]] = []
        for index, (_offset, args, _end) in enumerate(events):
            match = re.search(r"\\textbf\{\s*Table\s+(\d+)\b", args[-1], re.IGNORECASE)
            if match is None:
                continue
            candidates = tables_by_number.get(match.group(1), [])
            if not candidates:
                continue
            table = candidates.pop(0)
            replacements.append(
                (
                    index,
                    argument_count - 1,
                    f"\\{semantic_macro_name('Table', table.id, 'Caption')}",
                )
            )
        if replacements:
            body = _replace_command_arguments(body, events, tuple(replacements))

    requirements = {item.id: item for item in model.requirements}
    summary_events = _command_events(body, source.summary_rule, 2)
    summary_replacements = tuple(
        (
            index,
            1,
            f"\\{semantic_macro_name('Requirement', args[0], 'Statement')}",
        )
        for index, (_offset, args, _end) in enumerate(summary_events)
        if args[0] in requirements
    )
    if summary_replacements:
        body = _replace_command_arguments(body, summary_events, summary_replacements)

    detailed_events = _command_events(body, source.detailed_rule_heading, 2)
    detailed_replacements = tuple(
        (
            index,
            1,
            f"\\{semantic_macro_name('Requirement', args[0], 'Title')}",
        )
        for index, (_offset, args, _end) in enumerate(detailed_events)
        if args[0] in requirements
    )
    if detailed_replacements:
        body = _replace_command_arguments(body, detailed_events, detailed_replacements)

    normative_events = _command_events(body, source.normative_rule_statement, 1)
    normative_replacements: list[tuple[int, int, str]] = []
    for index, (offset, _args, _end) in enumerate(normative_events):
        prior = [item for item in detailed_events if item[0] < offset]
        if prior and prior[-1][1][0] in requirements:
            normative_replacements.append(
                (
                    index,
                    0,
                    f"\\{semantic_macro_name('Requirement', prior[-1][1][0], 'Statement')}",
                )
            )
    if normative_replacements:
        body = _replace_command_arguments(body, normative_events, tuple(normative_replacements))
    # Editorial extraction notes and the misspelled FDD label are source
    # anomalies, not released prose. Apply the simple text repairs here so
    # faithful 2010 pages receive the same production-surface cleanup as the
    # newer fixed-page adapters. The split 2025 fixed blocks receive their
    # structural removal below.
    body = re.sub(
        r"\s*\(Comment note - description is not part of FDD nor should it be and thus cannot be used for rejection\.\)",
        "",
        body,
    )
    body = body.replace("Directed interation", "Directed interaction")
    # Source page 41 splits the federate-lifetime paragraph at a fixed line
    # boundary after the word ``After``.  The semantic macro already contains
    # the preceding sentence; keeping ``After`` on that fixed line makes the
    # line wrap into the next absolute-positioned block and causes an overlap.
    # Keep the correction local to this compiled surface and preserve the
    # source anomaly in the anomaly ledger.
    if model.document_id == "hla-1516.1-2025" and block.sequence == 40:
        body = body.replace(
            r"\SemanticContentBlockProseConnectServiceInfrastructureText After\linebreak%",
            r"\SemanticContentBlockProseConnectServiceInfrastructureText\linebreak%",
        )
        body = body.replace(
            r"successful invocation of the \emph{Join Federation Execution}",
            r"After successful invocation of the \emph{Join Federation Execution}",
        )

        # The preceding normative sentence is semantically longer than the
        # fixed source line it replaced, so it occupies two 12 pt lines.  The
        # source page's next absolute block was only 12 pt below it, which
        # caused the rendered paragraph to collide with the following line.
        # Keep this correction local to the affected surface and leave the
        # footnote furniture at its original position.
        def _shift_following_fixed_block(match: re.Match[str]) -> str:
            y = float(match.group(2))
            if 408.0 <= y <= 672.9:
                return f"{match.group(1)}{{{y + 12.0:.3f}}}{match.group(3)}"
            return match.group(0)

        body = re.sub(
            r"(\\HLAFixedBlock\{[^{}]+\})\{([0-9]+(?:\.[0-9]+)?)\}(\{)",
            _shift_following_fixed_block,
            body,
        )
    # These two source-page captures contain defects that must not remain in
    # the released production surface.  Keep the source capture unchanged
    # for traceability, but apply the correction to the semanticized output.
    if model.document_id == "hla-1516.1-2025" and block.sequence == 47:
        body = body.replace("Directed interation", "Directed interaction")
    if model.document_id == "hla-1516.1-2025" and block.sequence == 48:
        comment_events = _command_events(body, source.fixed_text_block, 7)
        comment_replacements: list[tuple[int, int, str]] = []
        for index, (_offset, args, _end) in enumerate(comment_events):
            visible = args[-1]
            if "Comment note" in visible:
                cleaned = visible.split("(Comment note", 1)[0].rstrip()
                comment_replacements.append((index, 6, cleaned))
            elif "not part of FDD nor should it be and thus cannot be used for rejection" in visible:
                comment_replacements.append((index, 6, ""))
        if comment_replacements:
            body = _replace_command_arguments(
                body,
                comment_events,
                tuple(comment_replacements),
            )
    if model.document_id == "hla-1516.1-2025" and block.sequence == 397:
        body = body.replace(
            "Exceptions: The Annex E files define the encoding",
            "Exceptions: The Annex D files define the encoding",
        )
    if model.document_id == "hla-1516.1-2025" and block.sequence == 414:
        body = body.replace(
            "Federate Protocol API (see Annex E)",
            "Federate Protocol API (see Annex D)",
        )
    return body


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
        line.replace(r"\_", r"\_\penalty0").replace(",", r",\penalty0")
        for line in lines
    ]
    lines = [line for line in lines if line.strip() and line.strip() != r"\textbackslash{}"]
    if not lines:
        return r"\mbox{}"
    return (
        r"\begin{minipage}[t]{\linewidth}\setlength{\parskip}{0pt}"
        r"\setlength{\parindent}{0pt}\RaggedRight\RLMono"
        r"\fontsize{7.0pt}{7.8pt}\selectfont "
        + r"\penalty0 ".join(lines)
        + r"\end{minipage}"
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
    starts = [
        index
        for index, cell in enumerate(cells)
        if cell.column == type_start_column
    ]
    rows: list[tuple[list[str], list[str], list[str]]] = []
    for index, start in enumerate(starts):
        group = cells[start : starts[index + 1] if index + 1 < len(starts) else None]
        if not group:
            continue
        type_column = group[0].column
        encoding_candidates = [cell.column for cell in group if type_column - 3 <= cell.column < type_column]
        encoding_column = max(encoding_candidates, default=None)
        type_values = [cell.text for cell in group if cell.column == type_column]
        if encoding_column is None:
            encoding_values: list[str] = []
            example_values = [cell.text for cell in group if cell.column < type_column]
        else:
            encoding_values = [cell.text for cell in group if cell.column == encoding_column]
            example_values = [cell.text for cell in group if cell.column < encoding_column]
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


def _modern_mom_field_plan(table: Table) -> tuple[list[tuple[str, tuple[str, ...]]], str]:
    """Return output fields and the field that starts a logical MOM record."""

    kind = table.omt_kind or ""
    number = table.number or ""
    if number in {"8", "9"}:
        if number == "8":
            return [
                ("transport / order", ("Order",)),
                ("availability", ("Available",)),
                ("update", ("Update",)),
                ("data type", ("Data type",)),
                ("attribute", ("Attribute",)),
                ("object", ("Object",)),
            ], "attribute"
        return [
            ("transport / order", ("Order",)),
            ("availability", ("Available",)),
            ("data type", ("Data type",)),
            ("parameter", ("Parameter",)),
            ("interaction", ("Interaction",)),
        ], "parameter"
    if number in {"19", "20"}:
        target = "attribute" if number == "19" else "parameter"
        peer = "Attribute" if number == "19" else "Parameter"
        return [("semantics", ("Semantics",)), (target, (peer,)), ("class", ("Class",))], target
    if number == "17":
        return [("semantics", ("Semantics",)), ("object", ("Object",))], "object"
    if number == "18":
        return [("semantics", ("Semantics",)), ("interaction", ("Interaction",))], "interaction"
    if kind == "dimension":
        return [
            ("value when unspecified", ("Value when",)),
            ("normalization function", ("Normalization function",)),
            ("dimension", ("Dimension",)),
            ("data type", ("Data type",)),
            ("name", ("Name",)),
        ], "name"
    if kind == "basic data representation":
        return [
            ("encoding", ("Encoding",)),
            ("endian", ("Endian",)),
            ("interpretation", ("Interpretation",)),
            ("size in bits", ("Size in",)),
            ("name", ("Name",)),
        ], "name"
    if kind == "simple data type":
        return [
            ("semantics", ("Semantics",)),
            ("accuracy", ("Accuracy",)),
            ("resolution", ("Resolution",)),
            ("units", ("Units",)),
            ("representation", ("Representation",)),
            ("name", ("Name",)),
        ], "name"
    if kind == "reference data type":
        return [
            ("semantics", ("Semantics",)),
            ("referenced attribute", ("Referenced Attribute",)),
            ("referenced class", ("Referenced class",)),
            ("representation", ("Representation",)),
            ("name", ("Name",)),
        ], "name"
    if kind == "enumerated data type":
        return [
            ("semantics", ("Semantics",)),
            ("values", ("Values",)),
            ("enumerator", ("Enumerator",)),
            ("representation", ("Representation",)),
            ("name", ("Name",)),
        ], "name"
    if kind == "array data type":
        return [
            ("semantics", ("Semantics",)),
            ("encoding", ("Encoding",)),
            ("cardinality", ("Cardinality",)),
            ("element type", ("Element Type",)),
            ("name", ("Name",)),
        ], "name"
    if kind == "fixed record data type":
        return [
            ("semantics", ("Semantics",)),
            ("encoding", ("Encoding",)),
            ("field semantics", ("Semantics",)),
            ("type", ("Type",)),
            ("field", ("Name",)),
            ("record", ("Record name",)),
        ], "field"
    return [("content", ("Content",))], "content"


def _modern_mom_cells_by_row(table: Table) -> dict[int, list[object]]:
    rows: dict[int, list[object]] = {}
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
                    if candidate.column == cell.column
                    and candidate.id not in consumed
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


def _modern_mom_registry_rows(table: Table) -> tuple[list[str], list[list[str]]]:
    """Build semantic rows from source-cell anchors and continuation ranges."""

    plan, start_key = _modern_mom_field_plan(table)
    cells = tuple(table.cells)
    anchor_positions: dict[str, int] = {}
    header_rows: list[int] = []
    for key, aliases in plan:
        found = _modern_mom_anchor(cells, aliases)
        if found is None:
            continue
        row, column = found
        anchor_positions[key] = column
        header_rows.append(row)
    if not anchor_positions:
        content = [
            _modern_table_text(cell.text)
            for cell in cells
            if _modern_table_text(cell.text)
        ]
        return ["Content"], [[value] for value in content]

    source_order = sorted(anchor_positions, key=lambda key: (anchor_positions[key], key))
    start_anchor = anchor_positions.get(start_key, max(anchor_positions.values()))
    rows = _modern_mom_cells_by_row(table)
    table_number = table.number or ""
    header_end = max(header_rows, default=0)
    row_cutoff: int | None = None
    if table_number in {"17", "18"}:
        # A continuation page can include the header of the next MOM table
        # in the same extracted table object. Treat the next Semantics header
        # as a structural boundary instead of turning the following table
        # into extra rows here.
        semantic_header_rows = sorted(
            {
                cell.row
                for cell in cells
                if cell.row is not None
                and _modern_table_text(cell.text).casefold() == "semantics"
            }
        )
        if semantic_header_rows:
            header_end = semantic_header_rows[0]
            row_cutoff = next(
                (row for row in semantic_header_rows if row > header_end),
                None,
            )
        if row_cutoff is not None:
            rows = {row: row_cells for row, row_cells in rows.items() if row < row_cutoff}
    if table_number in {"17", "18"}:
        candidate_columns = {start_anchor - 1, start_anchor, start_anchor + 1}
    elif table_number in {"8", "9", "19", "20"}:
        candidate_columns = {start_anchor, start_anchor + 1}
    else:
        candidate_columns = {start_anchor + offset for offset in range(4)}
    start_rows = sorted(
        {
            row
            for row, row_cells in rows.items()
            if row > header_end
            and any(
                cell.column in candidate_columns
                and _modern_table_text(cell.text).casefold() not in {"", "(continued)"}
                and "(cont.)" not in _modern_table_text(cell.text).casefold()
                for cell in row_cells
            )
        }
    )
    if not start_rows:
        start_rows = [header_end + 1]

    field_labels = [key for key, _aliases in plan]
    output_rows: list[list[str]] = []
    for index, start_row in enumerate(start_rows):
        end_row = start_rows[index + 1] if index + 1 < len(start_rows) else None
        group_cells = [
            cell
            for row, row_cells in rows.items()
            if row >= start_row and (end_row is None or row < end_row)
            for cell in row_cells
        ]
        values: dict[str, list[str]] = {key: [] for key, _aliases in plan}
        for cell in sorted(group_cells, key=lambda item: (item.row, item.column, item.id)):
            text = _modern_table_text(cell.text)
            if not text or text.casefold() == "(continued)":
                continue
            if table_number in {"17", "18"}:
                target_key = "object" if table_number == "17" else "interaction"
                # Long semantic sentences can wrap onto a line beginning
                # with an HLA identifier. Column ownership is the reliable
                # discriminator for these two-column tables.
                # The identifier itself is commonly one extracted column to
                # the left of the header anchor; wrapped prose remains well
                # to the left of that boundary.
                key = target_key if cell.column >= start_anchor - 1 else "semantics"
            elif len(source_order) == 1:
                key = source_order[0]
            elif (table.number or "") == "18":
                key = min(
                    source_order,
                    key=lambda candidate: (
                        abs(cell.column - anchor_positions[candidate]),
                        -anchor_positions[candidate],
                    ),
                )
            else:
                key = min(
                    source_order,
                    key=lambda candidate: abs(cell.column - anchor_positions[candidate]),
                )
                for candidate_index, candidate in enumerate(source_order[:-1]):
                    next_key = source_order[candidate_index + 1]
                    if anchor_positions[candidate] <= cell.column < anchor_positions[next_key]:
                        key = candidate
                        break
            text = re.sub(r"\s*\(cont\.\)\s*$", "", text, flags=re.IGNORECASE)
            if text and text not in values[key]:
                values[key].append(text)
        if any(values.values()):
            output_rows.append([" ".join(values[key]) for key, _aliases in plan])

    if start_key in field_labels:
        start_index = field_labels.index(start_key)
        order = [start_index] + [index for index in range(len(field_labels)) if index != start_index]
        field_labels = [field_labels[index] for index in order]
        output_rows = [[row[index] for index in order] for row in output_rows]
    if (table.number or "") == "18" and len(field_labels) >= 2:
        # The source PDF sometimes places the first sentence of the
        # definition in the same physical cell as the interaction identifier.
        # Keep the identifier column technical and move that sentence into the
        # prose column so long definitions do not force a second page.
        for row in output_rows:
            interaction = row[0]
            for marker in (". It shall ", ". Cause the RTI ", ". The interaction "):
                split_at = interaction.find(marker)
                if split_at <= 0:
                    continue
                tail = interaction[split_at + 2 :].strip()
                row[0] = interaction[: split_at + 1].strip()
                row[1] = f"{tail} {row[1]}".strip().replace(
                    "the The interaction", "the interaction"
                )
                break
    return field_labels, output_rows


def _modern_mom_hierarchy_rows(table: Table) -> list[tuple[str, str]]:
    """Turn the two MOM class-structure tables into a compact tree registry."""

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
        root_names = {"HLAinteractionRoot (N)"}
        manager_names = {"HLAmanager (N)"}
        federate_names = {"HLAfederate (N)"}
        branch_names = {"HLAadjust (N)", "HLArequest (N)", "HLAreport (N)", "HLAservice (N)"}
        output: list[tuple[str, str]] = []
        for name in names:
            if name in root_names:
                depth = "0"
            elif name in manager_names:
                depth = "1"
            elif name in federate_names:
                depth = "2"
            elif name in branch_names:
                depth = "3"
            else:
                depth = "4"
            output.append((depth, name))
        return output

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


def _modern_mom_definition_rows(table: Table) -> tuple[list[str], list[list[str]]]:
    """Recover definition records as identifier, parent, and prose fields.

    Tables 17 and 18 are long two-column source tables. Their wrapped lines
    are captured in several physical columns, which made the old anchor
    heuristic put semantic sentences into the identifier column. Start a
    record from the exact HLA identifier cells and append all following
    source fragments until the next identifier.
    """

    number = table.number or ""
    target_label = "Object class" if number == "17" else "Interaction class"
    identifier_pattern = re.compile(
        r"(?:HLA|HL)[A-Za-z0-9_.]+(?: \(cont\.\))?"
    )

    def inferred_parent(target: str) -> str:
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
        if target in {
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
        }:
            return "HLAmanager.HLAfederate.HLAservice"
        return ""

    rows: list[list[str]] = []
    for _row_number, cells in sorted(_modern_mom_cells_by_row(table).items()):
        values = [
            (_modern_table_text(cell.text), int(cell.column))
            for cell in cells
            if _modern_table_text(cell.text)
        ]
        if not values:
            continue
        identifiers = [
            (value, column)
            for value, column in values
            if identifier_pattern.fullmatch(value)
        ]
        if number == "17":
            targets = [item for item in identifiers if item[1] >= 8][-1:]
            parents: list[str] = []
        else:
            # In Table 18 the lower-column identifier is the child and the
            # higher-column identifier is its parent in the source hierarchy.
            hierarchy_identifiers = [item for item in identifiers if item[1] >= 5]
            targets = hierarchy_identifiers[:1]
            parents = [value for value, _column in hierarchy_identifiers[1:]]
        identifier_columns = {
            column
            for _value, column in identifiers
            if column >= (8 if number == "17" else 5)
        }
        prose = [
            value
            for value, column in values
            if not (
                identifier_pattern.fullmatch(value)
                and column in identifier_columns
            )
            and value.casefold() not in {"object", "interaction", "semantics", "(continued)"}
        ]
        if targets:
            target = re.sub(r" \(cont\.\)$", "", targets[0][0])
            target = target.replace("HLmanager.", "HLAmanager.")
            if rows and rows[-1][0] == target:
                rows[-1][2] = f"{rows[-1][2]} {' '.join(prose)}".strip()
                continue
            if number == "17":
                rows.append([target, " ".join(prose)])
            else:
                parent = " ".join(parents) or inferred_parent(target)
                rows.append([target, parent, " ".join(prose)])
        elif rows:
            rows[-1][-1] = f"{rows[-1][-1]} {' '.join(prose)}".strip()

    if number == "17":
        return [target_label, "Semantics"], rows
    return [target_label, "Parent class", "Semantics"], rows


def _modern_mom_hierarchy_fixed_rows(body: str) -> list[tuple[str, str]]:
    """Recover continuation-page hierarchy rows from their semantic x-levels."""

    raw_rows: list[tuple[float, str]] = []
    for match in re.finditer(r"\\HLAFixedBlock", body):
        spans = _argument_spans(body, match.start(), 7)
        if not spans:
            continue
        try:
            x = float(body[spans[0][0] : spans[0][1]])
        except ValueError:
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
        if not text or text.startswith(("IEEE Std", "IEEE Standard", "Federate Interface Specification")):
            continue
        if text.startswith("Table 7---") or text.casefold() == "(continued)":
            continue
        raw_rows.append((x, text))

    rows: list[tuple[float, str]] = []
    for x, text in raw_rows:
        if text.casefold() == "(cont.)":
            continue
        if re.fullmatch(r"\([NPS]\)(?: \(cont\.\))?", text):
            if rows:
                rows[-1] = (rows[-1][0], f"{rows[-1][1]} {text.split()[0]}")
            continue
        rows.append((x, text))
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
    return rf"""\RLInlineTableCaption{{7}}{{MOM interaction class structure table\quad\textit{{(continued)}}}}
{body}
"""


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
        header = " & ".join(
            f"\\RLTableHeaderCell{{{tex_escape(value)}}}" for value in headers
        ) + r" \\"
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
        return f"""\\RLInlineTableCaption{{{tex_escape(number)}}}{{{tex_escape(title)}{continuation}}}
\\begingroup
\\setlength{{\\tabcolsep}}{{3.2pt}}
\\renewcommand{{\\arraystretch}}{{0.96}}
{table_body}
\\endgroup
"""
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
            "data type", "representation", "encoding", "type", "name", "attribute",
            "parameter", "object", "interaction", "class", "record", "field",
            "enumerator", "values",
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
    header = " & ".join(
        f"\\RLTableHeaderCell{{{tex_escape(value)}}}" for value in headers
    ) + r" \\"
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
        if not text or text.startswith(("IEEE Std", "IEEE Standard", "Federate Interface Specification")):
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
                    r"\begin{minipage}{\linewidth}\RaggedRight\rmfamily\fontsize{7pt}{8.4pt}\selectfont "
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
                r"\begin{minipage}{\linewidth}\RaggedRight\ttfamily\fontsize{4.7pt}{5.25pt}\selectfont",
                "\\par ".join(tex_escape(text) for text in fragments),
                r"\end{minipage}",
            ]
    return """\\HLASourcePage{{{source}}}{{{sequence}}}
\\begin{{RLLandscapePage}}
\\thispagestyle{{rl}}
{body}
\\end{{RLLandscapePage}}
""".format(source=sequence + 1, sequence=sequence, body="\n".join(blocks))


def _modern_protocol_rows(table: Table) -> tuple[list[str], list[list[str]]]:
    """Project protocol tables into stable registry rows."""

    def join_wrapped(values: Sequence[str]) -> str:
        text = " ".join(values)
        return re.sub(r"(?<=[A-Za-z])-\s+(?=[a-z])", "", text)

    by_row: dict[int, dict[int, list[str]]] = {}
    for cell in sorted(
        (cell for cell in table.cells if cell.row is not None and cell.column is not None),
        key=lambda cell: (cell.row, cell.column, cell.id),
    ):
        by_row.setdefault(cell.row, {}).setdefault(cell.column, []).append(
            _modern_table_text(cell.text)
        )

    def row_values(row: int) -> list[str]:
        return [
            value
            for column in sorted(by_row.get(row, {}))
            for value in by_row[row][column]
            if value
        ]

    number = table.number or ""
    if number in {"31", "32"}:
        names_by_column = by_row.get(0, {})
        description_by_column = by_row.get(1, {})
        default_by_column = by_row.get(2, {})
        rows: list[list[str]] = []
        for column in sorted(names_by_column):
            names = [value for value in names_by_column[column] if value.casefold() != "name"]
            if not names:
                continue
            descriptions = [
                value for value in description_by_column.get(column, [])
                if value.casefold() != "description"
            ]
            defaults = [
                value
                for value in default_by_column.get(column, [])
                if not value.casefold().startswith("default") and value.casefold() != "(s)"
            ]
            rows.append([names[-1], join_wrapped(descriptions), join_wrapped(defaults)])
        return ["Name", "Description", "Default (s)"], rows

    if number == "33":
        byte_ranges = [value for value in row_values(0) if value.casefold() != "byte"]
        names = [value for value in row_values(1) if value.casefold() != "name"]
        interpretations = [
            value for value in row_values(2) if value.casefold() != "interpretation"
        ]
        rows = [
            [byte_range, name, interpretation]
            for byte_range, name, interpretation in zip(byte_ranges, names, interpretations)
        ]
        return ["Bytes", "Field", "Interpretation"], rows

    if number == "34":
        rows: list[list[str]] = []
        current_group = ""
        for column in sorted(set(by_row.get(0, {})) | set(by_row.get(1, {}))):
            values = [value for value in by_row.get(0, {}).get(column, []) if value.casefold() != "value"]
            types = [value for value in by_row.get(1, {}).get(column, []) if value.casefold() != "type"]
            messages: list[str] = []
            for value in types:
                if value.casefold() in {"session management", "reconnection", "hla calls and callbacks"}:
                    current_group = value
                else:
                    messages.append(value)
            for value, message in zip(values, messages):
                direction = _protocol_message_direction(message)
                rows.append([value, message, current_group, direction])
        return ["Value", "Message", "Group", "Direction"], rows

    byte_ranges = [value for value in row_values(0) if value.casefold() != "byte"]
    names = [value for value in row_values(1) if value.casefold() != "name"]
    descriptions = [
        value for value in row_values(2) if value.casefold() != "description"
    ]
    if len(descriptions) > len(names) and names:
        descriptions = descriptions[: len(names) - 1] + [
            join_wrapped(descriptions[len(names) - 1 :])
        ]
    descriptions.extend([""] * max(0, len(names) - len(descriptions)))
    return ["Bytes", "Field", "Direction", "Description"], [
        [byte_range, name, _protocol_message_direction(table.title or name), description]
        for byte_range, name, description in zip(byte_ranges, names, descriptions)
    ]


def _protocol_message_direction(value: str) -> str:
    name = _modern_table_text(value)
    if "---" in name:
        name = name.split("---", 1)[1].strip()
    name = name.split()[0] if name else ""
    if name.startswith(("CTRL_NEW_SESSION_STATUS", "CTRL_HEARTBEAT_RESPONSE", "CTRL_SESSION_TERMINATED", "CTRL_RESUME_STATUS", "HLA_CALL_RESPONSE", "HLA_CALLBACK_REQUEST")):
        return "RTI -> FEDERATE"
    if name.startswith(("CTRL_NEW_SESSION", "CTRL_HEARTBEAT", "CTRL_TERMINATE_SESSION", "CTRL_RESUME_REQUEST", "HLA_CALL_REQUEST", "HLA_CALLBACK_RESPONSE")):
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
            _modern_mom_cell(value, technical=index < 2 or headers[index] in {"Name", "Field", "Message", "Bytes"})
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
            if value.startswith(("12.13.4.5.", "This message shall be sent", "Note that the Session ID"))
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


_FIGURE_TABLE_ROWS_2025: tuple[tuple[int, str], ...] = (
    (1, "Basic states of the federation execution"),
    (2, "Overall view of federate-to-RTI relationship"),
    (3, "Lifetime of a federate"),
    (4, "Joined federate state"),
    (5, "Normal Activity Permitted state"),
    (6, "Federation execution and sync points"),
    (7, "Global synch label (L)"),
    (8, "Awaiting synchronization (s, L)"),
    (9, "Local synch label (s, L)"),
    (10, "Object class (i)"),
    (11, "Class attribute (i, j)"),
    (12, "Class attribute (i, HLAprivilegeToDeleteObject)"),
    (13, "Interaction class (m)"),
    (14, "Object instance (i, k) known"),
    (15, "Implications of ownership of instance attribute (i, k, j)"),
    (16, "Establishing ownership of instance attribute (i, k, j)"),
    (17, "Temporal state"),
    (18, "Region of two dimensions"),
    (19, "MOM object class structure"),
    (20, "MOM interaction class structure"),
    (21, "HLA Federate Protocol layers"),
    (22, "Federate and RTI message sequence numbers"),
    (23, "Response messages"),
    (24, "Federate Connection and Reconnection States"),
    (25, "RTI Connection and Reconnection States"),
    (26, "Successful reconnection"),
    (27, "Federate Session Startup State Diagram"),
    (28, "Federate Resume State Diagram"),
    (29, "Federate Exception State Diagram"),
    (30, "RTI Port Handling State Diagram"),
    (31, "RTI Startup State Diagram"),
    (32, "RTI Resume State Diagram"),
    (33, "RTI Exception Handling State Diagram"),
)


def _modern_figure_table_page(sequence: int) -> str:
    """Render Annex H from figure labels rather than source-page integers."""

    start = 0 if sequence == 435 else 17
    rows = _FIGURE_TABLE_ROWS_2025[start : start + (17 if sequence == 435 else 16)]
    # RLInlineTableCaption supplies the table number; keep the title itself
    # free of a second ``Table H.1`` prefix.
    title = "Figure numbers" if sequence == 435 else "Figure numbers (continued)"
    rendered_rows = "\n".join(
        " & ".join(
            (
                f"\\hyperlink{{figure:{number}}}{{Figure {number}, {tex_escape(caption)}}}",
                f"page~\\pageref{{figure:{number}}}",
            )
        )
        + r" \\"
        + (r"\RLProductionRowRule" if index + 1 < len(rows) else "")
        for index, (number, caption) in enumerate(rows)
    )
    return f"""\\HLASourcePage{{{sequence + 1}}}{{{sequence}}}
\\begin{{RLLandscapePage}}
\\thispagestyle{{rl}}
\\noindent
{{\\RLSans\\bfseries\\fontsize{{13.2pt}}{{15.6pt}}\\selectfont Annex H}}\\par
\\vspace{{2pt}}
{{\\RLSans\\fontsize{{8.6pt}}{{10pt}}\\selectfont (informative)}}\\par
\\vspace{{11pt}}
\\RLInlineTableCaption{{H.1}}{{{tex_escape(title)}}}
\\begingroup
\\setlength{{\\tabcolsep}}{{5pt}}
\\renewcommand{{\\arraystretch}}{{1.12}}
\\begin{{tabularx}}{{\\linewidth}}{{@{{}}YL{{0.22\\linewidth}}@{{}}}}
\\RLProductionTopRule
\\RLProductionHeaderBand
\\RLTableHeaderCell{{Figure number and name}} & \\RLTableHeaderCell{{Requirements Lab page}} \\\\
\\RLProductionHeaderRule
{rendered_rows}
\\RLProductionBottomRule
\\end{{tabularx}}
\\endgroup
\\end{{RLLandscapePage}}
"""


def _inject_figure_caption_anchors(body: str) -> str:
    """Give legacy fixed captions the same page label as generated figures."""

    anchored = set(re.findall(r"\\HLAFigureAnchor\{(\d+)\}", body))

    def replace(match: re.Match[str]) -> str:
        number = match.group(1)
        if number in anchored:
            return match.group(0)
        anchored.add(number)
        return f"\\HLAFigureAnchor{{{number}}}{match.group(0)}"

    # Legacy fixed-page captions use either the three-hyphen source form or
    # the Unicode em dash form.  Anchor only caption-like occurrences so
    # prose references such as “depicted in Figure 19” remain untouched.
    return re.sub(r"Figure\s+(\d+)(?:---|—)", replace, body)


def _modernize_2025_source_surface(
    body: str,
    *,
    sequence: int,
    tables: Sequence[Table] = (),
) -> str:
    """Remove inherited publisher furniture from the 2025 Lab surface.

    The 2025 interface corpus is used as source material for a new Lab
    compilation.  A few source pages are still authored as rotated fixed
    surfaces, so their old masthead and folio would otherwise survive even
    after the surrounding document has been modernized.  Keep the semantic
    table/figure payload for the staged migration, but remove that publisher
    furniture and correct source markup that would otherwise be visible as
    LaTeX commands in the released PDF.
    """

    body = _remove_latex_macro_invocations(
        body,
        "HLAInvisibleFixedCenteredBlock",
        7,
    )
    body = _inject_figure_caption_anchors(body)

    if sequence in {435, 436}:
        return _modern_figure_table_page(sequence)

    if sequence == 360:
        return _modern_java_factory_page(body)

    # Clause 12 contains a long run of language-mapping pages.  Keeping these
    # source pages as absolute overlays makes API classes, packages, and code
    # look like bold prose and recreates the very justification gaps the Lab
    # style is intended to remove.  Reflow the complete mapping run with the
    # same grammar as the accepted factory page.
    if 354 <= sequence <= 394:
        return _modern_java_factory_page(body)

    # Annex B and C are canonical file inventories, not narrative lists.
    # Emit them as selectable monospaced listings with stable source order.
    if 416 <= sequence <= 421:
        return _modern_api_manifest_page(body)

    # Protocol narrative has its own compact rule grammar.  Tables and state
    # diagrams retain their dedicated landscape/PlantUML adapters below.
    if sequence in {395, 396, 397, 398, 399, 400, 401, 403, 408}:
        return _modern_protocol_prose_page(body)

    if 305 <= sequence <= 352:
        page_tables = tuple(
            table
            for table in tables
            if table.id.endswith(f"-p{sequence}")
        )
        return _modern_mom_page(
            page_tables,
            sequence=sequence,
            source_body=body,
        )

    if sequence in {402, 404, 405, 406, 407}:
        page_tables = tuple(
            table
            for table in tables
            if table.id.endswith(f"-p{sequence}")
        )
        if page_tables:
            return _modern_protocol_page(
                page_tables,
                sequence=sequence,
                source_body=body,
            )

    if 295 <= sequence <= 304:
        table_id = f"table-5-p{sequence}"
        table = next(
            (item for item in tables if item.id == table_id),
            None,
        )
        if table is not None:
            return _modern_table5_page(table, sequence=sequence)

    if sequence == 179:
        # Source page 180 contains a dense four-column time-advancement
        # summary.  Its source coordinates are internally consistent for the
        # original page, but the fixed-position adapter makes the cells
        # collide at Lab typography.  Preserve the source values and caption,
        # while giving the table a real landscape, content-driven layout.
        return r"""\HLASourcePage{180}{179}
\begin{RLLandscapePage}
\thispagestyle{rl}
\noindent
{\RLSans\bfseries\fontsize{10.2pt}{12pt}\selectfont 8.1.2 Time advancement summary}\par
\vspace{5pt}
\RaggedRight
A joined federate is permitted to advance its logical time only by requesting a time advancement from the RTI. Its logical time shall not actually be advanced until the RTI responds with a \emph{Time Advance Grant}\textdagger{} or \emph{Flush Queue Grant}\textdagger{} service invocation at that joined federate. The interval between these service invocations is the Time Advancing state shown in Figure 17.
\par\vspace{4pt}
Each service takes a specific logical time $t_R$ as an argument and requests different coordination from the RTI. The summary below preserves the source distinctions between the Time Advancing and Time Granted states.
\par\vspace{5pt}
\RLInlineTableCaption{1}{Service descriptions}
\setlength{\tabcolsep}{4pt}
\renewcommand{\arraystretch}{1.14}
\begin{longtable}{@{}p{0.20\linewidth}p{0.25\linewidth}p{0.29\linewidth}p{0.22\linewidth}@{}}
\RLProductionTopRule
\RLProductionHeaderBand
\RLTableHeaderCell{Time advancement service} &
\RLTableHeaderCell{Cannot send while advancing} &
\RLTableHeaderCell{Messages delivered before grant} &
\RLTableHeaderCell{Constraint after grant}\\
\RLProductionHeaderRule
\texttt{Time Advance Request} & $ts < t_R + \mathrm{lookahead}$ & All queued RO messages; all TSO messages with $ts \leq t_R$ & $ts < LT + \mathrm{lookahead}$\\
\RLProductionRowRule
\texttt{Time Advance Request} (zero lookahead) & $ts \leq t_R$ & All queued RO messages; all TSO messages with $ts \leq t_R$ & $ts \leq LT$\\
\RLProductionRowRule
\texttt{Time Advance Request Available} & $ts < t_R + \mathrm{lookahead}$ & All queued RO messages; all TSO messages with $ts < t_R$ & $ts < LT + \mathrm{lookahead}$\\
\RLProductionRowRule
\texttt{Next Message Request} & $ts < t_R + \mathrm{lookahead}$ & The TSO message with the smallest timestamp that will ever be received for which $ts \leq t_R$; all other TSO messages with the same $ts$ & $ts < LT + \mathrm{lookahead}$\\
\RLProductionRowRule
\texttt{Next Message Request} (zero lookahead) & $ts < t_R$ & The TSO message with the smallest timestamp that will ever be received for which $ts \leq t_R$; all other TSO messages with the same $ts$ & $ts < LT$\\
\RLProductionRowRule
\texttt{Next Message Request Available} & $ts < t_R + \mathrm{lookahead}$ & The TSO message with the smallest timestamp that will ever be received for which $ts \leq t_R$; all other queued TSO messages with the same $ts$ & $ts < LT + \mathrm{lookahead}$\\
\RLProductionRowRule
\texttt{Flush Queue Request} & $ts < t_R + \mathrm{lookahead}$ & All queued TSO messages & $ts < OLT + OL$\\
\RLProductionBottomRule
\end{longtable}
\vspace{3pt}
{\fontsize{7.8pt}{9.2pt}\selectfont\textdagger{} The Time Advance Grant service is used for all forms of time advance request except Flush Queue Request, which is granted by Flush Queue Grant.}\par
\end{RLLandscapePage}
"""

    if sequence >= 0:
        for pattern in (
            r"\s*\\HLARotatedLine\{30\.258\}\{435\.300\}.*?\n \}\n",
            r"\s*\\HLARotatedLine\{40\.278\}\{543\.000\}.*?\n \}\n",
            r"\s*\\HLARotatedLine\{50\.297\}\{451\.920\}.*?\n \}\n",
            r"\s*\\HLARotatedLine\{546\.226\}\{406\.560\}.*?\n \}\n",
        ):
            body = re.sub(pattern, "\n", body, flags=re.DOTALL)

    body = body.replace(
        r"\textbf{\{\textbackslash{}ldots\{\}\}}",
        r"\textbf{\{\dots\}}",
    )
    body = body.replace(r"\textbackslash{}ldots\{\}", r"\dots")
    body = body.replace(r"\textbackslash{}", r"\char92{}")
    body = body.replace(r"\_", r"\char95{}")
    body = body.replace(
        r"IEEE Std 1516.1\texttrademark-2025",
        "this document",
    )
    body = body.replace("IEEE Std 1516.1-2025", "this document")
    body = body.replace(
        "This standard, this document, provides",
        "This source compilation provides",
    )
    body = body.replace(
        "The RTI shall provide the this document Java API classes",
        "The RTI shall provide the HLA 1516.1 Java API classes",
    )
    body = body.replace(
        "IEEE Std 1516-2025, this standard, and IEEE Std\\linebreak 1516.2-2025",
        "the supplied HLA source set and this Requirements Lab compilation",
    )
    body = body.replace(
        "as prescribed in this document. See also",
        "as prescribed in this document. See also",
    )
    if sequence in {89, 150, 180, 187}:
        # These are the first portrait source pages after true landscape
        # insertions (Figures 11/12, 16/17, and the rebuilt Table 1).  Use the
        # fixed Lab furniture directly so no landscape page-style state can
        # affect their footer position.
        body = body.replace(
            r"\thispagestyle{hla-body}",
            r"\thispagestyle{empty}\RLFixedFurniture",
            1,
        )
    return body


def _modernize_2025_generated_tex(text: str) -> str:
    """Keep source tokens readable in the released PDF text layer."""

    return (
        text.replace(r"\textbackslash{}", r"\char92{}")
        .replace(r"\_", r"\char95{}")
        # Source captions sometimes contain an already escaped underscore
        # (``CTRL\_NEW``).  The first escape is source markup, not part of the
        # published protocol identifier.
        .replace(r"\char92{}\char95{}", r"\char95{}")
    )


def _semantic_content_body(block: ContentBlock, model: DocumentModel) -> str | None:
    """Render a layout-free prose block from its typed content elements."""
    if block.layout_body is not None:
        return None
    elements = {item.id: item for item in model.content_elements if item.block_id == block.id}
    values = [
        f"\\{semantic_macro_name('ContentElement', element.id, 'Text')}"
        for element_id in block.element_ids
        if (element := elements.get(element_id)) is not None
        and element.kind in {"paragraph", "note", "footnote", "list-item"}
    ]
    return "\n\n".join(values) if values else None


def _service_flow_text(value: str) -> str:
    """Remove source-page line wrapping before placing text in normal flow."""

    # The fixed-page adapter uses percent signs as TeX line-continuation
    # markers. They are not authored prose and would comment out a closing
    # brace when the same argument is moved into a flow macro.
    normalized = re.sub(r"\\linebreak\s*%?", " ", value).replace("%", "").strip()
    # Some extracted source lines end in ``\\ %``. Once the percent marker is
    # removed, the remaining control-space slash must not escape the flow
    # macro's closing brace.
    return re.sub(r"\\\s*$", "", normalized).strip()


def _modern_service_flow_page(body: str) -> str:
    """Convert one fixed source service page into the contract grammar.

    The source adapter deliberately keeps the authored service text and
    numbering, but its coordinates are a presentation concern. This
    command-aware adapter preserves the semantic macros while replacing the
    page's absolute blocks with a natural-flow service surface. It is only
    applied to pages that actually contain service headings; figures and other
    source-page compositions continue through their existing adapters.
    """

    service_events = [
        (offset, end, "service", args)
        for offset, args, end in _command_events(body, "HLAServiceHeadingAt", 2)
    ]
    section_events = [
        (offset, end, "section", args)
        for offset, args, end in _command_events(body, "HLAServiceComponentHeadingAt", 2)
    ]
    block_events = [
        (offset, end, "block", args)
        for offset, args, end in _command_events(body, "HLAFixedBlock", 7)
    ]
    events = sorted((*service_events, *section_events, *block_events), key=lambda item: item[0])
    if not service_events or not block_events:
        return body

    first_offset = events[0][0]
    last_end = max(item[1] for item in events)
    lead = body[:first_offset]
    tail = body[last_end:]
    if r"\begin{hlafixedpage}" not in lead or r"\end{hlafixedpage}" not in tail:
        return body
    lead = lead.replace(r"\begin{hlafixedpage}", r"\begin{HLAServiceFlowPage}", 1)
    tail = tail.replace(r"\end{hlafixedpage}", r"\end{HLAServiceFlowPage}", 1)

    rendered: list[str] = [lead.rstrip()]
    pending_label: str | None = None
    for _offset, _end, kind, args in events:
        if kind == "service":
            heading = _service_flow_text(args[1])
            direction = (
                r"RTI $\rightarrow$ FEDERATE"
                if "textdagger" in heading or "dagger" in heading
                else r"FEDERATE $\rightarrow$ RTI"
            )
            rendered.append(
                "\\HLAServiceFlowHeading{"
                f"{heading}"
                f"}}{{{direction}}}"
            )
            pending_label = None
            continue
        if kind == "section":
            if pending_label is not None:
                rendered.append(f"\\HLAServiceFlowParagraph{{{pending_label}}}")
                pending_label = None
            rendered.append(f"\\HLAServiceFlowSection{{{_service_flow_text(args[1])}}}")
            continue

        x_position = float(args[0])
        content = _service_flow_text(args[6])
        # Source list rows use an aligned label block at x≈100pt followed by
        # the value block at x≈122pt. Pair those rows without changing the
        # authored labels (including None and the return-code markers).
        if x_position < 115:
            if pending_label is not None:
                rendered.append(f"\\HLAServiceFlowParagraph{{{pending_label}}}")
            pending_label = content
            continue
        if pending_label is not None:
            rendered.append(f"\\HLAServiceFlowItem{{{pending_label}}}{{{content}}}")
            pending_label = None
        else:
            rendered.append(f"\\HLAServiceFlowParagraph{{{content}}}")
    if pending_label is not None:
        rendered.append(f"\\HLAServiceFlowParagraph{{{pending_label}}}")
    # A small number of source pages carry a fixed-position footnote rule
    # after the service blocks. The line is meaningful only inside the old
    # overlay picture; leaving it in a flow page would expose a bare TikZ
    # command in the document body.
    tail = re.sub(r"(?m)^\s*\\draw\[[^\n]*\][^\n;]*;\s*$", "", tail)
    rendered.append(tail.lstrip())
    return "\n".join(rendered)


def _factory_fixed_lines(body: str) -> list[tuple[float, str]]:
    """Collect one reading-order line from the fixed API source blocks."""

    records: list[tuple[float, float, str]] = []
    for _offset, args, _end in _command_events(body, "HLAFixedBlock", 7):
        try:
            x = float(args[0])
            y = float(args[1])
        except (IndexError, ValueError):
            continue
        text = re.sub(r"\\linebreak\s*%?", " ", args[6])
        text = text.replace("%", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if text and not text.startswith(r"\\draw"):
            records.append((y, x, text))
    records.sort(key=lambda item: (item[0], item[1]))

    # Inline bold tokens are separate fixed blocks, commonly offset by less
    # than one point from the surrounding line. Recombine them by baseline so
    # the reflowed paragraph reads naturally while retaining the token macro.
    lines: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, text in records:
        if lines and abs(y - lines[-1][0]) <= 1.0:
            lines[-1][1].append((x, text))
        else:
            lines.append((y, [(x, text)]))
    result = [
        (y, " ".join(text for _x, text in sorted(parts, key=lambda item: item[0])))
        for y, parts in lines
    ]
    normalized: list[tuple[float, str]] = []
    for y, text in result:
        if (
            normalized
            and normalized[-1][1].endswith("-")
            and re.match(r"^[A-Za-z]", text)
            and y - normalized[-1][0] <= 18
        ):
            previous_y, previous_text = normalized[-1]
            normalized[-1] = (previous_y, previous_text[:-1] + text)
        else:
            normalized.append((y, text))
    return normalized


def _factory_unescape(text: str) -> str:
    """Remove fixed-page TeX escapes before code/listing presentation."""

    return (
        text.replace(r"\char95{}", "_")
        .replace(r"\_", "_")
        .replace(r"\char92{}", "\\")
        .replace(r"\textbackslash{}", "\\")
        .replace(r"\texttrademark", "™")
        .replace(
            "The RTI shall provide the IEEE Std 1516.1-2025 Java API classes",
            "The RTI shall provide the HLA 1516.1 Java API classes",
        )
        .replace("IEEE Std 1516.1-2025", "this document")
        .replace("This standard provides", "This compilation provides")
        .replace("provided with the standard", "provided with this compilation")
        .replace("CTRL_TERMINATE SESSION", "CTRL_TERMINATE_SESSION")
        .replace(" ()", "()")
    )


def _factory_plain_text(text: str) -> str:
    text = _factory_unescape(text)
    for _ in range(3):
        updated = re.sub(r"\\(?:textbf|textit|emph)\{([^{}]*)\}", r"\1", text)
        if updated == text:
            break
        text = updated
    return text.strip()


def _factory_inline_tokens(text: str) -> str:
    """Apply the API token role to bold source identifiers in prose."""

    text = _factory_unescape(text)
    text = re.sub(
        r"\\textbf\{([^{}]+)\}",
        lambda match: rf"\HLAAPIToken{{{match.group(1)}}}",
        text,
    )
    for _ in range(3):
        text = re.sub(
            r"\\HLAAPIToken\{([^{}]*)-\}\s*\\HLAAPIToken\{([^{}]*)\}",
            lambda match: rf"\HLAAPIToken{{{match.group(1)}{match.group(2)}}}",
            text,
        )
    tokens: list[str] = []

    def protect(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"APITOKENPLACEHOLDER{len(tokens) - 1}"

    def split_long_qualified_token(match: re.Match[str]) -> str:
        token = match.group(1)
        if len(token) < 36:
            return match.group(0)
        scope_index = token.find("::")
        call_index = token.find("(")
        # Do not treat a namespace qualifier inside a function argument such
        # as ``std::wstring`` as the line-break boundary.  Only the scope
        # qualifier that precedes the callable/member itself is eligible.
        if call_index >= 0 and scope_index > call_index:
            return match.group(0)
        head, tail = token.split("::", 1)
        # Keep the identifier semantically intact while giving TeX one
        # meaningful break opportunity between a C++ scope qualifier and its
        # member.  HLAAPIToken itself is intentionally an unbreakable box so
        # identifiers are never split at arbitrary characters.
        return rf"\HLAAPIToken{{{head}::}}\allowbreak\HLAAPIToken{{{tail}}}"

    # Protect source-derived token macros before adding the plain-text token
    # pass so one API identifier cannot become nested inside another.
    text = re.sub(
        r"\\HLAAPIToken\{([^{}]*::[^{}]*)\}",
        split_long_qualified_token,
        text,
    )
    text = re.sub(r"\\HLAAPIToken\{[^{}]*\}", protect, text)
    # Source pages use bold as their only semantic signal for many API names,
    # but package names, protocol symbols, and a few Java platform identifiers
    # are plain source text.  Keep those technical tokens in the same role
    # without making ordinary narrative words monospace.
    explicit_patterns = (
        r"(?<![\w])(?:hla\.rti1516_2025(?:\.[A-Za-z_][\w]*)*)(?![\w])",
        r"(?<![\w])(?:CTRL|HLA|RTI|FED)_[A-Z0-9_]+(?![\w])",
        r"(?<![\w])(?:ServiceLoader|META-INF/services|java\.base/java/util/ServiceLoader\.html|META-INF|CLASSPATH|PATH|hashCode\(\))(?![\w])",
    )
    for pattern in explicit_patterns:
        text = re.sub(
            pattern,
            lambda match: rf"\HLAAPIToken{{{match.group(0)}}}",
            text,
        )

    text = re.sub(r"\\HLAAPIToken\{[^{}]*\}", protect, text)
    # Let hyperref break source download URLs on natural-flow annex pages.
    def protect_url(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,;")
        tokens.append(rf"\url{{{url}}}")
        return f"APITOKENPLACEHOLDER{len(tokens) - 1}"

    text = re.sub(r"(?<![\\{])https?://[^\s{}]+", protect_url, text)
    text = text.replace("_", r"\HLAUnderscore{}")
    for index, token in enumerate(tokens):
        text = text.replace(f"APITOKENPLACEHOLDER{index}", token)
    return text


def _modern_java_factory_page(body: str) -> str:
    """Reflow an API source page into prose, API tokens, and code blocks.

    The helper name is retained for the acceptance-slice API, but the same
    grammar is now used across the full programming-language mapping run.
    """

    lines = _factory_fixed_lines(body)
    if not lines:
        return body
    events = [(offset, end) for offset, _args, end in _command_events(body, "HLAFixedBlock", 7)]
    first_offset = min(offset for offset, _end in events)
    last_end = max(end for _offset, end in events)
    lead = body[:first_offset]
    tail = body[last_end:]
    if r"\begin{hlafixedpage}" not in lead or r"\end{hlafixedpage}" not in tail:
        return body
    lead = lead.replace(r"\begin{hlafixedpage}", r"\begin{HLAAPIFlowPage}", 1)
    tail = tail.replace(r"\end{hlafixedpage}", r"\end{HLAAPIFlowPage}", 1)

    rendered: list[str] = [lead.rstrip(), r"\setlength{\parindent}{0pt}", r"\setlength{\parskip}{5pt}"]
    code_lines: list[str] = []
    prose_lines: list[str] = []
    prose_y: float | None = None
    code_y: float | None = None

    def flush_code() -> None:
        if not code_lines:
            return
        rendered.append(r"\begin{RLCodeBlock}")
        rendered.extend(code_lines)
        rendered.append(r"\end{RLCodeBlock}")
        code_lines.clear()
        code_y = None

    def flush_prose() -> None:
        if prose_lines:
            joined = " ".join(prose_lines).strip()
            joined = re.sub(r"(?<=[A-Za-z0-9_])-\s+(?=[A-Za-z])", "", joined)
            rendered.append(joined + r"\par")
            prose_lines.clear()

    for y, raw in lines:
        plain = _factory_plain_text(raw)
        heading = re.fullmatch(r"(?:\\textbf\{)?(\d+(?:\.\d+)+\s+[^{}]+)(?:\})?", raw)
        if heading:
            flush_prose()
            flush_code()
            rendered.append(rf"\HLASubsubclause{{{_factory_unescape(heading.group(1))}}}")
            prose_y = None
            continue
        code_candidate = plain.startswith((
            "RtiFactoryFactory.",
            "LogicalTimeFactoryFactory.",
            "AuthorizerFactoryFactory.",
            "RTIambassador.",
            "Set<RtiFactory>",
            "org.someorganization.",
            "new ",
            "#include",
            "static std::",
            "C++ time class name",
            "C++ interval class name",
            "C++ time factory class name",
        )) or bool(
            re.fullmatch(
                r"(?:EncoderFactory|String)\s+[A-Za-z_][A-Za-z0-9_]*\([^)]*\)",
                plain,
            )
        ) or plain.endswith((";", " =", "="))
        if not code_candidate and plain.startswith(("std::", "makeLogicalTimeFactory")):
            # A source line may begin with a C++ namespace or factory call,
            # but narrative sentences containing ``std::`` are prose.  Keep
            # only compact source-shaped lines in a code block.
            code_candidate = (
                ". " not in plain
                and not re.search(r"\b(?:The|This|In|is|are|used|with|that|to|of)\b", plain)
            )
        if not code_candidate and plain.endswith((".java", ".h")):
            code_candidate = True
        if (
            not code_candidate
            and code_lines
            and code_y is not None
            and y - code_y <= 18
        ):
            # Keep wrapped source declarations together when the fixed source
            # page split a statement across adjacent baselines.
            code_candidate = plain.startswith(("=", ".", "&", "*"))
        if code_candidate:
            flush_prose()
            code_lines.append(plain)
            code_y = y
            prose_y = None
            continue
        flush_code()
        # A source line with a large baseline gap starts a new paragraph; the
        # natural-flow paragraph keeps the content selectable and lets the
        # page break at a real typographic boundary.
        if prose_y is not None and y - prose_y > 18:
            flush_prose()
        prose_lines.append(_factory_inline_tokens(raw))
        prose_y = y
    flush_prose()
    flush_code()
    rendered.append(tail.lstrip())
    result = "\n".join(rendered)
    for _ in range(3):
        result = re.sub(
            r"\\HLAAPIToken\{([^{}]*)-\}\s*\\HLAAPIToken\{([^{}]*)\}",
            lambda match: rf"\HLAAPIToken{{{match.group(1)}{match.group(2)}}}",
            result,
        )
    return result


def _modern_api_manifest_page(body: str) -> str:
    """Render Java/C++ file manifests as selectable directory listings."""

    lines = _factory_fixed_lines(body)
    if not lines:
        return body
    events = [(offset, end) for offset, _args, end in _command_events(body, "HLAFixedBlock", 7)]
    first_offset = min(offset for offset, _end in events)
    last_end = max(end for _offset, end in events)
    lead = body[:first_offset]
    tail = body[last_end:]
    if r"\begin{hlafixedpage}" not in lead or r"\end{hlafixedpage}" not in tail:
        return body
    lead = lead.replace(r"\begin{hlafixedpage}", r"\begin{HLAAPIFlowPage}", 1)
    tail = tail.replace(r"\end{hlafixedpage}", r"\end{HLAAPIFlowPage}", 1)
    rendered: list[str] = [lead.rstrip(), r"\setlength{\parindent}{0pt}", r"\setlength{\parskip}{5pt}"]
    code_lines: list[str] = []
    prose_lines: list[str] = []

    def flush_code() -> None:
        if not code_lines:
            return
        rendered.append(r"\begin{RLCodeBlock}")
        rendered.extend(code_lines)
        rendered.append(r"\end{RLCodeBlock}")
        code_lines.clear()

    def flush_prose() -> None:
        if prose_lines:
            rendered.append(" ".join(prose_lines).strip() + r"\par")
            prose_lines.clear()

    for _y, raw in lines:
        plain = _factory_plain_text(raw)
        heading = re.fullmatch(r"(Annex\s+[A-Z]|\d+(?:\.\d+)+)\s+.+", plain)
        if heading:
            flush_prose()
            flush_code()
            rendered.append(rf"\HLASubsubclause{{{_factory_unescape(plain)}}}")
            continue
        is_path = (
            plain.endswith((".java", ".h", "/", ":"))
            or plain.startswith(("hla/", "auth/", "encoding/", "exceptions/", "time/"))
        )
        if is_path:
            flush_prose()
            code_lines.append(plain)
        else:
            flush_code()
            prose_lines.append(_factory_inline_tokens(raw))
    flush_prose()
    flush_code()
    rendered.append(tail.lstrip())
    return "\n".join(rendered)


def _modern_protocol_prose_page(body: str) -> str:
    """Reflow protocol narrative and rules while preserving message tokens."""

    lines = _factory_fixed_lines(body)
    if not lines:
        return body
    events = [(offset, end) for offset, _args, end in _command_events(body, "HLAFixedBlock", 7)]
    first_offset = min(offset for offset, _end in events)
    last_end = max(end for _offset, end in events)
    lead = body[:first_offset]
    tail = body[last_end:]
    if r"\begin{hlafixedpage}" not in lead or r"\end{hlafixedpage}" not in tail:
        return body
    lead = lead.replace(r"\begin{hlafixedpage}", r"\begin{HLAProtocolFlowPage}", 1)
    tail = tail.replace(r"\end{hlafixedpage}", r"\end{HLAProtocolFlowPage}", 1)
    rendered: list[str] = [lead.rstrip()]
    prose_lines: list[str] = []
    list_label: str | None = None
    list_lines: list[str] = []
    list_y: float | None = None
    prose_y: float | None = None
    bullet_lines: list[str] = []
    bullet_y: float | None = None

    def join_lines(values: Sequence[str]) -> str:
        joined = " ".join(values).strip()
        return re.sub(r"(?<=[A-Za-z0-9_])-\s+(?=[A-Za-z])", "", joined)

    def flush_prose() -> None:
        nonlocal prose_y
        if prose_lines:
            rendered.append(_factory_inline_tokens(join_lines(prose_lines)) + r"\par")
            prose_lines.clear()
        prose_y = None

    def flush_list() -> None:
        nonlocal list_label, list_y
        if list_label is not None:
            rendered.append(
                rf"\HLAProtocolRule{{{tex_escape(list_label)}}}{{{_factory_inline_tokens(join_lines(list_lines))}}}"
            )
        list_label = None
        list_lines.clear()
        list_y = None

    def flush_bullet() -> None:
        nonlocal bullet_y
        if bullet_lines:
            rendered.append(
                rf"\HLAProtocolBullet{{{_factory_inline_tokens(join_lines(bullet_lines))}}}"
            )
            bullet_lines.clear()
        bullet_y = None

    for y, raw in lines:
        plain = _factory_plain_text(raw)
        heading = re.fullmatch(r"(\d+(?:\.\d+)+)\s+.+", plain)
        if heading:
            flush_prose()
            flush_list()
            flush_bullet()
            rendered.append(rf"\HLASubsubclause{{{_factory_unescape(plain)}}}")
            prose_y = None
            continue
        if plain == "---" or plain.startswith("--- "):
            flush_prose()
            flush_list()
            flush_bullet()
            bullet_lines.append(plain[3:].strip())
            bullet_y = y
            prose_y = None
            continue
        marker = re.match(r"^([a-z]|\d+)\)\s*(.*)$", plain)
        if marker:
            flush_prose()
            flush_list()
            flush_bullet()
            list_label = marker.group(1) + ")"
            list_lines.append(marker.group(2))
            list_y = y
            prose_y = None
            continue
        if list_label is not None:
            if list_y is not None and y - list_y > 18:
                flush_list()
            else:
                list_lines.append(plain)
                list_y = y
                continue
        if bullet_lines:
            if bullet_y is not None and y - bullet_y > 18:
                flush_bullet()
            else:
                bullet_lines.append(plain)
                bullet_y = y
                continue
        if prose_y is not None and y - prose_y > 18:
            flush_prose()
        prose_lines.append(raw)
        prose_y = y
    flush_prose()
    flush_list()
    flush_bullet()
    rendered.append(tail.lstrip())
    return "\n".join(rendered)


def _modernize_2010_service_surface(body: str) -> str:
    """Release source-page service clauses as normal flowing content.

    The 2010.1 source adapter contains many deliberate ``\\clearpage`` and
    large source-positioning ``\\vspace*`` commands.  Those commands are
    useful while reconstructing a scanned page, but they create empty
    continuation pages once the body contains generated vector figures and
    modern page furniture.  Remove only those layout-only commands from
    blocks that contain actual service headings; the authored prose, lists,
    numbering, and deferred native charts remain unchanged.
    """

    service_headings = [
        args[0]
        for _offset, args, _end in _command_events(body, "subsection", 1)
        if "service" in args[0].lower()
    ]
    if not service_headings:
        return body
    body = re.sub(r"(?m)^\s*\\clearpage\s*$", "", body)
    body = re.sub(r"(?m)^\s*\\newpage\s*$", "", body)
    # These are source-page placement offsets, not editorial spacing. Keep
    # ordinary point-sized paragraph spacing and local table rhythm intact.
    body = re.sub(r"\\vspace\*\{[-+]?\d+(?:\.\d+)?(?:in|pt)\}", "", body)

    # Keep the numbered subsection and its PDF bookmark, but add the same
    # explicit federate/RTI direction used by the 2025 service grammar.  The
    # source title carries the RTI-initiated marker when applicable.
    service_events = [
        (offset, args, end)
        for offset, args, end in _command_events(body, "subsection", 1)
        if "service" in args[0].lower()
    ]
    for offset, args, end in reversed(service_events):
        title = args[0]
        direction = (
            r"RTI $\rightarrow$ FEDERATE"
            if "rtiinitiated" in title.lower() or "dagger" in title.lower()
            else r"FEDERATE $\rightarrow$ RTI"
        )
        original = body[offset:end]
        replacement = original + "\n" + f"\\HLAServiceDirectionLine{{{direction}}}"
        body = body[:offset] + replacement + body[end:]
    return body


def render_build_manifest(
    model: DocumentModel,
    generated_files: tuple[str, ...],
    semantic_inputs: tuple[str, ...] = (),
) -> str:
    """Render a small generated entrypoint consumed by every LaTeX build."""
    lines = [
        "% Generated from the typed semantic model; edit semantic source instead.",
        f"\\providecommand{{\\SemanticDocumentID}}{{{tex_escape(model.document_id)}}}",
        f"\\providecommand{{\\SemanticSchemaVersion}}{{{model.schema_version}}}",
        f"\\providecommand{{\\SemanticClauseCount}}{{{len(model.clauses)}}}",
        f"\\providecommand{{\\SemanticDefinitionCount}}{{{len(model.definitions)}}}",
        f"\\providecommand{{\\SemanticRequirementCount}}{{{len(model.requirements)}}}",
        f"\\providecommand{{\\SemanticContentElementCount}}{{{len(model.content_elements)}}}",
        f"\\providecommand{{\\SemanticStateMachineCount}}{{{len(model.state_machines)}}}",
        f"\\providecommand{{\\SemanticSequenceDiagramCount}}{{{len(model.sequence_diagrams)}}}",
        f"\\providecommand{{\\SemanticGraphDiagramCount}}{{{len(model.graph_diagrams)}}}",
        f"\\providecommand{{\\SemanticReferenceCount}}{{{len(model.references)}}}",
        f"\\providecommand{{\\SemanticCrossReferenceCount}}{{{len(model.cross_references)}}}",
        f"\\providecommand{{\\SemanticFigureCount}}{{{len(model.figures)}}}",
        f"\\providecommand{{\\SemanticNoteCount}}{{{len(model.notes)}}}",
        f"\\providecommand{{\\SemanticTableCount}}{{{len(model.tables)}}}",
        *_wrapped_macro("GeneratedFiles", generated_files),
        (
            "\\typeout{Semantic model loaded: "
            f"{tex_escape(model.document_id)} ({len(model.clauses)} clauses)}}"
        ),
    ]
    for name in semantic_inputs:
        input_line = f"\\input{{output/semantic/{Path(name).with_suffix('').as_posix()}}}"
        if name.startswith("content-element-"):
            # Faithful page adapters already carry their source-positioned
            # visible text.  Very large content-element text macros are only
            # needed by layout-free semantic prose, so allow a faithful
            # entrypoint to omit them when the TeX engine's memory budget is
            # tighter than the complete typed manifest.
            lines.extend(
                ("\\ifdefined\\HLASkipSemanticContentElementData", "\\else", input_line, "\\fi")
            )
        else:
            lines.append(input_line)
    return "\n".join(lines)


def _render_semantic_index(model: DocumentModel) -> str:
    """Render model-wide IDs so every build consumes semantic source data."""
    values = {
        "CanonicalRecordIDs": model.canonical_record_ids(),
        "RootClauseIDs": tuple(item.id for item in model.root_clauses()),
        "DefinitionIDs": tuple(item.id for item in model.ordered_definitions()),
        "RequirementIDs": tuple(item.id for item in model.ordered_requirements()),
        "ContentElementIDs": tuple(item.id for item in model.content_elements),
        "StateMachineIDs": tuple(item.id for item in model.state_machines),
        "SequenceDiagramIDs": tuple(item.id for item in model.sequence_diagrams),
        "GraphDiagramIDs": tuple(item.id for item in model.graph_diagrams),
        "ReferenceIDs": tuple(item.id for item in model.references),
        "CrossReferenceIDs": tuple(item.id for item in model.cross_references),
        "FigureIDs": tuple(item.id for item in model.figures),
        "NoteIDs": tuple(item.id for item in model.notes),
        "TableIDs": tuple(item.id for item in model.tables),
    }
    lines = ["% Generated semantic index; layout adapters consume these IDs."]
    for suffix, identifiers in values.items():
        if not identifiers:
            lines.append(f"\\providecommand{{\\Semantic{suffix}}}{{}}")
            continue
        lines.append(f"\\providecommand{{\\Semantic{suffix}}}{{%")
        lines.extend(
            f"{tex_escape(identifier)}{',' if index < len(identifiers) - 1 else ''}%"
            for index, identifier in enumerate(identifiers)
        )
        lines.append("}")
    return "\n".join(lines)


def generate(request: GenerationRequest) -> GenerationResult:
    """Generate selected semantic blocks and return typed build outputs."""
    root = request.root
    output = request.output
    source = request.source
    dialect = request.dialect
    definition_ids = request.definition_ids
    requirement_ids = request.requirement_ids
    content_block_ids = request.content_block_ids
    content_element_ids = request.content_element_ids
    table_family_ids = request.table_family_ids
    include_outline = request.include_outline
    include_table_cells = request.include_table_cells
    include_faithful_body = request.include_faithful_body
    faithful_layout_profile = request.faithful_layout_profile
    faithful_body_exclude_path_parts = request.faithful_body_exclude_path_parts
    use_generated_faithful_blocks = request.use_generated_faithful_blocks
    service_page_renderer = request.service_page_renderer
    model = load_document_model(root, source)
    compiled_hierarchy = compile_hierarchy(model)
    output.mkdir(parents=True, exist_ok=True)
    # This directory is a generated-only build input. Remove stale generated
    # TeX blocks before writing the current deterministic selection; unrelated
    # review/export artifacts live in separate ignored directories.
    for path in output.glob("*.tex"):
        path.unlink()
    definitions = {item.id: item for item in model.ordered_definitions()}
    requirements = {item.id: item for item in model.ordered_requirements()}
    content_blocks = {item.id: item for item in model.content_blocks}
    content_elements = {item.id: item for item in model.content_elements}
    table_families = {item.id: item for item in model.table_families}
    tables = {item.id: item for item in model.tables}
    table_caption_overrides = {
        table_id: caption
        for family in model.table_families
        for table_id, caption in family.table_captions.items()
    }
    index_name = "semantic-index.tex"
    _write(output / index_name, _render_semantic_index(model))
    generated_files: list[str] = [index_name]
    semantic_inputs: list[str] = [index_name]

    for item in model.references:
        name = f"reference-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_reference_data(item))
        generated_files.append(name)
        semantic_inputs.append(name)
    for item in model.cross_references:
        name = f"cross-reference-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_cross_reference_data(item))
        generated_files.append(name)
    for item in model.figures:
        name = f"figure-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_figure_data(item))
        generated_files.append(name)
        semantic_inputs.append(name)
    for item in model.notes:
        name = f"note-{_generated_filename(item.id)}-data.tex"
        _write(output / name, render_note_data(item))
        generated_files.append(name)
        semantic_inputs.append(name)
    for item in model.tables:
        name = f"table-record-{_generated_filename(item.id)}-data.tex"
        _write(
            output / name,
            render_table_data(item, caption_override=table_caption_overrides.get(item.id)),
        )
        generated_files.append(name)
        semantic_inputs.append(name)

    # Diagram TeX is generated from the typed records and can be consumed by
    # both standalone review builds and faithful source-page adapters.
    diagram_inputs: dict[str, str] = {}
    native_fallback_diagrams: set[str] = set()
    diagram_captions: dict[str, str] = {}
    use_plantuml = request.state_machine_renderer == "plantuml"
    plantuml_review = _plantuml_review(root) if use_plantuml else None
    reviewed_plantuml_ids = plantuml_review[0] if plantuml_review is not None else None
    landscape_plantuml_ids = plantuml_review[1] if plantuml_review is not None else set()
    embedded_diagram_layout = {
        figure_number: (x, y, width, height)
        for figure_number, x, y, width, height in getattr(source, "embedded_diagram_layout", ())
    }
    landscape_figure_pages = {
        page_sequence: (figure_number, record_id, caption)
        for figure_number, page_sequence, record_id, caption in getattr(
            source, "landscape_figure_pages", ()
        )
    }
    diagram_bindings = getattr(source, "diagram_surface_bindings", ())
    if getattr(source, "diagram_surface_document_id", model.document_id) != model.document_id:
        diagram_bindings = ()
        # The shared edition profile also carries figure-only landscape and
        # coordinate metadata.  Non-interface volumes intentionally reuse the
        # command vocabulary but must not inherit 1516.1 figure bindings.
        embedded_diagram_layout = {}
        landscape_figure_pages = {}
    canonical_plantuml_payloads: dict[str, dict[str, object]] = {}
    if use_plantuml and model.document_id == "hla-1516.1-2010":
        canonical_root = root.parent / "hla-1516.1-2025"
        if canonical_root.is_dir():
            canonical_model = load_document_model(
                canonical_root,
                source_profile_for_document("hla-1516.1-2025"),
            )
            canonical_plantuml_payloads = {
                item.id: item.model_dump(mode="json")
                for item in canonical_model.state_machines
            }
    for machine in model.state_machines:
        name = f"state-machine-{_generated_filename(machine.id)}.tex"
        source_machine_payload = machine.model_dump(mode="json")
        machine_payload = _cross_edition_plantuml_payload(
            source_machine_payload,
            document_id=model.document_id,
            canonical_payloads=canonical_plantuml_payloads,
        )
        _write(output / name, render_state_machine(source_machine_payload))
        generated_files.append(name)
        plantuml_name = f"state-machine-{_generated_filename(machine.id)}.puml"
        _write(output / plantuml_name, render_plantuml(machine_payload))
        generated_files.append(plantuml_name)
        if machine.provenance is not None:
            diagram_captions[machine.id] = machine.provenance.caption
        if use_plantuml and (
            not _plantuml_ready(machine_payload)
            or (
                reviewed_plantuml_ids is not None
                and machine.id not in reviewed_plantuml_ids
            )
        ):
            # Keep the audited source figure in the faithful build until its
            # endpoint mapping and visual review are complete.  A partial or
            # unreviewed PlantUML graph is materially worse than a visibly
            # legacy figure because it can drop normative structure or make
            # the chart unreadable without warning.
            native_fallback_diagrams.add(machine.id)
            diagram_inputs[machine.id] = name
        else:
            diagram_inputs[machine.id] = (
                f"state-machine-{_generated_filename(machine.id)}.pdf" if use_plantuml else name
            )
    for diagram in model.sequence_diagrams:
        name = f"sequence-diagram-{_generated_filename(diagram.id)}.tex"
        _write(output / name, render_sequence_tikz(diagram))
        generated_files.append(name)
        diagram_inputs[diagram.id] = name
    for diagram in model.graph_diagrams:
        name = f"graph-diagram-{_generated_filename(diagram.id)}.tex"
        _write(output / name, render_graph_tikz(diagram))
        generated_files.append(name)
        diagram_inputs[diagram.id] = name

    hierarchy_json_name = "hierarchy.json"
    _write(output / hierarchy_json_name, compiled_hierarchy.to_json())
    generated_files.append(hierarchy_json_name)
    hierarchy_name = "hierarchy-index.tex"
    _write(output / hierarchy_name, render_hierarchy_index(compiled_hierarchy))
    generated_files.append(hierarchy_name)
    semantic_inputs.append(hierarchy_name)

    for identifier in definition_ids:
        if identifier not in definitions:
            raise ValueError(f"unknown definition ID: {identifier}")
        name = f"definition-{_generated_filename(identifier)}.tex"
        _write(
            output / name,
            render_definition(
                definitions[identifier],
                dialect,
                document_id=model.document_id,
            ),
        )
        generated_files.append(name)
        data_name = f"definition-{_generated_filename(identifier)}-data.tex"
        _write(output / data_name, render_definition_data(definitions[identifier]))
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    for identifier in requirement_ids:
        if identifier not in requirements:
            raise ValueError(f"unknown requirement ID: {identifier}")
        name = f"requirement-{_generated_filename(identifier)}.tex"
        _write(
            output / name,
            render_requirement(
                requirements[identifier],
                dialect,
                document_id=model.document_id,
            ),
        )
        generated_files.append(name)
        data_name = f"requirement-{_generated_filename(identifier)}-data.tex"
        _write(output / data_name, render_requirement_data(requirements[identifier]))
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    for identifier in content_block_ids:
        if identifier not in content_blocks:
            raise ValueError(f"unknown content block ID: {identifier}")
        name = f"content-block-{_generated_filename(identifier)}.tex"
        block = content_blocks[identifier]
        body = block.layout_body or ""
        landscape_page = landscape_figure_pages.get(block.sequence)
        if landscape_page is not None:
            figure_number, record_id, caption = landscape_page
            input_name = diagram_inputs.get(record_id)
            if input_name is None:
                raise ValueError(
                    f"landscape Figure {figure_number} references missing record {record_id}"
                )
            body = _landscape_figure_page_body(
                figure_number=figure_number,
                record_id=record_id,
                caption=caption,
                input_name=input_name,
            )
        elif block.layout_body is not None:
            body = _fit_fixed_page_makeboxes(body)
            body = _semanticize_visible_surfaces(body, block, model, source)
        else:
            body = _semantic_content_body(block, model) or body
        if (
            model.document_id == "hla-1516.1-2025"
            and service_page_renderer == "flow"
            and r"\HLAServiceHeadingAt" in body
        ):
            body = _modern_service_flow_page(body)
        if model.document_id == "hla-1516.1-2010" and service_page_renderer == "flow":
            body = _modernize_2010_service_surface(body)
        if model.document_id == "hla-1516.1-2025":
            body = _modernize_2025_source_surface(
                body,
                sequence=block.sequence,
                tables=model.tables,
            )
        embedded_figures: set[int] = set()
        reflowed_figures: set[int] = set()
        if model.document_id == "hla-1516.1-2025" and block.sequence in {40, 41}:
            for figure_number, page_sequence, record_id in diagram_bindings:
                if page_sequence != block.sequence:
                    continue
                input_name = diagram_inputs.get(record_id)
                caption = diagram_captions.get(record_id)
                if input_name is None or caption is None:
                    continue
                body = _modern_statechart_reflow_page(
                    body,
                    sequence=block.sequence,
                    figure_number=figure_number,
                    caption=caption,
                    input_name=input_name,
                )
                reflowed_figures.add(figure_number)
        if model.document_id == "hla-1516.1-2025" and block.sequence in {45, 46, 47}:
            bound_figures = [
                (
                    figure_number,
                    diagram_inputs[record_id],
                    diagram_captions[record_id],
                )
                for figure_number, page_sequence, record_id in diagram_bindings
                if page_sequence == block.sequence
                and record_id in diagram_inputs
                and record_id in diagram_captions
            ]
            if bound_figures:
                body = _modern_2025_statechart_reflow_page(
                    body,
                    sequence=block.sequence,
                    figures=bound_figures,
                )
                reflowed_figures.update(
                    figure_number for figure_number, _input, _caption in bound_figures
                )
        if model.document_id == "hla-1516.1-2025" and block.sequence == 42:
            body = _modern_statechart_reflow_page(
                body,
                sequence=block.sequence,
                figure_number=0,
                caption="",
                input_name="",
            )
        for figure_number, page_sequence, record_id in diagram_bindings:
            if page_sequence != block.sequence:
                continue
            if figure_number in reflowed_figures:
                embedded_figures.add(figure_number)
                continue
            input_name = diagram_inputs.get(record_id)
            if input_name is None:
                raise ValueError(
                    f"diagram surface Figure {figure_number} references missing record {record_id}"
                )
            body = _embed_diagram(
                body,
                figure_number,
                input_name,
                embedded_diagram_layout,
                preserve_native=record_id in native_fallback_diagrams,
                caption=diagram_captions.get(record_id),
                landscape=record_id in landscape_plantuml_ids,
            )
            embedded_figures.add(figure_number)
        for diagram in (*model.state_machines, *model.sequence_diagrams, *model.graph_diagrams):
            if diagram.provenance is None or diagram.provenance.page - 1 != block.sequence:
                continue
            figure_number = _figure_number(diagram.provenance.caption)
            input_name = diagram_inputs.get(diagram.id)
            if (
                figure_number is not None
                and figure_number not in embedded_figures
                and input_name is not None
            ):
                body = _embed_diagram(
                    body,
                    figure_number,
                    input_name,
                    embedded_diagram_layout,
                    preserve_native=diagram.id in native_fallback_diagrams,
                    caption=diagram_captions.get(diagram.id),
                    landscape=diagram.id in landscape_plantuml_ids,
                )
        if model.document_id == "hla-1516.1-2010":
            # Some faithful 2010 source blocks already contain a normalized
            # generated-PDF include, so they bypass the diagram binding path
            # above.  Apply the final promotion against the canonical asset
            # name for every state chart; the helper is a no-op when the
            # current block does not contain that chart.  This keeps every
            # PlantUML state chart on a true landscape page, including the
            # older Figure 8/9 center/makebox wrappers.
            for machine in model.state_machines:
                if machine.provenance is None:
                    continue
                figure_match = re.search(r"figure-(\d+)$", machine.id)
                if figure_match is None:
                    continue
                figure_number = int(figure_match.group(1))
                body = _promote_remaining_landscape_asset(
                    body,
                    figure_number=figure_number,
                    input_name=(
                        f"state-machine-{_generated_filename(machine.id)}.pdf"
                    ),
                    caption=machine.provenance.caption,
                )
        render_block = block.model_copy(update={"layout_body": body})
        _write(
            output / name,
            "\n".join(
                (
                    render_block_bindings(
                        model, render_block, dialect, compiled=compiled_hierarchy
                    ),
                    render_content_block(render_block),
                )
            ),
        )
        generated_files.append(name)
        data_name = f"content-block-{_generated_filename(identifier)}-data.tex"
        _write(output / data_name, render_content_block_data(content_blocks[identifier]))
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    for identifier in content_element_ids:
        if identifier not in content_elements:
            raise ValueError(f"unknown content element ID: {identifier}")
        name = f"content-element-{_generated_filename(identifier)}-data.tex"
        _write(output / name, render_content_element_data(content_elements[identifier]))
        generated_files.append(name)
        semantic_inputs.append(name)
    selected_table_family_ids = (
        tuple(table_families) if table_family_ids is None else table_family_ids
    )
    for identifier in selected_table_family_ids:
        if identifier not in table_families:
            raise ValueError(f"unknown table family ID: {identifier}")
        family = table_families[identifier]
        family_tables = tuple(tables[table_id] for table_id in family.table_ids)
        data_name = f"table-family-{_generated_filename(identifier)}-data.tex"
        _write(
            output / data_name,
            render_table_family_data(
                family,
                family_tables,
                include_cells=include_table_cells,
            ),
        )
        generated_files.append(data_name)
        semantic_inputs.append(data_name)
    if include_outline:
        name = "clause-outline.tex"
        _write(output / name, render_hierarchy_outline(model, dialect))
        generated_files.append(name)
        semantic_inputs.append(name)

    faithful_layout: FaithfulLayoutProjection | None = None
    if include_faithful_body:
        faithful_layout = build_faithful_layout_projection(
            model,
            content_block_ids=content_block_ids,
            profile=faithful_layout_profile,
            exclude_path_parts=faithful_body_exclude_path_parts,
        )
        name = "faithful-layout.json"
        _write(output / name, faithful_layout.model_dump_json(indent=2))
        generated_files.append(name)
        name = "faithful-body.tex"
        _write(
            output / name,
            render_faithful_body(
                faithful_layout,
                use_generated_blocks=use_generated_faithful_blocks,
            ),
        )
        generated_files.append(name)

    _write(
        output / "semantic-manifest.tex",
        render_build_manifest(model, tuple(generated_files), tuple(semantic_inputs)),
    )
    if model.document_id == "hla-1516.1-2025":
        for generated_path in output.glob("*.tex"):
            _write(
                generated_path,
                _modernize_2025_generated_tex(
                    generated_path.read_text(encoding="utf-8")
                ),
            )
    return GenerationResult(
        model=model,
        output=output,
        generated_files=tuple(generated_files),
        semantic_inputs=tuple(semantic_inputs),
        faithful_layout=faithful_layout,
    )
