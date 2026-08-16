"""Promote annotated HLA 1516.1-2010 TikZ figures into semantic records.

The handoff's native TikZ remains a faithful geometry/layout fixture.  The
stable figure comments (``Fxx-Syy``, ``Fxx-Pyy``, and ``Fxx-Exx``) are parsed
into generic state-machine and graph records so the semantic corpus owns the
meaning and the native source only owns exceptional page geometry.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from hla_lab.core.parsing import line_number
from hla_lab.core.semantic_model import (
    DiagramProvenance,
    GraphAnnotation,
    GraphDiagram,
    GraphDiagramFile,
    GraphEdge,
    GraphNode,
    NodePosition,
    SourceRef,
    State,
    StateMachine,
    StateMachineFile,
    StateMachineLayout,
    Transition,
)
from hla_lab.paths import DocumentResources, RESOURCES

ROOT = RESOURCES.document("hla-1516.1-2010").root
STATE_FIGURES = (1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17)
GRAPH_FIGURES = (2, 18, 19, 20)
PAGE_BY_FIGURE = {
    1: 39,
    2: 40,
    3: 41,
    4: 42,
    5: 44,
    6: 46,
    7: 47,
    8: 47,
    9: 48,
    10: 83,
    11: 84,
    12: 85,
    13: 86,
    14: 103,
    15: 104,
    16: 138,
    17: 171,
    18: 205,
    19: 262,
    20: 263,
}

# Captions that are split across several source comments or contain a generic
# placeholder in the native source.  These are semantic labels, not layout
# coordinates; the remaining state labels are recovered from their markers.
LABEL_OVERRIDES = {
    1: {
        "S00": "Federation Execution",
        "S01": "Federation Execution Does Not Exist",
        "S02": "Federation Execution Exists",
        "S03": "No Joined Federates",
        "S04": "Supporting Joined Federates",
    },
    3: {
        "S00": "Lifetime of a Federate",
        "S01": "Not Connected",
        "S02": "Connected",
        "S03": "Not Joined",
        "S04": "Joined Federate",
    },
    4: {
        "S00": "Joined Federate",
        "S01": "Active Federate",
        "S02": "Active",
        "S03": "Restore Request Pending",
        "S04": "Waiting for Restore to Begin",
        "S05": "Federate Save in Progress",
        "S06": "Instructed to Save",
        "S07": "Saving",
        "S08": "Waiting for Federation to Save",
        "S09": "Federate Restore in Progress",
        "S10": "Waiting for Federation to Restore",
        "S11": "Restoring",
        "S12": "Prepared to Restore",
        "S13": "Normal Activity Permitted",
        "S14": "Normal Activity Not Permitted",
    },
    5: {
        "S00": "Normal Activity Permitted",
        "S01": "First Object Class",
        "S02": "Last Object Class",
        "S03": "First Interaction Class",
        "S04": "Last Interaction Class",
    },
    7: {
        "S00": "Global Synch Label",
        "S01": "Synch Point Not Registered",
        "S02": "Validating Synch Point",
    },
    8: {"S00": "Awaiting Synchronization", "S01": "Waiting for Federate to Synchronize"},
    9: {
        "S00": "Local Synch Label",
        "S01": "No Activity",
        "S02": "Attempting to Register Synch Point",
        "S03": "Moving to Synch Point",
        "S04": "Waiting for Rest of Federation to Synchronize",
    },
    10: {
        "S01": "Class Attribute (i, HLAprivilegeToDeleteObject)",
        "S02": "Second Available Class Attribute",
        "S03": "Last Available Class Attribute",
        "S04": "Object Instance (i, 1) Not Known",
        "S05": "Object Instance (i, 1) Known",
        "S06": "Object Instance (i, 1) No Longer Known",
        "S07": "Object Instance (i, k) Not Known",
        "S08": "Object Instance (i, k) Known",
        "S09": "Object Instance (i, k) No Longer Known",
    },
    11: {
        "S00": "Class Attribute (i, j)",
        "S01": "Published (i, j)",
        "S02": "Unpublished (i, j)",
        "S03": "Subscribed (i, j)",
        "S04": "Unsubscribed (i, j)",
    },
    12: {
        "S00": "Class Attribute",
        "S01": "Implicit Publication",
        "S02": "Implicitly Unpublished",
        "S03": "Implicitly Published",
        "S04": "Explicit Publication",
        "S05": "Explicitly Unpublished",
        "S06": "Explicitly Published",
        "S07": "Subscribed",
        "S08": "Unsubscribed",
    },
    13: {
        "S00": "Interaction Class",
        "S01": "Unpublished (m)",
        "S02": "Published (m)",
        "S03": "No Control Sends",
        "S04": "Control Sends In Use",
        "S05": "Interaction Relevance Unknown",
        "S06": "Interactions Turned On",
        "S07": "Interactions Turned Off",
        "S08": "Subscribed (m)",
        "S09": "Unsubscribed (m)",
    },
    14: {"S00": "Object Instance (i, k) Known"},
    15: {
        "S00": "Ownership Implications",
        "S01": "Is Owned",
        "S02": "No Control Updates",
        "S03": "Control Updates In Use",
        "S05": "Control Updates Resolved",
        "S06": "Control Updates Disabled",
        "S07": "Is Not Owned",
        "S08": "No Scope Notification",
        "S09": "Notify of Scope In Use",
        "S11": "Scope Notification Resolved",
        "S12": "Scope Notification Disabled",
    },
    16: {
        "S00": "Establishing Ownership of Instance Attribute",
        "S01": "Owned (i, k, j)",
        "S02": "Not Divesting",
        "S03": "Waiting for a New Owner to be Found",
        "S04": "Completing Divestiture",
        "S05": "Unowned (i, k, j)",
        "S06": "Not Able to Acquire",
        "S07": "Able to Acquire",
        "S08": "Acquisition Pending",
        "S09": "Trying to Cancel Acquisition",
        "S10": "Acquiring",
        "S11": "Not Acquiring",
        "S12": "Willing to Acquire",
        "S13": "Not Trying to Acquire",
    },
    17: {"S00": "Temporal State"},
}

def _source(path: Path, text: str, offset: int) -> SourceRef:
    return SourceRef(path=path.relative_to(ROOT).as_posix(), line=line_number(text, offset))

def _title(text: str, figure: int) -> str:
    match = re.search(rf"^%\s*Figure\s+{figure}\s*-\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else f"Figure {figure}"

def _marker_records(text: str, figure: int, kind: str) -> list[tuple[str, str, int]]:
    marker = re.compile(rf"F{figure:02d}-{kind}\d{{2}}")
    matches = list(marker.finditer(text))
    records: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        identifier = match.group(0).split("-")[1]
        if identifier in seen:
            continue
        seen.add(identifier)
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        next_marker = matches[index + 1].start() if index + 1 < len(matches) else line_end
        end = min(next_marker, line_end)
        if end < 0:
            end = len(text)
        fragment = text[match.end(): end]
        fragment = re.sub(r"^[\s:/,\-]+", "", fragment).strip()
        records.append((identifier, fragment, match.start()))
    return records

def _clean_label(value: str, figure: int, identifier: str) -> str:
    suffix = identifier.removeprefix("S").removeprefix("P")
    override = LABEL_OVERRIDES.get(figure, {}).get(identifier)
    if override:
        return override
    value = re.sub(r"\s+", " ", value).strip(" .;:/-")
    value = re.sub(r"^(?:outer|nested|the|first|last)\s+", "", value, flags=re.I)
    if " and " in value and identifier.startswith("S"):
        value = value.rsplit(" and ", 1)[-1]
    if value and value.lower() not in {"state", "states", "placeholder"}:
        return value
    return f"Figure {figure} state {suffix}"

def _kind(identifier: str, label: str, marker_text: str) -> str:
    if identifier.startswith("P"):
        lowered = f"{label} {marker_text}".lower()
        if "final" in lowered:
            return "final"
        if "history" in lowered:
            return "history"
        if "connector" in lowered or "conditional" in lowered:
            return "connector"
        return "initial"
    lowered = f"{label} {marker_text}".lower()
    if "composite" in lowered or "outer" in lowered or "region" in lowered:
        return "composite"
    return "normal"

def _resolve_token(token: str, states: dict[str, State], initial: tuple[str, ...]) -> str | None:
    token = token.strip().replace(" ", "")
    if re.fullmatch(r"[SP]\d{2}", token):
        return next(
            (state_id for state_id in states if state_id.endswith(f".{token.lower()}")), None
        )
    lowered = token.casefold()
    for state_id, state in states.items():
        if state.label.casefold() == lowered or lowered in state.label.casefold():
            return state_id
    if "initial" in lowered:
        return initial[0] if initial else None
    return None

def _transition_endpoints(
    description: str, states: dict[str, State], initial: tuple[str, ...]
) -> tuple[str | None, str | None]:
    token_match = re.search(r"\b([SP]\d{2})\s*[-=]>\s*([SP]\d{2})\b", description, re.I)
    if token_match:
        return (
            _resolve_token(token_match.group(1).upper(), states, initial),
            _resolve_token(token_match.group(2).upper(), states, initial),
        )
    name_match = re.search(r"([^;,.]+?)\s+[-=]>\s+([^;,.]+)", description)
    if name_match:
        return (
            _resolve_token(name_match.group(1), states, initial),
            _resolve_token(name_match.group(2), states, initial),
        )
    return (None, None)

def _state_machine(path: Path, figure: int, text: str) -> StateMachine:
    state_markers = _marker_records(text, figure, "[SP]")
    states: dict[str, State] = {}
    root_id: str | None = None
    for identifier, marker_text, offset in state_markers:
        state_id = f"hla-1516.1-2010:figure-{figure:02d}.{identifier.lower()}"
        label = _clean_label(marker_text, figure, identifier)
        state = State(
            id=state_id,
            label=""
            if identifier.startswith("P")
               and _kind(identifier, label, marker_text) in {"initial", "final"}
            else label,
            kind=_kind(identifier, label, marker_text),
            source=_source(path, text, offset),
        )
        if identifier == "S00":
            root_id = state_id
        states[state_id] = state
    if root_id:
        for state_id, state in tuple(states.items()):
            if state_id != root_id and state.parent_id is None:
                states[state_id] = state.model_copy(update={"parent_id": root_id})
    initial = tuple(state_id for state_id, state in states.items() if state.kind == "initial")
    if not initial and states:
        initial = (next(iter(states)),)

    transitions: list[Transition] = []
    for identifier, description, offset in _marker_records(text, figure, "E"):
        event = re.sub(r"\s+", " ", description).strip(" .;:/-") or f"Transition {identifier}"
        source_state, target_state = _transition_endpoints(event, states, initial)
        transitions.append(
            Transition(
                id=f"hla-1516.1-2010:figure-{figure:02d}.{identifier.lower()}",
                source_state=source_state,
                event=event,
                target_state=target_state,
                source=_source(path, text, offset),
            )
        )
    positions = {
        state_id: NodePosition(x=float(index % 4) * 4.0, y=float(-(index // 4)) * 2.2, visible=True)
        for index, state_id in enumerate(states)
    }
    return StateMachine(
        id=f"hla-1516.1-2010:figure-{figure:02d}",
        title=_title(text, figure),
        states=tuple(states.values()),
        transitions=tuple(transitions),
        initial_state_ids=initial,
        source=SourceRef(path=path.relative_to(ROOT).as_posix(), line=1),
        provenance=DiagramProvenance(
            image=path.relative_to(ROOT).as_posix(),
            page=PAGE_BY_FIGURE[figure],
            caption=_title(text, figure),
        ),
        layout=StateMachineLayout(nodes=positions),
        notes=(
            "State and transition markers are source-derived; null endpoints remain "
            "explicit when the native annotation does not identify both states."
        ),
    )

def _graph(path: Path, figure: int, text: str) -> GraphDiagram:
    title = _title(text, figure)
    annotations: tuple[GraphAnnotation, ...] = ()
    if figure == 2:
        nodes = (
            GraphNode(
                id="federate", label="Federate", x=0, y=0, width=2.6, height=0.8, style="lifeline"
            ),
            GraphNode(id="rti", label="RTI", x=7, y=0, width=2.6, height=0.8, style="lifeline"),
        )
        edges = tuple(
            GraphEdge(
                id=f"figure-02-e{index:02d}",
                source="federate",
                target="rti",
                label=description.strip(" ."),
                direction="both" if index in {4, 5, 6} else "forward",
                source_ref=_source(path, text, offset),
            )
            for index, (_identifier, description, offset) in enumerate(
                _marker_records(text, figure, "E"), start=1
            )
        )
    elif figure == 18:
        nodes = (
            GraphNode(
                id="coordinate-space",
                label="Multi-Dimensional Coordinate Space",
                x=0,
                y=0,
                width=12,
                height=6,
                style="frame",
            ),
            GraphNode(
                id="region",
                label="Region",
                x=-2.2,
                y=1.5,
                width=2.4,
                height=1.0,
                style="box",
            ),
        )
        edges = ()
        annotations = (
            GraphAnnotation(id="upper-bound", x=4.0, y=1.0, text="Range Upper Bound"),
            GraphAnnotation(id="lower-bound", x=4.0, y=3.0, text="Range Lower Bound"),
            GraphAnnotation(id="horizontal-dimension", x=0, y=6.7, text="Dimension"),
            GraphAnnotation(id="vertical-dimension", x=6.5, y=3.0, text="Dimension", rotate=90),
        )
    else:
        if figure == 19:
            nodes = (
                GraphNode(
                    id="hla-manager",
                    label="HLAmanager",
                    x=0,
                    y=0,
                    width=4.0,
                    height=1.5,
                    style="box",
                ),
                GraphNode(
                    id="hla-federate",
                    label="HLAfederate",
                    x=-4,
                    y=3,
                    width=4.0,
                    height=1.5,
                    style="box",
                ),
                GraphNode(
                    id="hla-federation",
                    label="HLAfederation",
                    x=0,
                    y=3,
                    width=4.0,
                    height=1.5,
                    style="box",
                ),
                GraphNode(
                    id="manager-extension",
                    label="(extensions)",
                    x=4,
                    y=3,
                    width=4.0,
                    height=1.5,
                    style="box",
                ),
                GraphNode(
                    id="federate-extension",
                    label="(extensions)",
                    x=-4,
                    y=6,
                    width=4.0,
                    height=1.5,
                    style="box",
                ),
                GraphNode(
                    id="federation-extension",
                    label="(extensions)",
                    x=0,
                    y=6,
                    width=4.0,
                    height=1.5,
                    style="box",
                ),
            )
            edges = (
                GraphEdge(
                    id="figure-19-r01",
                    source="hla-manager",
                    target="hla-federate",
                    label="predefined hierarchy",
                ),
                GraphEdge(
                    id="figure-19-r02",
                    source="hla-manager",
                    target="hla-federation",
                    label="predefined hierarchy",
                ),
                GraphEdge(
                    id="figure-19-r03",
                    source="hla-manager",
                    target="manager-extension",
                    label="extension",
                    style="dotted",
                ),
                GraphEdge(
                    id="figure-19-r04",
                    source="hla-federate",
                    target="federate-extension",
                    label="extension",
                    style="dotted",
                ),
                GraphEdge(
                    id="figure-19-r05",
                    source="hla-federation",
                    target="federation-extension",
                    label="extension",
                    style="dotted",
                ),
            )
        else:
            labels = (
                ("manager", "HLAmanager", 0, 0),
                ("federation", "HLAfederation", -6, 2),
                ("federate", "HLAfederate", 0, 2),
                ("manager-extension", "(extensions)", 6, 2),
                ("federate-extension", "(extensions)", -8, 4),
                ("adjust", "HLAadjust", -4, 4),
                ("request", "HLArequest", -1.3, 4),
                ("report", "HLAreport", 1.3, 4),
                ("service", "HLAservice", 4, 4),
                ("adjust-extension", "(extensions)", -4, 6),
                ("request-extension", "(extensions)", -1.3, 6),
                ("report-extension", "(extensions)", 1.3, 6),
                ("service-extension", "(extensions)", 4, 6),
                ("federation-adjust", "HLAadjust", -6, 8),
                ("federation-request", "HLArequest", -3, 8),
                ("federation-report", "HLAreport", 0, 8),
                ("federation-extension", "(extensions)", -8, 8),
                ("federation-adjust-extension", "(extensions)", -6, 10),
                ("federation-request-extension", "(extensions)", -3, 10),
                ("federation-report-extension", "(extensions)", 0, 10),
            )
            nodes = tuple(
                GraphNode(id=identifier, label=label, x=x, y=y, width=2.4, height=0.8, style="box")
                for identifier, label, x, y in labels
            )
            edge_pairs = (
                ("manager", "federation", "predefined hierarchy", "solid"),
                ("manager", "federate", "predefined hierarchy", "solid"),
                ("manager", "manager-extension", "extension", "dotted"),
                ("federate", "adjust", "predefined hierarchy", "solid"),
                ("federate", "request", "predefined hierarchy", "solid"),
                ("federate", "report", "predefined hierarchy", "solid"),
                ("federate", "service", "predefined hierarchy", "solid"),
                ("federate", "federate-extension", "extension", "dotted"),
                ("adjust", "adjust-extension", "extension", "dotted"),
                ("request", "request-extension", "extension", "dotted"),
                ("report", "report-extension", "extension", "dotted"),
                ("service", "service-extension", "extension", "dotted"),
                ("federation", "federation-adjust", "predefined hierarchy", "solid"),
                ("federation", "federation-request", "predefined hierarchy", "solid"),
                ("federation", "federation-report", "predefined hierarchy", "solid"),
                ("federation", "federation-extension", "extension", "dotted"),
                ("federation-adjust", "federation-adjust-extension", "extension", "dotted"),
                ("federation-request", "federation-request-extension", "extension", "dotted"),
                ("federation-report", "federation-report-extension", "extension", "dotted"),
            )
            edges = tuple(
                GraphEdge(
                    id=f"figure-20-r{index:02d}",
                    source=source,
                    target=target,
                    label=label,
                    style=style,
                )
                for index, (source, target, label, style) in enumerate(edge_pairs, start=1)
            )
    annotations = (
        *annotations,
        GraphAnnotation(id=f"figure-{figure:02d}-caption", x=0, y=-2, text=title),
    )
    return GraphDiagram(
        id=f"hla-1516.1-2010:figure-{figure:02d}",
        title=title,
        kind="architecture" if figure == 2 else "hierarchy",
        nodes=nodes,
        edges=edges,
        annotations=annotations,
        source=SourceRef(path=path.relative_to(ROOT).as_posix(), line=1),
        provenance=DiagramProvenance(
            image=path.relative_to(ROOT).as_posix(), page=PAGE_BY_FIGURE[figure], caption=title
        ),
        notes=(
            "Semantic graph ownership is promoted from the annotated source fixture; "
            "native geometry remains a faithful layout adapter."
        ),
    )

def promote(root: Path) -> None:
    native = root / "figures" / "native"
    existing_state = DocumentResources(root).semantic_file("native-state-machines.json")
    prior_transitions: dict[str, dict[str, object]] = {}
    if existing_state.exists():
        payload = json.loads(existing_state.read_text(encoding="utf-8"))
        prior_transitions = {
            transition["id"]: transition
            for machine in payload.get("state_machines", ())
            for transition in machine.get("transitions", ())
        }
    coverage_file = DocumentResources(root).semantic_file("transition-coverage.json")
    coverage_transitions: dict[str, dict[str, object]] = {}
    if coverage_file.exists():
        coverage_payload = json.loads(coverage_file.read_text(encoding="utf-8"))
        coverage_transitions = {
            coverage["transition_id"]: coverage
            for coverage in coverage_payload.get("transition_coverage", ())
        }
    links_file = DocumentResources(root).semantic_file("requirement-links.json")
    requirement_links: dict[str, list[str]] = {}
    if links_file.exists():
        links_payload = json.loads(links_file.read_text(encoding="utf-8"))
        for link in links_payload.get("links", ()):
            requirement_links.setdefault(link["transition_id"], []).append(link["requirement_id"])
    state_machines: list[StateMachine] = []
    graph_diagrams: list[GraphDiagram] = []
    surfaces: list[dict[str, object]] = []
    for figure in (*STATE_FIGURES, *GRAPH_FIGURES):
        path = native / f"figure-{figure:02d}.tex"
        text = path.read_text(encoding="utf-8")
        if figure in STATE_FIGURES:
            record = _state_machine(path, figure, text)
            enriched_transitions = []
            for transition in record.transitions:
                prior = prior_transitions.get(transition.id, {})
                updates = {}
                for key in ("clause_id", "requirement_ids", "implementation_ids"):
                    if key not in prior:
                        continue
                    value = prior[key]
                    if key in {"requirement_ids", "implementation_ids"}:
                        value = tuple(value)
                    updates[key] = value
                coverage = coverage_transitions.get(transition.id, {})
                if not updates.get("implementation_ids") and "implementation_ids" in coverage:
                    updates["implementation_ids"] = tuple(coverage["implementation_ids"])
                if not updates.get("requirement_ids") and transition.id in requirement_links:
                    updates["requirement_ids"] = tuple(requirement_links[transition.id])
                enriched_transitions.append(transition.model_copy(update=updates))
            record = record.model_copy(update={"transitions": tuple(enriched_transitions)})
            state_machines.append(record)
            kind = "state_machine"
        else:
            record = _graph(path, figure, text)
            graph_diagrams.append(record)
            kind = "graph_diagram"
        surfaces.append(
            {
                "id": f"figure-{figure:02d}",
                "document_id": "hla-1516.1-2010",
                "page": PAGE_BY_FIGURE[figure],
                "figure_number": figure,
                "status": "generated",
                "record_id": record.id,
                "record_kind": kind,
                "reason": (
                    "Semantic record owns figure meaning; native TikZ is retained only "
                    "as a faithful geometry adapter."
                ),
            }
        )
    semantic = DocumentResources(root).semantic
    (semantic / "native-state-machines.json").write_text(
        json.dumps(
            StateMachineFile(schema_version=2, state_machines=tuple(state_machines)).model_dump(
                mode="json"
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (semantic / "native-graph-diagrams.json").write_text(
        json.dumps(
            GraphDiagramFile(schema_version=1, graph_diagrams=tuple(graph_diagrams)).model_dump(
                mode="json"
            ),
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (semantic / "diagram-surfaces.json").write_text(
        json.dumps({"schema_version": 1, "surfaces": surfaces}, indent=2) + "\n", encoding="utf-8"
    )
    print(f"promoted {len(state_machines)} state machines and {len(graph_diagrams)} graph diagrams")

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, default=ROOT, nargs="?")
    promote(parser.parse_args().root)

if __name__ == "__main__":
    main()
