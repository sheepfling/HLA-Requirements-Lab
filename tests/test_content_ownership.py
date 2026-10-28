"""Complete typed content ownership for the 1516.1 and 1516.2 tranche."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.semantic_generation import generate
from hla_lab.traceability.semantic_authority import load_authority
from tests.support import TEST_REPO_ROOT

REPO_ROOT = TEST_REPO_ROOT
ROOTS = MappingProxyType(
    {
        "hla-1516.1-2025": REPO_ROOT / "topics" / "ieee" / "hla-1516.1-2025",
        "hla-1516.2-2025": REPO_ROOT / "topics" / "ieee" / "hla-1516.2-2025",
    }
)


class ContentOwnershipTests(unittest.TestCase):
    def test_both_documents_have_typed_page_ownership(self) -> None:
        expected_pages = {"hla-1516.1-2025": 435, "hla-1516.2-2025": 122}
        for document_id, root in ROOTS.items():
            model = load_document_model(root, HLA_SOURCE)
            if document_id == "hla-1516.1-2025":
                page_files = tuple((root / "content").rglob("*-page-*.tex"))
                self.assertEqual(len(model.requirements), 2014)
                self.assertEqual(len(model.requirement_reviews), 12)
                self.assertEqual(len(model.definitions), 161)
                self.assertEqual(len(model.tables), 92)
                self.assertEqual(sum(len(item.cells) for item in model.tables), 5159)
                self.assertEqual(len(model.table_families), 46)
            else:
                page_files = tuple((root / "sections" / "semantic").rglob("page-*.tex"))
                self.assertEqual(len(model.definitions), 83)
                self.assertEqual(len(model.requirements), 340)
                self.assertEqual(len(model.requirement_reviews), 0)
                self.assertTrue(all(item.extraction == "explicit" for item in model.requirements))
                self.assertTrue(all(item.clause_id for item in model.requirements))
                self.assertEqual(len(model.tables), 89)
                self.assertEqual(sum(len(item.cells) for item in model.tables), 2840)
                self.assertGreater(len(model.table_families), 0)
            self.assertEqual(len(page_files), expected_pages[document_id])
            self.assertGreater(len(model.content_blocks), 0)
            self.assertGreater(len(model.content_elements), 0)
            self.assertTrue(
                all(
                    path.read_text(encoding="utf-8").count("\\input{output/semantic/content-block-")
                    == 1
                    for path in page_files
                )
            )
            self.assertTrue(
                all(
                    "\\HLASourcePage" not in path.read_text(encoding="utf-8") for path in page_files
                )
            )

    def test_content_element_and_block_references_are_closed(self) -> None:
        for root in ROOTS.values():
            model = load_document_model(root, HLA_SOURCE)
            block_ids = {item.id for item in model.content_blocks}
            element_ids = {item.id for item in model.content_elements}
            self.assertEqual(len(element_ids), len(model.content_elements))
            self.assertTrue(all(item.block_id in block_ids for item in model.content_elements))
            self.assertTrue(
                all(set(item.element_ids) <= element_ids for item in model.content_blocks)
            )
            self.assertTrue(
                all(
                    item.layout_body is not None or item.id.startswith("prose-")
                    for item in model.content_blocks
                )
            )

    def test_authority_manifest_declares_both_content_surfaces(self) -> None:
        authority = load_authority(REPO_ROOT / "data" / "semantic" / "authority.json")
        for document_id in ROOTS:
            document = next(item for item in authority.documents if item.document_id == document_id)
            surface_ids = {item.id for item in document.surfaces}
            self.assertIn("content-blocks", surface_ids)
            self.assertIn("content-elements", surface_ids)
        document = next(
            item
            for item in load_authority(REPO_ROOT / "data" / "semantic" / "authority.json").documents
            if item.document_id == "hla-1516.2-2025"
        )
        self.assertTrue(
            {"definitions", "requirements", "requirement-reviews", "table-families"}
            <= {item.id for item in document.surfaces}
        )

    def test_15162_prose_projection_has_no_layout_geometry(self) -> None:
        model = load_document_model(ROOTS["hla-1516.2-2025"], HLA_SOURCE)
        prose = tuple(
            item for item in model.content_elements if item.kind in {"paragraph", "list-item"}
        )
        self.assertTrue(prose)
        self.assertTrue(
            all(
                not any(token in item.text for token in ("HLAClause", "HLATable", "resizebox"))
                for item in prose
            )
        )
        self.assertTrue(all(item.text.strip() for item in prose))

    def test_content_element_mutation_reaches_each_document_build_input(self) -> None:
        for root in ROOTS.values():
            with self.subTest(document=root.name), tempfile.TemporaryDirectory() as temporary:
                copy_root = Path(temporary) / root.name
                shutil.copytree(root, copy_root)
                source_path = copy_root / "semantic" / "content-elements.json"
                payload = json.loads(source_path.read_text(encoding="utf-8"))
                target = payload["content_elements"][0]
                target["text"] = f"content-ownership mutation sentinel {root.name}"
                source_path.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                model = load_document_model(copy_root, HLA_SOURCE)
                output = Path(temporary) / "output"
                generate(
                    GenerationRequest(
                        root=copy_root,
                        output=output,
                        source=HLA_SOURCE,
                        dialect=HLA_LATEX_DIALECT,
                        content_block_ids=(model.content_blocks[0].id,),
                        content_element_ids=(model.content_elements[0].id,),
                    )
                )
                generated = next(output.glob("content-element-*-data.tex"))
                self.assertIn(
                    f"content-ownership mutation sentinel {root.name}",
                    generated.read_text(encoding="utf-8"),
                )


if __name__ == "__main__":
    unittest.main()
