"""Acceptance tests for honest IEEE 1516.1 content-extraction closure."""

from __future__ import annotations

import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.traceability.semantic_authority import load_authority

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOT = REPO_ROOT / "topics" / "ieee" / "hla-1516.1-2025"


class ContentClosureTests(unittest.TestCase):
    def test_all_15161_requirement_candidates_are_authoritative(self) -> None:
        model = load_document_model(ROOT, HLA_SOURCE)
        self.assertEqual(len(model.requirements), 1860)
        self.assertTrue(all(item.extraction == "explicit" for item in model.requirements))
        self.assertTrue(all(item.clause_id for item in model.requirements))
        self.assertEqual(model.requirement_reviews, ())
        self.assertEqual(
            model.requirement_review_counts(),
            {
                "deferred": 0,
                "non-normative": 0,
                "layout-only": 0,
                "unreviewed": 0,
            },
        )

    def test_every_transition_has_reciprocal_planned_implementation_coverage(self) -> None:
        model = load_document_model(ROOT, HLA_SOURCE)
        transitions = tuple(
            transition for machine in model.state_machines for transition in machine.transitions
        )
        self.assertEqual(len(transitions), 297)
        self.assertEqual(len(model.implementations), 283)
        self.assertEqual(model.transitions_missing_implementation_mapping(), ())
        self.assertEqual(
            model.transition_coverage_counts(),
            {
                "mapped": 297,
                "not-applicable": 0,
                "deferred": 0,
                "unclassified": 0,
            },
        )
        self.assertTrue(all(item.status == "planned" for item in model.implementations))
        self.assertTrue(all(transition.implementation_ids for transition in transitions))
        self.assertEqual(model.compliance_issues(), ())

    def test_direct_requirement_links_and_prose_ownership_are_closed(self) -> None:
        model = load_document_model(ROOT, HLA_SOURCE)
        links = {(item.requirement_id, item.transition_id) for item in model.requirement_links}
        self.assertTrue(links)
        self.assertTrue(
            all(
                (requirement.id, transition_id) in links
                for requirement in model.requirements
                if requirement.coverage_kind == "transition"
                for transition_id in requirement.transition_ids
            )
        )
        self.assertGreater(
            sum(
                any(item.startswith("requirement-") for item in block.record_ids)
                for block in model.content_blocks
            ),
            0,
        )
        self.assertGreater(
            sum(
                any(item.startswith("requirement-") for item in element.record_ids)
                for element in model.content_elements
            ),
            0,
        )

    def test_authority_manifest_declares_required_surfaces(self) -> None:
        authority = load_authority(REPO_ROOT / "data" / "semantic" / "authority.json")
        document = next(
            item for item in authority.documents if item.document_id == "hla-1516.1-2025"
        )
        surface_ids = {item.id for item in document.surfaces}
        self.assertTrue({"requirements", "requirement-links", "implementations"} <= surface_ids)


if __name__ == "__main__":
    unittest.main()
