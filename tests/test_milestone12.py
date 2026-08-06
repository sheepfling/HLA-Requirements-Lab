from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.generate_derivative import generate_derivative
from scripts.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
from scripts.hla_semantic import load_hla_corpus
from scripts.semantic_authority import validate_authority
from scripts.semantic_generation import generate
from scripts.semantic_model import load_document_model

REPO_ROOT = Path(__file__).resolve().parents[1]
ROOTS = tuple(sorted((REPO_ROOT / "topics" / "ieee").glob("hla-1516*/")))


class Milestone12Tests(unittest.TestCase):
    def test_authority_manifest_covers_migrated_surfaces(self) -> None:
        report = validate_authority(
            ROOTS, REPO_ROOT / "data" / "semantic" / "authority.json", check_generated=True
        )
        self.assertTrue(report["passed"], report["failures"])
        self.assertEqual(report["unresolved_references"], [])
        counts = {
            (item["document"], item["surface"]): item["records"] for item in report["surfaces"]
        }
        self.assertEqual(counts[("hla-1516-2025", "definitions")], 161)
        self.assertEqual(counts[("hla-1516-2025", "requirements")], 20)
        self.assertEqual(counts[("hla-1516.1-2025", "content-blocks")], 439)
        self.assertEqual(counts[("hla-1516.1-2025", "requirements")], 1697)
        self.assertEqual(counts[("hla-1516.1-2025", "transition-coverage")], 281)
        self.assertEqual(counts[("hla-1516.1-2025", "implementations")], 281)
        self.assertEqual(counts[("hla-1516.1-2025", "requirement-links")], 32)
        self.assertEqual(counts[("hla-1516.2-2025", "definitions")], 83)
        self.assertEqual(counts[("hla-1516.2-2025", "requirements")], 340)
        self.assertEqual(counts[("hla-1516.2-2025", "content-blocks")], 122)
        self.assertEqual(counts[("hla-1516.2-2025", "content-elements")], 1078)
        self.assertEqual(counts[("hla-1516.2-2025", "table-families")], 80)

    def test_candidate_queue_has_explicit_review_dispositions(self) -> None:
        for root, expected in ((ROOTS[1], 0), (ROOTS[2], 0)):
            model = load_document_model(root, HLA_SOURCE)
            self.assertEqual(model.requirement_review_counts()["deferred"], expected)
            self.assertEqual(model.requirement_review_counts()["unreviewed"], 0)

    def test_1516_definition_pages_consume_generated_inputs(self) -> None:
        directory = ROOTS[0] / "sections" / "semantic" / "definitions"
        texts = [path.read_text(encoding="utf-8") for path in directory.glob("page-*.tex")]
        self.assertTrue(all(r"\begin{hladefinition}" not in text for text in texts))
        content = json.loads(
            (ROOTS[0] / "semantic" / "content-blocks.json").read_text(encoding="utf-8")
        )
        layout_bodies = "\n".join(item["layout_body"] for item in content["content_blocks"])
        inputs = {
            identifier
            for text in (layout_bodies,)
            for identifier in re.findall(r"definition-(def-[^}]+)", text)
        }
        self.assertEqual(len(inputs), 161)

    def test_semantic_mutation_changes_faithful_and_derivative_views(self) -> None:
        """A source-record edit must reach both document products."""
        source_root = ROOTS[0]
        requirement_id = "summary-rule-1"
        changed_statement = "Federations shall expose a semantically generated FOM."
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            mutated_root = workspace / source_root.name
            shutil.copytree(
                source_root,
                mutated_root,
                ignore=shutil.ignore_patterns("output", "build", "dist"),
            )
            requirements_path = mutated_root / "semantic" / "requirements.json"
            payload = json.loads(requirements_path.read_text(encoding="utf-8"))
            for requirement in payload["requirements"]:
                if requirement["id"] == requirement_id:
                    requirement["statement"] = changed_statement
                    requirement["machine_statement"] = changed_statement
                    break
            else:  # pragma: no cover - protects the fixture contract
                self.fail(f"missing fixture requirement: {requirement_id}")
            requirements_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            original_output = workspace / "original-faithful"
            mutated_output = workspace / "mutated-faithful"
            for root, output in ((source_root, original_output), (mutated_root, mutated_output)):
                generate(
                    root,
                    output,
                    source=HLA_SOURCE,
                    dialect=HLA_LATEX_DIALECT,
                    requirement_ids=(requirement_id,),
                )
            original_derivative = workspace / "original-derivative"
            mutated_derivative = workspace / "mutated-derivative"
            generate_derivative(
                load_hla_corpus((source_root,)).documents,
                original_derivative,
            )
            generate_derivative(
                load_hla_corpus((mutated_root,)).documents,
                mutated_derivative,
            )

            original_faithful = (original_output / f"requirement-{requirement_id}.tex").read_text(
                encoding="utf-8"
            )
            mutated_faithful = (mutated_output / f"requirement-{requirement_id}.tex").read_text(
                encoding="utf-8"
            )
            original_derivative_tex = (original_derivative / "derivative.tex").read_text(
                encoding="utf-8"
            )
            mutated_derivative_tex = (mutated_derivative / "derivative.tex").read_text(
                encoding="utf-8"
            )

        self.assertNotEqual(original_faithful, mutated_faithful)
        self.assertIn(changed_statement, mutated_faithful)
        self.assertNotEqual(original_derivative_tex, mutated_derivative_tex)
        self.assertIn(changed_statement, mutated_derivative_tex)

    def test_compliance_json_exposes_stable_review_and_issue_surfaces(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.compliance",
                *(str(root) for root in ROOTS),
                "--json",
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = json.loads(result.stdout)
        self.assertEqual(payload["documents"], [root.name for root in ROOTS])
        self.assertEqual(
            set(payload["requirement_reviews"]),
            {"hla-1516-2025", "hla-1516.1-2025", "hla-1516.2-2025"},
        )
        self.assertIn("issue_counts", payload)


if __name__ == "__main__":
    unittest.main()
