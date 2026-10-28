"""Pydantic contract for the extracted diagram review inventory."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

DiagramType = Literal[
    "ddm_conceptual_diagram",
    "message_sequence",
    "mom_class_hierarchy",
    "other_asset",
    "protocol_architecture",
    "relationship_view",
    "state_machine",
    "unclassified",
]
DiagramStatus = Literal[
    "accepted",
    "classified",
    "draft",
    "needs_review",
    "rendered",
    "unmodeled",
    "validated",
]
ReviewPriority = Literal["high", "low", "medium", "none"]
InventoryStatus = Literal["inventoried", "not_started", "reviewed_no_state_diagrams"]


class DiagramInventoryEntry(BaseModel):
    """Classification and review metadata for one extracted source image."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    diagram_id: Annotated[str, Field(min_length=1)]
    source_image: Annotated[str, Field(min_length=1)]
    document: Annotated[str, Field(min_length=1)]
    page: Annotated[int, Field(ge=1)]
    xref: Annotated[str, Field(min_length=1)]
    diagram_type: DiagramType
    status: DiagramStatus
    model: str | None = None
    confidence: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    notes: str = ""
    review_priority: ReviewPriority = "none"
    review_reason: str = ""


class DocumentInventoryScope(BaseModel):
    """Inventory coverage for one source document's extracted-image directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document: Annotated[str, Field(min_length=1)]
    source_directory: Annotated[str, Field(min_length=1)]
    inventory_status: InventoryStatus
    extracted_candidates: Annotated[int, Field(ge=0)]
    notes: str = ""


class StateMachineInventory(BaseModel):
    """Validated state-machine diagram inventory and review queue."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["0.1"]
    generated_by: Literal["hla_lab/diagrams/inventory_state_machines.py"]
    document_scopes: tuple[DocumentInventoryScope, ...]
    diagrams: tuple[DiagramInventoryEntry, ...]

    @model_validator(mode="after")
    def validate_unique_inventory_ids(self) -> StateMachineInventory:
        diagram_ids = [item.diagram_id for item in self.diagrams]
        if len(diagram_ids) != len(set(diagram_ids)):
            raise ValueError("diagram inventory IDs must be unique")
        documents = [item.document for item in self.document_scopes]
        if len(documents) != len(set(documents)):
            raise ValueError("document inventory scopes must be unique")
        return self
