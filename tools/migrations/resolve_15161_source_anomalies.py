"""Apply reviewed dispositions to the HLA 1516.1-2025 source anomaly ledger."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.semantic_model import RequirementFile, SourceAnomalyLedger
from tools.migrations.workspace import document_root

DECISIONS = {
    "hla15161-overview-service-groups": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "The captured page says seven basic groups plus an eighth support group, but its "
            "enumeration contains seven items total, including Support services. It also prints "
            "DMM where this edition otherwise uses DDM."
        ),
        "rendered_text": (
            "The semantic inventory follows the seven named entries: six basic groups plus "
            "Support services. Data Distribution Management is identified as DDM in mapping "
            "metadata. The contradictory count and DMM spelling remain recorded as source text."
        ),
        "resolution": (
            "Use the enumerated names and count for semantic grouping; normalize DMM to DDM only "
            "in mapping metadata. Preserve the contradictory prose literally in the source layer."
        ),
        "mapping_effect": (
            "Do not create an eighth group or an extra requirement from the conflicting ordinal."
        ),
        "evidence_refs": [
            "content-15161-page-017",
            "content-15161-page-018",
        ],
    },
    "hla15161-footnotes-9-10": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "The supplied source capture shows markers 9 and 10 and isolated note numbers, but "
            "contains no note bodies."
        ),
        "rendered_text": (
            "Retain the source markers without inventing footnote text or deriving requirements "
            "from the missing notes."
        ),
        "resolution": (
            "Treat the note bodies as absent from the supplied source capture; preserve the "
            "markers as source evidence and leave their meaning unspecified."
        ),
        "mapping_effect": "No requirement or API binding is derived from either marker.",
        "evidence_refs": ["content-15161-page-021"],
    },
    "hla15161-private-use-glyphs": {
        "review_status": "RESOLVED",
        "reason": "Private-use glyphs in the source projection are unstable publication characters.",
        "rendered_text": "Ordinary parentheses and Unicode text characters are used.",
        "resolution": (
            "Replace only private-use wrapper glyphs with ordinary punctuation or their visible "
            "Unicode text equivalent."
        ),
        "mapping_effect": "No requirement meaning, identifier, or API binding changes.",
        "evidence_refs": ["content-elements.json"],
    },
    "hla15161-figure-caption-duplication": {
        "review_status": "RESOLVED",
        "reason": (
            "Source page furniture was composed with imported artwork, duplicating figure captions."
        ),
        "rendered_text": (
            "Each figure uses one generated caption attached to its reviewed semantic artwork."
        ),
        "resolution": (
            "Keep artwork caption-free and render one caption from the semantic figure record."
        ),
        "mapping_effect": "Figure IDs and their source associations remain unchanged.",
        "evidence_refs": ["content-elements.json", "semantic figure records"],
    },
    "hla15161-infrastructure-after": {
        "review_status": "RESOLVED",
        "reason": "The captured text joins the end of one sentence and the next word as infrastructure.After.",
        "rendered_text": "Rendered with a separating space after the sentence.",
        "resolution": "Insert the missing word boundary after infrastructure.",
        "mapping_effect": "No requirement or API binding changes.",
        "evidence_refs": ["content-elements.json"],
    },
    "hla15161-directed-interation": {
        "review_status": "RESOLVED",
        "reason": (
            "The FDD list prints Directed interation; the intended term is corroborated by the "
            "repeated Directed interaction terminology in the same edition."
        ),
        "rendered_text": (
            "Render Directed interaction table (complete); retain the source typo in this ledger."
        ),
        "resolution": (
            "Correct the obvious spelling error in the derived label while preserving the source "
            "literal here."
        ),
        "mapping_effect": "Use the canonical Directed interaction label for mapping.",
        "evidence_refs": ["content-15161-page-047"],
    },
    "hla15161-comment-note-contamination": {
        "review_status": "RESOLVED",
        "reason": "An editorial Comment note was embedded inside a normative FOM-combination bullet.",
        "rendered_text": (
            "Remove the editorial note from normative production prose and retain its literal "
            "content in this ledger."
        ),
        "resolution": "Exclude the parenthetical editorial instruction from the derived rule text.",
        "mapping_effect": "The note creates no requirement or API binding.",
        "evidence_refs": ["content-15161-page-048"],
    },
    "hla15161-initiate-federate-save-enumeration": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "The source lists Federation save label and Optional timestamp with the same a) label."
        ),
        "rendered_text": (
            "Preserve the duplicate source labels in the source layer; represent the arguments "
            "as an ordered label followed by an optional time value."
        ),
        "resolution": (
            "Use argument order and declaration names, not the duplicated alphabetic labels, as "
            "the semantic identity of these parameters."
        ),
        "mapping_effect": (
            "The first parameter remains the save label and the second remains the optional time; "
            "they are not merged."
        ),
        "evidence_refs": [
            "content-15161-page-067",
            "api-surface: FederateAmbassador.initiateFederateSave(String label)",
            "api-surface: FederateAmbassador.initiateFederateSave(String label, LogicalTime time)",
        ],
    },
    "hla15161-java-version-conflict": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "Clause 12.11 says the Java API shall be based on Java 11; a later paragraph in "
            "12.11.6 says Java 5 is assumed."
        ),
        "rendered_text": (
            "Keep both source statements visible in provenance. Use Java 11 as the implementation "
            "baseline; treat the Java 5 sentence as a conflicting legacy note."
        ),
        "resolution": (
            "Prefer the explicit shall statement in 12.11 for the implementation baseline, while "
            "retaining the contradictory Java 5 sentence without rewriting it."
        ),
        "mapping_effect": "Use Java 11 API declarations for implementation mapping.",
        "evidence_refs": [
            "content-15161-page-358",
            "content-15161-page-369",
        ],
    },
    "hla15161-time-class-capitalization": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "The source uses uppercase class names such as HLAInteger64Time and lowercase "
            "symbolic MIM names such as HLAinteger64Time in different contexts."
        ),
        "rendered_text": (
            "Keep technical tokens case-preserving; distinguish language API class identifiers "
            "from MIM symbolic names."
        ),
        "resolution": (
            "Do not globally normalize time-type capitalization. Match each token using its "
            "declared namespace and role."
        ),
        "mapping_effect": (
            "Case-sensitive Java class and filename mappings use the class spelling; MIM labels "
            "retain the symbolic-name spelling."
        ),
        "evidence_refs": [
            "content-15161-page-354",
            "content-15161-page-355",
            "content-15161-page-356",
        ],
    },
    "hla15161-annex-a-cross-reference": {
        "review_status": "RESOLVED",
        "reason": (
            "The Federate Protocol API is listed and defined in normative Annex D; Annex E is "
            "the rationale annex."
        ),
        "rendered_text": (
            "Correct the two Federate Protocol references to Annex D and preserve the original "
            "Annex E wording in this ledger."
        ),
        "resolution": "Use Annex D for the Federate Protocol API and its files.",
        "mapping_effect": "Protocol mappings resolve to Annex D declarations.",
        "evidence_refs": [
            "content-15161-page-015",
            "content-15161-page-020",
            "content-15161-page-414",
        ],
    },
    "hla15161-annex-classification": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "Annex E is labeled normative but its overview says nothing in it is required in an "
            "HLA implementation. Annex F is labeled informative while containing shall-like text."
        ),
        "rendered_text": (
            "Preserve the annex labels and wording as source evidence. Treat Annex E as rationale "
            "with no independent implementation obligations, and Annex F as informative."
        ),
        "resolution": (
            "The seven Annex E and three Annex F shall-like records are reviewed as non-normative "
            "source candidates. The source classification inconsistency remains explicitly noted."
        ),
        "mapping_effect": (
            "These ten records are excluded from the normative requirement set and from direct "
            "API obligation mapping."
        ),
        "evidence_refs": [
            "content-15161-page-423",
            "content-15161-page-433",
            "IEEE SA Standards Board Operations Manual 8.1.4",
        ],
    },
    "hla15161-annex-h-page-reference": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "Annex H's figure table uses printed source-page numbers; those numbers are not page "
            "numbers in the generated derivative."
        ),
        "rendered_text": (
            "Treat the source figure list as a printed-page index only. The reflowable derivative "
            "does not reuse those numbers as generated-page references."
        ),
        "resolution": (
            "Keep source page numbers as provenance and use semantic figure anchors where a "
            "figure is modeled; do not claim a source page is a generated PDF page."
        ),
        "mapping_effect": ("No requirement or API mapping depends on Annex H pagination."),
        "evidence_refs": ["content-elements.json: content-15161-page-435"],
    },
    "hla15161-figure-4-artwork-mapping": {
        "review_status": "RESOLVED",
        "reason": (
            "Reviewed figure associations distinguish Figure 4 Joined federate state from "
            "Figure 5 Normal Activity Permitted state."
        ),
        "rendered_text": (
            "Figure 3 is Lifetime of a federate, Figure 4 is Joined federate state, and Figure 5 "
            "is Normal Activity Permitted state."
        ),
        "resolution": "Bind each caption and generated artwork to its reviewed figure record.",
        "mapping_effect": "No requirement-to-API binding changes.",
        "evidence_refs": ["content-15161-page-054", "content-15161-page-055"],
    },
    "hla15161-table-5-configuration-result-example": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "Table 5's field is spelled additionalSettingsResultCode while its example has "
            "addtionalSettingsResultCode and malformed punctuation."
        ),
        "rendered_text": (
            "Use additionalSettingsResultCode as the structured field. Preserve the misspelled "
            "example only as source evidence; do not create a field from it."
        ),
        "resolution": (
            "The Table 5 field and supplied Java declaration agree on additionalSettingsResultCode; "
            "the example typo remains a source conflict."
        ),
        "mapping_effect": (
            "Only the canonical field spelling is eligible for an API binding; the misspelling "
            "has no separate binding."
        ),
        "evidence_refs": [
            "content-15161-page-296",
            "data/hla-15161-official-auxiliary-evidence-2026-10-25.json: RL-256",
        ],
    },
    "hla15161-table-5-restore-status-set-name": {
        "review_status": "DISPOSITIONED",
        "reason": (
            "Table 5 prints FederateHandleRestoreStatusSet as Array<FederateHandleRestoreStatus>. "
            "The same standard's Table 14 assigns type 20 to FederateRestoreStatusSet and type "
            "19 to FederateRestoreStatus; the supplied Java and C++ callback declarations and "
            "FedPro messages also use FederateRestoreStatus without the extra Handle token."
        ),
        "rendered_text": (
            "For semantic mapping, treat Table 5's extra Handle tokens as a likely typographical "
            "error: use FederateRestoreStatusSet (MIM type 20), containing FederateRestoreStatus "
            "(type 19). Preserve the exact Table 5 spelling and example as printed source evidence."
        ),
        "resolution": (
            "Resolve the mapping to FederateRestoreStatusSet with FederateRestoreStatus elements. "
            "Table 14 in the same standard is decisive for the MIM type numbers; Java, C++, and "
            "FedPro API declarations corroborate the element identifier and provide no declaration "
            "named FederateHandleRestoreStatus. The Table 5 row is therefore a high-confidence "
            "editorial/source typo, although no IEEE correction was found; do not rewrite its literal."
        ),
        "mapping_effect": (
            "Map semantic type 20 to FederateRestoreStatusSet and its elements to "
            "FederateRestoreStatus. Do not create a type or API binding for the spurious "
            "FederateHandleRestoreStatusSet/FederateHandleRestoreStatus spellings."
        ),
        "evidence_refs": [
            "content-15161-page-297",
            "content-15161-page-324",
            "data/hla-15161-official-auxiliary-evidence-2026-10-25.json: RL-369",
            "api.2025.java.federateambassador.federationrestorestatusresponse.bc12ec4286e0",
            "api.2025.cpp.federateambassador.federationrestorestatusresponse.000dead4d6cb",
            "api.2025.fedpro.fedprodatatypes.federaterestorestatus.1e54de9139cb",
            "1516.2-2025 MIM semantic source",
        ],
    },
}


def resolve(root: Path, workspace_root: Path) -> None:
    ledger_path = root / "semantic/source-anomaly-ledger.json"
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    entries = payload["entries"]
    by_id = {item["source_id"]: item for item in entries}
    if by_id.keys() != DECISIONS.keys():
        raise ValueError(
            f"Ledger IDs differ from reviewed decisions; missing={sorted(DECISIONS.keys() - by_id.keys())}, "
            f"unexpected={sorted(by_id.keys() - DECISIONS.keys())}"
        )
    for identifier, decision in DECISIONS.items():
        by_id[identifier].update(decision)
    ledger = SourceAnomalyLedger.model_validate(payload)
    ledger_path.write_text(
        json.dumps(ledger.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    requirement_path = root / "semantic/requirements.json"
    requirements = RequirementFile.model_validate_json(requirement_path.read_text(encoding="utf-8"))
    target_id = "requirement-candidate-table-5-p297-r007"
    requirements = requirements.model_copy(
        update={
            "requirements": tuple(
                item.model_copy(
                    update={
                        "coverage_note": (
                            "Table 5 likely contains an editorial typo: use FederateRestoreStatusSet "
                            "(type 20) with FederateRestoreStatus (type 19), "
                            "corroborated by Table 14 and Java/C++/FedPro declarations. Preserve the "
                            "literal Table 5 names as source provenance; no API binding is inferred from "
                            "the anomalous tokens."
                        )
                    }
                )
                if item.id == target_id
                else item
                for item in requirements.requirements
            )
        }
    )
    requirement_path.write_text(
        json.dumps(
            requirements.model_dump(mode="json", exclude_unset=True), ensure_ascii=False, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    backflow_note = (
        "The printed Table 5 row is a high-confidence editorial typo: it adds Handle to both "
        "FederateRestoreStatusSet and FederateRestoreStatus. Table 14 in the same standard maps "
        "type 20 to FederateRestoreStatusSet and type 19 to FederateRestoreStatus; the official "
        "Java/C++ callbacks and FedPro data types corroborate FederateRestoreStatus. Map the "
        "semantic collection to type 20 and its elements to type 19. Preserve the literal Table 5 "
        "text and do not invent API symbols from it. No IEEE correction was found, so this is a "
        "semantic mapping resolution, not a publisher correction."
    )
    ledger_path = workspace_root / "data/hla-backflow-2026-10-24.json"
    if ledger_path.is_file():
        backflow = json.loads(ledger_path.read_text(encoding="utf-8"))
        for issue in backflow.get("issues", []):
            if issue.get("id") == "RL-369":
                issue["resolution_note"] = backflow_note
        ledger_path.write_text(
            json.dumps(backflow, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Recorded resolved dispositions for {len(ledger.entries)} source anomalies")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    resolve(document_root("hla-1516.1-2025", args.workspace_root), args.workspace_root)


if __name__ == "__main__":
    main()
