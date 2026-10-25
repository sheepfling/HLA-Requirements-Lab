# External compliance kit

The semantic corpus and the RTI implementation have separate ownership. The
corpus repository owns requirements, state machines, exact API declarations,
crosswalks, and the verifier. An RTI repository owns implementation symbols,
binding status, and evidence. The two repositories communicate through JSON
contracts; the RTI does not import this repository's internal semantic modules.

## Portable boundary

The corpus checkout exports a `CorpusBundle` containing the selected documents,
an ordered, source-addressable requirement catalog, transitions, API surfaces,
implementation mappings, and API crosswalk statuses. The RTI checkout supplies
an `ImplementationManifest` with the bindings it claims and links to its
external evidence.

Both contracts are Pydantic-validated. The verifier joins records by:

```text
document_id + implementation_mapping_id + target
```

The corpus revision is also required to match. This permits 2010 and 2025
records to be consumed side-by-side without matching on human wording.

Generate the machine-readable boundary schemas with
`hla-lab-schema corpus_bundle` and `hla-lab-schema adapter_request`.
The source models are in `hla_lab.traceability.compliance_contract`.

Requirement records carry a document-local `ordinal` for presentation, full
normative/machine text, clause and coverage metadata, transition links,
extraction status, and source provenance. The ordinal and array position are
never identity; RTI catalogs and evidence use the stable requirement `id`.
`AdapterRequest.documents[].requirements` carries this same catalog to an
external test adapter, so the adapter does not need to reconstruct requirements
from implementation mappings.

## Corpus-side commands

Run these from a corpus checkout. `.compliance/` is ignored and is intended for
local or CI artifacts only:

```console
python -m hla_lab.publication.export_compliance_bundle --corpus-root . --edition 2025 --revision <corpus-commit> --output .compliance/corpus-bundle.json
python -m hla_lab.publication.verify_compliance_bundle --bundle .compliance/corpus-bundle.json --manifest ../my-rti/compliance/implementation-manifest.json --json
```

Use `--edition all` when one implementation manifest covers both editions.
The verifier exits zero only when the selected complete manifest has no error
findings.

## Adapter protocol

An RTI project can avoid hand-authoring the manifest by supplying a small
adapter executable. The sidecar invokes the executable as a subprocess, sends
one `AdapterRequest` JSON document on stdin, and expects one `AdapterResponse`
JSON document on stdout. Adapter diagnostics belong on stderr so stdout stays
machine-readable. The adapter may be written in Python, C++, Java, Go, or any
other language that can read and write JSON; it does not need to import this
repository.

The request contains the corpus revision, document IDs, implementation mapping
IDs, target/language expectations, requirement and transition links, and the
candidate API surface declarations. The response returns the adapter identity,
the matching request ID, implementation bindings, and evidence records. A
`complete` response claims that the adapter considered every expected target;
`partial` is appropriate for an exploratory probe and will not claim full
coverage.

The reference adapter in
[`examples/compliance-adapter.py`](../examples/compliance-adapter.py) is a
stdlib-only protocol template. Replace its planned-binding logic with symbol
discovery, generated-client inspection, integration tests, or runtime probes
owned by the RTI project.

For the usual Java and C++ test path, no custom adapter is needed initially.
[`hla_lab.traceability.junit_adapter`](../hla_lab/traceability/junit_adapter.py)
reads an RTI-owned validated catalog plus JUnit XML emitted by Catch2, Maven,
Gradle, or JUnit 5. It produces raw, unreviewed test evidence only; a protected
review step must accept real evidence before a binding can be promoted to
`verified`. The complete Java/C++ onboarding flow is in
[`docs/RTI-TEST-INTEGRATION.md`](RTI-TEST-INTEGRATION.md).

To run an adapter directly from an RTI checkout:

```console
python -m hla_lab.traceability.compliance_sidecar check --bundle .compliance/corpus-bundle.json --manifest-output .compliance/implementation-manifest.json --json --adapter-command python tools/rti_compliance_adapter.py
```

`--json` must appear before `--adapter-command` because all following tokens
are passed unchanged to the adapter. The sidecar then converts the adapter
response to the canonical `ImplementationManifest`, writes it when requested,
and runs the same generic verifier used for a hand-authored manifest. A
language-neutral adapter can also be driven in two explicit steps:

The JSON result includes a `coverage` summary with verified binding,
requirement, transition, and API-surface counts and ratios. Its
`fully_verified` flag is the strict behavioral-coverage result; `passed` only
means that the manifest is structurally valid and has no verifier errors.

```console
python -m hla_lab.traceability.compliance_sidecar prepare --bundle .compliance/corpus-bundle.json --output .compliance/adapter-request.json
python tools/rti_compliance_adapter.py < .compliance/adapter-request.json > .compliance/adapter-response.json
python -m hla_lab.traceability.compliance_sidecar check --bundle .compliance/corpus-bundle.json --adapter-response .compliance/adapter-response.json --manifest-output .compliance/implementation-manifest.json --json
```

The split form is useful when the RTI build system owns process execution or
when adapter output should be retained as a CI artifact. `--adapter-response`
validates that raw response, converts it to the canonical manifest, and runs
the same verifier as the one-process `--adapter-command` path.

The stable boundary is the JSON model, not the Python module path. The
Pydantic definitions in
[`hla_lab/traceability/compliance_contract.py`](../hla_lab/traceability/compliance_contract.py) are the
reference schema implementation; another language may generate equivalent
JSON from the field names and literals in that contract.

## RTI-side manifest

The implementation manifest is the only required RTI-side input:

```json
{
  "schema_version": 1,
  "manifest_id": "my-rti-2025",
  "repository": "example/my-rti",
  "corpus_revision": "<corpus-commit>",
  "document_ids": ["hla-1516.1-2025"],
  "targets": ["cpp"],
  "coverage_mode": "complete",
  "bindings": [
    {
      "id": "my-rti-connect",
      "document_id": "hla-1516.1-2025",
      "implementation_mapping_id": "<semantic-mapping-id>",
      "target": "cpp",
      "symbol": "RTI::RTIambassador::connect",
      "language": "cpp",
      "status": "verified",
      "api_surface_ids": ["<exact-api-surface-id>"],
      "evidence_ids": ["connect-integration-test"]
    }
  ],
  "evidence": [
    {
      "id": "connect-integration-test",
      "kind": "integration-test",
      "status": "passed",
      "execution_mode": "real",
      "review_status": "accepted",
      "reviewer": "protected-compliance-ci",
      "reviewed_at": "2026-08-15T00:00:00Z",
      "command": "ctest --test-dir build --tests-regex connect"
    }
  ]
}
```

The manifest is implementation configuration and may be committed with the
RTI. Test logs, generated bundles, PDFs, JUnit/SARIF output, and runtime traces
remain CI artifacts and are not baselined here.

## Submodule or package deployment

For an offline or tightly pinned workflow, the RTI repository may add this
repository as a submodule at a reviewed commit and invoke the two module
commands above. A future packaged release can expose the same contract and
CLI; the JSON boundary remains unchanged, so changing the deployment mechanism
does not couple RTI source code to the corpus implementation.

The verifier is intentionally generic in
[`hla_lab/traceability/compliance_contract.py`](../hla_lab/traceability/compliance_contract.py) and
[`hla_lab/publication/verify_compliance_bundle.py`](../hla_lab/publication/verify_compliance_bundle.py).
HLA-specific corpus selection and export remain in
[`hla_lab/publication/export_compliance_bundle.py`](../hla_lab/publication/export_compliance_bundle.py).
