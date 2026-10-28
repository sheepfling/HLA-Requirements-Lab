"""Replay semantic state traces against a generic state-machine model."""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Set as AbstractSet
from typing import Annotated, Literal

from pydantic import Field

from hla_lab.core.semantic_model import (
    SemanticRecord,
    StateMachine,
    StateTrace,
    TraceStep,
    Transition,
)

__all__ = ["TraceReplayResult", "TraceReplayStep", "replay_trace"]


class TraceReplayStep(SemanticRecord):
    """The observed result of replaying one trace step."""

    step_id: Annotated[str, Field(min_length=1)]
    status: Literal["passed", "failed", "blocked"]
    transition_id: str | None = None
    state_before: str | None = None
    state_after: str | None = None
    reason: str = ""


class TraceReplayResult(SemanticRecord):
    """A serializable state-trace replay result."""

    trace_id: Annotated[str, Field(min_length=1)]
    machine_id: Annotated[str, Field(min_length=1)]
    status: Literal["passed", "failed", "blocked"]
    final_state_id: str | None = None
    steps: tuple[TraceReplayStep, ...] = ()
    errors: tuple[str, ...] = ()


def _event_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _blocked(trace: StateTrace, reason: str) -> TraceReplayResult:
    return TraceReplayResult(
        trace_id=trace.id,
        machine_id=trace.machine_id,
        status="blocked",
        errors=(reason,),
    )


def _step_result(
    step: TraceStep,
    *,
    status: Literal["passed", "failed", "blocked"],
    transition_id: str | None,
    state_before: str | None,
    state_after: str | None,
    reason: str = "",
) -> TraceReplayStep:
    return TraceReplayStep(
        step_id=step.id,
        status=status,
        transition_id=transition_id,
        state_before=state_before,
        state_after=state_after,
        reason=reason,
    )


def _failed_step(
    step: TraceStep,
    before: str | None,
    transition_id: str | None,
    reason: str,
    *,
    state_after: str | None,
    status: Literal["failed", "blocked"] = "failed",
) -> tuple[TraceReplayStep, str]:
    result = _step_result(
        step,
        status=status,
        transition_id=transition_id,
        state_before=before,
        state_after=state_after,
        reason=reason,
    )
    return result, f"{step.id}: {reason}"


def _candidate_transitions(
    machine: StateMachine,
    step: TraceStep,
    current: str | None,
) -> tuple[Transition, ...]:
    return tuple(
        item
        for item in machine.transitions
        if (item.source_state is None or item.source_state == current)
        and _event_key(item.event) == _event_key(step.event)
    )


def _resolve_step_transition(
    machine: StateMachine,
    step: TraceStep,
    before: str | None,
    transitions: Mapping[str, Transition],
) -> tuple[Transition | None, TraceReplayStep | None, str | None]:
    if step.source_state is not None and before != step.source_state:
        reason = f"expected source {step.source_state}, observed {before}"
        result, error = _failed_step(step, before, step.transition_id, reason, state_after=before)
        return None, result, error
    transition = transitions.get(step.transition_id) if step.transition_id else None
    if step.transition_id is not None and transition is None:
        reason = f"transition {step.transition_id} is not defined by the machine"
        result, error = _failed_step(step, before, step.transition_id, reason, state_after=before)
        return None, result, error
    if transition is None:
        candidates = _candidate_transitions(machine, step, before)
        if len(candidates) != 1:
            reason = (
                f"event {step.event!r} matched {len(candidates)} transitions; "
                "provide transition_id for a deterministic trace"
            )
            result, error = _failed_step(step, before, None, reason, state_after=before)
            return None, result, error
        transition = candidates[0]
    return transition, None, None


def _validate_resolved_transition(
    step: TraceStep,
    before: str | None,
    transition: Transition,
) -> tuple[TraceReplayStep | None, str | None]:
    if transition.source_state is not None and transition.source_state != before:
        reason = f"transition source {transition.source_state} does not match {before}"
        return _failed_step(step, before, transition.id, reason, state_after=before)
    if step.event and _event_key(step.event) != _event_key(transition.event):
        reason = f"expected event {step.event!r}, observed {transition.event!r}"
        return _failed_step(step, before, transition.id, reason, state_after=before)
    if step.target_state is not None and transition.target_state != step.target_state:
        reason = f"expected target {step.target_state}, observed {transition.target_state}"
        return _failed_step(
            step, before, transition.id, reason, state_after=transition.target_state
        )
    if transition.target_state is None:
        reason = "transition has no explicit target state"
        return _failed_step(
            step,
            before,
            transition.id,
            reason,
            state_after=before,
            status="blocked",
        )
    return None, None


def _initial_replay_state(
    machine: StateMachine,
    trace: StateTrace,
    states: AbstractSet[str],
) -> tuple[str | None, str | None]:
    current = trace.initial_state_id
    if current is None and machine.initial_state_ids:
        current = machine.initial_state_ids[0]
    if current is not None and current not in states:
        return current, f"initial state {current} is not defined by the machine"
    return current, None


def replay_trace(machine: StateMachine, trace: StateTrace) -> TraceReplayResult:
    """Replay ``trace`` and verify source, transition, event, and target contracts.

    A trace may identify a transition directly, which is the preferred form
    for diagram-derived records whose event labels are descriptive rather than
    canonical API event names.  Event-only steps are accepted when exactly one
    transition from the current state matches the normalized event label.
    """
    if trace.machine_id != machine.id:
        return _blocked(trace, f"trace targets {trace.machine_id}, not {machine.id}")
    if not trace.steps:
        return _blocked(trace, "trace has no replay steps")
    states = {item.id for item in machine.states}
    transitions = {item.id: item for item in machine.transitions}
    current, initial_error = _initial_replay_state(machine, trace, states)
    if initial_error is not None:
        return _blocked(trace, initial_error)
    results: list[TraceReplayStep] = []
    errors: list[str] = []
    for step in trace.steps:
        before = current
        transition, failure, error = _resolve_step_transition(machine, step, before, transitions)
        if failure is not None:
            results.append(failure)
            errors.append(error or "")
            break
        assert transition is not None
        failure, error = _validate_resolved_transition(step, before, transition)
        if failure is not None:
            results.append(failure)
            errors.append(error or "")
            break
        current = transition.target_state
        results.append(
            _step_result(
                step,
                status="passed",
                transition_id=transition.id,
                state_before=before,
                state_after=current,
            )
        )
    if (
        not errors
        and trace.expected_final_state is not None
        and current != trace.expected_final_state
    ):
        errors.append(f"expected final state {trace.expected_final_state}, observed {current}")
    status: Literal["passed", "failed", "blocked"]
    if errors:
        status = "blocked" if results and results[-1].status == "blocked" else "failed"
    else:
        status = "passed"
    return TraceReplayResult(
        trace_id=trace.id,
        machine_id=machine.id,
        status=status,
        final_state_id=current,
        steps=tuple(results),
        errors=tuple(errors),
    )
