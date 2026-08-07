"""Acceptance tests for the cross-document semantic graph slice."""

from __future__ import annotations

import unittest
from pathlib import Path

from scripts.corpus_graph import (
    CorpusDocumentDescriptor,
    CorpusSemanticGraph,
    build_corpus_graph,
    load_document_metadata,
)
from scripts.semantic_model import (
    Clause,
    ComplianceCorpus,
    CrossReference,
    Definition,
    DocumentModel,
    SourceRef,
)


def _source(path: str, line: int) -> SourceRef:
    return SourceRef(path=path, line=line)


def _document(document_id: str, definition_id: str, *, cross_reference: bool) -> DocumentModel:
    clause = Clause(
        id="clause-1",
        number="1",
        title="Concepts",
        parent_id=None,
        level=1,
        source=_source(f"{document_id}.tex", 1),
    )
    definition = Definition(
        id=definition_id,
        term="Shared Concept",
        text="A concept shared by two editions.",
        clause_id=clause.id,
        source=_source(f"{document_id}.tex", 2),
    )
    references = (
        (
            CrossReference(
                id=f"xref-{document_id}",
                owner_id=definition.id,
                target_document_id="doc-b",
                target_record_id="definition-b",
                label="definition-b",
                kind="definition",
                source=_source(f"{document_id}.tex", 3),
            ),
        )
        if cross_reference
        else ()
    )
    return DocumentModel(
        document_id=document_id,
        clauses=(clause,),
        definitions=(definition,),
        requirements=(),
        cross_references=references,
    )


class Milestone29Tests(unittest.TestCase):
    def test_graph_keeps_explicit_links_separate_from_shared_term_candidates(self) -> None:
        corpus = ComplianceCorpus(
            documents=(
                _document("doc-a", "definition-a", cross_reference=True),
                _document("doc-b", "definition-b", cross_reference=False),
            )
        )
        graph = build_corpus_graph(
            corpus,
            metadata={
                "doc-a": CorpusDocumentDescriptor(
                    document_id="doc-a",
                    title="Edition A",
                    edition="1",
                    relationship="extends",
                    related_document_ids=("doc-b",),
                ),
                "doc-b": CorpusDocumentDescriptor(
                    document_id="doc-b",
                    title="Edition B",
                    edition="1",
                    relationship="standalone",
                ),
            },
        )

        explicit = graph.edges_for("doc-a", "definition-a", cross_document_only=True)
        self.assertTrue(any(item.evidence == "explicit" for item in explicit))
        candidates = graph.shared_term_edges()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].evidence, "candidate")
        self.assertIn("review before", candidates[0].note)
        self.assertEqual(graph.node("doc-a:definition-a").label, "Shared Concept")
        self.assertEqual(graph.documents[0].related_document_ids, ("doc-b",))
        self.assertEqual(
            len(graph.findings_for(kind="duplicate-definition")),
            1,
        )

    def test_hla_metadata_is_source_controlled_and_typed(self) -> None:
        metadata_path = (
            Path(__file__).resolve().parents[1]
            / "topics/ieee/hla-semantic-derivative-2025/semantic/corpus.json"
        )
        metadata = load_document_metadata(metadata_path)

        self.assertEqual(metadata["hla-1516.1-2025"].edition, "2025")
        self.assertEqual(metadata["hla-1516.1-2025"].relationship, "extends")
        self.assertEqual(
            metadata["hla-1516.1-2025"].related_document_ids,
            ("hla-1516-2025",),
        )

    def test_graph_round_trip_preserves_qualified_cross_document_queries(self) -> None:
        corpus = ComplianceCorpus(
            documents=(
                _document("doc-a", "definition-a", cross_reference=True),
                _document("doc-b", "definition-b", cross_reference=False),
            )
        )
        graph = build_corpus_graph(corpus)
        restored = CorpusSemanticGraph.model_validate_json(graph.to_json())

        edges = restored.cross_document_edges("doc-b")
        self.assertTrue(edges)
        self.assertTrue(all("doc-" in item.source_node_id for item in edges))
        self.assertEqual(
            len(restored.edges_for("doc-a", relation="shared-definition-term")),
            1,
        )


if __name__ == "__main__":
    unittest.main()
