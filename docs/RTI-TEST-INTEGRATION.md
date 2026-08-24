# RTI test-framework integration

Behavior verification is an external implementation concern, but it is a
first-class input to the lab's compliance result. The intended integration is:

```text
Catch2 / JUnit 5 / another test runner
    -> RTI-owned test catalog
    -> RTI compliance adapter
    -> AdapterResponse JSON
    -> Python sidecar verifier
```

The test framework executes behavior. The catalog gives that test a stable
evidence ID, names the exact requirement IDs it exercises, and connects it to
a corpus implementation mapping. The adapter translates test and
source-inspection results into the portable compliance contract. The sidecar
verifies the result against a pinned corpus bundle.

Declaring a test is never evidence. A test result is initially raw and
unreviewed. A separate protected review or verification step must accept the
evidence before a binding can become `verified`.

The RTI repository owns the test catalog, adapter, implementation symbols, and
test artifacts. This repository owns the requirements, transitions, API
surfaces, crosswalks, and verifier. The RTI does not need to import internal
Python modules from this repository.

## The stable test-catalog contract

An RTI repository should keep a small catalog such as
[`examples/compliance-test-catalog.json`](../examples/compliance-test-catalog.json).
The schema is
[`schemas/compliance_test_catalog.schema.json`](../schemas/compliance_test_catalog.schema.json).

Each entry has four important identities:

- `id`: stable evidence ID, not a display name;
- `document_id`: the selected corpus edition;
- `implementation_mapping_id`: the lab's semantic implementation seam;
- `target`: the implementation target, normally `cpp` or `java`.

`requirement_ids` is the explicit requirement join for a new catalog entry. It
must match the selected implementation mapping's requirement IDs and must
resolve in the ordered requirement catalog carried by the adapter request.
Schema-v1 catalogs may omit it for compatibility; those entries use the
mapping join and should be migrated when touched. The catalog position and
source coordinates are presentation/provenance metadata; requirement IDs are
the stable identity.

`api_surface_ids` names the exact declaration surfaces selected by the corpus
crosswalk. `result_selector` is the exact testcase name in the JUnit XML
result: either `name`, `classname#name`, or `classname.name`. A test tag or
test method name is only a runner selector; it is not the traceability key.
This prevents a harmless test rename from silently breaking compliance
coverage.

Example:

```json
{
  "schema_version": 1,
  "tests": [
    {
      "id": "cpp-connect-integration",
      "kind": "integration-test",
      "runner": "catch2",
      "selector": "[compliance][rti.service.connect]",
      "result_selector": "RTIambassador connect",
      "command": "build/rti_tests.exe --reporter junit --out build/compliance/connect.xml",
      "document_id": "hla-1516.1-2025",
      "implementation_mapping_id": "rti.service.connect",
      "target": "cpp",
      "language": "cpp",
      "symbol": "RTI::RTIambassador::connect",
      "api_surface_ids": ["cpp-rtiambassador-connect"],
      "requirement_ids": ["<requirement-id-from-corpus-bundle>"],
      "execution_mode": "real"
    }
  ]
}
```

The IDs in this example are illustrative. Replace the mapping, API, and
requirement IDs with IDs from the selected `corpus-bundle.json`.

## C++ with Catch2

Use Catch2 tags for discovery and selection, while keeping the semantic
mapping in the catalog:

```cpp
TEST_CASE("RTIambassador connect", "[compliance][rti.service.connect]") {
    auto rti = make_rti();
    REQUIRE_NOTHROW(rti.connect(...));
}
```

Have the RTI's existing build job write its normal JUnit report:

```console
build/rti_tests.exe "[compliance]" --reporter junit --out build/compliance/catch2-results.xml
```

The supplied JUnit-results adapter reads that report; it never runs an
arbitrary RTI command. This keeps test execution owned by the RTI build and
makes the same adapter usable for Java. A custom adapter may additionally
inspect C++ declarations or build metadata—`compile_commands.json`, Clang AST
output, exported symbols, or installed headers—to validate the RTI-owned
symbol. A passing Catch2 test proves observed behavior; the corpus crosswalk
provides the selected declaration surface.

Mocked or simulated tests may be retained as useful unit-test breadth, but
their evidence is marked `execution_mode: "mocked"` or `"simulated"` and cannot
support `fully_verified`. Use a real integration test, trace, or equivalent
runtime observation for the final behavior claim.

CTest can be the outer runner when the RTI already uses CMake:

```console
ctest --test-dir build --output-on-failure
```

Use `runner: "ctest"` and a stable CTest selector in the catalog in that case.

## Java with JUnit 5

Use JUnit tags for selection:

```java
@Tag("compliance")
@Tag("rti.service.connect")
@Test
void connect_satisfies_contract() {
    assertDoesNotThrow(() -> rti.connect(...));
}
```

Run through the build system already owned by the RTI:

```console
./mvnw test
```

or:

```console
./gradlew test
```

Pass the generated Surefire or Gradle JUnit XML report to the supplied adapter.
For a custom declaration-inspection adapter, compiled classes, JARs, generated
interfaces, or reflection metadata can validate the RTI-owned Java symbol. Use
`runner: "junit5"`, `"maven"`, or `"gradle"` according to the RTI's test
execution boundary.

The same real-versus-mocked rule applies to Java tests. A JUnit test that uses
a mock RTI or mock transport can demonstrate local control flow, but it does
not prove RTI behavior.

## What the adapter produces

For each expected mapping/target in the adapter request, the adapter returns
an `ImplementationBinding`. A verified binding should look like this:

```json
{
  "id": "my-rti.cpp.rti.service.connect",
  "document_id": "hla-1516.1-2025",
  "implementation_mapping_id": "rti.service.connect",
  "target": "cpp",
  "symbol": "RTI::RTIambassador::connect",
  "language": "cpp",
  "status": "verified",
  "api_surface_ids": ["cpp-rtiambassador-connect"],
  "evidence_ids": ["cpp-connect-integration"]
}
```

The corresponding evidence record points to the actual test command and
retained result:

```json
{
  "id": "cpp-connect-integration",
  "kind": "integration-test",
  "status": "passed",
  "execution_mode": "real",
  "review_status": "accepted",
  "reviewer": "protected-compliance-ci",
  "reviewed_at": "2026-08-15T00:00:00Z",
  "command": "ctest --test-dir build -R rti_connect",
  "artifact": "build/compliance/catch2-results.xml"
}
```

Use these status rules:

- `planned`: the catalog exists but the test has not run;
- `implemented`: the symbol exists, but behavioral evidence is incomplete;
- `verified`: the crosswalk is matched, exact API surfaces are named, and at
  least one linked evidence record is `passed` or `observed`;
- `partial`, `deferred`, or `not_applicable`: explain an intentional gap.

A passing test without an exact API surface is not sufficient for `verified`.
Likewise, an API declaration without passing behavioral evidence is not
verified implementation evidence.

The adapter must not accept its own evidence. Adapter responses may report
`passed` tests and `implemented` bindings, but they cannot carry accepted
evidence. Acceptance is added by a separate review/protected-CI step in the
implementation manifest. This creates the intended promotion boundary:

```text
declared catalog
  -> raw test result
  -> accepted real evidence
  -> verified binding
```

## One supplied adapter for Catch2 and JUnit 5

The repository includes `hla_lab.traceability.junit_adapter`. It validates the
catalog against the sidecar request, reads one or more JUnit XML artifacts, and
returns raw `AdapterResponse` JSON. It supports Catch2's JUnit reporter as well
as Maven Surefire, Gradle, and conventional JUnit 5 XML. It intentionally
emits only unreviewed evidence and statuses no stronger than `implemented`.

After the RTI CI job has run its tests, use the same command for C++ or Java by
changing only the report path and catalog:

```console
python -m hla_lab.traceability.compliance_sidecar check --bundle .compliance/corpus-bundle.json --manifest-output .compliance/implementation-manifest.raw.json --json --adapter-command python -m hla_lab.traceability.junit_adapter --catalog compliance/test-catalog.json --results build/compliance/catch2-results.xml --repository example/my-cpp-rti
```

For Maven or Gradle, point `--results` to its XML artifact and use a Java
catalog. Repeat `--results` when one CI run produces more than one report:

```console
python -m hla_lab.traceability.junit_adapter --catalog compliance/test-catalog.json --results target/surefire-reports/TEST-example.rti.RtiAmbassadorIT.xml --repository example/my-java-rti < .compliance/adapter-request.json > .compliance/adapter-response.raw.json
```

The second form is useful when the build system already owns the sidecar's
split protocol. The adapter reports a missing `result_selector` as `planned`,
and rejects ambiguous XML selectors or a catalog that disagrees with the
request's language, mapping, target, exact API surface IDs, or explicit
requirement IDs. The adapter request includes the same ordered requirement
records as the corpus bundle, including source provenance and coverage links.
This makes an incorrect catalog visible rather than creating an apparently
successful bundle.
One catalog may contain 2010 and 2025 entries together when the bundle was
exported with `--edition all`; `document_id` keeps their evidence independent.

## CI wiring

The corpus checkout first exports a revision-pinned bundle:

```console
python -m hla_lab.publication.export_compliance_bundle --corpus-root . --edition all --revision <corpus-commit> --output .compliance/corpus-bundle.json
```

The RTI CI job then builds the RTI, runs its standard tests, invokes the
adapter, and asks the sidecar to verify the response:

```console
python -m hla_lab.traceability.compliance_sidecar check --bundle .compliance/corpus-bundle.json --manifest-output .compliance/implementation-manifest.json --json --adapter-command python tools/rti_compliance_adapter.py
```

For a native adapter, replace the final command with the C++ executable or
Java JAR. The `--json` option must precede `--adapter-command`; all subsequent
arguments are passed to the adapter.

The adapter must return `coverage_mode: "complete"` for a release gate. Use
`"partial"` during exploratory development so missing bindings remain visible
without claiming complete coverage.

## Query total testing compliance

The verifier's JSON result includes a `coverage` object. It reports both the
structural binding result and the behavioral testing roll-up:

```console
python -m hla_lab.publication.verify_compliance_bundle --bundle .compliance/corpus-bundle.json --manifest .compliance/implementation-manifest.json --json
```

The same `coverage` object is returned by the sidecar adapter command. It
contains:

- verified versus expected implementation bindings;
- requirements with verified evidence versus total selected requirements;
- transitions with verified evidence versus total selected transitions;
- API surfaces with verified evidence versus matched selected API surfaces;
- normalized ratios for each dimension;
- `fully_verified`, which is true only when every expected binding,
  requirement, transition, and selected API surface has verified evidence;
- accepted versus unaccepted evidence and real versus non-real execution IDs;
- qualified IDs for untested bindings, requirements, transitions, and API
  surfaces.

`passed` means the manifest is structurally valid and has no verifier errors.
`coverage.fully_verified` answers the stricter question: has the selected
implementation scope actually been behaviorally verified? A manifest may pass
structural validation while still reporting planned or partial testing.

For build systems that own process execution, use the split protocol:

```console
python -m hla_lab.traceability.compliance_sidecar prepare --bundle .compliance/corpus-bundle.json --output .compliance/adapter-request.json

python tools/rti_compliance_adapter.py < .compliance/adapter-request.json > .compliance/adapter-response.json

python -m hla_lab.traceability.compliance_sidecar check --bundle .compliance/corpus-bundle.json --adapter-response .compliance/adapter-response.json --manifest-output .compliance/implementation-manifest.json --json
```

Keep adapter diagnostics on stderr and reserve stdout for one JSON response.
Store JUnit/Catch2 XML, logs, traces, binaries, and screenshots as CI
artifacts; commit only the RTI-owned catalog and manifest policy.

## New RTI onboarding checklist

1. Pin a corpus revision and export a bundle for the required edition(s).
2. Choose Catch2/CTest, JUnit 5/Maven/Gradle, or another existing test runner.
3. Add stable catalog entries for the first API seams.
4. Run the supplied JUnit-results adapter, or implement a custom adapter for a
   non-JUnit runner or declaration inspection.
5. Emit bindings using the exact mapping IDs, target, symbol, and API surface IDs.
6. Link each verified binding to passed evidence.
7. Run the sidecar in CI and publish its JSON result and test artifacts.
8. Expand coverage until the adapter can truthfully return `complete`.

The portable JSON contract and sidecar are defined in
[`docs/EXTERNAL-COMPLIANCE-KIT.md`](EXTERNAL-COMPLIANCE-KIT.md). The corpus
readiness gate remains separate from implementation readiness: this repository
defines what must be tested, while the RTI repository proves what was tested.
