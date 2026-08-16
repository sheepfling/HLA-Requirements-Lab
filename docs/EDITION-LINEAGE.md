# Edition lineage

`data/semantic/edition-lineage.json` is the source-controlled, Pydantic-validated
contract for comparing two editions of a standard. It is deliberately generic:
it has no HLA-specific constants, LaTeX, or assumptions about clause numbering.

An edition is identified by a corpus `document_id`, a stable `standard_id`, and
an `edition` label. A relation is reviewed evidence that one or more semantic
records from a baseline edition correspond to one or more records in a target
edition. It is never inferred from similar prose.

Supported relations are:

- `unchanged` and `revised` for records present in both editions;
- `split` and `merged` for one-to-many or many-to-one changes;
- `added` and `removed` for records unique to one edition.

Every relation uses a version-neutral `stable_id`, record-qualified references,
an explicit relation kind, review status, and a rationale. Requirements are the
initial intended surface; definitions, clauses, tables, state machines, and
transitions use the same contract.

The checked-in manifest registers the validated 2010 and 2025 document
identities and now contains the reviewed IEEE 1516.1 state-machine differential:
14 revised families, one 2010-to-2025 consolidation, and nine 2025 additions.
Requirements, definitions, tables, and individual transitions still require
their own reviewed relations. Matching numbers or similar text are not
evidence of equivalence; add a relation only after the corresponding records
have been reviewed in both corpora, for example:

```json
{
  "id": "hla-federation-join-2010-to-2025",
  "stable_id": "federation.join.lifecycle",
  "relation": "revised",
  "baseline_document_id": "hla-1516.1-2010",
  "target_document_id": "hla-1516.1-2025",
  "baseline_records": [
    {"document_id": "hla-1516.1-2010", "record_id": "req-join", "kind": "requirement"}
  ],
  "target_records": [
    {"document_id": "hla-1516.1-2025", "record_id": "req-join", "kind": "requirement"}
  ],
  "review_status": "reviewed",
  "rationale": "The 2025 requirement adds an explicit lifecycle precondition."
}
```

Query a reviewed side-by-side projection with:

```powershell
python -m hla_lab.corpus.edition_lineage data/semantic/edition-lineage.json `
  --baseline hla-1516.1-2010 `
  --target hla-1516.1-2025 `
  --kind requirement --reviewed-only --json
```

When a comparison is supplied a `ComplianceCorpus`, validation also verifies
that every referenced record actually exists and reports baseline/target records
that still have no lineage relation. This supplies the coverage gap list for an
edition-to-edition requirements traceability matrix.

For an immediately usable HLA inventory/differential report, compare the
edition-qualified semantic models directly:

```powershell
# Reviewed lineage plus every requirement without a reviewed correspondence.
python -m hla_lab.corpus.hla_edition_diff `
  --standard ieee-1516.1 `
  --kind requirement `
  --format csv

# State-machine inventory and transition inventory use the same contract.
python -m hla_lab.corpus.hla_edition_diff `
  --standard ieee-1516.1 `
  --kind state-machine `
  --format json
python -m hla_lab.corpus.hla_edition_diff `
  --standard ieee-1516.1 `
  --kind transition `
  --format csv
```

The adapter defaults to `2010 -> 2025` and resolves roots from
`topics/ieee/<document_id>`. Each row carries its document side, stable
record ID, clause, source location, and relevant state/transition fields.
Reviewed state-machine rows additionally carry state and transition IDs added
on the target side or removed from the target side within that reviewed
machine correspondence.
Rows marked `reviewed` come from the human-reviewed lineage manifest. Rows
marked `baseline-unmapped` or `target-unmapped` are inventory gaps only; they
must not be reported as semantic additions or removals until a reviewed
`added`/`removed` relation is recorded.
Transition rows owned by a reviewed `added` state machine are marked
`target-machine-added`; that is an inherited machine-level addition, not an
independent transition lineage claim.
