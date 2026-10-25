"""diagram diagram semantics, rendering, and source-only QA contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE, HLA_SOURCE_2010, source_profile_for_document
from hla_lab.core.semantic_model import (
    DiagramSurfaceFile,
    GraphDiagramFile,
    SequenceDiagramFile,
    load_document_model,
)
from hla_lab.diagrams.diagram_qa import validate_renderable
from hla_lab.diagrams.export_graph_diagram import render_mermaid as render_graph_mermaid
from hla_lab.diagrams.export_graph_diagram import render_tikz as render_graph_tikz
from hla_lab.diagrams.export_plantuml import render as render_plantuml
from hla_lab.diagrams.export_sequence_diagram import render_mermaid, render_tikz
from hla_lab.diagrams.plantuml_qa import (
    validate_models as validate_plantuml_models,
)
from hla_lab.diagrams.plantuml_qa import (
    validate_source as validate_plantuml_source,
)
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.generation.semantic_generation import _cross_edition_plantuml_payload
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
HLA_ROOT = ROOT / "topics" / "ieee" / "hla-1516.1-2025"


class DiagramPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_document_model(HLA_ROOT, HLA_SOURCE)

    def test_sequence_diagrams_are_typed_and_correlated(self) -> None:
        self.assertEqual(len(self.model.sequence_diagrams), 3)
        diagram = next(
            item
            for item in self.model.sequence_diagrams
            if item.id.endswith("figure-23-response-messages")
        )
        self.assertEqual(diagram.messages[-1].response_to, "figure-23-f3")
        self.assertEqual(
            SequenceDiagramFile.model_validate(
                {"schema_version": 1, "sequence_diagrams": [diagram.model_dump(mode="json")]}
            ).sequence_diagrams[0],
            diagram,
        )

    def test_sequence_exports_are_deterministic_text_sources(self) -> None:
        diagram = self.model.sequence_diagrams[2]
        mermaid = render_mermaid(diagram)
        tikz = render_tikz(diagram)
        self.assertIn("sequenceDiagram", mermaid)
        self.assertIn("Resume Request", mermaid)
        self.assertIn(r"\begin{tikzpicture}", tikz)
        self.assertIn("seq-participant", tikz)
        self.assertIn("New messages can be exchanged", tikz)

    def test_generic_graph_diagrams_are_typed_and_exportable(self) -> None:
        self.assertEqual(len(self.model.graph_diagrams), 5)
        graph = next(
            item
            for item in self.model.graph_diagrams
            if item.id.endswith("figure-21-federate-protocol-layers")
        )
        self.assertEqual(
            GraphDiagramFile.model_validate(
                {"schema_version": 1, "graph_diagrams": [graph.model_dump(mode="json")]}
            ).graph_diagrams[0],
            graph,
        )
        self.assertIn("flowchart", render_graph_mermaid(graph))
        self.assertIn("graph-frame", render_graph_tikz(graph))

    def test_mom_hierarchies_use_the_dedicated_publication_grammar(self) -> None:
        hierarchy = next(
            item
            for item in self.model.graph_diagrams
            if item.id.endswith("figure-20-mom-interaction-hierarchy")
        )
        tikz = render_graph_tikz(hierarchy)
        self.assertIn("graph-hierarchy-box", tikz)
        self.assertIn("graph-hierarchy-note", tikz)
        self.assertIn("RLGraphInterface", tikz)
        self.assertIn(r"\RLMono", tikz)
        self.assertIn("HLAmanager", tikz)

    def test_every_numbered_figure_has_a_surface_owner(self) -> None:
        payload = (ROOT / "data" / "semantic" / "diagram-surfaces.json").read_text(encoding="utf-8")
        manifest = DiagramSurfaceFile.model_validate(json.loads(payload))
        generated = {item.figure_number for item in manifest.surfaces if item.status == "generated"}
        self.assertEqual(generated, set(range(1, 34)))
        self.assertEqual(sum(item.status == "non-generatable" for item in manifest.surfaces), 10)

    def test_state_machine_renderer_has_no_unrenderable_transitions(self) -> None:
        self.assertEqual(validate_renderable(HLA_ROOT / "semantic"), [])

    def test_plantuml_spike_preserves_harel_semantics_for_three_charts(self) -> None:
        machines = {item.id: item for item in self.model.state_machines}
        for machine_id in (
            "global-synchronization-label",
            "normal-activity-permitted",
            "temporal-state",
        ):
            with self.subTest(machine=machine_id):
                source = render_plantuml(machines[machine_id].model_dump(mode="json"))
                self.assertEqual(
                    validate_plantuml_source(machines[machine_id].model_dump(mode="json"), source),
                    [],
                )
                self.assertNotIn("x=", source)
                self.assertNotIn("y=", source)
        joined = render_plantuml(machines["normal-activity-permitted"].model_dump(mode="json"))
        self.assertIn('state "Temporal State"', joined)
        self.assertIn("<<history>>", joined)
        temporal = render_plantuml(machines["temporal-state"].model_dump(mode="json"))
        self.assertIn("Enable Time Regulation", temporal)
        self.assertIn("†", temporal)
        synchronization = render_plantuml(
            machines["global-synchronization-label"].model_dump(mode="json")
        )
        self.assertIn("∀", synchronization)
        overview = render_plantuml(
            machines["federation-execution-sync-overview"].model_dump(mode="json")
        )
        self.assertNotIn("&quot;", overview)

    def test_2025_figure_four_uses_the_joined_federate_state_model(self) -> None:
        profile = json.loads(
            (ROOT / "data" / "semantic" / "source-profiles.json").read_text(encoding="utf-8")
        )
        bindings = next(
            item["diagram_surface_bindings"]
            for item in profile["profiles"]
            if item["id"] == "hla-2025"
        )
        by_figure = {item["figure"]: item["record_id"] for item in bindings}
        self.assertEqual(by_figure[4], "joined-federate-state")
        self.assertEqual(by_figure[5], "normal-activity-permitted")

        machines = {item.id: item for item in self.model.state_machines}
        joined = machines["joined-federate-state"]
        self.assertEqual(len(joined.transitions), 15)
        self.assertEqual(
            {
                "Active Federate",
                "Federate Save in Progress",
                "Federate Restore in Progress",
                "Normal Activity",
            },
            {item.title for item in joined.layout.containers if item.id != "joined.outer"},
        )
        source = render_plantuml(joined.model_dump(mode="json"))
        self.assertEqual(validate_plantuml_source(joined.model_dump(mode="json"), source), [])
        self.assertIn("Request Federation Save", source)
        self.assertIn("Federate Save Begun", source)
        self.assertIn("Federate Restore Complete", source)
        self.assertIn('state "Joined Federate"', source)

    def test_every_state_machine_has_a_valid_plantuml_projection(self) -> None:
        self.assertEqual(validate_plantuml_models(HLA_ROOT / "semantic"), [])

    def test_plantuml_projection_leaves_connector_routing_to_renderer(self) -> None:
        machines = {item.id: item for item in self.model.state_machines}
        for machine_id in ("federate-lifetime", "joined-federate-state", "temporal-state"):
            with self.subTest(machine=machine_id):
                source = render_plantuml(machines[machine_id].model_dump(mode="json"))
                self.assertNotRegex(source, r" -(?:left|right|up|down)-> ")
                self.assertIn(" --> ", source)

    def test_2010_plantuml_promotion_requires_reviewed_layout(self) -> None:
        root = ROOT / "topics" / "ieee" / "hla-1516.1-2010"
        review = json.loads(
            (root / "semantic" / "plantuml-review.json").read_text(encoding="utf-8")
        )
        approved = set(review["approved_machine_ids"])
        deferred = set(review["deferred_machine_ids"])
        landscape = set(review["landscape_machine_ids"])
        self.assertTrue(approved)
        self.assertFalse(deferred)
        self.assertEqual(approved & deferred, set())
        self.assertTrue(landscape <= approved)
        self.assertEqual(
            landscape,
            {
                "hla-1516.1-2010:figure-01",
                "hla-1516.1-2010:figure-03",
                "hla-1516.1-2010:figure-04",
                "hla-1516.1-2010:figure-05",
                "hla-1516.1-2010:figure-06",
                "hla-1516.1-2010:figure-07",
                "hla-1516.1-2010:figure-08",
                "hla-1516.1-2010:figure-09",
                "hla-1516.1-2010:figure-10",
                "hla-1516.1-2010:figure-11",
                "hla-1516.1-2010:figure-12",
                "hla-1516.1-2010:figure-13",
                "hla-1516.1-2010:figure-14",
                "hla-1516.1-2010:figure-15",
                "hla-1516.1-2010:figure-16",
                "hla-1516.1-2010:figure-17",
            },
        )
        self.assertIn("hla-1516.1-2010:figure-04", approved)
        machines = {
            item.id: item for item in load_document_model(root, HLA_SOURCE_2010).state_machines
        }
        canonical_root = ROOT / "topics" / "ieee" / "hla-1516.1-2025"
        canonical = {
            item.id: item.model_dump(mode="json")
            for item in load_document_model(
                canonical_root,
                source_profile_for_document("hla-1516.1-2025"),
            ).state_machines
        }
        projections = review["projection_sources"]
        for machine_id in approved:
            with self.subTest(machine=machine_id):
                payload = machines[machine_id].model_dump(mode="json")
                source_id = projections.get(machine_id)
                if source_id:
                    payload = _cross_edition_plantuml_payload(
                        payload,
                        document_id="hla-1516.1-2010",
                        canonical_payloads={
                            source_id.split(":", 1)[1]: canonical[source_id.split(":", 1)[1]]
                        },
                    )
                self.assertEqual(validate_plantuml_source(payload, render_plantuml(payload)), [])

    def test_2010_reviewed_plantuml_projection_keeps_complete_transition_topology(self) -> None:
        root = ROOT / "topics" / "ieee" / "hla-1516.1-2010"
        review = json.loads(
            (root / "semantic" / "plantuml-review.json").read_text(encoding="utf-8")
        )
        self.assertIn("hla-1516.1-2010:figure-07", review["approved_machine_ids"])
        machines = {item.id: item for item in load_document_model(root, HLA_SOURCE).state_machines}
        figure = machines["hla-1516.1-2010:figure-07"]
        self.assertEqual(len(figure.states), 5)
        self.assertEqual(len(figure.transitions), 5)
        self.assertTrue(all(item.source_state and item.target_state for item in figure.transitions))
        source = render_plantuml(figure.model_dump(mode="json"))
        self.assertIn("[*] -->", source)
        for event in (
            "initial entry to Synch Point Not Registered",
            "registration request",
            "registration failure",
            "registration success",
            "all subordinate members are complete",
        ):
            with self.subTest(event=event):
                self.assertIn(event, source)
        self.assertIn("hla-1516.1-2010:figure-04", review["approved_machine_ids"])

    def test_derivative_contains_sequence_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            derivative = generate_derivative((self.model,), Path(temporary))
            text = derivative.read_text(encoding="utf-8")
        self.assertIn("Message-sequence diagrams", text)
        self.assertIn("hla-1516.1.figure-26-successful-reconnection", text)


if __name__ == "__main__":
    unittest.main()
