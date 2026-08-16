from __future__ import annotations

import unittest
from pathlib import Path

from hla_lab.core.coercions import coerce_int, optional_float
from hla_lab.core.parsing import balanced_group, balanced_span, line_number, try_balanced_group
from hla_lab.core.text import (
    dot_quote,
    format_number,
    mermaid_text,
    normalize_whitespace,
    safe_filename,
    safe_identifier,
    slugify,
    tex_escape,
)
from tools.utility_inventory import inventory

class UtilityTests(unittest.TestCase):
    def test_text_helpers_cover_renderer_edge_cases(self) -> None:
        self.assertEqual(safe_identifier("1/ready", prefix="state"), "state_n_1_ready")
        self.assertEqual(safe_identifier("a b", prefix=""), "a_b")
        self.assertEqual(slugify("  HLA 1516.1 / RTI "), "hla-1516-1-rti")
        self.assertEqual(slugify("!!!", fallback="transition"), "transition")
        self.assertEqual(normalize_whitespace("a\r\n b\t c"), "a b c")
        self.assertEqual(format_number(1.2500), "1.25")
        self.assertEqual(format_number(0.0), "0")
        self.assertEqual(mermaid_text('a\\b"c\nd'), "a\\\\b'c d")
        self.assertEqual(dot_quote('a\\b"c\nd'), '"a\\\\b\\"c\\nd"')
        self.assertEqual(tex_escape(r"A&B%#_$\{}"), r"A\&B\%\#\_\$\textbackslash{}\{\}")

    def test_safe_filename_is_bounded_and_stable(self) -> None:
        value = "part/" + "x" * 200
        first = safe_filename(value)
        self.assertEqual(first, safe_filename(value))
        self.assertLessEqual(len(first), 120)
        self.assertTrue(first.endswith("-" + safe_filename(value)[-12:]))

    def test_balanced_parsers_share_escaped_nested_group_behavior(self) -> None:
        text = r"  {outer {inner\} still} tail}"
        body, end = balanced_group(text, 0, skip_whitespace=True)
        self.assertEqual(body, r"outer {inner\} still} tail")
        self.assertEqual(text[end:], "")
        self.assertEqual(balanced_span("{a{b}}", 0), (1, 5))
        self.assertIsNone(try_balanced_group("x", 0))
        self.assertEqual(line_number("one\ntwo\nthree", 8), 3)

    def test_coercions_are_explicit_at_untyped_boundaries(self) -> None:
        self.assertEqual(coerce_int("12"), 12)
        self.assertEqual(coerce_int(12.9), 12)
        self.assertEqual(optional_float("1.25"), 1.25)
        self.assertIsNone(optional_float("not-a-number"))
        with self.assertRaises(ValueError):
            coerce_int({})

    def test_repository_helper_inventory_has_no_exact_duplicate_bodies(self) -> None:
        _definitions, duplicates = inventory(Path(__file__).resolve().parents[1])
        self.assertEqual(duplicates, ())

if __name__ == "__main__":
    unittest.main()
