"""Typed content extraction and data-driven content-extraction contracts."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
from hla_lab.core.semantic_model import ContentElement, load_document_model
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.semantic_generation import generate
from hla_lab.reports.semantic_metrics import measure_document
from hla_lab.traceability.semantic_authority import load_authority

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "topics" / "ieee" / "hla-1516-2025"

class ContentExtractionTests(unittest.TestCase):
    def test_1516_content_is_typed_and_clause_owned(self) -> None:
        model = load_document_model(ROOT, HLA_SOURCE)
        self.assertEqual(len(model.content_blocks), 38)
        self.assertEqual(len(model.content_elements), 336)
        self.assertEqual(
            {item.kind for item in model.content_elements},
            {"paragraph", "list", "list-item", "note", "footnote", "cross-reference"},
        )
        self.assertIn(
            "formula",
            ContentElement.model_json_schema()["properties"]["kind"]["enum"],
        )
        self.assertTrue(all(item.source.path for item in model.content_elements))
        self.assertTrue(all(item.block_id for item in model.content_elements))
        self.assertTrue(
            all(
                element.clause_id is not None or element.block_id.startswith("content-front-matter")
                for element in model.content_elements
            )
        )
        element_ids = {item.id for item in model.content_elements}
        self.assertEqual(len(element_ids), len(model.content_elements))
        self.assertTrue(
            all(set(block.element_ids) <= element_ids for block in model.content_blocks)
        )
        self.assertGreater(sum(item.kind == "list-item" for item in model.content_elements), 0)
        self.assertGreater(sum(item.parent_id is not None for item in model.content_elements), 0)

    def test_content_queries_use_typed_records(self) -> None:
        model = load_document_model(ROOT, HLA_SOURCE)
        clause_elements = model.content_elements_for_clause("clause-1.4")
        self.assertTrue(clause_elements)
        self.assertTrue(all(item.clause_id == "clause-1.4" for item in clause_elements))
        matches = model.search_content("runtime infrastructure")
        self.assertTrue(matches)
        self.assertTrue(any(item.kind == "paragraph" for item in matches))
        self.assertTrue(model.search_content("formal definitions", kinds=("note",)))

    def test_content_element_authority_and_metrics_are_explicit(self) -> None:
        authority = load_authority(REPO_ROOT / "data" / "semantic" / "authority.json")
        document = next(item for item in authority.documents if item.document_id == ROOT.name)
        surface = next(item for item in document.surfaces if item.id == "content-elements")
        self.assertEqual(surface.kind, "content_elements")
        metrics = measure_document(ROOT)
        self.assertEqual(metrics.content_elements, 336)
        self.assertEqual(metrics.content_element_block_coverage, 1.0)

    def test_content_element_source_mutation_changes_generated_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            copy_root = Path(temporary) / ROOT.name
            shutil.copytree(ROOT, copy_root)
            source_path = copy_root / "semantic" / "content-elements.json"
            payload = json.loads(source_path.read_text(encoding="utf-8"))
            target = payload["content_elements"][0]
            target["text"] = "content-extraction mutation sentinel"
            source_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
            model = load_document_model(copy_root, HLA_SOURCE)
            output = Path(temporary) / "output"
            generate(
                GenerationRequest(
                    root=copy_root,
                    output=output,
                    source=HLA_SOURCE,
                    dialect=HLA_LATEX_DIALECT,
                    content_element_ids=(model.content_elements[0].id,),
                )
            )
            generated = next(output.glob("content-element-*-data.tex"))
            self.assertIn(
                "content-extraction mutation sentinel", generated.read_text(encoding="utf-8")
            )

if __name__ == "__main__":
    unittest.main()
