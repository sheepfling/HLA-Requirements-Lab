"""Build a typed, cross-document graph from validated semantic models.

The graph deliberately separates authored relationships from useful but
unreviewed candidates.  Exact term or statement matches are never promoted to
normative references; they are emitted as candidate edges with provenance so a
reviewer or downstream compliance tool can decide what they mean.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from collections.abc import Mapping, MutableMapping, Sequence
from collections.abc import Set as AbstractSet
from itertools import combinations
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator

from hla_lab.core.links import qualified_id
from hla_lab.core.semantic_model import (
    ComplianceCorpus,
    ComplianceDependency,
    DocumentModel,
    SemanticRecord,
    SourceRef,
)

__all__ = [
    "CorpusDocumentDescriptor",
    "CorpusDocumentMetadataFile",
    "CorpusGraphEdge",
    "CorpusGraphFinding",
    "CorpusGraphNode",
    "CorpusSemanticGraph",
    "build_corpus_graph",
    "load_corpus_graph",
    "load_document_metadata",
]

GraphEvidence = Literal["explicit", "derived", "candidate"]
_qualified_id = qualified_id
GraphRelation = Literal[
    "owned-by",
    "contains",
    "member-of",
    "references",
    "mentions",
    "continues",
    "governs",
    "implements",
    "annotates",
    "maps-to",
    "shared-definition-term",
    "shared-requirement-statement",
]
FindingKind = Literal[
    "duplicate-definition",
    "conflicting-definition",
    "duplicate-requirement",
    "near-duplicate-definition",
    "near-duplicate-requirement",
    "supersession-gap",
]
FindingSeverity = Literal["info", "warning", "error"]
RecordRef: TypeAlias = tuple[str, str, SourceRef]
CandidateRecord: TypeAlias = tuple[str, str, SourceRef, str, str, frozenset[str]]
DocumentRelationship = Literal[
    "standalone",
    "companion",
    "extends",
    "profiles",
    "supersedes",
    "unknown",
]


class CorpusDocumentDescriptor(SemanticRecord):
    """Edition and relationship metadata for a graph document node."""

    document_id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    edition: str | None = None
    relationship: DocumentRelationship = "unknown"
    related_document_ids: tuple[str, ...] = ()
    source: SourceRef | None = None


class CorpusGraphNode(SemanticRecord):
    """A qualified semantic record addressable from a corpus graph."""

    id: Annotated[str, Field(min_length=1)]
    document_id: Annotated[str, Field(min_length=1)]
    record_id: Annotated[str, Field(min_length=1)]
    kind: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    external: bool = False
    source: SourceRef | None = None


class CorpusGraphEdge(SemanticRecord):
    """A typed graph edge with evidence level and optional source provenance."""

    id: Annotated[str, Field(min_length=1)]
    source_node_id: Annotated[str, Field(min_length=1)]
    target_node_id: Annotated[str, Field(min_length=1)]
    relation: GraphRelation
    evidence: GraphEvidence
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    note: str = ""
    source: SourceRef | None = None


class CorpusGraphFinding(SemanticRecord):
    """A review finding derived from multiple corpus records."""

    id: Annotated[str, Field(min_length=1)]
    kind: FindingKind
    severity: FindingSeverity
    document_ids: Annotated[tuple[str, ...], Field(min_length=2)]
    node_ids: Annotated[tuple[str, ...], Field(min_length=2)]
    similarity: Annotated[float, Field(ge=0.0, le=1.0)] = 1.0
    message: Annotated[str, Field(min_length=1)]
    source: SourceRef | None = None


class CorpusDocumentMetadataFile(SemanticRecord):
    """Source-controlled metadata for a corpus's editions and relationships."""

    schema_version: Annotated[int, Field(ge=1)]
    documents: tuple[CorpusDocumentDescriptor, ...]


class CorpusSemanticGraph(SemanticRecord):
    """Serializable graph projection for cross-document semantic queries."""

    schema_version: Annotated[int, Field(ge=1)] = 1
    documents: tuple[CorpusDocumentDescriptor, ...]
    nodes: tuple[CorpusGraphNode, ...]
    edges: tuple[CorpusGraphEdge, ...]
    findings: tuple[CorpusGraphFinding, ...] = ()

    @model_validator(mode="after")
    def validate_graph_integrity(self) -> CorpusSemanticGraph:
        document_ids = self._unique_ids(
            "corpus graph document IDs", [item.document_id for item in self.documents]
        )
        self._unique_ids("corpus graph node IDs", [item.id for item in self.nodes])
        self._unique_ids("corpus graph edge IDs", [item.id for item in self.edges])
        node_index = {item.id: item for item in self.nodes}
        self._validate_node_documents(document_ids)
        self._validate_edge_endpoints(node_index)
        self._validate_related_documents(document_ids)
        self._unique_ids("corpus graph finding IDs", [item.id for item in self.findings])
        self._validate_finding_references(document_ids, node_index)
        return self

    @staticmethod
    def _unique_ids(label: str, identifiers: Sequence[str]) -> set[str]:
        unique = set(identifiers)
        if len(identifiers) != len(unique):
            raise ValueError(f"{label} must be unique")
        return unique

    def _validate_node_documents(self, document_ids: AbstractSet[str]) -> None:
        for node in self.nodes:
            if node.external and node.document_id in document_ids:
                raise ValueError(f"external graph node names a known document: {node.id}")
            if not node.external and node.document_id not in document_ids:
                raise ValueError(f"graph node {node.id} names an unknown internal document")

    def _validate_edge_endpoints(self, node_index: Mapping[str, CorpusGraphNode]) -> None:
        for edge in self.edges:
            if edge.source_node_id not in node_index:
                raise ValueError(f"graph edge {edge.id} has a missing source node")
            if edge.target_node_id not in node_index:
                raise ValueError(f"graph edge {edge.id} has a missing target node")

    def _validate_related_documents(self, document_ids: AbstractSet[str]) -> None:
        for document in self.documents:
            invalid = set(document.related_document_ids) - document_ids
            if invalid:
                raise ValueError(
                    f"document {document.document_id} has unknown related documents "
                    f"{sorted(invalid)}"
                )

    def _validate_finding_references(
        self,
        document_ids: AbstractSet[str],
        node_index: Mapping[str, CorpusGraphNode],
    ) -> None:
        for finding in self.findings:
            if not set(finding.document_ids) <= document_ids:
                raise ValueError(f"graph finding {finding.id} names an unknown document")
            if not set(finding.node_ids) <= node_index.keys():
                raise ValueError(f"graph finding {finding.id} has a missing node")

    def edges_for(
        self,
        document_id: str,
        record_id: str | None = None,
        *,
        relation: GraphRelation | None = None,
        evidence: GraphEvidence | None = None,
        cross_document_only: bool = False,
    ) -> tuple[CorpusGraphEdge, ...]:
        """Return graph edges touching a qualified document record."""
        node_id = _qualified_id(document_id, record_id) if record_id else None
        nodes = {
            item.id
            for item in self.nodes
            if item.document_id == document_id and (record_id is None or item.id == node_id)
        }
        result = []
        for edge in self.edges:
            if edge.source_node_id not in nodes and edge.target_node_id not in nodes:
                continue
            if relation is not None and edge.relation != relation:
                continue
            if evidence is not None and edge.evidence != evidence:
                continue
            source = self.node(edge.source_node_id)
            target = self.node(edge.target_node_id)
            if cross_document_only and source.document_id == target.document_id:
                continue
            result.append(edge)
        return tuple(result)

    def cross_document_edges(
        self,
        document_id: str | None = None,
        *,
        evidence: GraphEvidence | None = None,
    ) -> tuple[CorpusGraphEdge, ...]:
        """Return edges whose endpoints belong to different documents."""
        result = []
        for edge in self.edges:
            source = self.node(edge.source_node_id)
            target = self.node(edge.target_node_id)
            if source.document_id == target.document_id:
                continue
            if document_id is not None and document_id not in {
                source.document_id,
                target.document_id,
            }:
                continue
            if evidence is not None and edge.evidence != evidence:
                continue
            result.append(edge)
        return tuple(result)

    def node(self, node_id: str) -> CorpusGraphNode:
        """Return a graph node by its qualified ID."""
        try:
            return next(item for item in self.nodes if item.id == node_id)
        except StopIteration as error:
            raise ValueError(f"unknown graph node {node_id}") from error

    def shared_term_edges(self) -> tuple[CorpusGraphEdge, ...]:
        """Return exact cross-document term matches as review candidates."""
        return tuple(item for item in self.edges if item.relation == "shared-definition-term")

    def findings_for(
        self,
        document_id: str | None = None,
        *,
        kind: FindingKind | None = None,
    ) -> tuple[CorpusGraphFinding, ...]:
        """Return review findings involving a document or finding kind."""
        return tuple(
            item
            for item in self.findings
            if (document_id is None or document_id in item.document_ids)
            and (kind is None or item.kind == kind)
        )

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the graph with Pydantic's JSON encoder."""
        return self.model_dump_json(indent=indent)


def _normalized_text(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.casefold()))


def _similarity(left: str, right: str) -> float:
    """Return token-set Jaccard similarity for review-only comparisons."""
    return _token_similarity(
        frozenset(_normalized_text(left).split()),
        frozenset(_normalized_text(right).split()),
    )


def _token_similarity(left_tokens: frozenset[str], right_tokens: frozenset[str]) -> float:
    """Return Jaccard similarity when normalized token sets are already available."""
    if not left_tokens and not right_tokens:
        return 1.0
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _near_duplicate_pairs(
    records: Sequence[tuple[str, str, SourceRef, str, str, frozenset[str]]],
) -> tuple[
    tuple[
        tuple[str, str, SourceRef, str, str, frozenset[str]],
        tuple[str, str, SourceRef, str, str, frozenset[str]],
    ],
    ...,
]:
    """Return a bounded candidate set for high-similarity review comparisons.

    For a Jaccard threshold of 0.92, a near-duplicate must share at least one
    of ``floor(0.08 * token_count) + 1`` arbitrary source tokens.  Indexing a
    record by that many *rarest* tokens preserves the high-similarity candidate
    while avoiding a quadratic scan of every short normative statement.
    """
    token_frequency = Counter(token for record in records for token in record[5])
    buckets: dict[str, list[int]] = defaultdict(list)
    for index, record in enumerate(records):
        token_count = len(record[5])
        if not token_count:
            continue
        selected_count = int(0.08 * token_count) + 1
        selected_tokens = sorted(record[5], key=lambda token: (token_frequency[token], token))[
            :selected_count
        ]
        for token in selected_tokens:
            buckets[token].append(index)

    candidate_indices: set[tuple[int, int]] = set()
    for indices in buckets.values():
        for left_index, right_index in combinations(sorted(indices), 2):
            left = records[left_index]
            right = records[right_index]
            if left[0] == right[0]:
                continue
            smaller = min(len(left[5]), len(right[5]))
            larger = max(len(left[5]), len(right[5]))
            if larger and smaller / larger < 0.92:
                continue
            candidate_indices.add((left_index, right_index))
    return tuple(
        (records[left_index], records[right_index])
        for left_index, right_index in sorted(candidate_indices)
    )


def _record_labels(model: DocumentModel) -> dict[str, tuple[str, str, SourceRef | None]]:
    """Collect useful labels without making the graph depend on HLA names."""
    labels: dict[str, tuple[str, str, SourceRef | None]] = {}
    for record in model.clauses:
        labels[record.id] = ("clause", record.title, record.source)
    for record in model.definitions:
        labels[record.id] = ("definition", record.term, record.source)
    for record in model.requirements:
        labels[record.id] = ("requirement", record.title, record.source)
    for record in model.references:
        labels[record.id] = ("reference", record.label, record.source)
    for record in model.tables:
        labels[record.id] = ("table", record.caption or record.title or record.id, record.source)
    for record in model.table_families:
        labels[record.id] = ("table-family", record.title, record.source)
    for record in model.figures:
        labels[record.id] = ("figure", record.caption or record.number, record.source)
    for record in model.annexes:
        labels[record.id] = ("annex", record.title, record.source)
    return labels


def _edge_evidence(dependency: ComplianceDependency) -> GraphEvidence:
    if dependency.relation in {
        "references",
        "continues",
        "governs",
        "implements",
        "annotates",
        "mentions",
    }:
        return "explicit"
    return "derived"


def _document_descriptors(
    corpus: ComplianceCorpus,
    metadata: Mapping[str, CorpusDocumentDescriptor] | None,
) -> tuple[CorpusDocumentDescriptor, ...]:
    result = []
    for model in corpus.documents:
        descriptor = metadata.get(model.document_id) if metadata else None
        result.append(
            descriptor
            or CorpusDocumentDescriptor(
                document_id=model.document_id,
                title=model.document_id,
            )
        )
    return tuple(result)


def _add_node(
    nodes: MutableMapping[str, CorpusGraphNode],
    document_id: str,
    record_id: str,
    kind: str,
    label: str,
    source: SourceRef | None,
    *,
    external: bool = False,
) -> str:
    node_id = _qualified_id(document_id, record_id)
    nodes.setdefault(
        node_id,
        CorpusGraphNode(
            id=node_id,
            document_id=document_id,
            record_id=record_id,
            kind=kind,
            label=label or record_id,
            external=external,
            source=source,
        ),
    )
    return node_id


def _add_dependency_edges(
    corpus: ComplianceCorpus,
    document_ids: AbstractSet[str],
    nodes: MutableMapping[str, CorpusGraphNode],
    edges: MutableMapping[str, CorpusGraphEdge],
) -> None:
    for model in corpus.documents:
        labels = _record_labels(model)
        for record in (*model.definitions, *model.requirements):
            kind, label, source = labels[record.id]
            _add_node(nodes, model.document_id, record.id, kind, label, source)
        for dependency in model.semantic_dependencies():
            source_details = labels.get(dependency.source_record_id)
            source_node = _add_node(
                nodes,
                dependency.source_document_id,
                dependency.source_record_id,
                dependency.source_kind,
                source_details[1] if source_details else dependency.source_record_id,
                source_details[2] if source_details else dependency.source,
            )
            target_details = labels.get(dependency.target_record_id)
            target_node = _add_node(
                nodes,
                dependency.target_document_id,
                dependency.target_record_id,
                dependency.target_kind,
                target_details[1] if target_details else dependency.target_record_id,
                target_details[2] if target_details else None,
                external=dependency.target_document_id not in document_ids,
            )
            edge_id = f"dependency:{dependency.id}"
            edges.setdefault(
                edge_id,
                CorpusGraphEdge(
                    id=edge_id,
                    source_node_id=source_node,
                    target_node_id=target_node,
                    relation=dependency.relation,
                    evidence=_edge_evidence(dependency),
                    source=dependency.source,
                ),
            )


def _candidate_records(
    corpus: ComplianceCorpus,
) -> tuple[
    dict[str, list[RecordRef]],
    dict[str, list[RecordRef]],
    list[CandidateRecord],
    list[CandidateRecord],
]:
    definitions: dict[str, list[RecordRef]] = defaultdict(list)
    requirements: dict[str, list[RecordRef]] = defaultdict(list)
    definition_records: list[CandidateRecord] = []
    requirement_records: list[CandidateRecord] = []
    for model in corpus.documents:
        for definition in model.definitions:
            normalized_term = _normalized_text(definition.term)
            normalized_text = _normalized_text(definition.text)
            definitions[normalized_term].append(
                (model.document_id, definition.id, definition.source)
            )
            definition_records.append(
                (
                    model.document_id,
                    definition.id,
                    definition.source,
                    definition.text,
                    normalized_text,
                    frozenset(normalized_text.split()),
                )
            )
        for requirement in model.requirements:
            normalized_statement = _normalized_text(requirement.statement)
            requirements[normalized_statement].append(
                (model.document_id, requirement.id, requirement.source)
            )
            requirement_records.append(
                (
                    model.document_id,
                    requirement.id,
                    requirement.source,
                    requirement.statement,
                    normalized_statement,
                    frozenset(normalized_statement.split()),
                )
            )
    return definitions, requirements, definition_records, requirement_records


def _add_candidate_edges(
    groups: Mapping[str, Sequence[RecordRef]],
    relation: Literal["shared-definition-term", "shared-requirement-statement"],
    note: str,
    edges: MutableMapping[str, CorpusGraphEdge],
) -> None:
    for normalized, records in sorted(groups.items()):
        if not normalized:
            continue
        for left, right in combinations(sorted(records), 2):
            if left[0] == right[0]:
                continue
            source = _qualified_id(left[0], left[1])
            target = _qualified_id(right[0], right[1])
            edge_id = f"candidate:{relation}:{source}->{target}"
            edges.setdefault(
                edge_id,
                CorpusGraphEdge(
                    id=edge_id,
                    source_node_id=source,
                    target_node_id=target,
                    relation=relation,
                    evidence="candidate",
                    confidence=1.0,
                    note=note,
                    source=left[2],
                ),
            )


def _add_finding(
    findings: MutableMapping[str, CorpusGraphFinding],
    kind: FindingKind,
    severity: FindingSeverity,
    left: CandidateRecord,
    right: CandidateRecord,
    similarity: float,
    message: str,
) -> None:
    node_ids = tuple(sorted((_qualified_id(left[0], left[1]), _qualified_id(right[0], right[1]))))
    document_ids = tuple(sorted({left[0], right[0]}))
    finding_id = f"{kind}:{node_ids[0]}:{node_ids[1]}"
    findings.setdefault(
        finding_id,
        CorpusGraphFinding(
            id=finding_id,
            kind=kind,
            severity=severity,
            document_ids=document_ids,
            node_ids=node_ids,
            similarity=similarity,
            message=message,
            source=left[2],
        ),
    )


def _same_term_definition_findings(
    definitions: Mapping[str, Sequence[RecordRef]],
    definition_records: Sequence[CandidateRecord],
    findings: MutableMapping[str, CorpusGraphFinding],
) -> None:
    definition_by_id = {(item[0], item[1]): item for item in definition_records}
    for _normalized, records in sorted(definitions.items()):
        for left_key, right_key in combinations(sorted(records), 2):
            if left_key[0] == right_key[0]:
                continue
            left = definition_by_id[(left_key[0], left_key[1])]
            right = definition_by_id[(right_key[0], right_key[1])]
            same_text = left[4] == right[4]
            _add_finding(
                findings,
                "duplicate-definition" if same_text else "conflicting-definition",
                "info" if same_text else "warning",
                left,
                right,
                1.0 if same_text else _token_similarity(left[5], right[5]),
                "Exact term and definition text match; review before merging records."
                if same_text
                else "The same normalized term has different definition text across documents.",
            )


def _near_duplicate_definition_findings(
    definition_records: Sequence[CandidateRecord],
    findings: MutableMapping[str, CorpusGraphFinding],
) -> None:
    ordered = sorted(definition_records, key=lambda item: item[:2])
    for left, right in combinations(ordered, 2):
        if left[0] == right[0] or left[4] == right[4]:
            continue
        similarity = _token_similarity(left[5], right[5])
        if similarity >= 0.92:
            _add_finding(
                findings,
                "near-duplicate-definition",
                "warning",
                left,
                right,
                similarity,
                "Definition text is highly similar across documents; review for duplication.",
            )


def _requirement_findings(
    requirement_records: Sequence[CandidateRecord],
    findings: MutableMapping[str, CorpusGraphFinding],
) -> None:
    for left, right in _near_duplicate_pairs(requirement_records):
        if left[4] == right[4]:
            _add_finding(
                findings,
                "duplicate-requirement",
                "info",
                left,
                right,
                1.0,
                "Exact normative statement match; review for shared semantic ownership.",
            )
            continue
        similarity = _token_similarity(left[5], right[5])
        if similarity >= 0.92:
            _add_finding(
                findings,
                "near-duplicate-requirement",
                "warning",
                left,
                right,
                similarity,
                (
                    "Normative statements are highly similar across documents; "
                    "review their relationship."
                ),
            )


def build_corpus_graph(
    corpus: ComplianceCorpus,
    *,
    metadata: Mapping[str, CorpusDocumentDescriptor] | None = None,
) -> CorpusSemanticGraph:
    """Build a deterministic graph from a validated corpus.

    Existing semantic dependencies become graph edges.  Exact definition-term
    matches are added as candidate edges only; they are intentionally not
    emitted as normative references or merged records.
    """
    descriptors = _document_descriptors(corpus, metadata)
    nodes: dict[str, CorpusGraphNode] = {}
    edges: dict[str, CorpusGraphEdge] = {}
    document_ids = {item.document_id for item in corpus.documents}
    _add_dependency_edges(corpus, document_ids, nodes, edges)

    definitions, requirements, definition_records, requirement_records = _candidate_records(corpus)
    _add_candidate_edges(
        definitions,
        "shared-definition-term",
        "Exact normalized term match; review before treating as equivalent.",
        edges,
    )
    _add_candidate_edges(
        requirements,
        "shared-requirement-statement",
        "Exact normalized statement match; review before treating as shared normative text.",
        edges,
    )
    findings: dict[str, CorpusGraphFinding] = {}
    _same_term_definition_findings(definitions, definition_records, findings)
    _near_duplicate_definition_findings(definition_records, findings)
    _requirement_findings(requirement_records, findings)
    return CorpusSemanticGraph(
        documents=descriptors,
        nodes=tuple(sorted(nodes.values(), key=lambda item: item.id)),
        edges=tuple(sorted(edges.values(), key=lambda item: item.id)),
        findings=tuple(sorted(findings.values(), key=lambda item: item.id)),
    )


def load_corpus_graph(path: Path) -> CorpusSemanticGraph:
    """Load a graph emitted by this module and validate it with Pydantic."""
    return CorpusSemanticGraph.model_validate_json(path.read_text(encoding="utf-8"))


def load_document_metadata(path: Path) -> dict[str, CorpusDocumentDescriptor]:
    """Load source-controlled descriptors keyed by stable document ID."""
    payload = CorpusDocumentMetadataFile.model_validate_json(path.read_text(encoding="utf-8"))
    return {item.document_id: item for item in payload.documents}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "semantic_model",
        type=Path,
        help="A generated semantic-model.json containing a documents array",
    )
    parser.add_argument("--output", type=Path, help="Write the graph JSON to this path")
    args = parser.parse_args()
    payload = json.loads(args.semantic_model.read_text(encoding="utf-8"))
    corpus = ComplianceCorpus.model_validate({"documents": payload["documents"]})
    graph = build_corpus_graph(corpus)
    payload = graph.to_json()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


if __name__ == "__main__":
    main()
