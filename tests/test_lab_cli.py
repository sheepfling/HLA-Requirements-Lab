"""Contract tests for the public HLA Requirements Lab boundary."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

from hla_lab.cli import _test_workers, build_parser, main
from hla_lab.paths import document_ids, document_roots


class LabCliTests(unittest.TestCase):
    def test_help_and_schemas_work_without_a_corpus_workspace(self) -> None:
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment["HLA_LAB_ROOT"] = ""
        with tempfile.TemporaryDirectory() as workspace:
            for arguments, expected in (
                (["--help"], "hla-lab"),
                (["schema", "--list"], "requirements"),
            ):
                with self.subTest(arguments=arguments):
                    result = subprocess.run(
                        [sys.executable, "-m", "hla_lab.cli", *arguments],
                        cwd=workspace,
                        env=environment,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn(expected, result.stdout)

    def test_empty_command_prints_workflow_help(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = main([])
        self.assertEqual(result, 0)
        self.assertIn("hla-lab --root . build", output.getvalue())
        self.assertIn("hla-lab --root . quality", output.getvalue())

    def test_common_aliases_parse(self) -> None:
        parser = build_parser()
        self.assertEqual(parser.parse_args(["status"]).command, "status")
        self.assertEqual(parser.parse_args(["docs"]).command, "docs")
        self.assertEqual(parser.parse_args(["build"]).target, "all")
        self.assertTrue(parser.parse_args(["publish", "--clean", "example"]).clean)

    def test_public_document_catalog_matches_the_supported_corpus(self) -> None:
        roots = document_roots()
        self.assertEqual(tuple(path.name for path in roots), document_ids())
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
