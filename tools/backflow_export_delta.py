"""Compare a Requirements Lab backflow snapshot with two validated corpus bundles."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from hla_lab.traceability.compliance_contract import CorpusBundle


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_record(record: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in record.items() if key != "ordinal"}


def _record_hash(record: dict[str, Any]) -> str:
    encoded = json.dumps(
        _stable_record(record), sort_keys=True, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    return _sha256(encoded)


def requirement_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Describe an exported requirement change without duplicating its source text."""
    old = _stable_record(before)
    new = _stable_record(after)
    fields = sorted(key for key in old.keys() | new.keys() if old.get(key) != new.get(key))
    readable = {"clause", "clause_id", "kind", "extraction", "semantic_group_id", "source"}
    return {
        "id": after["id"],
        "changed_fields": fields,
        "readable_changes": {
            key: {"before": old.get(key), "after": new.get(key)}
            for key in fields
            if key in readable
        },
        "before_sha256": _record_hash(before),
        "after_sha256": _record_hash(after),
    }


def _requirement_index(bundle: CorpusBundle) -> dict[str, dict[str, dict[str, Any]]]:
    documents: dict[str, dict[str, dict[str, Any]]] = {}
    for document in bundle.documents:
        if document.document_id in documents:
            raise ValueError(f"duplicate document {document.document_id}")
        records: dict[str, dict[str, Any]] = {}
        for item in document.requirements:
            if item.id in records:
                raise ValueError(f"duplicate requirement {item.id} in {document.document_id}")
            records[item.id] = item.model_dump(mode="json")
        documents[document.document_id] = records
    return documents


def build_delta(
    snapshot: dict[str, Any],
    baseline: CorpusBundle,
    candidate: CorpusBundle,
    *,
    baseline_sha256: str,
    candidate_sha256: str,
) -> dict[str, Any]:
    """Return ordered issue deltas, rejecting missing stable IDs or untouched repairs."""
    before_by_document = _requirement_index(baseline)
    after_by_document = _requirement_index(candidate)
    issues = snapshot["issues"]
    if len({issue["id"] for issue in issues}) != len(issues):
        raise ValueError("duplicate issue ID in backflow snapshot")
    results: list[dict[str, Any]] = []
    for issue in issues:
        document_id = issue["document_id"]
        try:
            before = before_by_document[document_id]
            after = after_by_document[document_id]
        except KeyError as error:
            raise ValueError(f"missing export document for {issue['id']}: {document_id}") from error
        affected = []
        for requirement_id in issue["affected_requirement_ids"]:
            if requirement_id not in before or requirement_id not in after:
                raise ValueError(f"missing stable requirement for {issue['id']}: {requirement_id}")
            delta = requirement_delta(before[requirement_id], after[requirement_id])
            if issue["resolution"] == "corrected-in-lab" and not delta["changed_fields"]:
                raise ValueError(f"corrected issue has unchanged requirement: {issue['id']}")
            affected.append(delta)
        created = []
        for requirement_id in issue.get("created_requirement_ids", ()):
            if requirement_id in before or requirement_id not in after:
                raise ValueError(f"invalid new requirement for {issue['id']}: {requirement_id}")
            created.append(
                {"id": requirement_id, "after_sha256": _record_hash(after[requirement_id])}
            )
        if issue["resolution"] == "corrected-in-lab" and not (affected or created):
            raise ValueError(f"corrected issue has no exported requirement: {issue['id']}")
        results.append(
            {
                "id": issue["id"],
                "resolution": issue["resolution"],
                "document_id": document_id,
                "affected": affected,
                "created": created,
            }
        )
    return {
        "schema_version": 1,
        "baseline": {
            "bundle_id": baseline.bundle_id,
            "corpus_revision": baseline.corpus_revision,
            "sha256": baseline_sha256,
        },
        "candidate": {
            "bundle_id": candidate.bundle_id,
            "corpus_revision": candidate.corpus_revision,
            "sha256": candidate_sha256,
        },
        "issues": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
    baseline_bytes = args.baseline.read_bytes()
    candidate_bytes = args.candidate.read_bytes()
    delta = build_delta(
        snapshot,
        CorpusBundle.model_validate_json(baseline_bytes),
        CorpusBundle.model_validate_json(candidate_bytes),
        baseline_sha256=_sha256(baseline_bytes),
        candidate_sha256=_sha256(candidate_bytes),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(delta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(delta['issues'])} issue deltas to {args.output}")


if __name__ == "__main__":
    main()
