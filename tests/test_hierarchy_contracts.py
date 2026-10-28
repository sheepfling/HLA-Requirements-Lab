"""Acceptance tests for the hierarchy-driven document compiler."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import DocumentModel, load_document_model
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.generation.hierarchy_compiler import compile_hierarchy
from hla_lab.generation.semantic_generation import generate
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
FIXTURE_ROOT = ROOT / "topics" / "fixture" / "non-hla-demo-2025"
HLA_15161_ROOT = ROOT / "topics" / "ieee" / "hla-1516.1-2025"


def _fixture_profile() -> object:
    path = FIXTURE_ROOT / "fixture_profile.py"
    spec = importlib.util.spec_from_file_location("m18_fixture_profile", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load fixture profile: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROFILE = _fixture_profile()


class HierarchyContractTests(unittest.TestCase):
    def test_compiler_round_trips_a_complete_non_hla_hierarchy(self) -> None:
        model = load_document_model(FIXTURE_ROOT, PROFILE.DEMO_SOURCE)
        compiled = compile_hierarchy(model)

        self.assertEqual(compiled.root_ids, ("clause-1",))
        self.assertEqual(compiled.node("clause-1").child_ids, ("clause-1.1",))
        self.assertEqual(
            compiled.node("clause-1.1").record_ids,
            ("definition-widget", "demo-table-family", "reference-demo"),
        )
        self.assertEqual(len({item.key for item in compiled.records}), len(compiled.records))
        self.assertEqual(
            DocumentModel.model_validate(model.model_dump(mode="json")),
            model,
        )
        self.assertEqual(
            type(compiled).model_validate_json(compiled.to_json()),
            compiled,
        )

    def test_graph_namespaces_overlapping_state_and_transition_ids(self) -> None:
        model = load_document_model(HLA_15161_ROOT, HLA_SOURCE)
        compiled = compile_hierarchy(model)
        state_key = next(
            item.key
            for item in compiled.records
            if item.id == "federate-startup.heartbeat" and item.kind == "state"
        )
        transition_key = next(
            item.key
            for item in compiled.records
            if item.id == "federate-startup.heartbeat" and item.kind == "transition"
        )
        self.assertEqual(state_key, "state:federate-startup.heartbeat")
        self.assertEqual(transition_key, "transition:federate-startup.heartbeat")
        self.assertNotEqual(state_key, transition_key)
        self.assertIn(
            state_key,
            {item.key for item in compiled.anchors},
        )
        self.assertIn(
            transition_key,
            {item.key for item in compiled.anchors},
        )
        self.assertTrue(any(item.source_key.startswith("transition:") for item in compiled.links))

    def test_hierarchy_mutation_changes_compiled_order_and_navigation(self) -> None:
        model = load_document_model(FIXTURE_ROOT, PROFILE.DEMO_SOURCE)
        payload = model.model_dump(mode="json")
        payload["clause_order"] = ["clause-1.1", "clause-1"]
        payload["clauses"][0]["parent_id"] = "clause-1.1"
        payload["clauses"][1]["parent_id"] = None
        mutated = DocumentModel.model_validate(payload)

        original = compile_hierarchy(model)
        changed = compile_hierarchy(mutated)
        self.assertNotEqual(original.root_ids, changed.root_ids)
        self.assertNotEqual(original.to_json(), changed.to_json())
        self.assertEqual(changed.root_ids, ("clause-1.1",))
        self.assertEqual(changed.node("clause-1.1").child_ids, ("clause-1",))

    def test_build_generation_emits_hierarchy_contract_and_bindings(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "semantic"
            model = generate(
                GenerationRequest(
                    root=FIXTURE_ROOT,
                    output=output,
                    source=PROFILE.DEMO_SOURCE,
                    dialect=PROFILE.DEMO_LATEX_DIALECT,
                    definition_ids=("definition-widget",),
                    requirement_ids=("requirement-widget-ready",),
                    table_family_ids=("demo-table-family",),
                    include_outline=True,
                )
            ).model
            hierarchy = json.loads((output / "hierarchy.json").read_text(encoding="utf-8"))
            manifest = (output / "semantic-manifest.tex").read_text(encoding="utf-8")
            hierarchy_tex = (output / "hierarchy-index.tex").read_text(encoding="utf-8")
            outline = (output / "clause-outline.tex").read_text(encoding="utf-8")

        self.assertEqual(hierarchy["document_id"], model.document_id)
        self.assertEqual(hierarchy["root_ids"], ["clause-1"])
        self.assertIn(r"\input{output/semantic/hierarchy-index}", manifest)
        self.assertIn(r"\SemanticHierarchyAnchor", hierarchy_tex)
        self.assertIn(r"\pdfbookmark", outline)
        self.assertLess(outline.find("clause-1"), outline.find("clause-1.1"))

    def test_derivative_serializes_the_same_compiled_hierarchy(self) -> None:
        model = load_document_model(FIXTURE_ROOT, PROFILE.DEMO_SOURCE)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generate_derivative((model,), output)
            payload = json.loads((output / "hierarchy.json").read_text(encoding="utf-8"))
            derivative = (output / "derivative.tex").read_text(encoding="utf-8")

        compiled = compile_hierarchy(model).model_dump(mode="json")
        self.assertEqual(payload["documents"][0], compiled)
        self.assertIn("definition-widget", derivative)


if __name__ == "__main__":
    unittest.main()
