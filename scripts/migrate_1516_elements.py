"""Extract typed content elements from the faithful IEEE 1516 page adapters."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.hla_profile import HLA_SOURCE
from scripts.semantic_model import ContentElement, SourceRef, load_document_model


@dataclass(frozen=True)
class Event:
    name: str
    start: int
    end: int
    args: tuple[str, ...]


@dataclass(frozen=True)
class Spec:
    kind: str
    text: str
    offset: int
    clause_id: str | None = None
    parent_id: str | None = None
    record_ids: tuple[str, ...] = ()


LIST_ENVIRONMENTS = {
    "hlaoverviewservicelist",
    "hlaacronymrows",
    "hlasummaryrules",
}

HEADING_COMMANDS = {
    "HLAClauseHeading",
    "HLASubclauseHeading",
    "HLADetailedRuleHeading",
    "HLARationaleHeading",
    "HLAFrontHeading",
    "HLAFrontHeadingAdjusted",
    "HLAFrontMajorHeadingAdjusted",
    "HLAMinorClauseHeading",
}


def _balanced(text: str, start: int, opener: str = "{") -> tuple[str, int] | None:
    if start >= len(text) or text[start] != opener:
        return None
    closer = "}" if opener == "{" else "]"
    depth = 0
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
    return None


def _events(text: str, names: set[str]) -> tuple[Event, ...]:
    pattern = re.compile(r"\\(?P<name>[A-Za-z@]+)")
    result: list[Event] = []
    for match in pattern.finditer(text):
        name = match.group("name")
        if name not in names:
            continue
        cursor = match.end()
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor < len(text) and text[cursor] == "*":
            cursor += 1
        if cursor < len(text) and text[cursor] == "[":
            optional = _balanced(text, cursor, "[")
            if optional is None:
                continue
            cursor = optional[1]
        args: list[str] = []
        while cursor < len(text):
            while cursor < len(text) and text[cursor].isspace():
                cursor += 1
            if cursor >= len(text) or text[cursor] != "{":
                break
            value = _balanced(text, cursor)
            if value is None:
                break
            args.append(value[0])
            cursor = value[1]
        result.append(Event(name, match.start(), cursor, tuple(args)))
    return tuple(result)


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
        r"\b(?:remember|picture|overlay|current|page|north|south|east|west|anchor|inner|outer|sep|align|justify|selectfont|HLATitlePage|HLAPublicationPage|HLASemanticPage|flushright)\b",
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


def _source_for(block: dict[str, object], body: str, offset: int) -> dict[str, object]:
    source = block["source"]
    assert isinstance(source, dict)
    line = int(source["line"]) + body.count("\n", 0, offset)
    return {
        "path": source["path"],
        "line": line,
        "end_line": max(line, line + body[offset:].count("\n")),
    }


def _clause_positions(body: str, clause_ids: set[str]) -> tuple[tuple[int, str], ...]:
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


def _record_ids_for_input(path: str, known_ids: set[str]) -> tuple[str, ...]:
    match = re.search(r"(?:definition|requirement)-(.+?)(?:\.tex)?$", path)
    if match is None:
        return ()
    value = match.group(1)
    for identifier in known_ids:
        if identifier == value:
            return (identifier,)
    return ()


def _extract_block(
    block: dict[str, object],
    *,
    clause_ids: set[str],
    known_ids: set[str],
) -> tuple[dict[str, object], ...]:
    body = str(block.get("layout_body") or "")
    block_id = str(block["id"])
    positions = _clause_positions(body, clause_ids)
    specs: list[Spec] = []
    occupied: list[tuple[int, int]] = []
    list_numbers = 0
    direct_prose_events = _events(
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

    for env_name, start, end, env_body in _environments(body):
        list_numbers += 1
        list_id = f"content-element-{block_id}-list-{list_numbers:03d}"
        specs.append(
            Spec(
                "list",
                env_name,
                start,
                _clause_at(str(block.get("clause_id") or "") or None, positions, start),
            )
        )
        occupied.append((start, end))
        env_offset = start + body[start:end].find(env_body)
        row_events = _events(env_body, {"HLAAcronymRow", "HLASummaryRule"})
        item_events = _events(env_body, {"item"})
        if row_events:
            for _index, event in enumerate(row_events, 1):
                if event.name == "HLAAcronymRow" and len(event.args) >= 3:
                    value = f"{_strip_commands(event.args[1])} — {_strip_commands(event.args[2])}"
                    record_ids: tuple[str, ...] = ()
                elif len(event.args) >= 2:
                    value = _strip_commands(event.args[1])
                    record_ids = (event.args[0],) if event.args[0] in known_ids else ()
                else:
                    continue
                specs.append(
                    Spec(
                        "list-item",
                        value,
                        env_offset + event.start,
                        _clause_at(
                            str(block.get("clause_id") or "") or None,
                            positions,
                            env_offset + event.start,
                        ),
                        list_id,
                        record_ids,
                    )
                )
        elif item_events:
            boundaries = [event.start for event in item_events] + [len(env_body)]
            for index, event in enumerate(item_events):
                part = env_body[event.end : boundaries[index + 1]]
                value = _strip_commands(part)
                if value:
                    specs.append(
                        Spec(
                            "list-item",
                            value,
                            env_offset + event.start,
                            _clause_at(
                                str(block.get("clause_id") or "") or None,
                                positions,
                                env_offset + event.start,
                            ),
                            list_id,
                        )
                    )

    # Semantic page adapters retain prose inside positioned layout macros.
    # Extract those macros directly so the typed content surface contains the
    # words of the paragraph, rather than the coordinates and wrapper
    # commands that happen to surround it.
    for event in direct_prose_events:
        if not event.args:
            continue
        if event.name == "HLAClauseLabeledItem" and len(event.args) >= 2:
            value = f"{_strip_commands(event.args[0])} {_strip_commands(event.args[-1])}"
        elif event.name == "HLAContentsEntry" and len(event.args) >= 4:
            number = _strip_commands(event.args[1])
            title = _strip_commands(event.args[2])
            page = _strip_commands(event.args[3])
            value = " ".join(
                part for part in (number, title, f"(page {page})" if page else "") if part
            )
        else:
            value = _strip_commands(event.args[-1])
        if not value or len(value) < 12:
            continue
        if event.name in {"HLAClauseDashItem", "HLAClauseLabeledItem"}:
            list_numbers += 1
            list_id = f"content-element-{block_id}-list-{list_numbers:03d}"
            clause_id = _clause_at(
                str(block.get("clause_id") or "") or None,
                positions,
                event.start,
            )
            specs.extend(
                (
                    Spec("list", event.name, event.start, clause_id),
                    Spec("list-item", value, event.start, clause_id, list_id),
                )
            )
        else:
            kind = "note" if event.name == "HLANoteBlock" else "paragraph"
            specs.append(
                Spec(
                    kind,
                    value,
                    event.start,
                    _clause_at(
                        str(block.get("clause_id") or "") or None,
                        positions,
                        event.start,
                    ),
                )
            )
        occupied.append((event.start, event.end))

    footnotes = _events(body, {"footnote", "footnotetext"})
    for event in footnotes:
        if not event.args:
            continue
        specs.append(
            Spec(
                "footnote",
                _strip_commands(event.args[-1]),
                event.start,
                _clause_at(str(block.get("clause_id") or "") or None, positions, event.start),
            )
        )
        occupied.append((event.start, event.end))

    for match in re.finditer(r"\bNOTE---(?P<text>.*?)(?:\\par\b|$)", body, re.DOTALL):
        note_text = _strip_commands(match.group("text"))
        if not note_text:
            continue
        specs.append(
            Spec(
                "note",
                note_text,
                match.start(),
                _clause_at(str(block.get("clause_id") or "") or None, positions, match.start()),
            )
        )
        occupied.append((match.start(), match.end()))

    input_events = _events(body, {"input"})
    for event in input_events:
        if not event.args or not event.args[0].startswith("output/semantic/"):
            continue
        if any(start <= event.start < end for start, end in occupied):
            continue
        path = event.args[0]
        identifiers = _record_ids_for_input(path, known_ids)
        label = path.rsplit("/", 1)[-1].removesuffix(".tex")
        specs.append(
            Spec(
                "cross-reference",
                f"Semantic record {label}",
                event.start,
                _clause_at(str(block.get("clause_id") or "") or None, positions, event.start),
                record_ids=identifiers,
            )
        )
        occupied.append((event.start, event.end))

    formulas = list(re.finditer(r"\\\((.+?)\\\)|\\\[(.+?)\\\]", body, re.DOTALL))
    for match in formulas:
        specs.append(
            Spec(
                "formula",
                _strip_commands(match.group(1) or match.group(2) or ""),
                match.start(),
                _clause_at(str(block.get("clause_id") or "") or None, positions, match.start()),
            )
        )
        occupied.append((match.start(), match.end()))

    # The exact layout body owns headings and geometry; the paragraph records
    # retain only prose. Remove structure-bearing commands before normalizing.
    prose = body
    for start, end in sorted(occupied, reverse=True):
        prose = prose[:start] + "\n\n" + prose[end:]
    for event in sorted(
        _events(
            prose,
            HEADING_COMMANDS
            | {
                "HLAStartFrontMatterUnnumberedPage",
                "HLAStartFrontMatterPage",
                "HLAStartSemanticPage",
                "HLAStartSemanticOpenerPage",
                "HLAContentMarker",
            },
        ),
        key=lambda item: item.start,
        reverse=True,
    ):
        prose = prose[: event.start] + "\n\n" + prose[event.end :]
    # Once a semantic page has explicit positioned prose events, residual
    # wrapper geometry is layout noise rather than a second prose surface.
    generic_paragraphs = () if direct_prose_events else _paragraphs(prose)
    for _index, value in enumerate(generic_paragraphs, 1):
        if re.search(r"(?:HLA(?:Clause|Table)|m\d+\.|\b\d+\.\d{3}\b)", value):
            continue
        offset = body.find(value[:24]) if value[:24] else 0
        if offset < 0:
            offset = 0
        specs.append(
            Spec(
                "paragraph",
                value,
                offset,
                _clause_at(str(block.get("clause_id") or "") or None, positions, offset),
            )
        )

    if not specs:
        fallback = (
            ""
            if block_id.startswith("content-15162") and block.get("layout_body") is not None
            else _strip_commands(str(block.get("text") or ""))
        )
        fallback = re.sub(r"^\d+\s+", "", fallback)
        if fallback and len(fallback) >= 12:
            specs.append(
                Spec(
                    "paragraph",
                    fallback,
                    0,
                    str(block.get("clause_id") or "") or None,
                )
            )
        else:
            specs.append(
                Spec(
                    "paragraph",
                    f"Layout adapter for {block_id}; no independent prose surface was present.",
                    0,
                    str(block.get("clause_id") or "") or None,
                )
            )

    # Keep source order for the semantic document while ensuring list parents
    # are emitted before their children.
    specs.sort(key=lambda item: (item.offset, 0 if item.kind == "list" else 1))
    output: list[dict[str, object]] = []
    for local_index, spec in enumerate(specs, 1):
        identifier = f"content-element-{block_id}-{spec.kind}-{local_index:03d}"
        parent_id = spec.parent_id
        if parent_id is not None:
            # The temporary parent is the stable list ID generated above.
            parent_id = parent_id
        element = ContentElement(
            id=identifier,
            kind=spec.kind,  # type: ignore[arg-type]
            text=spec.text,
            clause_id=spec.clause_id,
            block_id=block_id,
            parent_id=parent_id,
            record_ids=spec.record_ids,
            source=SourceRef.model_validate(_source_for(block, body, spec.offset)),
            sequence=local_index,
        )
        output.append(element.model_dump(mode="json"))

    # Replace temporary list IDs with their emitted IDs. The list is always
    # emitted before its items due to the sort above.
    temporary_to_real: dict[str, str] = {}
    list_index = 0
    for spec, item in zip(specs, output, strict=True):
        if spec.kind == "list":
            list_index += 1
            temporary_to_real[f"content-element-{block_id}-list-{list_index:03d}"] = str(item["id"])
    for item in output:
        parent = item.get("parent_id")
        if parent in temporary_to_real:
            item["parent_id"] = temporary_to_real[parent]
    block["element_ids"] = [str(item["id"]) for item in output]
    return tuple(output)


def migrate(root: Path) -> None:
    model = load_document_model(root, HLA_SOURCE)
    blocks_path = root / "semantic" / "content-blocks.json"
    payload = json.loads(blocks_path.read_text(encoding="utf-8"))
    blocks = payload["content_blocks"]
    known_ids = set(model.semantic_record_ids())
    elements: list[dict[str, object]] = []
    for block in blocks:
        elements.extend(
            _extract_block(
                block,
                clause_ids={item.id for item in model.clauses},
                known_ids=known_ids,
            )
        )
    blocks_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "semantic" / "content-elements.json").write_text(
        json.dumps(
            {"schema_version": 1, "content_elements": elements}, ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"content blocks: {len(blocks)}")
    print(f"content elements: {len(elements)}")
    kinds = sorted({str(item["kind"]) for item in elements})
    print(f"kinds: {', '.join(kinds)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, nargs="?", default=Path("topics/ieee/hla-1516-2025"))
    args = parser.parse_args()
    migrate(args.root)


if __name__ == "__main__":
    main()
