"""Acceptance tests for the reflowable hierarchy-first renderer."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.generation.reflowable_renderer import render_reflowable_document
from hla_lab.publication.publication_contract import default_publication_profile

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = ROOT / "topics" / "fixture" / "non-hla-demo-2025"

def _fixture_profile() -> object:
    path = FIXTURE_ROOT / "fixture_profile.py"
    spec = importlib.util.spec_from_file_location("m26_fixture_profile", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load fixture profile: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

class ReflowableRendererTests(unittest.TestCase):
    def test_reflowable_view_uses_canonical_clause_order(self) -> None:
        profile = _fixture_profile()
        model = load_document_model(FIXTURE_ROOT, profile.DEMO_SOURCE)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "semantic"
            generate_derivative((model,), output)
            reflowable = (output / "reflowable.tex").read_text(encoding="utf-8")

        self.assertLess(reflowable.find("clause-1"), reflowable.find("clause-1.1"))
        self.assertIn("A reusable unit that accepts an input and produces a result.", reflowable)
        self.assertIn(
            "A widget provider shall validate the input before producing a result.", reflowable
        )
        self.assertIn("validated input", reflowable)
        self.assertNotIn("DemoFixedBlock", reflowable)

    def test_semantic_mutation_reaches_reflowable_view(self) -> None:
        profile = _fixture_profile()
        model = load_document_model(FIXTURE_ROOT, profile.DEMO_SOURCE)
        payload = model.model_dump(mode="json")
        payload["requirements"][0]["statement"] = "reflow reflowable mutation sentinel."
        mutated = type(model).model_validate(payload)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "semantic"
            generate_derivative((mutated,), output)
            reflowable = (output / "reflowable.tex").read_text(encoding="utf-8")

        self.assertIn("reflow reflowable mutation sentinel.", reflowable)

    def test_reflowable_renderer_removes_page_adapter_residue(self) -> None:
        profile = _fixture_profile()
        model = load_document_model(FIXTURE_ROOT, profile.DEMO_SOURCE)
        payload = model.model_dump(mode="json")
        source = {"path": "fixture.tex", "line": 1}
        payload["content_blocks"] = [
            {
                "id": "fixture-block",
                "kind": "context",
                "text": "fixture",
                "clause_id": "clause-1",
                "element_ids": ["fixture-element"],
                "source": source,
            }
        ]
        payload["content_elements"] = [
            {
                "id": "fixture-element",
                "kind": "paragraph",
                "text": (
                    "page 1 hla-body 90.000 69.786 432.000 9.96 12.00 "
                    "reflow clean prose sentinel hlafixedpage"
                ),
                "clause_id": "clause-1",
                "block_id": "fixture-block",
                "source": source,
            }
        ]
        mutated = type(model).model_validate(payload)

        rendered = render_reflowable_document(
            (mutated,),
            default_publication_profile((mutated.document_id,)),
        )

        self.assertIn("reflow clean prose sentinel", rendered)
        self.assertNotIn("90.000", rendered)
        self.assertNotIn("hla-body", rendered)
        self.assertNotIn("hlafixedpage", rendered)

if __name__ == "__main__":
    unittest.main()
