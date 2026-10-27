"""Render a hierarchy-first, reflowable publication view.

This renderer consumes only generic semantic records and a publication
profile.  It intentionally knows nothing about HLA commands or page geometry;
faithful coordinate adapters remain a separate product.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import PureWindowsPath
from types import MappingProxyType
from typing import TypeVar

from hla_lab.adapters.latex_renderer import tex_escape
from hla_lab.core.links import latex_anchor
from hla_lab.core.semantic_model import (
    ContentElement,
    CrossReference,
    DocumentModel,
    GraphDiagram,
    Table,
    TableFamily,
)
from hla_lab.core.source_paths import is_source_frontmatter
from hla_lab.corpus.corpus_graph import (
    CorpusGraphEdge,
    CorpusGraphFinding,
    CorpusSemanticGraph,
)
from hla_lab.publication.publication_contract import PublicationProfile

__all__ = ["render_reflowable_document"]


def _text(value: str) -> str:
    """Escape semantic text while accepting source-style escaped punctuation."""
    # The legacy 2010 handoff's plain-text extractor can collapse ``\\leq``
    # into two dollar signs. Keep that comparison readable and outside an
    # accidental empty math span in the reflowed publication.
    value = value.replace("$$", r"\\leq ")
    for escaped, plain in (
        (r"\$", "$"),
        (r"\_", "_"),
        (r"\&", "&"),
        (r"\%", "%"),
        (r"\#", "#"),
        (r"\{", "{"),
        (r"\}", "}"),
    ):
        value = value.replace(escaped, plain)
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
    # Preserve camel-case technical names as one searchable token while
    # giving TeX a legal break opportunity when the token is too wide.
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", "@@hlabreak@@", value)
    # Reflowed 2010 prose still contains page-layout fragments and equations
    # whose delimiters may be split across source surfaces. Render those as
    # safe readable text; the faithful products retain the original TeX math.
    rendered = tex_escape(value.replace("$", "").replace("^", r"\textasciicircum{}"))
    rendered = rendered.replace("@@hlabreak@@", r"\allowbreak{}")
    rendered = re.sub(
        r"(?<=[A-Za-z0-9])\.(?=[A-Za-z])",
        lambda match: f"{match.group(0)}\\allowbreak{{}}",
        rendered,
    )
    rendered = rendered.replace(r"\_", r"\_\allowbreak{}")
    return (
        rendered.replace("ₛ", r"\textsubscript{s}")
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
    if title and not title.casefold().startswith(("table-", "table_family-")):
        return title
    return _source_table_label(table.source.path)


def _table_display_label(table: Table, family_label: str) -> str:
    title = str(table.caption or table.title or "").strip()
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


def _heading(level: int, title: str, *, numbered: bool = False) -> str:
    command = {1: "section", 2: "subsection", 3: "subsubsection"}.get(level, "paragraph")
    suffix = "" if numbered else "*"
    return f"\\{command}{suffix}{{{_text(title)}}}"


def _trace_identifier(value: str) -> str:
    """Render a traceability identifier with intentional breakpoints."""
    return (
        _text(value)
        .replace("-", r"-\allowbreak{}")
        .replace("/", r"/\allowbreak{}")
        .replace(".", r".\allowbreak{}")
        .replace("_", r"_\allowbreak{}")
        .replace(":", r":\allowbreak{}")
    )


def _printed_source_label(source, clause: str | None = None) -> str:
    span = str(source.line)
    if source.end_line is not None and source.end_line != source.line:
        span += f"–{source.end_line}"
    prefix = f"§{clause}, " if clause else ""
    page = re.search(r"page-(\d+)\.tex$", source.path)
    if page is not None:
        return f"{prefix}printed p. {int(page.group(1))}, lines {span}"
    return f"{prefix}{source.path}, lines {span}"


def _clause_title(number: str, title: str) -> str:
    """Avoid repeating a clause number recovered inside its title text."""
    prefixes = (f"{number}. ", f"{number} ")
    normalized = title.strip()
    for prefix in prefixes:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
            break
    return f"{number} {normalized}".strip()


def _clean_content_text(value: str) -> str:
    """Remove layout-adapter residue before rendering reusable prose."""
    text = value
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
    text = text.replace("Directed interation", "Directed interaction")
    body_marker = re.search(r"\bhla-body(?:-[\w-]+)?\b", text)
    if body_marker:
        text = text[body_marker.end() :]
    text = re.sub(r"\bhlafixedpage\b", " ", text)
    text = re.sub(r"\b(?:bookmark|clause):[^\s]+", " ", text)
    text = re.sub(
        r"(?<!\S)(?:\d{1,3}\.\d{2,3}\s+){4}\d{1,3}\.\d{2,3}(?:\s+)?",
        " ",
        text,
    )
    text = re.sub(
        r"\b\d{1,3}\.\d{3}\s+(?=(?:\d+\.)+\d+\s)",
        " ",
        text,
    )
    text = re.sub(r"\bassets/extracted/[^\s]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
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
    return text


def _clean_table_cell_text(value: str) -> str:
    """Remove tabular layout tokens left by source TeX extraction."""
    text = _clean_content_text(value)
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
    normalized = text.casefold().strip(" .")
    return any(
        normalized
        in {
            f"{clause.number} {clause.title}".casefold().strip(" ."),
            clause.title.casefold().strip(" ."),
        }
        for clause in model.clauses
    )


def _content_segments(model: DocumentModel, value: str) -> tuple[tuple[str, str], ...]:
    """Split page-spanning prose at known semantic clause-heading markers."""
    text = _clean_content_text(value)
    markers = sorted(
        {
            _clause_title(clause.number, clause.title)
            for clause in model.clauses
            if clause.title.strip()
        },
        key=len,
        reverse=True,
    )
    if not text or not markers:
        return (("text", text),) if text else ()
    pattern = re.compile(
        r"(?<![\w.])(?:" + "|".join(re.escape(marker) for marker in markers) + r")(?![\w.])"
    )
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
        lines.extend(_render_clause_tree(
            model, child.id, render_body,
            base_level=base_level,
            included_clause_ids=included_clause_ids,
        ))
    return lines


def _render_concepts(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    definitions = _clause_groups(model.definitions, clause_getter=lambda item: item.clause_id)

    def body(clause_id: str | None) -> list[str]:
        lines: list[str] = []
        for definition in sorted(
            definitions.get(clause_id, ()), key=lambda item: (item.term.casefold(), item.id)
        ):
            definition_text = _clean_content_text(definition.text)
            term = _clean_content_text(definition.term)
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
        return lines

    lines = [
        _heading(
            1,
            f"Concepts and terminology — {_document_title(profile, model)}",
            numbered=True,
        )
    ]
    for clause in model.root_clauses():
        lines.extend(_render_clause_tree(model, clause.id, body))
    unowned = definitions.get(None, ())
    if unowned:
        lines.append(_heading(2, "Unassigned definitions"))
        lines.extend(body(None))
    return lines


def _render_content_element(
    model: DocumentModel,
    element: ContentElement,
    children: Mapping[str, tuple[ContentElement, ...]],
    cross_references: Mapping[str, tuple[CrossReference, ...]],
) -> list[str]:
    visible_text = _clean_content_text(element.text)
    text = _text(visible_text)
    special = _render_special_content_element(model, element, text, children, cross_references)
    if special is not None:
        return special
    if not visible_text:
        return []
    lines = [_anchor(model.document_id, element.id)]
    if element.kind == "paragraph":
        return [*lines, *_render_paragraph_segments(model, element)]
    return [*lines, text]


def _render_special_content_element(
    model: DocumentModel,
    element: ContentElement,
    text: str,
    children: Mapping[str, tuple[ContentElement, ...]],
    cross_references: Mapping[str, tuple[CrossReference, ...]],
) -> list[str] | None:
    if element.kind == "list":
        lines = [_anchor(model.document_id, element.id), "\\begin{itemize}"]
        for child in children.get(element.id, ()):
            lines.extend(_render_content_element(model, child, children, cross_references))
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


def _render_paragraph_segments(model: DocumentModel, element: ContentElement) -> list[str]:
    lines: list[str] = []
    for kind, segment in _content_segments(model, element.text):
        if kind == "heading":
            lines.extend(("\\par", f"\\textbf{{{_text(segment)}}}\\\\"))
        else:
            lines.extend((_text(segment), "\\par"))
    return lines


def _render_operations(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    elements = {item.id: item for item in model.content_elements}
    children: dict[str, tuple[ContentElement, ...]] = {}
    grouped_children: dict[str, list[ContentElement]] = defaultdict(list)
    for element in model.content_elements:
        if element.parent_id:
            grouped_children[element.parent_id].append(element)
    children = {
        parent_id: tuple(sorted(items, key=lambda item: (item.sequence, item.id)))
        for parent_id, items in grouped_children.items()
    }
    references: dict[str, list[CrossReference]] = defaultdict(list)
    for item in model.cross_references:
        references[item.owner_id].append(item)
    cross_references = {key: tuple(value) for key, value in references.items()}
    grouped = _clause_groups(model.content_elements, clause_getter=lambda item: item.clause_id)

    def body(clause_id: str | None) -> list[str]:
        items = sorted(
            (item for item in grouped.get(clause_id, ()) if item.parent_id is None),
            key=lambda item: (item.sequence, item.id),
        )
        lines: list[str] = []
        for element in items:
            visible_text = _clean_content_text(element.text)
            if not visible_text or _is_clause_heading(model, visible_text):
                continue
            lines.extend(_render_content_element(model, element, children, cross_references))
            if element.kind not in {"list", "formula"}:
                lines.append("\\par")
        return lines

    lines = [
        _heading(
            1,
            f"Services and operational behavior — {_document_title(profile, model)}",
            numbered=True,
        )
    ]
    for clause in model.root_clauses():
        lines.extend(_render_clause_tree(model, clause.id, body))
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
            title = requirement.title
            if title.casefold().startswith("normative statement at "):
                title = "Normative statement"
            lines.extend(
                (
                    r"\par\noindent\begin{minipage}{\linewidth}",
                    _anchor(model.document_id, requirement.id),
                    _heading(4, title),
                    f"\\texttt{{\\footnotesize {_trace_identifier(requirement.id)}}}\\par",
                    _text(requirement.statement),
                    f"\\par\\smallskip{{\\footnotesize Source: {_text(_printed_source_label(requirement.source, requirement.clause))}}}\\par",
                )
            )
            for source in requirement.additional_sources:
                lines.append(
                    f"{{\\footnotesize Additional source: {_text(_printed_source_label(source, requirement.clause))}}}\\par"
                )
            if requirement.coverage_note and requirement.coverage_note not in {
                "Source-derived normative statement retained at clause scope; no modeled state transition was asserted by the conservative event matcher.",
                "Source refinement retained as an explicit semantic fact; the record preserves source traceability without asserting a state transition.",
            }:
                lines.append(f"\\emph{{Coverage: {_text(requirement.coverage_note)}}}")
            lines.append(r"\par\end{minipage}\par\medskip")
        return lines

    lines = [
        _heading(
            1,
            f"Normative requirements — {_document_title(profile, model)}",
            numbered=True,
        )
    ]
    for clause in model.root_clauses():
        lines.extend(_render_clause_tree(
            model, clause.id, body, included_clause_ids=active_clauses,
        ))
    if grouped.get(None):
        lines.append(_heading(2, "Unassigned requirements"))
        lines.extend(body(None))
    if candidates:
        reviews = {item.requirement_id: item for item in model.requirement_reviews}
        lines.append(_heading(2, "Source candidate review"))
        for requirement in sorted(candidates, key=lambda item: item.id):
            review = reviews.get(requirement.id)
            disposition = (
                f"{review.status}: {review.reason}" if review is not None else "unreviewed"
            )
            lines.extend((
                r"\par\noindent\begin{minipage}{\linewidth}",
                _heading(4, requirement.title),
                f"\\texttt{{\\footnotesize {_trace_identifier(requirement.id)}}}\\par",
                _text(requirement.statement),
                f"\\par\\smallskip{{\\footnotesize Source: {_text(_printed_source_label(requirement.source, requirement.clause))}}}\\par",
                f"\\emph{{Disposition: {_text(disposition)}}}\\par",
            ))
            for source in requirement.additional_sources:
                lines.append(
                    f"{{\\footnotesize Additional source: {_text(_printed_source_label(source, requirement.clause))}}}\\par"
                )
            lines.append(r"\par\end{minipage}\par\medskip")
    return lines


def _render_state_logic(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    lines = [
        _heading(
            1,
            f"State machines and message sequences — {_document_title(profile, model)}",
            numbered=True,
        )
    ]
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
                    f"\\paragraph*{{{_text(transition.event)}}} {source} $\\rightarrow$ {target}.",
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


def _render_tables(model: DocumentModel, profile: PublicationProfile) -> list[str]:
    lines = [
        r"\clearpage",
        r"\Needspace{8\baselineskip}",
        _heading(
            1,
            f"Semantic tables — {_document_title(profile, model)}",
            numbered=True,
        ),
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
    for family, table_ids in families:
        family_label = _table_family_label(family, tables[table_ids[0]])
        lines.extend(
            (
                r"\Needspace{5\baselineskip}",
                _anchor(model.document_id, family.id),
                _heading(2, family_label),
            )
        )
        for table_id in table_ids:
            table = tables[table_id]
            lines.extend(
                (
                    _anchor(model.document_id, table.id),
                    _heading(3, _table_display_label(table, family_label)),
                    "\\begin{itemize}",
                )
            )
            lines.extend(
                f"\\item {_anchor(model.document_id, cell.id)}"
                f"[{cell.row if cell.row is not None else '?'}, "
                f"{cell.column if cell.column is not None else '?'}]: "
                f"{_text(_clean_table_cell_text(cell.text))}"
                + (
                    " ("
                    + ", ".join(
                        _link(model.document_id, record_id) for record_id in cell.record_ids
                    )
                    + ")"
                    if cell.record_ids
                    else ""
                )
                for cell in table.cells
            )
            lines.append("\\end{itemize}")
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


def _traceability_graph_edge(
    model: DocumentModel,
    graph: CorpusSemanticGraph,
    edge: CorpusGraphEdge,
) -> str:
    source = graph.node(edge.source_node_id)
    target = graph.node(edge.target_node_id)
    return (
        f"\\item {_anchor(model.document_id, edge.id)}"
        f"{_link(source.document_id, source.record_id, source.record_id)} "
        "$\\rightarrow$ "
        f"{_link(target.document_id, target.record_id, target.record_id)} "
        f"({_text(edge.relation)}; {_text(edge.evidence)})"
    )


def _traceability_graph_finding(finding: CorpusGraphFinding) -> str:
    nodes = ", ".join(_text(item) for item in finding.node_ids)
    return (
        f"\\item {_text(finding.kind)} ({_text(finding.severity)}, "
        f"similarity {finding.similarity:.2f}): {_text(finding.message)} [{nodes}]"
    )


def _traceability_graph_section(
    model: DocumentModel,
    graph: CorpusSemanticGraph | None,
) -> list[str]:
    if graph is None:
        return []
    lines: list[str] = []
    edges = graph.cross_document_edges(model.document_id)
    if edges:
        lines.extend(
            (
                _heading(2, "Cross-document semantic graph"),
                _text(
                    f"{len(edges)} graph edges touch this document. "
                    "Candidate matches are review data, not normative links."
                ),
                r"\begin{sloppypar}",
                "\\begin{itemize}",
            )
        )
        lines.extend(_traceability_graph_edge(model, graph, edge) for edge in edges)
        lines.extend(("\\end{itemize}", r"\end{sloppypar}"))
    findings = graph.findings_for(model.document_id)
    if findings:
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
        lines.extend(_traceability_graph_finding(item) for item in findings[:120])
        lines.append("\\end{itemize}")
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
) -> list[str]:
    lines = [
        _heading(
            1,
            f"Traceability and dependencies — {_document_title(profile, model)}",
            numbered=True,
        )
    ]
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
    lines.extend(
        _traceability_list_section(
            "Cross-reference edges",
            model.cross_references,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}{_text(item.owner_id)} "
                f"$\\rightarrow$ {item.target_document_id}:{item.target_record_id} "
                f"({_text(item.relation)})"
            ),
        )
    )
    lines.extend(_traceability_graph_section(model, corpus_graph))
    lines.extend(
        _traceability_list_section(
            "Figures",
            model.figures,
            lambda item: (
                f"\\item {_anchor(model.document_id, item.id)}Figure {item.number}: "
                f"{_text(item.caption or 'Caption not recorded.')}"
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


def render_reflowable_document(
    models: Iterable[DocumentModel],
    profile: PublicationProfile,
    corpus_graph: CorpusSemanticGraph | None = None,
) -> str:
    """Render the profile's sections from canonical semantic ownership."""
    ordered_models = tuple(sorted(models, key=lambda item: item.document_id))
    renderers = {
        "concepts": _render_concepts,
        "normative": _render_requirements,
        "operations": _render_operations,
        "state-logic": _render_state_logic,
        "tables": _render_tables,
        "traceability": lambda model, current_profile: _render_traceability(
            model, current_profile, corpus_graph
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
            lines.extend(renderer(model, profile))
    return "\n\n".join(lines) + "\n"
