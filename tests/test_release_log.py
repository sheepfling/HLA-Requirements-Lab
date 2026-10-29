"""Unit tests for release-log diagnostics."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hla_lab.publication.release_check import _log_errors


class ReleaseLogTests(unittest.TestCase):
    def test_release_log_check_reports_fatal_latex_lines(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.log"
            path.write_text(
                "Package Warning: okay\n! Undefined control sequence.\n", encoding="utf-8"
            )
            errors = _log_errors(path)
        self.assertEqual(len(errors), 1)
        self.assertIn("Undefined control sequence", errors[0])

    def test_release_log_check_ignores_wrapped_math_glyphs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.log"
            path.write_text(
                "Underfull \\hbox in paragraph\n!$ []\\TU/lmr/m/n/10 label[]\n",
                encoding="utf-8",
            )
            self.assertEqual(_log_errors(path), [])

    def test_release_log_check_reports_layout_diagnostics_for_faithful_products(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "main.log"
            path.write_text(
                "Overfull \\hbox (2.0pt too wide) in paragraph at lines 1--2\n",
                encoding="utf-8",
            )
            self.assertEqual(_log_errors(path), [])
            errors = _log_errors(path, strict_layout=True)
        self.assertEqual(len(errors), 1)
        self.assertIn("Overfull", errors[0])


if __name__ == "__main__":
    unittest.main()
