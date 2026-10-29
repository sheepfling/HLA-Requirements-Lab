"""Tests for source-to-semantic prose normalization."""

from __future__ import annotations

import unittest

from hla_lab.core.semantic_text import _latex_text


class SemanticTextTests(unittest.TestCase):
    def test_explicit_latex_spaces_and_line_breaks_preserve_word_boundaries(self) -> None:
        source = (
            r"padding\space{}bytes, if\space{}required; first\space{}element "
            r"of\space{}P\space{}that\newline{}continues"
        )

        self.assertEqual(
            _latex_text(source),
            "padding bytes, if required; first element of P that continues",
        )


if __name__ == "__main__":
    unittest.main()
