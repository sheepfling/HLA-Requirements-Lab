"""cross-reference semantic table ownership and cross-reference contracts."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
from hla_lab.core.semantic_model import (
    CrossReference,
    DocumentModel,
    SourceRef,
    load_document_model,
)
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.generation.semantic_generation import generate
from tests.support import TEST_REPO_ROOT

REPO_ROOT = TEST_REPO_ROOT
FRAMEWORK = REPO_ROOT / "topics" / "ieee" / "hla-1516-2025"
OMT = REPO_ROOT / "topics" / "ieee" / "hla-1516.2-2025"
SERVICES = REPO_ROOT / "topics" / "ieee" / "hla-1516.1-2025"


class CrossReferenceContractTests(unittest.TestCase):
    def test_cross_references_are_typed_and_resolved(self) -> None:
        model = load_document_model(FRAMEWORK, HLA_SOURCE)
        self.assertGreaterEqual(len(model.cross_references), 161)
        self.assertTrue({item.kind for item in model.cross_references} >= {"definition"})
        self.assertTrue(
            all(item.target_document_id == model.document_id for item in model.cross_references)
        )
        self.assertTrue(
            all(
                item.target_record_id in model.semantic_record_ids()
                for item in model.cross_references
            )
        )
        self.assertTrue(
            all(not item.label.startswith("Semantic record ") for item in model.cross_references)
        )
        self.assertIn("accuracy", {item.label for item in model.cross_references})

    def test_all_three_documents_have_projected_tables_definitions_and_links(self) -> None:
        expected = {
            "hla-1516-2025": (161, 0, 0),
            "hla-1516.1-2025": (161, 92, 46),
            "hla-1516.2-2025": (83, 89, 80),
        }
        for document_id, (definition_count, table_count, family_count) in expected.items():
            model = load_document_model(REPO_ROOT / "topics" / "ieee" / document_id, HLA_SOURCE)
            self.assertEqual(len(model.definitions), definition_count, document_id)
            self.assertEqual(len(model.tables), table_count, document_id)
            self.assertEqual(len(model.table_families), family_count, document_id)
            self.assertGreater(len(model.cross_references), 0, document_id)
            self.assertTrue(
                all(
                    item.target_record_id in model.semantic_record_ids()
                    for item in model.cross_references
                ),
                document_id,
            )
            self.assertTrue(
                all(
                    table.id
                    in {
                        table_id for family in model.table_families for table_id in family.table_ids
                    }
                    for table in model.tables
                ),
                document_id,
            )

    def test_tables_have_bidirectional_family_ownership_and_cells_are_addressable(self) -> None:
        model = load_document_model(OMT, HLA_SOURCE)
        self.assertEqual((len(model.tables), len(model.table_families)), (89, 80))
        self.assertEqual(sum(len(table.cells) for table in model.tables), 2840)
        self.assertTrue(all(table.family_id for table in model.tables))
        self.assertTrue(
            all(
                cell.id in model.semantic_record_ids()
                for table in model.tables
                for cell in table.cells
            )
        )
        self.assertEqual(sum(table.continuation for table in model.tables), 8)

    def test_faithful_and_derivative_outputs_emit_resolved_links(self) -> None:
        model = load_document_model(FRAMEWORK, HLA_SOURCE)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            faithful = output / "faithful"
            generate(
                GenerationRequest(
                    root=FRAMEWORK,
                    output=faithful,
                    source=HLA_SOURCE,
                    dialect=HLA_LATEX_DIALECT,
                    content_element_ids=(model.cross_references[0].owner_id,),
                )
            )
            data = "\n".join(
                path.read_text(encoding="utf-8")
                for path in faithful.glob("cross-reference-*-data.tex")
            )
            self.assertIn("TargetRecordID", data)
            self.assertIn("Label", data)
            self.assertIn("accuracy", data)

            derivative = output / "derivative"
            generate_derivative((model,), derivative)
            derivative_text = (derivative / "derivative.tex").read_text(encoding="utf-8")
            self.assertIn(r"\hyperlink{hla-1516-2025:def-accuracy}{accuracy}", derivative_text)
            self.assertNotIn("Semantic record definition-", derivative_text)

    def test_definition_term_mutation_reaches_cross_reference_data_and_derivative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / FRAMEWORK.name
            shutil.copytree(
                FRAMEWORK,
                root,
                ignore=shutil.ignore_patterns("output", "build", "dist", "review-artifacts"),
            )
            path = root / "semantic" / "definitions.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            for definition in payload["definitions"]:
                if definition["id"] == "def-accuracy":
                    definition["term"] = "cross-reference accuracy sentinel"
                    break
            else:
                self.fail("missing def-accuracy")
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

            model = load_document_model(root, HLA_SOURCE)
            cross_reference = next(
                item for item in model.cross_references if item.target_record_id == "def-accuracy"
            )
            self.assertEqual(cross_reference.label, "cross-reference accuracy sentinel")
            faithful = Path(temporary) / "faithful"
            generate(
                GenerationRequest(
                    root=root,
                    output=faithful,
                    source=HLA_SOURCE,
                    dialect=HLA_LATEX_DIALECT,
                    content_element_ids=(cross_reference.owner_id,),
                )
            )
            self.assertIn(
                "cross-reference accuracy sentinel",
                "\n".join(
                    path.read_text(encoding="utf-8")
                    for path in faithful.glob("cross-reference-*-data.tex")
                ),
            )
            derivative = Path(temporary) / "derivative"
            generate_derivative((model,), derivative)
            self.assertIn(
                r"\hyperlink{hla-1516-2025:def-accuracy}{cross-reference accuracy sentinel}",
                (derivative / "derivative.tex").read_text(encoding="utf-8"),
            )

    def test_layout_table_mutation_reaches_table_projection_and_derivative(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / SERVICES.name
            shutil.copytree(
                SERVICES,
                root,
                ignore=shutil.ignore_patterns("output", "build", "dist", "review-artifacts"),
            )
            path = root / "semantic" / "content-blocks.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            for block in payload["content_blocks"]:
                layout_body = block.get("layout_body") or ""
                if "Table 1---Service descriptions" in layout_body:
                    block["layout_body"] = layout_body.replace(
                        "Table 1---Service descriptions", "Table 1---cross-reference table sentinel"
                    )
                    break
            else:
                self.fail("missing recovered Table 1 layout surface")
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )

            model = load_document_model(root, HLA_SOURCE)
            table = next(item for item in model.tables if item.number == "1")
            self.assertIn("cross-reference table sentinel", table.title)
            faithful = Path(temporary) / "faithful"
            generate(
                GenerationRequest(
                    root=root,
                    output=faithful,
                    source=HLA_SOURCE,
                    dialect=HLA_LATEX_DIALECT,
                    table_family_ids=None,
                )
            )
            self.assertIn(
                "cross-reference table sentinel",
                (faithful / "table-family-table-family-table-1-data.tex").read_text(
                    encoding="utf-8"
                ),
            )
            derivative = Path(temporary) / "derivative"
            generate_derivative((model,), derivative)
            self.assertIn(
                "cross-reference table sentinel",
                (derivative / "derivative.tex").read_text(encoding="utf-8"),
            )

    def test_invalid_cross_reference_target_is_rejected(self) -> None:
        model = load_document_model(FRAMEWORK, HLA_SOURCE)
        bad = CrossReference(
            id="xref-invalid",
            owner_id=model.cross_references[0].owner_id,
            target_document_id=model.document_id,
            target_record_id="missing-record",
            label="missing",
            source=SourceRef(path="test", line=1),
        )
        payload = model.model_dump(mode="json")
        payload["cross_references"] = [bad.model_dump(mode="json")]
        with self.assertRaises(ValueError):
            DocumentModel.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
