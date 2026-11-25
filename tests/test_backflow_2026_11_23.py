"""Regression coverage for the 2026-11-23 Requirements Lab backflow queue."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
DOC_15162 = ROOT / "topics/ieee/hla-1516.2-2025"
SEMANTIC_15162 = DOC_15162 / "semantic"


def _payload(path: Path, collection: str) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))[collection]


def _by_id(records: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    return {str(item["id"]): item for item in records}


class HLA15162BackflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.requirements = _by_id(_payload(SEMANTIC_15162 / "requirements.json", "requirements"))
        cls.elements = _by_id(
            _payload(SEMANTIC_15162 / "content-elements.json", "content_elements")
        )
        cls.blocks = _by_id(_payload(SEMANTIC_15162 / "content-blocks.json", "content_blocks"))

    def test_annex_c7_continuations_inherit_the_correct_heading_and_source_elements(self) -> None:
        duplicate_id = "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l10-2"
        unique_id = "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l18-4"
        duplicate = self.requirements[duplicate_id]
        unique = self.requirements[unique_id]
        self.assertEqual((duplicate["clause"], duplicate["clause_id"]), ("C.7", "clause-C.7"))
        self.assertEqual((unique["clause"], unique["clause_id"]), ("C.7", "clause-C.7"))
        self.assertIn(
            duplicate_id,
            self.elements["content-element-content-15162-page-113-list-item-004"]["record_ids"],
        )
        self.assertIn(
            unique_id,
            self.elements["content-element-content-15162-page-113-paragraph-007"]["record_ids"],
        )

    def test_page_40_object_class_rules_are_complete_and_separated(self) -> None:
        hierarchy_id = "requirement-candidate-sections-semantic-clause-4a-page-040-l18-3"
        marker_id = "requirement-candidate-sections-semantic-clause-4a-page-040-l30-6"
        hierarchy = self.requirements[hierarchy_id]
        markers = self.requirements[marker_id]
        self.assertIn("right-most column", hierarchy["statement"])
        self.assertNotIn("naming conventions", hierarchy["statement"])
        self.assertIn("PublishSubscribe", markers["statement"])
        self.assertIn("Neither", markers["statement"])
        companion_ids = (
            hierarchy_id + "-naming",
            marker_id + "-fom-classification",
            marker_id + "-instance-eligibility",
        )
        for record_id in companion_ids:
            self.assertIn(record_id, self.requirements)
            self.assertIn(record_id, self.blocks["content-15162-page-040"]["record_ids"])
        self.assertIn(
            "federation", self.requirements[marker_id + "-fom-classification"]["statement"]
        )
        self.assertIn(
            "registered", self.requirements[marker_id + "-instance-eligibility"]["statement"]
        )

    def test_interaction_parameter_table_cross_page_text_is_complete(self) -> None:
        p52_id = "requirement-candidate-sections-semantic-clause-4b-page-052-l54-10"
        p53_id = "requirement-candidate-sections-semantic-clause-4b-page-053-l35-1"
        p52 = self.requirements[p52_id]
        p53 = self.requirements[p53_id]
        self.assertIn("infrared signature", p52["statement"])
        self.assertIn("specified characteristics", p52["statement"])
        self.assertNotIn("include a", p52["statement"][-30:])
        self.assertEqual((p53["clause"], p53["clause_id"]), ("4.6.2", "clause-4.6.2"))
        self.assertEqual(
            p53["statement"],
            "All interaction classes shall be included in this table so that transportation "
            "and order can be specified.",
        )
        self.assertIn(p52_id, self.blocks["content-15162-page-053"]["record_ids"])
        self.assertIn(p53_id, self.blocks["content-15162-page-053"]["record_ids"])

    def test_fixed_record_candidates_are_owned_by_subclause_4_14_10_1(self) -> None:
        ids = (
            "requirement-candidate-sections-semantic-clause-4c-page-080-l69-6",
            "requirement-candidate-sections-semantic-clause-4c-page-080-l73-7",
            "requirement-candidate-sections-semantic-clause-4c-page-081-l36-2",
        )
        for record_id in ids:
            with self.subTest(record_id=record_id):
                self.assertEqual(self.requirements[record_id]["clause_id"], "clause-4.14.10.1")
                self.assertIn("4.14.10.1", self.requirements[record_id]["coverage_note"])

    def test_variant_record_continuations_have_complete_statements_and_trace_links(self) -> None:
        encoding_id = "requirement-candidate-sections-semantic-clause-4c-page-077-l86-9"
        table_id = "requirement-candidate-sections-semantic-clause-4c-page-077-l54-1"
        encoding = self.requirements[encoding_id]
        table_format = self.requirements[table_id]
        self.assertIn("Record data should be interpreted first", encoding["statement"])
        self.assertTrue(encoding["statement"].endswith("field\u2019s data type."))
        self.assertTrue(
            any(item["path"].endswith("page-078.tex") for item in encoding["additional_sources"])
        )
        self.assertTrue(
            any(
                item["path"].endswith("page-076.tex") for item in table_format["additional_sources"]
            )
        )
        self.assertIn(encoding_id, self.blocks["content-15162-page-078"]["record_ids"])
        self.assertIn(table_id, self.blocks["content-15162-page-076"]["record_ids"])

    def test_source_anomalies_have_mapped_dispositions(self) -> None:
        root_15161 = ROOT / "topics/ieee/hla-1516.1-2025/semantic"
        ledger_15161 = json.loads(
            (root_15161 / "source-anomaly-ledger.json").read_text(encoding="utf-8")
        )
        ledger_15162 = json.loads(
            (SEMANTIC_15162 / "source-anomaly-ledger.json").read_text(encoding="utf-8")
        )
        entries = {
            item["related_issue_id"]: item
            for item in (*ledger_15161["entries"], *ledger_15162["entries"])
            if item.get("related_issue_id")
        }
        expected = {"RL-399", "RL-403", "RL-407", "RL-420", "RL-441", "RL-443", "RL-444", "RL-456"}
        self.assertTrue(expected.issubset(entries))
        for issue_id in expected:
            with self.subTest(issue_id=issue_id):
                self.assertIn(issue_id, entries)
                self.assertEqual(entries[issue_id]["review_status"], "DISPOSITIONED")
                self.assertTrue(entries[issue_id]["resolution"])
                self.assertTrue(entries[issue_id]["mapping_effect"])

        by_id = self.requirements
        self.assertIn("UserSuppliedTag=60", entries["RL-399"]["rendered_text"])
        self.assertIn("addVariant", entries["RL-420"]["mapping_effect"])
        self.assertIn(
            "spaces",
            by_id["requirement-candidate-sections-semantic-clauses-5-6-page-091-l54-7"][
                "coverage_note"
            ],
        )
        switch_rule = by_id[
            "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l50-9"
        ]["statement"]
        self.assertIn("a warning shall be provided to the user", switch_rule)
        self.assertIn("the merge shall fail", switch_rule)
        note_rule = by_id["requirement-candidate-sections-semantic-annexes-d-h-page-114-l42-5"][
            "statement"
        ]
        self.assertEqual(
            note_rule,
            "In the OMT XML Schema, note labels and note references shall be prefixed with an "
            "underscore to ensure that the labeling conforms to the NCName data type convention.",
        )
        self.assertIn(
            "NA",
            by_id["requirement-candidate-sections-semantic-clauses-5-6-page-093-l78-15"][
                "coverage_note"
            ],
        )


if __name__ == "__main__":
    unittest.main()
