"""Portability and profile-boundary tests for portability."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hla_lab.build.build import documents
from hla_lab.core.semantic_model import DocumentModel, load_corpus, load_document_model
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.generation.semantic_generation import generate
from tests.support import TEST_REPO_ROOT

REPO_ROOT = TEST_REPO_ROOT
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


class PortabilityContractTests(unittest.TestCase):
    def test_installed_modules_import_without_workspace_root(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("HLA_LAB_ROOT", None)
        script = (
            "import importlib, pkgutil, hla_lab; "
            "modules = [entry.name for entry in "
            "pkgutil.walk_packages(hla_lab.__path__, hla_lab.__name__ + '.')]; "
            "[importlib.import_module(name) for name in modules]; "
            "print(len(modules))"
        )
        with tempfile.TemporaryDirectory() as workspace:
            result = subprocess.run(
                [sys.executable, "-B", "-c", script],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertGreater(int(result.stdout.strip()), 0)

    def test_workspace_commands_show_help_without_configured_root(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("HLA_LAB_ROOT", None)
        modules = (
            "hla_lab.corpus.corpus_inventory",
            "hla_lab.corpus.hla_edition_diff",
            "tools.check_module_layout",
            "tools.utility_inventory",
        )
        with tempfile.TemporaryDirectory() as workspace:
            for module in modules:
                with self.subTest(module=module):
                    result = subprocess.run(
                        [sys.executable, "-B", "-m", module, "--help"],
                        cwd=workspace,
                        env=environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("usage:", result.stdout)

    def test_corpus_commands_accept_explicit_workspace_root(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.pop("HLA_LAB_ROOT", None)
        with tempfile.TemporaryDirectory() as workspace:
            output = Path(workspace) / "inventory.json"
            inventory = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "hla_lab.corpus.corpus_inventory",
                    "--workspace-root",
                    str(REPO_ROOT),
                    "--root",
                    str(REPO_ROOT / "topics/ieee/hla-1516.1-2025"),
                    "--output",
                    str(output),
                    "--write",
                ],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(inventory.returncode, 0, inventory.stderr)
            self.assertIn("hla-1516.1-2025", output.read_text(encoding="utf-8"))
            edition_diff = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "hla_lab.corpus.hla_edition_diff",
                    "--root",
                    str(REPO_ROOT),
                    "--standard",
                    "ieee-1516.1",
                    "--format",
                    "summary",
                ],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(edition_diff.returncode, 0, edition_diff.stderr)
            self.assertIn("hla-1516.1-2010 -> hla-1516.1-2025", edition_diff.stdout)
            model_view = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "hla_lab.semantic_model_cli",
                    str(REPO_ROOT / "topics/ieee/hla-1516.1-2025"),
                    "--workspace-root",
                    str(REPO_ROOT),
                ],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(model_view.returncode, 0, model_view.stderr)
            self.assertIn("requirements: ", model_view.stdout)
            bundle_path = Path(workspace) / "bundle.json"
            export = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "hla_lab.publication.export_compliance_bundle",
                    "--corpus-root",
                    str(REPO_ROOT),
                    "--edition",
                    "2025",
                    "--revision",
                    "package-portability-test",
                    "--output",
                    str(bundle_path),
                ],
                cwd=workspace,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(export.returncode, 0, export.stderr)
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            self.assertEqual(len(bundle["documents"]), 3)

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
        self.assertIn("hla_lab.generation.semantic_generation", build_script)
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import hla_lab.core.semantic_model; "
                    "import hla_lab.generation.semantic_generation; "
                    "import hla_lab.adapters.latex_renderer; "
                    "assert 'hla_lab.core.hla_profile' not in sys.modules"
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
    return tuple(path.resolve() for path in documents())


if __name__ == "__main__":
    unittest.main()
