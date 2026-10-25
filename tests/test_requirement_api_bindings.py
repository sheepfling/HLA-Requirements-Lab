"""Tests for requirement-to-language-API traceability."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from collections import Counter
from pathlib import PurePosixPath

from hla_lab.core.semantic_model import RequirementApiBindingFile
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.publication.export_compliance_bundle import _document
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
DOCUMENT_ROOT = ROOT / "topics" / "ieee" / "hla-1516.1-2025"


class RequirementApiBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.model = load_hla_document_model(DOCUMENT_ROOT)

    def test_manifest_is_complete_and_deterministic(self) -> None:
        path = DOCUMENT_ROOT / "semantic" / "api-requirement-bindings.json"
        restored = RequirementApiBindingFile.model_validate_json(path.read_text(encoding="utf-8"))
        self.assertEqual(restored.bindings, self.model.requirement_api_bindings)
        self.assertEqual(
            {item.requirement_id for item in restored.bindings},
            {item.id for item in self.model.requirements},
        )
        self.assertEqual(
            Counter(item.status for item in restored.bindings),
            Counter(
                reviewed=1851,
                matched=53,
            ),
        )
        self.assertEqual(build_requirement_api_bindings(self.model), restored.bindings)

    def test_matched_bindings_resolve_to_java_or_cpp_declarations(self) -> None:
        surfaces = {item.id: item for item in self.model.api_surfaces}
        matched = tuple(
            item for item in self.model.requirement_api_bindings if item.status == "matched"
        )
        self.assertEqual(len(matched), 53)
        for binding in matched:
            self.assertIsNotNone(binding.api_surface_id)
            surface = surfaces[binding.api_surface_id]
            self.assertIn(binding.language, {"cpp", "java"})
            self.assertEqual(surface.language, binding.language)
            self.assertIsNotNone(surface.source)
            self.assertTrue(surface.source.path.endswith((".h", ".java")))

    def test_requirement_query_exposes_both_language_declarations(self) -> None:
        rows = self.model.api_bindings_for_requirement("req-federate-connection-lost")
        self.assertEqual({item.language for item in rows}, {"cpp", "java"})
        self.assertTrue(all(item.status == "matched" for item in rows))

    def test_portable_bundle_preserves_binding_and_declaration_sources(self) -> None:
        document = _document(self.model)
        self.assertEqual(len(document.requirement_api_bindings), 1904)
        self.assertEqual(
            [item.ordinal for item in document.requirements],
            list(range(1, len(document.requirements) + 1)),
        )
        first = document.requirements[0]
        source = next(item for item in self.model.requirements if item.id == first.id).source
        self.assertEqual(first.source.path, source.path)
        source_requirement = next(item for item in self.model.requirements if item.id == first.id)
        self.assertEqual(first.kind, source_requirement.kind)
        self.assertEqual(first.transition_ids, source_requirement.transition_ids)
        self.assertEqual(
            {item.requirement_id for item in document.requirement_api_bindings},
            {item.id for item in self.model.requirements},
        )
        binding = next(
            item
            for item in document.requirement_api_bindings
            if item.requirement_id == "req-federate-connection-lost" and item.language == "cpp"
        )
        surface = next(item for item in document.api_surfaces if item.id == binding.api_surface_id)
        self.assertIsNotNone(surface.source)
        self.assertEqual(
            PurePosixPath(surface.source.path).parts[-2:],
            ("RTI", "FederateAmbassador.h"),
        )

    def test_both_hla_1516_1_editions_have_complete_binding_manifests(self) -> None:
        for document_name in ("hla-1516.1-2010", "hla-1516.1-2025"):
            root = ROOT / "topics" / "ieee" / document_name
            model = load_hla_document_model(root)
            path = root / "semantic" / "api-requirement-bindings.json"
            restored = RequirementApiBindingFile.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            self.assertEqual(
                {item.requirement_id for item in restored.bindings},
                {item.id for item in model.requirements},
            )
            self.assertEqual(build_requirement_api_bindings(model), restored.bindings)
            matched = tuple(item for item in restored.bindings if item.status == "matched")
            self.assertTrue(matched)
            self.assertEqual({item.language for item in matched}, {"cpp", "java"})

    def test_cli_requirement_query_includes_declaration_sources(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "hla_lab.traceability.compliance",
                str(DOCUMENT_ROOT),
                "--document",
                "hla-1516.1-2025",
                "--api-binding-requirement-id",
                "req-federate-connection-lost",
                "--json",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        bindings = payload["requirement_api_bindings"]
        surfaces = {item["id"]: item for item in payload["requirement_api_surfaces"]}
        self.assertEqual({item["language"] for item in bindings}, {"cpp", "java"})
        self.assertTrue(
            all(
                surfaces[item["api_surface_id"]]["source"]["path"].endswith((".h", ".java"))
                for item in bindings
            )
        )

    def test_transition_backed_rows_preserve_the_transition_hop(self) -> None:
        edition_model = load_hla_document_model(ROOT / "topics" / "ieee" / "hla-1516.1-2010")
        rows = edition_model.api_bindings_for_requirement("req-19b425a9de77")
        self.assertEqual({item.language for item in rows}, {"cpp", "java"})
        self.assertTrue(all(item.status == "matched" for item in rows))
        self.assertTrue(all(item.relationship == "transition-backed" for item in rows))
        self.assertEqual(
            {item.api_surface_id for item in rows},
            {
                surface.id
                for surface in edition_model.api_surfaces
                if surface.name == "unsubscribeObjectClassAttributes"
                and surface.language in {"cpp", "java"}
            },
        )

    def test_reviewed_protocol_requirement_is_explicitly_cross_cutting(self) -> None:
        rows = self.model.api_bindings_for_requirement(
            "requirement-candidate-content-clauses-12-programming-language-mappings-page-399-l41-13"
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].language, "unspecified")
        self.assertEqual(rows[0].relationship, "cross-cutting")
        self.assertEqual(rows[0].status, "reviewed")
        self.assertIsNone(rows[0].api_surface_id)

    def test_all_overloads_resolution_is_explicit_and_complete(self) -> None:
        edition_model = load_hla_document_model(ROOT / "topics" / "ieee" / "hla-1516.1-2010")
        rows = edition_model.api_bindings_for_requirement("req-2f698415a1b7")
        expected = {
            surface.id
            for surface in edition_model.api_surfaces
            if surface.name == "receiveInteraction" and surface.language in {"cpp", "java"}
        }
        self.assertEqual(len(rows), len(expected))
        self.assertEqual({item.api_surface_id for item in rows}, expected)
        self.assertTrue(all(item.status == "matched" for item in rows))
        self.assertTrue(all(item.relationship == "callback" for item in rows))


if __name__ == "__main__":
    unittest.main()
