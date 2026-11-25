from __future__ import annotations

import unittest

from hla_lab.core.semantic_model_tables import _table_text


class SemanticModelTableTextTests(unittest.TestCase):
    def test_layout_spacing_and_line_hyphenation_preserve_words(self) -> None:
        text = (
            r"\makebox[67bp][l]{Check-off\hfill{}on}"
            r"\newline{}\resizebox{67bp}{!}{\mbox{performed proper-}}"
            r"\newline{}\resizebox{67bp}{!}{\mbox{ly on elements}}"
        )

        self.assertEqual(
            _table_text(text),
            "Check-off on performed properly on elements",
        )


if __name__ == "__main__":
    unittest.main()
