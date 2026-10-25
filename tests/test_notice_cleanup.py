"""Prevent vendored source notices from leaking into Lab-authored editions.

The repository may retain source-faithful downloads and official FOM material
as provenance inputs.  Those inputs must not accidentally reintroduce
publisher notices, participant boilerplate, or source-license language into
the authored semantic and presentation outputs.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path, PureWindowsPath
from types import MappingProxyType

from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.generation.reflowable_renderer import _clean_content_text
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
TOPIC_ROOT = ROOT / "topics" / "ieee"
DOCUMENTS = (
    "hla-1516-2010",
    "hla-1516.1-2010",
    "hla-1516.2-2010",
    "hla-1516-2025",
    "hla-1516.1-2025",
    "hla-1516.2-2025",
)

LEGACY_NOTICE_MARKERS = (
    "IMPORTANT NOTICE: This standard is not intended",
    "This IEEE document is made available for use subject to important notices",
    "IEEE Standards documents are made available for use subject to important notices",
    "Important Notices and Disclaimers Concerning IEEE Standards Documents",
    "sent to SA ballot",
    "submitted to the IEEE-SA Standards Board for approval",
    "working group acknowledges the following",
    "Interface Specification Editors",
    "Object Model Template Specification Editors",
    "Drafting Group",
    "individual balloting committee voted",
    "IEEE-SA Standards Board approved this standard",
    "The Institute of Electrical and Electronics Engineers",
    "3 Park Avenue",
    "445 Hoes Lane",
    "All rights reserved",
    "reprinted with permission",
    "IEEE hereby grants",
    "No part of this publication",
    "IEEE publications are available",
    "trademarks owned by The Institute",
    "trademarks of the Institute",
    "source permission",
    "standard license",
)

OMITTED_SEMANTIC_BLOCKS = MappingProxyType(
    {
        "hla-1516-2010": {
            "content-frontmatter-01-external-cover-tex",
            "content-frontmatter-03-title-page-tex",
            "content-frontmatter-04-copyright-abstract-tex",
            "content-frontmatter-05-ieee-notices-tex",
            "content-frontmatter-07-updating-participants-tex",
            "content-frontmatter-08-participants-ballot-tex",
            "content-frontmatter-09-standards-board-tex",
        },
        "hla-1516.1-2010": {
            "content-frontmatter-title-tex",
            "content-frontmatter-publication-tex",
            "content-frontmatter-standards-notice-tex",
            "content-frontmatter-introduction-tex",
            "content-frontmatter-participants-tex",
        },
        "hla-1516-2025": {
            "content-front-matter-context-001",
            "content-front-matter-context-002",
            "content-front-matter-normative-001",
            "content-front-matter-normative-002",
            "content-front-matter-context-003",
            "content-front-matter-context-004",
        },
        "hla-1516.1-2025": {
            "content-15161-page-003",
            "content-15161-page-004",
            "content-15161-page-005",
            "content-15161-page-006",
            "content-15161-page-007",
            "content-15161-page-008",
        },
        "hla-1516.2-2025": {
            "content-15162-page-002",
            "content-15162-page-003",
            "content-15162-page-004",
            "content-15162-page-005",
            "content-15162-page-006",
            "content-15162-page-007",
            "content-15162-page-008",
            "content-15162-page-009",
            "content-15162-page-010",
        },
    }
)


def _authored_files(document_root: Path):
    ignored = {"build", "dist", "output", "__pycache__"}
    for path in document_root.rglob("*"):
        if path.is_file() and not ignored.intersection(path.parts):
            yield path


class NoticeCleanupTests(unittest.TestCase):
    def test_legacy_notice_markers_are_absent_from_authored_inputs(self) -> None:
        findings: list[str] = []
        for document in DOCUMENTS:
            for path in _authored_files(TOPIC_ROOT / document):
                text = path.read_text(encoding="utf-8", errors="ignore")
                for marker in LEGACY_NOTICE_MARKERS:
                    if marker in text:
                        findings.append(f"{path.relative_to(ROOT)} contains {marker!r}")
        self.assertEqual(findings, [])

    def test_derivative_models_exclude_source_frontmatter_and_preambles(self) -> None:
        residue = (
            "They can also be obtained on request from IEEE",
            "standards.ieee.org/IPR/disclaimers.html",
            "IEEE Standard for\\\\ Modeling and Simulation",
        )
        for document in ("hla-1516-2010", "hla-1516.2-2010", "hla-1516.1-2010"):
            model = load_hla_document_model(TOPIC_ROOT / document)
            visible = [
                *(item.text for item in model.content_blocks),
                *(item.text for item in model.content_elements),
            ]
            self.assertFalse(
                any(marker in text for marker in residue for text in visible),
                document,
            )
            frontmatter = [
                item.text
                for item in (*model.content_blocks, *model.content_elements)
                if PureWindowsPath(item.source.path).parts[0] == "frontmatter"
            ]
            self.assertTrue(all(not text.strip() for text in frontmatter), document)

    def test_omitted_notice_blocks_are_removed_from_semantic_source(self) -> None:
        for document, block_ids in OMITTED_SEMANTIC_BLOCKS.items():
            path = TOPIC_ROOT / document / "semantic" / "content-blocks.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            blocks = {str(block["id"]): block for block in payload["content_blocks"]}
            for block_id in block_ids:
                self.assertNotIn(block_id, blocks)

    def test_semantic_block_and_element_references_are_closed(self) -> None:
        for document in DOCUMENTS:
            semantic_root = TOPIC_ROOT / document / "semantic"
            blocks = json.loads(
                (semantic_root / "content-blocks.json").read_text(encoding="utf-8")
            )["content_blocks"]
            elements = json.loads(
                (semantic_root / "content-elements.json").read_text(encoding="utf-8")
            )["content_elements"]
            block_ids = {str(block["id"]) for block in blocks}
            element_ids = {str(element["id"]) for element in elements}
            self.assertEqual(
                [
                    (block["id"], element_id)
                    for block in blocks
                    for element_id in block.get("element_ids", [])
                    if str(element_id) not in element_ids
                ],
                [],
            )

            self.assertEqual(
                [
                    element["id"]
                    for element in elements
                    if str(element.get("block_id", "")) not in block_ids
                ],
                [],
            )

    def test_shared_derived_text_cleanup_removes_editorial_source_residue(self) -> None:
        source = (
            "Directed interation table (complete). "
            "(Comment note - description is not part of FDD nor should it be and thus "
            "cannot be used for rejection.)"
        )
        cleaned = _clean_content_text(source)
        self.assertEqual(cleaned, "Directed interaction table (complete).")

    def test_15162_2025_presentation_identity_is_lab_neutral(self) -> None:
        root = TOPIC_ROOT / "hla-1516.2-2025"
        base_style = (root / "ieee-hla-base.sty").read_text(encoding="utf-8")
        self.assertNotIn("IEEE Std 1516.2-2025", base_style)
        self.assertNotIn(
            "IEEE Standard for Modeling and Simulation (M\\&S) High Level Architecture",
            base_style,
        )

        payload = json.loads(
            (root / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )
        title_block = next(
            block for block in payload["content_blocks"] if block["id"] == "content-15162-page-013"
        )
        self.assertNotIn("IEEE Standard for", title_block["layout_body"])
        self.assertIn("HLA Requirements Lab", title_block["layout_body"])

    def test_15162_2010_presentation_identity_is_lab_neutral(self) -> None:
        root = TOPIC_ROOT / "hla-1516.2-2010"
        style = (root / "ieee1516style.sty").read_text(encoding="utf-8")
        self.assertNotIn("IEEE Std 1516.2-2010", style)
        self.assertNotIn(
            "IEEE STANDARD FOR MODELING AND SIMULATION (M\\&S)",
            style,
        )
        self.assertIn("HLA REQUIREMENTS LAB", style)


if __name__ == "__main__":
    unittest.main()
