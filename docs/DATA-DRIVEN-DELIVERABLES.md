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

Baseline captured on 2026-08-05:

| Surface | 1516 | 1516.1 | 1516.2 | End-state target |
| --- | ---: | ---: | ---: | --- |
| Extracted requirement records | 20 | 1,697 | 340 | Every candidate classified; every confirmed normative record reviewed |
| Reviewed requirements | 2 | 7 | 0 | All confirmed normative records have explicit coverage |
| State machines | 0 | 24 | 0 | All source-defined machines represented or explicitly marked absent |
| State transitions | 0 | 281 | 0 | All modeled transitions have complete semantic fields |
| Transition implementation mappings | 0 | 5 | 0 | Every compliance-scope transition classified and mapped or marked N/A/deferred |
| Migrated table families | 0 | 0 | 1 | All semantic table families represented with continued-fragment links |
| Page-fragment ratio | 0.8444 | 0.9887 | 0.9533 | Below 0.10 for semantic-owned source; layout adapters may remain |

The baseline is a prioritization tool, not a committed audit artifact. Run
the stdout-only metrics and dashboards locally:

```powershell
python -m scripts.semantic_metrics --json
python -m scripts.semantic_dashboard --json
python -m scripts.release_check --manifest data/release/documents.json --diagram-manifest data/state_machines/manifest.json --json
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

Deliver a complete machine-readable inventory of the three documents' semantic
surfaces: clauses, definitions, normative candidates, references, tables,
figures, examples, state machines, and layout-only artifacts.

Acceptance gates:

- every candidate has a classification and source provenance;
- every semantic surface has an owner and migration destination;
- the priority queue is ranked by reuse value and source-shape reduction;
- baseline metrics and release page counts remain reproducible.

### M9 — Make 1516 semantically complete

Migrate the framework-and-rules document's hierarchy, definitions, summary
rules, references, and confirmed normative content into canonical records.

Deliverables:

- complete clause/definition/reference ownership;
- reviewed classification of all 1516 requirement candidates;
- generated faithful semantic blocks for migrated content;
- derivative concepts and requirements view populated from those records;
- no duplicate semantic owner between page fragments and semantic source.

### M10 — Make 1516.1 operationally complete

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

### M11 — Make 1516.2 structurally semantic

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

### M12 — Authority switch and conformance release

Make the semantic corpus the normal authoring path for all confirmed semantic
content in the HLA tranche.

Acceptance gates:

- semantic records are the only normative owner for migrated content;
- faithful PDFs and the derivative are generated from the same records;
- a semantic mutation test proves the affected faithful and derivative views
  change together;
- all confirmed references resolve and all candidate gaps are classified;
- compliance queries and JSON exports are documented as stable consumers;
- CI verifies generation, builds, page counts, logs, diagrams, and Git hygiene.

### M13 — Prove HLA-neutral reuse

Load and build a small non-HLA document fixture through the shared model,
builder, hierarchy, table, requirement, and reference interfaces.

Acceptance gate: the second family requires a profile/adapter, but no HLA
constants or HLA LaTeX commands in the generic semantic model or renderers.

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
