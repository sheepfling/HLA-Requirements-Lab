# Data-driven reconstruction plan

This is the concrete delivery plan for the repository's main goal: make the
recreated documents increasingly data-driven while preserving faithful PDF
recreations as comparison products.

The HLA documents are the first corpus. The core architecture must remain
usable for other standards and whitepapers.

## Product contract

The repository produces three related products from one source pipeline:

```text
source adapters and authored records
                |
                v
       validated semantic corpus
       (Pydantic models + stable IDs)
          /            |             \
         v             v              v
 faithful PDF     derivative PDF    compliance API/export
 layout adapter   semantic renderer  queries and mappings
```

The products have different responsibilities:

1. **Faithful recreation** preserves the original wording, order, geometry,
   and visual behavior. Fixed coordinates and page-fragment adapters are
   allowed here, but they do not define semantic ownership.
2. **Semantic corpus** is the authoritative source for clause hierarchy,
   definitions, normative statements, tables, references, state machines,
   and implementation relationships. It is source-controlled text and must
   load, validate, serialize, and deserialize deterministically.
3. **Derivative document and compliance exports** are generated views of the
   semantic corpus. They must not contain hand-copied normative prose or
   independently maintained IDs.

## Definition of data-driven

The HLA tranche is data-driven when all confirmed semantic surfaces meet these
conditions:

- each record has a stable semantic ID, document owner, hierarchy owner, and
  source provenance;
- normative text, definitions, tables, references, and state behavior are
  represented as typed records rather than only as page-local LaTeX;
- state transitions expose event, source/target state, initiator, guard,
  action, preconditions, postconditions, and applicable clause links where
  those concepts exist in the source;
- every extracted candidate is classified as reviewed semantic content,
  non-normative/layout content, or explicitly deferred;
- faithful and derivative renderers consume the same semantic records;
- changing one semantic record changes the relevant generated output and
  machine-readable export without editing generated TeX;
- references, duplicate IDs, hierarchy, state targets, and requirement
  coverage are validated before rendering; and
- the faithful builds remain visually stable unless a layout change is
  intentional and reviewed.

“100% semantic coverage” therefore means 100% of confirmed semantic content,
not that every extracted sentence is blindly promoted to a requirement.

## Current measurable baseline

Baseline captured on 2026-08-05 from the validated semantic models and the
source-controlled corpus inventory:

| Surface | 1516 | 1516.1 | 1516.2 | End-state target |
| --- | ---: | ---: | ---: | --- |
| Extracted requirement records | 20 | 1,697 | 340 | Every candidate classified; every confirmed normative record reviewed |
| Reviewed requirements | 20 | 1,697 | 340 | All confirmed normative records have explicit coverage |
| Classified deferred candidates | 0 | 0 | 0 | Every candidate is reviewed, promoted, or explicitly deferred |
| Authored content blocks | 38 | 439 | 122 | All ordinary document content has a typed semantic owner |
| Typed content elements | 336 | 645 | 1,078 | Paragraphs, lists, notes, footnotes, formulas, and references are reusable records |
| Table-backed semantic definitions | 161 | 0 | 83 | Reusable meanings are derived from populated OMT Semantics columns |
| State machines | 0 | 24 | 0 | All source-defined machines represented or explicitly marked absent |
| State transitions | 0 | 281 | 0 | All modeled transitions have complete semantic fields |
| Transition implementation mappings | 0 | 281 mapped (planned seams) | 0 | Every compliance-scope transition classified and mapped or marked N/A/deferred |
| Migrated table families | 0 | 0 | 80 | All semantic table families represented with continued-fragment links |
| Page-fragment ratio | 0.8444 | 0.9887 | 0.9533 | Below 0.10 for semantic-owned source; layout adapters may remain |

The baseline is a prioritization tool, not a committed audit artifact. Run
the stdout-only metrics and dashboards locally:

```powershell
python -m scripts.corpus_inventory
python -m scripts.semantic_metrics --json
python -m scripts.semantic_dashboard --json
python -m scripts.release_check --manifest data/release/documents.json --diagram-manifest data/state_machines/manifest.json --authority-manifest data/semantic/authority.json --json
```

## Deliverable layers

Every migration slice must deliver all of the following, or explicitly record
why a layer is not applicable:

### A. Source and schema

- authored semantic records in the document's `semantic/` source tree;
- Pydantic validation and JSON round-trip coverage;
- stable IDs, parent/child ownership, source spans, and cross-document links;
- candidate classification and a documented review state.

### B. Generated faithful input

- generated semantic blocks or data macros under ignored output paths;
- page-local LaTeX reduced to layout, TikZ, and exceptional formatting;
- removal of duplicate definitions and normative prose from migrated pages;
- unchanged faithful page count and visual comparison for the affected scope.

### C. Programmatic views

- derivative LaTeX generated from the same records;
- machine-readable JSON for software consumers;
- hierarchy/navigation/anchor output derived from semantic IDs;
- state-machine DOT/Mermaid exports when diagrams are in scope.

### D. Compliance use

- requirement-to-clause and requirement-to-transition links;
- functional preconditions, postconditions, guards, and actions;
- RTI service, callback, adapter, and code-symbol mappings where applicable;
- queries for state/event applicability and unmapped implementation work;
- typed reports for orphan records, unresolved references, duplicates, and
  invalid state targets.

### E. Quality and hygiene

- unit and mutation tests for the semantic contract;
- clean rebuild through the common builder;
- release checks for PDF pages, LaTeX logs, and visual-review status;
- no PDFs, images, audits, review packets, logs, or generated exports tracked.

## Post-M7 milestones

### M8 — Corpus inventory and migration contracts

**Status: complete.**

Deliver a complete machine-readable inventory of the three documents' semantic
surfaces: clauses, definitions, normative candidates, references, tables,
figures, examples, state machines, and layout-only artifacts.

Acceptance gates:

- every candidate has a classification and source provenance;
- every semantic surface has an owner and migration destination;
- the priority queue is ranked by reuse value and source-shape reduction;
- baseline metrics and release page counts remain reproducible.

The source-controlled inventory is `data/semantic/inventory.json`; its
migration queue keeps deferred candidates visible without treating them as
normative requirements.

### M9 — Make 1516 semantically complete

**Status: complete for the semantic source/build boundary.**

Migrate the framework-and-rules document's hierarchy, definitions, summary
rules, references, and confirmed normative content into canonical records.

Deliverables:

- complete clause/definition/reference ownership;
- reviewed classification of all 1516 requirement candidates;
- generated faithful semantic blocks for migrated content;
- derivative concepts and requirements view populated from those records;
- no duplicate semantic owner between page fragments and semantic source.

All 161 definitions, 33 clauses, four references, and 20 framework-rule
records now load through the canonical model; the 20 requirements are emitted
as generated faithful build data and derivative input. The original definition
page typography remains a deliberate fidelity adapter, but it is now fed from
the semantic definition records rather than owning semantic identity or
machine-readable content.

### M10 — Make 1516.1 operationally complete

**Status: complete for the modeled operational surface.**

Migrate the federate interface specification's service families, callback
behavior, state-machine prose and figures, tables, and conformance links.

Deliverables:

- all 24 canonical state machines and 281 transitions source-linked;
- complete event/state/guard/action/precondition/postcondition records where
  present in the standard;
- every confirmed requirement attached to a clause and applicable transition
  or explicitly marked document-wide;
- each implementation-relevant transition mapped to an RTI service,
  callback, adapter, code symbol, N/A, or deferred work item;
- derivative state-logic and traceability views become useful for RTI review,
  not just inventory reporting.

The model contains all 24 state machines and 281 transitions. Every transition
has a typed coverage classification and a reciprocal planned implementation
seam. Concrete RTI/federate symbols remain `planned` mappings, which is an
implementation-maturity distinction rather than a deferred semantic gap.
The 1,697 source-derived requirements are authoritative, clause-owned records;
15 have conservative direct transition links and the remainder are explicitly
cross-cutting at clause scope.

### M11 — Make 1516.2 structurally semantic

**Status: complete for the table/document structure surface.**

Migrate the Object Model Template's definitions, references, normative rules,
and complete table families while keeping coordinate geometry in the layout
adapter.

Deliverables:

- logical table schemas with continued-fragment and row/column ownership;
- typed OMT concepts and cross-references;
- all requirement candidates classified and confirmed normative content
  promoted with coverage contracts;
- generated table and requirement views in both faithful and derivative
  builds;
- no OMT coordinate vocabulary leaking into the generic semantic model.

All 89 tables, 2,840 typed cells, and 80 logical table families are loaded and
generated; continued fragments share logical IDs and preserve source
provenance. The derivative now renders those families and cells from the same
validated records.

### M12 — Authority switch and conformance release

**Status: complete for the current HLA tranche.**

Make the semantic corpus the normal authoring path for all confirmed semantic
content in the HLA tranche.

Acceptance gates:

- semantic records are the only normative owner for migrated content;
- a source-controlled authority manifest declares each migrated surface and
  its generated faithful consumer;
- faithful PDFs and the derivative are generated from the same records;
- a semantic mutation test proves the affected faithful and derivative views
  change together;
- all confirmed references resolve and all candidate gaps are classified;
- compliance queries and JSON exports are documented as stable consumers;
- CI verifies generation, builds, page counts, logs, diagrams, and Git hygiene.

The first authority slice is declared in `data/semantic/authority.json` and
validated by `scripts/semantic_authority.py`. It covers 161 1516 definitions,
20 1516 requirements, all 38 1516 content blocks, 439 1516.1 content blocks,
645 1516.1 content elements, all 1,697 1516.1 requirements, 32 reviewed
requirement-transition links, 281 transition coverage records, 281 planned
implementation mappings, and the complete 1516.2 semantic surface: 83
table-backed definitions, 340 explicit requirements, 122 content blocks, 1,078
content elements, and all 80 table families. A mutation test proves that
source-record changes reach generated faithful and derivative views. The
authority validator also fails on unresolved references, and no HLA
requirement candidate remains deferred.

### M13 — Prove HLA-neutral reuse

**Status: complete.**

Load and build a small non-HLA document fixture through the shared model,
builder, hierarchy, table, requirement, and reference interfaces.

`topics/fixture/non-hla-demo-2025/` is the reference fixture. It defines a
family-local source profile and LaTeX dialect, loads two hierarchy nodes, a
definition, a requirement, a generic table, and a reference, then generates
and builds a one-page PDF through the same common builder used by HLA. Its
tests cover hierarchy navigation, definition search, requirement matching,
table search, reference lookup, Pydantic round trips, generated faithful
inputs, and the generic derivative renderer.

The profile contract is documented in
[`DOCUMENT-FAMILY-ONBOARDING.md`](DOCUMENT-FAMILY-ONBOARDING.md). The generic
semantic model, generator, and renderer do not import HLA constants, and
table domain classification is supplied by the family profile instead of
being inferred from a table number. The M13 fixture is also part of the
release manifest, so CI checks its build, page count, log, and Git hygiene.

### M14 — Close semantic coverage contracts

**Status: complete.**

Candidate classification and transition coverage are now enforceable rather
than report-only. Every extracted requirement candidate has exactly one typed
review disposition, every modeled transition has a coverage disposition, and
the HLA dashboard scopes itself to HLA roots so non-HLA profiles cannot be
loaded with HLA vocabulary.

The gate is `python -m scripts.semantic_coverage --check --json`. It permits
explicitly deferred work, but fails on unreviewed candidates or unclassified
transitions. Release checks and CI invoke the same gate.

### M15 — Complete 1516 semantic content ownership

**Status: complete for the full 1516 content boundary.**

All 38 physical 1516 pages now consume generated content-block bodies. The
source-controlled `semantic/content-blocks.json` contains normalized text,
clause ownership, stable sequence, provenance, and an exact `layout_body`
fidelity field. The canonical navigation manifest contains the complete
33-clause order and parent relationships. Page files remain only as physical
layout adapters; definitions and requirements continue to be generated from
their dedicated typed records.

This completed the 1516 document-level source-of-truth boundary without
claiming that page-sized blocks were the final semantic granularity. M16 now
decomposes those blocks into typed paragraph, list, list-item, note, footnote,
and cross-reference records. Formula records are supported by the contract;
the 1516 source contains no mathematical formula surface. Exact layout bodies
remain explicit fidelity exceptions only where necessary for faithful
rendering.

### M16 — Complete 1516.1 prose, requirements, and operational mappings

**Status: complete for IEEE 1516.1-2025.**

The typed content decomposition infrastructure is now applied to the entire
1516.1 source boundary: 439 content blocks and 645 content elements provide
provenance-owned prose inputs. All 1,690 source-shaped normative candidates
are promoted into 1,697 authoritative Pydantic `Requirement` records (the
seven previously authored records remain stable), every record has clause
ownership, and the review queue is empty. Conservative same-clause event
matching creates 32 reciprocal requirement-transition links for 15 directly
transition-covered requirements; the remaining requirements are explicitly
cross-cutting rather than silently attached to a state machine.

All 281 modeled transitions have reciprocal `TransitionCoverage` and
`ImplementationMapping` records. The 281 mappings are intentionally `planned`
seams, so M16 closes semantic and operational traceability without claiming
that concrete RTI implementation code already exists. `build.py` now passes
all 1,697 requirement IDs to semantic generation, making the full typed
requirement surface a normal faithful build input. The repeatable migration is
`scripts/complete_15161_m16.py`; the exit gate is the M16 completion test,
semantic coverage check, 338-page faithful build, authority check, and release
validation.

### M17 — Complete 1516.2 prose, definitions, requirements, and table semantics

**Status: complete for IEEE 1516.2-2025.**

M17 closes the remaining 1516.2 semantic gap. All 340 source-shaped normative
candidates are now explicit, clause-owned Pydantic `Requirement` records with
cross-cutting coverage notes, and the review queue is empty. The migration
also derives 83 reusable `Definition` records from populated OMT `Semantics`
table cells, preserving the table-cell source provenance rather than copying
meaning into page-local LaTeX.

The 1516.2 source now owns 122 typed content blocks and 1,078 readable content
elements, while retaining all 89 tables, 2,840 cells, and 80 logical table
families with continuation and clause links. Its builder emits definitions,
requirements, content records, and table families as normal generated inputs;
page files remain thin fidelity adapters. The migration is repeatable through
`scripts/complete_15162_m17.py`, and the regression gate is
`tests/test_milestone17.py` plus the authority, coverage, release, faithful
build, and visual checks.

### M18 — Full hierarchy-driven document compiler

**Status: complete.**

The common generator now compiles every validated document model into a
Pydantic hierarchy graph. The generated contract contains canonical clause
nodes, parent/child order, direct record ownership, stable anchors, explicit
cross-record links, and unassigned-record visibility. Each faithful build
receives the ignored `hierarchy.json` and `hierarchy-index.tex` inputs, while
page adapters get stable semantic anchors at their source boundaries. The
derivative renders its hierarchy from the compiler rather than independently
walking page-shaped or hand-maintained clause data.

The compiler remains HLA-neutral; source vocabulary and LaTeX commands stay in
family profiles. State and transition destinations are namespace-qualified in
the compiled graph when their source IDs overlap. M18 tests cover Pydantic
round trips, hierarchy mutation, overlapping state/transition IDs, generated
faithful inputs, derivative serialization, and the non-HLA fixture.

### M19 — Complete compliance/API queries and implementation mappings

**Status: complete for the semantic compliance contract.**

The generic `DocumentModel` now exposes typed state/event applicability results,
serializable `ComplianceQueryResult` reports, corpus document selection, and
mapping filters for requirements, clauses, transitions, interface kinds, and
statuses. Effective transition coverage distinguishes `unmapped`, `planned`,
`partial`, `implemented`, `verified`, and `mixed` mappings. Consumers can opt
into a concrete-implementation gate without changing the default semantic
coverage gate.

`ImplementationMapping` retains the stable `implementation` symbol for
compatibility and now provides a structured `ImplementationReference` target.
Legacy string-only records normalize deterministically to a symbol reference;
repository/path/line evidence remains optional until the RTI implementation
repository is in scope. The compliance CLI exposes the same typed applicability
and mapping filters, including `--document` for multi-document corpus queries.

M19 intentionally preserves the distinction between a complete semantic seam
and concrete code evidence: all 281 IEEE 1516.1 transitions have planned
mappings, but none are promoted to `implemented` or `verified` by inference.
The regression gate is `tests/test_milestone19.py` plus the full test suite,
lint/format, semantic authority/coverage, release, and source-hygiene checks.

## Slice-level acceptance checklist

Before calling a migration slice complete, record:

1. document and semantic surface;
2. source records and stable IDs added;
3. duplicated page-local owner removed;
4. Pydantic validation and query tests added;
5. generated faithful and derivative outputs rebuilt;
6. source-shape metric change or new semantic relationship;
7. visual/release checks passed; and
8. generated outputs left ignored and untracked.

This makes progress measurable without baselining binary analogues or audit
files.
