"""Record source conflicts and their semantic mapping dispositions in the Lab."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _upsert_entries(path: Path, document_id: str, entries: list[dict[str, Any]]) -> None:
    payload = _read(path)
    if not payload:
        payload = {
            "schema_version": 1,
            "document_id": document_id,
            "purpose": (
                "Record source, compilation, encoding, and editorial anomalies without silently "
                "rewriting unresolved source meaning."
            ),
            "entries": [],
        }
    existing = {item["source_id"]: item for item in payload.setdefault("entries", [])}
    for entry in entries:
        existing[entry["source_id"]] = entry
    payload["entries"] = list(existing.values())
    _write(path, payload)


def _append_note(record: dict[str, Any], note: str) -> None:
    current = record.get("coverage_note", "").strip()
    if note not in current:
        record["coverage_note"] = f"{current} {note}".strip()


def _remove_queue_issue_suffix(record: dict[str, Any]) -> None:
    """Keep issue-tracker IDs out of semantic coverage prose."""
    note = record.get("coverage_note", "")
    marker = note.find("RL-")
    if marker >= 0:
        record["coverage_note"] = note[:marker].rstrip()


def _set_requirement_mapping(
    requirements: dict[str, dict[str, Any]],
    requirement_id: str,
    statement: str,
    coverage_note: str,
) -> None:
    record = requirements[requirement_id]
    record["statement"] = statement
    record["machine_statement"] = statement
    _append_note(record, coverage_note)


def _update_semantic_mappings(repository_root: Path) -> None:
    path = repository_root / "topics/ieee/hla-1516.2-2025/semantic/requirements.json"
    payload = _read(path)
    requirements = {item["id"]: item for item in payload["requirements"]}

    mapped_requirement_ids = (
        "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l50-9",
        "requirement-candidate-sections-semantic-annexes-d-h-page-114-l42-5",
        "requirement-candidate-sections-semantic-clauses-5-6-page-091-l54-7",
        "requirement-candidate-sections-semantic-clause-4b-page-062-l35-2",
        "requirement-candidate-sections-semantic-clauses-5-6-page-093-l78-15",
    )
    for requirement_id in mapped_requirement_ids:
        _remove_queue_issue_suffix(requirements[requirement_id])

    _set_requirement_mapping(
        requirements,
        "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l50-9",
        "If some sub-elements of the switch are not equivalent, a warning shall be provided "
        "to the user. The switch already exists but is not equivalent and therefore cannot be "
        "inserted; the merge shall fail.",
        "The derived statement separates warning delivery from the failed-merge outcome. The "
        "captured source wording remains linked in the content element and page layout; no "
        "distinct callback or log channel is asserted.",
    )
    _set_requirement_mapping(
        requirements,
        "requirement-candidate-sections-semantic-annexes-d-h-page-114-l42-5",
        "In the OMT XML Schema, note labels and note references shall be prefixed with an "
        "underscore to ensure that the labeling conforms to the NCName data type convention.",
        "The requirement isolates the standalone normative prefix rule. Conflicting schema and "
        "example evidence is recorded separately in the source anomaly ledger.",
    )

    _append_note(
        requirements["requirement-candidate-sections-semantic-clauses-5-6-page-091-l54-7"],
        "Apply Clause 3.3 to the Model Identification Name; names containing spaces do not "
        "satisfy this requirement. The supplied example remains separately recorded as "
        "conflicting evidence and is not an exception.",
    )
    _append_note(
        requirements["requirement-candidate-sections-semantic-clause-4b-page-062-l35-2"],
        "Capability is NA for each FOM/FOM-module synchronization row; the conflicting "
        "Restaurant example values are not normative exceptions.",
    )
    _append_note(
        requirements["requirement-candidate-sections-semantic-clauses-5-6-page-093-l78-15"],
        "Retain the direct NA rule for FOMs and FOM modules. The conflicting Restaurant example "
        "values do not alter this requirement.",
    )
    payload["requirements"] = list(requirements.values())
    _write(path, payload)


def repair_backflow_source_anomalies(repository_root: Path) -> None:
    """Map clear source requirements and preserve the remaining source conflicts."""
    _update_semantic_mappings(repository_root)

    lab_15161 = repository_root / "topics/ieee/hla-1516.1-2025/semantic/source-anomaly-ledger.json"
    entry_420 = {
        "source_id": "hla15161-variant-record-method-name-conflict",
        "related_issue_id": "RL-420",
        "location": "Clause 12.12.4.2, page 381; HLAvariantRecord C++ declaration",
        "source_text": (
            "The Lab source calls the operation addMapping to associate encoders/decoders with "
            "discriminants. The published C++ header names the operation addVariant and documents "
            "it as adding a discriminant/variant pair that maps a unique discriminant to a copied "
            "value element; the header also has a distinct addVariantPointer operation."
        ),
        "rendered_text": (
            "Keep addMapping as the IEEE 1516.1 requirement wording. Crosswalk its mapping "
            "behavior to HLAvariantRecord::addVariant, whose header description matches the "
            "discriminant-to-variant association. Preserve the different API spelling."
        ),
        "classification": "SOURCE_ANOMALY",
        "reason": (
            "The source/API identifier differs, but the official header directly documents "
            "addVariant as adding the same discriminant-to-variant mapping described by the "
            "requirement. The semantic operation is therefore mappable without treating the "
            "names as literal aliases."
        ),
        "review_status": "DISPOSITIONED",
        "resolution": (
            "Map the addMapping requirement behavior to addVariant and retain the source/API "
            "name discrepancy. Do not map addVariantPointer to the copy-based addMapping "
            "requirement; it has a distinct pointer-lifetime contract."
        ),
        "mapping_effect": (
            "A C++ implementation crosswalk can target HLAvariantRecord::addVariant for the "
            "discriminant/variant association, together with setDiscriminant/getDiscriminant. "
            "The semantic requirement remains named addMapping, and no literal addMapping "
            "member is claimed."
        ),
        "evidence_refs": [
            "requirement-candidate-content-clauses-11-management-object-model-page-381-l16-5",
            "Umbra third_party/ieee1516.1-2025/include/RTI/encoding/HLAvariantRecord.h:87-127; SHA256 cfc4d1eb57f83df9b485e6da7422b01f10304d720e6a9c38d177b73192e9fcda",
        ],
    }
    _upsert_entries(lab_15161, "hla-1516.1-2025-federate-interface", [entry_420])

    entries_15162 = [
        {
            "source_id": "hla15162-model-identification-name-example",
            "related_issue_id": "RL-441",
            "location": "Clause 6.2.1 page 91; Clause 3.3.1 page 32; Restaurant FOM example",
            "source_text": (
                "Clause 6.2.1 requires the Model Identification Name to conform to Clause 3.3. "
                "Clause 3.3.1 says object-model names have no spaces. The published Restaurant "
                "FOM module names its model 'Restaurant FOM Module Example'."
            ),
            "rendered_text": (
                "Map the normative requirement by applying the Clause 3.3 name rules to the "
                "Model Identification Name. Preserve the example string as conflicting source "
                "evidence; do not infer an unstated exception."
            ),
            "classification": "SOURCE_ANOMALY",
            "reason": (
                "The requirement and Clause 3.3 determine the mapping, while the supplied example "
                "contains spaces and conflicts with that rule. The example does not make the "
                "normative name requirement ambiguous."
            ),
            "review_status": "DISPOSITIONED",
            "resolution": (
                "Treat names with spaces as violating the explicit Clause 3.3 requirement when "
                "checking Model Identification Name. Preserve the published example unchanged "
                "and record its nonconforming form as a source anomaly."
            ),
            "mapping_effect": (
                "The semantic requirement is mapped to the Clause 3.3 naming constraints. Do not "
                "treat 'Restaurant FOM Module Example' as evidence that spaces are permitted."
            ),
            "evidence_refs": [
                "requirement-candidate-sections-semantic-clauses-5-6-page-091-l54-7",
                "content-element-content-15162-page-032-paragraph-002",
                "Umbra third_party/ieee1516.2-2025/resources/examples/RestaurantFOMmodule-2025.xml:6; SHA256 8df2b31a09ebfadb206476c99f52dbcd4503fddb60445df2dc06e39b78a31a3d",
            ],
        },
        {
            "source_id": "hla15162-c8-switch-warning-and-merge-failure-wording",
            "related_issue_id": "RL-443",
            "location": "Annex C.8 page 113; switch merge conflict statement",
            "source_text": (
                "The captured semantic text reads 'a warning the merge shall be provided back to "
                "the user' and concludes 'cannot be inserted; the merge fails.' The captured page "
                "layout ends the corresponding line with 'cannot be insertedfail.'"
            ),
            "rendered_text": (
                "The derived requirement states two outcomes separately: a warning is provided "
                "to the user, and the non-equivalent switch is not inserted because the merge "
                "fails. The source wording and layout transcription remain unchanged in their "
                "source records."
            ),
            "classification": "SOURCE_ANOMALY",
            "reason": (
                "The source sentence has a duplicated phrase boundary and the layout joins "
                "'inserted' with 'fail'. Its explanation independently states that the switch "
                "cannot be inserted and the merge fails. Separating the outcomes repairs the "
                "semantic candidate without inventing an additional diagnostic channel."
            ),
            "review_status": "DISPOSITIONED",
            "resolution": (
                "Use the normalized candidate that states the warning and failed merge as "
                "separate outcomes. Preserve the captured wording verbatim in the content "
                "element and layout source."
            ),
            "mapping_effect": (
                "Map the warning obligation and merge-failure obligation distinctly. A consumer "
                "may crosswalk an exception detail to the warning only with an explicit "
                "interpretation note; the Lab does not assert a separate callback or log."
            ),
            "evidence_refs": [
                "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l50-9",
                "content-element-content-15162-page-113-list-item-019",
                "content-15162-page-113",
                "data/hla-backflow-2026-11-23.json#RL-443 upstream_record",
            ],
        },
        {
            "source_id": "hla15162-annex-d2-note-prefix-and-ncname-example",
            "related_issue_id": "RL-444",
            "location": "Annex D.2 page 114; DIF XSD and Restaurant/MIM examples",
            "source_text": (
                "Annex D.2 says note labels and references shall be prefixed with an underscore. "
                "The DIF schema declares note labels as xs:ID and noteReferences as xs:IDREFS. "
                "The published Restaurant FOM uses Note1/Note2 without underscores, and the MIM "
                "uses MOM1."
            ),
            "rendered_text": (
                "Map the standalone normative rule as written: prefix note labels and note "
                "references with an underscore. Preserve the schema and example values unchanged "
                "as contradictory source evidence; do not reinterpret 'shall' as conditional."
            ),
            "classification": "SOURCE_ANOMALY",
            "reason": (
                "The normative sentence unambiguously specifies prefixing, while the schema types "
                "and supplied examples accept or use unprefixed NCName-compatible values. This "
                "is a source-set contradiction, not a reason to leave the Lab mapping undefined."
            ),
            "review_status": "DISPOSITIONED",
            "resolution": (
                "Keep the isolated normative candidate and map mandatory underscore prefixing. "
                "Keep the official example and schema literals as source evidence; do not alter "
                "them or claim they satisfy the prefix sentence."
            ),
            "mapping_effect": (
                "The requirement mapping is explicit: labels and references are prefixed with an "
                "underscore. Conformance of the supplied unprefixed examples remains a separate "
                "source anomaly."
            ),
            "evidence_refs": [
                "requirement-candidate-sections-semantic-annexes-d-h-page-114-l42-5",
                "content-element-content-15162-page-114-paragraph-005",
                "Umbra third_party/ieee1516.2-2025/resources/schemas/IEEE1516-DIF-2025.xsd:2849,3045-3046; SHA256 7763639590950dba87d2a7f29d5735c78835855852113509754c24f20ceb3774",
                "Umbra third_party/ieee1516.2-2025/resources/examples/RestaurantFOMmodule-2025.xml:347-348,1048-1052; SHA256 8df2b31a09ebfadb206476c99f52dbcd4503fddb60445df2dc06e39b78a31a3d",
                "Umbra third_party/ieee1516.2-2025/resources/mim/HLAstandardMIM-2025.xml:3804",
            ],
        },
        {
            "source_id": "hla15162-fom-synchronization-capability-example",
            "related_issue_id": "RL-456",
            "location": "Clause 4.10 page 62; Clause 6.2.10 page 93; Restaurant FOM example",
            "source_text": (
                "Clauses 4.10 and 6.2.10 require Capability to be NA for FOMs and FOM modules. "
                "The published Restaurant FOM example assigns Achieve to InitialPublish, "
                "InitialUpdate, and BeginTimeAdvance, and RegisterAchieve to PauseExecution."
            ),
            "rendered_text": (
                "Map the FOM/FOM-module Capability field to NA for every synchronization row. "
                "Preserve the four conflicting example values and do not treat them as exceptions."
            ),
            "classification": "SOURCE_ANOMALY",
            "reason": (
                "The two normative requirement locations agree on NA; the provided example uses "
                "non-NA values without a stated exception. This conflict does not leave the "
                "semantic rule ambiguous."
            ),
            "review_status": "DISPOSITIONED",
            "resolution": (
                "Follow the explicit NA rule for the semantic mapping and preserve the original "
                "example values unchanged as contradictory source evidence."
            ),
            "mapping_effect": (
                "A check of FOM/FOM-module synchronization Capability maps to NA. Do not count "
                "acceptance of the supplied Restaurant example as satisfying this rule."
            ),
            "evidence_refs": [
                "requirement-candidate-sections-semantic-clause-4b-page-062-l35-2",
                "requirement-candidate-sections-semantic-clauses-5-6-page-093-l78-15",
                "Umbra third_party/ieee1516.2-2025/resources/examples/RestaurantFOMmodule-2025.xml:630-650; SHA256 8df2b31a09ebfadb206476c99f52dbcd4503fddb60445df2dc06e39b78a31a3d",
            ],
        },
    ]
    lab_15162 = repository_root / "topics/ieee/hla-1516.2-2025/semantic/source-anomaly-ledger.json"
    _upsert_entries(lab_15162, "hla-1516.2-2025-omt", entries_15162)


if __name__ == "__main__":
    repair_backflow_source_anomalies(Path(__file__).resolve().parents[2])
