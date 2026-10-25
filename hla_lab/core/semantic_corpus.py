"""Extract reusable semantic records from source-first LaTeX documents."""

from __future__ import annotations

from typing import Literal

from pydantic import model_validator

from hla_lab.core.semantic_document import DocumentModel
from hla_lab.core.semantic_types import (
    ComplianceCorpusReport,
    ComplianceDependency,
    ComplianceIssue,
    ComplianceQueryResult,
    ImplementationEvidence,
    OperationalImplication,
    RequirementApplicability,
    SemanticRecord,
    TransitionImplementationCoverage,
)

__all__ = ["ComplianceCorpus"]


class ComplianceCorpus(SemanticRecord):
    """A collection of documents used to resolve cross-document targets."""

    documents: tuple[DocumentModel, ...]

    @model_validator(mode="after")
    def validate_document_ids(self) -> ComplianceCorpus:
        document_ids = [item.document_id for item in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("document IDs must be unique in a compliance corpus")
        return self

    def document(self, document_id: str) -> DocumentModel:
        """Return one document by stable corpus ID."""
        document = next(
            (item for item in self.documents if item.document_id == document_id),
            None,
        )
        if document is None:
            raise ValueError(f"unknown document {document_id}")
        return document

    def _selected_documents(self, document_id: str | None = None) -> tuple[DocumentModel, ...]:
        """Return either the requested document or the complete corpus."""
        return (self.document(document_id),) if document_id is not None else self.documents

    def compliance_query(
        self,
        document_id: str,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> ComplianceQueryResult:
        """Run the generic compliance query against one corpus document."""
        return self.document(document_id).compliance_query(
            state_id,
            event,
            machine_id,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )

    def requirements_applicable_after(
        self,
        state_id: str,
        event: str,
        document_id: str | None = None,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
    ) -> tuple[RequirementApplicability, ...]:
        """Query state/event requirements across one or every corpus document."""
        result: list[RequirementApplicability] = []
        for document in self._selected_documents(document_id):
            if not document.state_machines:
                if document_id is not None:
                    raise ValueError(f"document {document.document_id} has no state machines")
                continue
            result.extend(
                document.query_requirements_applicable_after(
                    state_id,
                    event,
                    machine_id,
                    include_candidates=include_candidates,
                )
            )
        return tuple(result)

    def state_sequence_implications(
        self,
        document_id: str | None = None,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        sequence_diagram_id: str | None = None,
        include_unlinked: bool = True,
    ) -> tuple[OperationalImplication, ...]:
        """Query state and sequence implications with document-qualified results."""
        result: list[OperationalImplication] = []
        for document in self._selected_documents(document_id):
            if state_id is not None and not document.state_machines:
                if document_id is not None:
                    raise ValueError(f"document {document.document_id} has no state machines")
                continue
            result.extend(
                document.state_sequence_implications(
                    state_id,
                    event,
                    machine_id,
                    sequence_diagram_id=sequence_diagram_id,
                    include_unlinked=include_unlinked,
                )
            )
        return tuple(result)

    def semantic_dependencies(
        self,
        document_id: str | None = None,
        record_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return qualified dependency edges across the selected documents."""
        edges = [
            edge
            for document in self._selected_documents(document_id)
            for edge in document.semantic_dependencies(record_id)
        ]
        return tuple(sorted({edge.id: edge for edge in edges}.values(), key=lambda item: item.id))

    def dependencies_for_record(
        self,
        record_id: str,
        document_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return dependency edges touching a record, qualified by document."""
        return self.semantic_dependencies(document_id, record_id)

    def table_definition_dependencies(
        self,
        document_id: str | None = None,
    ) -> tuple[ComplianceDependency, ...]:
        """Return table/family/cell and definition dependency edges."""
        interesting = {"table", "table-family", "table-cell", "definition"}
        return tuple(
            edge
            for edge in self.semantic_dependencies(document_id)
            if edge.source_kind in interesting or edge.target_kind in interesting
        )

    def transitions_without_implementation_mappings(
        self,
        document_id: str | None = None,
        machine_id: str | None = None,
    ) -> tuple[TransitionImplementationCoverage, ...]:
        """Return qualified coverage records for transitions with no mapping."""
        result: list[TransitionImplementationCoverage] = []
        for document in self._selected_documents(document_id):
            selected_machine = machine_id if document_id is not None else None
            for transition in document.transitions_without_implementation_mapping(selected_machine):
                result.append(
                    document.implementation_coverage_for_transition(
                        transition.id,
                        selected_machine,
                    )
                )
        return tuple(result)

    def transitions_without_concrete_implementations(
        self,
        document_id: str | None = None,
        machine_id: str | None = None,
    ) -> tuple[TransitionImplementationCoverage, ...]:
        """Return qualified coverage records lacking implemented/verified evidence."""
        result: list[TransitionImplementationCoverage] = []
        for document in self._selected_documents(document_id):
            selected_machine = machine_id if document_id is not None else None
            for transition in document.transitions_without_concrete_implementation(
                selected_machine
            ):
                result.append(
                    document.implementation_coverage_for_transition(
                        transition.id,
                        selected_machine,
                    )
                )
        return tuple(result)

    def implementation_evidence(
        self,
        document_id: str | None = None,
        *,
        status: Literal["planned", "partial", "implemented", "verified"] | None = None,
        concrete: bool | None = None,
    ) -> tuple[ImplementationEvidence, ...]:
        """Return corpus-qualified planned, partial, implemented, or verified mappings."""
        evidence = tuple(
            item
            for document in self._selected_documents(document_id)
            for item in document.implementation_evidence(status=status, concrete=concrete)
        )
        return tuple(sorted(evidence, key=lambda item: (item.document_id, item.mapping_id)))

    def compliance_report(
        self,
        document_id: str | None = None,
        state_id: str | None = None,
        event: str | None = None,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
        dependency_record_id: str | None = None,
        include_unlinked_implications: bool = True,
    ) -> ComplianceCorpusReport:
        """Build the complete serializable M24 compliance-facing corpus report."""
        if (state_id is None) != (event is None):
            raise ValueError("state_id and event must be supplied together")
        selected = self._selected_documents(document_id)
        applicable = (
            self.requirements_applicable_after(
                state_id,
                event,
                document_id,
                machine_id,
                include_candidates=include_candidates,
            )
            if state_id is not None and event is not None
            else ()
        )
        implications = self.state_sequence_implications(
            document_id,
            state_id,
            event,
            machine_id,
            include_unlinked=include_unlinked_implications,
        )
        issues = self.compliance_issues(
            machine_id if document_id is not None else None,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )
        status_counts = {
            document.document_id: document.implementation_status_counts(
                machine_id if document_id is not None else None
            )
            for document in selected
        }
        implication_counts = {
            relation: sum(item.relation == relation for item in implications)
            for relation in ("direct", "clause-context", "unlinked")
        }
        table_definition_coverage = {
            document.document_id: document.table_definition_dependency_counts()
            for document in selected
        }
        return ComplianceCorpusReport(
            document_ids=tuple(document.document_id for document in selected),
            applicable_requirements=applicable,
            state_sequence_implications=implications,
            dependencies=self.semantic_dependencies(document_id, dependency_record_id),
            missing_implementation_mappings=self.transitions_without_implementation_mappings(
                document_id,
                machine_id,
            ),
            implementation_evidence=self.implementation_evidence(document_id),
            unresolved_references=self.unresolved_reference_issues(),
            issues=issues,
            implementation_status_counts=status_counts,
            operational_implication_counts=implication_counts,
            table_definition_coverage=table_definition_coverage,
        )

    def assert_compliance_surfaces_classified(self, document_id: str | None = None) -> None:
        """Raise unless operational surfaces are represented or explicitly unlinked."""
        selected = self._selected_documents(document_id)
        report = self.compliance_report(document_id)
        expected_messages = {
            message.id
            for document in selected
            for diagram in document.sequence_diagrams
            for message in diagram.messages
        }
        actual_messages = {
            item.record_id
            for item in report.state_sequence_implications
            if item.kind == "sequence-message"
        }
        if actual_messages != expected_messages:
            missing = sorted(expected_messages - actual_messages)
            extra = sorted(actual_messages - expected_messages)
            raise ValueError(
                f"sequence-message classification is incomplete (missing={missing}, extra={extra})"
            )
        for document in selected:
            expected_cells = sum(len(table.cells) for table in document.tables)
            observed = report.table_definition_coverage[document.document_id]["cells"]
            if observed != expected_cells:
                raise ValueError(
                    f"table-cell classification is incomplete for {document.document_id}: "
                    f"expected {expected_cells}, observed {observed}"
                )
        if report.unresolved_references:
            raise ValueError(
                "unresolved corpus references: "
                + ", ".join(item.record_id for item in report.unresolved_references)
            )

    def unresolved_reference_issues(self) -> tuple[ComplianceIssue, ...]:
        """Return unresolved external reference targets as typed issues."""
        documents = {item.document_id: item for item in self.documents}
        # A document can have thousands of targets; build each membership set once.
        record_ids = {
            document_id: frozenset(document.semantic_record_ids())
            for document_id, document in documents.items()
        }
        issues: list[ComplianceIssue] = []
        for document in self.documents:
            for reference in document.references:
                for target in reference.targets:
                    target_document = documents.get(target.document_id)
                    qualified = (
                        f"{document.document_id}:{reference.id}->"
                        f"{target.document_id}:{target.record_id}"
                    )
                    if target_document is None:
                        issues.append(
                            ComplianceIssue(
                                code="unresolved-reference",
                                severity="error",
                                record_id=qualified,
                                message=(
                                    f"reference target document does not exist: "
                                    f"{target.document_id}"
                                ),
                            )
                        )
                    elif target.record_id not in record_ids[target.document_id]:
                        issues.append(
                            ComplianceIssue(
                                code="unresolved-reference",
                                severity="error",
                                record_id=qualified,
                                message=(
                                    f"reference target record does not exist in "
                                    f"{target.document_id}: {target.record_id}"
                                ),
                            )
                        )
            for cross_reference in document.cross_references:
                target_document = documents.get(cross_reference.target_document_id)
                qualified = (
                    f"{document.document_id}:{cross_reference.owner_id}->"
                    f"{cross_reference.target_document_id}:{cross_reference.target_record_id}"
                )
                if target_document is None:
                    issues.append(
                        ComplianceIssue(
                            code="unresolved-reference",
                            severity="error",
                            record_id=qualified,
                            message=(
                                f"cross-reference target document does not exist: "
                                f"{cross_reference.target_document_id}"
                            ),
                        )
                    )
                elif (
                    cross_reference.target_record_id
                    not in record_ids[cross_reference.target_document_id]
                ):
                    issues.append(
                        ComplianceIssue(
                            code="unresolved-reference",
                            severity="error",
                            record_id=qualified,
                            message=(
                                f"cross-reference target record does not exist in "
                                f"{cross_reference.target_document_id}: "
                                f"{cross_reference.target_record_id}"
                            ),
                        )
                    )
        return tuple(issues)

    def compliance_issues(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> tuple[ComplianceIssue, ...]:
        """Return document coverage findings plus cross-document failures."""
        issues = []
        for document in self.documents:
            selected_machine = (
                machine_id
                if machine_id in {machine.id for machine in document.state_machines}
                else None
            )
            issues.extend(
                document.compliance_issues(
                    selected_machine,
                    include_candidates=include_candidates,
                    require_concrete_implementation=require_concrete_implementation,
                )
            )
        issues.extend(self.unresolved_reference_issues())
        return tuple(issues)

    def assert_compliance(
        self,
        machine_id: str | None = None,
        *,
        include_candidates: bool = False,
        require_concrete_implementation: bool = False,
    ) -> None:
        """Raise when any document or cross-document compliance issue exists."""
        issues = self.compliance_issues(
            machine_id,
            include_candidates=include_candidates,
            require_concrete_implementation=require_concrete_implementation,
        )
        if issues:
            raise ValueError("; ".join(f"{item.code}: {item.record_id}" for item in issues))

    def assert_references_resolved(self) -> None:
        """Raise when a cross-document target cannot be resolved."""
        issues = self.unresolved_reference_issues()
        if issues:
            raise ValueError("; ".join(f"{item.code}: {item.record_id}" for item in issues))
