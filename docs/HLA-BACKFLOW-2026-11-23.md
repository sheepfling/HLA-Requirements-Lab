# HLA implementation backflow review — 2026-11-23

This review follows the 63 issue IDs in the 2026-11-23 Requirements Lab queue.
The [machine-readable snapshot](../data/hla-backflow-2026-11-23.json) preserves
each full upstream issue record, its current upstream status, the Lab
disposition, work completed, verification references, and remaining action.
It also records the SHA-256 of the read-only source register used to build it.

Umbra's `compliance/requirements-lab/known-issues.json` remains authoritative
for upstream status. The register was read only. This Lab work does not close or
resynchronize Umbra issues.

## Status snapshot

| Measure | Count | Meaning |
|---|---:|---|
| Tracked queue records | 63 | The complete ID set from the 2026-11-23 queue, regardless of later status changes. |
| Still open upstream | 57 | Umbra's authoritative register still marks these records open. |
| Resolved in Umbra | 6 | RL-411–414 and RL-450–451 were already resolved in the register snapshot used here. |
| Corrected in Lab | 50 | Source-backed semantic, attribution, table, renderer, service-flow, or framing changes are present locally. |
| Source anomaly mapped | 8 | The Lab mapping is explicit; conflicting printed examples or API spellings remain preserved as source anomalies. |
| Downstream-only; no Lab change | 5 | The remaining concern was coverage or TCK workflow, not Lab source data. These records are now resolved upstream. |

The eight source-anomaly mappings are RL-399, RL-403, RL-407, RL-420, RL-441,
RL-443, RL-444, and RL-456. Their mapping decisions are stated in the
document-specific `source-anomaly-ledger.json` files. The ledgers preserve the
conflicting evidence and distinguish the semantic rule used by the Lab from
claims about example conformance. A source contradiction can remain open in
Umbra after its Lab requirement has become clear and traceable.

## Source-anomaly dispositions

- **RL-399:** Use HLAargumentType enumerants from Table 14
  (`InteractionClassHandle=27`, `UserSuppliedTag=60`). Preserve conflicting
  Table 5 example values 24, 58, and 63 with their page and row provenance.
- **RL-403:** Map `BinaryData` to the captured base-64 definition. Keep the
  printed examples verbatim, and do not turn their malformed/non-canonical
  lexical forms into an encoder rule.
- **RL-407:** Use `HLAservice` as the semantic `ServiceReportRecord` field,
  supported by the same-row example and repeated document spelling. Preserve
  the encoding typo `HLAservce` as source evidence.
- **RL-420:** Crosswalk the requirement's `addMapping` behavior to the published
  C++ `HLAvariantRecord::addVariant` operation based on its documented
  discriminant/variant mapping semantics. Preserve the API-name mismatch; do
  not claim an `addMapping` C++ symbol or conflate `addVariantPointer` with the
  copy-based operation.
- **RL-441:** Apply Clause 3.3 name rules to the Model Identification Name.
  Preserve the example name containing spaces as contradictory evidence, not
  an exception.
- **RL-443:** State the warning and failed-merge outcomes separately in the
  derived requirement. Preserve the captured wording and joined layout text;
  do not invent a separate callback or log channel.
- **RL-444:** Isolate and map the explicit underscore-prefix rule for note
  labels and references. Preserve the conflicting XSD and example evidence
  without weakening the word “shall.”
- **RL-456:** Map FOM/FOM-module synchronization Capability to `NA` as required
  by Clauses 4 and 6.2.10. Preserve the conflicting Restaurant example values.

The relevant normative and example wording is captured in this repository's
semantic content and page-layout records, which provide the primary evidence
for the Lab mappings. The cited 2025 header, DIF schema, Restaurant example,
and MIM provide additional cross-checks from the read-only sibling Umbra
source checkouts. Matching SHA-256 values confirmed the header, example, and
schema copies in both source checkouts are identical. The Lab ledgers cite the
local source records and identify the external artifact evidence.

## Other repair groups

- **Table 5 structured records, RL-394–401 and RL-403–410:** repaired parent
  and child structure, continuation rows, examples, enum values, and
  source-addressable spans.
- **Service and API clause attribution, RL-415–437, RL-442, RL-447–448:**
  reassigned candidates to visible service clauses and API surfaces, including
  cross-page and support-service cases.
- **Source labels, RL-413 and RL-418:** corrected the page-216 DDM adapter and
  Clause 11/12 page ownership labels while preserving stable candidate IDs.
- **Semantic extraction and service flow, RL-392, RL-416–417, RL-438–440,
  RL-446, RL-449, RL-452–455:** restored missing service-flow rules, complete
  statements, table hierarchy, applicability, and source spans. Framing that
  does not declare independent behavior remains contextual.
- **Protocol tables, RL-419 and RL-445:** corrected the production semantic
  renderer so the affected protocol tables retain their source row and cell
  structure.

The [snapshot](../data/hla-backflow-2026-11-23.json) is the issue-by-issue
ledger. Its `verification_refs` point to regression tests for each changed
group. The tests reject a changed queue ID set, preserve the actual upstream
statuses, and reject verification links that no longer resolve.

## Validation

The grouped regression suites are:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hla_backflow.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_backflow_2026_11_23.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_15161_acceptance_slice.py -k "production_protocol_renderer_preserves_table_31_through_39_shapes" -q
.\.venv\Scripts\python.exe -m pytest tests/test_backflow_snapshot.py tests/test_corpus_inventory.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_requirement_candidate_boundaries.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_semantic_quality_gates.py -q
.\.venv\Scripts\python.exe -m pytest tests/test_authority_contracts.py::AuthorityContractTests::test_authority_manifest_covers_migrated_surfaces -q
```

The 2026-11-23 backflow, semantic-quality, candidate-boundary, and authority
checks pass in the reviewed working tree. A full repository run was not used
as the acceptance gate: `tests/test_corpus_root.py` still imports the removed
module-level `DOCUMENT_IDS` and `RESOURCES` names and also asserts package
behaviors outside this source-mapping change.

The snapshot is generated from the sibling Umbra checkout with:

```powershell
.\.venv\Scripts\python.exe tools/migrations/snapshot_backflow_2026_11_23.py `
  --source ..\umbra\compliance\requirements-lab\known-issues.json `
  --output data\hla-backflow-2026-11-23.json
```

The builder verifies the exact 63 tracked queue IDs and captures their current
statuses. It does not write to the source register.
