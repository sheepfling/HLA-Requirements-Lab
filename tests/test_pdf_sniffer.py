"""Focused contracts for generated PDF artifact checks."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pymupdf

from hla_lab.publication.hla_pdf_sniffer import (
    _hla_text_findings,
    _list_label_sequence_findings,
    _missing_internal_reference_findings,
    _normalized_handle_semantics_findings,
    sniff_hla_pdf,
)
from hla_lab.publication.pdf_sniffer import _overfull_box_finding, sniff_pdf


class PdfSnifferTests(unittest.TestCase):
    def _pdf(self, root: Path, text: str = "") -> Path:
        path = root / "sample.pdf"
        document = pymupdf.open()
        page = document.new_page()
        if text:
            page.insert_text((72, 72), text)
        document.save(path)
        document.close()
        return path

    def test_visible_tex_command_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = sniff_pdf(self._pdf(Path(temporary), r"A visible \ldots command"))

        self.assertFalse(report.passed)
        self.assertIn("raw-tex-command", {finding.code for finding in report.findings})

    def test_incomplete_mom_table_header_is_an_error(self) -> None:
        text = "MOM attribute table Order Transportation Data type Attribute Object class"
        with tempfile.TemporaryDirectory() as temporary:
            report = sniff_hla_pdf(self._pdf(Path(temporary), text))

        finding = next(item for item in report.findings if item.code == "semantic-table-layout")
        self.assertFalse(report.passed)
        self.assertIn("availability", finding.message)
        self.assertIn("update behavior", finding.message)

    def test_mom_interaction_table_requires_three_semantic_columns(self) -> None:
        text = "Table 18 MOM interaction class definitions table Interaction Semantics"
        with tempfile.TemporaryDirectory() as temporary:
            report = sniff_hla_pdf(self._pdf(Path(temporary), text))

        finding = next(item for item in report.findings if item.code == "semantic-table-layout")
        self.assertIn("parent class", finding.message)

    def test_mom_attribute_table_requires_attribute_semantics_and_class(self) -> None:
        text = "Table 19 MOM attribute definitions table Attribute Semantics"
        with tempfile.TemporaryDirectory() as temporary:
            report = sniff_hla_pdf(self._pdf(Path(temporary), text))

        finding = next(item for item in report.findings if item.code == "semantic-table-layout")
        self.assertIn("class", finding.message)

    def test_mom_simple_data_type_table_requires_all_six_columns(self) -> None:
        text = "Table 12 MOM simple data type table Name Representation Units Resolution Semantics"
        with tempfile.TemporaryDirectory() as temporary:
            report = sniff_hla_pdf(self._pdf(Path(temporary), text))

        finding = next(item for item in report.findings if item.code == "semantic-table-layout")
        self.assertIn("accuracy", finding.message)

    def test_rotated_mom_normalization_sentence_order_is_checked(self) -> None:
        broken = (
            "HLAnormalizedFederateHandle Normalize Federate Handle "
            "The normalized value of a federate handle as returned by the service."
        )
        corrected = (
            "HLAnormalizedFederateHandle The normalized value of a federate handle "
            "as returned by the Normalize Federate Handle service."
        )

        self.assertEqual(len(_normalized_handle_semantics_findings(broken, 1)), 1)
        self.assertEqual(_normalized_handle_semantics_findings(corrected, 1), ())

    def test_overfull_tex_warning_includes_largest_source_locations(self) -> None:
        log = (
            "Overfull \\hbox (12.50pt too wide) in paragraph at lines 200--201\n"
            "Overfull \\hbox (28.75pt too wide) in alignment at lines 900--904\n"
        )

        finding = _overfull_box_finding(log)

        self.assertIsNotNone(finding)
        assert finding is not None
        self.assertIn("2 overfull box(es)", finding.message)
        self.assertIn("900-904", finding.message)
        self.assertIn("28.75 pt", finding.message)

    def test_duplicate_semantic_destinations_are_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "reflowable.tex"
            source.write_text(
                "\\hypertarget{repeated-clause}{}\n\\hypertarget{repeated-clause}{}\n",
                encoding="utf-8",
            )
            report = sniff_pdf(self._pdf(root), source_tex=source)

        self.assertFalse(report.passed)
        finding = next(item for item in report.findings if item.code == "duplicate-semantic-anchor")
        self.assertIn("repeated-clause (2x)", finding.message)

    def test_empty_brackets_are_a_warning_not_a_release_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = sniff_pdf(self._pdf(Path(temporary), "Source marker [ ]"))

        self.assertTrue(report.passed)
        self.assertIn("empty-brackets", {finding.code for finding in report.findings})

    def test_hla_ps_notation_is_not_mistaken_for_an_extraction_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = sniff_hla_pdf(self._pdf(Path(temporary), "The <P/S> field is retained."))

        self.assertNotIn("p-s-placeholder-residue", {finding.code for finding in report.findings})

    def test_hla_sniffer_flags_joined_source_words(self) -> None:
        findings = _hla_text_findings(
            "The switch cannot be insertedfail; see the equivalentto rule.",
            578,
        )

        finding = next(item for item in findings if item.code == "joined-source-token")
        self.assertEqual(finding.severity, "warning")
        self.assertIn("insertedfail", finding.message)

    def test_hla_sniffer_rejoins_line_wraps_before_checking_source_words(self) -> None:
        findings = _hla_text_findings("The rule was equiv-\nalentto the text.", 323)

        finding = next(item for item in findings if item.code == "joined-source-token")
        self.assertIn("equivalentto", finding.message)

    def test_hla_sniffer_does_not_flag_separated_source_words(self) -> None:
        findings = _hla_text_findings(
            "The switch cannot be inserted. The merge shall fail.",
            578,
        )

        self.assertNotIn("joined-source-token", {finding.code for finding in findings})

    def test_hla_sniffer_ignores_mixed_case_api_names_and_common_words(self) -> None:
        findings = _hla_text_findings(
            "Within the document, another federate uses HLAobjectClass and federateType.",
            578,
        )

        self.assertNotIn("joined-source-token", {finding.code for finding in findings})

    def test_hla_sniffer_preserves_intentional_hyphenation(self) -> None:
        findings = _hla_text_findings("A user- supplied tag is valid.", 67)

        self.assertNotIn("joined-source-token", {finding.code for finding in findings})

    def test_hla_sniffer_flags_fused_definition_phrases_and_source_markers(self) -> None:
        findings = _hla_text_findings(
            "[l]Collectionofall employee addresses; Check-offon whether the server succeeded.",
            41,
        )

        self.assertIn("source-list-marker-residue", {finding.code for finding in findings})
        joined = next(item for item in findings if item.code == "joined-source-token")
        self.assertIn("Collectionofall", joined.message)
        self.assertIn("Check-offon", joined.message)

    def test_hla_sniffer_flags_flattened_see_also_terms(self) -> None:
        findings = _hla_text_findings(
            "A named characteristic of an object class or object instance. "
            "class attribute instance attribute.",
            5,
        )

        self.assertIn("flattened-see-also-terms", {finding.code for finding in findings})

    def test_hla_list_sequence_ignores_valid_source_label_gaps(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "d) first item\ne) second item\ng) third item")

        findings = _list_label_sequence_findings(page, 1)
        document.close()

        self.assertEqual(findings, [])

    def test_hla_list_sequence_resets_at_a_subsection_heading(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "a) first item\nb) second item")
        page.insert_text((72, 105), "8.1.2 Supplied arguments", fontname="hebo")
        page.insert_text((72, 126), "a) next section\nb) next item")

        findings = _list_label_sequence_findings(page, 1)
        document.close()

        self.assertEqual(findings, [])

    def test_hla_list_sequence_reports_a_restart_without_a_boundary(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "a) first item\nb) second item\na) restarted item")

        findings = _list_label_sequence_findings(page, 1)
        document.close()

        self.assertEqual(len(findings), 1)
        self.assertIn("restarts from b) to a)", findings[0].message)

    def test_hla_list_sequence_resets_at_a_wrapped_lead_in(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text(
            (72, 72),
            "a) first list item\nb) second list item. The following cases\n"
            "are as follows:\na) first case\nb) second case",
        )

        findings = _list_label_sequence_findings(page, 1)
        document.close()

        self.assertEqual(findings, [])

    def test_hla_figure_reference_check_recognizes_linked_figure_title(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "linked-figure.pdf"
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((72, 72), "a) Figure 11, Class attribute (i, j).")
            target = page.search_for("Figure 11")[0]
            page.insert_link({"kind": pymupdf.LINK_GOTO, "from": target, "page": 0})
            document.save(path)
            document.close()

            with pymupdf.open(path) as verified:
                findings = _missing_internal_reference_findings(verified[0], 1)

        self.assertEqual(findings, [])

    def test_uppercase_hla_variables_are_not_alpha_list_labels(self) -> None:
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "a) first item\nb) the federate F) has invoked the service")

        findings = _list_label_sequence_findings(page, 1)
        document.close()

        self.assertEqual(findings, [])


if __name__ == "__main__":
    unittest.main()
