"""Compile a validated document model into a canonical hierarchy contract.

The compiler is deliberately document-family neutral.  A source profile may
teach the loader how to read a document and a LaTeX dialect may teach a
renderer how to typeset it, but neither is allowed to decide document order,
ownership, destinations, or cross-record relationships.  Those decisions are
made here from :class:`~hla_lab.core.semantic_model.DocumentModel`.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pydantic import Field

from hla_lab.adapters.latex_renderer import (
    LatexDialect,
    render_anchor,
    render_bookmark,
    tex_escape,
)
from hla_lab.core.semantic_model import (
    Clause,
    ContentBlock,
    ContentElement,
    DocumentModel,
    SemanticRecord,
    SourceRef,
    State,
    StateMachine,
    Table,
    TableCell,
    Transition,
)

__all__ = [
    "CompiledHierarchy",
    "HierarchyAnchor",
    "HierarchyLink",
    "HierarchyNode",
    "HierarchyRecord",
    "compile_hierarchy",
    "render_block_bindings",
    "render_hierarchy_index",
    "render_hierarchy_outline",
    "semantic_destination",
]


class HierarchyRecord(SemanticRecord):
    """One addressable record in the compiled document graph."""

    id: str = Field(min_length=1)
    key: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    owner_id: str | None = None
    parent_id: str | None = None
    sequence: int = Field(default=0, ge=0)
    source: SourceRef | None = None


class HierarchyNode(SemanticRecord):
    """A clause node with canonical children and directly owned records."""

    id: str = Field(min_length=1)
    number: str = Field(min_length=1)
    title: str = Field(min_length=1)
    parent_id: str | None = None
    level: int = Field(ge=1)
    child_ids: tuple[str, ...] = ()
    record_ids: tuple[str, ...] = ()
    source: SourceRef


class HierarchyAnchor(SemanticRecord):
    """A stable destination generated from a semantic record ID."""

    record_id: str = Field(min_length=1)
    key: str = Field(min_length=1)
    destination: str = Field(min_length=1)
    kind: str = Field(min_length=1)


class HierarchyLink(SemanticRecord):
    """An explicit relationship represented by the compiled document graph."""

    source_id: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    target_document_id: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    target_key: str = Field(min_length=1)
    relation: str = Field(min_length=1)


class CompiledHierarchy(SemanticRecord):
    """Complete hierarchy, ownership, navigation, and link output."""

    schema_version: int = Field(default=1, ge=1)
    document_id: str = Field(min_length=1)
    root_ids: tuple[str, ...]
    nodes: tuple[HierarchyNode, ...]
    records: tuple[HierarchyRecord, ...]
    anchors: tuple[HierarchyAnchor, ...]
    links: tuple[HierarchyLink, ...]
    unassigned_record_ids: tuple[str, ...] = ()

    def node(self, clause_id: str) -> HierarchyNode:
        """Return a compiled clause node by stable ID."""
        return next(item for item in self.nodes if item.id == clause_id)

    def to_json(self) -> str:
        """Serialize the compiler output with deterministic Pydantic JSON."""
        return self.model_dump_json(indent=2)


_SURFACE_ORDER = (
    "clauses",
    "definitions",
    "requirements",
    "requirement_links",
    "content_blocks",
    "content_elements",
    "state_machines",
    "implementations",
    "tables",
    "table_families",
    "references",
    "notes",
    "figures",
    "examples",
    "annexes",
)

_SURFACE_KINDS = {
    "clauses": "clause",
    "definitions": "definition",
    "requirements": "requirement",
    "requirement_links": "requirement-link",
    "content_blocks": "content-block",
    "content_elements": "content-element",
    "state_machines": "state-machine",
    "implementations": "implementation",
    "tables": "table",
    "table_families": "table-family",
    "references": "reference",
    "notes": "note",
    "figures": "figure",
    "examples": "example",
    "annexes": "annex",
}


def semantic_destination(document_id: str, record_id: str) -> str:
    """Return the cross-document destination contract for a record."""
    return f"{document_id}:{record_id}"


def _source(record: SemanticRecord) -> SourceRef | None:
    value = getattr(record, "source", None)
    return value if isinstance(value, SourceRef) else None


def _clause_owner(record: SemanticRecord) -> str | None:
    """Find a direct clause owner without using page or fragment filenames."""
    clause_id = getattr(record, "clause_id", None)
    if clause_id:
        return clause_id
    return getattr(record, "owner_id", None)


def _surface_records(model: DocumentModel) -> tuple[tuple[str, SemanticRecord], ...]:
    values: list[tuple[str, SemanticRecord]] = []
    for surface in _SURFACE_ORDER:
        for record in getattr(model, surface):
            values.append((_SURFACE_KINDS[surface], record))
            if isinstance(record, StateMachine):
                values.extend(("state", state) for state in record.states)
                values.extend(("transition", transition) for transition in record.transitions)
            if isinstance(record, Table):
                values.extend(("table-cell", cell) for cell in record.cells)
    return tuple(values)


def _record_kind(surface: str, record: SemanticRecord) -> str:
    if isinstance(record, Clause):
        return "clause"
    if isinstance(record, ContentBlock):
        return "content-block"
    if isinstance(record, ContentElement):
        return f"content-element:{record.kind}"
    if isinstance(record, State):
        return "state"
    if isinstance(record, Transition):
        return "transition"
    if isinstance(record, TableCell):
        return "table-cell"
    return surface


def _record_key(kind: str, record_id: str) -> str:
    """Namespace graph records whose source IDs overlap by record kind."""
    if kind in {"state-machine", "state", "transition", "table-cell"}:
        return f"{kind}:{record_id}"
    return record_id


def _key_for(compiled: CompiledHierarchy, record_id: str, *, kind: str | None = None) -> str:
    matches = [item for item in compiled.records if item.id == record_id]
    if kind:
        matches = [item for item in matches if item.kind == kind]
    if len(matches) != 1:
        raise ValueError(f"unable to resolve unique compiled record {kind or ''}:{record_id}")
    return matches[0].key


def _record_owner(record: SemanticRecord, *, by_id: Mapping[str, SemanticRecord]) -> str | None:
    if isinstance(record, Clause):
        return record.parent_id
    if isinstance(record, ContentElement):
        return record.clause_id
    if isinstance(record, State):
        return None
    if isinstance(record, Transition):
        return record.clause_id
    if isinstance(record, TableCell):
        return by_id.get(record.table_id) and _clause_owner(by_id[record.table_id])
    if isinstance(record, StateMachine):
        return record.clause_id
    return _clause_owner(record)


def _record_parent(record: SemanticRecord) -> str | None:
    if isinstance(record, Clause):
        return record.parent_id
    if isinstance(record, ContentElement):
        return record.parent_id
    if isinstance(record, State):
        return record.parent_id
    if isinstance(record, TableCell):
        return record.table_id
    return None


def _sort_records(
    model: DocumentModel, records: Iterable[HierarchyRecord]
) -> tuple[HierarchyRecord, ...]:
    clause_order = {item.id: index for index, item in enumerate(model.ordered_clauses())}
    return tuple(
        sorted(
            records,
            key=lambda item: (
                0 if item.kind == "clause" else 1,
                clause_order.get(
                    item.id if item.kind == "clause" else item.owner_id or "", len(clause_order)
                ),
                item.sequence,
                item.kind,
                item.id,
            ),
        )
    )


def _links(model: DocumentModel, compiled: CompiledHierarchy) -> tuple[HierarchyLink, ...]:
    def link(
        source_id: str,
        target_document_id: str,
        target_id: str,
        relation: str,
        *,
        source_kind: str | None = None,
        target_kind: str | None = None,
    ) -> HierarchyLink:
        return HierarchyLink(
            source_id=source_id,
            source_key=_key_for(compiled, source_id, kind=source_kind),
            target_document_id=target_document_id,
            target_id=target_id,
            target_key=(
                f"{target_kind}:{target_id}"
                if target_kind in {"state", "transition", "table-cell"}
                else (
                    _key_for(compiled, target_id, kind=target_kind)
                    if target_document_id == model.document_id
                    else target_id
                )
            ),
            relation=relation,
        )

    links: list[HierarchyLink] = []
    for reference in model.references:
        links.extend(
            link(reference.id, target.document_id, target.record_id, "references")
            for target in reference.targets
        )
    for requirement in model.requirements:
        links.extend(
            link(
                requirement.id,
                model.document_id,
                transition_id,
                "requires-transition",
                target_kind="transition",
            )
            for transition_id in requirement.transition_ids
        )
    for machine in model.state_machines:
        if machine.clause_id:
            links.append(
                link(
                    machine.id,
                    model.document_id,
                    machine.clause_id,
                    "owned-by-clause",
                    source_kind="state-machine",
                )
            )
        for transition in machine.transitions:
            for requirement_id in transition.requirement_ids:
                links.append(
                    link(
                        transition.id,
                        model.document_id,
                        requirement_id,
                        "satisfies-requirement",
                        source_kind="transition",
                    )
                )
            for implementation_id in transition.implementation_ids:
                links.append(
                    link(
                        transition.id,
                        model.document_id,
                        implementation_id,
                        "implemented-by",
                        source_kind="transition",
                    )
                )
    for implementation in model.implementations:
        for requirement_id in implementation.requirement_ids:
            links.append(
                link(implementation.id, model.document_id, requirement_id, "implements-requirement")
            )
    return tuple(sorted(links, key=lambda item: (item.source_id, item.relation, item.target_id)))


def compile_hierarchy(model: DocumentModel) -> CompiledHierarchy:
    """Compile every validated semantic surface into one canonical graph.

    Clause order comes only from ``DocumentModel.clause_order``.  Other
    surfaces are attached through explicit ``clause_id``/``owner_id`` fields;
    filenames are retained only as provenance on ``source``.
    """
    by_id: dict[str, SemanticRecord] = {}
    by_key: dict[str, SemanticRecord] = {}
    surface_records = _surface_records(model)
    for _surface, record in surface_records:
        record_id = getattr(record, "id", None)
        if record_id is None:
            continue
        by_id[record_id] = record

    clause_ids = {item.id for item in model.clauses}
    records: list[HierarchyRecord] = []
    for sequence, (surface, record) in enumerate(surface_records):
        record_id = getattr(record, "id", None)
        if record_id is None:
            continue
        owner_id = _record_owner(record, by_id=by_id)
        if owner_id is not None and owner_id not in clause_ids:
            # A non-clause parent (a table or list) is not a clause owner.  It
            # remains available through ``parent_id`` while the record is
            # promoted to the nearest explicit clause owner where possible.
            owner_id = None
        kind = _record_kind(surface, record)
        key = _record_key(kind, record_id)
        if key in by_key:
            raise ValueError(f"duplicate compiled record key: {key}")
        by_key[key] = record
        records.append(
            HierarchyRecord(
                id=record_id,
                key=key,
                kind=kind,
                owner_id=owner_id,
                parent_id=_record_parent(record),
                sequence=sequence,
                source=_source(record),
            )
        )

    ordered_records = _sort_records(model, records)
    records_by_owner: dict[str, list[str]] = {}
    for record in ordered_records:
        if record.owner_id and record.kind != "clause":
            records_by_owner.setdefault(record.owner_id, []).append(record.key)

    ordered_clauses = model.ordered_clauses()
    nodes = tuple(
        HierarchyNode(
            id=clause.id,
            number=clause.number,
            title=clause.title,
            parent_id=clause.parent_id,
            level=clause.level,
            child_ids=tuple(item.id for item in model.children_of(clause.id)),
            record_ids=tuple(records_by_owner.get(clause.id, ())),
            source=clause.source,
        )
        for clause in ordered_clauses
    )
    anchors = tuple(
        HierarchyAnchor(
            record_id=record.id,
            key=record.key,
            destination=semantic_destination(model.document_id, record.key),
            kind=record.kind,
        )
        for record in ordered_records
    )
    assigned = {record.key for record in ordered_records if record.owner_id is not None}
    compiled = CompiledHierarchy(
        document_id=model.document_id,
        root_ids=tuple(item.id for item in model.root_clauses()),
        nodes=nodes,
        records=ordered_records,
        anchors=anchors,
        links=(),
        unassigned_record_ids=tuple(
            record.key for record in ordered_records if record.key not in assigned
        ),
    )
    object.__setattr__(compiled, "links", _links(model, compiled))
    return compiled


def render_hierarchy_index(compiled: CompiledHierarchy) -> str:
    """Render model-wide hierarchy metadata and link helpers for LaTeX."""

    def macro(name: str, value: str) -> list[str]:
        if not value:
            return [f"\\providecommand{{\\SemanticHierarchy{name}}}{{}}"]
        chunks: list[str] = []
        current = ""
        for item in value.split(","):
            part = item if not current else f",{item}"
            if current and len(current) + len(part) > 96:
                chunks.append(current)
                current = item
            else:
                current += part
        if current:
            chunks.append(current)
        return [
            f"\\providecommand{{\\SemanticHierarchy{name}}}{{%",
            *(f"{tex_escape(chunk)}%" for chunk in chunks),
            "}",
        ]

    lines = ["% Generated hierarchy compiler output; edit semantic source instead."]
    for name, value in (
        ("DocumentID", compiled.document_id),
        ("SchemaVersion", str(compiled.schema_version)),
        ("NodeCount", str(len(compiled.nodes))),
        ("RecordCount", str(len(compiled.records))),
        ("AnchorCount", str(len(compiled.anchors))),
        ("LinkCount", str(len(compiled.links))),
        ("RootIDs", ",".join(compiled.root_ids)),
        ("ClauseIDs", ",".join(node.id for node in compiled.nodes)),
    ):
        lines.extend(macro(name, value))
    # These helpers are intentionally generic; a family profile only chooses
    # the surrounding layout commands.
    lines.extend(
        [
            (
                "\\providecommand{\\SemanticHierarchyAnchor}[1]{"
                f"\\hypertarget{{{tex_escape(compiled.document_id)}:#1}}{{}}}}"
            ),
            (
                "\\providecommand{\\SemanticHierarchyLink}[2]{"
                f"\\hyperlink{{{tex_escape(compiled.document_id)}:#1}}{{#2}}}}"
            ),
        ]
    )
    return "\n".join(lines)


def _records_on_source_path(compiled: CompiledHierarchy, path: str) -> tuple[HierarchyRecord, ...]:
    return tuple(item for item in compiled.records if item.source and item.source.path == path)


def render_block_bindings(
    model: DocumentModel,
    block: ContentBlock,
    dialect: LatexDialect,
    *,
    compiled: CompiledHierarchy | None = None,
) -> str:
    """Render anchors/bookmarks at a page adapter's semantic source boundary."""
    compiled = compiled or compile_hierarchy(model)
    first_block_for_clause: dict[str, int] = {}
    first_block_for_source_path: dict[str, int] = {}
    for candidate in model.content_blocks:
        first_block_for_clause[candidate.clause_id or ""] = min(
            candidate.sequence,
            first_block_for_clause.get(candidate.clause_id or "", candidate.sequence),
        )
        first_block_for_source_path[candidate.source.path] = min(
            candidate.sequence,
            first_block_for_source_path.get(candidate.source.path, candidate.sequence),
        )
    records = tuple(
        item
        for item in _records_on_source_path(compiled, block.source.path)
        if item.kind
        in {
            "content-block",
            "content-element:paragraph",
            "content-element:list",
            "content-element:list-item",
            "content-element:note",
            "content-element:footnote",
            "content-element:formula",
            "content-element:cross-reference",
        }
        and (
            item.kind != "clause"
            or block.sequence == first_block_for_source_path[block.source.path]
        )
    )
    ids: list[str] = [block.id]
    if block.clause_id and block.sequence == first_block_for_clause.get(block.clause_id):
        ids.append(block.clause_id)
    ids.extend(item.key for item in records)
    seen: set[str] = set()
    lines: list[str] = ["% Generated hierarchy bindings for this semantic content block."]
    for record_id in ids:
        if record_id in seen:
            continue
        seen.add(record_id)
        anchor = next(
            (
                item
                for item in compiled.anchors
                if item.record_id == record_id or item.key == record_id
            ),
            None,
        )
        if anchor is None:
            continue
        lines.append(render_anchor(anchor.key, dialect, document_id=model.document_id))
    return "\n".join(lines)


def render_hierarchy_outline(model: DocumentModel, dialect: LatexDialect) -> str:
    """Render the complete visible hierarchy recursively from compiled nodes."""
    compiled = compile_hierarchy(model)
    nodes = {item.id: item for item in compiled.nodes}
    lines: list[str] = []

    def render_node(node: HierarchyNode) -> None:
        command = (
            dialect.clause_heading_command if node.level == 1 else dialect.subclause_heading_command
        )
        lines.extend(
            (
                f"% {node.id}",
                render_anchor(node.id, dialect, document_id=model.document_id),
                render_bookmark(
                    node.title,
                    max(node.level - 1, 0),
                    dialect,
                    destination=semantic_destination(model.document_id, node.id),
                ),
                f"\\{command}{{{tex_escape(node.id)}}}{{{tex_escape(node.title)}}}",
            )
        )
        for child_id in node.child_ids:
            render_node(nodes[child_id])

    for root_id in compiled.root_ids:
        render_node(nodes[root_id])
    return "\n".join(lines)
