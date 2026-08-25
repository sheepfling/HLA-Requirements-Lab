"""Contracts for the shared HLA Requirements Lab publication style profile."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = (
    "hla-1516-2010",
    "hla-1516-2025",
    "hla-1516.1-2010",
    "hla-1516.1-2025",
    "hla-1516.2-2010",
    "hla-1516.2-2025",
)

STALE_PUBLICATION_PHRASES = (
    "IMPORTANT NOTICE",
    "made available for use subject",
    "This revision was sent to SA ballot",
    "Institute of Electrical and Electronics Engineers",
    "Drafting Group",
    "IEEE Standards Association",
    "All rights reserved",
)

OPENING_BLOCKS = {
    "hla-1516-2025": "content-1-normative-001",
    "hla-1516.1-2025": "content-15161-page-016",
    "hla-1516.2-2025": "content-15162-page-013",
}

OPENING_SOURCES = {
    "hla-1516-2010": "clauses/01-overview.tex",
    "hla-1516.1-2010": "clauses/01-overview.tex",
    "hla-1516.2-2010": "clauses/clause01_overview.tex",
}


class StyleProfileContractTests(unittest.TestCase):
    def test_canonical_specimen_and_shared_profile_are_documented(self) -> None:
        readme = (ROOT / "topics" / "ieee" / "requirements-lab" / "README.md").read_text(
            encoding="utf-8"
        )
        profile = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "STYLE-PROFILE.md"
        ).read_text(encoding="utf-8")

        self.assertIn("1516.2-2025 source compilation is the canonical style", readme)
        self.assertIn("style/rl-publication.sty", readme)
        self.assertIn("style/rl-fixed-page.sty", readme)
        self.assertIn("topics/ieee/hla-1516.2-2025/", profile)
        self.assertIn("The six products are deliberately not forced into one body-layout class", profile)

    def test_all_six_products_expose_the_shared_profile_hook(self) -> None:
        for product in PRODUCTS:
            main = (ROOT / "topics" / "ieee" / product / "main.tex").read_text(
                encoding="utf-8"
            )
            if product != "hla-1516.2-2025":
                self.assertIn(
                    "\\input{../requirements-lab/style/rl-publication.sty}",
                    main,
                )
            self.assertIn("\\RLConfigureHLAPublicationProfile", main)

    def test_fixed_page_rules_are_shared_and_parameterized(self) -> None:
        fixed = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "style" / "rl-fixed-page.sty"
        ).read_text(encoding="utf-8")
        publication = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "style" / "rl-publication.sty"
        ).read_text(encoding="utf-8")
        omt_base = (
            ROOT / "topics" / "ieee" / "hla-1516.2-2025" / "ieee-hla-base.sty"
        ).read_text(encoding="utf-8")

        self.assertIn("\\newcommand{\\RLDefineFixedPageStyle}", fixed)
        self.assertIn("\\newcommand{\\RLFixedFurniture}", fixed)
        self.assertIn("\\RLFixedHeaderLeft", fixed)
        self.assertIn("\\RLConfigureHLAPublicationProfile", publication)
        self.assertIn("\\RLDefineFixedPageStyle{RLHLA}", publication)
        self.assertIn("\\RLDefineFixedPageStyle{hla-body-no-ieee}", publication)
        self.assertIn("\\pagestyle{RLHLA}", publication)
        self.assertIn("\\input{../requirements-lab/style/rl-publication.sty}", omt_base)
        self.assertIn("\\RLDefineFixedPageStyle{HLARL}", omt_base)
        self.assertNotIn("\\fancypagestyle{HLARL}", omt_base)

    def test_all_products_use_the_canonical_reading_face_contract(self) -> None:
        type_style = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "style" / "rl-type.sty"
        ).read_text(encoding="utf-8")
        self.assertIn(r"\newfontfamily\RLSerif{Noto Serif}", type_style)
        self.assertIn(r"\newfontfamily\RLSans{Inter}", type_style)
        self.assertIn(r"\setmainfont{Noto Serif}", type_style)
        self.assertIn(r"\setsansfont{Inter}", type_style)

        adapter_styles = {
            "hla-1516-2010": "ieee1516-2010.sty",
            "hla-1516-2025": "hla1516.sty",
            "hla-1516.1-2010": "hla1516.sty",
            "hla-1516.1-2025": "hla2025.sty",
            "hla-1516.2-2010": "ieee1516style.sty",
        }
        for product, filename in adapter_styles.items():
            body = (ROOT / "topics" / "ieee" / product / filename).read_text(
                encoding="utf-8"
            )
            self.assertIn("Noto Serif", body, product)
            self.assertIn("Inter", body, product)
            self.assertNotIn(r"\setmainfont{Tinos}", body, product)
            self.assertNotIn(r"\setsansfont{Arimo}", body, product)

        publication = (
            ROOT
            / "topics"
            / "ieee"
            / "requirements-lab"
            / "style"
            / "rl-publication.sty"
        ).read_text(encoding="utf-8")
        self.assertIn(r"\input{../requirements-lab/style/rl-type.sty}", publication)
        self.assertIn(r"\renewcommand{\HLAFacSerif}{\RLSerif}", publication)
        self.assertIn(r"\renewcommand{\HLAFacSans}{\RLSans}", publication)

    def test_2010_interface_figures_use_canonical_sans_roles(self) -> None:
        root = ROOT / "topics" / "ieee" / "hla-1516.1-2010"
        paths = list((root / "figures" / "native").glob("*.tex"))
        paths.extend((root / "clauses").glob("*.tex"))
        paths.append(root / "semantic" / "content-blocks.json")

        for path in paths:
            body = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn(r"\fontfamily{phv}", body, str(path.relative_to(root)))
            self.assertNotIn(r"\fontfamily{qhv}", body, str(path.relative_to(root)))

    def test_direct_header_adapters_delegate_to_the_shared_header(self) -> None:
        framework_2025 = (
            ROOT / "topics" / "ieee" / "hla-1516-2025" / "main.tex"
        ).read_text(encoding="utf-8")
        omt_2010 = (
            ROOT / "topics" / "ieee" / "hla-1516.2-2010" / "main.tex"
        ).read_text(encoding="utf-8")
        fixed = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "style" / "rl-fixed-page.sty"
        ).read_text(encoding="utf-8")

        self.assertIn("\\renewcommand{\\HLASemanticHeader}{\\RLFixedHeaderFurniture}", framework_2025)
        self.assertIn("\\renewcommand{\\HLASemanticFooter}[2][standard]{\\RLFixedFooterFurniture}", framework_2025)
        self.assertIn("\\renewcommand{\\standardheaders}{\\pagestyle{RLHLA}}", omt_2010)
        self.assertIn("\\newcommand{\\RLFixedHeaderFurniture}", fixed)

    def test_natural_flow_2010_products_reserve_shared_header_height(self) -> None:
        expected = {
            "hla-1516-2010": "20pt",
            "hla-1516.1-2010": "20pt",
            "hla-1516.2-2010": "21pt",
        }
        for product, height in expected.items():
            main = (ROOT / "topics" / "ieee" / product / "main.tex").read_text(
                encoding="utf-8"
            )
            self.assertIn(f"\\setlength{{\\headheight}}{{{height}}}", main, product)

    def test_derived_products_reserve_shared_header_height(self) -> None:
        for product in (
            "hla-rti-compliance-2010",
            "hla-rti-compliance-2025",
            "hla-semantic-derivative-2010",
            "hla-semantic-derivative-2025",
        ):
            main = (ROOT / "topics" / "ieee" / product / "main.tex").read_text(
                encoding="utf-8"
            )
            self.assertIn(r"\setlength{\headheight}{19pt}", main, product)

    def test_derived_products_use_shared_reflowable_typography(self) -> None:
        style = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "style" / "rl-derived.sty"
        ).read_text(encoding="utf-8")
        self.assertIn("rl-headings.sty", style)
        self.assertIn("rl-tables.sty", style)
        self.assertIn(r"\RLBodyFont", style)
        for product in (
            "hla-rti-compliance-2010",
            "hla-rti-compliance-2025",
            "hla-semantic-derivative-2010",
            "hla-semantic-derivative-2025",
        ):
            main = (ROOT / "topics" / "ieee" / product / "main.tex").read_text(
                encoding="utf-8"
            )
            self.assertIn(r"\input{../requirements-lab/style/rl-derived.sty}", main, product)
            self.assertIn(r"\RLConfigureDerivativeTypography", main, product)

    def test_landscape_headers_do_not_add_reference_suffix(self) -> None:
        brand = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "style" / "rl-brand.sty"
        ).read_text(encoding="utf-8")
        self.assertIn(r"\providecommand{\RLLandscapeHeaderRight}{\RLPublicationTitle}", brand)
        page = (
            ROOT / "topics" / "ieee" / "requirements-lab" / "style" / "rl-page.sty"
        ).read_text(encoding="utf-8")
        self.assertIn(r"\renewcommand{\RLHeaderRight}{\RLPublicationTitle}", page)

    def test_landscape_statecharts_have_one_generated_caption(self) -> None:
        for path in (
            ROOT / "topics" / "ieee" / "hla-1516.1-2010" / "hla1516.sty",
            ROOT / "topics" / "ieee" / "hla-1516.1-2025" / "hla2025.sty",
        ):
            style = path.read_text(encoding="utf-8")
            self.assertIn(r"FIGURE~#1\par}%", style, str(path))
            self.assertNotIn(
                r"FIGURE~#1\enspace\textcolor{RLMid}{/}\enspace #2",
                style,
                str(path),
            )

    def test_2025_openers_use_shared_lab_furniture(self) -> None:
        expected = {
            "hla-1516-2025": (
                "content-1-normative-001",
                "\\HLAStartSemanticPage{12}{11}",
            ),
            "hla-1516.1-2025": (
                "content-15161-page-016",
                "\\thispagestyle{RLHLA}",
            ),
            "hla-1516.2-2025": (
                "content-15162-page-013",
                "\\begin{HLASemanticPage}[12]",
            ),
        }
        for product, (block_id, marker) in expected.items():
            path = ROOT / "topics" / "ieee" / product / "semantic" / "content-blocks.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            block = next(item for item in payload["content_blocks"] if item["id"] == block_id)
            body = str(block.get("layout_body") or "")
            self.assertIn(marker, body, product)

        opener = json.loads(
            (
                ROOT
                / "topics"
                / "ieee"
                / "hla-1516-2025"
                / "semantic"
                / "content-blocks.json"
            ).read_text(encoding="utf-8")
        )
        body = next(
            item["layout_body"]
            for item in opener["content_blocks"]
            if item["id"] == "content-1-normative-001"
        )
        self.assertIn("\\\\\nHLA 1516 family", body)
        self.assertIn("\\raggedright", body)

    def test_all_opening_pages_use_lab_identity(self) -> None:
        for product, block_id in OPENING_BLOCKS.items():
            path = ROOT / "topics" / "ieee" / product / "semantic" / "content-blocks.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            block = next(item for item in payload["content_blocks"] if item["id"] == block_id)
            body = str(block.get("layout_body") or "")
            self.assertTrue(
                "HLA Requirements Lab" in body or "\\RLDocumentOpeningTitle" in body,
                product,
            )
            self.assertNotIn("IEEE Standard for", body, product)

        for product, relative_path in OPENING_SOURCES.items():
            body = (ROOT / "topics" / "ieee" / product / relative_path).read_text(
                encoding="utf-8"
            )
            self.assertIn("\\RLDocumentOpeningTitle", body, product)
            self.assertNotIn("IEEE Standard for", body, product)

    def test_omt_glyph_category_is_live_vector_artwork_in_both_editions(self) -> None:
        omt_2010 = (
            ROOT / "topics" / "ieee" / "hla-1516.2-2010" / "ieee1516style.sty"
        ).read_text(encoding="utf-8")
        omt_2025 = (
            ROOT / "topics" / "ieee" / "hla-1516.2-2025" / "ieee-hla-base.sty"
        ).read_text(encoding="utf-8")

        self.assertIn(r"\newcommand{\omtcategoryglyph}", omt_2010)
        self.assertIn(r"\begin{tikzpicture}", omt_2010)
        self.assertIn(r"\fill[HLAOMTOrange", omt_2010)
        self.assertNotIn(r"\includegraphics", omt_2010)

        self.assertIn(r"\NewDocumentCommand{\HLAObjectModelGlyphAt}", omt_2025)
        self.assertIn(r"\begin{tikzpicture}", omt_2025)
        self.assertIn(r"\fill[RLOrange", omt_2025)

    def test_2010_omt_tables_use_the_shared_quiet_rule_surface(self) -> None:
        style = (
            ROOT / "topics" / "ieee" / "hla-1516.2-2010" / "ieee1516style.sty"
        ).read_text(encoding="utf-8")
        main = (
            ROOT / "topics" / "ieee" / "hla-1516.2-2010" / "main.tex"
        ).read_text(encoding="utf-8")

        self.assertIn(r"\colorbox{RLTableBand}", style)
        self.assertIn(r"draw=RLBlue", style)
        self.assertIn(r"draw=RLLine", style)
        self.assertIn(r"\arrayrulecolor{RLLine}", main)
        self.assertIn(r"\setlength{\arrayrulewidth}{0.35pt}", main)

    def test_2025_omt_example_caption_is_explicitly_semantic(self) -> None:
        payload = json.loads(
            (
                ROOT
                / "topics"
                / "ieee"
                / "hla-1516.2-2025"
                / "semantic"
                / "table-families.json"
            ).read_text(encoding="utf-8")
        )
        family = next(
            item for item in payload["table_families"] if item["id"] == "omt-object-model-identification"
        )
        self.assertEqual(
            family["table_captions"]["m4.p038.t01"],
            "Table 3—Object model identification table example",
        )

    def test_derived_sources_do_not_reintroduce_publisher_boilerplate(self) -> None:
        ignored_directories = {"build", "dist", "output", ".git"}
        for product in PRODUCTS:
            root = ROOT / "topics" / "ieee" / product
            for path in root.rglob("*"):
                if not path.is_file() or any(part in ignored_directories for part in path.parts):
                    continue
                if path.suffix.lower() not in {".tex", ".json"}:
                    continue
                body = path.read_text(encoding="utf-8", errors="ignore")
                for phrase in STALE_PUBLICATION_PHRASES:
                    self.assertNotIn(phrase, body, f"{product}: {path.relative_to(root)}")


if __name__ == "__main__":
    unittest.main()
