"""Promote legacy HLA 2010 LaTeX surfaces into the shared semantic model.

The 2010 handoffs predate the semantic HLA command vocabulary used by the 2025
recreations.  This adapter understands the older ``\\clause``/``\\subclause``
commands, ordinary section headings, ``\\defentry`` and ``definition``
environments, while emitting only the generic Pydantic record contracts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from hla_lab.core.io import write_json
from hla_lab.core.parsing import line_number, try_balanced_group
from hla_lab.core.semantic_model import (
    Clause,
    ContentBlock,
    ContentBlockFile,
    ContentElement,
    Definition,
    DefinitionFile,
    Figure,
    Note,
    Requirement,
    RequirementFile,
    SourceRef,
    Table,
    TableCell,
    _latex_text,
)
from hla_lab.core.text import slugify
from hla_lab.paths import DocumentResources


@dataclass(frozen=True)
class Heading:
    offset: int
    command: str
    number: str
    title: str
    line: int


_INCLUDE = re.compile(r"\\(?:input|include)\s*\{([^{}]+)\}")
_COMMAND = re.compile(r"\\(?P<name>[A-Za-z@]+)")
_HEADING = re.compile(
    r"\\(?P<command>clause|subclause|subsubclause|annexsection|annexsubsection|"
    r"section|subsection|subsubsection|paragraph|annexsubhead)\*?\s*\{"
)
_NORMATIVE_SENTENCE_END = re.compile(r"[.!?](?=\s+[A-Z0-9`\"(\[]|$)")
_NORMATIVE_LAYOUT_ENVIRONMENT = re.compile(
    r"(?s)\\begin\{(?:tikzpicture|picture)\*?\}.*?"
    r"\\end\{(?:tikzpicture|picture)\*?\}"
)
_NATIVE_FIGURE = re.compile(
    r"(?m)^\s*(?:\\stdnativefigure(?:\*?\[[^]]*\])?\s*)?"
    r"(?:\\input\s*\{)?figures/native/[^}\s]+(?:\})?\s*$"
)
_NORMATIVE_STOP_WORDS = {
    "a",
    "an",
    "about",
    "after",
    "also",
    "among",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "because",
    "been",
    "being",
    "during",
    "for",
    "from",
    "have",
    "if",
    "in",
    "into",
    "must",
    "of",
    "on",
    "or",
    "shall",
    "that",
    "the",
    "their",
    "these",
    "this",
    "those",
    "to",
    "through",
    "under",
    "using",
    "was",
    "were",
    "when",
    "which",
    "with",
}


def _arguments(text: str, offset: int, count: int) -> tuple[str, ...] | None:
    command = _COMMAND.match(text, offset)
    if command is None:
        return None
    cursor = command.end()
    values: list[str] = []
    for _ in range(count):
        value = try_balanced_group(text, cursor, skip_whitespace=True)
        if value is None:
            return None
        body, cursor = value
        values.append(body)
    return tuple(values)


def _plain(value: str) -> str:
    value = re.sub(r"(?m)^\s*%.*$", "", value)
    value = re.sub(r"figures/native/[^}\s]+", " ", value)
    value = re.sub(r"\\(?:input|include)\s*\{[^{}]*\}", " ", value)
    value = re.sub(r"\\stdnativefigure(?:\*?\[[^]]*\])?\s*\{[^{}]*\}", " ", value)
    value = value.replace("\\\\", " ")
    value = value.replace("&", " ")
    value = re.sub(r"\\(?:begin|end)\{[^{}]*\}", " ", value)
    value = re.sub(r"\\(?:vspace|hspace|addvspace)\*?\{[^{}]*\}", " ", value)
    try:
        return _latex_text(value).replace("\\\\", " ").strip()
    except ValueError:
        # Requirement candidates may be line-local slices through a larger
        # LaTeX command.  They remain useful inventory records even when the
        # slice is not a balanced standalone fragment.
        value = re.sub(r"\\[A-Za-z@]+(?:\*?\[[^]]*\])?", " ", value)
        return re.sub(r"\s+", " ", value.replace("{", "").replace("}", "")).strip()


def _source(root: Path, path: Path, text: str, offset: int, end: int | None = None) -> SourceRef:
    return SourceRef(
        path=path.relative_to(root).as_posix(),
        line=line_number(text, offset),
        end_line=line_number(text, end) if end is not None else None,
    )


def _direct_inputs(root: Path) -> tuple[Path, ...]:
    main = DocumentResources(root).main_tex
    text = main.read_text(encoding="utf-8")
    paths: list[Path] = []
    for match in _INCLUDE.finditer(text):
        candidate = main.parent / match.group(1).strip()
        if candidate.suffix != ".tex":
            candidate = candidate.with_suffix(".tex")
        if candidate.is_file() and DocumentResources(root).output not in candidate.parents:
            paths.append(candidate)
    return tuple(paths)


def _surface_inputs(root: Path) -> tuple[Path, ...]:
    """Return authored TeX surfaces, including files nested below main.tex."""
    excluded = {"output", "build", "dist", ".trash"}
    return tuple(
        sorted(
            (
                path
                for path in root.rglob("*.tex")
                if not any(part in excluded for part in path.relative_to(root).parts)
                and path.name != "main.tex"
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
    )


def _expand_local_inputs(root: Path, path: Path, text: str, stack: tuple[Path, ...] = ()) -> str:
    """Inline local input files while retaining native TikZ macro references.

    The generated semantic block becomes the visible source for ordinary
    clause/front-matter prose. Native figure calls are intentionally left as
    calls until their typed diagram records replace them in a later migration
    slice.
    """
    if path in stack:
        return text

    def replace(match: re.Match[str]) -> str:
        include = match.group(1).strip()
        candidate = path.parent / include
        if candidate.suffix != ".tex":
            candidate = candidate.with_suffix(".tex")
        if not candidate.is_file() or "figures/native" in candidate.as_posix():
            return match.group(0)
        nested = candidate.read_text(encoding="utf-8")
        return _expand_local_inputs(root, candidate, nested, (*stack, path))

    return _INCLUDE.sub(replace, text)


def _root_number(path: Path) -> str | None:
    value = "/".join(path.as_posix().casefold().split("/")[-2:])
    if "annex" in value:
        match = re.search(r"annex[-_ ]+([a-z])", value)
        return match.group(1).upper() if match else None
    match = re.search(r"(?:clause|^|[/_-])0*(\d+)(?:[/_.-]|$)", value)
    return match.group(1) if match else None


def _explicit_heading(command: str, value: str) -> tuple[str, str] | None:
    value = _plain(value)
    match = re.match(r"(?P<number>[A-Za-z]?\d+(?:\.\d+)*)\.\s*(?P<title>.+)$", value)
    if match:
        return match.group("number"), match.group("title").strip()
    match = re.match(r"(?P<number>[A-Za-z]?\d+(?:\.\d+)*)\s+(?P<title>.+)$", value)
    if (
        command in {"clause", "subclause", "subsubclause", "annexsection", "annexsubsection"}
        and match
    ):
        return match.group("number"), match.group("title").strip()
    return None


def _headings(root: Path, path: Path, text: str) -> tuple[Heading, ...]:
    root_number = _root_number(path)
    counters: dict[str, int] = {"subsection": 0, "subsubsection": 0, "paragraph": 0}
    current_root = root_number
    current_subsection: str | None = None
    records: list[Heading] = []
    for match in _HEADING.finditer(text):
        command = match.group("command")
        values = _arguments(text, match.start(), 1)
        if values is None:
            continue
        raw = values[0]
        explicit = _explicit_heading(command, raw)
        if explicit is not None:
            number, title = explicit
        elif command in {"section", "clause", "annexhead"} and root_number is not None:
            number, title = root_number, _plain(raw)
        elif (
            command in {"subsection", "subclause", "annexsubhead", "annexsection"} and current_root
        ):
            counters["subsection"] += 1
            counters["subsubsection"] = 0
            counters["paragraph"] = 0
            number, title = f"{current_root}.{counters['subsection']}", _plain(raw)
        elif command in {"subsubsection", "subsubclause", "annexsubsection"} and current_root:
            counters["subsubsection"] += 1
            counters["paragraph"] = 0
            parent = current_subsection or current_root
            number, title = f"{parent}.{counters['subsubsection']}", _plain(raw)
        elif command == "paragraph" and current_root:
            counters["paragraph"] += 1
            parent = current_subsection or current_root
            number, title = f"{parent}.{counters['paragraph']}", _plain(raw)
        else:
            continue
        if command in {"section", "clause", "annexdesignation", "annexhead"}:
            current_root = number
            counters = {"subsection": 0, "subsubsection": 0, "paragraph": 0}
            current_subsection = None
        elif command in {"subsection", "subclause", "annexsection", "annexsubhead"}:
            current_subsection = number
        records.append(
            Heading(
                offset=match.start(),
                command=command,
                number=number,
                title=title,
                line=line_number(text, match.start()),
            )
        )
    return tuple(records)


def _clause_records(root: Path, files: tuple[Path, ...]) -> tuple[Clause, ...]:
    records: dict[str, Clause] = {}
    for path in files:
        text = _expand_local_inputs(root, path, path.read_text(encoding="utf-8"))
        headings = _headings(root, path, text)
        for heading in headings:
            number = heading.number
            parts = number.split(".")
            parent = f"clause-{'.'.join(parts[:-1])}" if len(parts) > 1 else None
            record = Clause(
                id=f"clause-{number}",
                number=number,
                title=heading.title,
                parent_id=parent,
                level=len(parts),
                source=_source(root, path, text, heading.offset),
            )
            records.setdefault(record.id, record)
    return tuple(records.values())


def _clause_for(path: Path, headings: tuple[Heading, ...]) -> str | None:
    if headings:
        return f"clause-{headings[-1].number}"
    root_number = _root_number(path)
    return f"clause-{root_number}" if root_number else None


def _clause_for_line(
    path: Path, headings: tuple[Heading, ...], line: int
) -> str | None:
    """Resolve the heading that owns a source line, not the file's final heading."""

    prior = tuple(item for item in headings if item.line <= line)
    if prior:
        return f"clause-{prior[-1].number}"
    return _clause_for(path, headings)


def _paragraphs(
    root: Path, path: Path, text: str, block_id: str, clause_id: str | None
) -> tuple[ContentElement, ...]:
    plain = _plain(text)
    if len(plain) < 20 or not re.search(r"[A-Za-z]{3}", plain):
        return ()
    return (
        ContentElement(
            id=f"{block_id}-paragraph-0001",
            kind="paragraph",
            text=plain,
            clause_id=clause_id,
            block_id=block_id,
            source=_source(root, path, text, 0),
            sequence=1,
        ),
    )


def _content(
    root: Path, files: tuple[Path, ...]
) -> tuple[tuple[ContentBlock, ...], tuple[ContentElement, ...]]:
    blocks: list[ContentBlock] = []
    elements: list[ContentElement] = []
    for sequence, path in enumerate(files):
        text = _expand_local_inputs(root, path, path.read_text(encoding="utf-8"))
        block_id = f"content-{slugify(path.relative_to(root).as_posix())}"
        clause_id = _clause_for(path, _headings(root, path, text))
        block_elements = _paragraphs(root, path, text, block_id, clause_id)
        elements.extend(block_elements)
        blocks.append(
            ContentBlock(
                id=block_id,
                kind="context",
                text="",
                clause_id=clause_id,
                element_ids=tuple(item.id for item in block_elements),
                source=_source(root, path, text, 0),
                sequence=sequence,
                layout_body=text,
            )
        )
    return tuple(blocks), tuple(elements)


def _definitions(root: Path, files: tuple[Path, ...]) -> tuple[Definition, ...]:
    records: list[Definition] = []
    seen: set[str] = set()
    seen_values: set[tuple[str, str]] = set()
    for path in files:
        text = path.read_text(encoding="utf-8")
        headings = _headings(root, path, text)
        for command, arity in (("defentry", 2), ("term", 1)):
            for match in re.finditer(rf"\\{command}\b", text):
                values = _arguments(text, match.start(), arity)
                if values is None:
                    continue
                term = _plain(values[0])
                if not term:
                    continue
                if command == "defentry":
                    body = values[1]
                else:
                    line_end = text.find("\n", match.end())
                    body = text[match.end() : line_end if line_end >= 0 else len(text)]
                normalized = (term, _plain(body))
                if normalized in seen_values:
                    continue
                seen_values.add(normalized)
                definition_id = f"def-{slugify(term)}"
                if definition_id in seen:
                    digest = hashlib.sha1(f"{path}:{match.start()}".encode()).hexdigest()[:8]
                    definition_id = f"{definition_id}-{digest}"
                seen.add(definition_id)
                records.append(
                    Definition(
                        id=definition_id,
                        term=term,
                        text=_plain(body),
                        clause_id=_clause_for(path, headings),
                        source=_source(root, path, text, match.start()),
                    )
                )
        for match in re.finditer(r"\\begin\{definition\}", text):
            opening = try_balanced_group(text, match.end(), skip_whitespace=True)
            if opening is None:
                continue
            term_raw, body_start = opening
            term = _plain(term_raw)
            if not term:
                continue
            end_marker = text.find(r"\end{definition}", body_start)
            body = text[body_start : end_marker if end_marker >= 0 else len(text)]
            normalized = (term, _plain(body))
            if normalized in seen_values:
                continue
            seen_values.add(normalized)
            definition_id = f"def-{slugify(term)}"
            if definition_id in seen:
                digest = hashlib.sha1(f"{path}:{match.start()}".encode()).hexdigest()[:8]
                definition_id = f"{definition_id}-{digest}"
            seen.add(definition_id)
            records.append(
                Definition(
                    id=definition_id,
                    term=term,
                    text=_plain(body),
                    clause_id=_clause_for(path, _headings(root, path, text)),
                    source=_source(root, path, text, match.start()),
                )
            )
    return tuple(records)


@dataclass(frozen=True)
class _NormativeCandidate:
    """One sentence-level source candidate with a complete authored span."""

    statement: str
    line: int
    end_line: int
    offset: int


def _mask_layout_source(text: str) -> str:
    """Remove diagrams and table layout while preserving source line numbers."""

    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if character == "\n" else " " for character in match.group(0))

    masked = _NORMATIVE_LAYOUT_ENVIRONMENT.sub(blank, text)
    # Native figures are authored as layout calls, not normative prose.  A
    # complete source line may contain nested resize/input commands, so mask
    # the line rather than trying to balance every layout wrapper.
    return re.sub(r"(?m)^.*figures/native/[^\n]*$", blank, masked)


def _normative_paragraphs(text: str) -> tuple[tuple[tuple[int, str], ...], ...]:
    """Group prose lines without allowing layout artifacts to join sentences."""

    lines = _mask_layout_source(text).splitlines()
    paragraphs: list[tuple[tuple[int, str], ...]] = []
    current: list[tuple[int, str]] = []
    in_table = False
    list_depth = 0
    for number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        table_begin = re.search(r"\\begin\{(?:tabular|tabularx|longtable)\*?\}", raw)
        if table_begin:
            if current:
                paragraphs.append(tuple(current))
                current = []
            in_table = True
            raw = raw[table_begin.end() :]
            if not raw.strip():
                continue
        table_end = re.search(r"\\end\{(?:tabular|tabularx|longtable)\*?\}", raw)
        if table_end:
            raw = raw[: table_end.start()]
            if raw.strip():
                current.append((number, raw))
            if current:
                paragraphs.append(tuple(current))
                current = []
            in_table = False
            continue
        if re.match(r"^\\(?:begin|end)\{(?:compactstdpage|annexstdpage)\}", stripped):
            if current and re.match(r"^\\end", stripped):
                current_text = _plain(" ".join(value for _, value in current))
                if not re.search(
                    rf"\b(?:{'|'.join(sorted(_NORMATIVE_STOP_WORDS))})$",
                    current_text.rstrip(" ;"),
                    re.IGNORECASE,
                ):
                    paragraphs.append(tuple(current))
                    current = []
            continue
        if not stripped:
            continue
        if re.match(
            r"^\\(?:clause|subclause|subsubclause|annexsection|annexsubsection|"
            r"section|subsection|subsubsection|paragraph|annexsubhead)\b",
            stripped,
        ):
            continue
        list_begin = re.match(
            r"^\\begin\{(?:stdalphalist|stdnumlist|stddashlist|enumerate|itemize)\}",
            stripped,
        )
        if list_begin:
            list_depth += 1
            continue
        list_end = re.match(
            r"^\\end\{(?:stdalphalist|stdnumlist|stddashlist|enumerate|itemize)\}",
            stripped,
        )
        if list_end:
            list_depth = max(0, list_depth - 1)
            continue
        item = re.search(r"\\item(?:\s*\[[^]]*\])?", raw)
        if item and list_depth <= 1:
            current_text = _plain(" ".join(value for _, value in current))
            current_incomplete = bool(
                re.search(
                    rf"\b(?:{'|'.join(sorted(_NORMATIVE_STOP_WORDS))})$",
                    current_text.rstrip(" ;"),
                    re.IGNORECASE,
                )
            )
            if current and not current_incomplete:
                paragraphs.append(tuple(current))
                current = []
            raw = raw[item.end() :]
            if not raw.strip():
                continue
        current.append((number, raw))
        if in_table and re.search(r"\\\\(?:\[[^]]*\])?\s*(?:%.*)?$", stripped):
            paragraphs.append(tuple(current))
            current = []
    if current:
        paragraphs.append(tuple(current))
    return tuple(paragraphs)


def _normative_candidates(text: str) -> tuple[_NormativeCandidate, ...]:
    """Extract complete normative sentences from a legacy source file."""

    candidates: list[_NormativeCandidate] = []
    for paragraph in _normative_paragraphs(text):
        pieces: list[str] = []
        mapping: list[int] = []
        for number, raw in paragraph:
            cleaned = _plain(raw)
            if not cleaned:
                continue
            if pieces:
                pieces.append(" ")
                mapping.append(number)
            pieces.append(cleaned)
            mapping.extend([number] * len(cleaned))
        joined = "".join(pieces)
        if not joined:
            continue
        starts = [0]
        starts.extend(match.end() for match in _NORMATIVE_SENTENCE_END.finditer(joined))
        for marker in re.finditer(r"(?=\s+[a-z]\))", joined):
            prefix = joined[: marker.start()].rstrip()
            if not re.search(
                rf"\b(?:{'|'.join(sorted(_NORMATIVE_STOP_WORDS))})$",
                prefix,
                re.IGNORECASE,
            ):
                starts.append(marker.start())
        starts = sorted(set(starts))
        segments: list[_NormativeCandidate] = []
        for start, end in zip(starts, (*starts[1:], len(joined)), strict=True):
            raw_statement = joined[start:end]
            statement = raw_statement.strip(" ;")
            # A legacy compact page can end immediately after the final list
            # marker's conjunction.  Keep the authored source span, but do
            # not publish a dangling glue word as a standalone obligation.
            if re.search(r"\b(?:[a-z]|\d+)\)", statement) and re.search(
                r"\s+(?:and|or)$", statement, re.IGNORECASE
            ):
                statement = re.sub(r"\s+(?:and|or)$", "", statement, flags=re.IGNORECASE)
            if not statement:
                continue
            left = start + len(raw_statement) - len(raw_statement.lstrip())
            right = end - len(raw_statement) + len(raw_statement.rstrip())
            span = mapping[max(0, left) : min(len(mapping), right)]
            if not span:
                continue
            segments.append(
                _NormativeCandidate(
                    statement=statement,
                    line=min(span),
                    end_line=max(span),
                    offset=start,
                )
            )
        merged: list[_NormativeCandidate] = []
        for segment in segments:
            marker = bool(re.match(r"^(?:[a-z]|\d+)\)", segment.statement.lstrip()))
            previous_incomplete = bool(
                merged
                and re.search(
                    rf"\b(?:{'|'.join(sorted(_NORMATIVE_STOP_WORDS))})$",
                    merged[-1].statement.rstrip(" ;"),
                    re.IGNORECASE,
                )
            )
            continuation = not re.search(
                r"\b(?:shall|must)\b", segment.statement, re.IGNORECASE
            )
            if merged and continuation and (previous_incomplete or marker):
                prior = merged[-1]
                merged[-1] = _NormativeCandidate(
                    statement=f"{prior.statement} {segment.statement}".strip(),
                    line=prior.line,
                    end_line=segment.end_line,
                    offset=prior.offset,
                )
            else:
                merged.append(segment)
        candidates.extend(
            segment
            for segment in merged
            if len(segment.statement) >= 30
            and re.search(r"\b(?:shall|must)\b", segment.statement, re.IGNORECASE)
        )
    return tuple(candidates)


def _requirements(root: Path, files: tuple[Path, ...]) -> tuple[Requirement, ...]:
    records: list[Requirement] = []
    seen: set[str] = set()
    for path in files:
        relative = path.relative_to(root).as_posix()
        if "frontmatter" in relative:
            continue
        text = path.read_text(encoding="utf-8")
        headings = _headings(root, path, text)
        candidates = _normative_candidates(text)
        for candidate in candidates:
            statement = candidate.statement
            if len(statement) < 30:
                continue
            digest = hashlib.sha1(
                f"{relative}:{candidate.line}:{candidate.offset}:{statement}".encode()
            ).hexdigest()[:12]
            identifier = f"req-{digest}"
            if identifier in seen:
                continue
            seen.add(identifier)
            clause_id = _clause_for_line(path, headings, candidate.line)
            clause_number = clause_id.removeprefix("clause-") if clause_id else None
            records.append(
                Requirement(
                    id=identifier,
                    title=f"Normative candidate {relative}:{candidate.line}",
                    statement=statement,
                    kind="detailed",
                    clause=clause_number,
                    clause_id=clause_id,
                    extraction="candidate",
                    source=SourceRef(
                        path=relative,
                        line=candidate.line,
                        end_line=candidate.end_line,
                    ),
                )
            )
    return tuple(records)


def _figures(root: Path, files: tuple[Path, ...]) -> tuple[Figure, ...]:
    records: list[Figure] = []
    seen: set[str] = set()
    for path in files:
        text = path.read_text(encoding="utf-8")
        headings = _headings(root, path, text)
        for match in re.finditer(r"(?:Figure|figure)[^\d]{0,8}(\d+)", text):
            number = match.group(1)
            identifier = f"figure-{number}"
            if identifier in seen:
                continue
            seen.add(identifier)
            records.append(
                Figure(
                    id=identifier,
                    number=number,
                    caption=f"Figure {number}",
                    clause_id=_clause_for(path, headings),
                    source=_source(root, path, text, match.start()),
                )
            )
    return tuple(records)


def _notes(root: Path, files: tuple[Path, ...]) -> tuple[Note, ...]:
    records: list[Note] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for ordinal, match in enumerate(
            re.finditer(r"\\(?:footnote|hlaNote|stdnote)\s*\{", text), start=1
        ):
            value = try_balanced_group(text, match.end() - 1)
            if value is None:
                continue
            body, end = value
            records.append(
                Note(
                    id=f"note-{slugify(path.relative_to(root).as_posix())}-{ordinal}",
                    text=_plain(body),
                    kind="footnote" if "footnote" in match.group(0) else "informative",
                    source=_source(root, path, text, match.start(), end),
                )
            )
    return tuple(records)


def _tables(root: Path, files: tuple[Path, ...]) -> tuple[Table, ...]:
    records: list[Table] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for ordinal, match in enumerate(
            re.finditer(r"\\begin\{(?:tabular|longtable|hlatable|momtabletypeset)", text), start=1
        ):
            end_marker = re.search(
                r"\\end\{(?:tabular|longtable|hlatable|momtabletypeset)\}", text[match.end() :]
            )
            end = match.end() + end_marker.end() if end_marker else len(text)
            body = text[match.end() : end]
            table_id = f"table-{slugify(path.relative_to(root).as_posix())}-{ordinal}"
            cells: list[TableCell] = []
            rows = re.split(r"\\\\", body)
            for row, row_text in enumerate(rows):
                for column, cell_text in enumerate(row_text.split("&")):
                    value = _plain(cell_text)
                    if not value:
                        continue
                    cells.append(
                        TableCell(
                            id=f"{table_id}-r{row}-c{column}",
                            table_id=table_id,
                            text=value,
                            row=row,
                            column=column,
                            source=_source(root, path, text, match.start()),
                        )
                    )
            records.append(
                Table(
                    id=table_id,
                    title=table_id,
                    caption=table_id,
                    number=str(ordinal),
                    continuation=False,
                    cells=tuple(cells),
                    source=_source(root, path, text, match.start(), end),
                    domain="omt" if "1516.2" in root.name else "generic",
                )
            )
    return tuple(records)


_write = write_json


def import_root(root: Path) -> dict[str, int]:
    files = _direct_inputs(root)
    surface_files = _surface_inputs(root)
    clauses = _clause_records(root, files)
    blocks, elements = _content(root, files)
    definitions = _definitions(root, surface_files)
    requirements = _requirements(root, surface_files)
    figures = _figures(root, surface_files)
    notes = _notes(root, surface_files)
    tables = _tables(root, surface_files)

    navigation = {
        "schema_version": 1,
        "outline": [
            {
                "id": clause.id,
                "number": clause.number,
                "title": clause.title,
                "parent_id": clause.parent_id,
                "level": clause.level,
                "source": clause.source.model_dump(mode="json"),
            }
            for clause in clauses
        ],
    }
    document = DocumentResources(root)
    _write(document.canonical_file("source-navigation.json"), navigation)
    _write(
        document.semantic_file("content-blocks.json"),
        {"schema_version": 2, "content_blocks": [item.model_dump(mode="json") for item in blocks]},
    )
    _write(
        document.semantic_file("content-elements.json"),
        {
            "schema_version": 1,
            "content_elements": [item.model_dump(mode="json") for item in elements],
        },
    )
    _write(
        document.semantic_file("definitions.json"),
        DefinitionFile(schema_version=1, definitions=definitions).model_dump(mode="json"),
    )
    _write(
        document.semantic_file("requirements.json"),
        RequirementFile(schema_version=1, requirements=requirements).model_dump(mode="json"),
    )
    _write(
        document.semantic_file("figures.json"),
        {"schema_version": 1, "figures": [item.model_dump(mode="json") for item in figures]},
    )
    _write(
        document.semantic_file("notes.json"),
        {"schema_version": 1, "notes": [item.model_dump(mode="json") for item in notes]},
    )
    _write(
        document.semantic_file("tables.json"),
        {"schema_version": 1, "tables": [item.model_dump(mode="json") for item in tables]},
    )
    return {
        "clauses": len(clauses),
        "content_blocks": len(blocks),
        "content_elements": len(elements),
        "definitions": len(definitions),
        "requirements": len(requirements),
        "figures": len(figures),
        "notes": len(notes),
        "tables": len(tables),
    }


def promote_adapters(root: Path) -> int:
    """Replace direct hand-written inputs with generated semantic adapters."""
    files = _direct_inputs(root)
    if not files:
        document = DocumentResources(root)
        payload = ContentBlockFile.model_validate(
            json.loads(document.semantic_file("content-blocks.json").read_text(encoding="utf-8"))
        )
        files = tuple(root / item.source.path for item in payload.content_blocks)
    count = 0
    for path in files:
        adapter = (
            "% Generated adapter; visible content is authored in semantic/content-blocks.json.\n"
            f"\\input{{output/semantic/content-block-content-{slugify(path.relative_to(root).as_posix())}}}\n"
        )
        path.write_text(adapter, encoding="utf-8")
        count += 1
    return count


def repair_adapters(root: Path) -> dict[str, int]:
    """Rehydrate semantic layout bodies, re-import with corrected provenance, and re-adapt."""
    path = DocumentResources(root).semantic_file("content-blocks.json")
    payload = ContentBlockFile.model_validate(json.loads(path.read_text(encoding="utf-8")))
    for block in payload.content_blocks:
        if block.layout_body is None:
            continue
        target = root / block.source.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(block.layout_body, encoding="utf-8")
    summary = import_root(root)
    summary["adapters"] = promote_adapters(root)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument(
        "--promote-adapters",
        action="store_true",
        help="replace direct main.tex inputs with generated semantic adapters",
    )
    parser.add_argument(
        "--repair-adapters",
        action="store_true",
        help="rehydrate, re-import, and re-adapt an already promoted tree",
    )
    parser.add_argument(
        "--refresh-adapters",
        action="store_true",
        help="refresh adapters from the already-imported content-block source paths",
    )
    args = parser.parse_args()
    for root in args.roots:
        if args.refresh_adapters:
            summary = {"adapters": promote_adapters(root)}
        elif args.repair_adapters:
            summary = repair_adapters(root)
        else:
            summary = import_root(root)
        if args.promote_adapters and not args.repair_adapters:
            summary["adapters"] = promote_adapters(root)
        print(root, json.dumps(summary, sort_keys=True))


if __name__ == "__main__":
    main()
