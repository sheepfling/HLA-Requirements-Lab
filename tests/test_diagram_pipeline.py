"""diagram diagram semantics, rendering, and source-only QA contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
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
    validate_source as validate_plantuml_source,
)
from hla_lab.generation.generate_derivative import generate_derivative

ROOT = Path(__file__).resolve().parents[1]
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
                self.assertEqual(validate_plantuml_source(machines[machine_id].model_dump(mode="json"), source), [])
                self.assertNotIn("x=", source)
                self.assertNotIn("y=", source)
        joined = render_plantuml(machines["normal-activity-permitted"].model_dump(mode="json"))
        self.assertIn('state "Temporal State"', joined)
        self.assertIn('<<history>>', joined)
        temporal = render_plantuml(machines["temporal-state"].model_dump(mode="json"))
        self.assertIn("Enable Time Regulation", temporal)
        self.assertIn("†", temporal)
        synchronization = render_plantuml(
            machines["global-synchronization-label"].model_dump(mode="json")
        )
        self.assertIn("∀", synchronization)

    def test_every_state_machine_has_a_valid_plantuml_projection(self) -> None:
        self.assertEqual(validate_plantuml_models(HLA_ROOT / "semantic"), [])

    def test_derivative_contains_sequence_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            derivative = generate_derivative((self.model,), Path(temporary))
            text = derivative.read_text(encoding="utf-8")
        self.assertIn("Message-sequence diagrams", text)
        self.assertIn("hla-1516.1.figure-26-successful-reconnection", text)


if __name__ == "__main__":
    unittest.main()
