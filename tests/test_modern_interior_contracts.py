"""Source-level gates for the modern Requirements Lab interior profile."""

from __future__ import annotations

import unittest

from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
LAB_ROOT = ROOT / "topics" / "ieee" / "requirements-lab"
SLICE_ROOT = ROOT / "topics" / "ieee" / "hla-1516.2-2025-modern-acceptance"


class ModernInteriorContractTests(unittest.TestCase):
    def test_shared_typography_and_page_furniture_use_the_modern_tokens(self) -> None:
        typography = (LAB_ROOT / "style" / "rl-type.sty").read_text(encoding="utf-8")
        page = (LAB_ROOT / "style" / "rl-page.sty").read_text(encoding="utf-8")
        graphics = (LAB_ROOT / "style" / "rl-graphics.sty").read_text(encoding="utf-8")
        frontmatter = (LAB_ROOT / "style" / "rl-frontmatter.sty").read_text(encoding="utf-8")

        self.assertIn(r"\newfontfamily\RLSerif{Noto Serif}", typography)
        self.assertIn(r"\newfontfamily\RLSans{Inter}", typography)
        self.assertIn(r"\newfontfamily\RLMono{DejaVu Sans Mono}", typography)
        self.assertIn("Inter-Regular.ttf", typography)
        self.assertIn("Inter-ExtraBold.ttf", typography)
        self.assertNotIn("DejaVu Sans}[", typography)
        self.assertIn(r"\color{RLInk}", typography)
        self.assertIn(r"\RLHeaderMark", page)
        self.assertIn(r"\thepage", page)
        self.assertIn(r"\RLHeaderLeft", page)
        self.assertIn(r"\RLHeaderRight", page)
        self.assertIn(r"\RLHeaderFooter", page)
        self.assertIn(r"\newenvironment{RLLandscapePage}", page)
        self.assertIn("papersize=792bp,612bp", page)
        self.assertIn(r"\RLFamilyGlyph", graphics)
        self.assertIn(r"\RLOMTGlyph", graphics)
        self.assertIn("RLGraph2010", graphics)
        self.assertIn("RLGraph2025", graphics)
        self.assertIn("HLA REQUIREMENTS LAB \\textbar\\ SOURCE COMPILATION", frontmatter)
        self.assertNotIn("UNOFFICIAL", frontmatter)

    def test_shared_table_layer_exposes_the_modern_table_grammar(self) -> None:
        tables = (LAB_ROOT / "style" / "rl-tables.sty").read_text(encoding="utf-8")
        notes = (LAB_ROOT / "style" / "rl-notes.sty").read_text(encoding="utf-8")

        self.assertIn("RLTableBand", tables)
        self.assertIn(r"\RLInlineTableCaption", tables)
        self.assertIn(r"\newcommand{\RLProductionTopRule}", tables)
        self.assertIn(r"\newcommand{\RLProductionRowRule}", tables)
        self.assertIn(r"\newcommand{\RLProductionHeaderBand}", tables)
        self.assertIn(r"\newcommand{\RLProductionHeaderSpace}", tables)
        self.assertIn(r"\newcommand{\RLTableGroupHeader}", tables)
        self.assertIn(r"\NewDocumentCommand{\RLProductionNote}", notes)
        self.assertIn(r"\begin{longtable}", tables)
        self.assertIn(r"\RequirePackage{booktabs}", tables)
        self.assertIn(r"\RequirePackage{colortbl}", tables)
        self.assertIn(r"\rowcolor{RLTableBand}", tables)
        self.assertIn(r"\toprule", tables)

    def test_source_driven_preview_covers_the_required_layout_families(self) -> None:
        source = (SLICE_ROOT / "main.tex").read_text(encoding="utf-8")

        self.assertIn("A logical time represents a single point", source)
        self.assertIn(r"\RLInlineTableCaption{16}", source)
        self.assertIn(r"\RLInlineTableCaption{29}", source)
        self.assertIn(r"\RLInlineTableCaption{5}", source)
        self.assertIn(r"\RLInlineTableCaption{10}", source)
        self.assertIn(r"\RLInlineTableCaption{11}", source)
        self.assertIn(r"\RLInlineTableCaption{45}", source)
        self.assertIn(r"\RLInlineTableCaption{17}", source)
        self.assertEqual(source.count(r"\begin{RLLandscapePage}"), 2)
        self.assertIn(r"\RLSubclauseLabel{4.8", source)
        self.assertIn(r"\RLMinorHeading{4.8.4 Example}", source)
        self.assertIn(r"\RLMinorHeadingSmall{4.9.1 Purpose/background}", source)
        self.assertNotIn(r"\RLHeading{16pt}{4.8", source)
        self.assertIn(r"\RLIdentifier{LogicalTime}", source)
        self.assertIn(r"\RLIdentifier{LogicalTimeInterval}", source)
        self.assertIn(r"\TableTech{HLAinteger16BE}", source)
        self.assertIn(
            r"\TableTech{HLAfloat64BE} & 64 bit & Double-precision floating point number & "
            r"Big & 64-bit IEEE normalized double-precision format.",
            source,
        )
        self.assertIn(
            r"\TableTech{HLAfloat64LE} & 64 bit & Double-precision floating point number & "
            r"Little & 64-bit IEEE normalized double-precision format.",
            source,
        )
        self.assertEqual(source.count(r"\TableTech{<name>}"), 2)
        self.assertIn(r"\ASmallID{HLAprivilegeToDeleteObject}", source)
        self.assertIn(
            r"\ASmallID{HLAobjectRoot} & \ASmallID{HLAprivilegeToDeleteObject} & "
            r"\ASmallID{HLAtoken}",
            source,
        )
        self.assertIn("Value Required", source)
        self.assertIn("Available dimensions", source)
        self.assertIn(r"\ASmallID{Employee.Server} & \ASmallID{Efficiency}", source)
        self.assertIn(r"\ASmallID{Food.Drink}", source)
        self.assertIn(r"\ASmallID{Food.Drink.Soda}", source)
        self.assertIn(r"\ASmallID{Food.Drink.Soda} & \ASmallID{Light}", source)
        self.assertNotIn(r"\ASmallIDPath", source)
        self.assertIn(r"\ATemplate{<update type>}", source)
        self.assertIn(r"\ATemplate{<update condition>}", source)
        self.assertIn(r"\ATemplate{<value required>}", source)
        self.assertIn(r"\ASmallID{BarQuantity}", source)
        self.assertIn(r"\ASmallID{SodaFlavor}", source)
        self.assertIn(r"\ASmallID{Sweetener}", source)
        self.assertIn(r"\AText{TimeStamp}", source)
        self.assertNotIn("Time-stamp", source)
        self.assertIn(r"\TreeEdge{HLAobjectRoot}{Bill}", source)
        self.assertIn(r"\TreeEdge{Food}{Drink}", source)
        self.assertIn(r"\TreeEdge{Drink}{Water}", source)
        self.assertNotIn(r"\TreeRow{│\enspace├──}{Bill}", source)
        self.assertNotIn(r"\TreeRow{\enspace\enspace│\enspace├──}{Drink}", source)
        self.assertIn("Gluten Normalization Function", source)
        self.assertIn("can\u2019t be modified", source)
        self.assertIn("Note 7", source)
        self.assertNotIn("Meaning", source)
        self.assertNotIn("Own.", source)
        self.assertNotIn(r"\RLRationale", source)
        self.assertNotIn(r"\RLSourceStamp", source)

    def test_source_driven_preview_is_scoped_as_a_lab_publication(self) -> None:
        source = (SLICE_ROOT / "main.tex").read_text(encoding="utf-8")

        self.assertIn("HLA Requirements Lab", source)
        self.assertIn("HLA 1516.2-2025", source)
        self.assertIn(r"\textperiodcentered", source)
        self.assertIn("complete body migration follows", source)
        self.assertNotIn("IEEE Std 1516.2-2025", source)
        self.assertNotIn("IEEE Standard for Modeling and Simulation", source)

    def test_omt_glyph_category_is_vector_only(self) -> None:
        base = (ROOT / "topics" / "ieee" / "hla-1516.2-2025" / "ieee-hla-base.sty").read_text(
            encoding="utf-8"
        )
        blocks_2025 = (
            ROOT / "topics" / "ieee" / "hla-1516.2-2025" / "semantic" / "content-blocks.json"
        ).read_text(encoding="utf-8")
        style_2010 = (ROOT / "topics" / "ieee" / "hla-1516.2-2010" / "ieee1516style.sty").read_text(
            encoding="utf-8"
        )
        source_2010 = (
            ROOT
            / "topics"
            / "ieee"
            / "hla-1516.2-2010"
            / "clauses"
            / "clause04_omt_components_continuation.tex"
        ).read_text(encoding="utf-8")

        self.assertIn(r"\NewDocumentCommand{\HLAObjectModelGlyphAt}", base)
        self.assertIn(r"\HLAObjectModelGlyphAt{369.000}{601.320}{24.000}{24.000}", blocks_2025)
        self.assertNotIn("page-038-image-01.png", blocks_2025)
        self.assertIn(r"\newcommand{\omtcategoryglyph}", style_2010)
        self.assertIn(r"\omtcategoryglyph", source_2010)
        self.assertNotIn(r"\restaurantglyph", style_2010 + source_2010)

    def test_supplied_prototype_reference_is_preserved_with_the_production_adapter(self) -> None:
        reference = LAB_ROOT / "prototype-reference"

        for filename in (
            "hla_omt_modern_interior_prototype_v1.pdf",
            "hla_omt_modern_portrait_source.tex",
            "hla_omt_modern_landscape_source.tex",
            "rl_graphics.sty",
            "PROTOTYPE-SOURCE.md",
        ):
            self.assertTrue((reference / filename).is_file(), filename)


if __name__ == "__main__":
    unittest.main()
