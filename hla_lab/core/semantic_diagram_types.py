"""Typed semantic records for state, sequence, and generic diagrams."""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import Annotated, Literal, TypeAlias

from pydantic import Field, model_validator

from hla_lab.core.semantic_base import (
    RequirementApplicabilityRelation,
    SemanticRecord,
    SourceRef,
)


class State(SemanticRecord):
    """A named state in a document-defined state machine."""

    id: Annotated[str, Field(min_length=1)]
    label: str
    parent_id: str | None = None
    kind: Annotated[str, Field(min_length=1)] = "state"
    source: SourceRef | None = None

    @model_validator(mode="after")
    def validate_label(self) -> State:
        if not self.label and self.kind not in {"initial", "final", "history"}:
            raise ValueError("only initial/final/history pseudostates may have empty labels")
        return self


class Transition(SemanticRecord):
    """A state-machine transition with explicit conformance-oriented fields."""

    id: Annotated[str, Field(min_length=1)]
    source_state: str | None
    event: str
    target_state: str | None
    initiator: Literal["federate", "rti", "automatic", "unknown"] = "unknown"
    guard: str = ""
    action: str = ""
    precondition: str = ""
    postcondition: str = ""
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    implementation_ids: tuple[str, ...] = ()
    source: SourceRef | None = None


class DiagramProvenance(SemanticRecord):
    image: Annotated[str, Field(min_length=1)]
    page: Annotated[int, Field(ge=1)]
    xref: str | None = None
    caption: str = ""


class NodePosition(SemanticRecord):
    x: float
    y: float
    visible: bool = True


class LayoutContainer(SemanticRecord):
    id: Annotated[str, Field(min_length=1)]
    x: float
    y: float
    width: Annotated[float, Field(gt=0)]
    height: Annotated[float, Field(gt=0)]
    title: Annotated[str, Field(min_length=1)]
    visible: bool = True
    title_visible: bool = True


class TransitionLayout(SemanticRecord):
    """Manual geometry hints for a rendered transition label or edge."""

    style: Annotated[str, Field(min_length=1)] = "straight"
    loop_direction: Literal["left", "right", "above", "below"] | None = None
    label: str | None = None
    bend: float | None = None
    label_side: Literal["above", "below", "left", "right"] | None = None
    label_pos: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    label_x: float | None = None
    label_y: float | None = None
    label_width: Annotated[float | None, Field(gt=0.0)] = None
    label_align: Literal["left", "center", "right"] | None = None
    label_visible: bool = True


class LayoutRule(SemanticRecord):
    """A manual guide line retained as layout data, not state semantics."""

    x1: float
    y1: float
    x2: float
    y2: float
    style: str = "solid"


class LayoutAnnotation(SemanticRecord):
    """A text label positioned by the diagram layout adapter."""

    id: Annotated[str, Field(min_length=1)]
    x: float
    y: float
    text: Annotated[str, Field(min_length=1)]
    width: Annotated[float | None, Field(gt=0)] = None
    align: Literal["left", "center", "right"] = "left"


class StateMachineLayout(SemanticRecord):
    engine: Literal["automatic", "manual"] = "automatic"
    direction: Literal["left-to-right", "top-to-bottom"] = "top-to-bottom"
    state_font: str | None = None
    edge_label_font: str | None = None
    edge_label_distance: Annotated[float | None, Field(ge=0.0)] = None
    containers: tuple[LayoutContainer, ...] = ()
    nodes: Annotated[Mapping[str, NodePosition], Field(default_factory=dict)]
    transitions: Annotated[Mapping[str, TransitionLayout], Field(default_factory=dict)]
    rules: tuple[LayoutRule, ...] = ()
    annotations: tuple[LayoutAnnotation, ...] = ()


class StateMachine(SemanticRecord):
    """A reusable state machine linked to the document hierarchy."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    states: tuple[State, ...]
    transitions: tuple[Transition, ...]
    initial_state_ids: tuple[str, ...] = ()
    clause_id: str | None = None
    source: SourceRef | None = None
    provenance: DiagramProvenance | None = None
    layout: StateMachineLayout | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_graph_ids(self) -> StateMachine:
        state_ids = [state.id for state in self.states]
        transition_ids = [transition.id for transition in self.transitions]
        if len(state_ids) != len(set(state_ids)):
            raise ValueError("state IDs must be unique within a state machine")
        if len(transition_ids) != len(set(transition_ids)):
            raise ValueError("transition IDs must be unique within a state machine")
        state_id_set = set(state_ids)
        if any(item not in state_id_set for item in self.initial_state_ids):
            raise ValueError("initial states must reference defined states")
        self._validate_state_hierarchy(state_id_set)
        self._validate_transition_endpoints(state_id_set)
        return self

    def _validate_state_hierarchy(self, state_id_set: AbstractSet[str]) -> None:
        for state in self.states:
            if state.parent_id is not None and state.parent_id not in state_id_set:
                raise ValueError(f"state {state.id} references missing parent {state.parent_id}")
            seen: set[str] = set()
            current = state
            while current.parent_id is not None:
                if current.id in seen:
                    raise ValueError(f"state hierarchy cycle includes {current.id}")
                seen.add(current.id)
                current = next(item for item in self.states if item.id == current.parent_id)

    def _validate_transition_endpoints(self, state_id_set: AbstractSet[str]) -> None:
        for transition in self.transitions:
            for endpoint in (transition.source_state, transition.target_state):
                if endpoint is not None and endpoint not in state_id_set:
                    raise ValueError(
                        f"transition {transition.id} references unknown state {endpoint}"
                    )


ApplicabilityMatch: TypeAlias = tuple[
    StateMachine, Transition, dict[str, RequirementApplicabilityRelation]
]
ApplicabilityMatchView: TypeAlias = tuple[
    StateMachine, Transition, Mapping[str, RequirementApplicabilityRelation]
]


class StateMachineFile(SemanticRecord):
    schema_version: Annotated[int, Field(ge=2)]
    state_machines: tuple[StateMachine, ...]


class SequenceParticipant(SemanticRecord):
    """A lifeline in a reusable message-sequence diagram."""

    id: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    role: str = ""


class SequenceMessage(SemanticRecord):
    """An ordered message with explicit direction and optional response correlation."""

    id: Annotated[str, Field(min_length=1)]
    order: Annotated[int, Field(ge=1)]
    source_participant: Annotated[str, Field(min_length=1)]
    target_participant: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    kind: Literal["message", "request", "response", "control", "note"] = "message"
    response_to: str | None = None
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    source: SourceRef | None = None


class SequenceDiagram(SemanticRecord):
    """A document-independent sequence diagram owned by semantic source."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    participants: tuple[SequenceParticipant, ...]
    messages: tuple[SequenceMessage, ...]
    clause_id: str | None = None
    source: SourceRef | None = None
    provenance: DiagramProvenance | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_sequence(self) -> SequenceDiagram:
        participant_ids = [item.id for item in self.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("sequence participant IDs must be unique")
        message_ids = [item.id for item in self.messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("sequence message IDs must be unique")
        orders = [item.order for item in self.messages]
        if len(orders) != len(set(orders)):
            raise ValueError("sequence message order values must be unique")
        participant_id_set = set(participant_ids)
        message_id_set = set(message_ids)
        for message in self.messages:
            if message.source_participant not in participant_id_set:
                raise ValueError(
                    f"sequence message {message.id} references unknown source participant "
                    f"{message.source_participant}"
                )
            if message.target_participant not in participant_id_set:
                raise ValueError(
                    f"sequence message {message.id} references unknown target participant "
                    f"{message.target_participant}"
                )
            if message.response_to is not None and message.response_to not in message_id_set:
                raise ValueError(
                    f"sequence message {message.id} references unknown response "
                    f"{message.response_to}"
                )
        return self


class SequenceDiagramFile(SemanticRecord):
    """Authored sequence diagrams kept out of page-layout source."""

    schema_version: Annotated[int, Field(ge=1)]
    sequence_diagrams: tuple[SequenceDiagram, ...]


class GraphPoint(SemanticRecord):
    """A point in a diagram's document-independent coordinate system."""

    x: float
    y: float


class GraphNode(SemanticRecord):
    """A positioned node used by generic relationship and architecture diagrams."""

    id: Annotated[str, Field(min_length=1)]
    label: Annotated[str, Field(min_length=1)]
    x: float
    y: float
    width: Annotated[float, Field(gt=0)]
    height: Annotated[float, Field(gt=0)]
    style: Literal["box", "frame", "lifeline", "ellipse", "point", "invisible"] = "box"
    parent_id: str | None = None
    visible: bool = True


class GraphEdge(SemanticRecord):
    """A directed, undirected, dotted, or dimension relationship between nodes."""

    id: Annotated[str, Field(min_length=1)]
    source: str | None = None
    target: str | None = None
    label: str = ""
    style: Literal["solid", "dotted", "dashed", "dimension"] = "solid"
    direction: Literal["none", "forward", "reverse", "both"] = "forward"
    points: tuple[GraphPoint, ...] = ()
    clause_id: str | None = None
    requirement_ids: tuple[str, ...] = ()
    implementation_ids: tuple[str, ...] = ()
    source_ref: SourceRef | None = None


class GraphAnnotation(SemanticRecord):
    """Free-standing text or measurement label positioned by semantic data."""

    id: Annotated[str, Field(min_length=1)]
    x: float
    y: float
    text: Annotated[str, Field(min_length=1)]
    width: Annotated[float | None, Field(gt=0)] = None
    align: Literal["left", "center", "right"] = "center"
    rotate: float = 0.0


class GraphDiagram(SemanticRecord):
    """A reusable non-state diagram with explicit nodes, edges, and annotations."""

    id: Annotated[str, Field(min_length=1)]
    title: Annotated[str, Field(min_length=1)]
    kind: Literal["relationship", "conceptual", "hierarchy", "architecture"]
    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphEdge, ...] = ()
    annotations: tuple[GraphAnnotation, ...] = ()
    clause_id: str | None = None
    source: SourceRef | None = None
    provenance: DiagramProvenance | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def validate_graph(self) -> GraphDiagram:
        node_ids = [item.id for item in self.nodes]
        edge_ids = [item.id for item in self.edges]
        annotation_ids = [item.id for item in self.annotations]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("graph node IDs must be unique")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("graph edge IDs must be unique")
        if len(annotation_ids) != len(set(annotation_ids)):
            raise ValueError("graph annotation IDs must be unique")
        node_id_set = set(node_ids)
        for node in self.nodes:
            if node.parent_id is not None and node.parent_id not in node_id_set:
                raise ValueError(f"graph node {node.id} references missing parent {node.parent_id}")
        for edge in self.edges:
            if edge.source is not None and edge.source not in node_id_set:
                raise ValueError(f"graph edge {edge.id} references missing source {edge.source}")
            if edge.target is not None and edge.target not in node_id_set:
                raise ValueError(f"graph edge {edge.id} references missing target {edge.target}")
            if not edge.points and (edge.source is None or edge.target is None):
                raise ValueError(
                    f"graph edge {edge.id} needs source/target nodes or explicit points"
                )
        return self


class GraphDiagramFile(SemanticRecord):
    """Authored generic diagrams kept out of hand-written page layout."""

    schema_version: Annotated[int, Field(ge=1)]
    graph_diagrams: tuple[GraphDiagram, ...]


class DiagramSurface(SemanticRecord):
    """Inventory classification for every source figure or extracted asset."""

    id: Annotated[str, Field(min_length=1)]
    document_id: Annotated[str, Field(min_length=1)]
    page: Annotated[int, Field(ge=1)]
    figure_number: Annotated[int | None, Field(ge=1)] = None
    status: Literal["generated", "non-generatable"]
    record_id: str | None = None
    record_kind: Literal["state_machine", "sequence_diagram", "graph_diagram", "asset"]
    source_image: str | None = None
    reason: str = ""

    @model_validator(mode="after")
    def validate_surface(self) -> DiagramSurface:
        if self.status == "generated" and (self.figure_number is None or self.record_id is None):
            raise ValueError("generated diagram surfaces require figure_number and record_id")
        if self.status == "non-generatable" and not self.reason.strip():
            raise ValueError("non-generatable surfaces require a reason")
        return self


class DiagramSurfaceFile(SemanticRecord):
    """Source-controlled contract for complete figure-surface classification."""

    schema_version: Annotated[int, Field(ge=1)]
    surfaces: tuple[DiagramSurface, ...]
