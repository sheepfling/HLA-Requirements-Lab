"""Contracts for consuming the corpus from an external RTI repository."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hla_lab.publication.verify_compliance_bundle import verify
from hla_lab.traceability.compliance_contract import (
    AdapterResponse,
    BundleCrosswalk,
    BundleDocument,
    BundleMapping,
    BundleRequirement,
    BundleSurface,
    BundleTransition,
    ComplianceResult,
    CorpusBundle,
    EvidenceRecord,
    ImplementationBinding,
    ImplementationManifest,
)
from hla_lab.traceability.compliance_sidecar import (
    build_adapter_request,
    manifest_from_response,
    run_adapter,
)
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT


def _bundle(*, crosswalk_status: str = "matched") -> CorpusBundle:
    surface = BundleSurface(
        id="api.cpp.connect",
        name="connect",
        binding_kind="native",
        owner="RTIambassador",
        language="cpp",
        signature="virtual void connect();",
    )
    crosswalk = BundleCrosswalk(
        id="crosswalk.m-1.cpp",
        implementation_mapping_id="m-1",
        target="cpp",
        binding_kind="native",
        language="cpp",
        status=crosswalk_status,  # type: ignore[arg-type]
        candidate_api_surface_ids=(surface.id,) if crosswalk_status == "matched" else (),
        selected_api_surface_ids=(surface.id,) if crosswalk_status == "matched" else (),
    )
    return CorpusBundle(
        schema_version=1,
        bundle_id="test-bundle",
        corpus_revision="rev-1",
        documents=(
            BundleDocument(
                document_id="doc-1",
                requirements=(
                    BundleRequirement(
                        id="req-1",
                        clause_id="clause-1",
                        title="Connect",
                        statement="The RTI shall connect.",
                    ),
                ),
                transitions=(
                    BundleTransition(
                        id="transition-1",
                        machine_id="machine-1",
                        event="Connect",
                        requirement_ids=("req-1",),
                    ),
                ),
                mappings=(
                    BundleMapping(
                        id="m-1",
                        interface_kind="service",
                        interface_name="Connect",
                        requirement_ids=("req-1",),
                        transition_ids=("transition-1",),
                    ),
                ),
                api_surfaces=(surface,),
                api_crosswalks=(crosswalk,),
            ),
        ),
    )


def _manifest(*, status: str = "verified", evidence: bool = True) -> ImplementationManifest:
    return ImplementationManifest(
        schema_version=1,
        manifest_id="rti-test",
        repository="example/rti",
        corpus_revision="rev-1",
        document_ids=("doc-1",),
        targets=("cpp",),
        bindings=(
            ImplementationBinding(
                id="binding-1",
                document_id="doc-1",
                implementation_mapping_id="m-1",
                target="cpp",
                symbol="RTI::RTIambassador::connect",
                language="cpp",
                status=status,  # type: ignore[arg-type]
                api_surface_ids=("api.cpp.connect",),
                evidence_ids=("evidence-1",) if evidence else (),
            ),
        ),
        evidence=(
            EvidenceRecord(
                id="evidence-1",
                kind="integration-test",
                status="passed",
                execution_mode="real",
                review_status="accepted",
                reviewer="compliance-review",
                reviewed_at="2026-08-15T00:00:00Z",
                command="ctest --test-dir build",
            ),
        )
        if evidence
        else (),
    )


class ExternalComplianceTests(unittest.TestCase):
    def test_verified_external_manifest_passes(self) -> None:
        result = verify(_bundle(), _manifest())
        self.assertTrue(result.passed)
        self.assertEqual(result.binding_counts, {"verified": 1})
        self.assertEqual(result.evidence_counts, {"passed": 1})
        self.assertEqual(result.coverage.verified_binding_count, 1)
        self.assertEqual(result.coverage.requirements_with_verified_evidence_count, 1)
        self.assertEqual(result.coverage.transitions_with_verified_evidence_count, 1)
        self.assertEqual(result.coverage.api_surfaces_with_verified_evidence_count, 1)
        self.assertTrue(result.coverage.fully_verified)

    def test_planned_binding_is_reported_as_unverified_coverage(self) -> None:
        result = verify(_bundle(), _manifest(status="planned"))
        self.assertTrue(result.passed)
        self.assertEqual(result.coverage.verified_binding_count, 0)
        self.assertEqual(result.coverage.binding_coverage, 0)
        self.assertEqual(result.coverage.untested_binding_keys, ())
        self.assertFalse(result.coverage.fully_verified)

    def test_verified_binding_requires_accepted_real_evidence(self) -> None:
        manifest = _manifest().model_copy(
            update={
                "evidence": (
                    _manifest()
                    .evidence[0]
                    .model_copy(
                        update={
                            "review_status": "unreviewed",
                            "reviewer": None,
                            "reviewed_at": None,
                        }
                    ),
                )
            }
        )
        result = verify(_bundle(), manifest)
        self.assertFalse(result.passed)
        self.assertIn(
            "verified-binding-without-accepted-real-evidence",
            {item.code for item in result.findings},
        )

    def test_verified_binding_rejects_accepted_mocked_evidence(self) -> None:
        manifest = _manifest().model_copy(
            update={
                "evidence": (
                    _manifest().evidence[0].model_copy(update={"execution_mode": "mocked"}),
                )
            }
        )
        result = verify(_bundle(), manifest)
        self.assertFalse(result.passed)
        self.assertIn(
            "verified-binding-without-accepted-real-evidence",
            {item.code for item in result.findings},
        )
        self.assertEqual(result.coverage.non_real_evidence_ids, ("evidence-1",))

    def test_accepted_evidence_requires_a_reviewer_and_timestamp(self) -> None:
        with self.assertRaisesRegex(ValueError, "must name a reviewer"):
            EvidenceRecord(
                id="unreviewed-acceptance",
                kind="integration-test",
                status="passed",
                execution_mode="real",
                review_status="accepted",
            )

    def test_adapter_response_cannot_accept_its_own_evidence(self) -> None:
        with self.assertRaises(ValueError):
            AdapterResponse(
                schema_version=1,
                request_id="request-1",
                adapter_id="adapter-1",
                repository="example/rti",
                evidence=(_manifest().evidence[0],),
            )

    def test_sidecar_rejects_an_adapter_response_for_another_request(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        response = AdapterResponse(
            schema_version=1,
            request_id="other-request",
            adapter_id="adapter-1",
            repository="example/rti",
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            manifest_from_response(request, response)

    def test_complete_manifest_reports_missing_binding(self) -> None:
        manifest = _manifest()
        manifest = manifest.model_copy(update={"bindings": ()})
        result = verify(_bundle(), manifest)
        self.assertFalse(result.passed)
        self.assertIn(
            "missing-implementation-binding",
            {item.code for item in result.findings},
        )

    def test_concrete_binding_cannot_claim_unresolved_crosswalk(self) -> None:
        result = verify(_bundle(crosswalk_status="unmatched"), _manifest())
        self.assertFalse(result.passed)
        self.assertIn(
            "binding-on-unresolved-crosswalk",
            {item.code for item in result.findings},
        )

    def test_binding_outside_manifest_document_scope_fails(self) -> None:
        manifest = _manifest().model_copy(
            update={
                "bindings": (
                    ImplementationBinding(
                        id="binding-other-document",
                        document_id="doc-2",
                        implementation_mapping_id="m-1",
                        target="cpp",
                        symbol="RTI::RTIambassador::connect",
                        language="cpp",
                        status="verified",
                        api_surface_ids=("api.cpp.connect",),
                        evidence_ids=("evidence-1",),
                    ),
                )
            }
        )
        result = verify(_bundle(), manifest)
        self.assertFalse(result.passed)
        self.assertIn(
            "binding-document-not-selected",
            {item.code for item in result.findings},
        )

    def test_cli_round_trips_portable_json_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle_path = directory / "bundle.json"
            manifest_path = directory / "manifest.json"
            bundle_path.write_text(json.dumps(_bundle().model_dump(mode="json")), encoding="utf-8")
            manifest_path.write_text(
                json.dumps(_manifest().model_dump(mode="json")), encoding="utf-8"
            )
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "hla_lab.publication.verify_compliance_bundle",
                    "--bundle",
                    str(bundle_path),
                    "--manifest",
                    str(manifest_path),
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = ComplianceResult.model_validate_json(result.stdout)
            self.assertTrue(payload.passed)

    def test_external_adapter_protocol_can_return_a_verified_manifest(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        adapter_code = (
            "import json, sys; "
            "request=json.load(sys.stdin); "
            "expected=request['documents'][0]['bindings'][0]; "
            "print(json.dumps({"
            "'schema_version': 1, "
            "'request_id': request['request_id'], "
            "'adapter_id': 'test-adapter', "
            "'repository': 'example/rti', "
            "'coverage_mode': 'complete', "
            "'bindings': [{"
            "'id': 'binding-1', "
            "'document_id': 'doc-1', "
            "'implementation_mapping_id': expected['implementation_mapping_id'], "
            "'target': expected['target'], "
            "'symbol': 'RTI::RTIambassador::connect', "
            "'language': 'cpp', "
            "'status': 'implemented', "
            "'api_surface_ids': expected['selected_api_surface_ids'], "
            "'evidence_ids': ['evidence-1']}], "
            "'evidence': [{"
            "'id': 'evidence-1', "
            "'kind': 'integration-test', "
            "'status': 'passed'}]}))"
        )
        response = run_adapter((sys.executable, "-c", adapter_code), request)
        self.assertIsInstance(response, AdapterResponse)
        manifest = manifest_from_response(request, response)
        self.assertTrue(verify(_bundle(), manifest).passed)

    def test_sidecar_cli_runs_adapter_and_writes_manifest(self) -> None:
        adapter_code = (
            "import json, sys; "
            "request=json.load(sys.stdin); "
            "expected=request['documents'][0]['bindings'][0]; "
            "print(json.dumps({"
            "'schema_version': 1, "
            "'request_id': request['request_id'], "
            "'adapter_id': 'cli-adapter', "
            "'repository': 'example/rti', "
            "'coverage_mode': 'complete', "
            "'bindings': [{"
            "'id': 'binding-1', "
            "'document_id': 'doc-1', "
            "'implementation_mapping_id': expected['implementation_mapping_id'], "
            "'target': expected['target'], "
            "'symbol': 'RTI::RTIambassador::connect', "
            "'language': 'cpp', "
            "'status': 'implemented', "
            "'api_surface_ids': expected['selected_api_surface_ids'], "
            "'evidence_ids': ['evidence-1']}], "
            "'evidence': [{"
            "'id': 'evidence-1', "
            "'kind': 'integration-test', "
            "'status': 'passed'}]}))"
        )
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle_path = directory / "bundle.json"
            manifest_path = directory / "manifest.json"
            bundle_path.write_text(json.dumps(_bundle().model_dump(mode="json")), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "hla_lab.traceability.compliance_sidecar",
                    "check",
                    "--bundle",
                    str(bundle_path),
                    "--manifest-output",
                    str(manifest_path),
                    "--json",
                    "--adapter-command",
                    sys.executable,
                    "-c",
                    adapter_code,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = ComplianceResult.model_validate_json(result.stdout)
            self.assertTrue(payload.passed)
            self.assertTrue(manifest_path.exists())
            manifest = ImplementationManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            self.assertEqual(manifest.manifest_id, "cli-adapter.compliance-request")

    def test_sidecar_cli_checks_saved_adapter_response(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle_path = directory / "bundle.json"
            response_path = directory / "response.json"
            manifest_path = directory / "manifest.json"
            bundle_path.write_text(json.dumps(_bundle().model_dump(mode="json")), encoding="utf-8")
            raw_binding = _manifest().bindings[0].model_copy(update={"status": "implemented"})
            raw_evidence = (
                _manifest()
                .evidence[0]
                .model_copy(
                    update={"review_status": "unreviewed", "reviewer": None, "reviewed_at": None}
                )
            )
            response = AdapterResponse(
                schema_version=1,
                request_id="saved-request",
                adapter_id="saved-adapter",
                repository="example/rti",
                bindings=(raw_binding,),
                evidence=(raw_evidence,),
            )
            response_path.write_text(json.dumps(response.model_dump(mode="json")), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "hla_lab.traceability.compliance_sidecar",
                    "check",
                    "--bundle",
                    str(bundle_path),
                    "--request-id",
                    "saved-request",
                    "--adapter-response",
                    str(response_path),
                    "--manifest-output",
                    str(manifest_path),
                    "--json",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            payload = ComplianceResult.model_validate_json(result.stdout)
            self.assertTrue(payload.passed)
            self.assertEqual(
                ImplementationManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                ).manifest_id,
                "saved-adapter.saved-request",
            )


if __name__ == "__main__":
    unittest.main()
