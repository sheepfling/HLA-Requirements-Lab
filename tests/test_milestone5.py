"""Repeatable build-integration checks for Milestone 5."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.export_state_machine import export
from scripts.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
from scripts.promote_requirement import promote_requirement
from scripts.semantic_dashboard import build_dashboard
from scripts.semantic_generation import generate
from scripts.semantic_model import (
    Clause,
    DocumentModel,
    Requirement,
    SourceRef,
    State,
    StateMachine,
    StateMachineFile,
    Transition,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_ROOTS = tuple(
    REPO_ROOT / "topics" / "ieee" / name
    for name in (
        "hla-1516-2025",
        "hla-1516.1-2025",
        "hla-1516.2-2025",
    )
)


class Milestone5Tests(unittest.TestCase):
    def test_semantic_dashboard_reports_reviewed_and_candidate_coverage(self) -> None:
        report = build_dashboard(DOCUMENT_ROOTS)
        self.assertEqual(report["totals"]["documents"], 3)
        self.assertEqual(report["totals"]["explicit_requirements"], 9)
        self.assertEqual(report["totals"]["unresolved_references"], 0)
        lifecycle = next(
            item for item in report["documents"] if item["document"] == "hla-1516.1-2025"
        )
        self.assertEqual(lifecycle["requirements"]["explicit"], 7)
        self.assertEqual(
            lifecycle["requirements"]["explicit_transition_requirements_with_reviewed_links"], 7
        )
        self.assertEqual(lifecycle["state_machines"]["transitions_unmapped"], 276)

    def test_requirement_promotion_updates_reciprocal_source_records(self) -> None:
        source = SourceRef(path="source.tex", line=1)
        candidate = Requirement(
            id="candidate-requirement",
            title="Candidate requirement",
            statement="The service shall transition.",
            kind="detailed",
            clause="1",
            extraction="candidate",
            source=source,
        )
        machine = StateMachine(
            id="machine",
            title="Machine",
            clause_id="clause-1",
            states=(
                State(id="s0", label="Initial", source=source),
                State(id="s1", label="Final", source=source),
            ),
            transitions=(
                Transition(
                    id="machine.transition",
                    source_state="s0",
                    event="Transition",
                    target_state="s1",
                    clause_id="clause-1",
                    source=source,
                ),
            ),
        )
        model = DocumentModel(
            document_id="fixture",
            clauses=(
                Clause(
                    id="clause-1",
                    number="1",
                    title="Clause 1",
                    parent_id=None,
                    level=1,
                    source=source,
                ),
            ),
            definitions=(),
            requirements=(candidate,),
            state_machines=(machine,),
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            semantic = root / "semantic"
            semantic.mkdir()
            (semantic / "requirements.json").write_text(
                json.dumps({"schema_version": 1, "requirements": []}), encoding="utf-8"
            )
            (semantic / "machine.json").write_text(
                json.dumps(
                    StateMachineFile(schema_version=2, state_machines=(machine,)).model_dump(
                        mode="json"
                    )
                ),
                encoding="utf-8",
            )
            promoted = promote_requirement(
                root,
                candidate.id,
                model=model,
                transition_ids=("machine.transition",),
                notes="Reviewed fixture link.",
            )
            requirements = json.loads((semantic / "requirements.json").read_text(encoding="utf-8"))
            links = json.loads((semantic / "requirement-links.json").read_text(encoding="utf-8"))
            state_source = json.loads((semantic / "machine.json").read_text(encoding="utf-8"))

        self.assertEqual(promoted.extraction, "explicit")
        self.assertEqual(requirements["requirements"][0]["id"], candidate.id)
        self.assertEqual(links["links"][0]["requirement_id"], candidate.id)
        self.assertEqual(
            state_source["state_machines"][0]["transitions"][0]["requirement_ids"],
            [candidate.id],
        )

    def test_generic_layers_do_not_import_hla_profile(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import sys; import scripts.semantic_model; "
                    "import scripts.semantic_generation; "
                    "assert 'scripts.hla_profile' not in sys.modules"
                ),
            ],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.stdout, "")

    def test_generation_writes_typed_semantic_build_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "stale.tex").write_text("stale", encoding="utf-8")
            model = generate(
                DOCUMENT_ROOTS[0],
                output,
                source=HLA_SOURCE,
                dialect=HLA_LATEX_DIALECT,
                definition_ids=("def-accuracy",),
            )
            manifest = (output / "semantic-manifest.tex").read_text(encoding="utf-8")
            definition = (output / "definition-def-accuracy.tex").read_text(encoding="utf-8")
            data = (output / "definition-def-accuracy-data.tex").read_text(encoding="utf-8")
            index = (output / "semantic-index.tex").read_text(encoding="utf-8")

        self.assertEqual(model.document_id, "hla-1516-2025")
        self.assertFalse((output / "stale.tex").exists())
        self.assertIn(r"\SemanticDocumentID", manifest)
        self.assertIn("semantic-index.tex", manifest)
        self.assertIn("definition-def-accuracy.tex", manifest)
        self.assertIn("definition-def-accuracy-data.tex", manifest)
        self.assertIn(r"\begin{hladefinition}", definition)
        self.assertIn(r"\SemanticDefinitionDefAccuracyText", data)
        self.assertIn(r"\SemanticCanonicalRecordIDs", index)

    def test_generation_writes_migrated_content_block_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            model = generate(
                DOCUMENT_ROOTS[1],
                output,
                source=HLA_SOURCE,
                dialect=HLA_LATEX_DIALECT,
                content_block_ids=("prose-federate-lifetime-initial-state",),
            )
            data = (
                output / "content-block-prose-federate-lifetime-initial-state-data.tex"
            ).read_text(encoding="utf-8")
            manifest = (output / "semantic-manifest.tex").read_text(encoding="utf-8")

        self.assertEqual(len(model.content_blocks), 3)
        self.assertIn(r"\SemanticContentBlockProseFederateLifetimeInitialStateText", data)
        self.assertIn("content-block-prose-federate-lifetime-initial-state-data.tex", manifest)

    def test_generation_writes_migrated_requirement_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            model = generate(
                DOCUMENT_ROOTS[0],
                output,
                source=HLA_SOURCE,
                dialect=HLA_LATEX_DIALECT,
                requirement_ids=("summary-rule-1", "summary-rule-6"),
            )
            first = (output / "requirement-summary-rule-1.tex").read_text(encoding="utf-8")
            first_data = (output / "requirement-summary-rule-1-data.tex").read_text(
                encoding="utf-8"
            )
            manifest = (output / "semantic-manifest.tex").read_text(encoding="utf-8")

        self.assertEqual(
            {item.id for item in model.requirements if item.extraction == "explicit"}
            & {"summary-rule-1", "summary-rule-6"},
            {"summary-rule-1", "summary-rule-6"},
        )
        self.assertIn(r"\HLASummaryRule{summary-rule-1}", first)
        self.assertIn(r"\SemanticRequirementSummaryRule1Statement", first_data)
        self.assertIn("requirement-summary-rule-6-data.tex", manifest)

    def test_generation_writes_omt_table_family_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            model = generate(
                DOCUMENT_ROOTS[2],
                output,
                source=HLA_SOURCE,
                dialect=HLA_LATEX_DIALECT,
                table_family_ids=("omt-object-model-identification",),
            )
            data = (output / "table-family-omt-object-model-identification-data.tex").read_text(
                encoding="utf-8"
            )
            manifest = (output / "semantic-manifest.tex").read_text(encoding="utf-8")

        self.assertEqual(len(model.table_families), 1)
        self.assertIn(r"\SemanticTableM4P037T01Caption", data)
        self.assertIn(r"\SemanticTableM4P038T01Caption", data)
        self.assertIn("table-family-omt-object-model-identification-data.tex", manifest)

    def test_every_main_loads_a_generated_semantic_entrypoint(self) -> None:
        for root in DOCUMENT_ROOTS:
            main = (root / "main.tex").read_text(encoding="utf-8")
            self.assertIn(r"\input{output/semantic/semantic-manifest}", main)
        lifecycle_page = (
            DOCUMENT_ROOTS[1] / "content" / "clauses" / "04-federation-management-page-040.tex"
        ).read_text(encoding="utf-8")
        self.assertIn(
            r"\SemanticRequirementReqFederateConnectBeforeRtiWorkStatement",
            lifecycle_page,
        )
        self.assertIn(
            r"\SemanticContentBlockProseFederateLifetimeInitialStateText",
            lifecycle_page,
        )
        framework_page = (
            DOCUMENT_ROOTS[0] / "sections" / "semantic" / "final-body" / "page-32.tex"
        ).read_text(encoding="utf-8")
        self.assertIn(
            r"\input{output/semantic/requirement-summary-rule-1}",
            framework_page,
        )
        table_page = (
            DOCUMENT_ROOTS[2] / "sections" / "semantic" / "clause-4a" / "page-037.tex"
        ).read_text(encoding="utf-8")
        self.assertIn(r"\SemanticTableM4P037T01Caption", table_page)

    def test_all_document_builders_invoke_semantic_generation(self) -> None:
        for root in DOCUMENT_ROOTS:
            source = (root / "build.py").read_text(encoding="utf-8")
            self.assertIn("semantic_generator=generate_blocks", source)
            self.assertIn('ROOT / "output" / "semantic"', source)

    def test_state_machine_exports_are_deterministic_text_sources(self) -> None:
        model_path = DOCUMENT_ROOTS[1] / "semantic" / "federate-lifetime.json"
        with tempfile.TemporaryDirectory() as temporary:
            paths = export(
                model_path,
                Path(temporary),
                machine_ids=("federate-lifetime",),
            )
            dot = next(path for path in paths if path.suffix == ".dot")
            mermaid = next(path for path in paths if path.suffix == ".mmd")
            dot_text = dot.read_text(encoding="utf-8")
            mermaid_text = mermaid.read_text(encoding="utf-8")

        self.assertIn("digraph", dot_text)
        self.assertIn("Connect", dot_text)
        self.assertIn("stateDiagram-v2", mermaid_text)
        self.assertIn("Connect", mermaid_text)

    def test_generated_exports_and_reviews_are_ignored(self) -> None:
        for path in (
            "output/semantic/semantic-manifest.tex",
            "reviews/example.md",
            "review-artifacts/example.dot",
        ):
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", "--", path],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, path)


if __name__ == "__main__":
    unittest.main()
