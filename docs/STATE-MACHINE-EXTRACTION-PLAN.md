# State-machine extraction and regeneration plan

This is the M3 child plan in [`EXECUTION-PLAN.md`](EXECUTION-PLAN.md). Keep
diagram-specific inventory and visual-acceptance details here; milestone
status, cross-document dependencies, content migration, compliance coverage,
and derivative-document work belong in the execution plan.

## Objective

Convert the backlog of extracted diagram images into reviewed, programmatic
state-machine records that can regenerate TikZ/LaTeX and other renderer outputs.
The canonical record is a typed graph with provenance. Rendered output is a
build artifact, not the source of truth.

## Current baseline

The current extracted backlog for both standards is tracked in
`data/state_machines/manifest.json`. Run:

```powershell
python -m scripts.state_machine_metrics `
  --manifest data/state_machines/manifest.json `
  --models topics/ieee/hla-1516.1-2025/semantic
```

The metrics report is stdout-only and measures:

- total extracted diagrams in the manifest;
- diagrams classified beyond `unmodeled`;
- diagrams with a canonical model;
- status distribution;
- review-priority distribution;
- model-file and canonical-machine counts;
- structural validation errors.

The initial target is honest inventory coverage: every extracted image has a
stable ID, source page, xref, type/status, and review notes, even before it is
semantically modeled. A prose-derived pilot already exists separately from
this image inventory; it is useful for exercising the contract and is now
explicitly mapped to the page 41–42 source figures.

Current snapshot (2026-08-05):

| Measure | 1516.1 | 1516.2 |
| --- | ---: | ---: |
| Extracted-image candidates | 43 | 0 |
| Classified image candidates | 43 | 0 |
| Semantic records (modeled: draft/needs_review/validated) | 25 | 0 |
| Canonical machines | 24 | 0 |
| Review packets | 24 | 0 |
| Generated TikZ artifacts | 24 | 0 |
| Rendered preview PNGs | 24 | 0 |
| Accepted reviews | 24 | 0 |

1516.1 review priorities: `high=0`, `medium=0`, `low=25`, `none=18`.

The 1516.2 scope is `reviewed_no_state_diagrams`: the reconstructed source-page
and vector bundle has no Figure captions, state-chart/state-diagram/state-machine
markers, or diagram assets. Its only bundled raster is a small page-38 icon.

Current canonical-machine count: 24; structural validation errors = 0. The
1516.1 manifest has 18 explicitly `classified` non-model entries, no `draft`
or `needs_review` model-linked entries, and 25 validated source rows; no
extracted-image candidate remains `unmodeled`. All 24 canonical machines have
source-compared accepted previews; the visual review backlog is closed.

## Document coverage and diagram groups

The two standards are intentionally tracked as separate backlog scopes. The
manifest records the lifted 1516.1 images as provenance-only comparison inputs;
the image files themselves are not source artifacts to baseline.

### HLA 1516.1

The source text explicitly describes two independent hierarchical state-chart
sets, and it contains a later connection/reconnection state-diagram group:

| Group | Figures | Current backlog state |
| --- | --- | --- |
| Federation overview | 1 | Present in the 43-image inventory; page 39 is source-compared and accepted with TikZ generation, manual frame separators, and routed create/destroy edges. |
| Federate-perspective hierarchy | 3–5, 14–17 | Present in the 43-image inventory; pages 41–42 are linked to the provenance-backed federate-lifetime model, Figure 5 is accepted as a parameterized Normal Activity Permitted record, and Figures 14–17 have source-compared accepted records. |
| Federation-execution synchronization | 6–9 | Figures 6–9 are source-compared and accepted; Figure 6 uses parameterized overview regions with source-visible nested frames and separators. |
| Declaration-management state charts | 10–13 | Figures 10–13 are source-compared and accepted with explicit entry/repeat/history/nested-control elements and manual label anchors. |
| Object-management state charts | 14–16 | Figures 14–16 are source-compared and accepted with explicit composite/history/choice/relevance/scope/divestiture/acquisition regions. |
| Temporal-management state chart | 17 | Page 187 is source-compared and accepted in `ownership-and-temporal-state-machines.json`; the Time Granted composite, three parallel status/switch machines, and expanded message-transition legend are represented with manual label anchors. |
| Connection/reconnection protocol | 24–33 | Figures 24–25 and 27–33 are source-compared and accepted; Figure 26 is explicitly classified as a non-state message-sequence diagram. |

Figure 2 is a federate-to-RTI relationship view rather than a state machine.
Figures 18–23 are other diagram types and should not be counted as state
machines: the current inventory explicitly classifies Figure 18 as a DDM
conceptual diagram, Figures 19–20 as MOM class hierarchies, Figure 21 as a
protocol-layer architecture diagram, and Figures 22–23 as message-sequence
diagrams.

The 1516.1 manifest contains 18 `classified` non-model entries, no `draft` or
`needs_review` model-linked entries, and 25 validated source rows covering 24
canonical machines. The queue is empty for 1516.1; semantic extraction and
visual acceptance are complete. All 24 canonical machines have compiled,
source-compared, accepted preview PNGs, including the dense ownership/object
layouts and the combined multi-page lifetime view.

### HLA 1516.2

The current 1516.2 source contains no `state chart`, `state diagram`, or
`state machine` captions/markers. Its uses of “state” are OMT attribute, table,
or data-concept language. The source-page/vector audit found no state diagrams
and the only bundled raster is a small page-38 icon, so the manifest records
`reviewed_no_state_diagrams` with zero candidates. If a future source refresh
adds a figure, it gets its own 1516.2 group and provenance entries.

## Data contract

The schema is [`schemas/state_machine.schema.json`](../schemas/state_machine.schema.json).
Each model should contain:

- stable machine, state, and transition IDs;
- state labels and kinds;
- source/target state IDs;
- event, guard, action, precondition, and postcondition text;
- source image/page/xref provenance;
- clause and requirement links where known;
- optional manual layout coordinates for visual-fidelity work;
- optional transition-specific bends and label placement under
  `layout.transitions`.

Semantic fields and layout fields must remain separate. Automatic layout is the
default; manual coordinates are added only when required to match the source.

## Workflow

### Phase 1 — Inventory and classification

- [x] Add a deterministic inventory script.
- [x] Create a text-based manifest for extracted images across 1516.1 and 1516.2.
- [x] Audit 1516.2 source-page and vector figures; record the reviewed
  no-state-diagrams outcome rather than infer zero from a missing extraction
  directory.
- [x] Classify the 1516.1 inventory into the federation overview, federate
  hierarchy, synchronization, and connection/reconnection groups above.
- [x] Classify each 1516.1 image as state machine, another diagram type, or irrelevant.
- [x] Record ambiguous cases and assign deterministic review priority.
- [x] Add a deterministic review queue for the next unmodeled candidates.

### Phase 2 — Schema and tooling

- [x] Define the renderer-independent JSON schema.
- [x] Add structural metrics and validation.
- [x] Track review packets, TikZ artifacts, preview PNGs, and accepted reviews.
- [x] Reconcile inventory rows from canonical model provenance and review status after an inventory refresh.
- [ ] Add JSON Schema validation when the optional validator dependency is available.
- [x] Add Python loading/query helpers to `scripts/semantic_model.py`.

### Phase 3 — Pilot extraction

- [x] Select the first simple state-machine diagram: 1516.1 page 39.
- [x] Annotate states, edges, and labels with source-image and source-text provenance.
- [x] Encode the canonical `federation-execution` JSON record.
- [x] Link the existing federate-lifetime semantic model to the page 41–42 source figures.
- [x] Encode Figure 5's parameterized Normal Activity Permitted composite, including source-visible dashed separators.
- [x] Encode Figures 7–9 in the synchronization-point group.
- [x] Compare Figures 7–9 against their source images and record source-compared acceptance after label/frame refinement.
- [x] Encode Figure 6's parameterized federation-execution synchronization structure as a source-compared accepted overview with nested frames and separators.
- [x] Compare Figure 6 against its source image and record source-compared acceptance.
- [x] Encode Figures 10–13 in the declaration-management group.
- [x] Encode Figures 14–15 in the object-management group as a first semantic pass.
- [x] Encode Figure 16's ownership-transfer chart and Figure 17's temporal state chart as first semantic passes.
- [x] Encode Figure 24's federate connection/reconnection overview as a first semantic pass.
- [x] Compare Figure 24 against its source image and record source-compared acceptance after connector-loop routing refinement; the RTI counterpart is also accepted.
- [x] Encode Figures 25 and 27–33 in the detailed protocol state-machine group; classify Figure 26 as a message-sequence diagram.
- [x] Compare Figures 25, 27–28, and 30–33 against their source images and record source-compared acceptance after connector-context and dense-label refinement.
- [x] Refine Figure 12 cross-region publication transitions and Figure 13 nested control-send details.
- [x] Refine Figure 15 composite cross-region routing and verify every long edge label against the source image.
- [x] Refine Figure 16 acquisition/divestiture routing and verify its dense cross-region labels against the source image.
- [x] Refine Figure 17's expanded message-transition legend routing and typography.
- [x] Transcribe the remaining figure-only details in the federate-lifetime composite and source-compare the combined multi-page layout.
- [x] Validate records and compile generated previews for all 24 canonical machines.
- [x] Compare all 24 generated previews with their source images and accept the records.

### Phase 4 — Renderers

- [x] Implement Graphviz/DOT output for fast structural previews.
- [x] Implement a first TikZ output path for canonical state-machine records.
- [x] Add Mermaid output for lightweight Markdown review.
- [x] Add visual comparison notes and accepted/rejected render status.
- [x] Add a repeatable review packet command and tracked Markdown checklist.
- [x] Add a repeatable batch review driver that preserves existing Findings.

### Phase 5 — Batch migration

- [x] Process and semantically validate the first simple federation/synchronization diagrams.
- [x] Process self-loops, parallel edges, nested/composite states, and long labels.
- [x] Link modeled transitions to owning clauses; reviewed normative requirement
  promotion is tracked under M5 in `EXECUTION-PLAN.md`.
- [x] Record exceptions instead of weakening the common schema.

### Phase 6 — Integration and maintenance

- [x] Generate semantic blocks from the model during the document build.
- [x] Add queries for transitions applicable in a state after an event.
- [x] Add checks for orphaned requirements and unresolved clause links.
- [x] Keep the manifest and metrics as the migration dashboard.

## Status vocabulary

```text
unmodeled   discovered, but no classification or semantic extraction
classified  diagram type identified
draft       canonical record exists, not yet reviewed
needs_review record exists with known uncertainty or validation concerns
validated   structure and semantics reviewed
rendered    at least one renderer output generated successfully
accepted    rendered output reviewed against the source and accepted
```

## Definition of done for one diagram

A diagram is `accepted` when:

1. its manifest entry has a stable ID and source provenance;
2. its canonical model passes structural validation;
3. every visible state and transition is either represented or explicitly
   documented as non-semantic;
4. clause/requirement links are present where the source establishes them;
5. at least TikZ and one preview renderer can regenerate it;
6. the generated result has been visually compared with the extracted source.

## Quality gates

The migration is healthy when:

- no manifest entry is silently lost;
- validation errors are zero for `validated` and later records;
- modeled coverage increases monotonically;
- every model has source provenance;
- semantic changes do not require editing generated TikZ directly;
- the document build remains reproducible.

## Commands

Regenerate the inventory after new extraction work:

```powershell
python -m scripts.inventory_state_machines `
  --source 1516.1=topics/ieee/hla-1516.1-2025/assets/extracted `
  --source 1516.2=topics/ieee/hla-1516.2-2025/assets/extracted `
  --manifest data/state_machines/manifest.json --write
```

Measure progress:

```powershell
python -m scripts.state_machine_metrics `
  --manifest data/state_machines/manifest.json `
  --models topics/ieee/hla-1516.1-2025/semantic `
  --reviews reviews/state_machines `
  --artifacts build/state-machines
```
