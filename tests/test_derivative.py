"""Contract tests for the programmatic semantic derivative document."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.semantic_model import DocumentModel
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.generation.generate_derivative import _requirement_heading, generate_derivative
from hla_lab.publication.publication_registry import load_release_manifest
from tests.support import TEST_REPO_ROOT

REPO_ROOT = TEST_REPO_ROOT
DOCUMENT_ROOTS = tuple(
    REPO_ROOT / "topics" / "ieee" / name
    for name in ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025")
)


class DerivativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.models = load_hla_corpus(DOCUMENT_ROOTS).documents

    def test_derivative_emits_four_semantic_views_and_machine_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            derivative = generate_derivative(self.models, output)
            tex = derivative.read_text(encoding="utf-8")
            payload = json.loads((output / "semantic-model.json").read_text(encoding="utf-8"))

        self.assertIn(r"\section{Concepts and definitions", tex)
        self.assertIn(r"\section{Normative requirements", tex)
        self.assertIn(r"\section{State machines and event logic", tex)
        self.assertIn(r"\section{Traceability", tex)
        self.assertIn("req-connect-service-establishes-connection", tex)
        self.assertIn("federate.connection-lost", tex)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(
            {item["document_id"] for item in payload["documents"]},
            {"hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025"},
        )

    def test_semantic_record_change_updates_derivative_tex_and_json(self) -> None:
        framework = next(item for item in self.models if item.document_id == "hla-1516-2025")
        requirement = next(item for item in framework.requirements if item.id == "summary-rule-1")
        changed_statement = "Federations shall expose a semantically generated FOM."
        changed_requirement = requirement.model_copy(
            update={"statement": changed_statement, "machine_statement": changed_statement}
        )
        changed_framework = DocumentModel.model_validate(
            framework.model_copy(
                update={
                    "requirements": tuple(
                        changed_requirement if item.id == requirement.id else item
                        for item in framework.requirements
                    )
                }
            ).model_dump(mode="json")
        )
        changed_models = tuple(
            changed_framework if item.document_id == framework.document_id else item
            for item in self.models
        )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            generate_derivative(changed_models, output)
            tex = (output / "derivative.tex").read_text(encoding="utf-8")
            payload = json.loads((output / "semantic-model.json").read_text(encoding="utf-8"))

        self.assertIn(changed_statement, tex)
        framework_payload = next(
            item for item in payload["documents"] if item["document_id"] == framework.document_id
        )
        summary_payload = next(
            item for item in framework_payload["requirements"] if item["id"] == requirement.id
        )
        self.assertEqual(summary_payload["statement"], changed_statement)

    def test_cross_page_requirement_renders_continuation_source(self) -> None:
        model = next(item for item in self.models if item.document_id == "hla-1516.1-2025")
        requirement = next(item for item in model.requirements if item.additional_sources)
        with tempfile.TemporaryDirectory() as temporary:
            derivative = generate_derivative((model,), Path(temporary))
            tex = derivative.read_text(encoding="utf-8")
        self.assertIn("Additional source", tex)
        self.assertIn("printed p.", tex)
        self.assertIn(requirement.additional_sources[0].path.replace("_", r"\_"), tex)

    def test_source_derived_requirement_uses_substantive_heading(self) -> None:
        model = next(item for item in self.models if item.document_id == "hla-1516.1-2025")
        requirement = next(
            item
            for item in model.requirements
            if item.id.startswith("requirement-candidate-content-clauses-")
            and "shall" in item.statement
        )
        heading = _requirement_heading(requirement)
        self.assertIn("shall", heading)
        self.assertLessEqual(len(heading), 112)
        self.assertNotIn("content/clauses", heading)
        self.assertEqual(heading, requirement.title)

    def test_derivative_project_is_a_top_level_build_target(self) -> None:
        root = REPO_ROOT / "topics" / "ieee" / "hla-semantic-derivative-2025"
        self.assertIn(r"\input{output/semantic/reflowable}", (root / "main.tex").read_text())
        self.assertIn("from hla_lab.build.topic import main", (root / "build.py").read_text())
        project = load_release_manifest(REPO_ROOT / "data" / "release" / "documents.json").project(
            "hla-semantic-derivative-2025"
        )
        self.assertIsNotNone(project.build)
        self.assertEqual(project.build.strategy, "semantic-derivative")


if __name__ == "__main__":
    unittest.main()
