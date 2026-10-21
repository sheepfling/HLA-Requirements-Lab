"""Contract tests for the public HLA Requirements Lab boundary."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hla_lab.cli import _test_workers, build_parser, main
from hla_lab.paths import DOCUMENT_IDS, document_roots


class LabCliTests(unittest.TestCase):
    def test_empty_command_prints_workflow_help(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main([])
        self.assertEqual(result, 0)
        self.assertIn("hla-lab build", output.getvalue())
        self.assertIn("hla-lab quality", output.getvalue())

    def test_common_aliases_parse(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["status"]).command, "status")
        self.assertEqual(parser.parse_args(["docs"]).command, "docs")
        self.assertEqual(parser.parse_args(["build"]).target, "all")
        self.assertEqual(parser.parse_args(["generate"]).target, "all")
        self.assertEqual(
            parser.parse_args(["map", "hla-1516.1-2025"]).documents,
            ["hla-1516.1-2025"],
        )
        self.assertEqual(parser.parse_args(["matrix"]).edition, "2025")
        self.assertTrue(parser.parse_args(["publish", "--clean", "example"]).clean)

    def test_map_command_explains_canonical_files_and_mapping_status(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["map", "hla-1516.1-2025"])
        self.assertEqual(result, 0)
        rendered = output.getvalue()
        self.assertIn("Semantic mapping overview", rendered)
        self.assertIn("requirement-to-transition links: 32", rendered)
        self.assertIn("planned=281", rendered)
        self.assertIn("semantic/requirement-links.json", rendered)
        self.assertIn("not verified implementation evidence", rendered)

    def test_map_defaults_to_all_documents_and_marks_absent_mapping_sources(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["map"])
        rendered = output.getvalue()
        self.assertEqual(result, 0)
        self.assertIn("hla-1516-2010 (topics/ieee/hla-1516-2010)", rendered)
        self.assertIn("hla-1516.2-2025 (topics/ieee/hla-1516.2-2025)", rendered)
        self.assertIn("API crosswalks: not present", rendered)
        self.assertIn("requirement API bindings: not present", rendered)
        self.assertIn("requirement-to-transition links: not present", rendered)

    def test_map_json_marks_missing_optional_source_files(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["map", "hla-1516-2025", "--json"])
        payload = json.loads(output.getvalue())
        document = payload["documents"][0]
        self.assertEqual(result, 0)
        self.assertIsNone(document["requirement_links"])
        self.assertIsNone(document["implementations"])
        self.assertIsNone(document["api_surfaces"])
        self.assertIn("semantic/api-surfaces.json", document["semantic_files_missing"])
        self.assertIn("semantic/requirements.json", document["semantic_files_present"])

    def test_map_json_reports_independent_mapping_relationships(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["map", "hla-1516.1-2025", "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(payload["documents"][0]["document"], "hla-1516.1-2025")
        self.assertEqual(payload["documents"][0]["requirement_links"], 32)
        self.assertIn("semantic/api-crosswalk.json", payload["semantic_files"])
        self.assertIn("partial are mapping plans", payload["status_notes"]["implementation"])

    def test_map_reports_missing_source_root_with_an_actionable_error(self) -> None:
        output = io.StringIO()
        with (
            patch("hla_lab.cli.document_roots", side_effect=FileNotFoundError("source is absent")),
            redirect_stderr(output),
        ):
            result = main(["map", "hla-1516.1-2025"])
        self.assertEqual(result, 2)
        self.assertIn("Cannot read semantic mapping: source is absent", output.getvalue())

    def test_map_names_missing_canonical_input_file(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = Path(temporary)
            root = repository / "topics" / "ieee" / "fixture"
            root.mkdir(parents=True)
            output = io.StringIO()
            with (
                patch("hla_lab.cli.REPO_ROOT", repository),
                patch("hla_lab.cli.document_roots", return_value=(root,)),
                redirect_stderr(output),
            ):
                result = main(["map"])
        self.assertEqual(result, 2)
        self.assertIn("missing canonical mapping file", output.getvalue())
        self.assertIn("semantic/requirements.json", output.getvalue())

    def test_map_rejects_unknown_document_ids(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors):
            result = main(["map", "not-a-document"])
        self.assertEqual(result, 2)
        self.assertIn("unknown HLA document", errors.getvalue())

    def test_generate_routes_to_document_build_and_propagates_its_exit_code(self) -> None:
        with patch("hla_lab.cli._delegate", return_value=0) as delegate:
            result = main(["generate", "topics/ieee/hla-1516.1-2025"])
        self.assertEqual(result, 0)
        delegate.assert_called_once_with(
            "hla_lab.build.build", ("build", "topics/ieee/hla-1516.1-2025")
        )

    def test_generate_propagates_build_failure_with_prerequisite_guidance(self) -> None:
        errors = io.StringIO()
        with patch("hla_lab.cli._delegate", return_value=17), redirect_stderr(errors):
            result = main(["generate", "topics/ieee/hla-1516.1-2025"])
        self.assertEqual(result, 17)
        self.assertIn("PDF generation failed", errors.getvalue())
        self.assertIn("required fonts", errors.getvalue())

    def test_generate_rejects_missing_targets_with_discovery_guidance(self) -> None:
        errors = io.StringIO()
        with redirect_stderr(errors):
            result = main(["generate", "topics/ieee/not-a-document"])
        self.assertEqual(result, 2)
        self.assertIn("Cannot generate document PDFs", errors.getvalue())
        self.assertIn("hla-lab docs", errors.getvalue())

    def test_matrix_routes_both_editions_to_topic_generator_and_lists_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release_projects = []
            calls = []
            for edition in ("2010", "2025"):
                project = root / "topics" / "ieee" / f"hla-rti-compliance-{edition}"
                output = project / "output" / "compliance"
                csv_output = output / "csv"
                csv_output.mkdir(parents=True)
                for relative in (
                    "compliance-manifest.json",
                    "compliance-requirements.tex",
                    "csv/requirements.csv",
                    "csv/transitions.csv",
                    "csv/implementation-mappings.csv",
                    "csv/requirement-mapping-links.csv",
                    "csv/transition-mapping-links.csv",
                ):
                    (output / relative).write_text("generated", encoding="utf-8")
                release_projects.append(
                    {
                        "id": f"hla-rti-compliance-requirements-{edition}",
                        "publication_id": f"hla-rti-compliance-requirements-{edition}",
                        "root": project.relative_to(root).as_posix(),
                        "pdf": "dist/matrix.pdf",
                        "log": "build/main.log",
                        "kind": "requirements-publication",
                        "build": {"strategy": "compliance"},
                    }
                )

            release_manifest = root / "data" / "release" / "documents.json"
            release_manifest.parent.mkdir(parents=True)
            release_manifest.write_text(
                json.dumps({"schema_version": 1, "projects": release_projects}),
                encoding="utf-8",
            )

            for edition in ("2010", "2025"):
                output_text = io.StringIO()
                with (
                    patch("hla_lab.cli.REPO_ROOT", root),
                    patch(
                        "hla_lab.cli.subprocess.run",
                        side_effect=lambda args, **kwargs: (
                            calls.append((args, kwargs)) or SimpleNamespace(returncode=0)
                        ),
                    ),
                    redirect_stdout(output_text),
                ):
                    result = main(["matrix", "--edition", edition])
                self.assertEqual(result, 0)
                self.assertIn("output/compliance/csv/requirements.csv", output_text.getvalue())
                self.assertIn("does not run XeLaTeX", output_text.getvalue())

            self.assertEqual(len(calls), 2)
            for args, kwargs in calls:
                self.assertEqual(tuple(args[2:5]), ("hla_lab.build.topic", "generate", "--root"))
                self.assertNotIn("latexmk", args)
                self.assertIn("--repository-root", args)
                self.assertEqual(args[args.index("--repository-root") + 1], str(root))
                self.assertEqual(kwargs["cwd"], root)

    def test_matrix_reports_missing_project_and_missing_outputs_actionably(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            errors = io.StringIO()
            release_manifest = root / "data" / "release" / "documents.json"
            release_manifest.parent.mkdir(parents=True)
            release_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "projects": [
                            {
                                "id": "hla-rti-compliance-requirements-2025",
                                "publication_id": "hla-rti-compliance-requirements-2025",
                                "root": "topics/ieee/hla-rti-compliance-2025",
                                "pdf": "dist/matrix.pdf",
                                "log": "build/main.log",
                                "kind": "requirements-publication",
                                "build": {"strategy": "compliance"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            with patch("hla_lab.cli.REPO_ROOT", root), redirect_stderr(errors):
                result = main(["matrix"])
            self.assertEqual(result, 2)
            self.assertIn("source project is missing", errors.getvalue())
            self.assertIn("Check out the HLA corpus files", errors.getvalue())

            project = root / "topics" / "ieee" / "hla-rti-compliance-2025"
            project.mkdir(parents=True)
            errors = io.StringIO()
            with (
                patch("hla_lab.cli.REPO_ROOT", root),
                patch("hla_lab.cli.subprocess.run", return_value=SimpleNamespace(returncode=0)),
                redirect_stderr(errors),
            ):
                result = main(["matrix"])
            self.assertEqual(result, 1)
            self.assertIn("without its expected outputs", errors.getvalue())
            self.assertIn("data/release/documents.json", errors.getvalue())

    def test_matrix_propagates_generator_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "topics" / "ieee" / "hla-rti-compliance-2025"
            project.mkdir(parents=True)
            release_manifest = root / "data" / "release" / "documents.json"
            release_manifest.parent.mkdir(parents=True)
            release_manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "projects": [
                            {
                                "id": "hla-rti-compliance-requirements-2025",
                                "publication_id": "hla-rti-compliance-requirements-2025",
                                "root": "topics/ieee/hla-rti-compliance-2025",
                                "pdf": "dist/matrix.pdf",
                                "log": "build/main.log",
                                "kind": "requirements-publication",
                                "build": {"strategy": "compliance"},
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            errors = io.StringIO()
            with (
                patch("hla_lab.cli.REPO_ROOT", root),
                patch("hla_lab.cli.subprocess.run", return_value=SimpleNamespace(returncode=23)),
                redirect_stderr(errors),
            ):
                result = main(["matrix"])
        self.assertEqual(result, 23)
        self.assertIn("check the compliance profile", errors.getvalue())

    def test_matrix_rejects_unsupported_edition(self) -> None:
        with self.assertRaises(SystemExit):
            main(["matrix", "--edition", "2040"])

    def test_public_document_catalog_matches_the_supported_corpus(self) -> None:
        roots = document_roots()
        self.assertEqual(tuple(path.name for path in roots), DOCUMENT_IDS)
        self.assertTrue(all(path.is_dir() for path in roots))

    def test_documents_command_is_stable_and_machine_readable_enough_for_shells(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(["documents", "--document", "hla-1516.1-2025"])
        self.assertEqual(result, 0)
        self.assertIn("hla-1516.1-2025\tavailable\t", output.getvalue())

    def test_unknown_document_is_rejected_by_the_path_boundary(self) -> None:
        with self.assertRaises(ValueError):
            document_roots(document_ids=("not-an-hla-document",))

    def test_parallel_test_flag_and_pytest_arguments_are_forwardable(self) -> None:
        args, forwarded = build_parser().parse_known_args(["test", "--parallel", "-q"])
        self.assertTrue(args.parallel)
        self.assertEqual(forwarded, ["-q"])

    def test_parallel_tests_have_a_bounded_default_worker_count(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_test_workers(), "4")
        with patch.dict(os.environ, {"HLA_LAB_TEST_WORKERS": "2"}):
            self.assertEqual(_test_workers(), "2")


if __name__ == "__main__":
    unittest.main()
