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
semantic coverage check, 440-page faithful build, authority check, and release
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

### M20 — Complete data-driven diagram rendering and visual acceptance

**Status: complete for the 1516.1 diagram tranche.**

State-machine TikZ now comes from validated Pydantic records with deterministic
scaling and safe optional-layout defaults. The new sequence-diagram contract
captures participants, ordered messages, response correlation, clause links,
and source provenance, and exports to Mermaid and TikZ. Figures 22–33 are
generated semantic inputs in the faithful 1516.1 build; extracted raster
analogues remain comparison-only and are not tracked. The faithful build now
includes all source pages through 439 and produces 440 pages.

Visual acceptance is enforced through `scripts/diagram_qa.py`, compiled review
previews, faithful-page rendering, semantic diagram tests, release page-count
validation, and source-only Git hygiene. The model and exporters are generic;
only the published HLA page rectangles live in the HLA layout adapter.

### M21 — Migrate the remaining diagram surfaces

**Status: complete for the faithful 1516.1 figure tranche.**

The remaining early raster adapters and previously blank Figure 18–21
surfaces are now driven by semantic records. Figures 1–17 are bound to typed
state machines, Figure 2 is a generic relationship graph, Figures 18–21 are
generic conceptual/hierarchy/architecture graphs, and Figures 22–33 remain
typed sequence/state diagrams. The complete surface inventory is
`data/semantic/diagram-surfaces.json`; generated records are emitted through
TikZ and Mermaid without baselining comparison binaries.

The faithful build now has zero binary figure dependencies in generated
content blocks. `scripts/diagram_surface_qa.py` enforces the 33-surface
contract and explicit non-generatable asset classifications. The RTI-oriented
`scripts/rti_diagram_check.py` reports transition, sequence-message, and graph
edge mapping gaps for later implementation verification.

### M22 — Make prose fully semantic

**Status: complete for the faithful visible-surface contract.**

The shared Pydantic model now owns the visible semantic payloads that were
still embedded in generated layout bodies: normative requirement statements,
definitions, bibliography references, figure captions, table captions, and
explicit notes/footnotes. The loaders recover these records from the authored
`ContentBlock.layout_body` fidelity field after page adapters become thin, so
ownership no longer depends on a page fragment being the semantic source.

Faithful generation emits dedicated reference, figure, note, and table data
inputs and substitutes semantic macros into the coordinate-preserving block
bodies. Definitions and requirements continue to use their typed data inputs.
The derivative now renders the same references, figures, notes, table captions,
and reusable content elements from the validated model. Coordinates,
typography, line-break hints, and exceptional wrappers remain the explicit
fidelity boundary; they are not semantic ownership.

The authority manifest covers the new reference, figure, note, and table
surfaces. `tests/test_milestone22.py` proves the three document counts, thin
page adapters, generated macro inputs, and mutations to references, figure
captions, and table captions reaching both faithful and derivative products.
The 40-page, 440-page, and 124-page faithful builds remain green, and generated
outputs remain ignored rather than baselined.

### M23 — Complete semantic tables and cross-references

**Status: complete for all presently authored table and cross-reference surfaces.**

Explicit and visible source references now produce typed `CrossReference`
records with stable owners, local target IDs, target labels, relation kinds,
and source provenance. The faithful generator emits projection files, while
the derivative renders the same relationships as hyperlinks. The loader
recovers 1516.1's 161 definitions plus 92 physical table fragments grouped
into 46 logical families and 2,047 cells. 1516.2 validates 89 tables, 80 table
families, 2,840 cells, and eight continuation fragments. 1516 has no physical
table surface; its zero count is declared rather than silently omitted.
Family membership, duplicate cell IDs, missing targets, and invalid
cross-reference owners/targets fail validation. `tests/test_milestone23.py`
covers all three documents, faithful/derivative link emission,
definition-label mutation, table ownership, and invalid-target rejection.

### M24 — Build the compliance-facing corpus

**Status: complete for the current authored corpus.**

`ComplianceCorpus` now provides Pydantic projections for cross-document
requirements-after-event queries, state/sequence implications, qualified
dependency edges, unresolved cross-document references, missing transition
mappings, and implementation evidence. Mapping evidence is explicitly split
between planned/partial and concrete implemented/verified status, with an
additional source-backed flag. All 281 modeled state transitions are direct
implications; the 14 sequence messages are explicitly `unlinked` because the
source does not author direct transition relationships. Exact visible table
labels produce definition dependencies for 81 1516.1 cells and 65 1516.2
cells, while all remaining cells retain table/family ownership. The CLI
exposes the projection through
`scripts.compliance --corpus-report --json`; reports remain stdout-only.

All 281 RTI mappings are explicitly reported as planned and non-concrete; they
are not falsely upgraded to implementation evidence. A future implementation
repository can replace those records with concrete evidence through the same
typed query surface.

## Post-M24 structured-document program

M8-M24 establish the semantic corpus, faithful builds, hierarchy compiler, and
compliance query contract. They do not yet constitute the finished
next-generation standard. The next phase is therefore publication work: move
semantic ownership out of page-shaped fidelity inputs, define an intentional
hierarchy-first information architecture, and render a useful document from
that architecture.

The post-M24 program has five completion principles:

- the canonical hierarchy, not page-fragment order, determines document
  ownership and navigation;
- the derivative is a readable, reflowable publication with deliberate views,
  not a record dump;
- every confirmed semantic surface is either modeled, generated, or explicitly
  classified as layout-only/deferred;
- faithful recreation and derivative publication remain separate products that
  consume the same semantic records; and
- compliance evidence distinguishes semantic claims from concrete, verified
  implementation evidence.

### M25 — Define the hierarchy-first publication contract

**Status: complete.**

Specify the new document before broad migration begins. The contract will
define the canonical outline, section roles, document profiles, view order,
stable anchors, and the relationship between normative content and explanatory
content. It will also define the minimum derivative sections:

1. scope, concepts, and terminology;
2. normative clauses and requirements;
3. services, APIs, callbacks, and operational behavior;
4. state machines and message sequences;
5. semantic tables and reusable definitions; and
6. traceability, dependencies, and compliance annexes.

Deliverables:

- a typed publication profile and canonical derivative outline;
- explicit projection contracts for clauses, requirements, definitions,
  services, diagrams, tables, and traceability;
- stable navigation/anchor rules for the new publication; and
- a small generated skeleton proving the outline is driven by the hierarchy.

Exit gate: a clean build produces a navigable derivative skeleton from the
compiled hierarchy, with no hand-maintained clause order or duplicated
normative text in the derivative source.

The contract is implemented by the generic Pydantic records in
`scripts/publication_contract.py` and the HLA-owned profile at
`topics/ieee/hla-semantic-derivative-2025/semantic/publication.json`. The
generator emits `publication-contract.json` and `publication-outline.tex`
below ignored output; the M26 derivative body consumes the same profile as its
normal reflowable input. `tests/test_milestone25.py` covers canonical ordering,
invalid-contract rejection, stable destinations, and generic fixture output.
The contract-era record view was validated at 2,591 pages; the current
reflowable derivative path is release-tracked separately as its own publication
surface.

### M26 — Build the reflowable hierarchy-first compiler

**Status: complete for the structured derivative publication.**

Make the derivative a real document compiler rather than a collection of
semantic reports. Generate section headings, prose, definitions, requirements,
cross-references, tables, figures, and annexes from canonical records. Keep
page files limited to faithful-layout coordinates, typography, line-break
exceptions, and other explicitly declared fidelity data.

Deliverables:

- reflowable section and clause renderers;
- generated table, definition, requirement, figure, and reference projections;
- table of contents, indexes, bookmarks, and semantic cross-links;
- a document-level style/profile layer independent of HLA vocabulary; and
- mutation tests proving a semantic change reaches the relevant faithful and
  derivative views.

Exit gate: the derivative can be regenerated from a clean checkout after
deleting all generated output, and its ordinary prose is sourced from semantic
records rather than page-fragment bodies. The page-fragment ratio must fall by
at least 25 percentage points in each document touched by the slice.

The compiler is implemented in `scripts/reflowable_renderer.py`.
It groups definitions, requirements, prose elements, state behavior, tables,
and traceability under canonical clause ownership, renders candidate
requirements with an explicit non-normative label, and emits the generated
`reflowable.tex` view. The HLA derivative now builds from that view as its
normal input; the earlier record-reference stream remains generated as an
ignored comparison/annex source. The HLA derivative compiles at 1,241 pages
with no fatal log findings, and its reflowable traceability view receives the
M29 graph projection. The derivative source has a zero page-fragment ratio.

The faithful recreations intentionally retain page-sized adapters because
their job is pagination and visual comparison. Those adapters are a separate
publication path and are not ordinary prose input to the structured
derivative, so they do not block M26 completion.

### M27 — Close semantic surface gaps

**Status: complete for the current authored corpus.**

Finish the semantic depth that is currently only structurally classified.
Transcribe remaining figure-only transitions and parallel regions where the
source supports them; enrich sequence-message relationships; model meaningful
table rows, columns, attributes, constraints, and service/API fields; and
promote reusable definitions and dependencies without duplicating their text.

Deliverables:

- explicit records or reviewed classifications for every remaining semantic
  candidate;
- complete state/sequence semantics for the accepted 1516.1 operational scope;
- reusable table projections beyond captions and cell ownership; and
- a coverage report showing no silently unowned normative or operational
  surface.

Exit gate: all confirmed semantic surfaces have stable IDs, provenance,
hierarchy ownership, and a generated consumer. The aggregate target is a
page-fragment ratio below 0.10 for semantic-owned source; remaining layout
adapters must be listed as intentional fidelity boundaries.

The M27 closure is complete: all 281 1516.1 implementation seams
now carry explicit source provenance, including 247 mappings authored in
`semantic/implementations.json`; their lifecycle status remains `planned`, so
provenance has not been confused with concrete RTI evidence. All 14 sequence
messages are also source-backed and remain explicitly `unlinked` because the
source does not provide direct state-transition relationships. The coverage
gate reports zero semantic records without source, no unresolved references,
and no unclassified transition or diagram surfaces. Page-sized faithful
adapters remain explicitly classified fidelity boundaries rather than hidden
semantic gaps.

### M28 — Publish the structured derivative document

**Status: complete.**

Use the M25-M27 contracts to produce the first complete, intentionally
structured derivative for the HLA tranche. It should optimize for navigation,
understanding, and reuse rather than reproducing the original pagination.

Deliverables:

- a coherent front matter, body, and annex structure;
- readable requirement, service, state-machine, and table views;
- definition and reference navigation across 1516, 1516.1, and 1516.2;
- traceability and dependency annexes generated from the compliance corpus; and
- visual review of the derivative as a publication, including typography,
  density, page breaks, diagrams, tables, and navigation.

Exit gate: reviewers can follow a requirement from clause to definition,
state/event behavior, table dependencies, and implementation seam without
opening page-fragment source files. The derivative has a reviewed outline and
visual acceptance independent of faithful-PDF page-count acceptance.

The exit gate is satisfied. Representative front matter, clause transitions,
operations, traceability, and closing annex pages were rendered and visually
reviewed; the release gate independently confirms 1,241 derivative pages,
clean logs, complete semantic authority, and no tracked generated output.

### M29 — Build the cross-document semantic graph

**Status: complete for the current 2025 HLA corpus.**

Make the three standards behave as one navigable corpus while preserving their
document identities. Add shared-term links, normative dependencies, edition
and relationship metadata, duplicate/near-duplicate analysis, and reports for
conflicting or superseded definitions and requirements.

Exit gate: corpus queries can traverse document boundaries with qualified IDs,
and the derivative can render those links without ambiguous ownership or
duplicate semantic definitions.

The graph is implemented in the generic
`scripts/corpus_graph.py` module. `CorpusSemanticGraph` validates document
descriptors, qualified record nodes, and typed edges with explicit, derived,
or candidate evidence. Existing semantic dependencies become qualified graph
edges; exact shared definition terms and exact shared requirement statements
are emitted only as reviewable candidate edges, never as inferred normative
links. The derivative generator emits the ignored `corpus-graph.json` artifact
and renders cross-document edges in its traceability projection. The HLA
corpus currently produces 12,883 nodes, 38,323 edges, 168 review findings,
and 158 exact shared definition-term candidates. The findings include 121
duplicate-definition matches, 37 conflicting-definition matches, and 10
near-duplicate-definition matches. `tests/test_milestone29.py` covers explicit
versus candidate evidence, edition/relationship metadata, qualified
traversal, review findings, and Pydantic round trips.

Edition and relationship metadata are source-controlled in
`semantic/corpus.json`; near-duplicate and conflict findings are emitted as
review records, while exact shared terms remain candidate edges rather than
invented normative links. The current 2025 corpus has no superseding edition,
so there is no supersession relationship to infer. The graph is therefore
complete for the corpus in scope; candidate and warning findings remain
intentional review outputs.

### M30 — Connect concrete RTI compliance evidence

**Status: planned; awaits implementation repository scope.**

Replace planned implementation seams with concrete service, callback, adapter,
handler, and code-symbol evidence when the RTI implementation enters scope.
Add executable conformance checks for preconditions, postconditions, state
transitions, and applicable requirements. Keep absent implementation evidence
explicit rather than inferring it from semantic mappings.

Exit gate: every in-scope transition and implementation mapping is classified
as concrete, verified, intentionally not applicable, or explicitly deferred;
the corpus can answer compliance queries with source-backed evidence and the
derivative can render the evidence status.

### M31 — Publish the RTI compliance requirements document

**Status: complete for the current semantic corpus.**

Create a separate, hierarchy-driven engineering publication for implementation
planning and conformance review. It must turn the three standards into a
single readable and machine-queryable requirements contract without treating
an analogue, a planned seam, or a partial mapping as implementation evidence.

Deliverables:

- a source-controlled publication profile that names the corpus, scope, and
  evidence boundary;
- Pydantic manifest records for requirements, state transitions, implementation
  evidence, gaps, and semantic dependencies;
- a generated requirements catalogue grouped by document and clause, including
  machine expressions, operational bindings, and evidence status;
- a state/service transition matrix, evidence registry, and explicit gap queue;
- normalized CSV projections for spreadsheet and RTI-tool consumption, with
  separate link tables for one-to-many requirement/transition mappings; and
- a source-only build, release-manifest entry, mutation test, and visual PDF
  review.

The generic implementation lives in `scripts/compliance_publication.py`; the
HLA-specific profile and builder live in
`topics/ieee/hla-rti-compliance-2025/`. The generated publication is a
637-page compliance-readiness document built from all 2,057 requirements and
281 modeled transitions. Its ignored JSON manifest and `corpus-graph.json`
companion are the corresponding machine contracts; the latter carries 158
cross-document graph edges and review findings. The current 281 implementation
mappings remain `planned`, with zero concrete mappings, which is rendered as an
actionable gap rather than a claim of RTI conformance.
`tests/test_milestone31.py` verifies typed round trips,
requirement-to-operation/evidence binding, semantic mutation propagation to the
TeX and JSON outputs, and normalized CSV export rows.

### M32 — Generate faithful layout entrypoints

**Status: complete for the 2025 HLA faithful recreations.**

The three faithful `main.tex` files no longer own page ordering. Each consumes
one generated `output/semantic/faithful-body.tex`, projected from typed
content-block order and a source-controlled `semantic/faithful-layout.json`
profile. The profile is intentionally limited to non-semantic fidelity data:
page-range wrappers, navigation insertions, and declared layout-only pages.

The generic `scripts/faithful_renderer.py` writes both the LaTeX body and a
Pydantic JSON projection. `scripts.semantic_authority --check-generated --json`
now verifies that every profile adapter exists, no active `main.tex` directly
orders semantic pages, and the ignored generated projection exactly matches the
typed records. The release gate rebuilt and accepted the 40-page 1516,
440-page 1516.1, and 124-page 1516.2 PDFs.

This completes the data-first publication boundary: semantic records own
visible meaning and document order; document-local LaTeX owns only styles,
pagination, coordinate exceptions, and explicitly declared fidelity wrappers.
The remaining M30 boundary is concrete RTI implementation evidence, not
document reconstruction.

### Post-M24 dependency order

```text
M24 -> M25 -> M26 -> M27 -> M28 -> M29 -> M31 -> M32
                  \-> M30 (requires RTI implementation scope)
```

M25 fixed the publication contract before broad source migration. M26 is the
compiler and authority switch for reflowable prose. M27 closes semantic depth
that the compiler cannot invent. M28 is the complete structured publication,
M29 makes it a qualified multi-document corpus, and M31 projects it into an
implementation-facing requirements document. M32 moves faithful page ordering
behind the same typed source boundary. M30 proceeds when concrete RTI code and
test evidence are available.

### Post-M24 progress dashboard

In addition to the existing corpus and release checks, each post-M24 slice
must report:

- page-fragment ratio by document and semantic surface;
- percentage of ordinary prose generated from typed records;
- percentage of semantic records with hierarchy ownership and provenance;
- derivative sections generated from projections rather than hand-written
  source; and
- implementation mappings by planned, concrete, verified, not-applicable, and
  deferred status.

No dashboard, audit, PDF, image, or generated export is committed. These
measurements remain stdout-only or ignored local outputs.

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
