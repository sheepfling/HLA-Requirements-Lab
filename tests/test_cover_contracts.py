"""Regression checks for the HLA Requirements Lab edition covers."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED_COVER = ROOT / "topics" / "ieee" / "hla-requirements-lab-cover.tex"


class CoverContractTests(unittest.TestCase):
    def test_shared_cover_preserves_the_lab_visual_language(self) -> None:
        cover = SHARED_COVER.read_text(encoding="utf-8")

        self.assertIn("\\definecolor{HLALabBlue}", cover)
        self.assertIn("\\definecolor{HLALabOrange}", cover)
        self.assertIn("Product preambles load the shared graphics adapter", cover)
        self.assertGreaterEqual(cover.count("fill opacity="), 4)
        self.assertIn("HLA REQUIREMENTS LAB", cover)
        self.assertIn("\\HLALabNumber", cover)
        self.assertIn("HLA REQUIREMENTS LAB | SOURCE COMPILATION", cover)
        self.assertNotIn("UNOFFICIAL - NON-AUTHORITATIVE DERIVED EDITION", cover)
        self.assertIn("\\HLALabSourceAttribution", cover)
        self.assertNotIn("\\HLALabSourceRightsLine", cover)
        self.assertIn(
            "Prepared from supplied HLA source materials; "
            "source identifiers retained for traceability.",
            cover,
        )
        self.assertIn("HLA Requirements Lab original work", cover)
        self.assertIn("\\HLALabStatusLine", cover)
        self.assertIn("\\RLFamilyGlyph{\\HLALabEditionYear}{\\HLALabTheme}", cover)
        self.assertIn("HLALabPurple", cover)

    def test_all_source_compilations_use_the_shared_cover(self) -> None:
        expected = {
            ("1516.1", "2010"): (364,),
            ("1516.1", "2025"): (424,),
            ("1516", "2010"): (27,),
            ("1516", "2025"): (30,),
            ("1516.2", "2010"): (101,),
            ("1516.2", "2025"): (112,),
        }
        for (standard, edition), (expected_pages,) in expected.items():
            main = (
                ROOT / "topics" / "ieee" / f"hla-{standard}-{edition}" / "main.tex"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "\\input{../requirements-lab/style/rl-graphics.sty}",
                main,
            )
            self.assertIn("\\input{../hla-requirements-lab-cover}", main)
            self.assertIn(
                f"\\newcommand{{\\HLALabEdition}}{{{edition}-source compilation}}",
                main,
            )
            self.assertIn(f"\\newcommand{{\\HLALabEditionYear}}{{{edition}}}", main)
            self.assertIn("\\newcommand{\\HLALabTheme}", main)
            source_attribution = (
                "\\newcommand{\\HLALabSourceAttribution}{"
                f"Source set: supplied HLA {standard} family materials from {edition}."
            )
            self.assertIn(
                source_attribution,
                main,
            )
            self.assertNotIn("IEEE Std", main)

            manifest = json.loads((ROOT / "data" / "release" / "documents.json").read_text())
            project = next(
                item for item in manifest["projects"] if item["id"] == f"hla-{standard}-{edition}"
            )
            self.assertEqual(project["expected_pages"], expected_pages)
            self.assertNotIn("ieee-std-", project["pdf"])

    def test_readable_edition_labels_use_blue_text(self) -> None:
        for standard in ("1516", "1516.1", "1516.2"):
            main = (
                ROOT / "topics" / "ieee" / f"hla-{standard}-2025" / "main.tex"
            ).read_text(encoding="utf-8")
            self.assertIn(
                "\\newcommand{\\HLALabYearAccent}{HLALabBlue}",
                main,
            )

    def test_volume_accents_follow_the_family_graphics_system(self) -> None:
        expected = {
            "1516": "HLALabBlue",
            "1516.1": "HLALabPurple",
            "1516.2": "HLALabOrange",
        }
        for standard, accent in expected.items():
            for edition in ("2010", "2025"):
                main = (
                    ROOT / "topics" / "ieee" / f"hla-{standard}-{edition}" / "main.tex"
                ).read_text(encoding="utf-8")
                self.assertIn(
                    f"\\newcommand{{\\HLALabAccent}}{{{accent}}}",
                    main,
                )


if __name__ == "__main__":
    unittest.main()
