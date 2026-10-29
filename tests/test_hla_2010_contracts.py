from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE, HLA_SOURCE_2010
from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.semantic_generation import generate
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
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

    def test_15161_plantuml_review_manifest_is_explicit(self) -> None:
        root = ROOTS[1]
        payload = json.loads(
            (root / "semantic" / "plantuml-review.json").read_text(encoding="utf-8")
        )
        model = load_document_model(root, HLA_SOURCE_2010)
        machine_ids = {item.id for item in model.state_machines}
        approved = set(payload["approved_machine_ids"])
        deferred = set(payload["deferred_machine_ids"])
        self.assertTrue(approved)
        self.assertFalse(deferred)
        self.assertTrue(approved <= machine_ids)
        self.assertTrue(deferred <= machine_ids)
        self.assertTrue(approved.isdisjoint(deferred))
        self.assertEqual(
            set(payload["projection_sources"]),
            {
                "hla-1516.1-2010:figure-05",
                "hla-1516.1-2010:figure-06",
                "hla-1516.1-2010:figure-09",
                "hla-1516.1-2010:figure-12",
                "hla-1516.1-2010:figure-13",
                "hla-1516.1-2010:figure-14",
                "hla-1516.1-2010:figure-15",
                "hla-1516.1-2010:figure-16",
                "hla-1516.1-2010:figure-17",
            },
        )

    def test_15161_plantuml_statecharts_use_standalone_landscape_pages(self) -> None:
        root = ROOTS[1]
        model = load_document_model(root, HLA_SOURCE_2010)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generate(
                GenerationRequest(
                    root=root,
                    output=output,
                    source=HLA_SOURCE_2010,
                    dialect=HLA_LATEX_DIALECT,
                    content_block_ids=tuple(item.id for item in model.content_blocks),
                    state_machine_renderer="plantuml",
                    service_page_renderer="flow",
                    canonical_source=HLA_SOURCE,
                )
            )
            generated_body = "\n".join(
                path.read_text(encoding="utf-8") for path in output.glob("content-block-*.tex")
            )
        for figure_number in (1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17):
            with self.subTest(figure_number=figure_number):
                self.assertIn(
                    rf"\stdsemanticlandscapefigure{{{figure_number}}}",
                    generated_body,
                )
        self.assertNotIn(
            "\\begin{center}",
            generated_body.split("\\stdsemanticlandscapefigure{8}", 1)[1].split(
                "\\stdsemanticlandscapefigure{9}", 1
            )[0],
        )
        self.assertNotIn(
            "\\begin{center}",
            generated_body.split("\\stdsemanticlandscapefigure{9}", 1)[1].split(
                "\\subsubsection{FOM Document Data", 1
            )[0],
        )

    def test_15162_2010_has_no_statechart_migration_scope(self) -> None:
        model = load_document_model(ROOTS[2], HLA_SOURCE)
        self.assertEqual(model.state_machines, ())

    def test_15161_2010_flow_surface_removes_source_page_breaks(self) -> None:
        root = ROOTS[1]
        model = load_document_model(root, HLA_SOURCE_2010)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generate(
                GenerationRequest(
                    root=root,
                    output=output,
                    source=HLA_SOURCE_2010,
                    dialect=HLA_LATEX_DIALECT,
                    content_block_ids=tuple(item.id for item in model.content_blocks),
                    service_page_renderer="flow",
                )
            )
            body = "\n".join(
                path.read_text(encoding="utf-8")
                for path in output.glob("content-block-content-clauses-*.tex")
                if any(f"clauses-{index:02d}-" in path.name for index in range(4, 11))
            )
        self.assertIn(r"\subsection{Connect service}", body)
        self.assertIn(r"\HLAServiceDirectionLine{FEDERATE $\rightarrow$ RTI}", body)
        self.assertIn(r"\HLAServiceDirectionLine{RTI $\rightarrow$ FEDERATE}", body)
        self.assertNotIn(r"\clearpage", body)
        self.assertNotIn(r"\vspace*{1.12in}", body)
        self.assertNotIn("Comment note", body)
        self.assertNotIn("Directed interation", body)


if __name__ == "__main__":
    unittest.main()
