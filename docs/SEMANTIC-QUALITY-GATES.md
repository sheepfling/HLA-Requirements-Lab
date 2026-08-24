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
  an explicit change record, not in a temporary intake list.
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

## Shared presentation and build integrity

- All six products consume the Requirements Lab publication profile and fixed-page
  furniture; the canonical specimen remains 1516.2-2025.
- Opening pages use the Lab identity, restrained blue/ink reading text, and
  orange only for decorative accents.
- Both 1516.2 editions render the OMT Glyph category as live TikZ/vector artwork.
- Source trees contain no publisher boilerplate, ballot history, or legacy rights
  language that would assign identity or obligations to an external publisher.
- A release build must produce zero LaTeX errors, zero overfull boxes, and zero
  shared-header height warnings for every product.
- Representative rendered pages, including the page-23 bleed-risk check, are
  visually inspected for clipping, cutoff, and furniture drift.

For the six source-faithful HLA products, the release checker also treats
`Overfull \\hbox`, missing-character diagnostics, and undersized-header
diagnostics in `build/main.log` as release failures. Other repository
publications retain their own build policies.

Run the source-level and profile gates with:

```console
python -m unittest tests.test_semantic_quality_gates tests.test_style_profile_contracts tests.test_cover_contracts tests.test_modern_interior_contracts tests.test_authority_contracts tests.test_2010_requirement_closure
python -m unittest tests.integration.test_release_check
```

The PDF build and rendered-page checks remain release-level gates because they
depend on the local TeX runtime and page geometry.

## 2010 closure and edition-specific counts

The 2010 roots use the legacy source adapter, which extracts normative
``shall``/``must`` statements from the older LaTeX vocabulary. The closure
audit compares that source inventory with the promoted catalogs by count and
source-file distribution. It currently passes with no unpromoted candidates:

| Document | Source inventory | Explicit catalog | Generic tables |
|---|---:|---:|---:|
| IEEE 1516-2010 | 56 | 56 | 2 |
| IEEE 1516.1-2010 | 1,529 | 1,529 | 111 |
| IEEE 1516.2-2010 | 589 | 589 | 76 |

The 2010 generic tables remain typed table data. Their cells are not silently
converted into standalone requirements. The improved legacy adapter now emits
complete normative sentences and table-row obligations, carrying continuations
across page/layout boundaries and resolving each record to its owning clause.
The larger 1516.1-2010 and 1516.2-2010 counts are therefore source-closure
increases, not cosmetic renumbering. Legacy joins remain usable through the
per-edition `semantic/requirement-id-aliases.json` manifests.
Run the machine-enforced audit with:

```console
python -m hla_lab.traceability.requirement_closure --check --json
```

## Current clean counts

| Document | Requirements | Transitions | Planned seams | API binding rows |
|---|---:|---:|---:|---:|
| IEEE 1516-2010 | 56 | — | — | — |
| IEEE 1516.1-2010 | 1,529 | 212 | 212 | 1,611 |
| IEEE 1516.2-2010 | 589 | — | — | — |
| IEEE 1516-2025 | 20 | — | — | — |
| IEEE 1516.1-2025 | 1,860 | 282 | 282 | 1,894 |
| IEEE 1516.2-2025 | 340 | — | — | — |

The quality-gate tests live in
`tests/test_semantic_quality_gates.py`; they assert these properties rather
than the history or source of a particular change.
