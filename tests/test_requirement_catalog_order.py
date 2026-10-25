"""Consumer-facing ordering and alias contracts for all HLA editions."""

from __future__ import annotations

import json
import unittest

from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.publication.export_compliance_bundle import _document
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
DOCUMENTS = (
    "hla-1516-2010",
    "hla-1516.1-2010",
    "hla-1516.2-2010",
    "hla-1516-2025",
    "hla-1516.1-2025",
    "hla-1516.2-2025",
)


class RequirementCatalogOrderTests(unittest.TestCase):
    def test_portable_ordinals_follow_clause_and_source_order_for_both_editions(self) -> None:
        for document_name in DOCUMENTS:
            root = ROOT / "topics" / "ieee" / document_name
            model = load_hla_document_model(root)
            bundle = _document(model)
            with self.subTest(document=document_name):
                self.assertEqual(
                    [item.ordinal for item in bundle.requirements],
                    list(range(1, len(bundle.requirements) + 1)),
                )
                self.assertEqual(
                    [item.id for item in bundle.requirements],
                    [item.id for item in model.ordered_requirements()],
                )

    def test_aliases_point_to_live_canonical_records(self) -> None:
        for document_name in DOCUMENTS:
            path = (
                ROOT
                / "topics"
                / "ieee"
                / document_name
                / "semantic"
                / "requirement-id-aliases.json"
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            requirement_ids = {
                item["id"]
                for item in json.loads(
                    (path.parent / "requirements.json").read_text(encoding="utf-8")
                )["requirements"]
            }
            aliases = payload["aliases"]
            self.assertEqual(len({item["alias_id"] for item in aliases}), len(aliases))
            self.assertTrue(
                all(
                    item["alias_id"] not in requirement_ids
                    and item["canonical_id"] in requirement_ids
                    and item["alias_id"] != item["canonical_id"]
                    for item in aliases
                )
            )


if __name__ == "__main__":
    unittest.main()
