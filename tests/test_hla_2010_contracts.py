from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE, HLA_SOURCE_2010
from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.semantic_generation import generate

ROOT = Path(__file__).resolve().parents[1]
ROOTS = (
    ROOT / "topics" / "ieee" / "hla-1516-2010",
    ROOT / "topics" / "ieee" / "hla-1516.1-2010",
    ROOT / "topics" / "ieee" / "hla-1516.2-2010",
)


class Hla2010ContractTests(unittest.TestCase):
    def test_15161_note_ids_are_unique_across_source_views(self) -> None:
        model = load_document_model(ROOTS[1], HLA_SOURCE_2010)
        note_ids = [item.id for item in model.notes]
        self.assertEqual(len(note_ids), len(set(note_ids)))

    def test_all_2010_candidates_and_transitions_have_dispositions(self) -> None:
        for root in ROOTS:
            profile = HLA_SOURCE_2010 if root.name == "hla-1516.1-2010" else HLA_SOURCE
            model = load_document_model(root, profile)
            self.assertEqual(model.requirement_review_counts()["unreviewed"], 0)
            self.assertEqual(model.transition_coverage_counts()["unclassified"], 0)

    def test_15161_diagram_surfaces_are_semantically_embedded(self) -> None:
        root = ROOTS[1]
        model = load_document_model(root, HLA_SOURCE_2010)
        self.assertEqual(len(model.state_machines), 16)
        self.assertEqual(len(model.graph_diagrams), 4)
        self.assertEqual(
            {surface.figure_number for surface in model.diagram_surfaces},
            set(range(1, 21)),
        )
        self.assertTrue(all(surface.status == "generated" for surface in model.diagram_surfaces))

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generate(
                GenerationRequest(
                    root=root,
                    output=output,
                    source=HLA_SOURCE_2010,
                    dialect=HLA_LATEX_DIALECT,
                    content_block_ids=tuple(item.id for item in model.content_blocks),
                    include_faithful_body=True,
                )
            )
            body = "\n".join(
                path.read_text(encoding="utf-8") for path in output.glob("content-block-*.tex")
            )
        self.assertNotIn("figures/native/figure-", body)
        self.assertEqual(body.count("output/semantic/state-machine-"), 16)
        self.assertEqual(body.count("output/semantic/graph-diagram-"), 4)


if __name__ == "__main__":
    unittest.main()
