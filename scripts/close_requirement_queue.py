"""Write explicit review dispositions for unpromoted HLA requirement candidates."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from scripts.hla_profile import HLA_SOURCE
    from scripts.semantic_model import RequirementReview, SourceRef, load_document_model
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hla_profile import HLA_SOURCE
    from semantic_model import RequirementReview, SourceRef, load_document_model


REVIEW_REASON = (
    "Extracted requirement candidate retained for clause-level review; it is not "
    "promoted because the current tranche has not established explicit normative "
    "coverage, state applicability, or implementation scope for this record."
)


def write_review(root: Path) -> Path | None:
    """Close every current candidate with an explicit deferred disposition."""
    model = load_document_model(root, HLA_SOURCE)
    candidates = tuple(item for item in model.requirements if item.extraction == "candidate")
    if not candidates:
        return None
    reviews = tuple(
        RequirementReview(
            requirement_id=item.id,
            status="deferred",
            reason=REVIEW_REASON,
            source=SourceRef(path="semantic/requirement-review.json", line=1),
        )
        for item in candidates
    )
    payload = {"schema_version": 1, "reviews": [item.model_dump(mode="json") for item in reviews]}
    output = root / "semantic" / "requirement-review.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", action="append", type=Path)
    args = parser.parse_args()
    roots = tuple(args.root or sorted(Path("topics/ieee").glob("hla-1516*/")))
    for root in roots:
        output = write_review(root)
        if output is not None:
            print(output)
