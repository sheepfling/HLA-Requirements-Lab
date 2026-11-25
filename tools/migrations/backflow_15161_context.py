"""Repair page ownership and contextual candidate semantics for RL-413/453-455."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OLD_PAGE_216 = "content/clauses/08-time-management-page-216.tex"
NEW_PAGE_216 = "content/clauses/09-data-distribution-management-page-216.tex"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rewrite_source_paths(value: Any) -> bool:
    changed = False
    if isinstance(value, dict):
        for key, child in value.items():
            if key == "path" and child == OLD_PAGE_216:
                value[key] = NEW_PAGE_216
                changed = True
            else:
                changed = _rewrite_source_paths(child) or changed
    elif isinstance(value, list):
        for child in value:
            changed = _rewrite_source_paths(child) or changed
    return changed


def repair_15161_context(repository_root: Path) -> None:
    """Correct DDM page ownership and clarify the two candidate boundaries."""
    document_root = repository_root / "topics/ieee/hla-1516.1-2025"
    semantic_root = document_root / "semantic"

    # RL-413: page 216 is §9.1 DDM, not §8 time management. Preserve the stable
    # candidate IDs and clause IDs while correcting every semantic source path.
    source_paths = (
        semantic_root / "requirements.json",
        semantic_root / "content-blocks.json",
        semantic_root / "content-elements.json",
        semantic_root / "api-requirement-bindings.json",
    )
    payloads = [(path, _read(path)) for path in source_paths]
    path_changes = [_rewrite_source_paths(payload) for _, payload in payloads]
    # Idempotent reruns are valid when all paths already use the corrected name.
    if not any(path_changes) and not (document_root / NEW_PAGE_216).is_file():
        raise ValueError("page-216 DDM adapter is missing after source relabeling")

    old_adapter = document_root / OLD_PAGE_216
    new_adapter = document_root / NEW_PAGE_216
    if old_adapter.is_file() and new_adapter.exists():
        raise FileExistsError(f"both page-216 adapters exist: {old_adapter} and {new_adapter}")
    if old_adapter.is_file():
        old_adapter.rename(new_adapter)
    elif not new_adapter.is_file():
        raise FileNotFoundError(f"missing page-216 source adapter: {old_adapter}")

    for path, payload in payloads:
        _write(path, payload)

    requirements_path = semantic_root / "requirements.json"
    requirements_payload = _read(requirements_path)
    requirements = requirements_payload["requirements"]
    by_id = {item["id"]: item for item in requirements}

    # RL-453: retain the independently evidenced p.225 Allow Relaxed DDM rule;
    # only the detached fragment from the preceding sentence is removed.
    switch = by_id[
        "requirement-candidate-content-clauses-09-data-distribution-management-page-225-l120-37"
    ]
    switch_statement = "This switch setting shall not be modifiable during a federation execution."
    switch["statement"] = switch_statement
    switch["machine_statement"] = switch_statement

    # RL-454: these are wire-argument requirements only when services are invoked
    # over the Federate Protocol. Carry the source introduction into each stable
    # candidate instead of leaving its scope as orphan page context.
    protocol_applicability = "For HLA service arguments invoked over the Federate Protocol, "
    scoped_statements = {
        "requirement-candidate-content-clauses-12-programming-language-mappings-page-396-l147-48":
            "Time Representation arguments shall use the HLA time type name, such as HLAinteger64Time.",
        "requirement-candidate-content-clauses-12-programming-language-mappings-page-396-l159-52":
            "Handle arguments other than Conveyed Regions shall contain the opaque encoded bytes resulting from the handle’s encode operation.",
        "requirement-candidate-content-clauses-12-programming-language-mappings-page-396-l168-55":
            "Conveyed Regions shall not be passed as handles, but shall be passed as a full encoding of their constituent parts using the ConveyedRegionSet data type, as specified in Annex D.",
    }
    for record_id, statement in scoped_statements.items():
        record = by_id[record_id]
        scoped = protocol_applicability + statement
        record["statement"] = scoped
        record["machine_statement"] = scoped
        context_source = {
            "path": record["source"]["path"],
            "line": 109,
            "end_line": 109,
        }
        additional_sources = record.setdefault("additional_sources", [])
        if context_source not in additional_sources:
            additional_sources.append(context_source)
        note = (
            "The source introduction limits this rule to HLA service arguments invoked over the "
            "Federate Protocol; it does not establish a public C++ API call requirement."
        )
        record["coverage_note"] = note

    # RL-455: the lead-in organizes the immediately following transport rules;
    # it has no independent behavior or conformance oracle.
    transport_intro = by_id[
        "requirement-candidate-content-clauses-12-programming-language-mappings-page-411-l14-4"
    ]
    transport_intro.update(
        {
            "coverage_kind": "not-applicable",
            "coverage_note": (
                "Framing sentence introducing the transport-layer rules. It has no independent "
                "behavior or observable outcome; concrete protocol, address, port, and RID rules "
                "remain separate source-backed requirements."
            ),
            "api_surface_scope": "not-applicable",
            "api_surface_note": (
                "Section lead-in only; it does not define a separate callable API behavior."
            ),
        }
    )

    _write(requirements_path, requirements_payload)

    # The p.225 block and element must remain the sole content owners of RL-453.
    blocks = _read(semantic_root / "content-blocks.json")["content_blocks"]
    owners = [block for block in blocks if switch["id"] in block.get("record_ids", [])]
    if len(owners) != 1 or owners[0]["id"] != "content-15161-page-225":
        raise ValueError(f"RL-453 must be owned only by page 225, got {[b['id'] for b in owners]}")


if __name__ == "__main__":
    repair_15161_context(Path(__file__).resolve().parents[2])
