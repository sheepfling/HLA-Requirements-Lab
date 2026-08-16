"""Prepare and verify a language-neutral external compliance adapter exchange."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from pathlib import Path

from hla_lab.core.io import write_json
from hla_lab.publication.verify_compliance_bundle import verify
from hla_lab.traceability.compliance_contract import (
    AdapterDocumentRequest,
    AdapterExpectedBinding,
    AdapterRequest,
    AdapterResponse,
    ComplianceResult,
    CorpusBundle,
    ImplementationManifest,
)


def load_bundle(path: Path) -> CorpusBundle:
    """Load a portable corpus bundle."""
    return CorpusBundle.model_validate_json(path.read_text(encoding="utf-8"))


def build_adapter_request(bundle: CorpusBundle, request_id: str) -> AdapterRequest:
    """Project only the binding information an external adapter needs."""
    documents: list[AdapterDocumentRequest] = []
    for document in bundle.documents:
        mappings = {item.id: item for item in document.mappings}
        surfaces = {item.id: item for item in document.api_surfaces}
        expected: list[AdapterExpectedBinding] = []
        for crosswalk in document.api_crosswalks:
            mapping = mappings[crosswalk.implementation_mapping_id]
            expected.append(
                AdapterExpectedBinding(
                    implementation_mapping_id=mapping.id,
                    target=crosswalk.target,
                    binding_kind=crosswalk.binding_kind,
                    language=crosswalk.language,
                    interface_kind=mapping.interface_kind,
                    interface_name=mapping.interface_name,
                    crosswalk_status=crosswalk.status,
                    requirement_ids=mapping.requirement_ids,
                    transition_ids=mapping.transition_ids,
                    candidate_api_surface_ids=crosswalk.candidate_api_surface_ids,
                    selected_api_surface_ids=crosswalk.selected_api_surface_ids,
                    api_surfaces=tuple(
                        surfaces[item_id] for item_id in crosswalk.candidate_api_surface_ids
                    ),
                )
            )
        documents.append(
            AdapterDocumentRequest(
                document_id=document.document_id,
                bindings=tuple(sorted(expected, key=lambda item: item.implementation_mapping_id)),
            )
        )
    return AdapterRequest(
        schema_version=1,
        request_id=request_id,
        bundle_id=bundle.bundle_id,
        corpus_revision=bundle.corpus_revision,
        documents=tuple(documents),
    )


def manifest_from_response(
    request: AdapterRequest,
    response: AdapterResponse,
) -> ImplementationManifest:
    """Turn an adapter response into the verifier's canonical manifest."""
    if response.request_id != request.request_id:
        raise ValueError(
            f"adapter response request ID {response.request_id} does not match {request.request_id}"
        )
    return ImplementationManifest(
        schema_version=1,
        manifest_id=f"{response.adapter_id}.{request.request_id}",
        repository=response.repository,
        corpus_revision=request.corpus_revision,
        document_ids=tuple(item.document_id for item in request.documents),
        targets=tuple(
            sorted(
                {binding.target for document in request.documents for binding in document.bindings}
            )
        ),
        coverage_mode=response.coverage_mode,
        bindings=response.bindings,
        evidence=response.evidence,
    )


def run_adapter(command: Sequence[str], request: AdapterRequest) -> AdapterResponse:
    """Send one JSON request to an external executable and parse its stdout."""
    if not command:
        raise ValueError("adapter command cannot be empty")
    completed = subprocess.run(
        tuple(command),
        input=json.dumps(request.model_dump(mode="json")),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or "adapter returned a non-zero exit code"
        raise RuntimeError(detail)
    try:
        return AdapterResponse.model_validate_json(completed.stdout)
    except ValueError as error:
        raise ValueError("adapter stdout was not a valid AdapterResponse JSON document") from error


_write_json = write_json


def _print_result(result: ComplianceResult, as_json: bool) -> None:
    if as_json:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Create an AdapterRequest JSON document")
    prepare.add_argument("--bundle", type=Path, required=True)
    prepare.add_argument("--request-id", default="compliance-request")
    prepare.add_argument("--output", type=Path)

    check = subparsers.add_parser("check", help="Verify a manifest or run an external adapter")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--manifest", type=Path)
    check.add_argument("--adapter-response", type=Path)
    check.add_argument("--manifest-output", type=Path)
    check.add_argument("--request-id", default="compliance-request")
    check.add_argument("--json", action="store_true")
    check.add_argument(
        "--adapter-command",
        nargs=argparse.REMAINDER,
        help="Executable and arguments; adapter receives JSON on stdin and returns JSON on stdout",
    )

    args = parser.parse_args()
    if args.command == "prepare":
        request = build_adapter_request(
            load_bundle(args.bundle),
            args.request_id,
        )
        if args.output:
            _write_json(args.output, request)
            print(f"wrote adapter request to {args.output}")
        else:
            print(json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    modes = sum(
        item is not None for item in (args.manifest, args.adapter_response, args.adapter_command)
    )
    if modes != 1:
        parser.error(
            "check requires exactly one of --manifest, --adapter-response, or --adapter-command"
        )
    bundle = load_bundle(args.bundle)
    if args.manifest is not None:
        manifest = ImplementationManifest.model_validate_json(
            args.manifest.read_text(encoding="utf-8")
        )
    elif args.adapter_response is not None:
        request = build_adapter_request(bundle, args.request_id)
        response = AdapterResponse.model_validate_json(
            args.adapter_response.read_text(encoding="utf-8")
        )
        manifest = manifest_from_response(request, response)
        if args.manifest_output:
            _write_json(args.manifest_output, manifest)
    else:
        request = build_adapter_request(bundle, args.request_id)
        command = tuple(args.adapter_command)
        if command and command[0] == "--":
            command = command[1:]
        response = run_adapter(command, request)
        manifest = manifest_from_response(request, response)
        if args.manifest_output:
            _write_json(args.manifest_output, manifest)
    result = verify(bundle, manifest)
    _print_result(result, args.json)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
