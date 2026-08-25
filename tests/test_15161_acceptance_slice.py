"""Source-level contracts for the HLA 1516.1 staged acceptance slice."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE, source_profile_for_document
from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.semantic_generation import (
    _modern_api_manifest_page,
    _modern_java_factory_page,
    _modern_mom_definition_rows,
    _modern_mom_hierarchy_rows,
    _modern_protocol_prose_page,
    _modern_service_flow_page,
    _modern_2025_statechart_reflow_page,
    _modern_statechart_reflow_page,
    _modern_table_text,
    _semanticize_visible_surfaces,
)


ROOT = Path(__file__).resolve().parents[1]
DOC_ROOT = ROOT / "topics" / "ieee" / "hla-1516.1-2025"
SLICE = DOC_ROOT / "acceptance_slice.tex"


class HLA15161AcceptanceSliceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SLICE.read_text(encoding="utf-8")

    def test_required_acceptance_subjects_are_present(self) -> None:
        required = (
            "state-machine-federation-execution.tex",
            "state-machine-federate-lifetime.pdf",
            "state-machine-joined-federate-state.pdf",
            "state-machine-global-synchronization-label.pdf",
            "state-machine-awaiting-synchronization.tex",
            "state-machine-temporal-state.pdf",
            "HLAServiceContract}{4.2 Connect}",
            "HLAServiceContract}{4.4 Connection Lost",
            "MOM Table 5",
            "MOM object-class hierarchy",
            "Java mapping uses selectable monospace code",
            "Java and C++ encoding helper registry",
            "Federate Protocol settings",
            r"CTRL\_NEW\_SESSION",
            "hla/rti1516_2025/",
            "Regenerated figure index",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, self.source)

    def test_dense_charts_use_landscape_acceptance_pages(self) -> None:
        self.assertIn(
            r"\AcceptancePlantLandscapeFigure{3}{Federate lifetime}",
            self.source,
        )
        self.assertIn(
            r"\AcceptancePlantLandscapeFigure{7}{Global synch label (L)}",
            self.source,
        )
        self.assertIn(
            r"\AcceptancePlantLandscapeFigure{17}{Temporal state}",
            self.source,
        )
        self.assertNotIn("resizebox{0.96\\linewidth}{!}{\\input{output/semantic/state-machine-federate-lifetime.tex}}", self.source)

    def test_full_2025_sync_chart_run_has_one_landscape_page_per_chart(self) -> None:
        blocks = json.loads(
            (DOC_ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        by_sequence = {item["sequence"]: item for item in blocks}
        figure6 = _modern_2025_statechart_reflow_page(
            by_sequence[45]["layout_body"],
            sequence=45,
            figures=[
                (
                    6,
                    "state-machine-federation-execution-sync-overview.pdf",
                    "Federation Execution and Sync Points",
                )
            ],
        )
        figure78 = _modern_2025_statechart_reflow_page(
            by_sequence[46]["layout_body"],
            sequence=46,
            figures=[
                (7, "state-machine-global-synchronization-label.pdf", "Global synch label (L)"),
                (8, "state-machine-awaiting-synchronization.pdf", "Awaiting synchronization (s, L)"),
            ],
        )
        figure9 = _modern_2025_statechart_reflow_page(
            by_sequence[47]["layout_body"],
            sequence=47,
            figures=[
                (9, "state-machine-local-synchronization-label.pdf", "Local synch label (s, L)"),
            ],
        )
        self.assertEqual(figure6.count(r"\HLALandscapeFigurePDFPage"), 1)
        self.assertEqual(figure78.count(r"\HLALandscapeFigurePDFPage"), 2)
        self.assertEqual(figure9.count(r"\HLALandscapeFigurePDFPage"), 1)
        self.assertNotIn(r"\HLAFigureImageAt", figure9)

    def test_figure_titles_match_current_semantic_records(self) -> None:
        expected = {
            "federation-execution.json": "Basic states of the federation execution",
            "federate-lifetime.json": "Federate lifetime",
            "joined-federate-state.json": "Joined federate state",
            "global-synch-label.json": "Global synch label (L)",
            "awaiting-synchronization.json": "Awaiting synchronization (s, L)",
        }
        for filename, title in expected.items():
            payload = json.loads((DOC_ROOT / "semantic" / filename).read_text(encoding="utf-8"))
            record = payload["state_machines"][0]
            with self.subTest(filename=filename):
                self.assertEqual(record["title"], title)
                self.assertIn(title, self.source)

        self.assertIn("Joined federate state", self.source)

    def test_service_directions_and_protocol_tokens_are_textual(self) -> None:
        self.assertIn(r"{4.2 Connect}{FEDERATE $\rightarrow$ RTI}", self.source)
        self.assertIn(r"{4.4 Connection Lost \textdagger}{RTI $\rightarrow$ FEDERATE}", self.source)
        for token in (r"CTRL\_NEW\_SESSION", r"CTRL\_NEW\_SESSION\_STATUS", r"HLA\_CALLBACK\_REQUEST"):
            self.assertIn(token, self.source)
        self.assertIn(r"\RLInlineTableCaption{34--35}{Federate Protocol message registry}", self.source)

    def test_acceptance_slice_uses_source_backed_contracts_and_tables(self) -> None:
        content = json.loads(
            (DOC_ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        source_blocks = {item["id"]: item for item in content}
        normalized_source = re.sub(r"\s+", " ", self.source)
        self.assertIn(
            "service allows the RTI to set up and initialize its communication infrastructure.",
            normalized_source,
        )

        elements = json.loads(
            (DOC_ROOT / "semantic" / "content-elements.json").read_text(encoding="utf-8")
        )["content_elements"]
        background = next(
            item["text"]
            for item in elements
            if item.get("clause_id") == "clause-1.4"
            and "language- independent specification" in item.get("text", "")
        )
        self.assertIn("language-independent specification", self.source)
        self.assertIn("distributed simulation domain", background)

        generated_table_files = (
            "table-record-table-5-p295-data.tex",
            "table-record-table-5-p296-data.tex",
            "table-record-table-22-p362-data.tex",
            "table-record-table-26-p380-data.tex",
            "table-record-table-31-p402-data.tex",
            "table-record-table-32-p402-data.tex",
            "table-record-table-33-p402-data.tex",
            "table-record-table-34-p404-data.tex",
        )
        generated_tables = "\n".join(
            (DOC_ROOT / "output" / "semantic" / filename).read_text(encoding="utf-8")
            for filename in generated_table_files
        )
        for marker in (
            "AttributeRegionAssociationList",
            "ConfigurationResult",
            r"RTI\char95{}TIMEOUT\char95{}HEART",
            r"FED\char95{}TIMEOUT\char95{}RECONNECT",
            r"CTRL\char95{}NEW\char95{}SESSION",
            r"HLA\char95{}CALLBACK\char95{}REQUEST",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, generated_tables)

        for marker in (
            "AttributeRegionAssociationList",
            "ConfigurationResult",
            r"RTI\_TIMEOUT\_HEART",
            r"FED\_TIMEOUT\_RECONNECT",
            r"CTRL\_NEW\_SESSION",
            r"HLA\_CALLBACK\_REQUEST",
        ):
            with self.subTest(rendered_marker=marker):
                self.assertIn(marker, self.source)

        api = json.loads(
            (DOC_ROOT / "semantic" / "api-surfaces.json").read_text(encoding="utf-8")
        )["api_surfaces"]
        java_connect = next(
            item for item in api
            if item.get("language") == "java" and item.get("name") == "connect"
        )
        self.assertIn("ConfigurationResult connect", java_connect["signature"])
        for marker in ("RtiFactoryFactory", "RtiFactory", "RTIambassador"):
            self.assertIn(marker, self.source)

    def test_figure_furniture_has_one_generated_caption(self) -> None:
        self.assertNotIn(r"FIGURE~#1\enspace\textcolor", self.source)
        self.assertEqual(self.source.count("Figure~#1---#2"), 3)

    def test_acceptance_slice_has_no_stale_publication_furniture(self) -> None:
        forbidden = (
            "IMPORTANT NOTICE",
            "This document is made available",
            "SA ballot",
            "IEEE SA Standards Board",
            "by the Institute of Electrical and Electronics Engineers",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.source)

    def test_modern_table_text_removes_source_line_break_markers(self) -> None:
        self.assertEqual(
            _modern_table_text("HLAFOMmoduleDesigna-%"),
            "HLAFOMmoduleDesigna",
        )
        self.assertEqual(
            _modern_table_text("save-success %"),
            "save-success",
        )
        self.assertEqual(
            _modern_table_text("source-version"),
            "source-version",
        )
        self.assertEqual(
            _modern_table_text("HLAmanager.HLAfeder-ate"),
            "HLAmanager.HLAfederate",
        )

    def test_full_body_service_adapter_uses_natural_contract_flow(self) -> None:
        blocks = json.loads(
            (DOC_ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        connect = next(item for item in blocks if item.get("sequence") == 51)
        flow = _modern_service_flow_page(connect["layout_body"])
        self.assertIn(r"\begin{HLAServiceFlowPage}", flow)
        self.assertIn(r"\HLAServiceFlowHeading{4.2 \emph{Connect} service}", flow)
        self.assertIn(r"\HLAServiceFlowSection{4.2.1 Supplied arguments}", flow)
        self.assertIn(r"\HLAServiceFlowItem{a)}{Callback model.}", flow)
        self.assertNotIn(r"\begin{hlafixedpage}", flow)
        self.assertNotIn(r"\HLAFixedBlock", flow)

    def test_15161_release_selects_flow_service_pages(self) -> None:
        manifest = json.loads((ROOT / "data" / "release" / "documents.json").read_text())
        project = next(item for item in manifest["projects"] if item["id"] == "hla-1516.1-2025")
        self.assertEqual(project["build"]["service_page_renderer"], "flow")

    def test_mom_renderers_use_semantic_roles_not_extraction_coordinates(self) -> None:
        model = load_document_model(DOC_ROOT, HLA_SOURCE)
        table6 = next(item for item in model.tables if item.number == "6" and not item.continuation)
        table7 = next(item for item in model.tables if item.number == "7" and not item.continuation)
        table17 = next(item for item in model.tables if item.number == "17" and not item.continuation)
        table18 = next(item for item in model.tables if item.number == "18" and not item.continuation)

        self.assertEqual(_modern_mom_hierarchy_rows(table6)[:3], [
            ("0", "HLAobjectRoot (N)"),
            ("1", "HLAmanager (N)"),
            ("2", "HLAfederate (P)"),
        ])
        hierarchy = _modern_mom_hierarchy_rows(table7)
        self.assertTrue(hierarchy)
        self.assertNotIn(" / ", " ".join(value for _depth, value in hierarchy))
        self.assertEqual(hierarchy[0], ("0", "HLAinteractionRoot (N)"))

        object_headers, object_rows = _modern_mom_definition_rows(table17)
        self.assertEqual(object_headers, ["Object class", "Semantics"])
        self.assertIn("HLAmanager.HLAfederate", {row[0] for row in object_rows})
        self.assertTrue(all(not row[0].startswith("This object class") for row in object_rows))

        interaction_headers, interaction_rows = _modern_mom_definition_rows(table18)
        self.assertEqual(interaction_headers, ["Interaction class", "Parent class", "Semantics"])
        request = next(row for row in interaction_rows if row[0] == "HLArequest")
        self.assertEqual(request[1], "HLAmanager.HLAfederate")

    def test_java_factory_surface_has_selectable_code_and_api_tokens(self) -> None:
        blocks = json.loads(
            (DOC_ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        source = next(item["layout_body"] for item in blocks if item.get("sequence") == 360)
        rendered = _modern_java_factory_page(source)
        self.assertGreaterEqual(rendered.count(r"\begin{RLCodeBlock}"), 4)
        self.assertIn(r"\HLAAPIToken{RtiFactory}", rendered)
        self.assertIn("RTIambassador _rtiAmbassador", rendered)
        self.assertNotIn(r"\char95{}", rendered)
        self.assertNotIn(r"\_", rendered)

    def test_full_api_mapping_run_uses_natural_flow_and_token_roles(self) -> None:
        blocks = json.loads(
            (DOC_ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        by_sequence = {item["sequence"]: item for item in blocks}
        for sequence in range(354, 395):
            rendered = _modern_java_factory_page(by_sequence[sequence]["layout_body"])
            with self.subTest(sequence=sequence):
                self.assertNotIn(r"\begin{hlafixedpage}", rendered)
                self.assertNotIn(r"\HLAFixedBlock", rendered)
                self.assertNotIn(r"\HLAAPIToken{\HLAAPIToken", rendered)
                self.assertNotIn("IEEE Std 1516.1-2025", rendered)
        for sequence in range(416, 422):
            rendered = _modern_api_manifest_page(by_sequence[sequence]["layout_body"])
            with self.subTest(manifest_sequence=sequence):
                self.assertNotIn(r"\begin{hlafixedpage}", rendered)
                self.assertIn(r"\begin{RLCodeBlock}", rendered)

    def test_protocol_narrative_has_rule_grammar_and_selectable_message_tokens(self) -> None:
        blocks = json.loads(
            (DOC_ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        by_sequence = {item["sequence"]: item for item in blocks}
        for sequence in (395, 396, 397, 398, 399, 400, 401, 403, 408):
            rendered = _modern_protocol_prose_page(by_sequence[sequence]["layout_body"])
            with self.subTest(sequence=sequence):
                self.assertNotIn(r"\begin{hlafixedpage}", rendered)
                self.assertNotIn(r"\HLAFixedBlock", rendered)
                self.assertIn(r"\begin{HLAProtocolFlowPage}", rendered)
        protocol = _modern_protocol_prose_page(by_sequence[397]["layout_body"])
        self.assertIn(r"\HLAProtocolRule{a)}{", protocol)
        self.assertIn(r"\HLAAPIToken{HLA_CALL_REQUEST}", protocol)
        overview = _modern_protocol_prose_page(by_sequence[395]["layout_body"])
        self.assertIn(r"\HLAProtocolBullet{", overview)
        self.assertNotIn("HLA_CALL_RE- ", protocol)

    def test_known_source_surface_defects_are_corrected_in_generated_pages(self) -> None:
        model = load_document_model(DOC_ROOT, HLA_SOURCE)
        source = source_profile_for_document("hla-1516.1-2025")
        blocks = json.loads(
            (DOC_ROOT / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        by_sequence = {item["sequence"]: item for item in blocks}

        figure3 = _semanticize_visible_surfaces(
            by_sequence[40]["layout_body"],
            next(item for item in model.content_blocks if item.sequence == 40),
            model,
            source,
        )
        figure3 = _modern_statechart_reflow_page(
            figure3,
            sequence=40,
            figure_number=3,
            caption="Federate lifetime",
            input_name="state-machine-federate-lifetime.pdf",
        )
        self.assertNotIn("infrastructure.After", figure3)
        self.assertNotIn(
            r"\SemanticContentBlockProseConnectServiceInfrastructureText After",
            figure3,
        )

        fdd = _semanticize_visible_surfaces(
            by_sequence[47]["layout_body"],
            next(item for item in model.content_blocks if item.sequence == 47),
            model,
            source,
        )
        self.assertIn("Directed interaction table (complete)", fdd)
        self.assertNotIn("Directed interation", fdd)

        fom_rules = _semanticize_visible_surfaces(
            by_sequence[48]["layout_body"],
            next(item for item in model.content_blocks if item.sequence == 48),
            model,
            source,
        )
        self.assertNotIn("Comment note", fom_rules)

        protocol_surface = _semanticize_visible_surfaces(
            by_sequence[397]["layout_body"],
            next(item for item in model.content_blocks if item.sequence == 397),
            model,
            source,
        )
        self.assertIn("Exceptions: The Annex D files define", protocol_surface)
        self.assertNotIn("Exceptions: The Annex E files define", protocol_surface)

        annex_a = _semanticize_visible_surfaces(
            by_sequence[414]["layout_body"],
            next(item for item in model.content_blocks if item.sequence == 414),
            model,
            source,
        )
        self.assertIn("Federate Protocol API (see Annex D)", annex_a)
        self.assertNotIn("Federate Protocol API (see Annex E)", annex_a)

        ledger = json.loads(
            (DOC_ROOT / "semantic" / "source-anomaly-ledger.json").read_text(encoding="utf-8")
        )["entries"]
        status = {item["source_id"]: item["review_status"] for item in ledger}
        for source_id in (
            "hla15161-infrastructure-after",
            "hla15161-directed-interation",
            "hla15161-comment-note-contamination",
            "hla15161-annex-a-cross-reference",
        ):
            self.assertEqual(status[source_id], "APPLIED")


if __name__ == "__main__":
    unittest.main()
