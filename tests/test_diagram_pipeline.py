"""M20/M21 diagram semantics, rendering, and source-only QA contracts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.diagram_qa import validate_renderable
from scripts.export_graph_diagram import render_mermaid as render_graph_mermaid
from scripts.export_graph_diagram import render_tikz as render_graph_tikz
from scripts.export_sequence_diagram import render_mermaid, render_tikz
from scripts.generate_derivative import generate_derivative
from scripts.hla_profile import HLA_SOURCE
from scripts.semantic_model import (
    DiagramSurfaceFile,
    GraphDiagramFile,
    SequenceDiagramFile,
    load_document_model,
)

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

    def test_derivative_contains_sequence_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            derivative = generate_derivative((self.model,), Path(temporary))
            text = derivative.read_text(encoding="utf-8")
        self.assertIn("Message-sequence diagrams", text)
        self.assertIn("hla-1516.1.figure-26-successful-reconnection", text)


if __name__ == "__main__":
    unittest.main()
