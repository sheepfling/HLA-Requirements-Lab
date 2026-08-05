# HLA semantic reconstruction roadmap

This is the working backlog for turning the three HLA 1516 documents into
hierarchical, data-backed source. It is a delivery plan, not a verification
report. The rendered PDFs remain an output of the source model and its layout
adapter; they are not the source of truth.

For the execution order, statuses, dependencies, and milestone exit gates,
see [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md). This document remains the
strategic rationale and detailed implementation backlog; the execution plan is
the task-facing dashboard.

The concrete post-M7 source-of-truth milestones, deliverable layers, current
coverage baseline, and authority-switch acceptance gates are maintained in
[`DATA-DRIVEN-DELIVERABLES.md`](DATA-DRIVEN-DELIVERABLES.md).

The HLA standards are the initial corpus, not the endpoint. The project has a
three-stage purpose:

1. Recreate the original documents faithfully, retaining their structure,
   wording, layout behavior, and provenance.
2. Extract the recreated source into validated semantic records that capture
   hierarchy, requirements, definitions, meanings, functional preconditions
   and postconditions, tables, and state-machine behavior.
3. Generate a new, more programmatic document from those records, making
   normative relationships and conformance logic explicit for both people and
   software.

The original recreations remain fidelity references. The semantic model is the
reusable source for conformance queries and the new document, while the new
document is an intentional derivative rather than a replacement for the
original recreation.

## North star

The repository should make it possible to answer questions such as:

- Which clause owns this requirement?
- Which definitions and references does a requirement depend on?
- What state-machine event, guard, action, and postcondition implement this rule?
- Which HLA RTI behavior does a code path claim to satisfy?
- Can the same semantic records generate both a readable standard and a
  machine-checkable conformance view?

The core boundary is:

```text
original reconstruction -> semantic records -> hierarchy/navigation
                                  |                    |
                                  +-> faithful recreation PDF
                                  +-> next-generation programmatic document
                                  +-> RTI conformance queries and code exports
```

Page geometry, fixed coordinates, and page-break decisions belong in the
layout layer. Clause identity, normative text, definitions, references, and
state transitions belong in the semantic layer.

## Current baseline

Run the source-shape metric from the repository root:

```powershell
python -m scripts.semantic_metrics
python -m scripts.semantic_metrics --json
```

The command is deliberately stdout-only. Do not commit its output as an audit
artifact; use the values to measure progress between migrations.

Figure-derived diagram inventory is tracked separately in
`docs/STATE-MACHINE-EXTRACTION-PLAN.md` and `data/state_machines/`. The
document-local `semantic/` records in this roadmap are authored semantic
source; they do not replace the figure inventory or baseline its image files.
The state-machine backlog covers both 1516.1 and 1516.2 as separate scopes:
1516.1 has a 43-candidate lifted-image inventory awaiting figure-group
classification, while 1516.2 is explicitly tracked as a source-page/vector
review with no state-diagram markers found in the current source.

The current smell profile is intentionally asymmetric:

| Document | First migration concern | Why |
| --- | --- | --- |
| 1516 | Prove the semantic boundary | It already exposes clause, definition, and requirement records in source. |
| 1516.1 | Extract the most reusable semantics | Its services, interactions, and lifecycle logic are the best input to RTI conformance data. |
| 1516.2 | Isolate layout machinery | It has the largest fixed-coordinate/page-fragment burden, so it should move behind a layout adapter rather than become the semantic model. |

The metric names are stable enough to use as a lightweight progress gauge:

- `page_fragment_ratio` measures how much content is organized around page
  files instead of semantic units.
- `fixed_coordinate_markers` measures layout instructions mixed into source.
- `stable_id_markers` measures the existing identity scaffolding.
- `heading_markers`, `definition_markers`, and `requirement_markers` measure
  the records that can become generator inputs.
- `data_files` measures committed text-based data already available to the
  model.
- `scripts/layout_model.py` reports the text-bearing layout blocks that remain
  in the coordinate adapter; its output is also stdout-only.

## Backlog

### 1. Establish the common schema

- [x] Parse clauses into stable IDs, numbers, titles, parent IDs, levels, and
  source references from both semantic headings and existing PDF bookmarks.
- [x] Parse definitions and normative requirements into reusable records.
- [x] Expose clause paths, child clauses, definition search, and requirement
  matching through Python.
- [x] Use strict Pydantic models for semantic loading, validation, JSON
  serialization, and round-trip deserialization.
- [x] Isolate HLA source macros and LaTeX command names in
  `scripts/hla_profile.py`; keep rendering dialect-neutral in
  `scripts/latex_renderer.py`.
- [x] Extract 1516.2 table captions and cell text into typed `Table` and
  `TableCell` records with source references and logical row/column placement.
- [x] Add explicit records for references, notes, figures, examples, and
  annexes, retaining source spans and keeping analogue binaries out of the
  model.
- [x] Split the HLA source parser from the compatibility entry point so future
  document profiles can provide their own source adapter through the generic
  `LatexSourceProfile` contract in `scripts/source_adapter.py`.
- [x] Extend table records with OMT classification, logical table IDs,
  continued-fragment provenance, and an in-memory merged-table view.
- [x] Replace the placeholder state-machine tuple with typed `State`,
  `Transition`, and `StateMachine` records.
- [x] Give explicit requirements normalized `clause_id`, source spans, and
  machine-oriented statement text; retain additional source-shaped normative
  surfaces as explicitly labeled `candidate` records until reviewed.

### 2. Make hierarchy the primary document structure

Milestone 3 is complete for the hierarchy and navigation boundary. Clause
order is canonical by semantic number, parent references and cycles are
validated, and the same model emits semantic-ID headings, anchors, bookmarks,
and qualified cross-document destinations. The source loader follows each
document's `main.tex` include graph; ownership is carried across fragment
boundaries instead of inferred from page-fragment filenames.

Two plain 1516 definitions (`def-accuracy` and
`def-available-directed-interactions`) have crossed the ownership boundary
into authored semantic JSON. Rich definition and normative-text migration is
intentionally tracked as the next generator-adoption slice because those
records still contain page-specific line breaks and layout contracts.

Clause 3 and subclause 3.1 now use the semantic heading commands at their real
content location, so their titles, ownership, anchors, and bookmarks are no
longer duplicated in the page navigation file.

1516.1 service and component bookmarks are represented as a complete semantic
parent/child tree, including the fixed-block service roots. 1516.2's existing
canonical navigation manifest supplies its authoritative clause and annex
titles instead of leaving those roots as content-marker placeholders.

- [x] Define one canonical source order for roots, clauses, subclauses,
  definitions, requirements, and annexes.
- [x] Move headings and ownership out of page-fragment filenames.
- [x] Ensure every clause has one parent or an explicit document root; the
  Pydantic model now rejects missing parents and hierarchy cycles.
- [x] Generate navigation and clause outlines from the same hierarchy used by
  the renderer. The faithful 1516 build also emits rule and Annex A/B
  destinations at their content locations.
- [x] Define the cross-document link contract for shared terms and references
  across 1516, 1516.1, and 1516.2. Generated targets and links share the
  `<document-id>:<record-id>` destination format; populating every shared-term
  link remains part of content migration.

### 3. Extend the generator boundary

The hierarchy boundary is complete; the remaining work below is generator
adoption and content migration. It is deliberately separate from the
faithful-recreation build so layout-specific line breaks and coordinate
adapters do not leak into the generic semantic schema.

- [x] Provide opt-in LaTeX renderers for headings, definitions, requirements,
  tables, and outlines.
- [x] Parse fixed-coordinate text blocks into a separate layout model so
  geometry can be migrated without treating coordinates as document meaning.
- [x] Run profile-driven semantic generation before every document build and
  load its generated manifest from each document's `main.tex`; every manifest
  also consumes a generated semantic index and selected record data blocks.
- [x] Provide a portable LaTeX `tabular` renderer for selected semantic tables;
  integrate it into the document build after domain-specific table schemas are
  stable.
- [x] Keep the shared builder and semantic generator focused on model loading
  and record rendering; leave document-specific LaTeX focused on layout
  adapters, TikZ geometry, and exceptional formatting.
- [x] Generate page navigation and stable anchors from semantic IDs for the
  migrated hierarchy and build entry points.
- [x] Remove duplicated definitions and normative statements from the migrated
  proof slices; retain only one source record per migrated semantic item.

### 4. Migrate the documents in risk order

- [x] **1516:** finish the definition and Clause 3 proof slice and use it as
  the reference generator contract.
- [x] **1516.1:** migrate the federate-lifetime/service-family slice into
  semantic records, including requirements, transitions, and callbacks.
- [x] **1516.2:** migrate one typed OMT table family through the layout adapter;
  do not copy its coordinate vocabulary into the semantic schema.
- [x] Keep each migration buildable and preserve the current page-count
  smoke checks: 1516 = 40 pages, 1516.1 = 338 pages, 1516.2 = 124 pages.

### 5. Add state-machine and RTI conformance data

- [x] Model states, events, guards, actions, preconditions, postconditions,
  and transitions with stable IDs and source references.
- [x] Capture the prose-visible portion of the 1516.1 federate-lifetime
  machine in `topics/ieee/hla-1516.1-2025/semantic/`.
- [x] Encode the HLA printer's dagger semantically as
  `transition.initiator = "rti"`; renderers derive `\textdagger{}` from that
  field instead of treating the glyph as event text.
- [x] Inventory the 1516.1 and 1516.2 state-machine scopes separately; keep
  1516.1's lifted state-diagram groups distinct from the 1516.1 prose pilot,
  and keep 1516.2's no-diagram finding open until source-page review is done.
- [ ] Transcribe the remaining figure-only transitions and preserve parallel
  state-machine regions explicitly.
- [x] Link transitions to owning clauses and the reviewed pilot normative
  requirements; leave the remaining figure-only transitions visible as gaps.
- [x] Add a code-facing query API for “requirements applicable in state S after
  event E” and “transitions missing an implementation mapping.”
- [x] Define an implementation mapping format for RTI services, callbacks,
  and local adapter code.
- [x] Add semantic checks for missing transition targets, orphaned
  requirements, duplicate IDs, and unresolved references.
- [x] Export JSON for programmatic consumers without committing generated
  exports.

### 6. Milestone 4: connect semantics to compliance use

Milestone 4 is complete for the compliance-model boundary. The 1516.1 pilot
promotes seven reviewed federate-lifetime requirements and attaches them to
specific transitions. The model keeps the much larger source-shaped candidate
set available for the next review slices, while default compliance queries
only use reviewed records. Implementation mappings use stable RTI/federate
code symbols and carry an explicit lifecycle status; they are intentionally
still `planned` until the implementation repository is connected.

- [x] Link requirements, state machines, and transitions to existing clause
  IDs; materialize missing semantic clause ancestors before validation.
- [x] Add strict validation for duplicate IDs, unresolved clause/requirement/
  implementation/transition references, invalid state targets, and invalid
  state-parent relationships.
- [x] Add typed RTI service, callback, adapter, and handler implementation
  mappings with status and source-facing implementation references.
- [x] Support queries for requirements applicable after a state/event pair and
  transitions without implementation mappings.
- [x] Report orphan requirements and orphan implementation mappings as typed,
  non-fatal compliance issues so incomplete migration remains inspectable.
- [x] Promote reviewed candidate requirements to explicit compliance records
  and attach them to individual transitions. Remaining candidates stay
  reviewable and are not silently promoted.
- [x] Require explicit coverage semantics for every promoted requirement and
  provide a source-only promotion workflow with reciprocal link validation.
- [x] Emit a deterministic semantic coverage dashboard for reviewed records,
  candidates, implementation mappings, and typed remaining gaps.
- [x] Replace placeholder implementation references with stable RTI and
  federate code symbols, and carry implementation-level lifecycle status.
- [x] Add `ReferenceTarget` records plus corpus-level resolution and typed
  unresolved-target reporting for shared terms and normative references.

The corpus report is stdout-only. It does not create or baseline audit files;
unmapped transitions and orphan requirements remain visible as typed findings
until the next migration slice supplies their reviewed links.
The repeatable contract checks live in `tests/test_milestone4.py` and exercise
all three document roots, including negative validation cases.

### 7. Milestone 5: integrate generation into builds

Milestone 5 is complete for the build-integration boundary. Every document
build loads its typed semantic model before invoking LaTeX, includes an ignored
generated manifest, and consumes a generated semantic index. Selected
definition and requirement records also produce layout-consumable TeX data
macros; the 1516.1 lifecycle page uses the generated Connect requirement
through its fixed-coordinate layout adapter. The generic loader, renderer,
layout inventory, and state-machine exporters accept profiles; HLA command
vocabulary is confined to `scripts/hla_profile.py` and the HLA adapter facade.
This keeps the reusable pipeline available to future document families without
making HLA constants part of the model layer.

- [x] Add a common builder hook that runs semantic generation before `latexmk`.
- [x] Generate ignored, deterministic semantic build inputs for all three
  documents, load the manifest from each `main.tex`, and load the semantic
  index from each manifest.
- [x] Keep the selected 1516 definition migrations on generated semantic
  blocks rather than duplicated page-fragment definitions.
- [x] Emit typed definition/requirement data macros separately from visible
  LaTeX renderings so fixed-coordinate adapters can consume semantic text
  without owning it.
- [x] Export validated state machines as Graphviz DOT and Mermaid text.
- [x] Extend visual-review packets with TikZ, DOT, Mermaid, and optional
  Graphviz SVG provenance; skip SVG generation cleanly when `dot` is absent.
- [x] Keep PDFs, exports, review packets, audits, and build products ignored.
- [x] Add regression tests for profile isolation, generation, exports, review
  hygiene, and all three builder entry points.
- [x] Run the source-level CI contract, including the batch visual-review
  workflow and optional Graphviz path.

The current build smoke contract remains 1516 = 40 pages, 1516.1 = 338
pages, and 1516.2 = 124 pages. Generated files are intentionally written below
ignored `output/`, `review-artifacts/`, and `.tmp/` paths; no audit output is a
source artifact.

The remaining document-content migration and PDF-matrix work is intentionally
tracked separately below; it is not a prerequisite for the completed M4
vertical slices or the reusable build-integration boundary delivered by M5.

### 8. Post-M7 source-of-truth work

The remaining content migration, semantic coverage, authority-switch, and
non-HLA reuse work is now specified as M8-M13 in
[`DATA-DRIVEN-DELIVERABLES.md`](DATA-DRIVEN-DELIVERABLES.md). M6 generated the
first derivative and M7 completed the full PDF/CI release checks; the next
work is to increase semantic coverage rather than add another parallel
document pipeline.

## Progress metrics and exit criteria

Use `scripts/semantic_metrics.py` at the start and end of each migration slice.
The target is not to eliminate every page fragment immediately; it is to move
semantic ownership out of those fragments while keeping the visual result
stable.

Milestone 1 is complete when the shared model can load all three source trees,
validate round trips, retain source spans, represent non-prose requirement
surfaces without binary inputs, and provide a typed record for every currently
recognized structural surface. Candidate requirements are intentionally not
treated as implementation-ready compliance rules; their review and promotion
to explicit records belong to the document migration milestones.

| Metric | Near-term target | End-state target |
| --- | ---: | ---: |
| `page_fragment_ratio` | Establish baseline for all three docs | < 0.10 for semantic source |
| `fixed_coordinate_markers` in semantic blocks | No new growth | 0; coordinates live in layout adapters |
| Clauses with parent/root and source reference | 1516 complete | 100% across all three docs |
| Normative requirements with `clause_id` and machine text | 1516 complete | 100% across all three docs |
| Duplicate definitions or normative rules | Inventory duplicates | 0 semantic duplicates |
| State transitions with event/guard/action/target | Schema defined | 100% of modeled transitions |
| Build reproducibility | Keep all three builds passing | 40 / 338 / 124 pages without source drift |

## Working rules

- Commit source, schemas, generators, and provenance—not PDFs, scans, build
  directories, extracted page images, or audit output.
- Use analogue documents locally for comparison only; they are not baseline
  inputs to the semantic model.
- Land small migration slices. A slice should leave the document buildable and
  make one metric better or one semantic relationship more explicit.
- Prefer stable IDs and source references over positional assumptions such as
  “the third block on page 18.”
