# Document recreation execution plan

This is the operational plan for turning the repository from faithful document
recreations into reusable semantic sources and, eventually, a generated
programmatic document. It supersedes the older milestone numbering in the
strategic roadmap; that roadmap remains the rationale and detailed backlog.

The concrete post-M7 source-of-truth plan and deliverable contract is in
[`DATA-DRIVEN-DELIVERABLES.md`](DATA-DRIVEN-DELIVERABLES.md). This execution
plan records the completed foundation and the dependency order; the linked
plan defines the measurable semantic-coverage targets for M8 onward.

The HLA standards are the first corpus, not the boundary of the architecture.
The plan must preserve three distinct products:

1. faithful recreations of the original documents;
2. validated semantic records that can be queried by software; and
3. a new derivative document that makes hierarchy, requirements, state logic,
   and conformance relationships explicit.

## Current position

| Area | Status | Evidence of completion or remaining work |
| --- | --- | --- |
| Source-only repository hygiene | Complete | Outputs, audits, reviews, and analogue binaries are ignored. |
| Common Pydantic semantic model | Complete | All three HLA source trees load and round-trip through typed models. |
| HLA-neutral core boundary | Complete for the current tranche | Generic loading/rendering code is separated from HLA profiles and adapters. |
| Authoritative hierarchy | Framework complete | Canonical clause order and ownership exist; broad content adoption remains. |
| Build integration | Complete | Semantic generation runs before each LaTeX build. |
| Diagram inventory and canonical models | Complete | 1516.1 has 43 classified candidates and 24 source-compared canonical machines; 1516.2 has a reviewed no-state-diagram scope. |
| Semantic content migration | M4 slices complete | 1516 definitions and summary rules, the 1516.1 connection/service family, and a 1516.2 OMT table family now have typed source ownership and generated build inputs. |
| Compliance coverage | M5 complete for promoted slices | Reviewed requirements have explicit coverage contracts; remaining candidates and unmapped transitions are typed backlog. |
| New programmatic document | M6 complete | The HLA semantic derivative builds from the corpus into four generated semantic views. |
| Full PDF CI and visual regression | M7 complete | Ubuntu TeX Live release job checks all four PDFs, logs, page counts, diagram status, and Git hygiene. |
| Data-driven source-of-truth plan | Defined | M8–M13 deliverables, coverage gates, baselines, and authority-switch criteria are documented in [DATA-DRIVEN-DELIVERABLES.md](DATA-DRIVEN-DELIVERABLES.md). |

## Non-negotiable quality gates

Every milestone and migration slice must satisfy these gates:

- No PDF, raster image, archive, audit, verification report, or generated
  review packet is committed as source.
- Pydantic loading, validation, serialization, and deserialization remain
  deterministic.
- Semantic IDs, clause ownership, source provenance, and cross-references are
  explicit; page numbers and fragment filenames are not ownership keys.
- Generated LaTeX is written below ignored output paths and is never edited by
  hand.
- The three faithful builds remain reproducible at 40, 338, and 124 pages
  unless a reviewed layout change intentionally changes a count.
- Every migrated record has a source reference and a test or validation rule
  that protects its contract.
- A migration slice must either lower a source-shape metric or add a semantic
  relationship that was previously unavailable.

## Milestones

### M0 — Reproducible source baseline

**Status: complete.**

Establish the repository as a source-only collection of document projects.

Deliverables:

- common document entry points and builder hygiene;
- branch-based work with generated products ignored;
- baseline page-count and source-shape measurements;
- no analogue documents or binary comparisons in Git.

Exit gate: all three documents build from the repository's text source and the
working tree contains no tracked build products.

### M1 — Generic semantic foundation

**Status: complete.**

Provide a reusable model for document structure rather than an HLA-specific
bag of parsers.

Deliverables:

- typed clauses, definitions, requirements, references, notes, figures,
  examples, annexes, tables, states, transitions, and implementations;
- strict Pydantic validation and JSON round trips;
- profile-driven source adapters and renderers;
- HLA commands and vocabulary isolated behind the HLA profile.

Exit gate: a generic consumer can load a document model without importing the
HLA profile, while the HLA documents continue to load successfully.

### M2 — Authoritative hierarchy and identity

**Status: framework complete; content adoption continues in M4.**

Make semantic hierarchy authoritative for ownership, order, navigation, and
cross-document destinations.

Deliverables:

- one canonical order for roots, clauses, subclauses, definitions,
  requirements, and annexes;
- parent/child and cycle validation;
- semantic-ID headings, anchors, bookmarks, and links;
- no ownership inference from page-fragment filenames.

Exit gate: every migrated item has one semantic owner, one stable ID, one
source reference, and one generated navigation destination.

### M3 — Diagram and sequence semantics

**Status: complete.**

Complete the diagram track without treating lifted images as the baseline.
The detailed checklist lives in
[`STATE-MACHINE-EXTRACTION-PLAN.md`](STATE-MACHINE-EXTRACTION-PLAN.md).

Deliverables:

- stable inventory classification for every extracted 1516.1 candidate;
- canonical records for the 24 currently modeled 1516.1 machines;
- explicit representation of self-loops, parallel regions, nested states,
  long labels, guards, actions, and layout exceptions;
- Figure 26 retained as a message-sequence diagram, not misclassified as a
  state machine;
- a documented 1516.2 no-state-diagram finding, with its table/vector review
  kept separate;
- TikZ, DOT, and Mermaid outputs with local visual-review packets;
- clause and requirement provenance on modeled transitions.

Exit gate: every candidate is classified; every modeled machine passes
structural validation; every visible semantic state and transition is either
regenerated or explicitly recorded as a non-semantic/layout exception; all
accepted diagrams have source comparison notes.

The diagram child plan records the accepted preview and provenance status for
each modeled machine. Requirement promotion and implementation coverage are
now tracked under M5 rather than treated as diagram completion work.

### M4 — Content migration vertical slices

**Status: complete.**

Move semantic ownership out of handwritten page fragments in small,
buildable slices. M4 is complete as three bounded vertical slices. Each slice
has typed source records, stable links, generated visible input, duplicate
prose removed from the migrated page adapter, and a passing document build.

- **1516:** the authored definition proof-of-concept remains generated, and
  summary rules 1 and 6 are promoted to explicit semantic requirements.
- **1516.1:** three federate-lifetime content blocks plus the Connect,
  Disconnect, Connection Lost, and Federate Resigned service family are linked
  to Clause 4, lifecycle transitions, and RTI service/callback mappings.
- **1516.2:** the Object model identification table family owns Tables 2 and
  3, including typed captions and continued-family membership.

- **1516:** finish the definitions and Clause 3 proof-of-concept, including
  visible generated definitions and normative requirement records;
- **1516.1:** migrate the federate-lifetime material and one complete service
  family, including its clauses, requirements, transitions, and callbacks;
- **1516.2:** migrate one complete OMT table family, including continued
  fragments, logical rows/columns, captions, and cross-references.

For each slice:

1. author or normalize the text-based semantic records;
2. attach clause IDs, source spans, definitions, references, and table links;
3. generate the visible LaTeX blocks from those records;
4. remove the duplicate normative text from page fragments;
5. preserve the faithful build and add contract tests.

Exit gate: satisfied. The selected slices have one semantic source record, no
duplicate normative owner, generated visible output, stable navigation, and
passing builds at 40, 338, and 124 pages. The source-shape metric did not
regress, and each slice added semantic relationships unavailable to the page
fragments alone.

### M5 — Compliance-ready semantic coverage

**Status: complete for the migrated slices.**

Turn reviewed semantic records into a dependable conformance surface rather
than treating every extracted sentence as a requirement.

Deliverables:

- promotion workflow from `candidate` to reviewed requirement;
- requirement-to-clause, transition, service, callback, and implementation
  mappings;
- explicit preconditions, postconditions, guards, actions, and state targets;
- cross-document definition and reference resolution;
- typed reports for orphan requirements, unmapped transitions, duplicate IDs,
  unresolved references, and invalid state targets;
- query coverage for requirements applicable in state `S` after event `E`.

The promotion workflow is implemented by
`scripts/promote_requirement.py`; it validates a candidate, coverage kind,
clause ownership, reciprocal transition links, and canonical state-machine
updates before writing semantic source. `scripts/semantic_dashboard.py` emits
the deterministic corpus coverage report used by CI. Candidate requirements
remain queryable with `--include-candidates` but do not count as reviewed
compliance coverage.

Exit gate for each migrated slice: every promoted requirement has clause
ownership and a reviewed relationship to its applicable transition or an
explicit reason why no transition applies. This gate is satisfied by the
9 promoted records currently in the three-document tranche (7 transition-
covered in 1516.1 and 2 document-wide in 1516). All remaining gaps are typed
and visible rather than silently omitted.

### M6 — Programmatic derivative document

**Status: complete.**

Generate a new document from semantic records instead of reorganizing copied
page fragments.

The first derivative should contain four generated views:

1. concepts and definitions;
2. normative requirements with pre/postconditions;
3. state machines and event/transition logic; and
4. traceability from requirements to clauses, services, callbacks, and code.

`main.tex` for this document should contain layout and exceptional formatting,
not duplicated normative prose. The source model must be able to generate a
human-readable LaTeX view and machine-readable JSON from the same records.

The implementation lives in `scripts/generate_derivative.py` and
`topics/ieee/hla-semantic-derivative-2025/`. It generates concepts and
hierarchy, reviewed normative requirements, state-machine event logic, and
requirement-to-clause/service/callback/code traceability. The same invocation
also emits `semantic-model.json`; candidates are retained there but are not
rendered as reviewed normative material.

Exit gate: a clean build of the derivative document can be reproduced after
deleting all generated output, and changing a semantic record updates every
dependent view without hand-editing generated TeX. The current derivative
build is 296 pages and is covered by semantic mutation tests.

### M7 — Full build and visual release checks

**Status: complete.**

Move from source-level confidence to repeatable document-level release checks.

Deliverables:

- CI runner with a provisioned XeLaTeX/MiKTeX toolchain;
- full 1516/1516.1/1516.2 PDF smoke matrix;
- page-count and log-error checks;
- diagram visual-review status and optional Graphviz rendering;
- clean-output verification proving that ignored artifacts are not tracked.

`data/release/documents.json` is the source-controlled page-count and output
manifest. `scripts/release_check.py` validates each PDF, build log, expected
page count, ignored-output contract, and tracked-generated-output list. The
`document-release` CI job provisions Ubuntu TeX Live and Graphviz, builds all
three faithful documents plus the derivative, and runs the release checks.

Exit gate: a clean CI checkout builds all three faithful documents and the
derivative document, validates semantic coverage, and produces no tracked
outputs. The local release check currently passes at 40, 338, 124, and 296
pages respectively, with no fatal log findings or tracked generated outputs.

### M13 — Document-family generalization

**Status: planned.**

Prove that the shared layer is useful beyond HLA.

Deliverables:

- a documented profile/adapter contract for a second document family;
- a small non-HLA fixture or document recreation using the common builder;
- generic hierarchy, table, requirement, and reference queries with no HLA
  constants in the core model;
- onboarding documentation for new topic/document directories.

Exit gate: the second family can load, validate, generate, and build through
the shared pipeline without adding domain vocabulary to the generic semantic
model.

## Dependency and parallel-work map

```text
M0 -> M1 -> M2 -> M4 -> M5 -> M6 -> M7
              \-> M3 -----/              \
                                      -> M8 -> M9 -> M10 -> M11 -> M12 -> M13
```

M3 can proceed independently while M4 migrates prose and tables. M5 needs
reviewed diagram and content records, but its validation and query tooling can
continue to mature in parallel. M6 waited until at least one complete vertical
slice existed in each document; M8-M12 now complete the corpus coverage before
M13 proves reuse outside HLA.

## Progress dashboard

Run these commands from the repository root; they print reports to stdout and
do not create tracked audit files:

```powershell
python -m scripts.semantic_metrics --json
python -m scripts.semantic_dashboard --json
python -m scripts.release_check --manifest data/release/documents.json --diagram-manifest data/state_machines/manifest.json --json
python -m scripts.state_machine_metrics `
  --manifest data/state_machines/manifest.json `
  --models topics/ieee/hla-1516.1-2025/semantic
python -m unittest discover -s tests -v
```

The dashboard for a migration slice should record only source-controlled
changes: semantic records added, duplicate owners removed, links promoted,
tests added, and build results. Generated PDFs, images, exports, audits, and
review packets remain local and ignored.

## Immediate execution order

1. Execute the post-M7 semantic coverage plan in
   [`DATA-DRIVEN-DELIVERABLES.md`](DATA-DRIVEN-DELIVERABLES.md): M8 inventory,
   M9 1516, M10 1516.1, M11 1516.2, and M12 authority switch.
2. Use each migration slice to reduce page-fragment ownership and increase
   reviewed requirement/state/table coverage without destabilizing the
   faithful PDFs.
3. Prove the HLA-neutral profile/adapter boundary with the M13 non-HLA fixture,
   preserving the HLA derivative as the reference consumer.

Every future task should identify its milestone, document, semantic surface,
acceptance gate, and metric impact before implementation begins.
