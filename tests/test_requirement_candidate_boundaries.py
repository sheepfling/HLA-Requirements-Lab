"""Source candidate extraction must follow sentence boundaries across PDF lines."""

from __future__ import annotations

import unittest
import json
import re
from collections import Counter

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model_records import _load_requirement_candidates
from hla_lab.core.semantic_text import _machine_statement
from hla_lab.core.semantic_model import load_document_model
from hla_lab.publication.export_compliance_bundle import _document
from tests.support import TEST_REPO_ROOT
from tools.migrations.relabel_15161_source_clauses import source_clause_owners
from tools.migrations.repair_15161_shared_sentences import REPAIRS as SHARED_SENTENCE_REPAIRS
from tools.migrations.repair_15161_mom_fragments import REPAIRS as MOM_REPAIRS
from tools.migrations.repair_15161_cross_page import FIRST as CROSS_PAGE_ID
from tools.migrations.repair_15161_java_annex import ADDED as JAVA_ADDED
from tools.migrations.repair_15161_java_annex import PREFIX as JAVA_PREFIX
from tools.migrations.repair_15161_java_annex import REPAIRS as JAVA_REPAIRS
from tools.migrations.repair_15161_reviewed_fragments import ADDED as REVIEWED_ADDED
from tools.migrations.repair_15161_reviewed_fragments import COMPOUND_SPLITS
from tools.migrations.repair_15161_reviewed_fragments import PREFIX as REVIEWED_PREFIX
from tools.migrations.repair_15161_reviewed_fragments import REPAIRS as REVIEWED_REPAIRS


class RequirementCandidateBoundaryTests(unittest.TestCase):
    def test_promoted_requirements_have_closed_statements_and_real_source_spans(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        layouts = {
            block.source.path: block.layout_body.splitlines()
            for block in model.content_blocks
            if block.layout_body
        }
        for requirement in model.requirements:
            with self.subTest(requirement=requirement.id):
                self.assertNotRegex(requirement.statement.rstrip(), r"[:;]$")
                self.assertNotRegex(requirement.statement, r"\d+\.\d+pt")
                if requirement.id.startswith(REVIEWED_PREFIX):
                    self.assertNotIn("content/clauses", requirement.title)
                for source in (requirement.source, *requirement.additional_sources):
                    self.assertIn(source.path, layouts)
                    self.assertGreaterEqual(source.line, 1)
                    self.assertLessEqual(source.end_line or source.line, len(layouts[source.path]))

        duplicates = Counter((item.clause, item.statement) for item in model.requirements)
        self.assertFalse({key: count for key, count in duplicates.items() if count > 1})

    def test_reviewed_fragments_and_added_obligations_retain_source_spans(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        by_id = {item.id: item for item in model.requirements}
        binding_by_id = {item.requirement_id: item for item in model.requirement_api_bindings}
        for suffix, (statement, start, end) in REVIEWED_REPAIRS.items():
            identifier = REVIEWED_PREFIX + suffix
            with self.subTest(requirement=identifier):
                record = by_id[identifier]
                self.assertEqual(record.statement, statement)
                self.assertEqual((record.source.line, record.source.end_line), (start, end))
                self.assertIn(identifier, binding_by_id)
        for suffix, (_, statement, start, end) in REVIEWED_ADDED.items():
            identifier = REVIEWED_PREFIX + suffix
            with self.subTest(requirement=identifier):
                record = by_id[identifier]
                self.assertEqual(record.statement, statement)
                self.assertEqual((record.source.line, record.source.end_line), (start, end))
                self.assertIn(identifier, binding_by_id)

    def test_compound_splits_point_to_the_printed_modal_rule(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        layouts = {
            block.source.path: block.layout_body.splitlines()
            for block in model.content_blocks if block.layout_body
        }
        by_id = {item.id: item for item in model.requirements}
        for base_suffix, pieces in COMPOUND_SPLITS.items():
            for suffix, statement, start, end in pieces:
                identifier = REVIEWED_PREFIX + base_suffix
                if suffix != "base":
                    identifier += "-" + suffix
                with self.subTest(requirement=identifier):
                    record = by_id[identifier]
                    self.assertEqual(record.statement, statement)
                    self.assertEqual((record.source.line, record.source.end_line), (start, end))
                    source_lines = layouts[record.source.path][start - 1:end]
                    self.assertRegex(_machine_statement(" ".join(source_lines), HLA_SOURCE), r"\bshall\b")
    def test_java_annex_obligations_are_complete_and_source_traced(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        by_id = {item.id: item for item in model.requirements}
        binding_by_id = {item.requirement_id: item for item in model.requirement_api_bindings}
        for suffix, (statement, start, end) in JAVA_REPAIRS.items():
            identifier = JAVA_PREFIX + suffix
            with self.subTest(requirement=identifier):
                record = by_id[identifier]
                self.assertEqual(record.statement, statement)
                self.assertEqual((record.source.line, record.source.end_line), (start, end))
                self.assertIn(identifier, binding_by_id)
        for suffix, (_, statement, start, end) in JAVA_ADDED.items():
            identifier = JAVA_PREFIX + suffix
            with self.subTest(requirement=identifier):
                record = by_id[identifier]
                self.assertEqual(record.statement, statement)
                self.assertEqual((record.source.line, record.source.end_line), (start, end))
                self.assertIn(identifier, binding_by_id)

    def test_cross_page_requirement_preserves_both_source_spans_in_bundle(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        requirement = next(item for item in model.requirements if item.id == CROSS_PAGE_ID)
        self.assertEqual(requirement.source.path.rsplit("page-", 1)[-1], "049.tex")
        self.assertEqual(requirement.additional_sources[0].path.rsplit("page-", 1)[-1], "050.tex")
        bundle = _document(model)
        exported = next(item for item in bundle.requirements if item.id == CROSS_PAGE_ID)
        self.assertEqual(len(exported.additional_sources), 1)
        self.assertEqual(exported.additional_sources[0].path, requirement.additional_sources[0].path)

    def test_restore_status_enumeration_traces_continuation_page(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        requirement = next(
            item for item in model.requirements
            if item.id.endswith("04-federation-management-page-079-l158-43")
        )
        self.assertIn("Federate waiting for federation to restore", requirement.statement)
        self.assertEqual(len(requirement.additional_sources), 1)
        self.assertTrue(requirement.additional_sources[0].path.endswith("page-080.tex"))

    def test_table_order_type_introductions_are_reviewed_pointers(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        model = load_document_model(root, HLA_SOURCE)
        candidates = {item.id: item for item in model.requirements if item.extraction == "candidate"}
        self.assertEqual(len(candidates), 2)
        for suffix, table in (("l115-2", "Table 2"), ("l118-3", "Table 3")):
            record = next(item for key, item in candidates.items() if key.endswith("page-181-" + suffix))
            self.assertTrue(record.statement.startswith(table + " illustrates"))
            self.assertEqual(len(record.additional_sources), 1)
            self.assertTrue(record.additional_sources[0].path.endswith("page-181.tex"))
        self.assertEqual(model.requirement_review_counts()["unreviewed"], 0)

    def test_merged_disconnect_id_has_a_canonical_alias(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        aliases = json.loads((root / "semantic/requirement-id-aliases.json").read_text(encoding="utf-8"))["aliases"]
        self.assertIn(
            {
                "alias_id": "requirement-candidate-content-clauses-04-federation-management-page-040-l54-15",
                "canonical_id": "req-federate-disconnect-after-resign",
                "relation": "merged",
                "reason": "Exact duplicate of the authored Disconnect transition requirement; its full printed sentence is retained by the canonical record.",
            },
            aliases,
        )

    def test_escaped_tex_spacing_and_underscores_are_plain_text(self) -> None:
        self.assertEqual(
            _machine_statement(r"The\ Register\ service shall use HLA\_CALLBACK.", HLA_SOURCE),
            "The Register service shall use HLA_CALLBACK.",
        )

    def test_promoted_candidates_follow_visible_source_headings(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        owners = source_clause_owners(root)
        requirements = json.loads((root / "semantic/requirements.json").read_text(encoding="utf-8"))["requirements"]
        for record in requirements:
            if not record["id"].startswith(
                ("requirement-candidate-content-clauses-", "requirement-source-refinement-")
            ):
                continue
            owner = owners.get((record["source"]["path"], record["source"]["line"]))
            if owner is None:
                continue
            with self.subTest(requirement=record["id"]):
                self.assertEqual(record["clause"], owner)

    def test_page_48_rejection_cases_are_atomic_and_traced(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        requirements = json.loads((root / "semantic/requirements.json").read_text(encoding="utf-8"))["requirements"]
        bindings = json.loads((root / "semantic/api-requirement-bindings.json").read_text(encoding="utf-8"))["bindings"]
        by_id = {record["id"]: record for record in requirements}
        bindings_by_id = {}
        for binding in bindings:
            bindings_by_id.setdefault(binding["requirement_id"], []).append(binding)
        cases = [identifier for identifier in by_id if identifier.startswith("req-fom-module-reject-")]
        self.assertEqual(len(cases), 7)
        for identifier in cases:
            with self.subTest(requirement=identifier):
                record = by_id[identifier]
                self.assertEqual(record["clause"], "4.1.4.1")
                self.assertTrue(record["statement"].endswith("."))
                self.assertEqual(record["statement"].count("shall"), 1)
                self.assertEqual({row["status"] for row in bindings_by_id[identifier]}, {"matched"})
                self.assertEqual({row["language"] for row in bindings_by_id[identifier]}, {"cpp", "java"})

    def test_reviewed_shared_sentence_obligations_are_atomic(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        requirements = json.loads((root / "semantic/requirements.json").read_text(encoding="utf-8"))["requirements"]
        bindings = json.loads((root / "semantic/api-requirement-bindings.json").read_text(encoding="utf-8"))["bindings"]
        by_id = {record["id"]: record for record in requirements}
        bindings_by_id = {}
        for binding in bindings:
            bindings_by_id.setdefault(binding["requirement_id"], []).append(binding)
        for suffix, (statement, start, end) in SHARED_SENTENCE_REPAIRS.items():
            identifier = "requirement-candidate-content-clauses-" + suffix
            with self.subTest(requirement=identifier):
                record = by_id[identifier]
                self.assertEqual(record["statement"], statement)
                self.assertEqual((record["source"]["line"], record["source"]["end_line"]), (start, end))
                self.assertEqual(len(re.findall(r"\bshall\b", statement)), 1)
                self.assertIn(identifier, bindings_by_id)

    def test_mom_list_fragments_are_complete_and_traced(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        requirements = json.loads((root / "semantic/requirements.json").read_text(encoding="utf-8"))["requirements"]
        bindings = json.loads((root / "semantic/api-requirement-bindings.json").read_text(encoding="utf-8"))["bindings"]
        by_page = {record["id"].rsplit("page-", 1)[-1]: record for record in requirements if "page-" in record["id"]}
        binding_by_id = {record["requirement_id"]: record for record in bindings}
        for suffix, (statement, start, end) in MOM_REPAIRS.items():
            if any(key.endswith(suffix) for key in REVIEWED_REPAIRS):
                continue  # A later reviewed repair replaces this initial MOM reconstruction.
            with self.subTest(requirement=suffix):
                record = by_page[suffix]
                self.assertEqual(record["statement"], statement)
                self.assertEqual((record["source"]["line"], record["source"]["end_line"]), (start, end))
                self.assertTrue(statement.endswith((".", ":")))
                self.assertIn(record["id"], binding_by_id)

    def test_second_shall_on_next_source_line_stays_in_same_passage(self) -> None:
        root = TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"
        candidates = {item.id: item for item in _load_requirement_candidates(root, HLA_SOURCE)}
        prefix = "requirement-candidate-content-clauses-04-federation-management-page-048-"
        first = candidates[prefix + "l6-1"]
        self.assertIn("A user-extended MIM may be provided", first.statement)
        self.assertTrue(first.statement.endswith("standard MIM automatically."))
        self.assertEqual((first.source.line, first.source.end_line), (6, 14))
        self.assertEqual(first.clause, "4.1.4")
        self.assertNotIn(prefix + "l12-3", candidates)

        guarded = candidates[prefix + "l21-6"]
        self.assertTrue(guarded.statement.startswith("Additional FOM modules may be provided"))
        self.assertEqual(guarded.source.line, 15)
        self.assertTrue(guarded.statement.endswith("compliant FOM module."))

        passage = candidates[prefix + "l33-10"]
        self.assertIn("The RTI shall consider only the FDD", passage.statement)
        self.assertTrue(passage.statement.endswith("current FOM."))
        self.assertEqual((passage.source.line, passage.source.end_line), (33, 56))
        self.assertEqual(passage.clause, "4.1.4.1")

        # Navigation bookmarks for later headings are emitted at the top of
        # a physical page. Visible service headings own the following text.
        enable_result = candidates[
            "requirement-candidate-content-clauses-08-time-management-page-190-l64-15"
        ]
        disable_service = candidates[
            "requirement-candidate-content-clauses-08-time-management-page-190-l103-25"
        ]
        self.assertEqual(enable_result.clause, "8.3.4")
        self.assertEqual(disable_service.clause, "8.4")


if __name__ == "__main__":
    unittest.main()
