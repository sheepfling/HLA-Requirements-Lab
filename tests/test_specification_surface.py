"""Specification-facing API, verification, trace, and readiness contracts."""

from __future__ import annotations

import unittest
from pathlib import Path

from hla_lab.core.semantic_model import (
    DocumentModel,
    State,
    StateMachine,
    StateTrace,
    TraceStep,
    Transition,
)
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.traceability.spec_readiness import assess_corpus
from hla_lab.traceability.state_trace import replay_trace

ROOT = Path(__file__).resolve().parents[1]
HLA_ROOT = ROOT / "topics" / "ieee"

class StateTraceReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = StateMachine(
            id="machine",
            title="Machine",
            states=(
                State(id="idle", label="Idle"),
                State(id="ready", label="Ready"),
            ),
            transitions=(
                Transition(
                    id="start",
                    source_state="idle",
                    event="Start",
                    target_state="ready",
                ),
            ),
            initial_state_ids=("idle",),
        )

    def test_transition_id_trace_replays(self) -> None:
        trace = StateTrace(
            id="trace",
            machine_id="machine",
            title="Start",
            steps=(
                TraceStep(
                    id="step",
                    event="Start",
                    source_state="idle",
                    transition_id="start",
                    target_state="ready",
                ),
            ),
            expected_final_state="ready",
        )
        result = replay_trace(self.machine, trace)
        self.assertEqual(result.status, "passed")
        self.assertEqual(result.final_state_id, "ready")

    def test_event_only_trace_rejects_ambiguous_event(self) -> None:
        machine = self.machine.model_copy(
            update={
                "transitions": (
                    *self.machine.transitions,
                    Transition(
                        id="start-again",
                        source_state="idle",
                        event="Start",
                        target_state="ready",
                    ),
                )
            }
        )
        trace = StateTrace(
            id="trace",
            machine_id="machine",
            title="Ambiguous",
            steps=(TraceStep(id="step", event="Start"),),
        )
        result = replay_trace(machine, trace)
        self.assertEqual(result.status, "failed")
        self.assertIn("matched 2 transitions", result.errors[0])

    def test_replay_rejects_unknown_transition(self) -> None:
        trace = StateTrace(
            id="trace",
            machine_id="machine",
            title="Unknown",
            steps=(TraceStep(id="step", transition_id="missing"),),
        )
        result = replay_trace(self.machine, trace)
        self.assertEqual(result.status, "failed")
        self.assertIn("not defined", result.errors[0])

class HlaSurfaceReadinessTests(unittest.TestCase):
    def test_surface_records_round_trip_through_pydantic(self) -> None:
        model = load_hla_document_model(HLA_ROOT / "hla-1516.1-2025")
        restored = DocumentModel.model_validate_json(model.model_dump_json())
        self.assertEqual(len(restored.api_surfaces), len(model.api_surfaces))
        self.assertEqual(len(restored.state_traces), len(model.state_traces))

    def test_surface_references_are_strictly_validated(self) -> None:
        model = load_hla_document_model(HLA_ROOT / "hla-1516.1-2025")
        payload = model.model_dump(mode="json")
        payload["api_surfaces"][0]["transition_ids"] = ["missing-transition"]
        with self.assertRaises(ValueError):
            DocumentModel.model_validate(payload)

    def test_15161_models_have_complete_planned_surface_slots(self) -> None:
        model = load_hla_document_model(HLA_ROOT / "hla-1516.1-2025")
        transitions = {
            transition.id for machine in model.state_machines for transition in machine.transitions
        }
        semantic_surfaces = tuple(
            surface for surface in model.api_surfaces if surface.binding_kind == "semantic"
        )
        self.assertEqual(len(semantic_surfaces), len(model.implementations))
        self.assertTrue(any(surface.binding_kind == "native" for surface in model.api_surfaces))
        self.assertTrue(any(surface.binding_kind == "protocol" for surface in model.api_surfaces))
        self.assertEqual(
            {
                transition_id
                for surface in model.api_surfaces
                for transition_id in surface.transition_ids
            },
            transitions,
        )
        self.assertEqual(
            {machine.id for machine in model.state_machines},
            {trace.machine_id for trace in model.state_traces},
        )
        self.assertTrue(all(surface.owner for surface in model.api_surfaces))
        self.assertTrue(all(test.status == "planned" for test in model.verification_tests))
        transition_id = next(iter(transitions))
        self.assertTrue(model.api_surfaces_for_transition(transition_id))
        requirement_id = model.requirements[0].id
        self.assertTrue(model.verification_tests_for_requirement(requirement_id))
        self.assertTrue(model.state_traces_for_machine(model.state_machines[0].id))

    def test_corpus_readiness_distinguishes_surface_from_code_readiness(self) -> None:
        roots = tuple(
            HLA_ROOT / document_id
            for document_id in (
                "hla-1516-2010",
                "hla-1516.1-2010",
                "hla-1516.2-2010",
                "hla-1516-2025",
                "hla-1516.1-2025",
                "hla-1516.2-2025",
            )
        )
        report = assess_corpus(roots)
        self.assertTrue(report.specification_ready)
        self.assertTrue(report.api_contract_ready)
        self.assertFalse(report.implementation_ready)
        for edition in ("2010", "2025"):
            lifecycle = next(
                item for item in report.documents if item.document_id == f"hla-1516.1-{edition}"
            )
            self.assertEqual(lifecycle.transitions_without_api_surface, ())
            self.assertEqual(lifecycle.machines_without_trace, ())
            self.assertEqual(lifecycle.api_surfaces_without_language, ())
            self.assertEqual(lifecycle.api_surfaces_without_parameters, ())
            self.assertGreater(lifecycle.planned_mapping_count, 0)
            self.assertEqual(lifecycle.concrete_mapping_count, 0)

if __name__ == "__main__":
    unittest.main()
