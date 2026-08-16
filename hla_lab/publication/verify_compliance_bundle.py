"""Verify an external implementation manifest against a portable corpus bundle."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from hla_lab.traceability.compliance_contract import (
    ComplianceCoverage,
    ComplianceFinding,
    ComplianceResult,
    CorpusBundle,
    ImplementationManifest,
)


def _coverage_ratio(numerator: int, denominator: int) -> float:
    """Return a normalized coverage ratio; empty dimensions are vacuously complete."""
    return 1.0 if denominator == 0 else round(numerator / denominator, 4)


def _finding(
    code: str,
    severity: str,
    record_id: str,
    message: str,
) -> ComplianceFinding:
    return ComplianceFinding(
        code=code,
        severity=severity,  # type: ignore[arg-type]
        record_id=record_id,
        message=message,
    )


def verify(
    bundle: CorpusBundle,
    manifest: ImplementationManifest,
) -> ComplianceResult:
    """Verify scope, mapping joins, API bindings, and external evidence."""
    findings: list[ComplianceFinding] = []
    documents = {item.document_id: item for item in bundle.documents}
    selected_documents = tuple(documents.get(identifier) for identifier in manifest.document_ids)
    for document_id, document in zip(manifest.document_ids, selected_documents, strict=True):
        if document is None:
            findings.append(
                _finding(
                    "document-not-in-bundle",
                    "error",
                    document_id,
                    f"manifest selects document {document_id}, but the bundle does not contain it",
                )
            )
    if manifest.corpus_revision != bundle.corpus_revision:
        findings.append(
            _finding(
                "corpus-revision-mismatch",
                "error",
                manifest.manifest_id,
                f"manifest expects {manifest.corpus_revision}, bundle is {bundle.corpus_revision}",
            )
        )

    evidence_by_id = {item.id: item for item in manifest.evidence}
    crosswalks_by_key = {
        (document.document_id, crosswalk.implementation_mapping_id, crosswalk.target): (
            document,
            crosswalk,
        )
        for document in bundle.documents
        for crosswalk in document.api_crosswalks
    }
    mappings_by_key = {
        (document.document_id, mapping.id): mapping
        for document in bundle.documents
        for mapping in document.mappings
    }
    expected_keys = {
        (document.document_id, crosswalk.implementation_mapping_id, crosswalk.target)
        for document in selected_documents
        if document is not None
        for crosswalk in document.api_crosswalks
        if crosswalk.target in manifest.targets
    }
    selected_crosswalks_by_key = {
        (document.document_id, crosswalk.implementation_mapping_id, crosswalk.target): crosswalk
        for document in selected_documents
        if document is not None
        for crosswalk in document.api_crosswalks
    }
    expected_requirement_keys = {
        (document.document_id, requirement.id)
        for document in selected_documents
        if document is not None
        for requirement in document.requirements
    }
    expected_transition_keys = {
        (document.document_id, transition.id)
        for document in selected_documents
        if document is not None
        for transition in document.transitions
    }
    expected_api_surface_keys = {
        (document_id, surface_id)
        for (document_id, mapping_id, target), crosswalk in selected_crosswalks_by_key.items()
        for surface_id in crosswalk.selected_api_surface_ids
        if (document_id, mapping_id, target) in expected_keys
    }
    binding_by_key = {
        (binding.document_id, binding.implementation_mapping_id, binding.target): binding
        for binding in manifest.bindings
    }
    passing_evidence_ids = {
        item.id for item in manifest.evidence if item.status in {"passed", "observed"}
    }
    failed_evidence_ids = {item.id for item in manifest.evidence if item.status == "failed"}
    accepted_evidence_ids = {
        item.id for item in manifest.evidence if item.review_status == "accepted"
    }
    accepted_real_evidence_ids = {
        item.id
        for item in manifest.evidence
        if item.review_status == "accepted" and item.execution_mode == "real"
    }
    unaccepted_evidence_ids = {
        item.id for item in manifest.evidence if item.review_status != "accepted"
    }
    non_real_evidence_ids = {item.id for item in manifest.evidence if item.execution_mode != "real"}
    tested_keys: set[tuple[str, str, str]] = set()
    verified_keys: set[tuple[str, str, str]] = set()
    for key in expected_keys:
        binding = binding_by_key.get(key)
        if binding is None:
            continue
        evidence_ids = set(binding.evidence_ids)
        has_passing_evidence = bool(evidence_ids & passing_evidence_ids)
        has_failed_evidence = bool(evidence_ids & failed_evidence_ids)
        if has_passing_evidence and not has_failed_evidence:
            tested_keys.add(key)
            crosswalk = selected_crosswalks_by_key.get(key)
            selected_surfaces = (
                set(crosswalk.selected_api_surface_ids) if crosswalk is not None else set()
            )
            evidence_ids = set(binding.evidence_ids)
            if (
                binding.status == "verified"
                and crosswalk is not None
                and crosswalk.status == "matched"
                and set(binding.api_surface_ids) == selected_surfaces
                and evidence_ids & accepted_real_evidence_ids
            ):
                verified_keys.add(key)

    def covered_semantic_keys(
        keys: set[tuple[str, str, str]],
        field: str,
    ) -> set[tuple[str, str]]:
        covered: set[tuple[str, str]] = set()
        for document_id, mapping_id, _target in keys:
            mapping = mappings_by_key.get((document_id, mapping_id))
            if mapping is None:
                continue
            covered.update((document_id, identifier) for identifier in getattr(mapping, field))
        return covered

    verified_requirement_keys = covered_semantic_keys(verified_keys, "requirement_ids")
    verified_transition_keys = covered_semantic_keys(verified_keys, "transition_ids")
    verified_api_surface_keys = {
        (document_id, surface_id)
        for document_id, mapping_id, target in verified_keys
        for surface_id in selected_crosswalks_by_key[
            (document_id, mapping_id, target)
        ].selected_api_surface_ids
    }
    coverage = ComplianceCoverage(
        expected_binding_count=len(expected_keys),
        present_binding_count=len(expected_keys & binding_by_key.keys()),
        tested_binding_count=len(tested_keys),
        verified_binding_count=len(verified_keys),
        expected_requirement_count=len(expected_requirement_keys),
        requirements_with_verified_evidence_count=len(
            expected_requirement_keys & verified_requirement_keys
        ),
        expected_transition_count=len(expected_transition_keys),
        transitions_with_verified_evidence_count=len(
            expected_transition_keys & verified_transition_keys
        ),
        expected_api_surface_count=len(expected_api_surface_keys),
        api_surfaces_with_verified_evidence_count=len(
            expected_api_surface_keys & verified_api_surface_keys
        ),
        binding_coverage=_coverage_ratio(len(verified_keys), len(expected_keys)),
        requirement_coverage=_coverage_ratio(
            len(expected_requirement_keys & verified_requirement_keys),
            len(expected_requirement_keys),
        ),
        transition_coverage=_coverage_ratio(
            len(expected_transition_keys & verified_transition_keys),
            len(expected_transition_keys),
        ),
        api_surface_coverage=_coverage_ratio(
            len(expected_api_surface_keys & verified_api_surface_keys),
            len(expected_api_surface_keys),
        ),
        accepted_evidence_count=len(accepted_evidence_ids),
        accepted_real_evidence_count=len(accepted_real_evidence_ids),
        fully_verified=(
            len(verified_keys) == len(expected_keys)
            and expected_requirement_keys <= verified_requirement_keys
            and expected_transition_keys <= verified_transition_keys
            and expected_api_surface_keys <= verified_api_surface_keys
        ),
        untested_binding_keys=tuple(sorted(":".join(key) for key in expected_keys - tested_keys)),
        untested_requirement_ids=tuple(
            sorted(
                f"{document_id}:{requirement_id}"
                for document_id, requirement_id in expected_requirement_keys
                - verified_requirement_keys
            )
        ),
        untested_transition_ids=tuple(
            sorted(
                f"{document_id}:{transition_id}"
                for document_id, transition_id in expected_transition_keys
                - verified_transition_keys
            )
        ),
        unverified_api_surface_ids=tuple(
            sorted(
                f"{document_id}:{surface_id}"
                for document_id, surface_id in expected_api_surface_keys - verified_api_surface_keys
            )
        ),
        unaccepted_evidence_ids=tuple(sorted(unaccepted_evidence_ids)),
        non_real_evidence_ids=tuple(sorted(non_real_evidence_ids)),
    )
    binding_keys = {
        (binding.document_id, binding.implementation_mapping_id, binding.target)
        for binding in manifest.bindings
    }
    if manifest.coverage_mode == "complete":
        for key in sorted(expected_keys - binding_keys):
            findings.append(
                _finding(
                    "missing-implementation-binding",
                    "error",
                    ":".join(key),
                    "complete manifest does not provide an implementation binding",
                )
            )

    for binding in manifest.bindings:
        key = (binding.document_id, binding.implementation_mapping_id, binding.target)
        if binding.document_id not in manifest.document_ids:
            findings.append(
                _finding(
                    "binding-document-not-selected",
                    "error",
                    binding.id,
                    f"binding targets document {binding.document_id}, which is not selected "
                    "by the manifest",
                )
            )
            continue
        mapping = mappings_by_key.get((binding.document_id, binding.implementation_mapping_id))
        crosswalk_entry = crosswalks_by_key.get(key)
        if mapping is None:
            findings.append(
                _finding(
                    "mapping-not-in-bundle",
                    "error",
                    binding.id,
                    "implementation mapping is not present in the selected corpus bundle",
                )
            )
            continue
        if crosswalk_entry is None:
            findings.append(
                _finding(
                    "crosswalk-not-in-bundle",
                    "error",
                    binding.id,
                    "implementation target has no corresponding corpus crosswalk",
                )
            )
            continue
        _, crosswalk = crosswalk_entry
        selected = set(crosswalk.selected_api_surface_ids)
        candidates = set(crosswalk.candidate_api_surface_ids)
        requested_surfaces = set(binding.api_surface_ids)
        if not requested_surfaces <= candidates:
            findings.append(
                _finding(
                    "api-surface-not-candidate",
                    "error",
                    binding.id,
                    f"implementation names surfaces outside crosswalk candidates: "
                    f"{sorted(requested_surfaces - candidates)}",
                )
            )
        if binding.status in {"implemented", "verified"}:
            if crosswalk.status != "matched":
                findings.append(
                    _finding(
                        "binding-on-unresolved-crosswalk",
                        "error",
                        binding.id,
                        f"{binding.status} binding requires a matched crosswalk, "
                        f"found {crosswalk.status}",
                    )
                )
            if not requested_surfaces:
                findings.append(
                    _finding(
                        "binding-missing-api-surface",
                        "error",
                        binding.id,
                        "concrete binding must name its exact API surface IDs",
                    )
                )
            elif requested_surfaces != selected:
                findings.append(
                    _finding(
                        "binding-surface-mismatch",
                        "error",
                        binding.id,
                        f"binding surfaces {sorted(requested_surfaces)} do not equal "
                        f"selected surfaces {sorted(selected)}",
                    )
                )
        elif crosswalk.status != "matched":
            findings.append(
                _finding(
                    "binding-crosswalk-gap",
                    "warning",
                    binding.id,
                    f"binding remains {binding.status} while crosswalk is {crosswalk.status}",
                )
            )
        evidence = tuple(evidence_by_id[item] for item in binding.evidence_ids)
        if binding.status == "verified":
            if not evidence:
                findings.append(
                    _finding(
                        "verified-binding-without-evidence",
                        "error",
                        binding.id,
                        "verified binding must link at least one evidence record",
                    )
                )
            if not any(item.status in {"passed", "observed"} for item in evidence):
                findings.append(
                    _finding(
                        "verified-binding-without-passing-evidence",
                        "error",
                        binding.id,
                        "verified binding needs passed or observed evidence",
                    )
                )
            if not any(
                item.status in {"passed", "observed"}
                and item.review_status == "accepted"
                and item.execution_mode == "real"
                for item in evidence
            ):
                findings.append(
                    _finding(
                        "verified-binding-without-accepted-real-evidence",
                        "error",
                        binding.id,
                        "verified binding needs accepted evidence from a real execution",
                    )
                )
        if any(item.status == "failed" for item in evidence):
            findings.append(
                _finding(
                    "binding-has-failed-evidence",
                    "error",
                    binding.id,
                    "implementation binding links failed evidence",
                )
            )

    coverage = coverage.model_copy(
        update={
            "fully_verified": coverage.fully_verified
            and not any(item.severity == "error" for item in findings)
        }
    )

    binding_counts = dict(Counter(item.status for item in manifest.bindings))
    evidence_counts = dict(Counter(item.status for item in manifest.evidence))
    return ComplianceResult(
        schema_version=1,
        bundle_id=bundle.bundle_id,
        manifest_id=manifest.manifest_id,
        passed=not any(item.severity == "error" for item in findings),
        binding_counts=binding_counts,
        evidence_counts=evidence_counts,
        coverage=coverage,
        findings=tuple(findings),
    )


def verify_files(bundle_path: Path, manifest_path: Path) -> ComplianceResult:
    """Load and verify two portable JSON contracts."""
    bundle = CorpusBundle.model_validate_json(bundle_path.read_text(encoding="utf-8"))
    manifest = ImplementationManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    return verify(bundle, manifest)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = verify_files(args.bundle, args.manifest)
    if args.json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(f"compliance: {'PASS' if result.passed else 'FAIL'}")
        print(f"bindings: {sum(result.binding_counts.values())}")
        print(f"evidence: {sum(result.evidence_counts.values())}")
        print(
            "testing coverage: "
            f"{result.coverage.verified_binding_count}/{result.coverage.expected_binding_count} "
            f"bindings ({result.coverage.binding_coverage:.1%}), "
            f"{result.coverage.requirements_with_verified_evidence_count}/"
            f"{result.coverage.expected_requirement_count} requirements, "
            f"{result.coverage.transitions_with_verified_evidence_count}/"
            f"{result.coverage.expected_transition_count} transitions"
        )
        print(f"fully verified: {result.coverage.fully_verified}")
        for finding in result.findings:
            print(f"{finding.severity}: {finding.code}: {finding.record_id} — {finding.message}")
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
