"""Diagram rendering and placement helpers for semantic generation."""

from __future__ import (
    annotations,
)

import json
import re
from collections.abc import (
    Mapping,
    MutableMapping,
    MutableSequence,
    Sequence,
)
from pathlib import (
    Path,
)
from types import (
    MappingProxyType,
)

from pydantic import (
    JsonValue,
)

from hla_lab.adapters.latex_renderer import (
    tex_escape,
)
from hla_lab.core.parsing import (
    balanced_span,
)
from hla_lab.core.text import (
    safe_filename,
)

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


def _plantuml_ready(machine: Mapping[str, JsonValue]) -> bool:
    """Return whether every asserted transition has renderable endpoints."""

    raw_states: JsonValue = machine.get("states", [])
    if not isinstance(raw_states, list):
        return False
    states: list[JsonValue] = raw_states
    state_ids: set[str] = set()
    for raw_state in states:
        state: JsonValue = raw_state
        if isinstance(state, dict) and state.get("id"):
            state_ids.add(str(state["id"]))
    raw_transitions: JsonValue = machine.get("transitions", [])
    if not isinstance(raw_transitions, list):
        return False
    transitions: list[JsonValue] = raw_transitions
    transition_records: list[dict[str, JsonValue]] = []
    for raw_transition in transitions:
        transition: JsonValue = raw_transition
        if isinstance(transition, dict):
            transition_records.append(transition)
    return bool(state_ids) and all(
        transition.get("source_state") in state_ids and transition.get("target_state") in state_ids
        for transition in transition_records
    )


def _manifest_string_list(value: JsonValue, path: Path, field: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{path}: {field} must be a list of strings")
    raw_items: list[JsonValue] = value
    strings: list[str] = []
    for raw_item in raw_items:
        item: JsonValue = raw_item
        if not isinstance(item, str):
            raise ValueError(f"{path}: {field} must be a list of strings")
        strings.append(item)
    return strings


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
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: review manifest must be a JSON object")
    approved = _manifest_string_list(
        payload.get("approved_machine_ids"), path, "approved_machine_ids"
    )
    landscape = _manifest_string_list(
        payload.get("landscape_machine_ids", []), path, "landscape_machine_ids"
    )
    approved_ids = set(approved)
    landscape_ids = set(landscape)
    if not landscape_ids <= approved_ids:
        raise ValueError(f"{path}: landscape_machine_ids must be a subset of approved_machine_ids")
    return approved_ids, landscape_ids


_2010_PLANTUML_CORROBORATION = MappingProxyType(
    {
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
)


def _canonical_payload_for_machine(
    machine_id: str,
    canonical_payloads: Mapping[str, Mapping[str, JsonValue]],
) -> Mapping[str, JsonValue] | None:
    figure_match = re.search(r"figure-(\d+)$", machine_id)
    if figure_match is None:
        return None
    canonical_id = _2010_PLANTUML_CORROBORATION.get(f"figure-{int(figure_match.group(1)):02d}")
    return canonical_payloads.get(canonical_id or "")


def _canonical_state_id_map(states: Sequence[JsonValue], machine_id: str) -> dict[str, str]:
    state_ids: dict[str, str] = {}
    for raw_state in states:
        if not isinstance(raw_state, dict) or not raw_state.get("id"):
            continue
        old_id = str(raw_state["id"])
        state_ids[old_id] = f"{machine_id}.{old_id.split('.', 1)[-1]}"
    return state_ids


def _remap_canonical_states(
    states: Sequence[JsonValue], state_ids: Mapping[str, str], machine_id: str
) -> None:
    for raw_state in states:
        if not isinstance(raw_state, dict):
            continue
        old_id = str(raw_state.get("id", ""))
        raw_state["id"] = state_ids.get(old_id, f"{machine_id}.{old_id}")
        parent_id = raw_state.get("parent_id")
        if parent_id in state_ids:
            raw_state["parent_id"] = state_ids[str(parent_id)]


def _remap_canonical_transitions(
    transitions: Sequence[JsonValue], state_ids: Mapping[str, str], machine_id: str
) -> None:
    for raw_transition in transitions:
        if not isinstance(raw_transition, dict):
            continue
        raw_transition["id"] = f"{machine_id}.{raw_transition.get('id', 'transition')}"
        for key in ("source_state", "target_state"):
            endpoint = raw_transition.get(key)
            if endpoint in state_ids:
                raw_transition[key] = state_ids[str(endpoint)]


def _apply_authoritative_machine_fields(
    payload: MutableMapping[str, JsonValue],
    machine_payload: Mapping[str, JsonValue],
    machine_id: str,
    state_ids: Mapping[str, str],
) -> None:
    for field in ("title", "clause_id", "source", "provenance"):
        payload[field] = machine_payload.get(field, payload.get(field))
    payload["id"] = machine_id
    payload["initial_state_ids"] = [
        state_ids.get(str(value), f"{machine_id}.{value}")
        for value in payload.get("initial_state_ids", ())
    ]
    payload["notes"] = (
        "PlantUML artwork projection corroborated against the corresponding "
        "2025 Harel state record; the 2010 source record remains the document authority."
    )


def _project_canonical_machine(
    canonical: Mapping[str, JsonValue],
    machine_payload: Mapping[str, JsonValue],
    machine_id: str,
) -> dict[str, JsonValue]:
    payload: dict[str, JsonValue] = json.loads(json.dumps(canonical))
    states_value = payload.get("states", [])
    states = states_value if isinstance(states_value, list) else []
    state_ids = _canonical_state_id_map(states, machine_id)
    _remap_canonical_states(states, state_ids, machine_id)
    transitions_value = payload.get("transitions", [])
    transitions = transitions_value if isinstance(transitions_value, list) else []
    _remap_canonical_transitions(transitions, state_ids, machine_id)
    _apply_authoritative_machine_fields(payload, machine_payload, machine_id, state_ids)
    return payload


def _cross_edition_plantuml_payload(
    machine_payload: Mapping[str, JsonValue],
    *,
    document_id: str,
    canonical_payloads: Mapping[str, Mapping[str, JsonValue]],
) -> dict[str, JsonValue]:
    """Complete 2010 PlantUML projections from an explicit family crosswalk.

    The 2010 source records remain authoritative for the faithful document,
    captions, and provenance. Several extracted 2010 charts omit endpoint
    mappings, so the corresponding 2025 Harel record supplies artwork topology
    without replacing the 2010 semantic source record.
    """
    if document_id != "hla-1516.1-2010" or _plantuml_ready(machine_payload):
        return machine_payload  # type: ignore[return-value]
    machine_id = str(machine_payload.get("id", ""))
    canonical = _canonical_payload_for_machine(machine_id, canonical_payloads)
    if canonical is None:
        return machine_payload  # type: ignore[return-value]
    return _project_canonical_machine(canonical, machine_payload, machine_id)


def _diagram_embed_macro(
    input_name: str, geometry: tuple[float, float, float, float] | None
) -> str:
    if geometry is None:
        return ""
    x, y, width, height = geometry
    embed_macro = "\\HLAEmbeddedGraphicAt" if input_name.endswith(".pdf") else "\\HLAEmbeddedTikZAt"
    return (
        f"  {embed_macro}{{{x:g}}}{{{y:g}}}{{{width:g}}}{{{height:g}}}{{"
        f"output/semantic/{input_name}}}%\n"
    )


def _landscape_page_replacement(figure_number: int, input_name: str, caption: str | None) -> str:
    return (
        rf"\stdsemanticlandscapefigure{{{figure_number}}}"
        rf"{{{tex_escape(caption or f'Figure {figure_number}')}}}"
        rf"{{output/semantic/{input_name}}}"
    )


def _replace_landscape_figure_line(
    lines: MutableSequence[str],
    index: int,
    replacement: str,
    input_name: str,
    native_source_marker: str,
) -> bool:
    line = lines[index]
    if input_name in line and (r"\input" in line or r"\includegraphics" in line):
        lines[index] = replacement
        return True
    if (input_name in line or native_source_marker in line) and (
        "\\stdsemanticfigure" in line or "\\stdnativefigure" in line
    ):
        lines[index] = replacement
        return True
    return False


def _replace_landscape_tikz_block(
    lines: MutableSequence[str],
    index: int,
    replacement: str,
    input_name: str,
    native_source_marker: str,
) -> bool:
    if "\\begin{tikzpicture}" not in lines[index]:
        return False
    end = next(
        (
            candidate
            for candidate in range(index + 1, len(lines))
            if "\\end{tikzpicture}" in lines[candidate]
        ),
        None,
    )
    if end is None:
        return False
    contains_asset = any(
        input_name in lines[candidate] or native_source_marker in lines[candidate]
        for candidate in range(index, end + 1)
    )
    if not contains_asset:
        return False
    lines[index : end + 1] = [replacement]
    return True


def _replace_landscape_asset(
    lines: MutableSequence[str],
    figure_number: int,
    input_name: str,
    caption: str | None,
    landscape: bool,
) -> bool:
    if not landscape or not input_name.endswith(".pdf"):
        return False
    replacement = _landscape_page_replacement(figure_number, input_name, caption)
    native_marker = f"figures/native/figure-{figure_number:02d}.tex"
    for index in range(len(lines)):
        if _replace_landscape_figure_line(lines, index, replacement, input_name, native_marker):
            return True
        if _replace_landscape_tikz_block(lines, index, replacement, input_name, native_marker):
            return True
    return False


def _replace_coordinate_figure(
    lines: MutableSequence[str], caption_marker: str, macro_line: str, has_geometry: bool
) -> bool:
    if not has_geometry:
        return False
    caption_index = next(
        (index for index, line in enumerate(lines) if caption_marker in line), None
    )
    if caption_index is None:
        return False
    image_index = next(
        (
            candidate
            for candidate in range(caption_index - 1, -1, -1)
            if "\\HLAFigureImageAt{" in lines[candidate]
        ),
        None,
    )
    if image_index is None:
        lines.insert(caption_index, macro_line)
    else:
        lines[image_index] = macro_line
    return True


def _native_figure_line_replacement(
    line: str,
    native_argument: str,
    generated_argument: str,
    input_name: str,
    figure_number: int,
    caption: str | None,
) -> tuple[str, str | None] | None:
    if native_argument not in line:
        return None
    stdnative_match = re.search(
        rf"\\stdnativefigure(?:\[([^\]]+)\])?{re.escape(native_argument)}", line
    )
    if stdnative_match and caption:
        width = stdnative_match.group(1) or r"\linewidth"
        figure_caption = tex_escape(f"Figure {figure_number}---{caption}")
        return (
            line.replace(
                stdnative_match.group(0),
                rf"\stdsemanticfigure[{width}]{{output/semantic/{input_name}}}{{{figure_caption}}}",
            ),
            None,
        )
    if not input_name.endswith(".pdf"):
        return line.replace(native_argument, generated_argument), None
    updated = line.replace(
        f"\\input{native_argument}", f"\\includegraphics{generated_argument}"
    ).replace(f"\\input{generated_argument}", f"\\includegraphics{generated_argument}")
    if updated == line:
        updated = line.replace(native_argument, generated_argument)
    caption_line = None
    if caption:
        figure_caption = tex_escape(f"Figure {figure_number}---{caption}")
        caption_line = rf"\stdsemanticcaption{{{figure_caption}}}"
    return updated, caption_line


def _replace_native_figure_argument(
    lines: MutableSequence[str], figure_number: int, input_name: str, caption: str | None
) -> bool:
    native_argument = f"{{figures/native/figure-{figure_number:02d}.tex}}"
    generated_argument = f"{{output/semantic/{input_name}}}"
    for index, line in enumerate(lines):
        result = _native_figure_line_replacement(
            line, native_argument, generated_argument, input_name, figure_number, caption
        )
        if result is None:
            continue
        lines[index], caption_line = result
        if caption_line is not None:
            lines.insert(index + 1, caption_line)
        return True
    return False


def _replace_native_input_path(
    lines: MutableSequence[str], figure_number: int, input_name: str, caption: str | None
) -> bool:
    native_input = re.compile(rf"(\\input\{{)figures/native/figure-{figure_number:02d}\.tex(\}})")
    for index, line in enumerate(lines):
        if not native_input.search(line):
            continue
        lines[index] = native_input.sub(rf"\1output/semantic/{input_name}\2", line)
        if input_name.endswith(".pdf"):
            lines[index] = lines[index].replace(
                f"\\input{{output/semantic/{input_name}}}",
                f"\\includegraphics{{output/semantic/{input_name}}}",
            )
            if caption:
                figure_caption = tex_escape(f"Figure {figure_number}---{caption}")
                lines.insert(index + 1, rf"\stdsemanticcaption{{{figure_caption}}}")
        return True
    return False


def _replace_unique_figure_image(
    lines: MutableSequence[str], macro_line: str, has_geometry: bool
) -> bool:
    image_indices = [index for index, line in enumerate(lines) if "\\HLAFigureImageAt{" in line]
    if not has_geometry or len(image_indices) != 1:
        return False
    lines[image_indices[0]] = macro_line
    return True


def _replace_visible_figure_marker(
    lines: MutableSequence[str], marker: str, macro_line: str, body: str
) -> tuple[bool, str]:
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
                    for candidate, value in enumerate(lines)
                    if "\\HLAFigureImageAt{" in value
                ),
                None,
            )
            if image_index is not None:
                lines[image_index] = macro_line
            return True, "\n".join(lines) if image_index is not None else body
        image_index = next(
            (
                candidate
                for candidate in range(caption_start - 1, -1, -1)
                if "\\HLAFigureImageAt{" in lines[candidate]
            ),
            None,
        )
        if image_index is None:
            lines.insert(caption_start, macro_line)
        else:
            lines[image_index] = macro_line
        return True, "\n".join(lines)
    return False, body


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
    macro_line = _diagram_embed_macro(input_name, geometry).rstrip("\n")
    lines = body.splitlines()
    if _replace_landscape_asset(lines, figure_number, input_name, caption, landscape):
        return "\n".join(lines)
    caption_marker = f"\\HLAFigureCaptionAt{{{figure_number}}}"
    if _replace_coordinate_figure(lines, caption_marker, macro_line, geometry is not None):
        return "\n".join(lines)
    if _replace_native_figure_argument(lines, figure_number, input_name, caption):
        return "\n".join(lines)
    if _replace_native_input_path(lines, figure_number, input_name, caption):
        return "\n".join(lines)
    if _replace_unique_figure_image(lines, macro_line, geometry is not None):
        return "\n".join(lines)
    replaced, result = _replace_visible_figure_marker(
        lines, f"Figure {figure_number}", macro_line, body
    )
    return result if replaced else body


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
                or lines[after].strip() == r"\par"
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

    macro = (
        "\\HLALandscapeFigurePDFPage" if input_name.endswith(".pdf") else "\\HLALandscapeFigurePage"
    )
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
