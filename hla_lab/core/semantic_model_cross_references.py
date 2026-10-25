"""Build visible cross-reference records from semantic surfaces."""

from __future__ import (
    annotations,
)

import json
import re
from collections.abc import (
    Iterable,
    Mapping,
    MutableMapping,
    Sequence,
)
from pathlib import (
    Path,
)

from pydantic import (
    JsonValue,
)

from hla_lab.core.semantic_model_resources import _clause_shape, _document_resources
from hla_lab.core.semantic_types import (
    Annex,
    ApiCrosswalk,
    ApiSurface,
    CatalogEntry,
    Clause,
    ContentBlock,
    ContentElement,
    CrossReference,
    CrossReferenceKind,
    Definition,
    Example,
    Figure,
    GraphDiagram,
    ImplementationMapping,
    Note,
    Reference,
    ReferenceAlias,
    Requirement,
    SequenceDiagram,
    SourceRef,
    StateMachine,
    StateTrace,
    Table,
    TableFamily,
    VerificationTest,
    VisibleReferenceTarget,
)
from hla_lab.core.text import (
    slugify,
)


def _add_catalog_entry(
    catalog: MutableMapping[str, CatalogEntry],
    record_id: str,
    kind: CrossReferenceKind,
    label: str,
) -> None:
    catalog.setdefault(record_id, (kind, label.strip() or record_id))


def _add_primary_catalog_entries(
    catalog: MutableMapping[str, CatalogEntry],
    clauses: Iterable[Clause],
    definitions: Iterable[Definition],
    requirements: Iterable[Requirement],
    content_blocks: Iterable[ContentBlock],
    content_elements: Iterable[ContentElement],
    tables: Iterable[Table],
) -> None:
    for item in clauses:
        _add_catalog_entry(catalog, item.id, "clause", f"{item.number}. {item.title}")
    for item in definitions:
        _add_catalog_entry(catalog, item.id, "definition", item.term)
    for item in requirements:
        _add_catalog_entry(catalog, item.id, "requirement", item.title)
    for item in content_blocks:
        _add_catalog_entry(catalog, item.id, "content", item.text)
    for item in content_elements:
        _add_catalog_entry(catalog, item.id, "content", item.text)
    for item in tables:
        _add_catalog_entry(catalog, item.id, "table", item.caption or item.title or item.id)
        for cell in item.cells:
            _add_catalog_entry(catalog, cell.id, "content", cell.text)


def _add_attachment_catalog_entries(
    catalog: MutableMapping[str, CatalogEntry],
    table_families: Iterable[TableFamily],
    references: Iterable[Reference],
    notes: Iterable[Note],
    figures: Iterable[Figure],
    examples: Iterable[Example],
    annexes: Iterable[Annex],
) -> None:
    for item in table_families:
        _add_catalog_entry(catalog, item.id, "table-family", item.title)
    for item in references:
        _add_catalog_entry(catalog, item.id, "reference", f"{item.label} {item.text}".strip())
    for item in notes:
        _add_catalog_entry(catalog, item.id, "note", item.text)
    for item in figures:
        _add_catalog_entry(
            catalog, item.id, "figure", f"Figure {item.number} — {item.caption}".rstrip(" —")
        )
    for item in examples:
        _add_catalog_entry(catalog, item.id, "example", item.title)
    for item in annexes:
        _add_catalog_entry(catalog, item.id, "annex", item.title)


def _add_diagram_catalog_entries(
    catalog: MutableMapping[str, CatalogEntry],
    state_machines: Iterable[StateMachine],
    sequence_diagrams: Iterable[SequenceDiagram],
    graph_diagrams: Iterable[GraphDiagram],
) -> None:
    for item in state_machines:
        _add_catalog_entry(catalog, item.id, "state-machine", item.title)
        for state in item.states:
            _add_catalog_entry(catalog, state.id, "state", state.label or state.id)
        for transition in item.transitions:
            _add_catalog_entry(
                catalog, transition.id, "transition", transition.event or transition.id
            )
    for item in sequence_diagrams:
        _add_catalog_entry(catalog, item.id, "sequence-diagram", item.id)
    for item in graph_diagrams:
        _add_catalog_entry(catalog, item.id, "graph-diagram", item.id)


def _add_api_catalog_entries(
    catalog: MutableMapping[str, CatalogEntry],
    implementations: Iterable[ImplementationMapping],
    api_surfaces: Iterable[ApiSurface],
    api_crosswalks: Iterable[ApiCrosswalk],
    verification_tests: Iterable[VerificationTest],
    state_traces: Iterable[StateTrace],
) -> None:
    for item in implementations:
        _add_catalog_entry(catalog, item.id, "implementation", item.interface_name)
    for item in api_surfaces:
        _add_catalog_entry(catalog, item.id, "api-surface", item.name)
    for item in api_crosswalks:
        _add_catalog_entry(catalog, item.id, "api-crosswalk", f"{item.target} {item.status}")
    for item in verification_tests:
        _add_catalog_entry(catalog, item.id, "verification-test", item.title)
    for item in state_traces:
        _add_catalog_entry(catalog, item.id, "state-trace", item.title)


def _cross_reference_catalog(
    *,
    clauses: Iterable[Clause],
    definitions: Iterable[Definition],
    requirements: Iterable[Requirement],
    content_blocks: Iterable[ContentBlock],
    content_elements: Iterable[ContentElement],
    tables: Iterable[Table],
    table_families: Iterable[TableFamily],
    references: Iterable[Reference],
    notes: Iterable[Note],
    figures: Iterable[Figure],
    examples: Iterable[Example],
    annexes: Iterable[Annex],
    state_machines: Iterable[StateMachine],
    sequence_diagrams: Iterable[SequenceDiagram],
    graph_diagrams: Iterable[GraphDiagram],
    implementations: Iterable[ImplementationMapping],
    api_surfaces: Iterable[ApiSurface] = (),
    api_crosswalks: Iterable[ApiCrosswalk] = (),
    verification_tests: Iterable[VerificationTest] = (),
    state_traces: Iterable[StateTrace] = (),
) -> dict[str, tuple[CrossReferenceKind, str]]:
    """Build the local target label catalog used by typed cross-references."""
    catalog: dict[str, tuple[CrossReferenceKind, str]] = {}
    _add_primary_catalog_entries(
        catalog, clauses, definitions, requirements, content_blocks, content_elements, tables
    )
    _add_attachment_catalog_entries(
        catalog, table_families, references, notes, figures, examples, annexes
    )
    _add_diagram_catalog_entries(catalog, state_machines, sequence_diagrams, graph_diagrams)
    _add_api_catalog_entries(
        catalog, implementations, api_surfaces, api_crosswalks, verification_tests, state_traces
    )
    return catalog


def _basic_reference_aliases(
    clauses: Iterable[Clause],
    definitions: Iterable[Definition],
    figures: Iterable[Figure],
) -> dict[tuple[str, str], tuple[str, CrossReferenceKind, str]]:
    aliases: dict[tuple[str, str], tuple[str, CrossReferenceKind, str]] = {}
    for item in clauses:
        aliases.setdefault(("clause", item.number), (item.id, "clause", item.title))
    for item in definitions:
        aliases.setdefault(("definition", item.term.casefold()), (item.id, "definition", item.term))
    for item in figures:
        aliases.setdefault(("figure", item.number), (item.id, "figure", f"Figure {item.number}"))
    return aliases


def _add_table_reference_aliases(
    aliases: MutableMapping[ReferenceAlias, VisibleReferenceTarget],
    tables: Iterable[Table],
    table_families: Iterable[TableFamily],
) -> None:
    family_by_table = {
        table_id: family for family in table_families for table_id in family.table_ids
    }
    for item in sorted(tables, key=lambda value: (value.source.path, value.source.line, value.id)):
        if item.number is None:
            continue
        family = family_by_table.get(item.id)
        target = family or item
        kind: CrossReferenceKind = "table-family" if family is not None else "table"
        label = family.title if family is not None else item.caption or item.title or item.id
        aliases.setdefault(("table", item.number), (target.id, kind, label))


def _visible_alias_matches(
    text: str,
    pattern: str,
    kind: CrossReferenceKind,
    aliases: Mapping[ReferenceAlias, VisibleReferenceTarget],
) -> list[VisibleReferenceTarget]:
    found: list[tuple[str, CrossReferenceKind, str]] = []
    for match in re.finditer(pattern, text, re.IGNORECASE):
        target = aliases.get((kind, match.group(1)))
        if target is not None:
            found.append(target)
    return found


def _visible_definition_mentions(
    suffix: str, definitions: Sequence[Definition]
) -> list[tuple[str, CrossReferenceKind, str]]:
    return [
        (definition.id, "definition", definition.term)
        for definition in definitions
        if re.search(rf"\b{re.escape(definition.term)}\b", suffix, re.IGNORECASE)
    ]


def _visible_targets(
    text: str,
    aliases: Mapping[ReferenceAlias, VisibleReferenceTarget],
    definitions: Sequence[Definition],
) -> tuple[VisibleReferenceTarget, ...]:
    found = _visible_alias_matches(
        text,
        r"\b(?:see|shown\s+in|specified\s+in|described\s+in|summarized\s+in|defined\s+in)"
        r"\s+(?:Clause\s+)?(\d+(?:\.\d+)*)",
        "clause",
        aliases,
    )
    found.extend(_visible_alias_matches(text, r"\bTable\s+(\d+)\b", "table", aliases))
    found.extend(_visible_alias_matches(text, r"\bFigure\s+(\d+)\b", "figure", aliases))
    see_also = re.search(r"\bsee\s+also\s*:\s*(.+)$", text, re.IGNORECASE)
    if see_also:
        found.extend(_visible_definition_mentions(see_also.group(1), definitions))
    deduplicated: list[tuple[str, CrossReferenceKind, str]] = []
    seen: set[str] = set()
    for target in found:
        if target[0] not in seen:
            seen.add(target[0])
            deduplicated.append(target)
    return tuple(deduplicated)


def _content_element_cross_references(
    document_id: str,
    element: ContentElement,
    catalog: Mapping[str, CatalogEntry],
    aliases: Mapping[ReferenceAlias, VisibleReferenceTarget],
    definitions: Sequence[Definition],
) -> tuple[ContentElement, list[CrossReference], list[CrossReference]]:
    text = element.text
    explicit_targets: set[str] = set()
    explicit: list[CrossReference] = []
    surface: list[CrossReference] = []
    for ordinal, target_id in enumerate(element.record_ids, 1):
        target = catalog.get(target_id)
        if target is None:
            continue
        kind, label = target
        explicit_targets.add(target_id)
        if element.kind == "cross-reference" and text.startswith("Semantic record "):
            text = label
        explicit.append(
            CrossReference(
                id=f"xref-{element.id}-{ordinal:03d}",
                owner_id=element.id,
                target_document_id=document_id,
                target_record_id=target_id,
                label=label,
                kind=kind,
                source=element.source,
            )
        )
    for target_id, kind, label in _visible_targets(text, aliases, definitions):
        if target_id in explicit_targets:
            continue
        target_slug = slugify(target_id)
        surface.append(
            CrossReference(
                id=f"xref-{element.id}-surface-{target_slug}",
                owner_id=element.id,
                target_document_id=document_id,
                target_record_id=target_id,
                label=label,
                kind=kind,
                source=element.source,
            )
        )
    normalized = element.model_copy(update={"text": text}) if text != element.text else element
    return normalized, explicit, surface


def _definition_surface_references(
    document_id: str,
    definitions: Sequence[Definition],
    aliases: Mapping[ReferenceAlias, VisibleReferenceTarget],
) -> list[CrossReference]:
    cross_references: list[CrossReference] = []
    for definition in definitions:
        for target_id, kind, label in _visible_targets(definition.text, aliases, definitions):
            target_slug = slugify(target_id)
            cross_references.append(
                CrossReference(
                    id=f"xref-{definition.id}-surface-{target_slug}",
                    owner_id=definition.id,
                    target_document_id=document_id,
                    target_record_id=target_id,
                    label=label,
                    kind=kind,
                    source=definition.source,
                )
            )
    return cross_references


def _derive_cross_references(
    document_id: str,
    content_elements: Sequence[ContentElement],
    catalog: Mapping[str, CatalogEntry],
    clauses: Iterable[Clause] = (),
    definitions: Iterable[Definition] = (),
    tables: Iterable[Table] = (),
    table_families: Iterable[TableFamily] = (),
    figures: Iterable[Figure] = (),
) -> tuple[tuple[ContentElement, ...], tuple[CrossReference, ...]]:
    """Turn explicit and visible source references into typed relationships."""
    clause_records = tuple(clauses)
    definition_records = tuple(definitions)
    figure_records = tuple(figures)
    aliases = _basic_reference_aliases(clause_records, definition_records, figure_records)
    _add_table_reference_aliases(aliases, tables, table_families)

    normalized: list[ContentElement] = []
    cross_references: list[CrossReference] = []
    surface_cross_references: list[CrossReference] = []
    for element in content_elements:
        normalized_element, explicit, surface = _content_element_cross_references(
            document_id, element, catalog, aliases, definition_records
        )
        normalized.append(normalized_element)
        cross_references.extend(explicit)
        surface_cross_references.extend(surface)
    cross_references.extend(surface_cross_references)
    cross_references.extend(
        _definition_surface_references(document_id, definition_records, aliases)
    )
    return tuple(normalized), tuple(cross_references)


def _load_navigation_clauses(root: Path) -> tuple[Clause, ...]:
    """Load clause labels from an existing canonical navigation manifest."""
    path = _document_resources(root).canonical_file("source-navigation.json")
    if not path.is_file():
        return ()
    raw: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    outline_value: JsonValue = raw.get("outline", []) if isinstance(raw, dict) else []
    outline: list[JsonValue] = outline_value if isinstance(outline_value, list) else []
    source = SourceRef(path=path.relative_to(root).as_posix(), line=1)
    clauses: dict[str, Clause] = {}
    for raw_entry in outline:
        entry: JsonValue = raw_entry
        if isinstance(entry, dict):
            identifier = str(entry.get("id", "")).strip()
            if not identifier:
                continue
            try:
                entry_source = (
                    source if "source" not in entry else SourceRef.model_validate(entry["source"])
                )
                clauses[identifier] = Clause(
                    id=identifier,
                    number=str(entry["number"]),
                    title=str(entry["title"]),
                    parent_id=entry.get("parent_id"),
                    level=int(entry["level"]),
                    source=entry_source,
                )
            except (KeyError, TypeError, ValueError):
                continue
            continue
        if not isinstance(entry, list) or len(entry) < 2:
            continue
        label = str(entry[1]).strip()
        annex = re.match(r"Annex\s+([A-H])\s+\((?:normative|informative)\).+", label)
        numbered = re.match(r"(?P<number>\d+(?:\.\d+)*)\.\s+.+", label)
        if annex:
            identifier = f"clause-{annex.group(1)}"
            number = annex.group(1)
        elif numbered:
            number = numbered.group("number")
            identifier = f"clause-{number}"
        else:
            continue
        clause_number, parent_id, level = _clause_shape(identifier)
        clauses[identifier] = Clause(
            id=identifier,
            number=clause_number,
            title=label,
            parent_id=parent_id,
            level=level,
            source=source,
        )
    return tuple(clauses.values())
