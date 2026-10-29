"""Primitive semantic model contracts shared by domain modules."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RequirementApplicabilityRelation = Literal[
    "transition", "reviewed-link", "implementation", "clause-fallback"
]


class SemanticRecord(BaseModel):
    """Shared strict contract for semantic records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(SemanticRecord):
    path: Annotated[str, Field(min_length=1)]
    line: Annotated[int, Field(ge=1)]
    end_line: Annotated[int | None, Field(ge=1)] = None

    @model_validator(mode="after")
    def validate_span(self) -> SourceRef:
        if self.end_line is not None and self.end_line < self.line:
            raise ValueError("source end_line must not precede line")
        return self
