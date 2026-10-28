"""Pydantic contracts for source-navigation manifests."""

from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import BaseModel, ConfigDict, Field

from hla_lab.core.semantic_base import SourceRef

LegacyNavigationEntry: TypeAlias = tuple[int, str] | tuple[int, str, int]


class NavigationOutlineItem(BaseModel):
    """One structured clause in a canonical navigation outline."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    id: Annotated[str, Field(min_length=1)]
    number: Annotated[str, Field(min_length=1)]
    title: str
    parent_id: str | None = None
    level: Annotated[int, Field(ge=1)]
    source: SourceRef | None = None


NavigationOutlineEntry: TypeAlias = NavigationOutlineItem | LegacyNavigationEntry


class SourceNavigationManifest(BaseModel):
    """Current structured and legacy array navigation formats."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: Annotated[int, Field(ge=1)]
    document: str | None = None
    page_count: Annotated[int | None, Field(ge=1)] = None
    outline: tuple[NavigationOutlineEntry, ...] = ()
    notes: str | None = None
