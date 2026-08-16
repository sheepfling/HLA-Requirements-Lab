"""Acceptance tests for the generated RTI compliance requirements publication."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.semantic_model import (
    Clause,
    ComplianceCorpus,
    DocumentModel,
    ImplementationMapping,
    Requirement,
    RequirementLink,
    SourceRef,
    State,
    StateMachine,
    Transition,
)
from hla_lab.corpus.corpus_graph import CorpusSemanticGraph, build_corpus_graph
from hla_lab.publication.compliance_publication import (
    CompliancePublicationManifest,
    CompliancePublicationProfile,
    build_compliance_manifest,
    load_compliance_publication_profile,
    render_compliance_document,
    write_compliance_csv_exports,
    write_compliance_publication,
)

ROOT = Path(__file__).resolve().parents[1]


def _source(line: int) -> SourceRef:
    return SourceRef(path="fixture.tex", line=line)


def _corpus() -> ComplianceCorpus:
    clause = Clause(
        id="clause-1",
        number="1",
        title="Service contract",
        parent_id=None,
        level=1,
        source=_source(1),
    )
    requirement = Requirement(
        id="requirement-connect",
        title="Connect before use",
        statement="The RTI shall establish a connection before serving requests.",
        kind="detailed",
        clause="1",
        transition_ids=("transition-connect",),
        source=_source(2),
    )
    transition = Transition(
        id="transition-connect",
        source_state="offline",
        event="Connect",
        target_state="online",
        precondition="The caller is not connected.",
        postcondition="The caller is connected.",
        clause_id=clause.id,
        requirement_ids=(requirement.id,),
        implementation_ids=("mapping-connect",),
        source=_source(3),
    )
    machine = StateMachine(
        id="connection",
        title="Connection lifecycle",
        states=(
            State(id="offline", label="Offline", source=_source(4)),
            State(id="online", label="Online", source=_source(5)),
        ),
        transitions=(transition,),
        clause_id=clause.id,
        source=_source(3),
    )
    mapping = ImplementationMapping(
        id="mapping-connect",
        interface_kind="service",
        interface_name="Connect",
        implementation="rti.connect",
        status="planned",
        clause_ids=(clause.id,),
        requirement_ids=(requirement.id,),
        transition_ids=(transition.id,),
        source=_source(6),
    )
    return ComplianceCorpus(
        documents=(
            DocumentModel(
                document_id="fixture-2025",
                clauses=(clause,),
                definitions=(),
                requirements=(requirement,),
                state_machines=(machine,),
                requirement_links=(
                    RequirementLink(
                        id="requirement-link-connect",
                        requirement_id=requirement.id,
                        transition_id=transition.id,
                        source=_source(7),
                    ),
                ),
                implementations=(mapping,),
            ),
        )
    )


def _profile() -> CompliancePublicationProfile:
    return CompliancePublicationProfile(
        schema_version=1,
        publication_id="fixture-compliance",
        title="Fixture Compliance Requirements",
        document_ids=("fixture-2025",),
        scope_statement="Fixture scope.",
        evidence_boundary="Planned mappings are not concrete implementation evidence.",
    )


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class CompliancePublicationTests(unittest.TestCase):
    def test_manifest_is_typed_and_connects_requirements_to_operational_evidence(self) -> None:
        manifest = build_compliance_manifest(_corpus(), _profile())

        self.assertEqual(manifest.summary.requirement_count, 1)
        self.assertEqual(manifest.summary.operational_transition_count, 1)
        self.assertEqual(manifest.summary.implementation_mapping_count, 1)
        self.assertEqual(manifest.summary.concrete_implementation_count, 0)
        self.assertEqual(manifest.requirements[0].evidence_status, "planned")
        self.assertEqual(manifest.operations[0].implementation_status, "planned")
        self.assertFalse(manifest.operations[0].concrete)
        self.assertEqual(manifest.gaps[0].code, "non-concrete-implementation")
        self.assertEqual(
            CompliancePublicationManifest.model_validate_json(manifest.to_json()),
            manifest,
        )

    def test_semantic_mutation_reaches_pdf_input_and_json_contract(self) -> None:
        corpus = _corpus()
        model = corpus.documents[0]
        payload = model.model_dump(mode="json")
        payload["requirements"][0]["statement"] = (
            "compliance-publication compliance mutation sentinel."
        )
        mutated = type(model).model_validate(payload)
        mutated_corpus = ComplianceCorpus(documents=(mutated,))
        graph = build_corpus_graph(mutated_corpus)
        manifest = build_compliance_manifest(
            mutated_corpus,
            _profile(),
            graph=graph,
        )
        rendered = render_compliance_document(manifest, (mutated,))

        self.assertIn("compliance-publication compliance mutation sentinel.", rendered)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "compliance"
            written = write_compliance_publication(
                mutated_corpus,
                _profile(),
                output,
                graph=graph,
                csv_output=output / "csv",
            )
            self.assertEqual(written, manifest)
            self.assertIn(
                "compliance-publication compliance mutation sentinel.",
                (output / "compliance-requirements.tex").read_text(encoding="utf-8"),
            )
            restored = CompliancePublicationManifest.model_validate_json(
                (output / "compliance-manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(restored, manifest)
            restored_graph = CorpusSemanticGraph.model_validate_json(
                (output / "corpus-graph.json").read_text(encoding="utf-8")
            )
            self.assertEqual(restored_graph, graph)
            requirements = _csv_rows(output / "csv" / "requirements.csv")
            mappings = _csv_rows(output / "csv" / "implementation-mappings.csv")
            requirement_links = _csv_rows(output / "csv" / "requirement-mapping-links.csv")
            transition_links = _csv_rows(output / "csv" / "transition-mapping-links.csv")
            self.assertEqual(
                requirements[0]["statement"], "compliance-publication compliance mutation sentinel."
            )
            self.assertEqual(len(mappings), 1)
            self.assertEqual(len(requirement_links), 1)
            self.assertEqual(len(transition_links), 1)

            direct_csv_output = output / "direct-csv"
            written_paths = write_compliance_csv_exports(manifest, direct_csv_output)
            self.assertEqual(len(written_paths), 5)
            self.assertTrue(all(path.is_file() for path in written_paths))

    def test_publication_normalizes_layout_markers_but_preserves_numeric_percentages(self) -> None:
        model = _corpus().documents[0]
        payload = model.model_dump(mode="json")
        text = "The RTI shall retain 10% capacity % while joining recovered lines."
        payload["requirements"][0]["statement"] = text
        payload["requirements"][0]["machine_statement"] = text
        mutated = type(model).model_validate(payload)

        manifest = build_compliance_manifest(
            ComplianceCorpus(documents=(mutated,)),
            _profile(),
        )
        rendered = render_compliance_document(manifest, (mutated,))

        self.assertEqual(
            manifest.requirements[0].statement,
            "The RTI shall retain 10% capacity while joining recovered lines.",
        )
        self.assertIn("10\\% capacity while", rendered)
        self.assertNotIn("capacity \\% while", rendered)

    def test_hla_publication_profile_is_source_controlled_and_typed(self) -> None:
        profile = load_compliance_publication_profile(
            ROOT / "topics/ieee/hla-rti-compliance-2025/semantic/publication.json"
        )

        self.assertEqual(profile.publication_id, "hla-rti-compliance-requirements-2025")
        self.assertEqual(
            profile.document_ids,
            ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025"),
        )


if __name__ == "__main__":
    unittest.main()
