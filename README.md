# Document-Recreation
# Document Recreation

A collection of reproducible recreations of historical and technical documents, including SISO PDFs, IEEE papers, and other whitepapers.

## Repository layout

```text
topics/
  <topic>/
    <document>/
      build.py          # repository-standard document entry point
      main.tex          # typical LaTeX entry point
      src/              # Python or LaTeX source files
      assets/           # figures, scans, and other inputs
      output/           # generated artifacts; ignored by Git
scripts/
  build.py              # top-level build orchestrator
  latex_renderer.py     # HLA-neutral semantic-to-LaTeX renderer
  hla_profile.py        # HLA source macros and LaTeX dialect only
```

Each document is intentionally self-contained. A document directory is considered buildable when it contains `build.py`. The top-level builder can build one document, one topic, or every document in the repository.

The current IEEE ingestion lives at:

```text
topics/ieee/hla-1516.1-2025/
topics/ieee/hla-1516.2-2025/
topics/ieee/hla-1516-2025/
```

Those projects expose thin document-level wrappers backed by the shared Python builder.
The HLA-neutral portability fixture lives at
`topics/fixture/non-hla-demo-2025/`; its family-local profile is the onboarding
reference for future document families.

## Source-of-truth policy

The repository should generally baseline the reconstruction source and provenance notes, not rendered or extracted binaries. PDFs, raster image files, archives, and build outputs are ignored by default. Use TikZ/LaTeX and Python to regenerate document visuals and rendered artifacts from committed text-based sources.

Binary files may remain in a local working tree when an upstream build or visual comparison needs them, but they should not be force-added to Git without an explicit reason.

## Analogue and comparison boundary

An existing document, PDF, scan, rendered page, or extracted image may be used as an analogue while recreating a document. It is working reference material—not the recreation baseline. Keep that material outside the committed source tree or under an ignored `.local/`, `reference/`, or `comparison/` directory.

The baseline should contain the independently authored reconstruction: LaTeX/TikZ source, Python generators and validators, text-based metadata, tests, and provenance notes. Comparison artifacts may inform implementation and verification, but they should not become the implementation itself.

## Long-term document strategy

The HLA documents are the starting corpus, not the final form of the project.
The work proceeds in three deliberate stages:

1. Recreate each original document faithfully enough to preserve its structure,
   wording, layout, and visual behavior.
2. Extract that reconstruction into validated semantic records for clauses,
   requirements, definitions, references, tables, functional preconditions and
   postconditions, and state-machine behavior.
3. Use the semantic records to author a new, more programmatic document that
   makes relationships, meanings, normative logic, and executable conformance
   surfaces explicit rather than reproducing the original presentation alone.

The recreated originals provide the fidelity reference and provenance trail.
The semantic model becomes the reusable source for both conformance tooling and
the next-generation document; the new document is therefore an intentional
derivative, not a replacement baseline for the original recreation.

## Build commands

From the repository root:

The utilities under `scripts/` are a Python package. Prefer module invocation
(`python -m scripts.<module>`) so imports work consistently from the repository
root; `python -m scripts --help` lists the available command modules.

```powershell
python -m pip install -e .
python -m scripts.build list
python -m scripts.build build all
python -m scripts.build build topics/siso/example-document
python -m scripts.build build topics/fixture/non-hla-demo-2025
python -m scripts.build clean

# Independent HLA publication destinations.
python -m scripts.build publication list
python -m scripts.build publication build hla-unofficial-faithful-reconstruction-2025
python -m scripts.build publication build hla-hierarchy-reconstruction-2025
python -m scripts.build publication build hla-rti-compliance-requirements-2025
```

The HLA products are explicitly separated in
[`data/publications.json`](data/publications.json): the unofficial faithful
reconstructions, the hierarchy-first reconstruction, and the RTI compliance
requirements publication. Each names only its own build roots, so it can be
added, built, release-checked, or removed without coupling it to another
publication's generated outputs. See
[`docs/PUBLICATION-PRODUCTS.md`](docs/PUBLICATION-PRODUCTS.md) for the product
boundaries and commands.

Semantic records can be queried directly from source-first LaTeX:

```powershell
python -m scripts.semantic_model topics/ieee/hla-1516-2025
python -m scripts.semantic_model topics/ieee/hla-1516.2-2025
python -m scripts.semantic_model topics/ieee/hla-1516.2-2025 --json
```

The semantic model extracts typed clauses, definitions, requirements, content
blocks, references, notes, figures, examples, annexes, state machines, and HLA
1516.2 table/cell records. Pydantic provides the strict loading, validation, JSON serialization,
and round-trip deserialization contract. Explicit normative rules are marked
`explicit`; all current IEEE 1516.1 and 1516.2 normative records are now
authoritative and clause-owned. IEEE 1516.1 has 1,697 source-derived
requirements; IEEE 1516.2 has 340 cross-cutting requirements and 83 reusable
table-backed definitions. The 1516.2 table model
keeps semantic cell text and source references separate from page geometry,
classifies OMT table kinds, and exposes continued-table merging. Selected
tables can be re-injected through the portable renderer in
`scripts/latex_renderer.py`. HLA-specific command names and source macros are
isolated in `scripts/hla_profile.py`; the existing `scripts/semantic_latex.py`
module remains a compatibility facade for HLA output.

The loader accepts any structural `LatexSourceProfile`, so a future document
family can supply its own command vocabulary without adding HLA constants to
the semantic model. `DocumentModel.ordered_clauses()` and
`DocumentModel.root_clauses()` provide canonical navigation. Compliance
consumers can use `query_requirements_applicable_after()` for typed
state/event traceability, `compliance_query()` for a serializable report,
`transitions_without_implementation_mapping()` for missing seams, and
`transitions_without_concrete_implementation()` for mappings that remain
planned or partial.

The shared generator compiles each validated model through
`scripts/hierarchy_compiler.py`. Every build emits ignored `hierarchy.json` and
`hierarchy-index.tex` inputs containing canonical clause parent/child order,
direct record ownership, stable semantic destinations, and explicit record
links. Page adapters receive qualified anchors from that same graph, and the
derivative renders its clause tree from the compiled hierarchy. State and
transition destinations are namespace-qualified when their source IDs overlap.

The compliance layer adds authored implementation mappings for RTI services,
callbacks, and adapters. They live in each document's
`semantic/implementations.json` and are validated against clause, requirement,
and transition IDs. Each mapping exposes a structured
`ImplementationReference` while retaining the stable legacy symbol field.
IEEE 1516.1 now has one planned seam for each of its 281 modeled transitions;
the `planned` status deliberately does not claim concrete implementation code.
The same
queries are available from the stdout-only CLI:

```powershell
python -m scripts.compliance topics/ieee/hla-1516.1-2025 `
  --machine federate-lifetime `
  --state federate.not-connected `
  --event Connect `
  --include-candidates
python -m scripts.compliance topics/ieee/hla-1516.1-2025 `
  --machine federate-lifetime --json
python -m scripts.compliance `
  topics/ieee/hla-1516-2025 `
  topics/ieee/hla-1516.1-2025 `
  topics/ieee/hla-1516.2-2025 `
  --document hla-1516.1-2025 `
  --implementation-status planned `
  --interface-kind service `
  --json
```

Authoritative requirement records and their transition relationships live in
`semantic/requirements.json` and `semantic/requirement-links.json`. Requirement
links and implementation links are bidirectional and validated at load time.
A corpus-level report can include all three documents:

```powershell
python -m scripts.compliance `
  topics/ieee/hla-1516-2025 `
  topics/ieee/hla-1516.1-2025 `
  topics/ieee/hla-1516.2-2025 `
  --json
```

After reviewing a candidate, promote it with the source-only workflow. The
default transition coverage requires a reciprocal transition link; use
`--coverage-kind` and `--coverage-note` for a reviewed requirement that is
cross-cutting or document-wide:

```powershell
python -m scripts.promote_requirement `
  topics/ieee/hla-1516.1-2025 `
  <candidate-id> `
  --transition <transition-id> `
  --dry-run
```

The deterministic coverage dashboard is stdout-only and keeps candidates,
reviewed records, mappings, and remaining gaps separate:

```powershell
python -m scripts.semantic_dashboard --json
```

`ReferenceTarget` records provide the cross-document target contract, and
`load_corpus()` resolves those targets against the loaded document set. The
report remains stdout-only; no audit or verification output is part of the
tracked source tree.

Run the repeatable Milestone 4 contract checks with:

```powershell
python -m unittest discover -s tests -v
```

Invalid state targets, local unresolved semantic references, duplicate IDs, and
missing clause ownership fail model validation. Cross-document targets that
cannot be resolved are returned as typed error issues by the corpus report.
Coverage gaps such as orphan requirements and unmapped transitions remain
queryable as typed findings while their backlog is visible.

The M24 compliance-facing corpus adds `ComplianceCorpus.compliance_report()`
and related typed queries for state/sequence implications, table/definition
dependencies, missing implementation mappings, and planned-versus-concrete
implementation evidence. Use `--corpus-report --json` with
`scripts.compliance` to expose that projection without writing a report file.

The compliance publication builder also emits ignored, normalized CSV
projections under
`topics/ieee/hla-rti-compliance-2025/output/compliance/csv/`: requirements,
transitions, implementation mappings, and one-to-many requirement/transition
mapping link tables. The JSON manifest remains canonical; use the standalone
export option when working from an existing semantic model:

```powershell
python -m scripts.compliance_publication `
  topics/ieee/hla-semantic-derivative-2025/output/semantic/semantic-model.json `
  topics/ieee/hla-rti-compliance-2025/semantic/publication.json `
  --csv-output topics/ieee/hla-rti-compliance-2025/output/compliance/csv
```

Milestone 3 now has an authoritative hierarchy generator in
`scripts/generate_semantic_blocks.py`. It writes ignored LaTeX output from
semantic IDs, including anchors/bookmarks and cross-document links. The first
1516 definition migrations are `def-accuracy` and
`def-available-directed-interactions`: their authored records live in
`topics/ieee/hla-1516-2025/semantic/definitions.json`, and their page fragments
no longer own duplicate hand-written definitions. The latter migration also
keeps its source page's zero-gap layout as a local adapter detail.

The 1516.1 tranche now includes a text-based federate-lifetime state-machine
source under `topics/ieee/hla-1516.1-2025/semantic/`. Its JSON is semantic
source, not a generated audit or a binary analogue.

M4 content slices are now complete: 1516 generates selected Clause 3 summary
requirements, 1516.1 generates the Connect/Disconnect/Connection Lost/Federate
Resigned service-family prose and mappings, and 1516.2 generates the typed
Object model identification table family. The three source builds remain at
40, 440, and 124 pages.

The hierarchy-first reconstruction is implemented at
`topics/ieee/hla-semantic-derivative-2025/`. Its generated document has four
views—concepts and hierarchy, reviewed normative requirements, state-machine
logic, and traceability to clauses/services/callbacks/code—and its ignored
`semantic-model.json` is generated from the same Pydantic records as the TeX.
Build it with:

```powershell
python topics/ieee/hla-semantic-derivative-2025/build.py build
```

The independent RTI compliance requirements publication is at
`topics/ieee/hla-rti-compliance-2025/`. It produces a readable requirements
catalogue, transition matrix, implementation-evidence registry, gap queue, and
machine-readable Pydantic manifest from the same cross-document corpus. It
deliberately distinguishes planned mapping seams from concrete and verified
RTI implementation evidence. Build it with:

```powershell
python topics/ieee/hla-rti-compliance-2025/build.py build
```

The full release smoke check covers the three faithful PDFs, both derivatives,
and the one-page non-HLA portability fixture:

```powershell
python -m scripts.release_check `
  --manifest data/release/documents.json `
  --diagram-manifest data/state_machines/manifest.json `
  --authority-manifest data/semantic/authority.json `
  --json
```

The execution milestones, exit gates, dependencies, and immediate work order
are in [docs/EXECUTION-PLAN.md](docs/EXECUTION-PLAN.md). The extracted-diagram
migration plan, inventory manifest, schema, and progress metrics are in
[docs/STATE-MACHINE-EXTRACTION-PLAN.md](docs/STATE-MACHINE-EXTRACTION-PLAN.md).

The HLA semantic reconstruction backlog and its measurable source-shape targets
are in [docs/HLA-SEMANTIC-ROADMAP.md](docs/HLA-SEMANTIC-ROADMAP.md). The
concrete data-driven source-of-truth contract, current baseline, and M8-M19
deliverables are in
[docs/DATA-DRIVEN-DELIVERABLES.md](docs/DATA-DRIVEN-DELIVERABLES.md). Capture a
fresh, stdout-only baseline with:

```powershell
python -m scripts.semantic_metrics
```

Coordinate-heavy source can be inspected separately from semantic records:

```powershell
python -m scripts.layout_model topics/ieee/hla-1516.1-2025
```

On Windows with MiKTeX, enable one-time automatic installation of missing LaTeX packages with:

```powershell
initexmf --enable-installer
```

The document `latexmkrc` files opt into this setting for Windows builds. MiKTeX also exposes the same
setting in MiKTeX Console under the package installation preferences.

Document build scripts should write generated files to their local `output/` directory and keep source inputs in the document directory (or its `src/` and `assets/` subdirectories).

Every document build regenerates `output/semantic/semantic-index.tex` and
`output/semantic/semantic-manifest.tex` from the typed model before running
LaTeX. The generated directory is ignored. Selected definitions and
requirements also produce typed TeX data macros; migrated prose content blocks
and the 1516 typed content-element records use the same contract so layout
adapters consume semantic data while keeping page geometry in
document-specific source. The 1516 definition pilot and the 1516.1
federate-lifetime slice additionally consume generated visible semantic
blocks.

The faithful HLA recreations also consume one generated
`output/semantic/faithful-body.tex` entrypoint. Semantic content-block records
provide the active page order; each document's
`semantic/faithful-layout.json` declares only layout-only wrappers, navigation
insertions, and exceptional pages. Validate this boundary after a build with:

```powershell
python -m scripts.semantic_authority --check-generated --json
```
State-machine diagrams can be exported as source-only DOT and Mermaid files:

```powershell
python -m scripts.export_state_machine `
  topics/ieee/hla-1516.1-2025/semantic/federate-lifetime.json `
  --output .tmp/state-machines --format both
```

Generic relationship, hierarchy, conceptual, and protocol-layer diagrams use
the same source-only contract and can be exported as TikZ or Mermaid:

```powershell
python -m scripts.export_graph_diagram `
  topics/ieee/hla-1516.1-2025/semantic/graph-diagrams.json `
  --output .tmp/graph-diagrams --format both
```

The faithful 1516.1 figure-surface gate and RTI-oriented coverage report are:

```powershell
python scripts.diagram_surface_qa.py `
  --surface-manifest data/semantic/diagram-surfaces.json `
  --models topics/ieee/hla-1516.1-2025/semantic `
  --generated topics/ieee/hla-1516.1-2025/output/semantic `
  --expected-figures 33 --json
python scripts.rti_diagram_check.py topics/ieee/hla-1516.1-2025 --json
```

Visual review packets are likewise ignored and retain their generated TikZ,
DOT, and Mermaid sources. Add `--graphviz` to render an SVG when Graphviz's
`dot` executable is installed:

```powershell
python -m scripts.review_state_machines `
  --manifest data/state_machines/manifest.json `
  --models topics/ieee/hla-1516.1-2025/semantic `
  --reviews reviews --artifacts review-artifacts --graphviz
```

## Adding a document

1. Create `topics/<topic>/<document>/`.
2. Add a document-local `build.py`.
3. Keep the build reproducible and avoid committing generated output.
4. Add notes about provenance, source material, and known differences to the document's README.
