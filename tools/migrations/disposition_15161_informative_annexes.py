"""Disposition shall-like text in HLA 1516.1-2025 rationale/informative annexes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    RequirementApiBindingFile,
    RequirementFile,
    RequirementReviewFile,
    load_document_model,
)
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.workspace import document_root

ANNEX_E_IDS = {
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-426-l220-73",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-426-l235-78",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-426-l265-88",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-428-l82-27",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-429-l13-4",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-429-l136-45",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-431-l85-28",
}
ANNEX_F_IDS = {
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-433-l25-8",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-433-l43-14",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-433-l46-15",
}
REVIEW_TITLES = {
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-426-l220-73": "Attribute updates for subscribed federates",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-426-l235-78": "Example: subscribed attribute update",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-426-l265-88": "Example: unsubscribed attributes are not reflected",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-428-l82-27": "Interfaces for time-management abstract data types",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-429-l13-4": "Clarification of logical-time advance behavior",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-429-l136-45": "Logical-time advance after a flush-queue request",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-431-l85-28": "Example: reflection of updated attributes",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-433-l25-8": "FDD XML Schema filename",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-433-l43-14": "FDD validity under the XML Schema",
    "requirement-candidate-content-clauses-12-programming-language-mappings-page-433-l46-15": "RTI support for valid FDDs",
}
REVIEW_TITLES["requirement-candidate-content-clauses-01-overview-page-018-l4-1"] = (
    "At most one federate or the RTI shall update an attribute"
)

ANNEX_E_REASON = (
    "Annex E is labeled normative, but its E.1 overview explicitly says that nothing in the "
    "annex is required in an HLA implementation. Preserve this sentence as rationale/source "
    "evidence; it creates no independent conformance requirement."
)
ANNEX_F_REASON = (
    "Annex F is labeled informative. IEEE SA Standards Board Operations Manual 8.1.4 says "
    "informative annexes are for information only and are not normative. Preserve this "
    "sentence as source text; it creates no independent conformance requirement."
)


def disposition(root: Path) -> None:
    requirement_path = root / "semantic/requirements.json"
    raw_requirements = json.loads(requirement_path.read_text(encoding="utf-8"))
    requirements = RequirementFile.model_validate(raw_requirements)
    by_id = {item.id: item for item in requirements.requirements}
    expected_ids = ANNEX_E_IDS | ANNEX_F_IDS
    missing = expected_ids - by_id.keys()
    if missing:
        raise ValueError(f"Missing Annex E/F records: {sorted(missing)}")

    updated = []
    for item in requirements.requirements:
        if item.id not in expected_ids and item.id not in REVIEW_TITLES:
            updated.append(item)
            continue
        if item.id in REVIEW_TITLES and item.id not in expected_ids:
            updated.append(item.model_copy(update={"title": REVIEW_TITLES[item.id]}))
            continue
        reason = ANNEX_E_REASON if item.id in ANNEX_E_IDS else ANNEX_F_REASON
        updated.append(
            item.model_copy(
                update={
                    "title": REVIEW_TITLES[item.id],
                    "extraction": "candidate",
                    "coverage_kind": "not-applicable",
                    "coverage_note": reason,
                    "api_surface_scope": "not-applicable",
                    "api_surface_note": reason,
                }
            )
        )
    requirements = requirements.model_copy(update={"requirements": tuple(updated)})
    requirement_path.write_text(
        json.dumps(
            requirements.model_dump(mode="json", exclude_unset=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    review_path = root / "semantic/requirement-review.json"
    reviews = RequirementReviewFile.model_validate_json(review_path.read_text(encoding="utf-8"))
    reviews_by_id = {item.requirement_id: item for item in reviews.reviews}
    for identifier in ANNEX_E_IDS | ANNEX_F_IDS:
        reason = ANNEX_E_REASON if identifier in ANNEX_E_IDS else ANNEX_F_REASON
        requirement = by_id[identifier]
        reviews_by_id[identifier] = {
            "requirement_id": identifier,
            "status": "non-normative",
            "reason": reason,
            "source": requirement.source.model_dump(mode="json"),
        }
    reviews_payload = {
        "schema_version": reviews.schema_version,
        "reviews": list(reviews_by_id.values()),
    }
    reviews = RequirementReviewFile.model_validate(reviews_payload)
    review_path.write_text(
        json.dumps(reviews.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    model = load_document_model(root, HLA_SOURCE)
    bindings = build_requirement_api_bindings(model)
    binding_path = root / "semantic/api-requirement-bindings.json"
    binding_file = RequirementApiBindingFile.model_validate(
        {"schema_version": 1, "bindings": bindings}
    )
    binding_path.write_text(
        json.dumps(binding_file.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Dispositioned {len(expected_ids)} shall-like Annex E/F statements as non-normative")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    disposition(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
