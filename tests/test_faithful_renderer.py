"""Tests for data-driven faithful-layout entrypoint generation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE, HLA_SOURCE_2010
from hla_lab.core.semantic_model import ContentBlock, DocumentModel, SourceRef, load_document_model
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.generation.faithful_renderer import (
    build_faithful_layout_projection,
    load_faithful_layout_profile,
    render_faithful_body,
)
from hla_lab.generation.semantic_generation import generate

ROOT = Path(__file__).resolve().parents[1]


def _block(identifier: str, sequence: int, source_path: str) -> ContentBlock:
    return ContentBlock(
        id=identifier,
        kind="context",
        text=identifier,
        sequence=sequence,
        source=SourceRef(path=source_path, line=sequence + 1),
    )


class FaithfulRendererTests(unittest.TestCase):
    def test_projection_groups_adapter_paths_and_uses_semantic_sequence(self) -> None:
        model = DocumentModel(
            document_id="fixture-2025",
            clauses=(),
            definitions=(),
            requirements=(),
            content_blocks=(
                _block("late", 8, "pages/page-008.tex"),
                _block("shared-b", 4, "pages/page-004.tex"),
                _block("early", 2, "pages/page-002.tex"),
                _block("shared-a", 3, "pages/page-004.tex"),
            ),
        )

        projection = build_faithful_layout_projection(model)

        self.assertEqual(
            tuple(item.source_path for item in projection.entries),
            ("pages/page-002.tex", "pages/page-004.tex", "pages/page-008.tex"),
        )
        self.assertEqual(projection.entries[1].sequence, 3)
        self.assertEqual(projection.entries[1].content_block_ids, ("shared-a", "shared-b"))
        rendered = render_faithful_body(projection)
        self.assertLess(rendered.find("page-002"), rendered.find("page-004"))
        self.assertLess(rendered.find("page-004"), rendered.find("page-008"))

    def test_projection_rejects_non_local_or_non_tex_layout_sources(self) -> None:
        model = DocumentModel(
            document_id="fixture-2025",
            clauses=(),
            definitions=(),
            requirements=(),
            content_blocks=(_block("invalid", 1, "../outside.tex"),),
        )

        with self.assertRaises(ValueError):
            build_faithful_layout_projection(model)

    def test_hla_entrypoints_consume_one_generated_faithful_body(self) -> None:
        document_roots = (
            ROOT / "topics" / "ieee" / "hla-1516-2025",
            ROOT / "topics" / "ieee" / "hla-1516.1-2025",
            ROOT / "topics" / "ieee" / "hla-1516.2-2025",
        )
        for root in document_roots:
            with self.subTest(document=root.name):
                main = (root / "main.tex").read_text(encoding="utf-8")
                self.assertEqual(main.count(r"\input{output/semantic/faithful-body}"), 1)
                self.assertNotIn(r"\input{content/clauses/", main)
                self.assertNotIn(r"\input{sections/semantic/", main)

    def test_generation_emits_a_faithful_body_and_projection(self) -> None:
        root = ROOT / "topics" / "ieee" / "hla-1516-2025"
        model = load_document_model(root, HLA_SOURCE)
        profile = load_faithful_layout_profile(root / "semantic" / "faithful-layout.json")
        with self.subTest(document=root.name), tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "semantic"
            generated = generate(
                GenerationRequest(
                    root=root,
                    output=output,
                    source=HLA_SOURCE,
                    dialect=HLA_LATEX_DIALECT,
                    content_block_ids=tuple(item.id for item in model.content_blocks),
                    include_faithful_body=True,
                    faithful_layout_profile=profile,
                )
            )
            projection = build_faithful_layout_projection(generated.model, profile=profile)
            self.assertEqual(
                (output / "faithful-layout.json").read_text(encoding="utf-8"),
                projection.model_dump_json(indent=2) + "\n",
            )
            self.assertEqual(
                (output / "faithful-body.tex").read_text(encoding="utf-8"),
                render_faithful_body(projection) + "\n",
            )

    def test_hla_layout_profiles_declare_all_nonprose_boundaries(self) -> None:
        expected_entries = {
            "hla-1516-2025": 38,
            "hla-1516.1-2025": 437,
            "hla-1516.2-2025": 122,
        }
        for name, expected_count in expected_entries.items():
            root = ROOT / "topics" / "ieee" / name
            model = load_document_model(root, HLA_SOURCE)
            profile = load_faithful_layout_profile(root / "semantic" / "faithful-layout.json")
            projection = build_faithful_layout_projection(model, profile=profile)
            with self.subTest(document=name):
                self.assertEqual(len(projection.entries), expected_count)
                self.assertTrue(
                    all((root / item.source_path).is_file() for item in projection.entries)
                )
        profile_1516 = load_faithful_layout_profile(
            ROOT / "topics" / "ieee" / "hla-1516-2025" / "semantic" / "faithful-layout.json"
        )
        model_1516 = load_document_model(ROOT / "topics" / "ieee" / "hla-1516-2025", HLA_SOURCE)
        rendered = render_faithful_body(
            build_faithful_layout_projection(model_1516, profile=profile_1516)
        )
        self.assertEqual(rendered.count(r"\HLAStartSemanticPages"), 4)
        self.assertEqual(rendered.count(r"\HLAEndSemanticPages"), 4)
        self.assertIn(r"\HLAInstallContentsLinks", rendered)

    def test_release_faithful_products_use_the_trimmed_core_body_policy(self) -> None:
        manifest = json.loads(
            (ROOT / "data" / "release" / "documents.json").read_text(encoding="utf-8")
        )
        faithful = [item for item in manifest["projects"] if item["kind"] == "faithful"]
        self.assertEqual(len(faithful), 6)
        for item in faithful:
            with self.subTest(document=item["id"]):
                self.assertEqual(
                    item["build"]["faithful_body_exclude_path_parts"],
                    ["frontmatter", "front-matter"],
                )
                main = (ROOT / item["root"] / "main.tex").read_text(encoding="utf-8")
                self.assertNotIn(r"\HLACoverPage", main)
                self.assertNotIn(r"\HLABackCoverPage", main)
                self.assertNotIn(r"\input{frontmatter/cover}", main)

    def test_trimmed_projection_excludes_front_matter_adapters(self) -> None:
        for name in (
            "hla-1516-2010",
            "hla-1516.2-2010",
            "hla-1516.1-2010",
            "hla-1516-2025",
            "hla-1516.1-2025",
            "hla-1516.2-2025",
        ):
            root = ROOT / "topics" / "ieee" / name
            source = HLA_SOURCE_2010 if name == "hla-1516.1-2010" else HLA_SOURCE
            model = load_document_model(root, source)
            profile = load_faithful_layout_profile(root / "semantic" / "faithful-layout.json")
            projection = build_faithful_layout_projection(
                model,
                profile=profile,
                exclude_path_parts=("frontmatter", "front-matter"),
            )
            with self.subTest(document=name):
                self.assertTrue(projection.entries)
                self.assertTrue(
                    all(
                        not {"frontmatter", "front-matter"}.intersection(
                            Path(entry.source_path).parts
                        )
                        for entry in projection.entries
                    )
                )


if __name__ == "__main__":
    unittest.main()
