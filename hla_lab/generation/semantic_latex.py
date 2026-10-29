"""Compatibility rendering facade for the HLA LaTeX dialect."""

from __future__ import annotations

from collections.abc import Iterable

from hla_lab.adapters.latex_renderer import render_clause_heading as _render_clause_heading
from hla_lab.adapters.latex_renderer import (
    render_cross_document_link as _render_cross_document_link,
)
from hla_lab.adapters.latex_renderer import render_definition as _render_definition
from hla_lab.adapters.latex_renderer import render_outline as _render_outline
from hla_lab.adapters.latex_renderer import render_records as _render_records
from hla_lab.adapters.latex_renderer import render_requirement as _render_requirement
from hla_lab.adapters.latex_renderer import render_table as _render_table
from hla_lab.adapters.latex_renderer import render_transition_event as _render_transition_event
from hla_lab.adapters.latex_renderer import tex_escape
from hla_lab.core.hla_profile import HLA_LATEX_DIALECT
from hla_lab.core.semantic_model import (
    Clause,
    Definition,
    DocumentModel,
    Requirement,
    Table,
    Transition,
)

__all__ = [
    "render_clause_heading",
    "render_cross_document_link",
    "render_definition",
    "render_outline",
    "render_records",
    "render_requirement",
    "render_table",
    "render_transition_event",
    "tex_escape",
]


def render_clause_heading(clause: Clause) -> str:
    return _render_clause_heading(clause, HLA_LATEX_DIALECT)


def render_definition(definition: Definition) -> str:
    return _render_definition(definition, HLA_LATEX_DIALECT)


def render_requirement(requirement: Requirement) -> str:
    return _render_requirement(requirement, HLA_LATEX_DIALECT)


def render_table(table: Table) -> str:
    return _render_table(table, HLA_LATEX_DIALECT)


def render_cross_document_link(label: str, target_document: str, target_id: str) -> str:
    return _render_cross_document_link(
        label,
        target_document,
        target_id,
        HLA_LATEX_DIALECT,
    )


def render_transition_event(transition: Transition) -> str:
    """Render HLA's RTI dagger from semantic initiator data."""
    suffix = r"\textdagger{}" if transition.initiator == "rti" else ""
    return _render_transition_event(transition, suffix)


def render_outline(model: DocumentModel) -> str:
    return _render_outline(model, HLA_LATEX_DIALECT)


def render_records(
    model: DocumentModel,
    *,
    definitions: Iterable[Definition] = (),
    requirements: Iterable[Requirement] = (),
    tables: Iterable[Table] = (),
) -> str:
    return _render_records(
        model,
        HLA_LATEX_DIALECT,
        definitions=definitions,
        requirements=requirements,
        tables=tables,
    )
