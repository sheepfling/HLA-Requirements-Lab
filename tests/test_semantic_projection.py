"""semantic-projection semantic-prose and faithful/derivative mutation contracts."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.generation.semantic_generation import generate
from hla_lab.traceability.semantic_authority import validate_authority

REPO_ROOT = Path(__file__).resolve().parents[1]
ALL_ROOTS = tuple(sorted((REPO_ROOT / "topics" / "ieee").glob("hla-1516*/")))
ROOTS = {
    name: REPO_ROOT / "topics" / "ieee" / name
    for name in ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025")
}


def _copy_without_generated(source_root: Path, destination: Path) -> None:
    shutil.copytree(
        source_root,
        destination,
        ignore=shutil.ignore_patterns("output", "build", "dist", "review-artifacts"),
    )


def _mutate_layout_block(root: Path, block_id: str, old: str, new: str) -> None:
    path = root / "semantic" / "content-blocks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    for block in payload["content_blocks"]:
        if block["id"] != block_id:
            continue
        body = block.get("layout_body") or ""
        if old not in body:
            raise AssertionError(f"mutation target {old!r} is absent from {block_id}")
        block["layout_body"] = body.replace(old, new)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    raise AssertionError(f"missing content block {block_id}")


class SemanticProjectionTests(unittest.TestCase):
    def test_surface_records_are_recovered_behind_thin_page_adapters(self) -> None:
        expected = {
            "hla-1516-2025": (4, 0, 6, 0),
            "hla-1516.1-2025": (0, 17, 45, 92),
            "hla-1516.2-2025": (0, 0, 2, 89),
        }
        for name, root in ROOTS.items():
            with self.subTest(document=name):
                model = load_document_model(root, HLA_SOURCE)
                self.assertEqual(
                    (
                        len(model.references),
                        len(model.figures),
                        len(model.notes),
                        len(model.tables),
                    ),
                    expected[name],
                )
                page_files = (
                    tuple((root / "content").rglob("*-page-*.tex"))
                    if name == "hla-1516.1-2025"
                    else tuple((root / "sections" / "semantic").rglob("page-*.tex"))
                    if name == "hla-1516.2-2025"
                    else ()
                )
                self.assertTrue(
                    all(
                        path.read_text(encoding="utf-8").count(
                            r"\input{output/semantic/content-block-"
                        )
                        == 1
                        for path in page_files
                    )
                )

    def test_authority_declares_visible_prose_surface_records(self) -> None:
        report = validate_authority(
            ALL_ROOTS,
            REPO_ROOT / "data" / "semantic" / "authority.json",
            check_generated=False,
        )
        self.assertTrue(report.passed, report.failures)
        counts = {(item.document, item.surface): item.records for item in report.surfaces}
        self.assertEqual(counts[("hla-1516-2025", "references")], 4)
        self.assertEqual(counts[("hla-1516.1-2025", "figures")], 17)
        self.assertEqual(counts[("hla-1516.2-2025", "tables")], 89)

    def test_faithful_generation_macroizes_reference_figure_and_table_payloads(self) -> None:
        targets = (
            ("hla-1516-2025", "content-B-context-001", "SemanticReferenceBibliographyOneText"),
            ("hla-1516.1-2025", "content-15161-page-040", "SemanticFigureFigureThreeCaption"),
            (
                "hla-1516.2-2025",
                "content-15162-page-035",
                "SemanticTableMFourPZeroThreeFiveTZeroOneCaption",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            for name, block_id, expected_macro in targets:
                root = ROOTS[name]
                output = Path(temporary) / f"{name}-faithful"
                generate(
                    GenerationRequest(
                        root=root,
                        output=output,
                        source=HLA_SOURCE,
                        dialect=HLA_LATEX_DIALECT,
                        content_block_ids=(block_id,),
                    )
                )
                block_text = (output / f"content-block-{block_id}.tex").read_text(encoding="utf-8")
                self.assertIn(f"\\{expected_macro}", block_text)

    def test_caption_and_reference_mutations_reach_faithful_and_derivative(self) -> None:
        mutations = (
            (
                "hla-1516-2025",
                "content-B-context-001",
                r"IEEE Std 1730\HLAStandardMark-2022",
                "semantic-projection reference mutation sentinel",
                "reference-bibliography-1",
            ),
            (
                "hla-1516.1-2025",
                "content-15161-page-040",
                "Lifetime of a federate",
                "semantic-projection figure caption mutation sentinel",
                "figure-figure-3",
            ),
            (
                "hla-1516.2-2025",
                "content-15162-page-035",
                "Table 1—OMT metadata descriptions",
                "semantic-projection table caption mutation sentinel",
                "table-record-m4.p035.t01",
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            for name, block_id, old, sentinel, record_file in mutations:
                with self.subTest(document=name):
                    mutated_root = workspace / f"{name}-mutated"
                    _copy_without_generated(ROOTS[name], mutated_root)
                    _mutate_layout_block(mutated_root, block_id, old, sentinel)
                    model = load_document_model(mutated_root, HLA_SOURCE)
                    faithful = workspace / f"{name}-faithful"
                    generate(
                        GenerationRequest(
                            root=mutated_root,
                            output=faithful,
                            source=HLA_SOURCE,
                            dialect=HLA_LATEX_DIALECT,
                            content_block_ids=(block_id,),
                        )
                    )
                    derivative = workspace / f"{name}-derivative"
                    generate_derivative(
                        load_hla_corpus((mutated_root,)).documents,
                        derivative,
                    )
                    faithful_text = (faithful / f"content-block-{block_id}.tex").read_text(
                        encoding="utf-8"
                    )
                    record_text = next(
                        path.read_text(encoding="utf-8")
                        for path in faithful.glob(f"{record_file}-data.tex")
                    )
                    derivative_text = (derivative / "derivative.tex").read_text(encoding="utf-8")
                    self.assertIn(sentinel, faithful_text + record_text)
                    self.assertIn(sentinel, derivative_text)
                    self.assertTrue(model.references or model.figures or model.tables)


if __name__ == "__main__":
    unittest.main()
