"""Contract tests for the portable Catch2/JUnit test-result adapter."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from hla_lab.publication.verify_compliance_bundle import verify
from hla_lab.traceability.compliance_contract import (
    BundleCrosswalk,
    BundleDocument,
    BundleMapping,
    BundleRequirement,
    BundleSurface,
    ComplianceTestCatalog,
    CorpusBundle,
)
from hla_lab.traceability.compliance_sidecar import build_adapter_request, manifest_from_response
from hla_lab.traceability.junit_adapter import parse_junit_results, response_from_catalog

ROOT = Path(__file__).resolve().parents[1]


def _bundle() -> CorpusBundle:
    surface = BundleSurface(
        id="api.cpp.connect",
        name="connect",
        binding_kind="native",
        owner="RTIambassador",
        language="cpp",
        signature="virtual void connect();",
    )
    return CorpusBundle(
        schema_version=1,
        bundle_id="test-bundle",
        corpus_revision="rev-1",
        documents=(
            BundleDocument(
                document_id="doc-1",
                requirements=(BundleRequirement(id="req-1"),),
                mappings=(
                    BundleMapping(
                        id="m-1",
                        interface_kind="service",
                        interface_name="Connect",
                        requirement_ids=("req-1",),
                    ),
                ),
                api_surfaces=(surface,),
                api_crosswalks=(
                    BundleCrosswalk(
                        id="crosswalk.m-1.cpp",
                        implementation_mapping_id="m-1",
                        target="cpp",
                        binding_kind="native",
                        language="cpp",
                        status="matched",
                        candidate_api_surface_ids=(surface.id,),
                        selected_api_surface_ids=(surface.id,),
                    ),
                ),
            ),
        ),
    )


def _java_bundle() -> CorpusBundle:
    surface = BundleSurface(
        id="api.java.connect",
        name="connect",
        binding_kind="language-adapter",
        owner="RtiAmbassador",
        language="java",
        signature="void connect();",
    )
    return CorpusBundle(
        schema_version=1,
        bundle_id="java-test-bundle",
        corpus_revision="rev-1",
        documents=(
            BundleDocument(
                document_id="doc-java-1",
                requirements=(BundleRequirement(id="req-java-1"),),
                mappings=(
                    BundleMapping(
                        id="m-java-1",
                        interface_kind="service",
                        interface_name="Connect",
                        requirement_ids=("req-java-1",),
                    ),
                ),
                api_surfaces=(surface,),
                api_crosswalks=(
                    BundleCrosswalk(
                        id="crosswalk.m-java-1.java",
                        implementation_mapping_id="m-java-1",
                        target="java",
                        binding_kind="language-adapter",
                        language="java",
                        status="matched",
                        candidate_api_surface_ids=(surface.id,),
                        selected_api_surface_ids=(surface.id,),
                    ),
                ),
            ),
        ),
    )


def _two_binding_bundle() -> CorpusBundle:
    bundle = _bundle()
    document = bundle.documents[0]
    surface = BundleSurface(
        id="api.cpp.disconnect",
        name="disconnect",
        binding_kind="native",
        owner="RTIambassador",
        language="cpp",
        signature="virtual void disconnect();",
    )
    expanded_document = document.model_copy(
        update={
            "requirements": (*document.requirements, BundleRequirement(id="req-2")),
            "mappings": (
                *document.mappings,
                BundleMapping(
                    id="m-2",
                    interface_kind="service",
                    interface_name="Disconnect",
                    requirement_ids=("req-2",),
                ),
            ),
            "api_surfaces": (*document.api_surfaces, surface),
            "api_crosswalks": (
                *document.api_crosswalks,
                BundleCrosswalk(
                    id="crosswalk.m-2.cpp",
                    implementation_mapping_id="m-2",
                    target="cpp",
                    binding_kind="native",
                    language="cpp",
                    status="matched",
                    candidate_api_surface_ids=(surface.id,),
                    selected_api_surface_ids=(surface.id,),
                ),
            ),
        }
    )
    return bundle.model_copy(update={"documents": (expanded_document,)})


def _catalog(
    *,
    selector: str = "example.rti.ConnectIT#connect",
    requirement_ids: tuple[str, ...] = ("req-1",),
) -> ComplianceTestCatalog:
    return ComplianceTestCatalog.model_validate(
        {
            "schema_version": 1,
            "tests": [
                {
                    "id": "cpp-connect-integration",
                    "kind": "integration-test",
                    "runner": "catch2",
                    "selector": "[compliance][rti.service.connect]",
                    "result_selector": selector,
                    "command": "build/rti_tests.exe [compliance] --reporter junit",
                    "document_id": "doc-1",
                    "implementation_mapping_id": "m-1",
                    "target": "cpp",
                    "language": "cpp",
                    "symbol": "RTI::RTIambassador::connect",
                    "api_surface_ids": ["api.cpp.connect"],
                    "requirement_ids": list(requirement_ids),
                    "execution_mode": "real",
                }
            ],
        }
    )


def _write_result(
    path: Path,
    body: str = "",
    *,
    classname: str = "example.rti.ConnectIT",
    name: str = "connect",
) -> None:
    path.write_text(
        f'<testsuite><testcase classname="{classname}" name="{name}">{body}</testcase></testsuite>',
        encoding="utf-8",
    )


class JunitAdapterTests(unittest.TestCase):
    def test_junit_result_creates_unreviewed_implemented_binding(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        self.assertEqual(
            [item.id for item in request.documents[0].requirements],
            ["req-1"],
        )
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "results.xml"
            _write_result(result_path)
            response = response_from_catalog(
                request,
                _catalog(),
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

        self.assertEqual(response.coverage_mode, "complete")
        self.assertEqual(response.bindings[0].status, "implemented")
        self.assertEqual(response.evidence[0].status, "passed")
        self.assertEqual(response.evidence[0].execution_mode, "real")
        self.assertEqual(response.evidence[0].review_status, "unreviewed")
        self.assertEqual(response.evidence[0].requirement_ids, ("req-1",))
        self.assertEqual(response.bindings[0].requirement_ids, ("req-1",))
        manifest = manifest_from_response(request, response)
        result = verify(_bundle(), manifest)
        self.assertTrue(result.passed)
        self.assertFalse(result.coverage.fully_verified)

    def test_reviewed_promotion_of_raw_junit_result_becomes_fully_verified(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "results.xml"
            _write_result(result_path)
            response = response_from_catalog(
                request,
                _catalog(),
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

        raw_manifest = manifest_from_response(request, response)
        promoted_manifest = raw_manifest.model_copy(
            update={
                "bindings": (raw_manifest.bindings[0].model_copy(update={"status": "verified"}),),
                "evidence": (
                    raw_manifest.evidence[0].model_copy(
                        update={
                            "review_status": "accepted",
                            "reviewer": "protected-compliance-ci",
                            "reviewed_at": "2026-08-16T00:00:00Z",
                        }
                    ),
                ),
            }
        )
        result = verify(_bundle(), promoted_manifest)
        self.assertTrue(result.passed)
        self.assertTrue(result.coverage.fully_verified)

    def test_failed_junit_result_keeps_binding_partial_and_fails_verification(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "results.xml"
            _write_result(result_path, '<failure message="connection failed" />')
            response = response_from_catalog(
                request,
                _catalog(),
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

        self.assertEqual(response.bindings[0].status, "partial")
        self.assertEqual(response.evidence[0].status, "failed")
        result = verify(_bundle(), manifest_from_response(request, response))
        self.assertFalse(result.passed)
        self.assertIn("binding-has-failed-evidence", {item.code for item in result.findings})

    def test_missing_result_remains_planned(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "results.xml"
            _write_result(result_path)
            response = response_from_catalog(
                request,
                _catalog(selector="absent-testcase"),
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

        self.assertEqual(response.bindings[0].status, "planned")
        self.assertEqual(response.evidence[0].status, "planned")
        self.assertIn("no matching JUnit testcase", response.evidence[0].notes)

    def test_skipped_junit_result_is_blocked_and_does_not_claim_implementation(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "results.xml"
            _write_result(result_path, "<skipped />")
            response = response_from_catalog(
                request,
                _catalog(),
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

        self.assertEqual(response.bindings[0].status, "planned")
        self.assertEqual(response.evidence[0].status, "blocked")

    def test_catch2_overall_result_failure_is_not_misread_as_a_passing_test(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "catch2-results.xml"
            _write_result(
                result_path,
                '<OverallResult success="false" />',
                classname="",
                name="RTIambassador connect",
            )
            response = response_from_catalog(
                request,
                _catalog(selector="RTIambassador connect"),
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

        self.assertEqual(response.bindings[0].status, "partial")
        self.assertEqual(response.evidence[0].status, "failed")

    def test_junit5_class_and_method_selector_maps_java_surface(self) -> None:
        bundle = _java_bundle()
        request = build_adapter_request(bundle, "request-java-1")
        base_test = _catalog(selector="example.rti.RtiAmbassadorIT#connect").tests[0]
        catalog = ComplianceTestCatalog(
            schema_version=1,
            tests=(
                base_test.model_copy(
                    update={
                        "id": "java-connect-integration",
                        "runner": "junit5",
                        "document_id": "doc-java-1",
                        "implementation_mapping_id": "m-java-1",
                        "target": "java",
                        "language": "java",
                        "symbol": "example.rti.RtiAmbassador#connect",
                        "api_surface_ids": ("api.java.connect",),
                        "requirement_ids": ("req-java-1",),
                    }
                ),
            ),
        )
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "surefire.xml"
            _write_result(result_path, classname="example.rti.RtiAmbassadorIT")
            response = response_from_catalog(
                request,
                catalog,
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/java-rti",
            )
            dotted_catalog = catalog.model_copy(
                update={
                    "tests": (
                        catalog.tests[0].model_copy(
                            update={"result_selector": "example.rti.RtiAmbassadorIT.connect"}
                        ),
                    )
                }
            )
            dotted_response = response_from_catalog(
                request,
                dotted_catalog,
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/java-rti",
            )

        self.assertEqual(response.coverage_mode, "complete")
        self.assertEqual(response.bindings[0].language, "java")
        self.assertEqual(response.bindings[0].api_surface_ids, ("api.java.connect",))
        self.assertEqual(dotted_response.evidence[0].status, "passed")

    def test_ambiguous_result_selector_across_artifacts_is_rejected(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first_path = directory / "first.xml"
            second_path = directory / "second.xml"
            _write_result(first_path)
            _write_result(second_path)
            with self.assertRaisesRegex(ValueError, "is ambiguous"):
                response_from_catalog(
                    request,
                    _catalog(),
                    parse_junit_results((first_path, second_path)),
                    adapter_id="junit-results-adapter",
                    repository="example/rti",
                )

    def test_incomplete_catalog_emits_partial_coverage_without_a_false_complete_claim(self) -> None:
        bundle = _two_binding_bundle()
        request = build_adapter_request(bundle, "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            result_path = Path(temporary) / "results.xml"
            _write_result(result_path)
            response = response_from_catalog(
                request,
                _catalog(),
                parse_junit_results((result_path,)),
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

        self.assertEqual(response.coverage_mode, "partial")
        result = verify(bundle, manifest_from_response(request, response))
        self.assertTrue(result.passed)
        self.assertEqual(result.coverage.expected_binding_count, 2)
        self.assertEqual(result.coverage.present_binding_count, 1)
        self.assertFalse(result.coverage.fully_verified)

    def test_catalog_rejects_language_that_disagrees_with_request(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        catalog = _catalog().model_copy(
            update={"tests": (_catalog().tests[0].model_copy(update={"language": "java"}),)}
        )
        with self.assertRaisesRegex(ValueError, "does not match expected language"):
            response_from_catalog(
                request,
                catalog,
                {},
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

    def test_catalog_rejects_api_surface_that_disagrees_with_request(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        catalog = _catalog().model_copy(
            update={
                "tests": (
                    _catalog().tests[0].model_copy(update={"api_surface_ids": ("wrong-api",)}),
                )
            }
        )
        with self.assertRaisesRegex(ValueError, "must exactly match"):
            response_from_catalog(
                request,
                catalog,
                {},
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

    def test_catalog_rejects_requirement_id_outside_ordered_request_catalog(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with self.assertRaisesRegex(ValueError, "missing requirements"):
            response_from_catalog(
                request,
                _catalog(requirement_ids=("missing-requirement",)),
                {},
                adapter_id="junit-results-adapter",
                repository="example/rti",
            )

    def test_shipped_catalog_example_matches_the_runtime_contract(self) -> None:
        catalog = ComplianceTestCatalog.model_validate_json(
            (ROOT / "examples" / "compliance-test-catalog.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(catalog.tests), 2)
        self.assertTrue(all(item.result_selector for item in catalog.tests))

    def test_cli_consumes_stdin_and_emits_only_adapter_json(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            catalog_path = directory / "catalog.json"
            result_path = directory / "results.xml"
            catalog_path.write_text(
                json.dumps(_catalog().model_dump(mode="json")), encoding="utf-8"
            )
            _write_result(result_path)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "hla_lab.traceability.junit_adapter",
                    "--catalog",
                    str(catalog_path),
                    "--results",
                    str(result_path),
                    "--repository",
                    "example/rti",
                ],
                cwd=ROOT,
                input=json.dumps(request.model_dump(mode="json")),
                capture_output=True,
                text=True,
                check=True,
            )

        self.assertEqual(completed.stderr, "")
        self.assertEqual(json.loads(completed.stdout)["coverage_mode"], "complete")

    def test_cli_rejects_malformed_junit_xml_without_emitting_response_json(self) -> None:
        request = build_adapter_request(_bundle(), "request-1")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            catalog_path = directory / "catalog.json"
            result_path = directory / "results.xml"
            catalog_path.write_text(
                json.dumps(_catalog().model_dump(mode="json")), encoding="utf-8"
            )
            result_path.write_text("<testsuite><testcase>", encoding="utf-8")
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "hla_lab.traceability.junit_adapter",
                    "--catalog",
                    str(catalog_path),
                    "--results",
                    str(result_path),
                    "--repository",
                    "example/rti",
                ],
                cwd=ROOT,
                input=json.dumps(request.model_dump(mode="json")),
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 2)
        self.assertEqual(completed.stdout, "")
        self.assertIn("junit adapter:", completed.stderr)

    def test_sidecar_runs_bundled_adapter_and_writes_raw_manifest(self) -> None:
        request_bundle = _bundle()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            bundle_path = directory / "bundle.json"
            catalog_path = directory / "catalog.json"
            result_path = directory / "results.xml"
            manifest_path = directory / "manifest.json"
            bundle_path.write_text(
                json.dumps(request_bundle.model_dump(mode="json")), encoding="utf-8"
            )
            catalog_path.write_text(
                json.dumps(_catalog().model_dump(mode="json")), encoding="utf-8"
            )
            _write_result(result_path)
            completed = subprocess.run(
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
                    "-m",
                    "hla_lab.traceability.junit_adapter",
                    "--catalog",
                    str(catalog_path),
                    "--results",
                    str(result_path),
                    "--repository",
                    "example/rti",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=True,
            )

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertTrue(json.loads(completed.stdout)["passed"])
        self.assertEqual(manifest["bindings"][0]["status"], "implemented")
        self.assertEqual(manifest["evidence"][0]["review_status"], "unreviewed")


if __name__ == "__main__":
    unittest.main()
