"""Turn an RTI test catalog and JUnit XML into a raw sidecar response.

The adapter deliberately does not execute tests or inspect a live implementation.
It consumes XML reports already produced by the RTI's own Catch2, Maven, Gradle,
or compatible runner, then emits unreviewed evidence over the portable sidecar
protocol. A protected review step remains responsible for accepting real evidence
and promoting an implementation binding to ``verified``.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from hla_lab.traceability.compliance_contract import (
    AdapterExpectedBinding,
    AdapterRequest,
    AdapterResponse,
    ComplianceTestCase,
    ComplianceTestCatalog,
    EvidenceRecord,
    ImplementationBinding,
)

_EvidenceStatus = Literal["planned", "passed", "failed", "blocked"]
_BindingKey = tuple[str, str, str]


@dataclass(frozen=True)
class JunitCaseResult:
    """One test case observed in a JUnit-compatible XML artifact."""

    status: _EvidenceStatus
    artifact: str


def load_catalog(path: Path) -> ComplianceTestCatalog:
    """Load one strict RTI test catalog."""
    return ComplianceTestCatalog.model_validate_json(path.read_text(encoding="utf-8"))


def _local_name(tag: object) -> str:
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", maxsplit=1)[-1].lower()


def _case_status(case: ElementTree.Element) -> _EvidenceStatus:
    """Normalize common JUnit and Catch2 outcome shapes."""
    descendants = tuple(case.iter())
    names = {_local_name(item.tag) for item in descendants}
    if names & {"failure", "error"}:
        return "failed"
    for item in descendants:
        if _local_name(item.tag) != "overallresult":
            continue
        if item.attrib.get("success", "true").lower() not in {"1", "true", "yes"}:
            return "failed"
    if names & {"skipped", "disabled"} or case.attrib.get("status", "").lower() in {
        "disabled",
        "notrun",
        "skipped",
    }:
        return "blocked"
    return "passed"


def _case_selectors(case: ElementTree.Element) -> tuple[str, ...]:
    name = case.attrib.get("name", "").strip()
    classname = case.attrib.get("classname", "").strip()
    selectors = [name]
    if classname and name:
        selectors.extend((f"{classname}#{name}", f"{classname}.{name}"))
    return tuple(item for item in dict.fromkeys(selectors) if item)


def parse_junit_results(paths: Iterable[Path]) -> dict[str, tuple[JunitCaseResult, ...]]:
    """Index JUnit-compatible case results by their stable result selectors."""
    results: dict[str, list[JunitCaseResult]] = defaultdict(list)
    for path in paths:
        root = ElementTree.parse(path).getroot()
        for case in root.iter():
            if _local_name(case.tag) != "testcase":
                continue
            result = JunitCaseResult(status=_case_status(case), artifact=str(path))
            for selector in _case_selectors(case):
                results[selector].append(result)
    return {selector: tuple(items) for selector, items in results.items()}


def _expected_bindings(request: AdapterRequest) -> dict[_BindingKey, AdapterExpectedBinding]:
    expected: dict[_BindingKey, AdapterExpectedBinding] = {}
    for document in request.documents:
        for binding in document.bindings:
            key = (document.document_id, binding.implementation_mapping_id, binding.target)
            if key in expected:
                raise ValueError(f"adapter request has duplicate expected binding {':'.join(key)}")
            expected[key] = binding
    return expected


def _test_key(test: ComplianceTestCase) -> _BindingKey:
    return (test.document_id, test.implementation_mapping_id, test.target)


def _validate_catalog(request: AdapterRequest, catalog: ComplianceTestCatalog) -> None:
    expected = _expected_bindings(request)
    requirements_by_document = {
        document.document_id: {item.id for item in document.requirements}
        for document in request.documents
    }
    grouped: dict[_BindingKey, list[ComplianceTestCase]] = defaultdict(list)
    for test in catalog.tests:
        key = _test_key(test)
        binding = expected.get(key)
        if binding is None:
            raise ValueError(
                f"catalog test {test.id} references binding outside the request: {':'.join(key)}"
            )
        if binding.crosswalk_status != "matched" or not binding.selected_api_surface_ids:
            raise ValueError(
                f"catalog test {test.id} needs a matched crosswalk with an exact API surface: "
                f"{':'.join(key)}"
            )
        if test.language != binding.language:
            raise ValueError(
                f"catalog test {test.id} language {test.language} does not match expected "
                f"language {binding.language}"
            )
        if set(test.api_surface_ids) != set(binding.selected_api_surface_ids):
            raise ValueError(
                f"catalog test {test.id} API surfaces must exactly match the selected "
                f"crosswalk surfaces for {':'.join(key)}"
            )
        if test.requirement_ids:
            missing = set(test.requirement_ids) - requirements_by_document.get(test.document_id, set())
            if missing:
                raise ValueError(
                    f"catalog test {test.id} references missing requirements: {sorted(missing)}"
                )
            if set(test.requirement_ids) != set(binding.requirement_ids):
                raise ValueError(
                    f"catalog test {test.id} requirement IDs must exactly match the "
                    f"implementation mapping requirements for {':'.join(key)}"
                )
        grouped[key].append(test)

    for key, tests in grouped.items():
        first = tests[0]
        for test in tests[1:]:
            if test.symbol != first.symbol:
                raise ValueError(
                    f"catalog tests for {':'.join(key)} must use one implementation symbol"
                )


def _result_for(
    test: ComplianceTestCase,
    results: dict[str, tuple[JunitCaseResult, ...]],
) -> JunitCaseResult | None:
    matches = results.get(test.result_selector, ())
    if len(matches) > 1:
        artifacts = sorted({item.artifact for item in matches})
        raise ValueError(
            f"catalog test {test.id} result selector {test.result_selector!r} is ambiguous "
            f"across {artifacts}"
        )
    return matches[0] if matches else None


def response_from_catalog(
    request: AdapterRequest,
    catalog: ComplianceTestCatalog,
    results: dict[str, tuple[JunitCaseResult, ...]],
    *,
    adapter_id: str,
    repository: str,
) -> AdapterResponse:
    """Build a raw, unreviewed adapter response from cataloged test results."""
    _validate_catalog(request, catalog)
    expected = _expected_bindings(request)
    grouped: dict[_BindingKey, list[tuple[ComplianceTestCase, EvidenceRecord]]] = defaultdict(list)
    for test in catalog.tests:
        result = _result_for(test, results)
        notes = (
            f"runner={test.runner}; selector={test.selector}; "
            f"result_selector={test.result_selector}"
        )
        if result is None:
            status: _EvidenceStatus = "planned"
            artifact = None
            notes += "; no matching JUnit testcase was found"
        else:
            status = result.status
            artifact = result.artifact
        record = EvidenceRecord(
            id=test.id,
            kind=test.kind,
            status=status,
            execution_mode=test.execution_mode,
            requirement_ids=test.requirement_ids or expected[_test_key(test)].requirement_ids,
            command=test.command,
            artifact=artifact,
            notes=notes if not test.notes else f"{notes}; {test.notes}",
        )
        grouped[_test_key(test)].append((test, record))

    bindings: list[ImplementationBinding] = []
    all_evidence: list[EvidenceRecord] = []
    for key in sorted(grouped):
        tests_and_evidence = grouped[key]
        first_test = tests_and_evidence[0][0]
        evidence_records = tuple(item[1] for item in tests_and_evidence)
        statuses = {item.status for item in evidence_records}
        has_real_pass = any(
            item.status == "passed" and item.execution_mode == "real" for item in evidence_records
        )
        if has_real_pass:
            binding_status = "implemented"
        elif "passed" in statuses or "failed" in statuses:
            binding_status = "partial"
        else:
            binding_status = "planned"
        document_id, mapping_id, target = key
        bindings.append(
            ImplementationBinding(
                id=f"{adapter_id}.{document_id}.{mapping_id}.{target}",
                document_id=document_id,
                implementation_mapping_id=mapping_id,
                target=target,
                symbol=first_test.symbol,
                language=first_test.language,
                status=binding_status,
                requirement_ids=(
                    first_test.requirement_ids
                    or expected[key].requirement_ids
                ),
                api_surface_ids=first_test.api_surface_ids,
                evidence_ids=tuple(item.id for item in evidence_records),
                notes="Generated from RTI-owned JUnit results; evidence remains unreviewed.",
            )
        )
        all_evidence.extend(evidence_records)

    return AdapterResponse(
        schema_version=1,
        request_id=request.request_id,
        adapter_id=adapter_id,
        repository=repository,
        coverage_mode="complete" if set(grouped) == set(expected) else "partial",
        bindings=tuple(bindings),
        evidence=tuple(all_evidence),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument(
        "--results",
        type=Path,
        action="append",
        required=True,
        help="JUnit XML result file; repeat for multiple runner outputs",
    )
    parser.add_argument("--repository", required=True)
    parser.add_argument("--adapter-id", default="junit-results-adapter")
    args = parser.parse_args()
    try:
        request = AdapterRequest.model_validate_json(sys.stdin.read())
        response = response_from_catalog(
            request,
            load_catalog(args.catalog),
            parse_junit_results(args.results),
            adapter_id=args.adapter_id,
            repository=args.repository,
        )
    except (ElementTree.ParseError, OSError, ValueError) as error:
        print(f"junit adapter: {error}", file=sys.stderr)
        return 2
    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
