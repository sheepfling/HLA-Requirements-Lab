"""Extract typed content elements from the faithful IEEE 1516 page adapters."""

from __future__ import annotations

import argparse
import re
from collections.abc import Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from pydantic import ConfigDict

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.parsing import try_balanced_group
from hla_lab.core.semantic_model import (
    ContentBlock,
    ContentBlockFile,
    ContentElement,
    ContentElementFile,
    SourceRef,
    load_document_model,
)
from hla_lab.paths import DocumentResources, repository_root, resources


class _MutableContentBlock(ContentBlock):
    """Mutable migration view derived from the canonical content block model."""

    model_config = ConfigDict(frozen=False, validate_assignment=True)


@dataclass(frozen=True, slots=True)
class Event:
    name: str
    start: int
    end: int
    args: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Spec:
    kind: str
    text: str
    offset: int
    clause_id: str | None = None
    parent_id: str | None = None
    record_ids: tuple[str, ...] = ()


LIST_ENVIRONMENTS = frozenset(
    {
        "hlaoverviewservicelist",
        "hlaacronymrows",
        "hlasummaryrules",
    }
)

HEADING_COMMANDS = frozenset(
    {
        "HLAClauseHeading",
        "HLASubclauseHeading",
        "HLADetailedRuleHeading",
        "HLARationaleHeading",
        "HLAFrontHeading",
        "HLAFrontHeadingAdjusted",
        "HLAFrontMajorHeadingAdjusted",
        "HLAMinorClauseHeading",
    }
)


def _events(text: str, names: AbstractSet[str]) -> tuple[Event, ...]:
    pattern = re.compile(r"\\(?P<name>[A-Za-z@]+)")
    result: list[Event] = []
    for match in pattern.finditer(text):
        name = match.group("name")
        if name not in names:
            continue
        cursor = _event_argument_start(text, match.end())
        if cursor is None:
            continue
        args, end = _event_arguments(text, cursor)
        result.append(Event(name, match.start(), end, args))
    return tuple(result)


def _event_argument_start(text: str, cursor: int) -> int | None:
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if cursor < len(text) and text[cursor] == "*":
        cursor += 1
    if cursor < len(text) and text[cursor] == "[":
        optional = try_balanced_group(text, cursor, "[", "]")
        if optional is None:
            return None
        cursor = optional[1]
    return cursor


def _event_arguments(text: str, cursor: int) -> tuple[tuple[str, ...], int]:
    arguments: list[str] = []
    while cursor < len(text):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            break
        value = try_balanced_group(text, cursor)
        if value is None:
            break
        arguments.append(value[0])
        cursor = value[1]
    return tuple(arguments), cursor


def _environments(text: str) -> tuple[tuple[str, int, int, str], ...]:
    result: list[tuple[str, int, int, str]] = []
    for match in re.finditer(r"\\begin\{([^}]+)\}", text):
        name = match.group(1)
        if name not in LIST_ENVIRONMENTS:
            continue
        end_match = re.search(rf"\\end\{{{re.escape(name)}\}}", text[match.end() :])
        if end_match is None:
            continue
        body_start = match.end()
        body_end = match.end() + end_match.start()
        result.append(
            (name, match.start(), match.end() + end_match.end(), text[body_start:body_end])
        )
    return tuple(result)


def _strip_commands(text: str) -> str:
    value = text
    value = re.sub(r"%[^\n]*", " ", value)
    value = value.replace(r"\&", "&").replace(r"\#", "#")
    value = value.replace(r"\textcopyright{}", "©")
    value = value.replace(r"\HLAStandardMark", "")
    value = value.replace("---", "—")
    value = re.sub(r"\\(?:linebreak|newline|\\)", " ", value)
    value = re.sub(r"\\(?:par)\b", "\n\n", value)
    wrappers = {
        "textit",
        "textbf",
        "texttt",
        "textrm",
        "textsf",
        "emph",
        "textcolor",
        "HLAService",
        "HLAFrontPageThreeLine",
        "makebox",
        "mbox",
        "hbox",
        "textsuperscript",
        "HLAClauseParagraph",
    }
    for _ in range(5):
        before = value
        value = re.sub(
            r"\\(?:" + "|".join(sorted(wrappers)) + r")\s*(?:\[[^]]*\])?\{([^{}]*)\}",
            r" \1 ",
            value,
        )
        if value == before:
            break
    value = re.sub(
        r"\\resizebox(?:\[[^]]*\])?\s*\{[^{}]*\}\{[^{}]*\}\{([^{}]*)\}",
        r" \1 ",
        value,
    )
    value = re.sub(
        r"\\(?:vspace|hspace|fontsize|addfontfeatures)\*?\s*\{[^{}]*\}(?:\{[^{}]*\})?",
        " ",
        value,
    )
    value = re.sub(
        r"\\(?:selectfont|relax|hbadness|hfuzz|clearpage|begingroup|endgroup)\b(?:\s*=\s*[^\s]+)?",
        " ",
        value,
    )
    value = value.replace(r"\space", " ").replace(r"\texttrademark", "™")
    value = re.sub(r"\\[A-Za-z@]+", " ", value)
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\{([^{}]*)\}", r" \1 ", value)
    value = re.sub(
        r"\b(?:xshift|yshift|width|height|line|FakeStretch)\s*=\s*[-+.\d]+pt", " ", value
    )
    value = re.sub(r"\b[-+]?\d+(?:\.\d+)?pt\b", " ", value)
    value = re.sub(r"\b[-+]?\d+(?:\.\d+)?bp\b", " ", value)
    value = re.sub(
        r"\b(?:remember|picture|overlay|current|page|north|south|east|west|anchor|"
        r"inner|outer|sep|align|justify|selectfont|HLATitlePage|HLAPublicationPage|"
        r"HLASemanticPage|flushright)\b",
        " ",
        value,
    )
    value = re.sub(r"#\d+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip(" {}\n\t")


def _paragraphs(raw: str) -> tuple[str, ...]:
    values: list[str] = []
    for part in re.split(r"\n\s*\n", raw):
        value = _strip_commands(part)
        if value and len(value) >= 12:
            values.append(value)
    return tuple(values)


def _source_for(block: _MutableContentBlock, body: str, offset: int) -> SourceRef:
    line = block.source.line + body.count("\n", 0, offset)
    return SourceRef(
        path=block.source.path,
        line=line,
        end_line=max(line, line + body[offset:].count("\n")),
    )


def _clause_positions(body: str, clause_ids: AbstractSet[str]) -> tuple[tuple[int, str], ...]:
    positions: list[tuple[int, str]] = []
    for event in _events(
        body,
        {"HLAContentMarker", "HLAClauseHeading", "HLASubclauseHeading", "HLAAnchor"},
    ):
        if not event.args:
            continue
        identifier = event.args[0].strip()
        if event.name == "HLAAnchor" and identifier.startswith("clause:"):
            identifier = f"clause-{identifier.removeprefix('clause:')}"
        if identifier in clause_ids:
            positions.append((event.start, identifier))
    return tuple(sorted(positions))


def _clause_at(
    block_clause: str | None,
    positions: tuple[tuple[int, str], ...],
    offset: int,
) -> str | None:
    current = block_clause
    for position, clause_id in positions:
        if position > offset:
            break
        current = clause_id
    return current


def _record_ids_for_input(path: str, known_ids: AbstractSet[str]) -> tuple[str, ...]:
    match = re.search(r"(?:definition|requirement)-(.+?)(?:\.tex)?$", path)
    if match is None:
        return ()
    value = match.group(1)
    for identifier in known_ids:
        if identifier == value:
            return (identifier,)
    return ()


@dataclass(slots=True)
class _BlockContext:
    block: _MutableContentBlock
    body: str
    block_id: str
    clause_id: str | None
    positions: tuple[tuple[int, str], ...]
    specs: list[Spec] = field(default_factory=list)
    occupied: list[tuple[int, int]] = field(default_factory=list)
    list_number: int = 0

    def clause_at(self, offset: int) -> str | None:
        return _clause_at(self.clause_id, self.positions, offset)

    def next_list_id(self) -> str:
        self.list_number += 1
        return f"content-element-{self.block_id}-list-{self.list_number:03d}"


def _row_event_spec(
    event: Event,
    context: _BlockContext,
    env_offset: int,
    list_id: str,
    known_ids: AbstractSet[str],
) -> Spec | None:
    if event.name == "HLAAcronymRow" and len(event.args) >= 3:
        value = f"{_strip_commands(event.args[1])} — {_strip_commands(event.args[2])}"
        record_ids: tuple[str, ...] = ()
    elif len(event.args) >= 2:
        value = _strip_commands(event.args[1])
        record_ids = (event.args[0],) if event.args[0] in known_ids else ()
    else:
        return None
    offset = env_offset + event.start
    return Spec("list-item", value, offset, context.clause_at(offset), list_id, record_ids)


def _append_list_item_specs(
    context: _BlockContext,
    env_body: str,
    env_offset: int,
    list_id: str,
    known_ids: AbstractSet[str],
) -> None:
    row_events = _events(env_body, {"HLAAcronymRow", "HLASummaryRule"})
    if row_events:
        for event in row_events:
            spec = _row_event_spec(event, context, env_offset, list_id, known_ids)
            if spec is not None:
                context.specs.append(spec)
        return
    item_events = _events(env_body, {"item"})
    boundaries = [event.start for event in item_events] + [len(env_body)]
    for index, event in enumerate(item_events):
        value = _strip_commands(env_body[event.end : boundaries[index + 1]])
        if value:
            offset = env_offset + event.start
            context.specs.append(
                Spec("list-item", value, offset, context.clause_at(offset), list_id)
            )


def _extract_list_specs(context: _BlockContext, known_ids: AbstractSet[str]) -> None:
    for env_name, start, end, env_body in _environments(context.body):
        list_id = context.next_list_id()
        context.specs.append(Spec("list", env_name, start, context.clause_at(start)))
        context.occupied.append((start, end))
        env_offset = start + context.body[start:end].find(env_body)
        _append_list_item_specs(context, env_body, env_offset, list_id, known_ids)


def _direct_prose_value(event: Event) -> str | None:
    if not event.args:
        return None
    if event.name == "HLAClauseLabeledItem" and len(event.args) >= 2:
        value = f"{_strip_commands(event.args[0])} {_strip_commands(event.args[-1])}"
    elif event.name == "HLAContentsEntry" and len(event.args) >= 4:
        number = _strip_commands(event.args[1])
        title = _strip_commands(event.args[2])
        page = _strip_commands(event.args[3])
        value = " ".join(part for part in (number, title, f"(page {page})" if page else "") if part)
    else:
        value = _strip_commands(event.args[-1])
    return value if len(value) >= 12 else None


def _extract_direct_prose(context: _BlockContext, events: Sequence[Event]) -> None:
    for event in events:
        value = _direct_prose_value(event)
        if value is None:
            continue
        clause_id = context.clause_at(event.start)
        if event.name in {"HLAClauseDashItem", "HLAClauseLabeledItem"}:
            list_id = context.next_list_id()
            context.specs.extend(
                (
                    Spec("list", event.name, event.start, clause_id),
                    Spec("list-item", value, event.start, clause_id, list_id),
                )
            )
        else:
            kind = "note" if event.name == "HLANoteBlock" else "paragraph"
            context.specs.append(Spec(kind, value, event.start, clause_id))
        context.occupied.append((event.start, event.end))


def _extract_footnotes_and_notes(context: _BlockContext) -> None:
    for event in _events(context.body, {"footnote", "footnotetext"}):
        if not event.args:
            continue
        context.specs.append(
            Spec(
                "footnote",
                _strip_commands(event.args[-1]),
                event.start,
                context.clause_at(event.start),
            )
        )
        context.occupied.append((event.start, event.end))
    for match in re.finditer(r"\bNOTE---(?P<text>.*?)(?:\\par\b|$)", context.body, re.DOTALL):
        note_text = _strip_commands(match.group("text"))
        if not note_text:
            continue
        context.specs.append(
            Spec("note", note_text, match.start(), context.clause_at(match.start()))
        )
        context.occupied.append((match.start(), match.end()))


def _extract_cross_references(context: _BlockContext, known_ids: AbstractSet[str]) -> None:
    for event in _events(context.body, {"input"}):
        if not event.args:
            continue
        path = PurePosixPath(event.args[0])
        if path.parts[:2] != ("output", "semantic"):
            continue
        if any(start <= event.start < end for start, end in context.occupied):
            continue
        path_text = path.as_posix()
        identifiers = _record_ids_for_input(path_text, known_ids)
        context.specs.append(
            Spec(
                "cross-reference",
                f"Semantic record {path.stem}",
                event.start,
                context.clause_at(event.start),
                record_ids=identifiers,
            )
        )
        context.occupied.append((event.start, event.end))


def _extract_formulas(context: _BlockContext) -> None:
    for match in re.finditer(r"\\\((.+?)\\\)|\\\[(.+?)\\\]", context.body, re.DOTALL):
        context.specs.append(
            Spec(
                "formula",
                _strip_commands(match.group(1) or match.group(2) or ""),
                match.start(),
                context.clause_at(match.start()),
            )
        )
        context.occupied.append((match.start(), match.end()))


def _paragraph_body(context: _BlockContext) -> str:
    prose = context.body
    for start, end in sorted(context.occupied, reverse=True):
        prose = prose[:start] + "\n\n" + prose[end:]
    structural_commands = HEADING_COMMANDS | {
        "HLAStartFrontMatterUnnumberedPage",
        "HLAStartFrontMatterPage",
        "HLAStartSemanticPage",
        "HLAStartSemanticOpenerPage",
        "HLAContentMarker",
    }
    events = sorted(_events(prose, structural_commands), key=lambda item: item.start, reverse=True)
    for event in events:
        prose = prose[: event.start] + "\n\n" + prose[event.end :]
    return prose


def _extract_paragraph_specs(context: _BlockContext, has_direct_events: bool) -> None:
    paragraphs = () if has_direct_events else _paragraphs(_paragraph_body(context))
    for value in paragraphs:
        if re.search(r"(?:HLA(?:Clause|Table)|m\d+\.|\b\d+\.\d{3}\b)", value):
            continue
        offset = context.body.find(value[:24]) if value[:24] else 0
        context.specs.append(
            Spec("paragraph", value, max(offset, 0), context.clause_at(max(offset, 0)))
        )


def _append_fallback_spec(context: _BlockContext) -> None:
    if context.specs:
        return
    fallback = (
        ""
        if context.block_id.startswith("content-15162") and context.block.layout_body is not None
        else _strip_commands(context.block.text)
    )
    fallback = re.sub(r"^\d+\s+", "", fallback)
    if fallback and len(fallback) >= 12:
        spec = Spec("paragraph", fallback, 0, context.clause_id)
    else:
        spec = Spec(
            "paragraph",
            f"Layout adapter for {context.block_id}; no independent prose surface was present.",
            0,
            context.clause_id,
        )
    context.specs.append(spec)


def _serialize_specs(context: _BlockContext) -> tuple[ContentElement, ...]:
    context.specs.sort(key=lambda item: (item.offset, 0 if item.kind == "list" else 1))
    output: list[ContentElement] = []
    for local_index, spec in enumerate(context.specs, 1):
        identifier = f"content-element-{context.block_id}-{spec.kind}-{local_index:03d}"
        element = ContentElement(
            id=identifier,
            kind=spec.kind,  # type: ignore[arg-type]
            text=spec.text,
            clause_id=spec.clause_id,
            block_id=context.block_id,
            parent_id=spec.parent_id,
            record_ids=spec.record_ids,
            source=_source_for(context.block, context.body, spec.offset),
            sequence=local_index,
        )
        output.append(element)
    temporary_to_real: dict[str, str] = {}
    list_index = 0
    for spec, item in zip(context.specs, output, strict=True):
        if spec.kind == "list":
            list_index += 1
            temporary_id = f"content-element-{context.block_id}-list-{list_index:03d}"
            temporary_to_real[temporary_id] = item.id
    for index, item in enumerate(output):
        parent = item.parent_id
        if parent in temporary_to_real:
            output[index] = item.model_copy(update={"parent_id": temporary_to_real[parent]})
    context.block.element_ids = tuple(item.id for item in output)
    return tuple(output)


def _extract_block(
    block: _MutableContentBlock,
    *,
    clause_ids: AbstractSet[str],
    known_ids: AbstractSet[str],
) -> tuple[ContentElement, ...]:
    body = block.layout_body or ""
    context = _BlockContext(
        block=block,
        body=body,
        block_id=block.id,
        clause_id=block.clause_id,
        positions=_clause_positions(body, clause_ids),
    )
    direct_events = _events(
        body,
        {
            "HLAClauseParagraph",
            "HLAClauseDashItem",
            "HLAClauseLabeledItem",
            "HLAPara",
            "HLAFrontPlacedBlock",
            "HLACompactPara",
            "HLANoteBlock",
            "HLAAnnexFieldBlock",
            "HLAContentsEntry",
        },
    )
    _extract_list_specs(context, known_ids)
    _extract_direct_prose(context, direct_events)
    _extract_footnotes_and_notes(context)
    _extract_cross_references(context, known_ids)
    _extract_formulas(context)
    _extract_paragraph_specs(context, bool(direct_events))
    _append_fallback_spec(context)
    return _serialize_specs(context)


def migrate(root: Path) -> None:
    model = load_document_model(root, HLA_SOURCE)
    blocks_path = DocumentResources(root).semantic_file("content-blocks.json")
    payload = ContentBlockFile.model_validate_json(blocks_path.read_text(encoding="utf-8"))
    blocks = [
        _MutableContentBlock.model_validate(block.model_dump(mode="python", exclude_unset=True))
        for block in payload.content_blocks
    ]
    known_ids = set(model.semantic_record_ids())
    elements: list[ContentElement] = []
    for block in blocks:
        elements.extend(
            _extract_block(
                block,
                clause_ids={item.id for item in model.clauses},
                known_ids=known_ids,
            )
        )
    blocks_path.write_text(
        ContentBlockFile(
            schema_version=payload.schema_version,
            content_blocks=tuple(
                ContentBlock.model_validate(block.model_dump(mode="python", exclude_unset=True))
                for block in blocks
            ),
        ).model_dump_json(indent=2, exclude_unset=True)
        + "\n",
        encoding="utf-8",
    )
    DocumentResources(root).semantic_file("content-elements.json").write_text(
        ContentElementFile(schema_version=1, content_elements=tuple(elements)).model_dump_json(
            indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"content blocks: {len(blocks)}")
    print(f"content elements: {len(elements)}")
    kinds = sorted({item.kind for item in elements})
    print(f"kinds: {', '.join(kinds)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", help="document root to migrate")
    parser.add_argument(
        "--workspace-root", type=Path, help="workspace for the default document root"
    )
    args = parser.parse_args()
    root = (
        args.root or resources(repository_root(args.workspace_root)).document("hla-1516-2025").root
    )
    migrate(root)


if __name__ == "__main__":
    main()
