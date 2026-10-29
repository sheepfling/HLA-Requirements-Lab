"""Render a hierarchy-first, reflowable publication view.

This renderer consumes only generic semantic records and a publication
profile.  It intentionally knows nothing about HLA commands or page geometry;
faithful coordinate adapters remain a separate product.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import (
    dataclass,
)
from dataclasses import field as dataclass_field
from functools import lru_cache
from pathlib import PureWindowsPath
from types import MappingProxyType
from typing import TypedDict, TypeVar

from hla_lab.adapters.latex_renderer import tex_escape
from hla_lab.core.links import latex_anchor
from hla_lab.core.semantic_model import (
    ContentElement,
    CrossReference,
    DocumentModel,
    GraphDiagram,
    Table,
    TableCell,
    TableFamily,
)
from hla_lab.core.source_paths import is_source_frontmatter
from hla_lab.corpus.corpus_graph import (
    CorpusGraphEdge,
    CorpusGraphFinding,
    CorpusGraphNode,
    CorpusSemanticGraph,
)
from hla_lab.publication.publication_contract import PublicationProfile

__all__ = ["render_reflowable_document"]


class _ByteLayoutPart(TypedDict):
    table: Table
    has_byte_header: bool
    offsets_by_column: dict[int, tuple[int, TableCell]]
    values: dict[int, TableCell]
    roles: dict[int, TableCell]
    start: int
    end: int
    page: re.Match[str] | None


@dataclass(slots=True)
class _HierarchyNode:
    name: str = ""
    marker: str = ""
    cells: list[str] = dataclass_field(default_factory=list)
    children: list[_HierarchyNode] = dataclass_field(default_factory=list)
    index: dict[str, _HierarchyNode] = dataclass_field(default_factory=dict)


def _math_text(value: str) -> str:
    """Normalize common source subscripts for readable inline mathematics."""
    # Some legacy extracted cells contain math delimiters inside an already
    # delimited formula. They are source artefacts, not nested math groups.
    value = re.sub(r"\\([()\[\]])", r"\1", value).replace(r"\/", "/")
    value = re.sub(
        r"\\textsubscript\s*\{([^{}]+)\}",
        lambda match: rf"_{{\mathrm{{{match.group(1)}}}}}",
        value,
    )
    value = re.sub(r"\\(?:emph|textit|textbf)\s*\{([^{}]+)\}", r"\1", value)
    value = re.sub(
        r"(?<=\w)_\s*(lower|upper)\b",
        lambda match: rf"_{{\mathrm{{{match.group(1)}}}}}",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"(?<=[A-Za-z])_\s+(lower|upper)\b",
        lambda match: rf"_{{\mathrm{{{match.group(1)}}}}}",
        value,
        flags=re.IGNORECASE,
    )
    value = value.replace("@@hlabreak@@", "")
    return re.sub(r"\s+", " ", value).strip()


def _breakable_code_identifier(value: str) -> str:
    """Insert TeX break opportunities without changing identifier characters."""

    def allowbreak(_match: re.Match[str]) -> str:
        return r"\allowbreak{}"

    value = re.sub(r"(?<=\.)(?=[A-Za-z])", allowbreak, value)
    value = re.sub(r"\\_(?=[A-Za-z0-9])", lambda _match: r"\_\allowbreak{}", value)
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", allowbreak, value)
    value = re.sub(r"\bHLA(?=[a-z])", lambda _match: r"HLA\allowbreak{}", value)
    return re.sub(
        r"[A-Za-z]{12,}",
        lambda match: r"\allowbreak{}".join(
            match.group(0)[index : index + 8] for index in range(0, len(match.group(0)), 8)
        ),
        value,
    )


def _break_long_camel_case_parts(value: str) -> str:
    """Add invisible breakpoints inside long components of camel-case text."""
    return re.sub(
        r"[A-Za-z]{12,}(?=@@hlabreak@@[A-Z])",
        lambda match: "@@hlabreak@@".join(
            match.group(0)[offset : offset + 8] for offset in range(0, len(match.group(0)), 8)
        ),
        value,
    )


def _text(value: str) -> str:
    """Escape semantic prose, preserving inline math and styling source notes."""
    # A legacy plain-text handoff collapses the source ``\\leq`` command to
    # two dollar signs. Render that known artifact as the intended relation.
    value = value.replace("$$", "≤").replace("\ufffd", "—")
    value = re.sub(r"\\ldots(?:\s*\\\s*){0,3}", "…", value)
    value = re.sub(r"(?<![A-Za-z])\\?ldots\b", "…", value)
    value = re.sub(r"\buser-\s+supplied\b", "user-supplied", value, flags=re.IGNORECASE)
    value = re.sub(
        r"(?P<name>[A-Za-z_$][A-Za-z0-9_$.-]*(?:\s+[A-Z][A-Za-z0-9_$-]*)*)\s*\(\)",
        lambda match: re.sub(r"[-\s]+", "", match.group("name")) + "()",
        value,
    )
    # TeX control spaces and thin spaces sometimes survive when source macros
    # are flattened into prose. They should separate words, not print as code.
    value = value.replace(r"\ ", " ").replace(r"\,", " ")
    value = re.sub(r"(?<=\w)(<[A-Za-z][A-Za-z0-9_./-]*>)(?=\w)", r" \1 ", value)
    value = re.sub(r"\s+([,.;:])", r"\1", value)
    value = re.sub(r"(?<!\\)%\s*(?=NOTE---)", "", value, flags=re.IGNORECASE)
    for escaped, replacement in (
        (r"\$", "$"),
        (r"\_", "_"),
        (r"\&", "&"),
        (r"\%", "%"),
        (r"\#", "#"),
        (r"\{", "{"),
        (r"\}", "}"),
    ):
        value = value.replace(escaped, replacement)
    # Faithful extraction can carry TeX layout controls into semantic prose.
    # They are not document content and, when left in place, create both
    # visible residue and unbreakable overfull lines in the derivatives.
    value = value.replace(r"\textbackslash{}", " ")
    value = re.sub(r"\[l\]", " ", value)
    value = re.sub(
        r"\bskip\d+(?:\.\d+)?pt(?:\s+plus\s+\d+(?:\.\d+)?pt\s+minus\s+\d+(?:\.\d+)?pt)?",
        " ",
        value,
    )
    value = re.sub(
        r"(?<=[A-Za-z])\d+(?:\.\d+)?pt\d+(?:\.\d+)?pt\s*(?=\.)",
        "",
        value,
    )
    value = re.sub(r"\d+(?:\.\d+)?(?:pt|bp)!", " ", value)
    value = re.sub(r"\d+(?:\.\d+)?pt", " ", value)
    value = value.replace(
        "Thefollowingappliesforeachnamedvariantrecorddatatypeusingthe",
        "The following applies for each named variant record datatype using the ",
    )
    for collapsed, spaced in (
        ("sub-elementsalternative", "sub-elements alternative"),
        ("variantrecord", "variant record"),
        ("discriminantenumerators", "discriminant enumerators"),
        ("nameddiscriminant", "named discriminant"),
        ("eachenumerator", "each enumerator"),
        ("namedalternatives", "named alternatives"),
        ("ofallassociated", "of all associated"),
        ("classHLA", "class HLA"),
        ("theHLA", "the HLA"),
        ("oneinteraction", "one interaction"),
        ("eachinteraction", "each interaction"),
        ("eachnamed", "each named"),
        ("for eachnamed", "for each named"),
        ("a)The", "a) The"),
        ("b)The", "b) The"),
        ("c)The", "c) The"),
        ("d)The", "d) The"),
        ("e)The", "e) The"),
        ("f)The", "f) The"),
        ("a)Object", "a) Object"),
        ("b)Object", "b) Object"),
        ("c)Object", "c) Object"),
        ("d)Object", "d) Object"),
        ("e)Object", "e) Object"),
        ("f)Object", "f) Object"),
    ):
        value = value.replace(collapsed, spaced)
    # TeX comment markers sometimes survive in text fields as trailing
    # layout artifacts. A percent following a digit remains meaningful.
    value = re.sub(r"(?<=[A-Za-z])%(?=\s|$)", "", value)
    value = re.sub(r"(?<=\.)%(?=\s|$)", "", value)
    # Preserve camel-case technical names as one searchable token while
    # giving TeX a legal break opportunity when the token is too wide.
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", "@@hlabreak@@", value)
    value = re.sub(r"\bHLA(?=[a-z])", lambda _match: "HLA@@hlabreak@@", value)
    value = _break_long_camel_case_parts(value)
    value = re.sub(
        r"[A-Z]{12,}",
        lambda match: "@@hlabreak@@".join(
            match.group(0)[offset : offset + 8] for offset in range(0, len(match.group(0)), 8)
        ),
        value,
    )
    token_pattern = re.compile(
        r"\\\((.+?)\\\)|\$([^$]+)\$|NOTE---(.*)$",
        flags=re.IGNORECASE,
    )
    rendered: list[str] = []
    cursor = 0

    def plain(fragment: str) -> str:
        identifier = r"[A-Za-z_$][A-Za-z0-9_$]*(?:@@hlabreak@@[A-Za-z0-9_$]+)*"
        code_pattern = re.compile(rf"(?<![\w.]){identifier}(?:\.{identifier})*\([^()\n]*\)")
        url_pattern = re.compile(r"https?://[^\s<>{}]+", re.IGNORECASE)
        bnf_pattern = re.compile(r"(?<!\w)<[A-Za-z][A-Za-z0-9_./-]*>(?!\w)")
        parts: list[str] = []
        cursor = 0

        def prose(part: str) -> str:
            escaped = tex_escape(part.replace("^", r"\textasciicircum{}"))
            escaped = escaped.replace("@@hlabreak@@", r"\allowbreak{}")
            escaped = re.sub(
                r"(?<=[A-Za-z0-9])\.(?=[A-Za-z])",
                lambda match: f"{match.group(0)}\\allowbreak{{}}",
                escaped,
            )
            escaped = re.sub(r":(?=[A-Za-z0-9])", r":\\allowbreak{}", escaped)
            return escaped.replace(r"\_", r"\_\allowbreak{}")

        matches: list[tuple[int, int, str, str]] = []
        for match in code_pattern.finditer(fragment):
            invocation = match.group(0)
            callable_name = invocation.split("(", 1)[0].strip()
            arguments = invocation.split("(", 1)[1][:-1].strip()
            # Camel-cased/qualified names are code calls; no-argument calls and
            # comma-separated pseudocode functions are also unambiguous. Keep
            # parenthetical plurals such as ``attribute(s)`` in prose.
            if (
                "." in callable_name
                or "@@hlabreak@@" in callable_name
                or re.search(r"[a-z][A-Z]|[_$0-9]", callable_name)
                or not arguments
                or "," in arguments
                or callable_name.casefold() in {"get", "memcpy"}
            ):
                matches.append((match.start(), match.end(), "code", invocation))
        for match in url_pattern.finditer(fragment):
            target = match.group(0).replace("@@hlabreak@@", "").rstrip(".,;:\"'")
            if target:
                matches.append((match.start(), match.end(), "url", target))
        for match in bnf_pattern.finditer(fragment):
            matches.append((match.start(), match.end(), "bnf", match.group(0)))
        matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))
        occupied_until = -1
        for start, end, kind, token in matches:
            if start < cursor or start < occupied_until:
                continue
            preceding = fragment[cursor:start]
            parts.append(prose(preceding))
            if kind == "code" and len(token) >= 36 and preceding.rstrip().endswith(":"):
                parts.append(r"\linebreak{}")
            if kind == "url":
                parts.append(rf"\href{{\detokenize{{{token}}}}}{{\nolinkurl{{{token}}}}}")
            elif kind == "bnf":
                identifier = _breakable_code_identifier(tex_escape(token[1:-1]))
                parts.append(r"\texttt{\textless{}" + identifier + r"\textgreater{}}")
            else:
                code = re.sub(r"\s+\(", "(", token).replace("@@hlabreak@@", "")
                escaped_code = _breakable_code_identifier(tex_escape(code))
                parts.append(r"\allowbreak{}\texttt{" + escaped_code + "}")
            cursor = end
            occupied_until = end
        parts.append(prose(fragment[cursor:]))
        return "".join(parts)

    for match in token_pattern.finditer(value):
        rendered.append(plain(value[cursor : match.start()]))
        if match.group(1) is not None or match.group(2) is not None:
            formula = _math_text(match.group(1) or match.group(2) or "")
            rendered.append(rf"\ensuremath{{{formula}}}")
        else:
            note = (match.group(3) or "").strip()
            rendered.append(rf"\textit{{Note: {plain(note)}}}")
        cursor = match.end()
    rendered.append(plain(value[cursor:]))
    return (
        "".join(rendered)
        .replace("ₛ", r"\textsubscript{s}")
        .replace("∀", r"\ensuremath{\forall}")
        .replace("≤", r"\ensuremath{\leq}")
        .replace("≥", r"\ensuremath{\geq}")
        .replace("≠", r"\ensuremath{\neq}")
        .replace("∈", r"\ensuremath{\in}")
        .replace("∅", r"\ensuremath{\emptyset}")
    )


_TABLE_LABEL_ACRONYMS = MappingProxyType(
    {
        "api": "API",
        "ddm": "DDM",
        "fdd": "FDD",
        "fom": "FOM",
        "i": "I",
        "ii": "II",
        "iii": "III",
        "iv": "IV",
        "mom": "MOM",
        "omt": "OMT",
        "rti": "RTI",
    }
)


def _source_table_label(path: str) -> str:
    """Turn a source filename into a readable fallback table label."""
    filename = PureWindowsPath(path).name
    stem = re.sub(r"\.[^.]+$", "", filename)
    stem = re.sub(r"^\d+[-_]", "", stem)
    words = re.split(r"[-_]", stem)
    return (
        " ".join(
            _TABLE_LABEL_ACRONYMS.get(word.casefold(), word.capitalize()) for word in words if word
        )
        or "Source table"
    )


def _table_family_label(family: TableFamily, table: Table) -> str:
    title = family.title.strip()
    if re.fullmatch(r"(?i)OMT table family\s+.*", title):
        cells = sorted(table.cells, key=lambda cell: (cell.row or 0, cell.column or 0))
        first_row = [
            _clean_table_cell_text(cell.text).casefold() for cell in cells if cell.row == 0
        ]
        if first_row == ["class", "semantics"]:
            title = "FOM class semantics examples"
        elif first_row == ["class", "attribute", "semantics"]:
            title = "FOM attribute semantics examples"
        elif any(
            _clean_table_cell_text(cell.text).casefold() == "hlainteractionroot" for cell in cells
        ):
            title = "Object class hierarchy example"
        else:
            title = "OMT source table"
        page = re.search(r"page-(\d+)\.tex$", table.source.path)
        if page:
            title += f" — printed p. {int(page.group(1))}"
        return title
    if title.casefold().endswith(" table family"):
        title = title[: -len(" table family")].strip()
    if title and not title.casefold().startswith(("table-", "table_family-")):
        return title
    return _source_table_label(table.source.path)


def _table_display_label(table: Table, family_label: str) -> str:
    title = str(table.caption or table.title or "").replace("\ufffd", "—").strip()
    identifier = table.id
    if title and not title.casefold().startswith("table-") and title != identifier:
        return title
    number = table.number
    return f"{family_label} {number}" if number else family_label


_anchor = latex_anchor


def _link(document_id: str, record_id: str, label: str | None = None) -> str:
    return (
        f"\\hyperlink{{{tex_escape(document_id)}:{tex_escape(record_id)}}}"
        f"{{{_text(label or record_id)}}}"
    )


def _flexible_reference_title(title: str) -> str:
    """Build a title pattern tolerant of source whitespace around punctuation."""
    tokens = re.findall(r"[\w]+|[^\w\s]", title, flags=re.UNICODE)
    parts: list[str] = []
    for index, token in enumerate(tokens):
        if index:
            previous = tokens[index - 1]
            separator = r"\s+" if previous[-1:].isalnum() and token[:1].isalnum() else r"\s*"
            parts.append(separator)
        parts.append(re.escape(token))
    return "".join(parts)


def _text_with_semantic_links(
    model: DocumentModel,
    value: str,
    *,
    fallback_record_id: str | None = None,
) -> str:
    """Typeset prose while linking explicit clause and modeled-figure references."""

    def plain(fragment: str) -> str:
        if fallback_record_id and fragment:
            return _link(model.document_id, fallback_record_id, fragment)
        return _text(fragment)

    clause_ids = {clause.number: clause.id for clause in model.clauses}
    figure_ids: dict[str, str] = {}
    figure_titles: dict[str, str] = {}
    for machine in model.state_machines:
        if machine.provenance is None:
            continue
        match = re.search(
            r"\bFigure\s+(?P<number>\d+(?:\.\d+)*)\b",
            machine.provenance.caption,
            re.I,
        )
        if match is not None:
            number = match.group("number")
            figure_ids.setdefault(number, machine.id)
            figure_titles.setdefault(number, machine.title)
    for figure in model.figures:
        figure_ids.setdefault(figure.number, figure.id)
        caption = figure.caption
        title = re.sub(
            rf"^Figure\s+{re.escape(figure.number)}\s*(?:---|[\u2014\u2013-]|:)\s*",
            "",
            caption,
            flags=re.I,
        ).strip()
        if title:
            figure_titles.setdefault(figure.number, title)
    for diagram in model.graph_diagrams:
        if diagram.provenance is None:
            continue
        match = re.search(
            r"\bFigure\s+(?P<number>\d+(?:\.\d+)*)\b",
            diagram.provenance.caption,
            re.I,
        )
        if match is not None:
            number = match.group("number")
            figure_ids.setdefault(number, diagram.id)
            figure_titles.setdefault(number, diagram.title)

    links: list[tuple[int, int, str, str]] = []
    for number, target_id in figure_ids.items():
        title = figure_titles.get(number)
        title_pattern = (
            rf"(?:\s*[,\u2014\u2013-]\s*{_flexible_reference_title(title)})" if title else ""
        )
        pattern = re.compile(
            rf"\bFigure\s+{re.escape(number)}\b{title_pattern}",
            re.I,
        )
        for match in pattern.finditer(value):
            links.append((match.start(), match.end(), target_id, match.group(0)))
        # Captured prose often contains a shortened or partially clipped
        # caption (for example, ``Figure 10, Object class (i,``). Keep the
        # stable figure number clickable even when the remainder cannot be
        # matched to the modeled title.
        number_pattern = re.compile(rf"\bFigure\s+{re.escape(number)}\b", re.I)
        for match in number_pattern.finditer(value):
            if not any(start <= match.start() and match.end() <= end for start, end, *_ in links):
                links.append((match.start(), match.end(), target_id, match.group(0)))
    for match in re.finditer(
        r"\bsee(?:\s+also)?\s+(?:Clause\s+|§\s*)?"
        r"(?P<number>\d+(?:\.\d+)+)\b",
        value,
        re.I,
    ):
        target_id = clause_ids.get(match.group("number"))
        if target_id is not None:
            start, end = match.span("number")
            links.append((start, end, target_id, match.group("number")))

    if not links:
        return plain(value)
    links.sort(key=lambda item: (item[0], item[1]))
    rendered: list[str] = []
    cursor = 0
    for start, end, target_id, label in links:
        if start < cursor:
            continue
        rendered.append(plain(value[cursor:start]))
        rendered.append(_link(model.document_id, target_id, label))
        cursor = end
    rendered.append(plain(value[cursor:]))
    return "".join(rendered)


def _heading(level: int, title: str, *, numbered: bool = False) -> str:
    command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(level, "paragraph")
    suffix = "" if numbered else "*"
    title_text = _text(title)
    bookmark = (
        f"\\HLASemanticBookmark{{{level}}}{{{title_text}}}\n"
        if not numbered and level in {2, 3}
        else ""
    )
    return f"{bookmark}\\{command}{suffix}{{{title_text}}}"


def _document_section_heading(
    label: str,
    profile: PublicationProfile,
    model: DocumentModel,
) -> str:
    source_title = _document_title(profile, model)
    toc_title = _text(f"{label} — {source_title}")
    display = (
        rf"\thesection\quad {_text(label)}"
        + r"\\{\fontsize{12pt}{15pt}\selectfont "
        + _text(source_title)
        + "}"
    )
    return (
        r"\refstepcounter{section}"
        + "\n"
        + rf"\addcontentsline{{toc}}{{section}}{{\protect\numberline{{\thesection}}{toc_title}}}"
        + "\n"
        + rf"\section*{{{display}}}"
    )


def _short_requirement_identifier(requirement) -> str:
    """Build a compact human-facing ID while retaining the canonical anchor."""
    clause = requirement.clause
    if not clause and requirement.clause_id:
        clause = requirement.clause_id.removeprefix("clause-")
    label = clause or "Requirement"
    return f"{label} / L{requirement.source.line}"


def _requirement_identifier_link(model: DocumentModel, requirement) -> str:
    identifier = _text(_short_requirement_identifier(requirement))
    return (
        r"\noindent\hyperlink{"
        f"{tex_escape(model.document_id)}:{tex_escape(requirement.id)}"
        f"}}{{\\mbox{{\\texttt{{\\footnotesize {identifier}}}}}}}\\par"
    )


def _printed_source_label(source, clause: str | None = None) -> str:
    span = str(source.line)
    if source.end_line is not None and source.end_line != source.line:
        span += f"\u2013{source.end_line}"
    prefix = f"§{clause}, " if clause else ""
    page = re.search(r"page-(\d+)\.tex$", source.path)
    if page is not None:
        return f"{prefix}printed p. {int(page.group(1))}, lines {span}"
    return f"{prefix}{source.path}, lines {span}"


def _clause_title(number: str, title: str) -> str:
    """Avoid repeating a clause number recovered inside its title text."""
    if re.fullmatch(r"[A-Z]", number) and title.strip().startswith(f"Annex {number} "):
        return title.strip()
    prefixes = (f"{number}. ", f"{number} ")
    normalized = title.strip()
    if number == "3" and normalized.rstrip(".").strip() == "3":
        normalized = "Definitions, abbreviations and acronyms"
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return f"{number} {normalized}".strip()


def _clean_content_text(value: str) -> str:
    """Remove layout-adapter residue before rendering reusable prose."""
    text = value.replace("\ufffd", "—")
    # A few landscape source-page captures flatten the PDF rotation command,
    # empty-page marker, image placement coordinates, and artwork filename into
    # the same string as the surrounding prose. Remove that complete metadata
    # record while keeping any extracted figure caption that follows it.
    text = re.sub(
        r"(?i)\b\d{1,3}\s+\d{1,3}\s+\d{1,3}\s+pdf:put\s+@thispage\s+"
        r"<</Rotate\s+\d+>>\s+hla-empty\b(?:\s+hlafixedpage)?"
        r"(?:\s+-?\d+(?:\.\d+)?){0,6}\s+assets/(?:derived|extracted)/\S+"
        r"(?:\s+-\s*space\.png)?",
        " ",
        text,
    )
    text = re.sub(r"(?i)\b(?:pdf:put|@thispage|hla-empty)\b|<</Rotate\s+\d+>>", " ", text)
    if re.fullmatch(
        r"\s*Layout adapter for content-\d+-page-\d+;\s*"
        r"no independent prose surface was present\.\s*",
        text,
        re.IGNORECASE,
    ):
        return ""
    # Fixed-page captures can expose a literal NBSP code and a standalone
    # exclamation marker that the source uses as extraction/layout metadata.
    text = text.replace('"00A0', " ")
    text = re.sub(r"(?<!\S)!\s+", " ", text)
    text = re.sub(r"\buser-\s+supplied\b", "user-supplied", text, flags=re.IGNORECASE)
    # Empty source optional-argument markers and spaced brace groups can leak
    # when fixed-layout TeX is interpreted as prose. Keep populated brackets
    # and braces that are adjacent to their content, since those can be real
    # notation.
    text = re.sub(r"\[\s*\]\s*;?", " ", text)
    text = re.sub(
        r"\[\s*-?\d+(?:\.\d+)?\s*(?:pt|bp|mm|cm|in)\s*\]\s*;?\s*",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    brace_pattern = re.compile(r"(?<!\\)\{([^{}]*?)\s+\}")
    previous = None
    while previous != text:
        previous = text
        text = brace_pattern.sub(lambda match: " " + match.group(1).strip() + " ", text)
    # Fixed-layout captures also contain unmatched grouping braces at page or
    # line boundaries. Paired groups above retain their prose; remaining raw
    # braces are layout residue, while escaped braces remain literal notation.
    text = re.sub(r"(?<!\\)[{}]", " ", text)
    # The source opening carries its running standard title and page numbers
    # into the body capture. Keep the actual overview prose, not that furniture.
    text = re.sub(r"\bhla-opening\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<!\S)\d{1,3}\s+\d{1,3}\s+(?=clause:)", " ", text)
    text = re.sub(
        r"IEEE Standard for Modeling and Simulation \(M&S\) High Level Architecture "
        r"\(HLA\)[^A-Za-z]{1,3}(?:Federate Interface Specification|Framework and Rules|"
        r"Object Model Template \(OMT\) Specification)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    service_groups = (
        "Federation management",
        "Declaration management (DM)",
        "Object management",
        "Ownership management",
        "Time management",
        "Data distribution management (DMM)",
        "Support services",
    )

    def replace_service_group_list(match: re.Match[str]) -> str:
        captured = re.sub(r"\s+", " ", match.group(1)).strip()
        if all(label.casefold() in captured.casefold() for label in service_groups):
            return "The HLA service groups are " + "; ".join(service_groups) + "."
        return captured

    text = re.sub(
        r"\bhlaalphlist\b(.*?)\bhlaalphlist\b",
        replace_service_group_list,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bhlaalphlist\b", " ", text, flags=re.IGNORECASE)
    # Source captures occasionally carry editorial review notes into the
    # semantic prose stream. They remain available in source ledgers, but are
    # not publication content. Normalize the associated FDD spelling defect
    # at this boundary for every derived edition.
    text = re.sub(
        r"\s*\(Comment note - description is not part of FDD nor should it be "
        r"and thus cannot be used for rejection\.\)",
        "",
        text,
    )
    text = re.sub(r"\\?%\s*(?=(?:NOTE---|Note:))", " ", text, flags=re.IGNORECASE)
    text = text.replace("Directed interation", "Directed interaction")
    # Remove the unescaped percent signs that close captured TeX arguments.
    # Keep real numeric percentages and turn source NOTE comments into prose
    # that _text can typeset as a note.
    text = re.sub(
        r"\s*\\?%\s*(?:\d+(?:\.\d+)?pt){2}\s*NOTE---See\s+",
        " Note: See ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"(?<!\\)%\s*(?=NOTE---)", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"(?<=[A-Za-z])%(?=\s|$)", "", text)
    text = re.sub(r"(?<=\.)%(?=\s|$)", "", text)
    # Source captures can leave the escaped percent as a standalone closing
    # token after a note; actual percentages stay attached to their number.
    text = re.sub(r"(?<=\s)\\?%(?=\s|[;,.]|$)", "", text)
    body_marker = re.search(r"\bhla-body(?:-[\w-]+)?\b", text)
    if body_marker:
        text = text[body_marker.end() :]
    text = re.sub(r"\bhlafixedpage\b", " ", text)
    text = re.sub(r"\b(?:bookmark|clause):[^\s]+", " ", text)
    # Fixed-position macros contribute x, y, width, font-size and line-height
    # before each fragment. Accept integer and decimal spellings, and remove
    # the five-value run only when source prose or a clause heading follows.
    text = re.sub(
        r"(?<!\S)(?:-?\d+(?:\.\d+)?\s+){5}"
        r"(?=(?:\{\s*)?(?:\d+(?:\.\d+)*\.?\s+)?(?:[A-Za-z]|\d+\)))",
        " ",
        text,
    )
    # Some fixed-page captures omit the line-height value and leave a
    # four-number coordinate/font run before a heading or field label.
    text = re.sub(
        r"(?<!\S)-?\d{1,3}\s+\d{1,3}\.\d{2}\s+\d{3}\s+\d{1,2}"
        r"(?=\s+(?:\{\s*)?[A-Z])",
        " ",
        text,
    )
    text = re.sub(
        r"\b\d{1,3}\.\d{3}\s+(?=(?:\d+\.)+\d+\s)",
        " ",
        text,
    )
    text = re.sub(r"\bassets/(?:extracted|derived)/[^\s]+", " ", text)
    # Isolated two-decimal values left beside headings are source coordinates;
    # numeric prose with units or neighboring words is retained.
    text = re.sub(r"(?<!\S)\d{1,3}\.\d{2}(?!\S)", " ", text)
    # Some figure captures retain the image's placement coordinate and a
    # duplicate alt-text title immediately before the proper Figure caption.
    text = re.sub(
        r"(?<!\S)\d{1,3}\.\d{3}\s+(?P<number>\d{1,2})\s+"
        r"[A-Za-z][A-Za-z0-9 ,()'\u2019-]{1,80}?\s+Figure\s+(?P=number)"
        r"(?=\s*[^\w\s]|$)",
        lambda match: f"Figure {match.group('number')}",
        text,
        flags=re.IGNORECASE,
    )
    # The inheritance-tree figure is flattened into node labels in the source
    # page adapter. Keep its caption, but do not insert graph labels into prose.
    text = re.sub(
        r"\bA\s+xy\s+B\s+vw\s+C\s+zt\s+D\s+w\s+E\s+u\s+"
        r"(?=Figure\s+E\.1\b)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(
        r"\bFederation execution\s+Federate\s+Object class\s+Attribute\s+"
        r"Object instance\s+Interaction class\s+Parameter\s+Order\s+"
        r"Transportation type\s+Dimension\b",
        "Federation execution; Federate; Object class; Attribute; Object instance; "
        "Interaction class; Parameter; Order; Transportation type; Dimension",
        text,
    )
    # Geometry tokens between the two wrapped halves of an editorial note are
    # removed above; apply the same content filter once more to the now
    # normalized sentence.
    text = re.sub(
        r"\s*\(Comment note - description is not part of FDD nor should it be "
        r"and thus cannot be used for rejection\.\)",
        "",
        text,
    )
    duplicate_prefix = re.match(r"^(\d+(?:\.\d+)+)\s+\1\s+", text)
    if duplicate_prefix:
        text = text[duplicate_prefix.end(1) + 1 :]
    repeated_capture = re.fullmatch(r"(.{6,120}?)\s+\1", text, re.IGNORECASE)
    if repeated_capture:
        text = repeated_capture.group(1).strip()
    return text


def _clean_table_cell_text(value: str) -> str:
    """Remove tabular layout tokens left by source TeX extraction."""
    text = _clean_content_text(value)
    # Correct a source-table transcription typo in the standard's predefined
    # 64-bit representation name; preserve the canonical HLA type spelling.
    text = re.sub(r"\bHLAintteger64BE\b", "HLAinteger64BE", text)
    if re.fullmatch(r"\s*\)\.\s*", text):
        return ""
    # Unescaped percent signs close source TeX lines; escaped percent signs
    # remain visible data and are handled by _text.
    text = re.sub(r"(?<!\\)%", "", text)
    text = re.sub(r"(?<=-)%(?=\s|$)", "", text)
    # Table capture stores TeX row-break residue as standalone `\\%` or `\\,`.
    # These are layout markers, not values in the example column.
    if text.strip() in {r"\%", r"\,"}:
        return ""
    # A TeX row break can also be captured as a leading backslash on the next
    # JSON field; remove that marker while preserving backslashes in values.
    text = re.sub(r'(^|[\s{])\\(?=[A-Za-z_][A-Za-z0-9_]*":)', r"\1", text)
    text = re.sub(r"\s*\(cont\.\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?:\|?>[^|]+\|)+", " ", text)
    text = re.sub(r"\|\s*\d+\s*\|\s*[lcr]\s*\|", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s*\|\s*[lcr]\s*\|", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\|\s*[lcr]\s*\|", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d+\s*[lcr]\s*\|", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"@[A-Za-z0-9. +\-]+@", " ", text)
    text = re.sub(r"\[[^\]]*(?:pt|bp)[^\]]*\]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _is_clause_heading(model: DocumentModel, text: str) -> bool:
    """Avoid repeating page-local clause headings in the operations view."""
    return _normalize_clause_heading(text) in _clause_heading_labels(
        tuple((clause.number, clause.title) for clause in model.clauses)
    )


def _normalize_clause_heading(value: str) -> str:
    value = re.sub(r"^(\d+(?:\.\d+)*)\.?\s+", r"\1 ", value.strip())
    return value.casefold().strip(" .")


@lru_cache(maxsize=24)
def _clause_heading_labels(clause_specs: tuple[tuple[str, str], ...]) -> frozenset[str]:
    return frozenset(
        label
        for number, title in clause_specs
        for label in (
            _normalize_clause_heading(_clause_title(number, title)),
            _normalize_clause_heading(title),
        )
    )


@lru_cache(maxsize=24)
def _clause_heading_pattern(
    clause_specs: tuple[tuple[str, str], ...],
) -> re.Pattern[str] | None:
    markers: set[str] = set()
    for number, title in clause_specs:
        title = re.sub(rf"^{re.escape(number)}\.?\s+", "", title.strip())
        if title:
            markers.add(rf"{re.escape(number)}\.?\s+{re.escape(title)}")
    if not markers:
        return None
    ordered = sorted(markers, key=len, reverse=True)
    return re.compile(r"(?<![\w.])(?:" + "|".join(ordered) + r")(?![\w.])", re.IGNORECASE)


def _content_segments(model: DocumentModel, value: str) -> tuple[tuple[str, str], ...]:
    """Split page-spanning prose at known semantic clause-heading markers."""
    text = _clean_content_text(value)
    clause_specs = tuple((clause.number, clause.title) for clause in model.clauses)
    pattern = _clause_heading_pattern(clause_specs)
    if not text or pattern is None:
        return (("text", text),) if text else ()
    segments: list[tuple[str, str]] = []
    cursor = 0
    for match in pattern.finditer(text):
        if match.start() > cursor:
            segments.append(("text", text[cursor : match.start()].strip()))
        segments.append(("heading", match.group(0).strip()))
        cursor = match.end()
    if cursor < len(text):
        segments.append(("text", text[cursor:].strip()))
    return tuple((kind, value) for kind, value in segments if value)


def _document_title(profile: PublicationProfile, model: DocumentModel) -> str:
    try:
        title = profile.document(model.document_id).title
        # Derived-volume navigation should identify the source family without
        # repeating provenance boilerplate in every heading and TOC entry.
        return re.sub(r"\s+source material\s+—\s+", " · ", title, flags=re.IGNORECASE)
    except StopIteration:
        return model.document_id


T = TypeVar("T")


def _clause_groups(
    items: Iterable[T], *, clause_getter: Callable[[T], str | None]
) -> dict[str | None, list[T]]:
    groups: dict[str | None, list[T]] = defaultdict(list)
    for item in items:
        clause_id = clause_getter(item)
        groups[clause_id].append(item)
    return groups


def _content_element_order(element: ContentElement) -> tuple[str, int, int, str]:
    """Order page-local extraction sequences by their source page first."""
    source_path = element.source.path.replace("\\", "/").casefold()
    page = re.search(r"(?P<prefix>.*)page-(?P<number>\d+)\.tex$", source_path)
    if page is None:
        return source_path, -1, element.sequence, element.id
    return (
        page.group("prefix"),
        int(page.group("number")),
        element.sequence,
        element.id,
    )


def _clauses_with_ancestors(model: DocumentModel, clause_ids: Iterable[str | None]) -> set[str]:
    """Return relevant clauses and their ancestors for a focused projection."""
    clauses = {item.id: item for item in model.clauses}
    included: set[str] = set()
    for clause_id in clause_ids:
        while clause_id and clause_id not in included:
            included.add(clause_id)
            clause = clauses.get(clause_id)
            clause_id = clause.parent_id if clause is not None else None
    return included


def _render_clause_tree(
    model: DocumentModel,
    clause_id: str,
    render_body: Callable[[str | None], Sequence[str]],
    *,
    base_level: int = 2,
    included_clause_ids: set[str] | None = None,
) -> list[str]:
    if included_clause_ids is not None and clause_id not in included_clause_ids:
        return []
    clause = next(item for item in model.clauses if item.id == clause_id)
    heading_level = min(base_level + clause.level - 1, 4)
    lines = [
        _anchor(model.document_id, clause.id),
        _heading(
            heading_level,
            _clause_title(clause.number, clause.title),
            numbered=False,
        ),
    ]
    if heading_level == 4:
        # LaTeX paragraphs are run-in headings. End the heading explicitly so
        # the first unbreakable requirement block starts below its clause.
        lines.append(r"\mbox{}\par")
    lines.extend(render_body(clause.id))
    for child in model.children_of(clause.id):
        lines.extend(
            _render_clause_tree(
                model,
                child.id,
                render_body,
                base_level=base_level,
                included_clause_ids=included_clause_ids,
            )
        )
    return lines


def _source_definition_entries(
    model: DocumentModel,
) -> tuple[tuple[ContentElement, str, str, str], ...]:
    """Recover readable term, label, and meaning fields from legacy captures."""
    entries: list[tuple[ContentElement, str, str, str]] = []
    pattern = re.compile(
        r"^\s*\{?\s*(?P<key>[a-z][a-z0-9-]*)\s+"
        r"(?P<label>[^:]+?)\s*:\s*(?P<meaning>.+?)\s*\}?\s*$",
        re.IGNORECASE | re.DOTALL,
    )
    for element in model.content_elements:
        if not re.search(r"03-definitions-page-\d+\.tex$", element.source.path):
            continue
        text = _clean_content_text(element.text)
        match = pattern.match(text)
        if match is None:
            continue
        key = match.group("key").strip()
        label = match.group("label").strip()
        meaning = match.group("meaning").strip()
        if not meaning:
            continue
        expected_labels = {key.casefold(), key.replace("-", " ").casefold()}
        if label.casefold() not in expected_labels:
            continue
        label = key.replace("-", " ")
        label = re.sub(r"\s+", " ", label).strip()
        meaning = re.sub(r"\s+", " ", meaning).strip().rstrip("}").strip()
        if label and meaning:
            entries.append((element, key, label, meaning))
    return tuple(sorted(entries, key=lambda item: _content_element_order(item[0])))


def _source_definition_introduction(
    model: DocumentModel,
) -> tuple[ContentElement, str] | None:
    for element in model.content_elements:
        if not re.search(r"03-definitions-page-\d+\.tex$", element.source.path):
            continue
        text = _clean_content_text(element.text).lstrip("{").strip()
        if "IEEE Standards Dictionary Online" not in text:
            continue
        text = re.sub(r"\s+\d{1,2}$", "", text).strip()
        if text:
            return element, text
    return None


def _source_abbreviation_entries(
    model: DocumentModel,
) -> tuple[tuple[ContentElement, str, str, str], ...]:
    """Recover abbreviation keys and meanings from the source glossary grid."""
    entries: list[tuple[ContentElement, str, str, str]] = []
    start = re.compile(r"(?<!\S)([a-z][a-z0-9-]*)\s+([A-Z][A-Z0-9&.-]*)\s+")
    for element in model.content_elements:
        if not re.search(r"03-abbreviations-page-\d+\.tex$", element.source.path):
            continue
        text = _clean_content_text(element.text)
        if not re.match(r"^[a-z][a-z0-9-]*\s+[A-Z][A-Z0-9&.-]*\s+", text):
            continue
        matches = tuple(start.finditer(text))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            meaning = re.sub(r"\s+", " ", text[match.end() : end]).strip(" .;:")
            if meaning:
                entries.append((element, match.group(1), match.group(2), meaning))
    return tuple(entries)


def _source_abbreviation_introduction(
    model: DocumentModel,
) -> tuple[ContentElement, str] | None:
    for element in model.content_elements:
        if not re.search(r"03-abbreviations-page-\d+\.tex$", element.source.path):
            continue
        text = _clean_content_text(element.text)
        if text.casefold().startswith("the following abbreviations and acronyms"):
            return element, text
    return None


def _render_concepts(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    definitions = _clause_groups(model.definitions, clause_getter=lambda item: item.clause_id)
    extracted_definitions = _source_definition_entries(model)
    definition_introduction = _source_definition_introduction(model)
    convention_elements = tuple(
        element
        for element in model.content_elements
        if element.clause_id in {"clause-3.3", "clause-3.3.1"}
        and element.source.path.endswith("clauses-1-3/page-032.tex")
    )
    convention_children: dict[str, tuple[ContentElement, ...]] = {}
    grouped_convention_children: dict[str, list[ContentElement]] = defaultdict(list)
    for element in convention_elements:
        if element.parent_id:
            grouped_convention_children[element.parent_id].append(element)
    convention_children = {
        parent_id: tuple(sorted(items, key=_content_element_order))
        for parent_id, items in grouped_convention_children.items()
    }
    extracted_by_clause: dict[str | None, list[tuple[ContentElement, str, str, str]]] = defaultdict(
        list
    )
    for entry in extracted_definitions:
        extracted_by_clause[entry[0].clause_id].append(entry)
    included_clauses = _clauses_with_ancestors(
        model,
        (
            *(item.clause_id for item in model.definitions if _clean_content_text(item.text)),
            *(element.clause_id for element, _key, _label, _meaning in extracted_definitions),
            *(element.clause_id for element in convention_elements),
        ),
    )
    if definition_introduction and definition_introduction[0].clause_id:
        included_clauses.update(
            _clauses_with_ancestors(model, (definition_introduction[0].clause_id,))
        )

    def body(clause_id: str | None) -> list[str]:
        lines: list[str] = []
        if definition_introduction and definition_introduction[0].clause_id == clause_id:
            element, introduction = definition_introduction
            lines.extend(
                (
                    _heading(3, "Definitions"),
                    _anchor(model.document_id, element.id),
                    _text(introduction),
                    "\\par",
                )
            )
        for definition in sorted(
            definitions.get(clause_id, ()), key=lambda item: (item.term.casefold(), item.id)
        ):
            definition_text = _clean_content_text(definition.text)
            term = _clean_content_text(definition.term)
            definition_text = re.sub(r"\[\s*\]\s*;?\s*", "", definition_text)
            definition_text = re.sub(r"^\s*;\s*", "", definition_text)
            if not definition_text:
                continue
            if definition_text.casefold().startswith(term.casefold()):
                definition_text = definition_text[len(term) :].lstrip(" :.-")
            lines.extend(
                (
                    _anchor(model.document_id, definition.id),
                    f"\\textbf{{{_text(term)}}}\\par",
                    _text(definition_text),
                    "\\par",
                )
            )
        for element, _key, term, meaning in extracted_by_clause.get(clause_id, ()):
            page = re.search(r"page-(\d+)\.tex$", element.source.path)
            source_label = f"printed p. {int(page.group(1))}" if page else element.source.path
            lines.extend(
                (
                    _anchor(model.document_id, element.id),
                    f"\\textbf{{{_text(term[:1].upper() + term[1:])}}}\\par",
                    _text(meaning),
                    f"{{\\footnotesize Source: {_text(source_label)}.}}\\par",
                )
            )
        if clause_id in {"clause-3.3", "clause-3.3.1"}:
            for element in sorted(convention_elements, key=_content_element_order):
                if element.clause_id != clause_id or element.parent_id is not None:
                    continue
                lines.extend(
                    _render_content_element(
                        model,
                        element,
                        convention_children,
                        {},
                        included_clause_ids=included_clauses,
                    )
                )
                if element.kind not in {"list", "formula"}:
                    lines.append("\\par")
        return lines

    lines = [
        _document_section_heading("Concepts and terminology", profile, model),
        _text(
            "Bold terms identify concepts; each meaning follows directly below. "
            "Acronym entries show the bold abbreviation, its source key, and its meaning."
        ),
    ]
    for clause in model.root_clauses():
        lines.extend(
            _render_clause_tree(model, clause.id, body, included_clause_ids=included_clauses)
        )
    unowned = definitions.get(None, ())
    if unowned:
        lines.append(_heading(2, "Unassigned definitions"))
        lines.extend(body(None))
    abbreviations = _source_abbreviation_entries(model)
    if abbreviations:
        abbreviation_introduction = _source_abbreviation_introduction(model)
        if abbreviation_introduction:
            source_element, source_text = abbreviation_introduction
        else:
            source_element = abbreviations[0][0]
            source_text = "Abbreviations and acronyms are retained from the source glossary."
        source_page = re.search(r"page-(\d+)\.tex$", source_element.source.path)
        source_label = (
            f"printed p. {int(source_page.group(1))}" if source_page else source_element.source.path
        )
        lines.extend(
            (
                _heading(3, "Abbreviations and acronyms"),
                _anchor(model.document_id, source_element.id),
                _text(
                    f"{source_text} Source: {source_label}. Each entry gives the bold "
                    "abbreviation, its source key in monospace, and its meaning."
                ),
                r"\begin{itemize}",
            )
        )
        for _element, key, acronym, meaning in abbreviations:
            lines.append(
                f"\\item \\textbf{{{_text(acronym)}}} (\\texttt{{{_text(key)}}}) — {_text(meaning)}"
            )
        lines.append(r"\end{itemize}")
    return lines


def _render_content_element(
    model: DocumentModel,
    element: ContentElement,
    children: Mapping[str, tuple[ContentElement, ...]],
    cross_references: Mapping[str, tuple[CrossReference, ...]],
    included_clause_ids: set[str] | None = None,
) -> list[str]:
    visible_text = _clean_content_text(element.text)
    text = _text_with_semantic_links(model, visible_text)
    api_file_list = _render_api_file_list(model, element, visible_text)
    if api_file_list is not None:
        return api_file_list
    special = _render_special_content_element(
        model, element, text, children, cross_references, included_clause_ids
    )
    if special is not None:
        return special
    if not visible_text:
        return []
    lines = [_anchor(model.document_id, element.id)]
    if element.kind == "paragraph":
        return [
            *lines,
            *_render_paragraph_segments(model, element, included_clause_ids),
        ]
    return [*lines, text]


def _render_java_implementation_excerpt(
    value: str, *, model: DocumentModel | None = None
) -> list[str] | None:
    """Render a flattened Java package/class example as a distinct code block."""
    match = re.search(
        r"package\s+(?P<package>[A-Za-z_][A-Za-z0-9_.]*)\s*;\s*"
        r"public\s+final\s+class\s+(?P<class>[A-Za-z_$][A-Za-z0-9_$]*)\s+"
        r"implements\s+(?P<interface>[A-Za-z_$][A-Za-z0-9_.$\\]*)\s*\\?\{\s*"
        r"(?:\\?ldots|…|\.{3})(?:\\\s*)*\\?\}",
        value,
        re.IGNORECASE,
    )
    if match is None:
        return None

    def code_line(text: str) -> str:
        escaped = tex_escape(text)
        escaped = escaped.replace(r"\_", r"\_\allowbreak{}")
        escaped = re.sub(r"(?<=\.)(?=[A-Za-z])", lambda _match: r"\allowbreak{}", escaped)
        escaped = re.sub(r"(?<=[a-z])(?=[A-Z])", lambda _match: r"\allowbreak{}", escaped)
        return r"\noindent\texttt{" + escaped + r"}\par"

    package = match.group("package")
    class_name = match.group("class")
    interface = match.group("interface").replace(r"\_", "_")
    lines: list[str] = []
    prefix = value[: match.start()].strip()
    suffix = value[match.end() :].strip()
    if prefix:
        lines.extend(_render_labeled_narrative(prefix, model=model))
    lines.extend(
        (
            r"\begin{quote}\small",
            code_line(f"package {package};"),
            code_line(f"public final class {class_name} implements {interface} {{"),
            code_line("    …"),
            code_line("}"),
            r"\end{quote}",
        )
    )
    if suffix:
        lines.extend(_render_labeled_narrative(suffix, model=model))
    return lines


def _render_api_file_list(
    model: DocumentModel, element: ContentElement, value: str
) -> list[str] | None:
    """Give annex file inventories a clear heading and one filename per item."""
    normalized = value.replace(r"\_", "_")
    filename_pattern = re.compile(
        r"(?<![A-Za-z0-9_])"
        r"([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*"
        r"\.(?:java|proto|h|hpp|cpp|cc))\b",
        re.IGNORECASE,
    )
    filenames = tuple(filename_pattern.finditer(normalized))
    if not filenames:
        return None
    file_count = len(filenames)
    is_protocol_inventory = "federate protocol api" in normalized.casefold()
    if file_count < (3 if is_protocol_inventory else 12):
        return None

    has_inventory_introduction = "files listed below" in normalized.casefold()
    prefix = normalized[: filenames[0].start()].strip() if has_inventory_introduction else ""
    prefix = re.sub(r"\bAPI files\s*$", "", prefix, flags=re.IGNORECASE).strip()
    prefix = re.sub(r"\bhla:\s*[A-Za-z0-9_./-]+\s*$", "", prefix, flags=re.IGNORECASE).strip()
    lines = [_anchor(model.document_id, element.id)]
    if prefix:
        lines.append(_text(prefix) + r"\par\smallskip")
    if has_inventory_introduction:
        lines.append(r"\noindent\textbf{API files}\par")
    lines.extend(
        (
            r"\begin{multicols}{3}\footnotesize",
            r"\begin{itemize}[leftmargin=*,nosep]",
        )
    )
    for match in filenames:
        filename = match.group(1)
        escaped = tex_escape(filename)
        escaped = re.sub(r"(?<=[a-z])(?=[A-Z])", lambda _match: r"\allowbreak{}", escaped)
        escaped = escaped.replace(".", r".\allowbreak{}")
        lines.append(r"\item \texttt{" + escaped + "}")
    lines.extend((r"\end{itemize}", r"\end{multicols}"))
    return lines


def _source_list_kind(element: ContentElement) -> str | None:
    if element.kind != "list":
        return None
    list_type = element.text.casefold()
    if "labeleditem" in list_type:
        return "ordered"
    if "dashitem" in list_type:
        return "dash"
    return None


def _source_list_label(text: str) -> tuple[str, int, str, int] | None:
    match = re.match(r"\s*(?P<label>\d+|[A-Za-z])(?P<punct>[.)])\s*", text)
    if match is None:
        return None
    label = match.group("label")
    if label.isdigit():
        style, value = "arabic", int(label)
    else:
        style = "alpha-upper" if label.isupper() else "alpha-lower"
        value = ord(label.casefold()) - ord("a") + 1
    return style, value, match.group("punct"), match.end()


def _source_list_labels(
    element: ContentElement, children: Mapping[str, tuple[ContentElement, ...]]
) -> tuple[tuple[str, int, str, int] | None, ...]:
    return tuple(_source_list_label(child.text) for child in children.get(element.id, ()))


def _render_source_list_group(
    model: DocumentModel,
    elements: Sequence[ContentElement],
    children: Mapping[str, tuple[ContentElement, ...]],
) -> list[str]:
    """Render adjacent source list records as one semantic list."""
    kind = _source_list_kind(elements[0])
    entries = tuple(
        (element, child) for element in elements for child in children.get(element.id, ())
    )
    anchors = [_anchor(model.document_id, element.id) for element in elements]
    if kind == "ordered":
        labels = tuple(_source_list_label(child.text) for _element, child in entries)
        first_label = next((label for label in labels if label is not None), None)
        if first_label is None:
            lines = [*anchors, r"\begin{itemize}[leftmargin=*,nosep]"]
            lines.extend(
                f"\\item {_anchor(model.document_id, child.id)}"
                f"{_text_with_semantic_links(model, _clean_content_text(child.text))}"
                for _element, child in entries
            )
            return [*lines, r"\end{itemize}"]
        lines = [
            *anchors,
            r"\begin{enumerate}[leftmargin=*,nosep]",
        ]
        for (_element, child), label in zip(entries, labels, strict=True):
            child_text = _clean_content_text(child.text)
            body = child_text[label[3] :] if label is not None else child_text
            source_label = child_text[: label[3]].strip() if label is not None else ""
            item_label = f"[{_text(source_label)}]" if source_label else ""
            lines.append(
                f"\\item{item_label} {_anchor(model.document_id, child.id)}"
                f"{_text_with_semantic_links(model, body)}"
            )
        return [*lines, r"\end{enumerate}"]

    if kind == "dash":
        lines = [*anchors, r"\begin{itemize}[leftmargin=*,nosep]"]
        lines.extend(
            f"\\item {_anchor(model.document_id, child.id)}"
            f"{_text_with_semantic_links(model, _clean_content_text(child.text))}"
            for _element, child in entries
        )
        return [*lines, r"\end{itemize}"]
    return [
        *anchors,
        r"\begin{itemize}",
        *(
            f"\\item {_anchor(model.document_id, child.id)}"
            f"{_text_with_semantic_links(model, _clean_content_text(child.text))}"
            for _element, child in entries
        ),
        r"\end{itemize}",
    ]


def _render_special_content_element(
    model: DocumentModel,
    element: ContentElement,
    text: str,
    children: Mapping[str, tuple[ContentElement, ...]],
    cross_references: Mapping[str, tuple[CrossReference, ...]],
    included_clause_ids: set[str] | None = None,
) -> list[str] | None:
    if element.kind == "list":
        child_items = children.get(element.id, ())
        list_type = element.text.casefold()
        if "labeleditem" in list_type or "dashitem" in list_type:
            return _render_source_list_group(model, (element,), children)

        lines = [_anchor(model.document_id, element.id), "\\begin{itemize}"]
        for child in child_items:
            lines.extend(
                _render_content_element(
                    model, child, children, cross_references, included_clause_ids
                )
            )
        return [*lines, "\\end{itemize}"]
    if element.kind == "list-item":
        return [f"\\item {_anchor(model.document_id, element.id)}{text}"]
    if element.kind == "note":
        return [f"\\paragraph*{{Note.}} {_anchor(model.document_id, element.id)}{text}"]
    if element.kind == "footnote":
        return [f"\\footnote{{{_anchor(model.document_id, element.id)}{text}}}"]
    if element.kind == "formula":
        return [f"\\[{_anchor(model.document_id, element.id)}{text}\\]"]
    if element.kind == "cross-reference":
        links = cross_references.get(element.id, ())
        if links:
            return [
                _anchor(model.document_id, element.id),
                ", ".join(
                    f"\\hyperlink{{{tex_escape(item.target_document_id)}:"
                    f"{tex_escape(item.target_record_id)}}}"
                    f"{{{_text(item.label)}}}"
                    for item in links
                ),
            ]
    return None


def _render_paragraph_segments(
    model: DocumentModel,
    element: ContentElement,
    included_clause_ids: set[str] | None = None,
) -> list[str]:
    lines: list[str] = []
    for kind, segment in _content_segments(model, element.text):
        if kind == "text":
            enum_values = _render_resign_action_values(segment)
            if enum_values is not None:
                lines.extend(enum_values)
            else:
                java_excerpt = _render_java_implementation_excerpt(segment, model=model)
                lines.extend(
                    java_excerpt
                    if java_excerpt is not None
                    else _render_labeled_narrative(segment, model=model)
                )
            continue
        heading_number = re.match(r"\s*(\d+(?:\.\d+)*)\.?\s+", segment)
        if heading_number is None:
            continue
        number = heading_number.group(1)
        clause = next((item for item in model.clauses if item.number == number), None)
        if clause is None or (included_clause_ids and clause.id in included_clause_ids):
            continue
        parent_id = element.clause_id
        if parent_id:
            clauses_by_id = {item.id: item for item in model.clauses}
            current_id = clause.id
            descendant = False
            while current_id in clauses_by_id:
                current = clauses_by_id[current_id]
                if current.parent_id == parent_id:
                    descendant = True
                    break
                if current.parent_id is None:
                    break
                current_id = current.parent_id
            if not descendant:
                continue
        lines.append(
            r"\par\smallskip\noindent"
            + _anchor(model.document_id, clause.id)
            + r"\textbf{"
            + _text(_clause_title(clause.number, clause.title))
            + r"}\par\smallskip"
        )
    return lines


def _render_resign_action_values(value: str) -> list[str] | None:
    """Render the source's six ResignAction values as named enum values."""
    marker = re.search(
        r"The\s+ResignAction\s+enumeration\s+has\s+the\s+following\s+values\s*:",
        value,
        re.IGNORECASE,
    )
    if marker is None:
        return None
    raw_values = value[marker.end() :]
    items = [
        item.strip().replace(r"\_", "_")
        for item in re.split(r"\s+[\u2014\u2013]\s+", raw_values)
        if item.strip()
    ]
    if len(items) != 6 or not all(re.fullmatch(r"[A-Z][A-Z_]+", item) for item in items):
        return None
    prefix = value[: marker.end()].strip()
    lines = [_text(prefix), r"\begin{itemize}"]
    for item in items:
        lines.append(r"\item \texttt{" + tex_escape(item) + "}")
    lines.append(r"\end{itemize}")
    return lines


def _render_labeled_narrative(value: str, *, model: DocumentModel | None = None) -> list[str]:
    """Separate labeled rationale stages from adjacent source prose."""
    marker = re.compile(
        r"(?:^|\s+)(?:[\u2014\u2013]|\ufffd)\s*(?=(?:Ownership|Discovery\s+at\s+Federate\s+"
        r"[A-Z]|Reflection)\s*:)"
    )
    matches = tuple(marker.finditer(value))
    if not matches:
        return _render_alpha_list_segment(value, model=model)
    parts: list[tuple[str, str]] = []
    cursor = 0
    for match in matches:
        if match.start() > cursor:
            parts.append(("text", value[cursor : match.start()].strip()))
        cursor = match.end()
        label = re.match(
            r"(Ownership|Discovery\s+at\s+Federate\s+[A-Z]|Reflection)\s*:\s*",
            value[cursor:],
            re.IGNORECASE,
        )
        if label is None:
            continue
        label_text = re.sub(r"\s+", " ", label.group(1)).strip()
        content_start = cursor + label.end()
        next_marker = marker.search(value, content_start)
        content_end = next_marker.start() if next_marker else len(value)
        parts.append((label_text, value[content_start:content_end].strip()))
        cursor = content_end
    if cursor < len(value):
        tail = value[cursor:].strip()
        if tail and not any(text == tail for _label, text in parts):
            parts.append(("text", tail))
    rendered: list[str] = []
    for label, text in parts:
        if not text:
            continue

        def emit_text_part(part: str, *, current_label: str = label) -> None:
            if not part:
                return
            if current_label == "text":
                rendered.extend(_render_alpha_list_segment(part, model=model))
            else:
                rendered.extend(
                    (
                        r"\par\medskip\noindent\textbf{" + _text(current_label) + r":}\par",
                        *_render_alpha_list_segment(part, model=model),
                    )
                )

        figure_caption = re.search(
            r"\bFigure\s+(?P<number>E\.1)\s*[\u2014\u2013-]\s*"
            r"(?P<title>Example object class inheritance tree)",
            text,
            re.IGNORECASE,
        )
        if figure_caption is None:
            emit_text_part(text)
            continue
        emit_text_part(text[: figure_caption.start()].strip())
        caption = f"Figure {figure_caption.group('number')}—{figure_caption.group('title')}"
        rendered.append(r"\par\medskip\noindent\textbf{" + _text(caption) + r"}\par\smallskip")
        emit_text_part(text[figure_caption.end() :].strip())
    return rendered


def _render_alpha_list_segment(value: str, *, model: DocumentModel | None = None) -> list[str]:
    """Render flattened source lists while preserving printed labels and nesting."""

    def text(value: str) -> str:
        return _text_with_semantic_links(model, value) if model else _text(value)

    # HLA list labels are lowercase. Uppercase variables such as ``F)`` in
    # explanatory prose are not list markers and must remain in the sentence.
    marker = re.compile(r"(?<![\w.])([a-z])\)\s+(?=[^\s.,;:)])")
    matches = tuple(marker.finditer(value))
    if not matches or matches[0].group(1).casefold() != "a":
        return [text(value), "\\par"]
    prefix = value[: matches[0].start()].strip()
    if prefix and len(matches) == 1:
        return [text(value), "\\par"]

    groups: list[list[tuple[str, str]]] = []
    previous_label = 0
    for index, match in enumerate(matches):
        label = match.group(1).casefold()
        label_value = ord(label) - ord("a") + 1
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        item_text = value[match.end() : end].strip()
        if not item_text:
            continue
        if not groups or label_value <= previous_label:
            groups.append([])
        groups[-1].append((match.group(1) + ")", item_text))
        previous_label = label_value

    lines: list[str] = []
    if prefix:
        lines.extend((text(prefix), "\\par"))
    for items in groups:
        lines.append(r"\begin{enumerate}[leftmargin=*,nosep]")
        for label, item_text in items:
            numeric_marker = re.compile(r"(?<![\w.])(?P<label>\d+)\)\s+")
            numbered = tuple(numeric_marker.finditer(item_text))
            if not numbered or numbered[0].group("label") != "1":
                lines.append(f"\\item[{_text(label)}] {text(item_text)}")
                continue

            prefix_text = item_text[: numbered[0].start()].strip()
            lines.append(f"\\item[{_text(label)}] {text(prefix_text)}")
            lines.append(r"\begin{enumerate}[leftmargin=2em,nosep]")
            for index, nested in enumerate(numbered):
                end = numbered[index + 1].start() if index + 1 < len(numbered) else len(item_text)
                nested_text = item_text[nested.end() : end].strip()
                nested_label = f"{nested.group('label')})"
                lines.append(f"\\item[{_text(nested_label)}] {text(nested_text)}")
            lines.append(r"\end{enumerate}")
        lines.append(r"\end{enumerate}")
    return lines or [text(value), "\\par"]


def _same_requirement_text(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", value.casefold())

    return normalize(left) == normalize(right)


def _render_requirement_record(
    model: DocumentModel,
    requirement,
    source_label: str,
    *,
    disposition: str | None = None,
) -> list[str]:
    title = requirement.title
    if title.casefold().startswith("normative statement at "):
        title = "Normative statement"
    lines = [
        r"\par\noindent\begin{minipage}{\linewidth}",
        _anchor(model.document_id, requirement.id),
        _requirement_identifier_link(model, requirement),
    ]
    if title and not _same_requirement_text(title, requirement.statement):
        lines.append(f"\\noindent\\textbf{{Title:}} {_text_with_semantic_links(model, title)}\\par")
    lines.extend(
        (
            "\\noindent\\textbf{Statement:} "
            f"{_text_with_semantic_links(model, requirement.statement)}\\par",
            f"{{\\footnotesize Source: {_text(source_label)}}}\\par",
        )
    )
    if disposition:
        lines.append(f"\\emph{{Review disposition: {_text(disposition)}}}\\par")
    if requirement.coverage_note and requirement.coverage_note not in {
        (
            "Source-derived normative statement retained at clause scope; no modeled "
            "state transition was asserted by the conservative event matcher."
        ),
        (
            "Source refinement retained as an explicit semantic fact; the record preserves "
            "source traceability without asserting a state transition."
        ),
    }:
        lines.append(f"\\emph{{Coverage: {_text(requirement.coverage_note)}}}\\par")
    for source in requirement.additional_sources:
        lines.append(
            f"{{\\footnotesize Additional source: "
            f"{_text(_printed_source_label(source, requirement.clause))}}}\\par"
        )
    lines.append(r"\end{minipage}\par\medskip")
    return lines


def _render_operations(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    table_source_paths = {item.source.path for item in model.tables}
    operational_elements = tuple(
        item for item in model.content_elements if item.source.path not in table_source_paths
    )
    elements = {item.id: item for item in operational_elements}
    children: dict[str, tuple[ContentElement, ...]] = {}
    grouped_children: dict[str, list[ContentElement]] = defaultdict(list)
    for element in operational_elements:
        if element.parent_id:
            grouped_children[element.parent_id].append(element)
    children = {
        parent_id: tuple(sorted(items, key=_content_element_order))
        for parent_id, items in grouped_children.items()
    }
    references: dict[str, list[CrossReference]] = defaultdict(list)
    for item in model.cross_references:
        references[item.owner_id].append(item)
    cross_references = {key: tuple(value) for key, value in references.items()}
    grouped = _clause_groups(operational_elements, clause_getter=lambda item: item.clause_id)
    included_clauses = _clauses_with_ancestors(
        model,
        (
            item.clause_id
            for item in operational_elements
            if any(kind == "text" for kind, _ in _content_segments(model, item.text))
        ),
    )

    def body(clause_id: str | None) -> list[str]:
        items = sorted(
            (item for item in grouped.get(clause_id, ()) if item.parent_id is None),
            key=_content_element_order,
        )
        lines: list[str] = []
        index = 0
        while index < len(items):
            element = items[index]
            visible_text = _clean_content_text(element.text)
            if (
                not visible_text
                or _is_clause_heading(model, visible_text)
                or not any(kind == "text" for kind, _ in _content_segments(model, visible_text))
            ):
                index += 1
                continue
            list_kind = _source_list_kind(element)
            if list_kind is not None:
                list_group = [element]
                labels = _source_list_labels(element, children)
                previous_label = next((label for label in reversed(labels) if label), None)
                cursor = index + 1
                while cursor < len(items) and _source_list_kind(items[cursor]) == list_kind:
                    candidate = items[cursor]
                    candidate_labels = _source_list_labels(candidate, children)
                    if list_kind == "ordered":
                        first_label = next((label for label in candidate_labels if label), None)
                        if (
                            previous_label is None
                            or first_label is None
                            or first_label[0] != previous_label[0]
                            or first_label[2] != previous_label[2]
                            or first_label[1] <= previous_label[1]
                        ):
                            break
                        previous_label = next(
                            (label for label in reversed(candidate_labels) if label), first_label
                        )
                    list_group.append(candidate)
                    cursor += 1
                lines.extend(_render_source_list_group(model, list_group, children))
                index += len(list_group)
                continue
            lines.extend(
                _render_content_element(
                    model,
                    element,
                    children,
                    cross_references,
                    included_clause_ids=included_clauses,
                )
            )
            if element.kind not in {"list", "formula"}:
                lines.append("\\par")
            index += 1
        return lines

    lines = [
        _document_section_heading("Services and operational behavior", profile, model),
        _text(
            "The source overview is retained as context. Definitions and normative "
            "references are presented in their dedicated sections; the clauses below "
            "focus on operational behavior."
        ),
    ]
    service_fields = {
        "supplied arguments",
        "returned arguments",
        "preconditions",
        "postconditions",
        "exceptions",
        "reference state charts",
    }
    if any(
        re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", clause.title).casefold().strip(" .") in service_fields
        for clause in model.clauses
    ):
        lines.append(
            _text(
                "Within each service, the source uses separate fields: Supplied arguments "
                "are call inputs; Returned arguments are results returned to the caller; "
                "Preconditions describe what must hold before invocation; Postconditions "
                "describe the result after success; Exceptions list possible error "
                "outcomes; and Reference state charts point to related models. Lettered "
                "numbering restarts at a) within each field."
            )
        )
    for clause in model.root_clauses():
        root_title = clause.title.casefold()
        if (
            clause.number == "3"
            or "normative references" in root_title
            or ("definitions" in root_title and "abbreviations" in root_title)
        ):
            continue
        if clause.number == "1" or "overview" in root_title or "scope" in root_title:
            lines.extend((r"\paragraph*{Source context}", r"\mbox{}\par"))
        lines.extend(
            _render_clause_tree(model, clause.id, body, included_clause_ids=included_clauses)
        )
    if not elements:
        lines.append(r"\emph{No typed operational prose is currently authored.}")
    return lines


def _render_requirements(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    explicit = tuple(item for item in model.requirements if item.extraction == "explicit")
    candidates = tuple(item for item in model.requirements if item.extraction == "candidate")
    grouped = _clause_groups(explicit, clause_getter=lambda item: item.clause_id)
    clauses_by_id = {item.id: item for item in model.clauses}
    active_clauses: set[str] = set()
    for requirement in explicit:
        clause_id = requirement.clause_id
        while clause_id and clause_id not in active_clauses:
            active_clauses.add(clause_id)
            clause_id = clauses_by_id[clause_id].parent_id

    def body(clause_id: str | None) -> list[str]:
        lines: list[str] = []
        for requirement in sorted(grouped.get(clause_id, ()), key=lambda item: item.id):
            source_label = _printed_source_label(requirement.source, requirement.clause)
            lines.extend(_render_requirement_record(model, requirement, source_label))
        return lines

    lines = [
        _document_section_heading("Normative requirements", profile, model),
        _text(
            "Clause headings show each requirement's context. Every record begins "
            "with a linked source locator, followed by its normative statement and "
            "printed-source citation. A separate title appears only when it adds "
            "wording beyond the statement."
        ),
    ]
    for clause in model.root_clauses():
        lines.extend(
            _render_clause_tree(
                model,
                clause.id,
                body,
                included_clause_ids=active_clauses,
            )
        )
    if grouped.get(None):
        lines.append(_heading(2, "Unassigned requirements"))
        lines.extend(body(None))
    if candidates:
        reviews = {item.requirement_id: item for item in model.requirement_reviews}
        lines.append(_heading(2, "Source candidate review"))
        for requirement in sorted(candidates, key=lambda item: item.id):
            review = reviews.get(requirement.id)
            source_label = _printed_source_label(requirement.source, requirement.clause)
            disposition = (
                f"{review.status}: {review.reason}" if review is not None else "unreviewed"
            )
            lines.extend(
                _render_requirement_record(
                    model, requirement, source_label, disposition=disposition
                )
            )
    return lines


def _render_state_logic(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    lines = [_document_section_heading("State machines and message sequences", profile, model)]
    if not model.state_machines and not model.sequence_diagrams:
        return [*lines, r"\emph{No state machines or message sequences are currently modeled.}"]
    for machine in model.state_machines:
        lines.extend(
            (
                _anchor(model.document_id, machine.id),
                _heading(2, machine.title),
                f"\\emph{{{len(machine.states)} states; {len(machine.transitions)} transitions.}}",
                _heading(3, "States"),
                "\\begin{itemize}",
            )
        )
        lines.extend(
            f"\\item {_anchor(model.document_id, state.id)}{_text(state.label or state.id)}"
            for state in machine.states
        )
        lines.append("\\end{itemize}")
        lines.append(_heading(3, "Transitions"))
        for transition in machine.transitions:
            source = _text(transition.source_state or "initial")
            target = _text(transition.target_state or "final")
            lines.extend(
                (
                    _anchor(model.document_id, transition.id),
                    f"\\RLMinorHeadingSmall{{{_text(transition.event)}}}",
                    f"\\noindent {source} $\\rightarrow$ {target}.\\par",
                )
            )
            if transition.guard:
                lines.append(f"\\emph{{Guard: {_text(transition.guard)}}}")
    for diagram in model.sequence_diagrams:
        lines.extend(
            (
                _anchor(model.document_id, diagram.id),
                _heading(2, diagram.title),
            )
        )
        for message in sorted(diagram.messages, key=lambda item: item.order):
            lines.append(
                f"{message.order}. {_text(message.source_participant)} $\\rightarrow$ "
                f"{_text(message.target_participant)}: {_text(message.label)}\\par"
            )
    return lines


def _table_cell_text(model: DocumentModel, cell, value: str | None = None) -> str:
    text = _clean_table_cell_text(cell.text) if value is None else value
    if not text:
        return ""
    label = _text_with_semantic_links(
        model,
        text,
        fallback_record_id=cell.record_ids[0] if cell.record_ids else None,
    )
    if cell.record_ids:
        url_matches = tuple(re.finditer(r"https?://[^\s<>{}]+", text, re.IGNORECASE))
        if url_matches:
            parts: list[str] = []
            cursor = 0
            for match in url_matches:
                target = match.group(0).rstrip(".,;:\"'")
                if not target:
                    continue
                target_end = match.start() + len(target)
                before = text[cursor : match.start()]
                if before:
                    parts.append(_link(model.document_id, cell.record_ids[0], before))
                parts.append(_text(target))
                cursor = target_end
            after = text[cursor:]
            if after:
                parts.append(_link(model.document_id, cell.record_ids[0], after))
            label = "".join(parts)
    return f"{_anchor(model.document_id, cell.id)}{label}"


def _table_column_spec(widths: Sequence[float]) -> str:
    """Fit table columns and their gutters inside the available line width."""
    if not widths:
        raise ValueError("semantic tables need at least one column")
    gutter = min(0.006, 0.035 / max(1, len(widths) - 1))
    separator = rf"@{{\hspace{{{gutter:.4f}\linewidth}}}}"
    columns = separator.join(f"L{{{width:.3f}\\linewidth}}" for width in widths)
    return f"@{{}}{columns}@{{}}"


_PARAMETER_TABLE_COLUMNS = (
    ("Order", 0, 1),
    ("Transportation", 2, 3),
    ("Available dimensions", 4, 5),
    ("Data type", 6, 8),
    ("Parameter", 9, 10),
    ("Interaction", 11, 13),
)


def _parameter_table_rows(model: DocumentModel, tables: Sequence[Table]):
    """Recover the six labeled fields of the OMT parameter table."""
    headers = tuple(column[0] for column in _PARAMETER_TABLE_COLUMNS)
    rows: list[dict[str, str]] = []
    for table in tables:
        first_data_row = True
        grouped: dict[int, list] = defaultdict(list)
        for cell in table.cells:
            if cell.row is not None and cell.column is not None:
                grouped[cell.row].append(cell)
        for row_number, cells in sorted(grouped.items()):
            # The six semantic headings below replace the repeated source
            # header rows on every physical continuation page.
            if row_number < 4:
                continue
            values: dict[str, list[str]] = {header: [] for header in headers}
            for cell in sorted(cells, key=lambda item: (item.column, item.id)):
                header = next(
                    (
                        label
                        for label, first_column, last_column in _PARAMETER_TABLE_COLUMNS
                        if first_column <= cell.column <= last_column
                    ),
                    None,
                )
                rendered = _table_cell_text(model, cell)
                if header and rendered:
                    values[header].append(rendered)
            row = {header: r"\newline ".join(parts) for header, parts in values.items() if parts}
            if not row:
                continue
            if first_data_row:
                first_header = next(header for header in headers if header in row)
                row[first_header] = f"{_anchor(model.document_id, table.id)}{row[first_header]}"
                first_data_row = False
            interaction_only = set(row) == {"Interaction"}
            if interaction_only and rows and rows[-1].get("Interaction"):
                rows[-1]["Interaction"] += r"\newline " + row["Interaction"]
                continue
            parameter = row.get("Parameter", "")
            if (
                set(row) == {"Parameter"}
                and rows
                and rows[-1].get("Parameter", "").rstrip().endswith("-")
            ):
                rows[-1]["Parameter"] = rows[-1]["Parameter"].rstrip()[:-1] + parameter
                continue
            rows.append(row)
    return headers, rows


def _render_parameter_table_family(
    model: DocumentModel,
    family: TableFamily,
    tables: Sequence[Table],
    family_label: str,
) -> list[str]:
    headers, rows = _parameter_table_rows(model, tables)
    if not rows:
        return []
    title = family_label
    number = tables[0].number or ""
    if number:
        title = re.sub(
            rf"^Table\s*{re.escape(number)}\s*(?:---?|[\u2013\u2014:])\s*",
            "",
            title,
            flags=re.IGNORECASE,
        )
    widths = (0.10, 0.13, 0.14, 0.16, 0.18, 0.24)
    spec = _table_column_spec(widths)
    lines = [
        r"\begin{RLLandscapePage}",
        f"\\HLASemanticBookmark{{1}}{{{_text(family_label)}}}",
        f"\\RLInlineTableCaption{{{_text(number)}}}{{{_text(title)}}}",
        _anchor(model.document_id, family.id),
        r"\begin{longtable}{" + spec + "}",
        r"\toprule",
        " & ".join(f"\\RLTableHeaderCell{{{_text(header)}}}" for header in headers) + r" \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        " & ".join(f"\\RLTableHeaderCell{{{_text(header)}}}" for header in headers) + r" \\",
        r"\midrule",
        r"\endhead",
        r"\midrule",
        r"\endfoot",
        r"\bottomrule",
        r"\endlastfoot",
    ]
    for row in rows:
        lines.append(" & ".join(row.get(header, "") for header in headers) + r" \\")
    lines.extend((r"\bottomrule", r"\end{longtable}", r"\end{RLLandscapePage}"))
    return lines


_TABLE_HEADER_LABELS = frozenset(
    {
        "accuracy",
        "available",
        "attribute",
        "category",
        "cell",
        "class",
        "data type",
        "dimensions",
        "endian",
        "encoding",
        "enumerator",
        "example",
        "identifier",
        "interpretation",
        "interaction",
        "meaning",
        "name",
        "order",
        "parameter",
        "p s",
        "representation",
        "referenced attribute",
        "referenced class",
        "resolution",
        "semantics",
        "size in bits",
        "transportation",
        "type",
        "units",
        "values",
    }
)


def _table_cell_key(value: str) -> str:
    value = re.sub(r"(?<!\\)%", "", value).strip()
    value = re.sub(r"[^A-Za-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip().casefold()


def _table_row_groups(table: Table) -> dict[int, list[TableCell]]:
    grouped: dict[int, list[TableCell]] = defaultdict(list)
    for cell in table.cells:
        if cell.row is not None and cell.column is not None:
            grouped[cell.row].append(cell)
    return grouped


def _table_header_row(table: Table) -> tuple[int | None, tuple[TableCell, ...]]:
    """Find a source header row from its recognized semantic column labels."""
    candidates: list[tuple[int, int, tuple[TableCell, ...]]] = []
    for row_number, cells in _table_row_groups(table).items():
        recognized = tuple(
            cell for cell in cells if _table_cell_key(cell.text) in _TABLE_HEADER_LABELS
        )
        if recognized:
            candidates.append((len(recognized), row_number, recognized))
    if not candidates:
        return None, ()
    _, row_number, cells = max(candidates, key=lambda item: (item[0], -item[1]))
    return row_number, tuple(
        sorted(cells, key=lambda item: (item.column if item.column is not None else -1, item.id))
    )


def _explicit_table_schema(family: TableFamily) -> tuple[tuple[str, int, int], ...] | None:
    """Preserve known semantic spans where source layout columns are fragmented."""
    if family.id == "table-family-table-9":
        return _PARAMETER_TABLE_COLUMNS
    if family.id == "table-family-table-5":
        return (
            ("Example", 0, 5),
            ("Encoding", 6, 7),
            ("Type", 8, 10**6),
        )
    if family.id == "table-family-table-11":
        return (
            ("Name", 14, 10**6),
            ("Encoding", 0, 2),
            ("Endian", 3, 4),
            ("Interpretation", 5, 10),
            ("Size in bits", 11, 13),
        )
    if family.id == "table-family-table-10":
        return (
            ("Name", 10, 10**6),
            ("Value when unspecified", 0, 3),
            ("Normalization function", 4, 5),
            ("Dimension upper bound", 6, 7),
            ("Data type", 8, 9),
        )
    if family.id == "table-family-table-12":
        return (
            ("Name", 20, 21),
            ("Representation", 18, 19),
            ("Units", 16, 17),
            ("Resolution", 14, 15),
            ("Accuracy", 12, 13),
            ("Semantics", 0, 11),
        )
    if family.id == "table-family-table-13":
        return (
            ("Name", 8, 10**6),
            ("Semantics", 0, 1),
            ("Referenced Attribute", 2, 3),
            ("Referenced class", 4, 5),
            ("Representation", 6, 7),
        )
    if family.id == "table-family-table-14":
        return (
            ("Semantics", 0, 1),
            ("Values", 2, 3),
            ("Enumerator", 4, 5),
            ("Representation", 6, 7),
            ("Name", 8, 10**6),
        )
    return None


def _inferred_table_schema(
    family: TableFamily, tables: Sequence[Table]
) -> tuple[tuple[str, int, int], ...]:
    explicit = _explicit_table_schema(family)
    if explicit is not None:
        return explicit

    _header_row, header_cells = _table_header_row(tables[0])
    if not header_cells:
        header_cells = tuple(
            sorted(
                (cell for cell in tables[0].cells if cell.row == 0 and cell.column is not None),
                key=lambda item: (item.column, item.id),
            )
        )
    header_names = tuple(_clean_table_cell_text(cell.text) for cell in header_cells)
    header_names = tuple(name for name in header_names if name)
    if not header_names:
        return ()
    if family.id == "table-family-table-19":
        # The source table labels its columns Attribute, Semantics, Class;
        # extracted header tokens are sometimes positioned in a different order.
        return (
            ("Attribute", 0, 10**6),
            ("Semantics", 0, 10**6),
            ("Class", 0, 10**6),
        )

    header_rows = {table.id: _table_header_row(table)[0] for table in tables}
    counts: dict[int, int] = defaultdict(int)
    for table in tables:
        repeated_header = header_rows[table.id]
        for cell in table.cells:
            if cell.column is None or cell.row == repeated_header:
                continue
            if _table_cell_key(cell.text) == "continued":
                continue
            counts[cell.column] += 1
    anchors = sorted(
        column
        for column, _count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[
            : len(header_names)
        ]
    )
    if len(anchors) != len(header_names):
        anchors = [cell.column for cell in header_cells if cell.column is not None]
        anchors = anchors[: len(header_names)]
    if len(anchors) != len(header_names):
        return tuple((name, index, index) for index, name in enumerate(header_names))

    boundaries = [(anchors[index] + anchors[index + 1]) / 2 for index in range(len(anchors) - 1)]
    minimum = min(counts, default=0)
    maximum = max(counts, default=len(anchors) - 1)
    ranges: list[tuple[str, int, int]] = []
    first = min(0, minimum)
    for index, name in enumerate(header_names):
        low = first if index == 0 else int(boundaries[index - 1]) + 1
        high = maximum if index == len(header_names) - 1 else int(boundaries[index])
        ranges.append((name, low, high))
    return tuple(ranges)


def _schema_column(schema: Sequence[tuple[str, int, int]], source_column: int) -> str | None:
    for label, lower, upper in schema:
        if lower <= source_column <= upper:
            return label
    return None


def _table_local_schema(
    family: TableFamily,
    table: Table,
    fallback: Sequence[tuple[str, int, int]],
) -> tuple[tuple[tuple[str, int, int], ...], int | None]:
    """Infer column ranges from this physical page when its headers are present.

    Continuation pages in the source PDFs do not keep a stable TeX column
    index: extraction can shift a table from columns 3/6 on one page to 8/14
    later. A family-wide schema then assigns semantic cells to the wrong
    output column. Explicitly authored schemas remain authoritative.
    """
    if _explicit_table_schema(family) is not None:
        return tuple(fallback), _table_header_row(table)[0]

    expected = {_table_cell_key(label): label for label, _low, _high in fallback}
    if not expected:
        return tuple(fallback), None
    labels = tuple(expected.values())

    matching_headers: tuple[TableCell, ...] = ()
    matching_row: int | None = None
    for row_number, cells in sorted(_table_row_groups(table).items()):
        by_name: dict[str, TableCell] = {}
        for cell in cells:
            key = _table_cell_key(cell.text)
            if key in expected:
                by_name.setdefault(key, cell)
        if set(by_name) == set(expected):
            matching_row = row_number
            matching_headers = tuple(by_name[_table_cell_key(label)] for label in expected)
            break
    if matching_row is None or not matching_headers:
        return tuple(fallback), None

    anchors = [cell.column for cell in matching_headers if cell.column is not None]
    if len(anchors) != len(expected) or (
        family.id != "table-family-table-19" and anchors != sorted(anchors)
    ):
        return tuple(fallback), None
    columns = [cell.column for cell in table.cells if cell.column is not None]

    if family.id == "table-family-table-18":
        # The MOM interaction table has a wide hierarchy column. Header text
        # is centered over that area, while interaction-class names begin at
        # the first body column. Use those class-name cells as the real split.
        following_header = _following_table_header_row(table, matching_row, set(expected))
        class_columns = [
            cell.column
            for row_number, cells in _table_row_groups(table).items()
            if row_number > matching_row
            and (following_header is None or row_number < following_header)
            for cell in cells
            if cell.column is not None
            and _is_hla_class_name(_clean_table_cell_text(cell.text))
            and "." not in _clean_table_cell_text(cell.text)
        ]
        if class_columns:
            column_counts = Counter(class_columns)
            first_class_column = min(
                column_counts,
                key=lambda column: (-column_counts[column], column),
            )
            semantic_columns = [
                cell.column
                for row_number, cells in _table_row_groups(table).items()
                if row_number > matching_row
                and (following_header is None or row_number < following_header)
                for cell in cells
                if cell.column is not None
                and cell.column < first_class_column
                and _table_cell_key(cell.text) not in expected
                and not _is_hla_class_name(_clean_table_cell_text(cell.text))
            ]
            last_semantic_column = max(semantic_columns, default=first_class_column - 1)
            boundary = (last_semantic_column + first_class_column) / 2
            minimum = min(columns, default=0)
            maximum = max(columns, default=len(anchors) - 1)
            return (
                (
                    (labels[0], min(0, minimum), int(boundary)),
                    (labels[1], int(boundary) + 1, maximum),
                ),
                matching_row,
            )

    if family.id == "table-family-table-19":
        # Attribute and class names are stable identifiers in the table body;
        # their columns are more reliable than the centered, shifting headers.
        labels_by_key = {_table_cell_key(label): label for label in labels}
        attribute_label = labels_by_key["attribute"]
        semantics_label = labels_by_key["semantics"]
        class_label = labels_by_key["class"]
        attribute_columns: list[int] = []
        class_value_columns: list[int] = []
        following_header = _following_table_header_row(table, matching_row, set(expected))
        for row_number, cells in _table_row_groups(table).items():
            if row_number <= matching_row or (
                following_header is not None and row_number >= following_header
            ):
                continue
            for cell in cells:
                if cell.column is None:
                    continue
                value = _clean_table_cell_text(cell.text)
                if _is_hla_class_name(value) and "." in value:
                    class_value_columns.append(cell.column)
                elif _is_hla_class_name(value):
                    attribute_columns.append(cell.column)
        if attribute_columns and class_value_columns:
            attribute_header_column = next(
                cell.column
                for cell in matching_headers
                if _table_cell_key(cell.text) == "attribute"
            )
            class_header_column = next(
                cell.column for cell in matching_headers if _table_cell_key(cell.text) == "class"
            )
            if attribute_header_column is None or class_header_column is None:
                return tuple(fallback), None
            attribute_column = min(
                attribute_columns,
                key=lambda column: abs(column - attribute_header_column),
            )
            class_column = min(
                class_value_columns,
                key=lambda column: abs(column - class_header_column),
            )
            semantic_columns = [
                cell.column
                for row_number, cells in _table_row_groups(table).items()
                if row_number > matching_row
                for cell in cells
                if cell.column is not None
                and cell.column < attribute_column
                and _table_cell_key(cell.text) not in expected
                and not _is_hla_class_name(_clean_table_cell_text(cell.text))
            ]
            last_semantic_column = max(semantic_columns, default=attribute_column - 1)
            semantic_boundary = (last_semantic_column + attribute_column) / 2
            attribute_boundary = (attribute_column + class_column) / 2
            minimum = min(columns, default=0)
            maximum = max(columns, default=len(anchors) - 1)
            return (
                (
                    (attribute_label, int(semantic_boundary) + 1, int(attribute_boundary)),
                    (semantics_label, min(0, minimum), int(semantic_boundary)),
                    (class_label, int(attribute_boundary) + 1, maximum),
                ),
                matching_row,
            )

    minimum = min(columns, default=0)
    maximum = max(columns, default=len(anchors) - 1)
    boundaries = [(anchors[index] + anchors[index + 1]) / 2 for index in range(len(anchors) - 1)]
    ranges: list[tuple[str, int, int]] = []
    for index, label in enumerate(labels):
        lower = min(0, minimum) if index == 0 else int(boundaries[index - 1]) + 1
        upper = maximum if index == len(labels) - 1 else int(boundaries[index])
        ranges.append((label, lower, upper))
    return tuple(ranges), matching_row


def _is_hla_class_name(value: str) -> bool:
    """Return whether a captured cell contains one HLA class or attribute name."""
    value = re.sub(r"\s*\(cont\.\)\s*$", "", value.strip(), flags=re.IGNORECASE)
    value = value.rstrip(".,;:")
    return re.fullmatch(r"HLA[A-Za-z0-9_.-]+", value) is not None


def _without_semantic_anchors(value: str) -> str:
    """Return a display value without source-link target declarations."""
    return re.sub(r"\\hypertarget\{[^{}]*\}\{\}", "", value).strip()


def _following_table_header_row(
    table: Table,
    header_row: int | None,
    expected_headers: set[str],
) -> int | None:
    """Find a later table header accidentally included in the same page capture."""
    if header_row is None:
        return None
    for row_number, cells in sorted(_table_row_groups(table).items()):
        if row_number <= header_row:
            continue
        recognized = {
            _table_cell_key(cell.text)
            for cell in cells
            if _table_cell_key(cell.text) in _TABLE_HEADER_LABELS
        }
        if len(recognized) >= 2 and recognized - expected_headers:
            return row_number
    return None


def _table_cell_source_order(cell: TableCell) -> tuple[int, int, str]:
    source = getattr(cell, "source", None)
    line = getattr(source, "line", None)
    column = cell.column if cell.column is not None else -1
    return (line if line is not None else 10**9, column, cell.id)


def _join_rendered_table_cell_fragments(parts: Sequence[tuple[str, str]]) -> str:
    rendered = ""
    for value, fragment in parts:
        if not fragment:
            continue
        if rendered and re.fullmatch(r"[,.;:!?)}\]]", value.strip()):
            rendered = rendered.rstrip() + fragment
        else:
            rendered += (" " if rendered else "") + fragment
    return rendered


def _table_family_rows(
    model: DocumentModel,
    family: TableFamily,
    tables: Sequence[Table],
    schema: Sequence[tuple[str, int, int]],
) -> list[dict[str, str]]:
    headers = tuple(label for label, _low, _high in schema)
    known_headers = {_table_cell_key(label) for label in headers}
    rows: list[dict[str, str]] = []
    for table in tables:
        table_schema, header_row = _table_local_schema(family, table, schema)
        if header_row is None:
            header_row, _header_cells = _table_header_row(table)
        following_header = (
            _following_table_header_row(table, header_row, known_headers)
            if family.id == "table-family-table-18"
            else None
        )
        first_data_row = True
        for row_number, cells in sorted(_table_row_groups(table).items()):
            if following_header is not None and row_number >= following_header:
                # Page 340 ends Table 18 and starts Table 19 in one extracted
                # physical table. The next family owns rows after that header.
                continue
            if family.id == "table-family-table-10" and row_number in {0, 1, 2}:
                continue
            if family.id == "table-family-table-11" and (
                row_number in {0, 1, 2} or row_number >= 9
            ):
                continue
            if family.id == "table-family-table-12" and row_number >= 19:
                # The source page capture continues with Table 13 after row 18;
                # that second logical table has its own family and caption.
                continue
            text_values = [_clean_table_cell_text(cell.text) for cell in cells]
            nonempty = [value for value in text_values if value]
            if not nonempty or row_number == header_row:
                continue
            if all(_table_cell_key(value) in {"continued", "cont"} for value in nonempty):
                continue
            normalized = {_table_cell_key(value) for value in nonempty}
            if len(normalized) >= 2 and normalized.issubset(known_headers):
                continue
            grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
            for cell in sorted(
                cells,
                key=(
                    _table_cell_source_order
                    if family.id in {"table-family-table-12", "table-family-table-19"}
                    else lambda item: (
                        item.column if item.column is not None else -1,
                        item.id,
                    )
                ),
            ):
                if cell.column is None:
                    continue
                header = _schema_column(table_schema, cell.column)
                rendered = _table_cell_text(model, cell)
                if header and rendered:
                    grouped[header].append((_clean_table_cell_text(cell.text), rendered))
            row = {
                header: _join_rendered_table_cell_fragments(parts)
                for header, parts in grouped.items()
                if parts
            }
            if not row:
                continue
            if family.id == "table-family-table-11" and row_number in {3, 5}:
                power = 31 if row_number == 3 else 63
                semantic_anchors = "".join(
                    _anchor(model.document_id, cell.id)
                    for cell in cells
                    if cell.column is not None and 5 <= cell.column <= 10
                )
                row["Interpretation"] = (
                    semantic_anchors
                    + "Integer in the range "
                    + rf"\ensuremath{{\left[-2^{{{power}}},\,2^{{{power}}}-1\right]}}."
                )
            if family.id == "table-family-table-12" and row_number == 1:
                semantic_anchors = "".join(
                    _anchor(model.document_id, cell.id)
                    for cell in cells
                    if cell.column is not None and 0 <= cell.column <= 14
                )
                row["Semantics"] = semantic_anchors + _text(
                    "Unicode UTF-16 character (see The Unicode Standard)."
                )
            if first_data_row:
                first_header = next(header for header in headers if header in row)
                row[first_header] = f"{_anchor(model.document_id, table.id)}{row[first_header]}"
                first_data_row = False
            rows.append(row)
    return rows


def _merge_continuation_table_rows(
    family: TableFamily,
    headers: Sequence[str],
    rows: Sequence[dict[str, str]],
) -> list[dict[str, str]]:
    title = family.title.casefold()
    result: list[dict[str, str]] = []
    if family.id in {"table-family-table-18", "table-family-table-19"}:
        identifier_column = "Interaction" if family.id == "table-family-table-18" else "Attribute"
        for row in rows:
            is_new_entry = identifier_column in row and (
                family.id == "table-family-table-19" or "Semantics" in row
            )
            if is_new_entry:
                result.append(dict(row))
                continue
            if not result:
                result.append(dict(row))
                continue
            target = result[-1]
            for column, value in row.items():
                if not value:
                    continue
                previous = target.get(column, "")
                target[column] = f"{previous.rstrip()} {value.lstrip()}" if previous else value
        if family.id == "table-family-table-19":
            current_class = ""
            for row in result:
                if row.get("Class"):
                    current_class = _without_semantic_anchors(row["Class"])
                elif row.get("Attribute") and current_class:
                    row["Class"] = current_class
        return result

    if "enumerated data type" in title:
        enumerator = next((name for name in headers if _table_cell_key(name) == "enumerator"), None)
        values = next((name for name in headers if _table_cell_key(name) == "values"), None)
        name_column = next((name for name in headers if _table_cell_key(name) == "name"), None)
        representation = next(
            (name for name in headers if _table_cell_key(name) == "representation"), None
        )
        semantics = next((name for name in headers if _table_cell_key(name) == "semantics"), None)
        for row in rows:
            continuation = (
                enumerator in row
                and values in row
                and not any(
                    column in row
                    for column in (name_column, representation, semantics)
                    if column is not None
                )
            )
            if continuation and result:
                for column in (enumerator, values):
                    if column and column in row:
                        result[-1][column] = (
                            result[-1].get(column, "")
                            + (r"\newline " if result[-1].get(column) else "")
                            + row[column]
                        )
                continue
            result.append(dict(row))
        return result

    if "basic data representation" in title:
        encoding = next((name for name in headers if _table_cell_key(name) == "encoding"), None)
        for row in rows:
            if encoding in row and len(row) == 1 and result:
                result[-1][encoding] += r"\newline " + row[encoding]
            else:
                result.append(dict(row))
        return result

    if "dimension table" in title:
        name = next((header for header in headers if _table_cell_key(header) == "name"), None)
        for row in rows:
            if name not in row and result:
                for column, value in row.items():
                    result[-1][column] = (
                        result[-1].get(column, "") + (" " if result[-1].get(column) else "") + value
                    )
            else:
                result.append(dict(row))
        return result

    if "simple data type" in title:
        semantics = next((name for name in headers if _table_cell_key(name) == "semantics"), None)
        for row in rows:
            if semantics in row and len(row) == 1 and result:
                result[-1][semantics] += r"\newline " + row[semantics]
            else:
                result.append(dict(row))
        return result
    return [dict(row) for row in rows]


def _mom_interaction_table_rows(
    model: DocumentModel,
    tables: Sequence[Table],
) -> tuple[tuple[str, ...], list[dict[str, str]]]:
    """Rebuild the MOM interaction table's class hierarchy and prose fields.

    The captured PDF table uses three semantic fields, but its extracted cell
    grid contains only two recognized headers and shifts body columns across
    continuation pages. Exact HLA class names identify the hierarchy columns;
    the remaining cells form the semantics column.
    """
    headers = ("Interaction class", "Parent class", "Semantics")
    result: list[dict[str, str]] = []
    expected_headers = {"semantics", "interaction"}
    for table in tables:
        header_row = next(
            (
                row_number
                for row_number, cells in sorted(_table_row_groups(table).items())
                if expected_headers.issubset({_table_cell_key(cell.text) for cell in cells})
            ),
            None,
        )
        following_header = _following_table_header_row(table, header_row, expected_headers)
        class_cells = [
            cell
            for row_number, cells in _table_row_groups(table).items()
            if header_row is not None
            and row_number > header_row
            and (following_header is None or row_number < following_header)
            for cell in cells
            if cell.column is not None
            and _is_hla_class_name(_clean_table_cell_text(cell.text))
            and "." not in _clean_table_cell_text(cell.text)
        ]
        if not class_cells:
            continue
        column_counts = Counter(cell.column for cell in class_cells if cell.column is not None)
        interaction_column = min(
            column_counts,
            key=lambda column: (-column_counts[column], column),
        )

        for row_number, cells in sorted(_table_row_groups(table).items()):
            if (
                header_row is None
                or row_number <= header_row
                or (following_header is not None and row_number >= following_header)
            ):
                continue
            text_values = [_clean_table_cell_text(cell.text) for cell in cells]
            if not any(text_values) or all(
                _table_cell_key(value) in {"continued", "cont"} for value in text_values if value
            ):
                continue

            interaction_cells = [
                cell
                for cell in cells
                if cell.column == interaction_column
                and _is_hla_class_name(_clean_table_cell_text(cell.text))
                and "." not in _clean_table_cell_text(cell.text)
            ]
            simple_class_cells = [
                cell
                for cell in cells
                if cell.column is not None
                and _is_hla_class_name(_clean_table_cell_text(cell.text))
                and "." not in _clean_table_cell_text(cell.text)
            ]
            # The first root-class row can sit in the parent column because it
            # has no parent of its own. Keep it as an interaction class.
            if not interaction_cells and not result and len(simple_class_cells) == 1:
                interaction_cells = simple_class_cells

            fragments: dict[str, list[tuple[str, str]]] = {header: [] for header in headers}
            ordered_cells = sorted(cells, key=_table_cell_source_order)
            for cell in ordered_cells:
                if cell.column is None:
                    continue
                value = _clean_table_cell_text(cell.text)
                if not value:
                    continue
                is_class_name = _is_hla_class_name(value)
                if cell in interaction_cells:
                    label = "Interaction class"
                elif is_class_name and cell.column >= interaction_column:
                    label = "Parent class"
                else:
                    label = "Semantics"
                rendered = _table_cell_text(model, cell)
                if rendered:
                    fragments[label].append((value, rendered))

            row = {
                header: _join_rendered_table_cell_fragments(parts)
                for header, parts in fragments.items()
                if parts
            }
            starts_record = "Interaction class" in row
            if starts_record:
                if not result:
                    row["Interaction class"] = (
                        f"{_anchor(model.document_id, table.id)}{row['Interaction class']}"
                    )
                result.append(row)
                continue
            if not result:
                result.append(row)
                continue
            for header, value in row.items():
                previous = result[-1].get(header, "")
                result[-1][header] = f"{previous.rstrip()} {value.lstrip()}" if previous else value
    current_parent = ""
    for row in result:
        if row.get("Parent class"):
            current_parent = _without_semantic_anchors(row["Parent class"])
        elif row.get("Interaction class") and current_parent:
            row["Parent class"] = current_parent
    return headers, result


def _source_table_note(
    model: DocumentModel, family: TableFamily, tables: Sequence[Table]
) -> tuple[str, str] | None:
    """Reassemble the source footnotes split across table-cell captures."""
    if family.id not in {"table-family-table-11", "table-family-table-12"}:
        return None
    cells = tuple(cell for table in tables for cell in table.cells)
    note_cell = next(
        (
            cell
            for cell in cells
            if _clean_table_cell_text(cell.text).casefold().startswith("note---")
        ),
        None,
    )
    if note_cell is None:
        return None
    row_groups: dict[int, list] = defaultdict(list)
    for cell in cells:
        if cell.row is not None:
            row_groups[cell.row].append(cell)
    base = re.sub(
        r"^note---\s*", "", _clean_table_cell_text(note_cell.text), flags=re.IGNORECASE
    ).strip()
    anchors = [_anchor(model.document_id, note_cell.id)]
    if family.id == "table-family-table-11":
        citation_cells = [
            cell
            for cell in row_groups.get(9, ())
            if cell.column == 0 and "found in ieee std" in cell.text.casefold()
        ]
        continuation_cells = [cell for cell in row_groups.get(10, ()) if "1516.2-2025" in cell.text]
        citation = "found in IEEE Std"
    else:
        citation_cells = [
            cell
            for cell in row_groups.get(19, ())
            if cell.column == 12 and "found in ieee std" in cell.text.casefold()
        ]
        continuation_cells = [cell for cell in row_groups.get(20, ()) if cell.column == 29]
        citation = ""
    for cell in (*citation_cells, *continuation_cells):
        anchors.append(_anchor(model.document_id, cell.id))
    continuation = " ".join(_clean_table_cell_text(cell.text) for cell in continuation_cells)
    if family.id == "table-family-table-12" and citation_cells:
        citation = _clean_table_cell_text(citation_cells[0].text).lstrip("(").strip()
    citation = re.sub(r"\s+", " ", citation).strip()
    continuation = re.sub(r"\s+", " ", continuation).strip()
    if not citation or not continuation:
        return None
    return f"Note: {base} ({citation} {continuation}", "".join(anchors)


def _column_stacked_table_rows(
    model: DocumentModel,
    family: TableFamily,
    tables: Sequence[Table],
) -> tuple[tuple[str, ...], list[dict[str, str]]] | None:
    """Rebuild the two encoding-helper tables stored as three vertical columns.

    The source extractor records each of these tables' logical columns as an
    alternating sequence of data and header rows, with all cells at column 0.
    Treating that capture as a grid invents one PDF column per data value.
    """
    if family.id not in {"table-family-table-22", "table-family-table-26"}:
        return None

    headers: tuple[str, ...] | None = None
    rows: list[dict[str, str]] = []
    for table in tables:
        groups = _table_row_groups(table)
        data_groups = [
            (row_number, cells) for row_number, cells in sorted(groups.items()) if len(cells) > 1
        ]
        if not data_groups:
            continue
        if len(data_groups) != 3 or len({len(cells) for _, cells in data_groups}) != 1:
            return None
        header_cells = []
        for row_number, _cells in data_groups:
            matching = groups.get(row_number + 1, ())
            if len(matching) != 1:
                return None
            header_cells.append(matching[0])
        current_headers = tuple(_clean_table_cell_text(cell.text) for cell in header_cells)
        if not all(current_headers):
            return None
        if headers is not None and headers != current_headers:
            return None
        headers = current_headers

        ordered_columns = [cells for _row_number, cells in data_groups]
        for value_index in range(len(ordered_columns[0])):
            rendered = [_table_cell_text(model, cells[value_index]) for cells in ordered_columns]
            row = {header: value for header, value in zip(headers, rendered, strict=True) if value}
            if not row:
                continue
            if value_index == 0:
                first_header = headers[0]
                row[first_header] = f"{_anchor(model.document_id, table.id)}{row[first_header]}"
            rows.append(row)

    return (headers, rows) if headers is not None and rows else None


def _byte_layout_table_data(table: Table) -> _ByteLayoutPart | None:
    """Read a source byte diagram without treating offsets as table columns."""
    rows: dict[int, list[TableCell]] = defaultdict(list)
    for cell in table.cells:
        if cell.row is not None and cell.column is not None:
            rows[cell.row].append(cell)
    for cells in rows.values():
        cells.sort(key=lambda cell: cell.column if cell.column is not None else -1)

    byte_header = next(
        (cell for cell in table.cells if _clean_table_cell_text(cell.text).casefold() == "byte"),
        None,
    )
    offset_row_number = (
        byte_header.row + 1
        if byte_header is not None and byte_header.row is not None
        else min(rows, default=-1)
    )
    offset_cells = rows.get(offset_row_number, [])
    offsets_by_column: dict[int, tuple[int, TableCell]] = {}
    for cell in offset_cells:
        if cell.column is None:
            continue
        label = _clean_table_cell_text(cell.text)
        if not re.fullmatch(r"\d+", label):
            return None
        offsets_by_column[cell.column] = (int(label), cell)
    offsets = sorted(offset for offset, _cell in offsets_by_column.values())
    if len(offsets) < 4 or offsets != list(range(offsets[0], offsets[-1] + 1)):
        return None

    values: dict[int, TableCell] = {}
    for cell in rows.get(offset_row_number + 1, []):
        if cell.column is None or cell.column not in offsets_by_column:
            continue
        offset, _offset_cell = offsets_by_column[cell.column]
        if _clean_table_cell_text(cell.text):
            values[offset] = cell
    if not values:
        return None

    roles: dict[int, TableCell] = {}
    for cell in rows.get(offset_row_number + 2, []):
        if (
            cell.column is not None
            and cell.column in offsets_by_column
            and _clean_table_cell_text(cell.text)
        ):
            offset, _offset_cell = offsets_by_column[cell.column]
            roles[offset] = cell
    return {
        "table": table,
        "has_byte_header": byte_header is not None,
        "offsets_by_column": offsets_by_column,
        "values": values,
        "roles": roles,
        "start": offsets[0],
        "end": offsets[-1],
        "page": re.search(r"page-(\d+)\.tex$", table.source.path),
    }


def _byte_layout_value_text(value: str) -> str:
    value = re.sub(r"\bHLAoc-\s*tet\b", "HLAoctet", value, flags=re.IGNORECASE)
    value = re.sub(r"\bHLA\s+octet\b", "HLAoctet", value, flags=re.IGNORECASE)
    rendered = _text(value)
    if re.fullmatch(r"HLA[A-Za-z0-9_]+", value):
        return r"\texttt{" + rendered + "}"
    return rendered


def _render_byte_layout_diagram(
    model: DocumentModel,
    profile: PublicationProfile,
    parts: Sequence[tuple[TableFamily, _ByteLayoutPart]],
) -> list[str]:
    """Render offsets as labeled fields while retaining source-cell anchors."""
    all_cells: dict[int, tuple[TableCell, TableCell, TableCell | None]] = {}
    for _family, part in parts:
        offsets_by_column = part["offsets_by_column"]
        values = part["values"]
        roles = part["roles"]
        for _column, (offset, offset_cell) in offsets_by_column.items():
            value_cell = values.get(offset)
            if value_cell is not None:
                all_cells[offset] = (offset_cell, value_cell, roles.get(offset))

    sorted_offsets = sorted(all_cells)
    rows: list[str] = []
    index = 0
    while index < len(sorted_offsets):
        offset = sorted_offsets[index]
        _offset_cell, value_cell, role_cell = all_cells[offset]
        value_text = _clean_table_cell_text(value_cell.text)
        value_text = re.sub(r"\bHLAoc-\s*tet\b", "HLAoctet", value_text, flags=re.IGNORECASE)
        value_text = re.sub(r"\bHLA\s+octet\b", "HLAoctet", value_text, flags=re.IGNORECASE)
        grouped_offsets = [offset]
        grouped_values = [value_cell]
        if value_text == "0":
            next_index = index + 1
            while next_index < len(sorted_offsets):
                next_offset = sorted_offsets[next_index]
                _next_offset_cell, next_value_cell, next_role_cell = all_cells[next_offset]
                next_value = _clean_table_cell_text(next_value_cell.text)
                if (
                    next_value != "0"
                    or next_offset != grouped_offsets[-1] + 1
                    or next_role_cell is not None
                ):
                    break
                grouped_offsets.append(next_offset)
                grouped_values.append(next_value_cell)
                next_index += 1
            index = next_index
        else:
            index += 1

        offset_label = str(grouped_offsets[0])
        if len(grouped_offsets) > 1:
            offset_label += f"\u2013{grouped_offsets[-1]}"
        offset_content = "".join(
            _anchor(model.document_id, all_cells[item][0].id) for item in grouped_offsets
        ) + _text(offset_label)
        value_content = "".join(_anchor(model.document_id, cell.id) for cell in grouped_values)
        if value_text == "0" and len(grouped_offsets) > 1:
            value_content += _text("0 in each byte")
        else:
            value_content += _byte_layout_value_text(value_text)
        role_content = _table_cell_text(model, role_cell) if role_cell is not None else ""
        rows.append(f"{offset_content} & {value_content} & {role_content} \\\\")

    page_match = parts[0][1]["page"]
    page_label = f"printed p. {int(page_match.group(1))}" if page_match else None
    source_label = _document_title(profile, model)
    source_note = (
        f"Source: {source_label}, {page_label}." if page_label else f"Source: {source_label}."
    )
    source_anchors = "".join(
        _anchor(model.document_id, family.id)
        + _anchor(model.document_id, part["table"].id)
        + "".join(
            _anchor(model.document_id, cell.id)
            for cell in part["table"].cells
            if _clean_table_cell_text(cell.text).casefold() == "byte"
        )
        for family, part in parts
    )
    caption = f"Byte layout example — {page_label}" if page_label else "Byte layout example"
    columns = r"@{}L{0.18\linewidth}L{0.36\linewidth}L{0.34\linewidth}@{}"
    header_row = (
        r"\RLTableHeaderCell{Byte offset(s)}"
        r" & \RLTableHeaderCell{Encoded value}"
        r" & \RLTableHeaderCell{Field role} \\"
    )
    return [
        r"\Needspace{20\baselineskip}",
        r"\begin{samepage}",
        source_anchors,
        f"\\RLTableCaption{{{_text(caption)}}}",
        f"\\begin{{tabular}}{{{columns}}}",
        r"\toprule",
        header_row,
        r"\midrule",
        *rows,
        r"\bottomrule",
        r"\end{tabular}",
        r"\par\smallskip\noindent\emph{" + _text(source_note) + r"}\par",
        r"\end{samepage}",
    ]


def _render_hierarchy_table_family(
    model: DocumentModel,
    profile: PublicationProfile,
    family: TableFamily,
    tables: Sequence[Table],
) -> list[str]:
    """Render MOM source grids as an indented class hierarchy."""
    root = _HierarchyNode()

    def add_anchor(node: _HierarchyNode, cell: TableCell) -> None:
        if cell.id not in node.cells:
            node.cells.append(cell.id)

    def node_for(parent: _HierarchyNode, cell: TableCell, label: str) -> _HierarchyNode:
        marker_match = re.search(r"\([NPS]\)", label)
        name = label[: marker_match.start()].strip() if marker_match else label.strip()
        name = re.sub(r"\s+", " ", name)
        key = name.casefold()
        node = parent.index.get(key)
        if node is None:
            node = _HierarchyNode(
                name=name,
                marker=marker_match.group(0) if marker_match else "",
            )
            parent.index[key] = node
            parent.children.append(node)
        elif marker_match and not node.marker:
            node.marker = marker_match.group(0)
        add_anchor(node, cell)
        return node

    for table in tables:
        rows: dict[int, list[TableCell]] = defaultdict(list)
        for cell in table.cells:
            if cell.row is not None and cell.column is not None:
                rows[cell.row].append(cell)
        current_path: dict[int, _HierarchyNode] = {}
        for _row_number, cells in sorted(rows.items()):
            for cell in sorted(
                cells,
                key=lambda item: item.column if item.column is not None else -1,
            ):
                if cell.column is None:
                    continue
                label = _clean_table_cell_text(cell.text)
                if not label:
                    continue
                depth = cell.column
                marker_match = re.search(r"\([NPS]\)", label)
                continuation = "(cont.)" in label.casefold()
                remainder = re.sub(r"\([NPS]\)", "", label)
                remainder = re.sub(r"\(cont\.\)", "", remainder, flags=re.IGNORECASE).strip()
                if not remainder:
                    current = current_path.get(depth)
                    if current is not None:
                        add_anchor(current, cell)
                        if marker_match and not current.marker:
                            current.marker = marker_match.group(0)
                    continue

                parent_depth = max((item for item in current_path if item < depth), default=-1)
                parent = current_path[parent_depth] if parent_depth >= 0 else root
                node = node_for(parent, cell, label)
                current_path[depth] = node
                for deeper in tuple(current_path):
                    if deeper > depth:
                        del current_path[deeper]
                if continuation:
                    # Continuation cells name the existing path and contribute
                    # provenance; they are not additional classes.
                    continue

    source_pages = sorted(
        {
            int(match.group(1))
            for table in tables
            if (match := re.search(r"page-(\d+)\.tex$", table.source.path))
        }
    )
    if len(source_pages) == 1:
        source_page_label = f"printed p. {source_pages[0]}"
    elif source_pages:
        source_page_label = f"printed pp. {source_pages[0]}\u2013{source_pages[-1]}"
    else:
        source_page_label = ""
    source_note = (
        f"Source: {_document_title(profile, model)}, {source_page_label}."
        if source_page_label
        else f"Source: {_document_title(profile, model)}."
    )
    if family.id == "table-family-table-6":
        hierarchy_title = "MOM object-class hierarchy"
    else:
        hierarchy_title = "MOM interaction-class hierarchy"
    all_anchors = _anchor(model.document_id, family.id) + "".join(
        _anchor(model.document_id, table.id) for table in tables
    )

    def render_node(node: _HierarchyNode, depth: int = 0) -> list[str]:
        needspace = r"\Needspace{2\baselineskip}"
        indent = f"\\hspace*{{{1.35 * depth:.2f}em}}"
        label = (
            "".join(_anchor(model.document_id, cell_id) for cell_id in node.cells)
            + r"\texttt{"
            + _text(node.name)
            + "}"
        )
        if node.marker:
            label += r" \emph{" + _text(node.marker) + "}"
        result = [
            needspace,
            r"\noindent" + indent + r"\textbullet\ " + label + r"\par",
        ]
        for child in node.children:
            result.extend(render_node(child, depth + 1))
        return result

    lines = [
        r"\clearpage",
        r"\Needspace{12\baselineskip}",
        _heading(2, hierarchy_title),
        all_anchors,
        _text(
            "Indentation shows the parent and child class relationships. "
            "The source markers in parentheses are retained without reinterpretation."
        ),
    ]
    for node in root.children:
        lines.extend(render_node(node))
    lines.extend((r"\par\smallskip\noindent\emph{" + _text(source_note) + r"}\par",))
    return lines


def _table8_header_columns(table: Table) -> tuple[int, int, int] | None:
    """Return source columns for the data-type, attribute, and object headings."""
    for _row_number, cells in sorted(_table_row_groups(table).items()):
        headings = {
            _table_cell_key(cell.text): cell.column for cell in cells if cell.column is not None
        }
        if {"data type", "attribute", "object"}.issubset(headings):
            return (
                headings["data type"],
                headings["attribute"],
                headings["object"],
            )
    return None


def _join_table8_fragments(
    model: DocumentModel,
    field: str,
    fragments: Sequence[tuple[TableCell, str]],
) -> str:
    """Rejoin line-wrapped source cells while retaining source links and anchors."""
    if not fragments:
        return ""
    values = [value.strip() for _cell, value in fragments]
    separators: list[str] = []
    for index in range(1, len(values)):
        previous = values[index - 1]
        current = values[index]
        if previous.endswith("-"):
            values[index - 1] = previous[:-1]
            separators.append("")
        elif (field == "Object class" and previous.endswith(".") and current.startswith("HLA")) or (
            field in {"Data type", "Attribute", "Object class"}
            and re.fullmatch(r"[A-Za-z0-9_.-]+", previous)
            and re.fullmatch(r"[A-Za-z0-9_.-]+", current)
        ):
            separators.append("")
        else:
            separators.append(" ")
    rendered: list[str] = []
    for index, ((cell, _value), value) in enumerate(zip(fragments, values, strict=True)):
        # Table cells use source record links where present; re-render the
        # normalized fragment so a source line-break hyphen is removed first.
        label = _table_cell_text(model, cell, value)
        if index:
            rendered.append(separators[index - 1])
            if not separators[index - 1] and field in {"Data type", "Attribute", "Object class"}:
                rendered.append(r"\allowbreak{}")
        if field == "Object class" and value.endswith("."):
            label += r"\allowbreak{}"
        rendered.append(label)
    return "".join(rendered)


def _joined_table8_raw(field: str, fragments: Sequence[tuple[TableCell, str]]) -> str:
    """Return a normalized plain-text value for carried-forward class context."""
    values = [value.strip() for _cell, value in fragments]
    if not values:
        return ""
    result = values[0]
    for index in range(1, len(values)):
        previous = values[index - 1]
        current = values[index]
        if previous.endswith("-"):
            result = result[:-1]
            separator = ""
        elif field == "Object class" and previous.endswith(".") and current.startswith("HLA"):
            separator = ""
        else:
            separator = " "
        result += separator + current
    return result


def _table8_update_condition(
    model: DocumentModel,
    attribute: str,
    fragments: Sequence[tuple[TableCell, str]],
) -> str:
    """Reassemble conditions whose source cell grid splits event names."""
    conditions = {
        "HLAtimeConstrained": (
            "Whenever services Time Constrained Enabled † or Disable Time Constrained "
            "are successfully invoked (including via the HLAdisableTimeConstrained interaction)."
        ),
        "HLAtimeRegulating": (
            "Whenever services Time Regulation Enabled † or Disable Time Regulation "
            "are successfully invoked (including via the HLAdisableTimeRegulation interaction)."
        ),
        "HLAasynchronousDelivery": (
            "Whenever services Enable Asynchronous Delivery or Disable Asynchronous "
            "Delivery are successfully invoked (including via the "
            "HLAenableAsynchronousDelivery or HLAdisableAsynchronousDelivery interactions)."
        ),
        "HLAfederateState": (
            "Whenever the services Initiate Federate Save †, Federation Saved †, "
            "Federation Restore Begun †, Confirm Federation Restoration Request "
            "(success) †, or Join Federation Execution are successfully invoked. "
            "Also, after the Federation Restored † service has been invoked at all "
            "federates in the federation execution. If a joined federate is in the "
            "Federate Save in Progress state, no corresponding reflects shall be "
            "invoked at that joined federate."
        ),
        "HLAtimeManagerState": (
            "Whenever services Time Advance Request, Time Advance Request Available, "
            "Next Message Request, Next Message Request Available, Flush Queue Request, "
            "or Time Advance Grant † are successfully invoked (including via the "
            "HLAtimeAdvanceRequest, HLAtimeAdvanceRequestAvailable, "
            "HLAnextMessageRequest, HLAnextMessageRequestAvailable, or "
            "HLAflushQueueRequest interactions)."
        ),
        "HLAlastSaveName": (
            "Whenever Federation Saved † service is successfully invoked with a "
            "save-success indicator of successful."
        ),
        "HLAlastSaveTime": (
            "Whenever Federation Saved † service is successfully invoked with a "
            "save-success indicator of successful."
        ),
        "HLAnextSaveName": "Whenever Request Federation Save service is successfully invoked.",
        "HLAnextSaveTime": "Whenever Request Federation Save service is successfully invoked.",
    }
    text = conditions.get(attribute)
    if text is None:
        return _join_table8_fragments(model, "Update condition", fragments)

    anchors = "".join(_anchor(model.document_id, cell.id) for cell, _value in fragments)
    parts: list[str] = []
    cursor = 0
    for match in re.finditer(r"\bHLA[A-Za-z0-9]+\b", text):
        if match.start() > cursor:
            parts.append(_text(text[cursor : match.start()]))
        parts.append(r"\texttt{" + _text(match.group(0)) + "}")
        cursor = match.end()
    if cursor < len(text):
        parts.append(_text(text[cursor:]))
    return anchors + "".join(parts)


def _table8_attribute_rows(model: DocumentModel, tables: Sequence[Table]) -> list[dict[str, str]]:
    """Reconstruct Table 8 attributes from its page-spanning source grid."""
    source_fields = {
        "Order",
        "Transportation",
        "Available dimensions",
        "P/S",
        "D/A",
        "Data type",
        "Attribute",
        "Object class",
    }
    result: list[dict[str, str]] = []
    active_object_class = ""

    for table in tables:
        columns = _table8_header_columns(table)
        if columns is None:
            raise ValueError(f"MOM attribute table {table.id} is missing semantic headers")
        data_type_column, attribute_column, object_column = columns
        schema = (
            ("Order", 0, 1),
            ("Transportation", 2, 3),
            ("Available dimensions", 4, 5),
            ("P/S", 6, 7),
            ("D/A", 8, 9),
            ("Update condition", 10, data_type_column - 2),
            ("Update type", data_type_column - 1, data_type_column - 1),
            ("Data type", data_type_column, attribute_column - 1),
            ("Attribute", attribute_column, object_column - 1),
            ("Object class", object_column, 10**6),
        )
        header_cell = next(
            cell.row
            for cell in table.cells
            if cell.column == data_type_column
            and _table_cell_key(cell.text) == "data type"
            and cell.row is not None
        )
        header_row = header_cell
        active_record: dict[str, list[tuple[TableCell, str]]] | None = None

        def flush() -> None:
            nonlocal active_record, active_object_class
            if active_record is None:
                return
            object_fragments = active_record.get("Object class", ())
            object_class_text = _joined_table8_raw("Object class", object_fragments)
            row = {
                name: _join_table8_fragments(model, name, active_record.get(name, ()))
                for name in (
                    "Order",
                    "Transportation",
                    "Available dimensions",
                    "P/S",
                    "D/A",
                    "Data type",
                    "Attribute",
                    "Object class",
                )
            }
            update_type = _join_table8_fragments(
                model, "Update type", active_record.get("Update type", ())
            )
            attribute_text = _joined_table8_raw("Attribute", active_record.get("Attribute", ()))
            update_condition = _table8_update_condition(
                model,
                attribute_text,
                active_record.get("Update condition", ()),
            )
            update_behavior = ""
            if update_type or update_condition:
                fields = []
                if update_type:
                    fields.append(r"\textbf{Update type:} " + update_type)
                if update_condition:
                    fields.append(r"\textbf{Update condition:} " + update_condition)
                update_behavior = r"\par ".join(fields)
            row["Availability"] = r"\par ".join(
                field
                for field in (
                    r"\textbf{Dimensions:} " + row["Available dimensions"]
                    if row["Available dimensions"]
                    else "",
                    r"\textbf{P/S:} " + row["P/S"] if row["P/S"] else "",
                    r"\textbf{D/A:} " + row["D/A"] if row["D/A"] else "",
                )
                if field
            )
            row["Update behavior"] = update_behavior
            if object_class_text:
                active_object_class = object_class_text
            else:
                row["Object class"] = re.sub(
                    r"\.(?=HLA)", r".\allowbreak{}", _text(active_object_class)
                )
            if row["Attribute"]:
                row["Attribute"] = r"\texttt{" + row["Attribute"] + "}"
            if row["Data type"]:
                row["Data type"] = r"\texttt{" + row["Data type"] + "}"
            if row["Object class"]:
                row["Object class"] = r"\texttt{" + row["Object class"] + "}"
            if row["Order"]:
                result.append(row)
            active_record = None

        for row_number, cells in sorted(_table_row_groups(table).items()):
            if row_number <= header_row:
                continue
            order_cells = [
                cell
                for cell in cells
                if cell.column is not None
                and _schema_column(schema, cell.column) == "Order"
                and _clean_table_cell_text(cell.text)
            ]
            if order_cells:
                flush()
                active_record = defaultdict(list)
            if active_record is None:
                continue
            for cell in sorted(
                cells,
                key=lambda item: (item.column if item.column is not None else -1, item.id),
            ):
                if cell.column is None:
                    continue
                value = _clean_table_cell_text(cell.text)
                field = _schema_column(schema, cell.column)
                if not field or field == "Update behavior" or not value:
                    continue
                if field in source_fields or field in {"Update condition", "Update type"}:
                    active_record[field].append((cell, value))
        flush()

    missing = [index for index, row in enumerate(result, start=1) if not row["Attribute"]]
    if missing:
        raise ValueError(
            "MOM attribute table rows must retain their attribute names; "
            f"missing rendered rows: {missing}"
        )
    missing_classes = [
        index for index, row in enumerate(result, start=1) if not row["Object class"]
    ]
    if missing_classes:
        raise ValueError(
            "MOM attribute table rows must retain their object classes; "
            f"missing rendered rows: {missing_classes}"
        )
    return result


def _render_mom_attribute_table(
    model: DocumentModel,
    profile: PublicationProfile,
    family: TableFamily,
    tables: Sequence[Table],
    family_label: str,
) -> list[str]:
    rows = _table8_attribute_rows(model, tables)
    if not rows:
        return []
    display_title = _table_display_label(tables[0], family_label)
    number = tables[0].number or "8"
    title = re.sub(
        rf"^\s*Table\s*{re.escape(number)}\s*(?:---?|[\u2013\u2014\ufffd:])\s*",
        "",
        display_title,
        flags=re.IGNORECASE,
    )
    headers = (
        "Order",
        "Transportation",
        "Availability",
        "Update behavior",
        "Data type",
        "Attribute",
        "Object class",
    )
    widths = (0.065, 0.115, 0.15, 0.25, 0.095, 0.13, 0.115)
    spec = _table_column_spec(widths)
    anchors = _anchor(model.document_id, family.id) + "".join(
        _anchor(model.document_id, table.id) for table in tables
    )
    source_pages = sorted(
        {
            int(match.group(1))
            for table in tables
            if (match := re.search(r"page-(\d+)\.tex$", table.source.path))
        }
    )
    page_label = (
        f"printed pp. {source_pages[0]}--{source_pages[-1]}"
        if len(source_pages) > 1
        else f"printed p. {source_pages[0]}"
        if source_pages
        else ""
    )
    source_note = f"Source: {_document_title(profile, model)}, {page_label}.".strip()
    lines = [
        r"\clearpage",
        r"\Needspace{10\baselineskip}",
        r"\begin{RLLandscapePage}",
        f"\\HLASemanticBookmark{{2}}{{{_text(family_label)}}}",
        anchors,
        f"\\RLInlineTableCaption{{{_text(number)}}}{{{_text(title)}}}",
        _text(
            "Each row describes one management object attribute. The first two "
            "columns show delivery order and transportation type separately. "
            "Availability lists any dimensions and the source P/S and D/A values. "
            "Update type and condition are labeled separately. Object-class paths "
            "carry forward until the next source class label; wrapped source text is rejoined."
        ),
        r"\small",
        r"\begin{longtable}{" + spec + "}",
        r"\toprule",
        " & ".join(f"\\RLTableHeaderCell{{{_text(header)}}}" for header in headers) + " \\\\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        " & ".join(f"\\RLTableHeaderCell{{{_text(header)}}}" for header in headers) + " \\\\",
        r"\midrule",
        r"\endhead",
        r"\midrule",
        r"\endfoot",
        r"\bottomrule",
        r"\endlastfoot",
    ]
    for row in rows:
        lines.append(" & ".join(row.get(header, "") for header in headers) + " \\\\")
    lines.extend(
        (
            r"\bottomrule",
            r"\end{longtable}",
            r"\par\smallskip\noindent\emph{" + _text(source_note) + r"}\par",
            r"\end{RLLandscapePage}",
        )
    )
    return lines


def _render_generic_table_family(
    model: DocumentModel,
    family: TableFamily,
    tables: Sequence[Table],
    family_label: str,
) -> list[str]:
    if family.id == "table-family-table-18":
        headers, rows = _mom_interaction_table_rows(model, tables)
    else:
        stacked = _column_stacked_table_rows(model, family, tables)
        schema = _inferred_table_schema(family, tables)
        if stacked is None and not schema:
            return []
        if stacked is None:
            headers = tuple(label for label, _low, _high in schema)
            rows = _table_family_rows(model, family, tables, schema)
        else:
            headers, rows = stacked
        rows = _merge_continuation_table_rows(family, headers, rows)
    if not rows:
        return []
    if family.id == "table-family-table-10":
        incomplete = [
            index
            for index, row in enumerate(rows, start=1)
            if not row.get("Name") or not row.get("Data type")
        ]
        if incomplete:
            raise ValueError(
                "MOM dimension table rows must retain both Name and Data type values; "
                f"incomplete rendered rows: {incomplete}"
            )
    if family.id == "table-family-table-12":
        incomplete = [
            index
            for index, row in enumerate(rows, start=1)
            if not row.get("Name") or not row.get("Representation")
        ]
        if incomplete:
            raise ValueError(
                "MOM simple data type rows must retain both Name and Representation values; "
                f"incomplete rendered rows: {incomplete}"
            )
    descriptive = any(
        _table_cell_key(header) in {"semantics", "description", "meaning", "interpretation"}
        for header in headers
    )
    landscape = (
        family.id == "table-family-table-5"
        or family.id in {"table-family-table-18", "table-family-table-19"}
        or len(headers) >= 5
        or (len(headers) >= 4 and descriptive)
    )
    total = 0.96
    weights = []
    for header in headers:
        key = _table_cell_key(header)
        if family.id == "table-family-table-5" and key == "type":
            weights.append(3.5)
        elif family.id == "table-family-table-5" and key == "encoding":
            weights.append(2.0)
        elif key in {"semantics", "description", "meaning", "interpretation", "example"}:
            weights.append(3.0)
        elif key in {
            "interaction",
            "parameter",
            "encoding",
            "representation",
            "data type",
            "normalization function",
        }:
            weights.append(1.8)
        elif key in {"name", "enumerator", "values", "type"}:
            weights.append(1.2)
        else:
            weights.append(1.0)
    weight_total = sum(weights)
    spec = _table_column_spec(tuple(total * weight / weight_total for weight in weights))
    begin = r"\begin{RLLandscapePage}" if landscape else ""
    end = r"\end{RLLandscapePage}" if landscape else ""
    display_title = _table_display_label(tables[0], family_label)
    table_note = _source_table_note(model, family, tables)
    number = tables[0].number or ""
    if not number:
        number_match = re.match(r"\s*Table\s*(\d+)\b", display_title, re.IGNORECASE)
        number = number_match.group(1) if number_match else ""
    if landscape and number:
        display_title = re.sub(
            rf"^\s*Table\s*{re.escape(number)}\s*(?:---?|[\u2013\u2014\ufffd:])\s*",
            "",
            display_title,
            flags=re.IGNORECASE,
        )
        caption = f"\\RLInlineTableCaption{{{_text(number)}}}{{{_text(display_title)}}}"
    else:
        caption = f"\\RLTableCaption{{{_text(display_title)}}}"
    lines = [
        begin,
        r"\Needspace{8\baselineskip}",
        f"\\HLASemanticBookmark{{2}}{{{_text(family_label)}}}",
        _anchor(model.document_id, family.id),
        caption,
        r"\begin{longtable}{" + spec + "}",
        r"\toprule",
        " & ".join(f"\\RLTableHeaderCell{{{_text(header)}}}" for header in headers) + r" \\",
        r"\midrule",
        r"\endfirsthead",
        r"\toprule",
        " & ".join(f"\\RLTableHeaderCell{{{_text(header)}}}" for header in headers) + r" \\",
        r"\midrule",
        r"\endhead",
        r"\midrule",
        r"\endfoot",
        r"\bottomrule",
        r"\endlastfoot",
    ]
    for row in rows:
        lines.append(" & ".join(row.get(header, "") for header in headers) + r" \\")
    lines.extend((r"\bottomrule", r"\end{longtable}"))
    if table_note is not None:
        note_text, note_anchors = table_note
        lines.extend(
            (r"\par\smallskip\noindent\emph{" + note_anchors + _text(note_text) + r"}\par",)
        )
    lines.append(end)
    return [line for line in lines if line]


def _render_tables(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    lines = [
        r"\clearpage",
        r"\Needspace{8\baselineskip}",
        _heading(
            1,
            "Semantic tables",
            numbered=True,
        ),
        rf"\noindent\emph{{{_text(_document_title(profile, model))}}}\par",
    ]
    visible_tables = filter(lambda item: not is_source_frontmatter(item.source.path), model.tables)
    tables = {item.id: item for item in visible_tables}
    families = tuple(
        (family, tuple(table_id for table_id in family.table_ids if table_id in tables))
        for family in model.table_families
    )
    families = tuple((family, table_ids) for family, table_ids in families if table_ids)
    if not families:
        return [*lines, r"\emph{No semantic table families are currently authored.}"]

    byte_diagrams: dict[str, list[tuple[TableFamily, _ByteLayoutPart]]] = {}
    byte_continuations: set[str] = set()
    active_diagram: list[tuple[TableFamily, _ByteLayoutPart]] | None = None
    active_page: str | None = None
    active_end: int | None = None
    for family, table_ids in families:
        family_tables = tuple(tables[table_id] for table_id in table_ids)
        part = (
            _byte_layout_table_data(family_tables[0])
            if family.id.startswith("omt-") and len(family_tables) == 1
            else None
        )
        if part is None:
            active_diagram = None
            active_page = None
            active_end = None
            continue

        page_match = part["page"]
        source_page = page_match.group(1) if page_match else None
        if part["has_byte_header"]:
            active_diagram = [(family, part)]
            active_page = source_page
            active_end = part["end"]
            byte_diagrams[family.id] = active_diagram
        elif (
            active_diagram is not None
            and source_page is not None
            and source_page == active_page
            and active_end is not None
            and part["start"] == active_end + 1
        ):
            active_diagram.append((family, part))
            active_end = part["end"]
            byte_continuations.add(family.id)
        else:
            active_diagram = None
            active_page = None
            active_end = None

    byte_heading_added = False
    for family, table_ids in families:
        if family.id in byte_continuations:
            continue
        if family.id in byte_diagrams:
            if not byte_heading_added:
                lines.append(r"\Needspace{28\baselineskip}")
                lines.extend(
                    (
                        _heading(2, "Byte layout examples"),
                        _text(
                            "Each row gives the byte offset where an encoded value begins. "
                            "Adjacent zero bytes are grouped into a range; field roles are "
                            "shown when the source diagram labels them."
                        ),
                    )
                )
                byte_heading_added = True
            lines.extend(_render_byte_layout_diagram(model, profile, byte_diagrams[family.id]))
            continue
        family_label = _table_family_label(family, tables[table_ids[0]])
        family_tables = tuple(tables[table_id] for table_id in table_ids)
        if family.id in {"table-family-table-6", "table-family-table-7"}:
            lines.extend(_render_hierarchy_table_family(model, profile, family, family_tables))
        elif family.id == "table-family-table-8":
            lines.extend(
                _render_mom_attribute_table(
                    model,
                    profile,
                    family,
                    family_tables,
                    family_label,
                )
            )
        elif family.id == "table-family-table-9":
            lines.extend(_render_parameter_table_family(model, family, family_tables, family_label))
        else:
            lines.extend(_render_generic_table_family(model, family, family_tables, family_label))
    return lines


def _traceability_list_section(
    title: str,
    records: Sequence[T],
    render_item: Callable[[T], str],
) -> list[str]:
    if not records:
        return []
    return [
        _heading(2, title),
        "\\begin{itemize}",
        *(render_item(item) for item in records),
        "\\end{itemize}",
    ]


def _short_graph_label(value: str, limit: int = 84) -> str:
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > limit:
        value = value[: limit - 1].rstrip() + "…"
    return value


def _traceability_record_labels(
    models: Sequence[DocumentModel],
) -> dict[tuple[str, str], str]:
    """Resolve opaque graph record IDs to linked, reader-facing labels."""
    labels: dict[tuple[str, str], str] = {}
    fields = (
        "clauses",
        "definitions",
        "requirements",
        "content_elements",
        "content_blocks",
        "tables",
        "table_families",
        "references",
        "cross_references",
        "notes",
        "figures",
        "examples",
        "annexes",
        "state_machines",
        "sequence_diagrams",
        "graph_diagrams",
    )
    for model in models:
        for field in fields:
            for record in getattr(model, field, ()):
                record_id = getattr(record, "id", None)
                if not record_id:
                    continue
                if field == "clauses":
                    value = f"§{record.number} {record.title}"
                elif field == "definitions":
                    value = record.term
                elif field == "requirements":
                    value = record.title or record.statement
                elif field == "content_elements":
                    source_path = record.source.path
                    page = re.search(r"page-(\d+)\.tex$", source_path)
                    source_label = f"p. {int(page.group(1))}: " if page else "Source text: "
                    value = source_label + _clean_content_text(record.text)
                elif field == "content_blocks":
                    value = record.text or record.kind
                elif field in {"tables", "table_families"}:
                    value = record.caption or record.title if field == "tables" else record.title
                elif field == "references":
                    value = record.label or record.text
                elif field == "cross_references":
                    value = getattr(record, "label", None) or record.relation
                elif field == "notes":
                    value = getattr(record, "title", None) or getattr(record, "text", None)
                elif field == "figures":
                    value = record.caption
                elif field == "examples":
                    value = getattr(record, "title", None) or getattr(record, "description", None)
                elif field == "annexes":
                    value = f"Annex {record.letter}: {record.title}"
                else:
                    value = getattr(record, "title", None) or getattr(record, "name", None)
                if value:
                    labels[(model.document_id, record_id)] = _short_graph_label(str(value))
    return labels


def _graph_node_link_label(node, labels: Mapping[tuple[str, str], str]) -> str:
    value = labels.get((node.document_id, node.record_id)) or node.label
    if not value or value == node.record_id:
        value = node.kind.replace("-", " ")
    document = node.document_id.removeprefix("hla-").replace("-2025", "")
    return _short_graph_label(f"{document} · {value}")


def _traceability_graph_edge(
    model: DocumentModel,
    graph: CorpusSemanticGraph,
    edge: CorpusGraphEdge,
    labels: Mapping[tuple[str, str], str],
) -> str:
    source = graph.node(edge.source_node_id)
    target = graph.node(edge.target_node_id)
    return (
        f"\\item {_anchor(model.document_id, edge.id)}"
        f"{_link(source.document_id, source.record_id, _graph_node_link_label(source, labels))} "
        "$\\rightarrow$ "
        f"{_link(target.document_id, target.record_id, _graph_node_link_label(target, labels))} "
        f"({_text(edge.relation)}; {_text(edge.evidence)})"
    )


def _traceability_graph_finding(
    finding: CorpusGraphFinding,
    graph_nodes: Mapping[str, CorpusGraphNode],
    labels: Mapping[tuple[str, str], str],
) -> str:
    rendered_nodes: list[str] = []
    for node_id in finding.node_ids:
        node = graph_nodes.get(node_id)
        if node is None:
            rendered_nodes.append(_text(_short_graph_label(node_id)))
        else:
            rendered_nodes.append(
                _link(
                    node.document_id,
                    node.record_id,
                    _graph_node_link_label(node, labels),
                )
            )
    nodes = ", ".join(rendered_nodes)
    return (
        f"\\item {_text(finding.kind)} ({_text(finding.severity)}, "
        f"similarity {finding.similarity:.2f}): {_text(finding.message)} — {nodes}"
    )


def _traceability_graph_section(
    model: DocumentModel,
    graph: CorpusSemanticGraph | None,
    labels: Mapping[tuple[str, str], str],
) -> list[str]:
    if graph is None:
        return []
    lines: list[str] = []
    edges = graph.cross_document_edges(model.document_id)
    if edges:
        counts: dict[str, int] = defaultdict(int)
        for edge in edges:
            counts[edge.relation] += 1
        lines.extend(
            (
                _heading(2, "Cross-document graph summary"),
                _text(
                    f"{len(edges)} graph edges touch this document. "
                    "The count table summarizes the complete relation set. "
                    "The linked examples below open source records; candidate "
                    "matches are review data, not normative links. Complete "
                    "edge-level records are retained in the generated corpus graph."
                ),
                r"\begin{tabularx}{\linewidth}{@{}L{0.34\linewidth}L{0.13\linewidth}Y@{}}",
                r"\toprule",
                r"\RLTableHeaderCell{Relationship} & \RLTableHeaderCell{Edges} & "
                r"\RLTableHeaderCell{Graph role} \\",
                r"\midrule",
            )
        )
        for relation, count in sorted(counts.items()):
            label = relation.replace("-", " ").capitalize()
            lines.append(f"{_text(label)} & {count} & {_text(label)} " + r" \\")
        lines.extend((r"\bottomrule", r"\end{tabularx}"))
        sample_relations = tuple(
            relation
            for relation in sorted(counts)
            if relation not in {"owned-by", "contains", "member-of", "mentions", "annotates"}
        )
        graph_nodes = {node.id: node for node in graph.nodes}
        examples = [
            edge
            for relation in sample_relations
            for edge in sorted(
                (item for item in edges if item.relation == relation),
                key=lambda item: (item.source_node_id, item.target_node_id),
            )[:2]
        ]
        if examples:
            lines.extend(
                (
                    r"\par\smallskip",
                    r"\textbf{Representative links.}",
                    r"\begin{sloppypar}",
                    "\\begin{itemize}",
                )
            )
            lines.extend(_traceability_graph_edge(model, graph, edge, labels) for edge in examples)
            lines.extend(("\\end{itemize}", r"\end{sloppypar}"))
    findings = graph.findings_for(model.document_id)
    if findings:
        graph_nodes = {node.id: node for node in graph.nodes}
        lines.extend(
            (
                _heading(2, "Cross-document review findings"),
                _text(
                    f"{len(findings)} findings are available in the machine-readable graph. "
                    "The visible list is a navigational sample; review the graph artifact "
                    "for the full set."
                ),
                "\\begin{itemize}",
            )
        )
        lines.extend(
            _traceability_graph_finding(item, graph_nodes, labels) for item in findings[:120]
        )
        lines.append("\\end{itemize}")
    return lines


def _traceability_cross_reference_section(
    model: DocumentModel,
    labels: Mapping[tuple[str, str], str],
) -> list[str]:
    """Summarize source cross-references and provide a small linked sample."""
    if not model.cross_references:
        return []
    grouped: dict[str, list[CrossReference]] = defaultdict(list)
    for item in model.cross_references:
        grouped[item.relation].append(item)
    lines = [
        _heading(2, "Cross-reference summary"),
        _text(
            f"{len(model.cross_references)} source cross-references are recorded. "
            "The table counts every relation; examples link to their semantic records. "
            "The complete edge-level set remains in the generated semantic model."
        ),
        r"\begin{tabularx}{\linewidth}{@{}L{0.72\linewidth}r@{}}",
        r"\toprule",
        r"\RLTableHeaderCell{Relationship} & \RLTableHeaderCell{Edges} \\",
        r"\midrule",
    ]
    for relation, items in sorted(grouped.items()):
        lines.append(f"{_text(relation.replace('-', ' ').capitalize())} & {len(items)} " + r" \\")
    lines.extend((r"\bottomrule", r"\end{tabularx}"))
    samples = [
        item
        for _relation, items in sorted(grouped.items())[:8]
        for item in sorted(
            items,
            key=lambda value: (value.owner_id, value.target_document_id, value.target_record_id),
        )[:1]
    ]
    if samples:
        lines.extend(
            (
                r"\par\smallskip",
                r"\textbf{Representative links.}",
                r"\begin{sloppypar}",
                "\\begin{itemize}",
            )
        )
        for item in samples:
            source_label = labels.get((model.document_id, item.owner_id), "Source record")
            target_label = labels.get(
                (item.target_document_id, item.target_record_id), "Related record"
            )
            lines.append(
                f"\\item {_link(model.document_id, item.owner_id, source_label)} "
                f"$\\rightarrow$ "
                f"{_link(item.target_document_id, item.target_record_id, target_label)} "
                f"({_text(item.relation)})"
            )
        lines.extend(("\\end{itemize}", r"\end{sloppypar}"))
    return lines


def _traceability_diagram(model: DocumentModel, diagram: GraphDiagram) -> list[str]:
    lines = [
        _anchor(model.document_id, diagram.id),
        _heading(3, diagram.title),
        f"\\emph{{{len(diagram.nodes)} nodes; {len(diagram.edges)} edges.}}",
    ]
    if diagram.edges:
        lines.append("\\begin{itemize}")
        lines.extend(
            f"\\item {_anchor(model.document_id, edge.id)}"
            f"{_text(edge.source or 'free-form')} $\\rightarrow$ "
            f"{_text(edge.target or 'free-form')}: {_text(edge.label)}"
            for edge in diagram.edges
        )
        lines.append("\\end{itemize}")
    return lines


def _traceability_diagrams(model: DocumentModel) -> list[str]:
    if not model.graph_diagrams:
        return []
    lines = [_heading(2, "Conceptual and architecture diagrams")]
    for diagram in model.graph_diagrams:
        lines.extend(_traceability_diagram(model, diagram))
    return lines


def _render_traceability(
    model: DocumentModel,
    profile: PublicationProfile,
    corpus_graph: CorpusSemanticGraph | None = None,
    labels: Mapping[tuple[str, str], str] | None = None,
) -> list[str]:
    labels = labels or {}
    lines = [_document_section_heading("Traceability and dependencies", profile, model)]
    lines.extend(
        _traceability_list_section(
            "References",
            model.references,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}"
                f"{_text(item.label)}: {_text(item.text)}"
            ),
        )
    )
    lines.extend(_traceability_cross_reference_section(model, labels))
    lines.extend(_traceability_graph_section(model, corpus_graph, labels))
    lines.extend(
        _traceability_list_section(
            "Figures",
            model.figures,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}Figure {item.number}: "
                f"{_text(item.caption or 'Caption unavailable in source data.')}"
            ),
        )
    )
    lines.extend(_traceability_diagrams(model))
    lines.extend(
        _traceability_list_section(
            "Implementation seams",
            model.implementations,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}{_text(item.interface_kind)} "
                f"{_text(item.interface_name)} $\\rightarrow$ "
                f"{_text(item.implementation)} ({_text(item.status)})"
            ),
        )
    )
    lines.extend(
        _traceability_list_section(
            "Notes",
            model.notes,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}"
                f"{_text(item.text)} ({_text(item.kind)})"
            ),
        )
    )
    lines.extend(
        _traceability_list_section(
            "Examples",
            model.examples,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}Example {item.number}: "
                f"{_text(item.title)}"
            ),
        )
    )
    lines.extend(
        _traceability_list_section(
            "Annexes",
            model.annexes,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}Annex {item.letter}: "
                f"{_text(item.title)} ({_text(item.status)})"
            ),
        )
    )
    return lines


def _keep_first_hyper_targets(source: str) -> str:
    """Keep one destination per semantic ID across repeated projections.

    A source record can appear in more than one human-facing projection (for
    example, a clause may appear in both the concepts and requirements
    sections). The links share its canonical ID, so emit the destination at
    its first rendered occurrence and leave later copies as readable content.
    This avoids duplicate PDF destinations while preserving cross-references.
    """

    seen: set[str] = set()

    def keep_first(match: re.Match[str]) -> str:
        target = match.group(1)
        if target in seen:
            return ""
        seen.add(target)
        return match.group(0)

    return re.sub(r"\\hypertarget\{([^{}]+)\}\{\}", keep_first, source)


def render_reflowable_document(
    models: Iterable[DocumentModel],
    profile: PublicationProfile,
    corpus_graph: CorpusSemanticGraph | None = None,
) -> str:
    """Render the profile's sections from canonical semantic ownership."""
    ordered_models = tuple(sorted(models, key=lambda item: item.document_id))
    traceability_labels = _traceability_record_labels(ordered_models)
    renderers = {
        "concepts": _render_concepts,
        "normative": _render_requirements,
        "operations": _render_operations,
        "state-logic": _render_state_logic,
        "tables": _render_tables,
        "traceability": lambda model, current_profile: _render_traceability(
            model, current_profile, corpus_graph, traceability_labels
        ),
    }
    lines = [
        "% Generated reflowable view; edit semantic source instead.",
        _heading(1, profile.title, numbered=True),
    ]
    if profile.subtitle:
        lines.append(f"\\emph{{{_text(profile.subtitle)}}}")
    lines.append(_text(profile.description))
    for section in profile.sections:
        projection = profile.projection(section.projection_id)
        lines.append(r"\clearpage")
        if projection.renderer == "scope":
            lines.extend((_heading(section.level + 1, section.title), "\\begin{itemize}"))
            lines.extend(
                f"\\item {_text(_document_title(profile, model))} ({_text(model.document_id)})"
                for model in ordered_models
            )
            lines.append("\\end{itemize}")
            continue
        renderer = renderers.get(projection.renderer)
        if renderer is None:
            lines.extend(
                (_heading(section.level + 1, section.title), r"\emph{No renderer registered.}")
            )
            continue
        for model in ordered_models:
            lines.append(r"\clearpage")
            lines.extend(renderer(model, profile))
    return _keep_first_hyper_targets("\n\n".join(lines) + "\n")
