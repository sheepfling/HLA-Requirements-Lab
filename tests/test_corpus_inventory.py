"""Contract tests for inventory corpus inventory through table-inventory OMT migration."""

from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.corpus.corpus_inventory import CorpusInventory, build_inventory

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOTS = tuple(
    REPO_ROOT / "topics" / "ieee" / name
    for name in ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025")
)
INVENTORY_ROOTS = tuple(
    REPO_ROOT / "topics" / "ieee" / name
    for name in (
        "hla-1516-2010",
        "hla-1516.1-2010",
        "hla-1516.2-2010",
        "hla-1516-2025",
        "hla-1516.1-2025",
        "hla-1516.2-2025",
    )
)


class CorpusInventoryTests(unittest.TestCase):
    def test_inventory_is_source_controlled_and_complete(self) -> None:
        path = REPO_ROOT / "data" / "semantic" / "inventory.json"
        inventory = CorpusInventory.model_validate(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(
            {item.document_id for item in inventory.documents},
            {
                "hla-1516-2010",
                "hla-1516.1-2010",
                "hla-1516.2-2010",
                "hla-1516-2025",
                "hla-1516.1-2025",
                "hla-1516.2-2025",
            },
        )
        self.assertGreaterEqual(inventory.totals["clause"], 1800)
        self.assertEqual(inventory.totals.get("status:unclassified", 0), 0)
        # content-ownership closes the last HLA requirement queue; the inventory remains
        # source-controlled even when no migration work is outstanding.
        self.assertFalse(inventory.migration_queue)
        rebuilt = build_inventory(
            INVENTORY_ROOTS,
            REPO_ROOT / "data" / "release" / "documents.json",
        )
        self.assertEqual(
            {item.document_id for item in inventory.documents},
            {item.document_id for item in rebuilt.documents},
        )
        self.assertEqual(inventory.totals, rebuilt.totals)
        self.assertEqual(inventory.migration_queue, rebuilt.migration_queue)

    def test_1516_requirements_are_promoted_and_grouped(self) -> None:
        model = load_document_model(ROOTS[0], HLA_SOURCE)
        self.assertEqual(len(model.requirements), 20)
        self.assertTrue(all(item.extraction == "explicit" for item in model.requirements))
        groups = Counter(item.semantic_group_id for item in model.requirements)
        self.assertEqual(len(groups), 10)
        self.assertTrue(all(count == 2 for count in groups.values()))
        content_blocks = json.loads(
            (ROOTS[0] / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )["content_blocks"]
        for path in sorted(
            (ROOTS[0] / "sections" / "semantic" / "final-body").glob("page-3[2-8].tex")
        ):
            relative = path.relative_to(ROOTS[0]).as_posix()
            text = next(
                item["layout_body"] for item in content_blocks if item["source"]["path"] == relative
            )
            statements = re.findall(r"\\HLANormativeRuleStatement\{([^}]*)\}", text)
            self.assertTrue(statements)
            self.assertTrue(all(value.startswith("\\SemanticRequirement") for value in statements))

    def test_all_transitions_have_explicit_coverage_dispositions(self) -> None:
        model = load_document_model(ROOTS[1], HLA_SOURCE)
        self.assertEqual(sum(len(machine.transitions) for machine in model.state_machines), 282)
        self.assertEqual(len(model.transition_coverage), 282)
        self.assertEqual(model.transitions_missing_coverage(), ())
        self.assertEqual(
            model.transition_coverage_counts(),
            {"mapped": 282, "not-applicable": 0, "deferred": 0, "unclassified": 0},
        )

    def test_all_omt_tables_belong_to_families(self) -> None:
        model = load_document_model(ROOTS[2], HLA_SOURCE)
        family_table_ids = [
            table_id for family in model.table_families for table_id in family.table_ids
        ]
        self.assertEqual(len(model.tables), 89)
        self.assertEqual(len(family_table_ids), 89)
        self.assertEqual(set(family_table_ids), {table.id for table in model.tables})
        self.assertEqual(sum(len(table.cells) for table in model.tables), 2840)
        self.assertTrue(
            all(table.continued_from is None or table.logical_id for table in model.tables)
        )


if __name__ == "__main__":
    unittest.main()
