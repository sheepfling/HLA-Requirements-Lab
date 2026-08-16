"""Acceptance tests for semantic-surface closure slices."""

from __future__ import annotations

import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_corpus, load_document_model

ROOT = Path(__file__).resolve().parents[1]
HLA_15161 = ROOT / "topics" / "ieee" / "hla-1516.1-2025"
CORPUS_ROOTS = tuple(
    ROOT / "topics" / "ieee" / name
    for name in ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025")
)


class SemanticGraphTests(unittest.TestCase):
    def test_authored_implementation_seams_have_provenance_without_becoming_concrete(self) -> None:
        model = load_document_model(HLA_15161, HLA_SOURCE)

        self.assertEqual(len(model.implementations), 281)
        self.assertTrue(all(item.source is not None for item in model.implementations))
        self.assertTrue(all(item.status == "planned" for item in model.implementations))
        self.assertEqual(
            sum(
                item.source.path == "semantic/implementations.json"
                for item in model.implementations
            ),
            247,
        )

    def test_sequence_messages_remain_explicitly_unlinked_without_invented_transitions(
        self,
    ) -> None:
        corpus = load_corpus(CORPUS_ROOTS, HLA_SOURCE)
        implications = corpus.state_sequence_implications("hla-1516.1-2025")
        sequence_messages = tuple(item for item in implications if item.kind == "sequence-message")

        self.assertEqual(len(sequence_messages), 14)
        self.assertTrue(all(item.relation == "unlinked" for item in sequence_messages))
        self.assertTrue(all(not item.related_transition_ids for item in sequence_messages))
        self.assertTrue(all(item.source is not None for item in sequence_messages))


if __name__ == "__main__":
    unittest.main()
