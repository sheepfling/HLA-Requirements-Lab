# Semantic quality gates

These gates define the durable acceptance criteria for the IEEE 1516-family
semantic surfaces. They apply to both the 2010 and 2025 editions; an edition
may add source-specific records without weakening the shared invariants.

The portable comparison artifact is:

`.tmp/quality-gated-baseline-2026-08-23.json`

It contains all six 2010/2025 HLA documents and carries no intake or issue
identifiers.

## Source integrity

- Every requirement has a real source path and valid line span.
- A generated title that includes a source location agrees with the record's
  path and line.
- Normative statements do not end at TeX line-comment markers or contain raw
  layout comment markers.
- Candidate and explicit requirement identifiers are stable semantic names,
  not workflow labels.

## Editorial fidelity

- Source-derived table values, identifiers, and note prose use exact-transcription
  mode; machine-significant spellings such as `TimeStamp` are not normalized
  for appearance.
- A derived document may improve layout and navigation, but it does not silently
  rewrite source semantics. Any intentional editorial normalization belongs in
  an explicit change record, not in a temporary intake or complaint list.
- Visual hierarchy is independent of source parentage: tree renderers consume
  explicit parent-child edges, while indentation and branch glyphs are only
  presentation data.

## Composition integrity

- Every table cell's related record IDs resolve in the same document.
- Table continuations retain their data cells and source provenance.
- Cross-page service content remains discoverable from the service's semantic
  requirements.
- State-machine transitions, implementation seams, and transition coverage
  are reciprocal and complete.

## API and publication integrity

- Every requirement has exactly one API-binding row in the portable manifest.
- Direct API matches resolve to a declared source-backed Java or C++ surface.
- Planned implementation seams are never reported as concrete implementation
  evidence.
- Both editions pass the compliance-surface and unresolved-reference checks.

## 2010 closure and edition-specific counts

The 2010 roots use the legacy source adapter, which extracts normative
``shall``/``must`` statements from the older LaTeX vocabulary. The closure
audit compares that source inventory with the promoted catalogs by count and
source-file distribution. It currently passes with no unpromoted candidates:

| Document | Source inventory | Explicit catalog | Generic tables |
|---|---:|---:|---:|
| IEEE 1516-2010 | 55 | 55 | 2 |
| IEEE 1516.1-2010 | 942 | 942 | 111 |
| IEEE 1516.2-2010 | 388 | 388 | 76 |

The 2010 generic tables remain typed table data. Their cells are not silently
converted into standalone requirements. This is why their counts do not rise
to match the 2025.1 page-faithful Table 5 migration: that 163-record increase
is a 2025 source-specific closure, not a shared requirement rule. Run the
machine-enforced audit with:

```console
python -m hla_lab.traceability.requirement_closure --check --json
```

## Current clean counts

| Document | Requirements | Transitions | Planned seams | API binding rows |
|---|---:|---:|---:|---:|
| IEEE 1516-2010 | 55 | — | — | — |
| IEEE 1516.1-2010 | 942 | 212 | 212 | 1,078 |
| IEEE 1516.2-2010 | 388 | — | — | — |
| IEEE 1516-2025 | 20 | — | — | — |
| IEEE 1516.1-2025 | 1,860 | 282 | 282 | 1,894 |
| IEEE 1516.2-2025 | 340 | — | — | — |

The quality-gate tests live in
`tests/test_semantic_quality_gates.py`; they assert these properties rather
than the history or source of a particular change.
