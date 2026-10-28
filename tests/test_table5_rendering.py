"""Regression checks for the three-column Table 5 publication layout."""

from __future__ import annotations

import unittest

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.semantic_generation import _modern_table5_page
from tests.support import TEST_REPO_ROOT


class Table5RenderingTests(unittest.TestCase):
    def test_continued_encoding_fields_stay_in_encoding_column(self) -> None:
        root = TEST_REPO_ROOT / "topics" / "ieee" / "hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        table = next(table for table in model.tables if table.id == "table-5-p296")
        rendered = _modern_table5_page(table, sequence=296)

        for type_name, encoding_field, example_field in (
            ("ConfigurationResult", "configurationUsed:Boolean", "configurationUsed"),
            ("Credentials", "Type:String", "HLAplainTextPassword"),
        ):
            with self.subTest(type_name=type_name):
                row = next(line for line in rendered.splitlines() if type_name in line)
                type_cell, encoding_cell, example_cell = row.split(" & ", 2)
                self.assertIn(type_name, type_cell)
                self.assertIn(encoding_field.replace(":", r":\penalty0"), encoding_cell)
                self.assertNotIn(encoding_field, example_cell)
                self.assertIn(example_field, example_cell)
                self.assertIn(r"\par", encoding_cell)


if __name__ == "__main__":
    unittest.main()
