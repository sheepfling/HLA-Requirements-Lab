"""Portability and profile-boundary tests for Milestone 13."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.generate_derivative import generate_derivative
from scripts.semantic_generation import generate
from scripts.semantic_model import DocumentModel, load_corpus, load_document_model

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "topics" / "fixture" / "non-hla-demo-2025"


def _load_fixture_profile() -> object:
    path = FIXTURE_ROOT / "fixture_profile.py"
    spec = importlib.util.spec_from_file_location("m13_fixture_profile", path)
    if spec is None or spec.loader is None:  # pragma: no cover - fixture contract failure
        raise AssertionError(f"unable to load fixture profile: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


PROFILE = _load_fixture_profile()


class Milestone13Tests(unittest.TestCase):
    def test_non_hla_fixture_loads_and_supports_generic_queries(self) -> None:
        model = load_document_model(FIXTURE_ROOT, PROFILE.DEMO_SOURCE)

        self.assertEqual(model.document_id, "non-hla-demo-2025")
        self.assertEqual(
            tuple(item.id for item in model.children_of("clause-1")),
            ("clause-1.1",),
        )
        self.assertEqual(model.search_definitions("widget")[0].id, "definition-widget")
        self.assertEqual(
            model.match_requirements("validate widget input")[0].requirement.id,
            "requirement-widget-ready",
        )
        self.assertEqual(model.search_tables("mapping")[0].domain, "generic")
        self.assertEqual(model.search_tables("mapping")[0].cells[2].text, "validated input")
        self.assertEqual(
            model.references_for_clause("clause-1.1")[0].id,
            "reference-demo",
        )
        self.assertEqual(
            load_corpus((FIXTURE_ROOT,), PROFILE.DEMO_SOURCE).unresolved_reference_issues(), ()
        )
        self.assertEqual(DocumentModel.from_json(model.to_json()), model)

    def test_common_generation_consumes_non_hla_records(self) -> None:
        model = load_document_model(FIXTURE_ROOT, PROFILE.DEMO_SOURCE)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "faithful"
            generate(
                FIXTURE_ROOT,
                output,
                source=PROFILE.DEMO_SOURCE,
                dialect=PROFILE.DEMO_LATEX_DIALECT,
                definition_ids=("definition-widget",),
                requirement_ids=("requirement-widget-ready",),
                table_family_ids=("demo-table-family",),
                include_outline=True,
            )
            derivative_output = Path(temporary) / "derivative"
            derivative = generate_derivative((model,), derivative_output)
            generated_text = "\n".join(
                path.read_text(encoding="utf-8") for path in output.glob("*.tex")
            )
            derivative_text = derivative.read_text(encoding="utf-8")
            payload = json.loads((derivative_output / "semantic-model.json").read_text())

        self.assertIn("definition-widget", generated_text)
        self.assertIn("requirement-widget-ready", generated_text)
        self.assertIn(r"\SemanticTableDemoTOneCaption", generated_text)
        self.assertIn("Widget mapping", derivative_text)
        self.assertIn("validated input", derivative_text)
        self.assertEqual(payload["documents"][0]["document_id"], "non-hla-demo-2025")
        self.assertNotIn("HLA", generated_text)
        self.assertNotIn("HLA", derivative_text)

    def test_fixture_is_discovered_by_common_build_and_has_no_hla_import(self) -> None:
        build_script = (FIXTURE_ROOT / "build.py").read_text(encoding="utf-8")
        self.assertIn("BuildConfig", build_script)
        self.assertIn("scripts.semantic_generation", build_script)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import scripts.semantic_model; "
                    "import scripts.semantic_generation; import scripts.latex_renderer; "
                    "assert 'scripts.hla_profile' not in sys.modules"
                ),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout, "")
        self.assertIn(FIXTURE_ROOT.resolve(), _document_roots())


def _document_roots() -> tuple[Path, ...]:
    from scripts.build import documents

    return tuple(path.resolve() for path in documents())


if __name__ == "__main__":
    unittest.main()
