"""Acceptance tests for the hierarchy-first publication contract."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.publication.publication_contract import (
    PublicationProfile,
    default_publication_profile,
    load_publication_profile,
    publication_destination,
)
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
FIXTURE_ROOT = ROOT / "topics" / "fixture" / "non-hla-demo-2025"
FIXTURE_PROFILE = FIXTURE_ROOT / "fixture_profile.py"
HLA_PROFILE = (
    ROOT / "topics" / "ieee" / "hla-semantic-derivative-2025" / "semantic" / "publication.json"
)


def _load_fixture_source() -> object:
    spec = importlib.util.spec_from_file_location("m25_fixture_profile", FIXTURE_PROFILE)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load fixture profile: {FIXTURE_PROFILE}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PublicationContractTests(unittest.TestCase):
    def test_hla_profile_has_canonical_order_and_projection_contracts(self) -> None:
        profile = load_publication_profile(HLA_PROFILE)

        self.assertEqual(profile.profile_id, "hla-semantic-derivative-2025")
        self.assertEqual(
            tuple(item.id for item in profile.sections),
            (
                "scope",
                "concepts",
                "normative",
                "operations",
                "state-logic",
                "tables",
                "traceability",
            ),
        )
        self.assertEqual(
            tuple(item.id for item in profile.documents),
            ("hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025"),
        )
        self.assertEqual(profile.section("normative").projection_id, "normative")
        self.assertEqual(profile.projection("traceability").output, "annex")
        self.assertEqual(profile.projection("normative").renderer, "normative")
        self.assertEqual(
            publication_destination(profile.profile_id, "normative"),
            "hla-semantic-derivative-2025:normative",
        )

    def test_profile_validation_rejects_noncanonical_section_order(self) -> None:
        profile = default_publication_profile(("fixture",))
        payload = profile.model_dump(mode="json")
        payload["sections"][1]["order"] = 9

        with self.assertRaises(ValueError):
            PublicationProfile.model_validate(payload)

    def test_generator_emits_contract_and_hierarchy_driven_outline(self) -> None:
        source = _load_fixture_source()
        model = load_document_model(FIXTURE_ROOT, source.DEMO_SOURCE)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "semantic"
            derivative = generate_derivative((model,), output)
            contract = json.loads(
                (output / "publication-contract.json").read_text(encoding="utf-8")
            )
            outline = (output / "publication-outline.tex").read_text(encoding="utf-8")
            derivative_text = derivative.read_text(encoding="utf-8")

        self.assertEqual(contract["profile_id"], "generic-semantic-publication")
        self.assertEqual(
            [item["order"] for item in contract["sections"]],
            list(range(1, len(contract["sections"]) + 1)),
        )
        self.assertIn("generic-semantic-publication:concepts", outline)
        self.assertIn("non-hla-demo-2025", outline)
        self.assertIn(r"\input{output/semantic/publication-outline}", derivative_text)


if __name__ == "__main__":
    unittest.main()
