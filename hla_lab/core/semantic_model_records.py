"""Load source headings, attachments, requirements, and authored records."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    Mapping,
    MutableMapping,
    Sequence,
)
from pathlib import (
    Path,
)

from hla_lab.core.navigation_manifest import SourceNavigationManifest
from hla_lab.core.parsing import (
    line_number,
)
from hla_lab.core.semantic_diagram_types import SemanticDiagramFileEnvelope
from hla_lab.core.semantic_model_authored import _load_authored_content_blocks
from hla_lab.core.semantic_model_resources import (
    _document_resources,
    _files,
    _source,
    _source_key,
    _source_order,
)
from hla_lab.core.semantic_model_tables import (
    _authored_layout_units,
)
from hla_lab.core.semantic_text import (
    _command_events,
    _latex_text,
    _machine_statement,
)
from hla_lab.core.semantic_types import (
    Annex,
    AnnexStatus,
    CommandEvent,
    ContentBlock,
    DiagramSurface,
    DiagramSurfaceFile,
    Example,
    Figure,
    GraphDiagram,
    GraphDiagramFile,
    HeadingEvent,
    HeadingParts,
    Note,
    NoteKind,
    Reference,
    Requirement,
    SequenceDiagram,
    SequenceDiagramFile,
    SourceRef,
    StateMachine,
    StateMachineFile,
)
from hla_lab.core.source_adapter import (
    LatexSourceProfile,
)


def _record_id(prefix: str, root: Path, path: Path, text: str, offset: int, ordinal: int) -> str:
    relative = path.relative_to(root).with_suffix("").as_posix()
    slug = re.sub(r"[^a-z0-9]+", "-", relative.casefold()).strip("-")
    return f"{prefix}-{slug}-l{line_number(text, offset)}-{ordinal}"


def _heading_parts(args: Sequence[str], source: LatexSourceProfile) -> tuple[str, str] | None:
    """Return a normalized clause ID and title from either heading shape."""
    if not args:
        return None
    if len(args) >= 2 and args[0].strip().startswith("clause-"):
        return args[0].strip(), _latex_text(args[1], source)
    last_argument = next(iter(reversed(args)), None)
    if last_argument is None:
        return None
    value = _latex_text(last_argument, source)
    direct_match = re.match(
        r"(?P<number>[A-Za-z](?:\.\d+)*|\d+(?:\.\d+)*)\.\s+(?P<title>.+)",
        value,
    )
    if direct_match:
        number = direct_match.group("number")
        return f"clause-{number}", value.strip()
    match = re.match(r"(?P<number>[A-Za-z](?:\.\d+)*|\d+(?:\.\d+)*)\s*(?P<title>.*)", value)
    if not match:
        return None
    number = match.group("number")
    title = match.group("title").strip() or value
    return f"clause-{number}", title


def _store_heading_event(
    events: MutableMapping[int, HeadingEvent],
    root: Path,
    path: Path,
    text: str,
    offset: int,
    end_offset: int,
    parts: HeadingParts | None,
    *,
    overwrite: bool,
) -> None:
    if parts is None or (not overwrite and offset in events):
        return
    identifier, title = parts
    events[offset] = (offset, identifier, title, _source(root, path, text, offset, end_offset))


def _collect_clause_command_headings(
    events: MutableMapping[int, HeadingEvent],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> None:
    for name in source.clause_headings:
        for offset, args, end_offset in _command_events(text, name, 2):
            _store_heading_event(
                events,
                root,
                path,
                text,
                offset,
                end_offset,
                _heading_parts(args, source),
                overwrite=True,
            )
        for offset, args, end_offset in _command_events(text, name, 1):
            _store_heading_event(
                events,
                root,
                path,
                text,
                offset,
                end_offset,
                _heading_parts(args, source),
                overwrite=False,
            )


def _collect_hierarchy_heading_commands(
    events: MutableMapping[int, HeadingEvent],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> None:
    for name, count, title_index in source.hierarchy_heading_commands:
        for offset, args, end_offset in _command_events(text, name, count):
            _store_heading_event(
                events,
                root,
                path,
                text,
                offset,
                end_offset,
                _heading_parts((args[title_index],), source),
                overwrite=False,
            )


def _collect_hierarchy_id_commands(
    events: MutableMapping[int, HeadingEvent],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> None:
    for name, identifier_index, title_index in source.hierarchy_id_commands:
        count = max(identifier_index, title_index) + 1
        for offset, args, end_offset in _command_events(text, name, count):
            number = args[identifier_index].strip()
            if not re.fullmatch(r"[A-Za-z](?:\.\d+)*|\d+(?:\.\d+)*", number):
                continue
            identifier = f"clause-{number}"
            title = f"{number} {_latex_text(args[title_index], source)}"
            _store_heading_event(
                events,
                root,
                path,
                text,
                offset,
                end_offset,
                (identifier, title),
                overwrite=True,
            )


def _fixed_text_heading_parts(
    raw_value: str, source: LatexSourceProfile, style: str = ""
) -> tuple[str, str] | None:
    if r"\textbf" not in raw_value and r"\bfseries" not in style:
        return None
    value = _latex_text(raw_value, source).replace("%", "").strip()
    match = re.match(
        r"(?P<number>[A-Za-z]\.\d+(?:\.\d+)*|\d+(?:\.\d+)*)(?:\.)?\s+\S.+",
        value,
    )
    if not match:
        return None
    return f"clause-{match.group('number')}", value


def _collect_fixed_text_headings(
    events: MutableMapping[int, HeadingEvent],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> None:
    for offset, args, end_offset in _command_events(text, source.fixed_text_block, 7):
        parts = _fixed_text_heading_parts(args[-1], source, args[3])
        if parts is None and r"\textbf" in args[-1]:
            annex = re.fullmatch(
                r"Annex\s+([A-Za-z])", _latex_text(args[-1], source).strip("% \n")
            )
            if annex is not None:
                letter = annex.group(1).upper()
                parts = (f"clause-{letter}", f"Annex {letter}")
        if parts is not None:
            _store_heading_event(
                events, root, path, text, offset, end_offset, parts, overwrite=False
            )


def _collect_annex_headings(
    events: MutableMapping[int, HeadingEvent],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> None:
    for offset, args, end_offset in _command_events(text, source.annex_heading, 1):
        value = _latex_text(args[0], source)
        match = re.fullmatch(r"Annex\s+([A-Za-z])", value)
        if match is None or offset in events:
            continue
        identifier = f"clause-{match.group(1).upper()}"
        _store_heading_event(
            events,
            root,
            path,
            text,
            offset,
            end_offset,
            (identifier, value),
            overwrite=True,
        )


def _collect_content_marker_headings(
    events: MutableMapping[int, HeadingEvent],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> None:
    for offset, args, end_offset in _command_events(text, source.content_marker, 1):
        identifier = args[0].strip()
        if not identifier.startswith("clause-") or offset in events:
            continue
        number = identifier.removeprefix("clause-")
        _store_heading_event(
            events,
            root,
            path,
            text,
            offset,
            end_offset,
            (identifier, f"Content marker {number}"),
            overwrite=True,
        )


def _hierarchy_headings(
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
    *,
    include_navigation: bool = True,
) -> tuple[tuple[int, str, str, SourceRef], ...]:
    events: dict[int, tuple[int, str, str, SourceRef]] = {}
    _collect_clause_command_headings(events, root, path, text, source)
    _collect_hierarchy_heading_commands(events, root, path, text, source)
    if include_navigation:
        _collect_hierarchy_id_commands(events, root, path, text, source)
    _collect_fixed_text_headings(events, root, path, text, source)
    _collect_annex_headings(events, root, path, text, source)
    _collect_content_marker_headings(events, root, path, text, source)
    return tuple(events[offset] for offset in sorted(events))


def _nearest_heading(headings: Sequence[HeadingEvent], offset: int) -> str | None:
    prior = [item for item in headings if item[0] <= offset]
    return prior[-1][1] if prior else None


def _heading_context_by_file(
    root: Path, source: LatexSourceProfile
) -> dict[Path, tuple[tuple[int, str, str, SourceRef], ...]]:
    """Carry the last semantic heading across the document include order.

    A LaTeX page fragment is often included after its heading was declared in
    a neighboring fragment.  The include graph, rather than the fragment
    filename, is therefore the ownership boundary for semantic records.
    The synthetic ``-1`` entry keeps that context available to all event
    loaders without changing source offsets in the current fragment.
    """
    context: dict[Path, tuple[tuple[int, str, str, SourceRef], ...]] = {}
    prior: tuple[int, str, str, SourceRef] | None = None
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        local_events = list(_hierarchy_headings(root, path, text, source))
        for offset, args, end_offset in _command_events(text, source.pdf_bookmark, 2):
            bookmark = args[1]
            if not bookmark.startswith("bookmark:clause:"):
                continue
            identifier = f"clause-{bookmark.removeprefix('bookmark:clause:')}"
            local_events.append(
                (
                    offset,
                    identifier,
                    _latex_text(args[0], source),
                    _source(root, path, text, offset, end_offset),
                )
            )
        local = tuple(sorted(local_events, key=lambda item: item[0]))
        effective = ((-1, prior[1], prior[2], prior[3]), *local) if prior else local
        context[path] = tuple(effective)
        if local:
            prior = local[-1]
    return context


def _load_references(root: Path, source: LatexSourceProfile) -> tuple[Reference, ...]:
    records: list[Reference] = []
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path, text in _authored_layout_units(root):
        headings = tuple(
            sorted(
                (*heading_context.get(path, ()), *_hierarchy_headings(root, path, text, source)),
                key=lambda item: item[0],
            )
        )
        for _ordinal, (offset, args, end_offset) in enumerate(
            _command_events(text, source.bibliography_entry, 3), start=1
        ):
            records.append(
                Reference(
                    id=args[0],
                    label=_latex_text(args[1], source),
                    text=_latex_text(args[2], source),
                    kind="bibliographic",
                    clause_id=_nearest_heading(headings, offset),
                    source=_source(root, path, text, offset, end_offset),
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))


def _load_notes(root: Path, source: LatexSourceProfile) -> tuple[Note, ...]:
    records: list[Note] = []
    seen: set[tuple[str, int, int | None, NoteKind, str]] = set()
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path, text in _authored_layout_units(root):
        events: list[tuple[int, NoteKind, tuple[str, ...], int]] = []
        events.extend(
            (offset, "informative", args, end_offset)
            for offset, args, end_offset in _command_events(text, source.note_block, 1)
        )
        for name in source.definition_note_commands:
            events.extend(
                (offset, "definition", args, end_offset)
                for offset, args, end_offset in _command_events(text, name, 1)
            )
        events.extend(
            (offset, "definition", args, end_offset)
            for offset, args, end_offset in _command_events(text, source.definition_note_at, 3)
        )
        events.extend(
            (offset, "footnote", args, end_offset)
            for offset, args, end_offset in _command_events(text, source.footnote_text, 1)
        )
        for name in getattr(source, "additional_note_commands", ()):
            events.extend(
                (offset, "footnote", args, end_offset)
                for offset, args, end_offset in _command_events(text, name, 2)
            )
        headings = tuple(
            sorted(
                (*heading_context.get(path, ()), *_hierarchy_headings(root, path, text, source)),
                key=lambda item: item[0],
            )
        )
        for ordinal, (offset, kind, args, end_offset) in enumerate(sorted(events), start=1):
            payload = args[-1]
            note = Note(
                id=_record_id("note", root, path, text, offset, ordinal),
                text=_latex_text(payload, source),
                kind=kind,  # type: ignore[arg-type]
                owner_id=_nearest_heading(headings, offset),
                source=_source(root, path, text, offset, end_offset),
            )
            source_key = (
                note.source.path,
                note.source.line,
                note.source.end_line,
                note.kind,
                note.text,
            )
            if source_key in seen:
                continue
            seen.add(source_key)
            records.append(note)
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))


def _load_figures(root: Path, source: LatexSourceProfile) -> tuple[Figure, ...]:
    records: list[Figure] = []
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    for path, text in _authored_layout_units(root):
        images = _command_events(text, source.figure_image, 5)
        captions = _command_events(text, source.figure_caption, 3)
        anchors = _command_events(text, source.figure_anchor, 1)
        headings = tuple(
            sorted(
                (*heading_context.get(path, ()), *_hierarchy_headings(root, path, text, source)),
                key=lambda item: item[0],
            )
        )
        for index, (offset, image_args, end_offset) in enumerate(images):
            number = str(index + 1)
            prior_anchors = [item for item in anchors if item[0] <= offset]
            if prior_anchors:
                number = _latex_text(prior_anchors[-1][1][0], source)
            if index < len(captions):
                caption_offset, caption_args, _ = captions[index]
                number = _latex_text(caption_args[0], source)
                caption = _latex_text(caption_args[2], source)
                if caption_offset < offset:
                    caption = ""
            else:
                caption = ""
            records.append(
                Figure(
                    id=f"figure-{number}",
                    number=number,
                    caption=caption,
                    image=_latex_text(image_args[4], source),
                    clause_id=_nearest_heading(headings, offset),
                    source=_source(root, path, text, offset, end_offset),
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))


def _load_examples(root: Path, source: LatexSourceProfile) -> tuple[Example, ...]:
    records: list[Example] = []
    source_order = _source_order(root)
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        for _offset, identifier, title, heading_source in _hierarchy_headings(
            root, path, text, source
        ):
            if not title.casefold().endswith("example"):
                continue
            number = identifier.removeprefix("clause-")
            records.append(
                Example(
                    id=f"example-{number}",
                    number=number,
                    title=title,
                    clause_id=identifier,
                    source=heading_source,
                )
            )
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))


def _annex_status(value: str) -> AnnexStatus:
    normalized = value.casefold()
    if normalized == "normative":
        return "normative"
    if normalized == "informative":
        return "informative"
    return "unknown"


def _store_annex_descriptor(
    records: MutableMapping[str, Annex], descriptor: str, source_ref: SourceRef
) -> None:
    match = re.match(
        r"Annex\s+([A-Za-z])\s+\((normative|informative)\)\s*(.*)",
        descriptor,
        re.IGNORECASE,
    )
    if match is None:
        return
    letter, status, title = match.groups()
    identifier = f"annex-{letter.casefold()}"
    records.setdefault(
        identifier,
        Annex(
            id=identifier,
            letter=letter.upper(),
            title=title.strip() or f"Annex {letter.upper()}",
            status=_annex_status(status),
            source=source_ref,
        ),
    )


def _collect_source_annex_headings(
    records: MutableMapping[str, Annex],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
    headings: Sequence[CommandEvent],
    statuses: Sequence[CommandEvent],
    titles: Sequence[CommandEvent],
) -> None:
    for offset, heading_args, end_offset in headings:
        match = re.search(r"Annex\s+([A-Za-z])", _latex_text(heading_args[0], source))
        if match is None:
            continue
        letter = match.group(1).upper()
        next_headings = [item[0] for item in headings if item[0] > offset]
        limit = min(next_headings) if next_headings else len(text)
        status_value = next(
            (
                _latex_text(item[1][0], source).strip("() ").casefold()
                for item in statuses
                if offset < item[0] < limit
            ),
            "unknown",
        )
        title = next(
            (_latex_text(item[1][0], source) for item in titles if offset < item[0] < limit),
            f"Annex {letter}",
        )
        identifier = f"annex-{letter.casefold()}"
        records.setdefault(
            identifier,
            Annex(
                id=identifier,
                letter=letter,
                title=title,
                status=_annex_status(status_value),
                source=_source(root, path, text, offset, end_offset),
            ),
        )


def _collect_source_annex_descriptors(
    records: MutableMapping[str, Annex],
    root: Path,
    path: Path,
    text: str,
    source: LatexSourceProfile,
) -> None:
    for offset, args, end_offset in _command_events(text, source.toc_line_at, 7):
        descriptor = _latex_text(args[4], source)
        _store_annex_descriptor(records, descriptor, _source(root, path, text, offset, end_offset))
    for offset, args, end_offset in _command_events(text, source.annex_bookmark, 1):
        descriptor = _latex_text(args[0], source)
        _store_annex_descriptor(records, descriptor, _source(root, path, text, offset, end_offset))


def _collect_navigation_annexes(records: MutableMapping[str, Annex], root: Path) -> None:
    navigation = _document_resources(root).canonical_file("source-navigation.json")
    if not navigation.is_file():
        return
    manifest = SourceNavigationManifest.model_validate_json(navigation.read_text(encoding="utf-8"))
    navigation_source = SourceRef(path=navigation.relative_to(root).as_posix(), line=1)
    for entry in manifest.outline:
        match entry:
            case (_, label) | (_, label, _):
                _store_annex_descriptor(records, str(label).strip(), navigation_source)


def _load_annexes(root: Path, source: LatexSourceProfile) -> tuple[Annex, ...]:
    records: dict[str, Annex] = {}
    source_order = _source_order(root)
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        headings = _command_events(text, source.annex_heading, 1)
        statuses = _command_events(text, source.annex_status, 1)
        titles = _command_events(text, source.annex_title, 1)
        _collect_source_annex_headings(
            records, root, path, text, source, headings, statuses, titles
        )
        _collect_source_annex_descriptors(records, root, path, text, source)
    _collect_navigation_annexes(records, root)
    return tuple(sorted(records.values(), key=lambda item: _source_key(item, source_order)))


def _requirement_candidate_units(
    root: Path,
    source: LatexSourceProfile,
    heading_context: Mapping[Path, Sequence[HeadingEvent]],
    authored_blocks: Sequence[ContentBlock],
) -> list[tuple[Path, str, tuple[tuple[int, str, str, SourceRef], ...]]]:
    authored_by_path = {
        item.source.path: item for item in authored_blocks if item.layout_body is not None
    }
    adapter_paths = {
        relative
        for relative in authored_by_path
        if (root / relative).is_file()
        and "\\input{output/semantic/content-block-"
        in (root / relative).read_text(encoding="utf-8")
    }
    units: list[tuple[Path, str, tuple[tuple[int, str, str, SourceRef], ...]]] = []
    for path in _files(root):
        relative = path.relative_to(root).as_posix()
        if "frontmatter" in relative or "generated" in relative or relative in adapter_paths:
            continue
        units.append((path, path.read_text(encoding="utf-8"), tuple(heading_context[path])))
    prior_heading: HeadingEvent | None = None
    for block in sorted(authored_blocks, key=lambda item: item.sequence):
        if block.layout_body is None:
            continue
        if "frontmatter" in block.source.path or "generated" in block.source.path:
            continue
        virtual_path = root / block.source.path
        local_headings = list(
            _hierarchy_headings(
                root, virtual_path, block.layout_body, source, include_navigation=False
            )
        )
        inherited = prior_heading
        if inherited is not None:
            local_headings.insert(
                0,
                (-1, inherited[1], inherited[2], inherited[3]),
            )
        elif block.clause_id is not None and not any(
            item[1] == block.clause_id for item in local_headings
        ):
            local_headings.insert(
                0,
                (
                    -1,
                    block.clause_id,
                    block.clause_id.removeprefix("clause-"),
                    block.source,
                ),
            )
        units.append((virtual_path, block.layout_body, tuple(local_headings)))
        if local_headings:
            prior_heading = local_headings[-1]
    return units


def _extend_fixed_candidate_statement(
    body: str,
    statement: str,
    start_offset: int,
    end_offset: int,
    args: Sequence[str],
    fixed_index: int | None,
    fixed_events: Sequence[CommandEvent],
    source: LatexSourceProfile,
) -> tuple[str, str, int, int, tuple[int, ...]]:
    if fixed_index is None or not re.search(r"\bshall\b", statement, re.IGNORECASE):
        return body, statement, start_offset, end_offset, ()
    # A physical PDF line can start in the middle of a sentence. Walk back
    # through the same paragraph before extracting a requirement from the
    # line containing "shall". The earlier lines carry the subject or guard.
    previous_index = fixed_index
    while previous_index > 0:
        previous_offset, previous_args, _previous_end = fixed_events[previous_index - 1]
        current_y = float(fixed_events[previous_index][1][1])
        previous_y = float(previous_args[1])
        previous_text = _machine_statement(previous_args[-1], source).strip()
        if (
            current_y < previous_y
            or current_y - previous_y > 18.0
            or not previous_text
            or re.search(r"[.!?]\s*$", previous_text)
            or re.search(r"\bshall\b", previous_text, re.IGNORECASE)
            or "\\bfseries" in previous_args[3]
        ):
            break
        body = f"{previous_args[-1]} {body}"
        start_offset = previous_offset
        previous_index -= 1
    statement = _machine_statement(body, source)
    continuation = fixed_index
    previous_y = float(args[1])
    consumed_offsets: list[int] = []
    while continuation + 1 < len(fixed_events):
        without_marker = statement.rstrip().rstrip("%").rstrip()
        if without_marker.endswith((".", ":", ";", "?", "!", ")")):
            break
        continuation += 1
        next_offset, next_args, next_end_offset = fixed_events[continuation]
        next_y = float(next_args[1])
        if next_y - previous_y > 18.0:
            break
        consumed_offsets.append(next_offset)
        body = f"{body} {next_args[-1]}"
        statement = _machine_statement(body, source)
        end_offset = next_end_offset
        previous_y = next_y
    statement = re.sub(r"\s*%", " ", statement)
    statement = re.sub(r"\s+", " ", statement).strip()
    return body, statement, start_offset, end_offset, tuple(consumed_offsets)


def _candidate_requirement_for_event(
    root: Path,
    path: Path,
    text: str,
    headings: Sequence[HeadingEvent],
    source: LatexSourceProfile,
    relative: str,
    ordinal: int,
    event: CommandEvent,
    fixed_event_index: Mapping[int, int],
    fixed_events: Sequence[CommandEvent],
) -> tuple[Requirement | None, tuple[int, ...]]:
    offset, args, end_offset = event
    body = args[-1]
    statement = _machine_statement(body, source)
    body, statement, source_start_offset, end_offset, consumed = _extend_fixed_candidate_statement(
        body,
        statement,
        offset,
        end_offset,
        args,
        fixed_event_index.get(offset),
        fixed_events,
        source,
    )
    if not re.search(r"\bshall\b", statement, re.IGNORECASE):
        return None, consumed
    clause_id = _nearest_heading(headings, offset)
    clause = clause_id.removeprefix("clause-") if clause_id else None
    requirement = Requirement(
        id=_record_id("requirement-candidate", root, path, text, offset, ordinal),
        title=f"Normative candidate at {relative}:{line_number(text, offset)}",
        statement=statement,
        kind="detailed",
        clause=clause,
        machine_statement=statement,
        extraction="candidate",
        source=_source(root, path, text, source_start_offset, end_offset),
    )
    return requirement, consumed


def _requirements_from_candidate_unit(
    root: Path,
    path: Path,
    text: str,
    headings: Sequence[HeadingEvent],
    source: LatexSourceProfile,
) -> list[Requirement]:
    fixed_events = sorted(_command_events(text, source.fixed_text_block, 7))
    fixed_event_index = {offset: index for index, (offset, _, _) in enumerate(fixed_events)}
    events: list[tuple[int, tuple[str, ...], int]] = []
    events.extend(fixed_events)
    events.extend(_command_events(text, source.clause_paragraph, 1))
    events.extend(_command_events(text, source.clause_labeled_item, 2))
    records: list[Requirement] = []
    consumed_fixed_offsets: set[int] = set()
    relative = path.relative_to(root).as_posix()
    for ordinal, event in enumerate(sorted(events), start=1):
        offset = event[0]
        if offset in consumed_fixed_offsets:
            continue
        requirement, consumed = _candidate_requirement_for_event(
            root,
            path,
            text,
            headings,
            source,
            relative,
            ordinal,
            event,
            fixed_event_index,
            fixed_events,
        )
        consumed_fixed_offsets.update(consumed)
        if requirement is not None:
            records.append(requirement)
    return records


def _load_requirement_candidates(root: Path, source: LatexSourceProfile) -> tuple[Requirement, ...]:
    """Extract reviewable normative candidates from non-semantic page sources."""
    source_order = _source_order(root)
    heading_context = _heading_context_by_file(root, source)
    authored_blocks = _load_authored_content_blocks(root)
    units = _requirement_candidate_units(root, source, heading_context, authored_blocks)
    records: list[Requirement] = []
    seen_units: set[tuple[str, str]] = set()
    for path, text, headings in units:
        unit_key = (path.relative_to(root).as_posix(), text)
        if unit_key in seen_units:
            continue
        seen_units.add(unit_key)
        records.extend(_requirements_from_candidate_unit(root, path, text, headings, source))
    return tuple(sorted(records, key=lambda item: _source_key(item, source_order)))


def _load_state_machines(root: Path) -> tuple[StateMachine, ...]:
    semantic_root = _document_resources(root).semantic
    if not semantic_root.exists():
        return ()
    machines: list[StateMachine] = []
    for path in sorted(semantic_root.glob("*.json")):
        source = path.read_text(encoding="utf-8")
        envelope = SemanticDiagramFileEnvelope.model_validate_json(source)
        if "state_machines" not in envelope.model_fields_set:
            continue
        if envelope.schema_version is None or envelope.state_machines is None:
            raise ValueError(f"{path}: state-machine model needs schema_version and state_machines")
        payload = StateMachineFile.model_validate_json(source)
        machines.extend(payload.state_machines)
    return tuple(machines)


def _load_sequence_diagrams(root: Path) -> tuple[SequenceDiagram, ...]:
    """Load authored sequence diagrams from the semantic source directory."""
    semantic_root = _document_resources(root).semantic
    if not semantic_root.exists():
        return ()
    diagrams: list[SequenceDiagram] = []
    for path in sorted(semantic_root.glob("*.json")):
        source = path.read_text(encoding="utf-8")
        envelope = SemanticDiagramFileEnvelope.model_validate_json(source)
        if "sequence_diagrams" not in envelope.model_fields_set:
            continue
        if envelope.schema_version is None or envelope.sequence_diagrams is None:
            raise ValueError(f"{path}: sequence diagram model needs schema_version and records")
        payload = SequenceDiagramFile.model_validate_json(source)
        diagrams.extend(payload.sequence_diagrams)
    return tuple(diagrams)


def _load_graph_diagrams(root: Path) -> tuple[GraphDiagram, ...]:
    """Load authored generic graph diagrams from the semantic source directory."""
    semantic_root = _document_resources(root).semantic
    if not semantic_root.exists():
        return ()
    diagrams: list[GraphDiagram] = []
    for path in sorted(semantic_root.glob("*.json")):
        source = path.read_text(encoding="utf-8")
        envelope = SemanticDiagramFileEnvelope.model_validate_json(source)
        if "graph_diagrams" not in envelope.model_fields_set:
            continue
        if envelope.schema_version is None or envelope.graph_diagrams is None:
            raise ValueError(f"{path}: graph diagram model needs schema_version and records")
        payload = GraphDiagramFile.model_validate_json(source)
        diagrams.extend(payload.graph_diagrams)
    return tuple(diagrams)


def _load_diagram_surfaces(root: Path) -> tuple[DiagramSurface, ...]:
    """Load the explicit figure/artwork classification for this document."""
    path = _document_resources(root).semantic_file("diagram-surfaces.json")
    if not path.is_file():
        return ()
    payload = DiagramSurfaceFile.model_validate_json(path.read_text(encoding="utf-8"))
    return payload.surfaces
