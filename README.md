# HLA Requirements Lab

Source-controlled extraction, validation, traceability, and publication of
requirements from the IEEE HLA standards. LaTeX builds, and diagrams remain
provenance adapters for the requirements corpus.

The project scope and definition of done are explicit in
[`docs/SCOPE.md`](docs/SCOPE.md); the dependency direction and product
boundaries are in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Repository layout

```text
hla_lab/                 # stable public CLI and domain orchestration
topics/ieee/             # 2010/2025 HLA source corpus and adapters
data/                    # authority, inventory, release, and lineage manifests
hla_lab/schemas.py       # Pydantic contract registry and on-demand JSON Schema export
tools/                   # installed CI tooling and one-time corpus migrations
tests/                   # capability-oriented contract tests
docs/                    # active architecture and product contracts
```

The public workflow is exposed through `hla-lab`. Document-local build scripts
remain publication adapters, and new reusable behavior lives under `hla_lab`.
One-time corpus migrations live in `tools/migrations/` and are not active
workflow entrypoints.

The supported corpus currently includes:

```text
topics/ieee/hla-1516-2010/
topics/ieee/hla-1516.1-2010/
topics/ieee/hla-1516.2-2010/
topics/ieee/hla-1516-2025/
topics/ieee/hla-1516.1-2025/
topics/ieee/hla-1516.2-2025/
```

## Source-of-truth policy

The repository should generally baseline the reconstruction source and provenance notes, not rendered or extracted
binaries. PDFs, raster image files, archives, and build outputs are ignored by default. Use TikZ/LaTeX and Python to
regenerate document visuals and rendered artifacts from committed text-based sources.

Binary files may remain in a local working tree when an upstream build or visual comparison needs them, but they should
not be force-added to Git without an explicit reason.

## Analogue and comparison boundary

An existing document, PDF, scan, rendered page, or extracted image may be used as an analogue while recreating a
document. It is working reference material—not the recreation baseline. Keep that material outside the committed source
tree or under an ignored `.local/`, `reference/`, or `comparison/` directory.

The baseline should contain the independently authored reconstruction: LaTeX/TikZ source, Python generators and
validators, text-based metadata, tests, and provenance notes. Comparison artifacts may inform implementation and
verification, but they should not become the implementation itself.

## Product definition

The lab has one primary product: a validated, queryable HLA requirements
corpus. Its core outputs are source-owned semantic records, coverage and
traceability reports, portable contracts, and evidence-ready projections.

Faithful documents and diagrams remain useful when they protect provenance or
make a semantic relationship reviewable, but page fidelity is no longer the
project's definition of success. Planned implementation mappings are kept
distinct from concrete or verified evidence.

See [SCOPE.md](docs/SCOPE.md) for the product boundary and
[ARCHITECTURE.md](docs/ARCHITECTURE.md) for the dependency direction.

## Build commands

From the repository root:

Install the project and use the installed `hla-lab` entry point for normal
workflows:

```console
python -m pip install -e .
hla-lab --root . status --require-api-contract
hla-lab --root . build
hla-lab --root . publish
hla-lab-schema --list
```

Corpus commands require an explicit workspace. Set `HLA_LAB_ROOT`, or pass
`--root <workspace>` before the subcommand (for example,
`hla-lab --root . status`). The package does not infer a corpus root from its
installation location or the current directory.
Contract models are importable from `hla_lab.schemas`; `hla-lab schema <name>`
or the standalone `hla-lab-schema <name>` command generates JSON Schema on
demand for external consumers. The specialized model and inventory commands
accept `--workspace-root` in addition to a document root, for example
`hla-lab-model topics/ieee/hla-1516.1-2025 --workspace-root .`.

For contributor tooling, `uv sync --dev` is an optional reproducible setup;
prefix the same commands with `uv run` when using that environment.

Command examples use `console` fences and one-line invocations when the same
command works in PowerShell and POSIX shells. Truly shell-specific setup, such
as enabling MiKTeX package installation on Windows, remains explicitly labeled
with its required shell.

The stable command has defaults for the common workflows:

```console
hla-lab                  # show the workflow menu
hla-lab --root . docs             # list supported document roots
hla-lab --root . status           # check all documents
hla-lab --root . build            # build all document products
hla-lab --root . build topics/fixture/non-hla-demo-2025
hla-lab --root . publish          # list declared publications
hla-lab --root . publish hla-hierarchy-reconstruction-2025
hla-lab --root . clean            # clean all document products
hla-lab --root . test --parallel
hla-lab --root . quality          # run the ordered quality workflow
hla-lab --root . quality --fix
```

Specialized operations that need detailed selectors remain available through
their owning `hla_lab` module, but are not required for the normal workflow.

```console
python -m hla_lab.build.build list
python -m hla_lab.build.build build all
python -m hla_lab.build.build build topics/siso/example-document
python -m hla_lab.build.build build topics/fixture/non-hla-demo-2025
python -m hla_lab.build.build clean

# Independent HLA publication destinations.
python -m hla_lab.build.build publication list
python -m hla_lab.build.build publication build hla-unofficial-faithful-reconstruction-2010
python -m hla_lab.build.build publication build hla-unofficial-faithful-reconstruction-2025
python -m hla_lab.build.build publication build hla-hierarchy-reconstruction-2025
python -m hla_lab.build.build publication build hla-rti-compliance-requirements-2025
```

For the complete development quality workflow, use the dev dependency group:

```console
uv sync --dev
uv run rumdl fmt .
uv run rumdl check .
uv run mdrepo check .
uv run pre-commit run --all-files
uv run pytest tests
```

Alphus is pinned to an immutable Git revision in the development dependencies.
Its initial Python review profile is local and advisory: it reports source
style, path discovery, runtime type-flow, file-size, line-length, and
cyclomatic-complexity findings without changing the existing CI gates. Preview
the selected checks, then save a JSON report under the ignored `out/quality/`
directory:

Create an isolated Python 3.11 environment for the pinned Alphus, Ruff,
and Pyright tooling. On Windows, run:

```console
uv venv --python 3.11 out/alphus-env
uv pip install --python out/alphus-env/Scripts/python.exe -r tools/requirements-alphus.txt
out/alphus-env/Scripts/python.exe -c "from pathlib import Path; Path('out/quality').mkdir(parents=True, exist_ok=True)"
out/alphus-env/Scripts/alphus.exe --root . --config tools/quality-gates.toml --plan --profile python-review
out/alphus-env/Scripts/alphus.exe --root . --config tools/quality-gates.toml --run --json --history-dir out/quality/history --profile python-review > out/quality/alphus-python-review.json
```

On macOS or Linux, invoke the matching tools under `out/alphus-env/bin/`.

Review findings before promoting any rule to a blocking check. The exact
revision and its optional complexity analyzer are also recorded in
[`tools/requirements-alphus.txt`](tools/requirements-alphus.txt) for pip-based
development environments.

`hla-lab --root . test --parallel` uses `pytest-xdist` workers for the capability suite;
the default remains serial for easier debugging. Tests write temporary
fixtures to isolated directories, so the parallel path is suitable for CI.

The repository also includes `.editorconfig` and `.gitattributes` to keep editor
output and Git’s stored text representation on UTF-8/LF with final newlines.
Invoke `rumdl` through its CLI (`uv run rumdl` locally or `rumdl` in CI), not
with `python -m rumdl`.

The HLA products are explicitly separated in
[`data/publications.json`](data/publications.json): the unofficial faithful
2010 and 2025 reconstructions, the hierarchy-first reconstruction, and the RTI
compliance requirements publication. Each names only its own build roots, so it
can be added, built, release-checked, or removed without coupling it to another
publication's generated outputs. See
[`docs/PUBLICATION-PRODUCTS.md`](docs/PUBLICATION-PRODUCTS.md) for the product
boundaries and commands.

Semantic records can be queried directly from source-first LaTeX:

```console
python -m hla_lab.core.semantic_model topics/ieee/hla-1516-2025
python -m hla_lab.core.semantic_model topics/ieee/hla-1516.2-2025
python -m hla_lab.core.semantic_model topics/ieee/hla-1516.2-2025 --json
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
`hla_lab/adapters/latex_renderer.py`. HLA-specific command names and source macros are
isolated in `hla_lab/core/hla_profile.py`; the existing `hla_lab/generation/semantic_latex.py`
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
`hla_lab/generation/hierarchy_compiler.py`. Every build emits ignored `hierarchy.json` and
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

```console
python -m hla_lab.traceability.compliance topics/ieee/hla-1516.1-2025 --machine federate-lifetime --state federate.not-connected --event Connect --include-candidates
python -m hla_lab.traceability.compliance topics/ieee/hla-1516.1-2025 --machine federate-lifetime --json
python -m hla_lab.traceability.compliance topics/ieee/hla-1516-2025 topics/ieee/hla-1516.1-2025 topics/ieee/hla-1516.2-2025 --document hla-1516.1-2025 --implementation-status planned --interface-kind service --json
```

Before RTI code development, run the specification-surface readiness gate:

```console
python -m hla_lab.traceability.spec_readiness --root .
python -m hla_lab.traceability.spec_readiness --root . --json
```

The gate distinguishes a structurally complete semantic specification from a
language-complete API contract and from concrete implementation evidence. The
current corpus is specification-ready: each requirement and transition has a
planned verification slot, each 1516.1 state-machine transition has a typed
API surface, and each state machine has a replayable trace seed. Exact source
declarations are now ingested into the 2010 and 2025 `1516.1` semantic trees:
2010 C++/Java/WSDL and 2025 C++/Java/FedPro protobuf. The remaining gap is the
implementation crosswalk from those exact bindings to every semantic mapping;
requirement-to-declaration bindings now cover every 2010 and 2025 `1516.1`
requirement. Python and transport/service projections and concrete test
evidence remain separate implementation work. See
[`docs/COMPLIANCE-SURFACE-CONTRACT.md`](docs/COMPLIANCE-SURFACE-CONTRACT.md).

Regenerate the text-only API manifests from the local comparison archives with:

```console
python -m hla_lab.corpus.ingest_hla_api --edition 2010 --root . --output topics/ieee/hla-1516.1-2010/semantic/api-surfaces.json
python -m hla_lab.corpus.ingest_hla_api --edition 2025 --root . --output topics/ieee/hla-1516.1-2025/semantic/api-surfaces.json
```

The inbox archives remain comparison inputs; only the generated, provenance-
annotated JSON is part of the semantic source tree.

Crosswalk statuses can be queried without producing an audit file:

```console
python -m hla_lab.traceability.compliance topics/ieee/hla-1516.1-2025 --api-target fedpro --api-gaps --json
```

Audit the complete requirement-to-Java/C++ declaration path for both editions:

```console
python -m hla_lab.traceability.api_traceability --workspace-root . --check --require-complete --json
```

For use from an independent RTI repository, export a portable corpus bundle
and verify an implementation-owned manifest through the external sidecar
contract described in
[`docs/EXTERNAL-COMPLIANCE-KIT.md`](docs/EXTERNAL-COMPLIANCE-KIT.md).
An RTI can also provide a language-neutral adapter executable: the sidecar
sends it a JSON request describing expected API seams and receives bindings and
evidence back over JSON stdin/stdout, so the RTI need not import this project.
For the standard Catch2 or JUnit 5 path, the supplied JUnit-results adapter
reads the RTI's existing XML results and an RTI-owned test catalog; no custom
adapter is required to create the initial raw compliance bundle.
Use the RTI-owned test catalog to connect Catch2/CTest or JUnit 5/Maven/Gradle
behavior tests to stable evidence IDs, implementation mappings, and exact API
surfaces. The complete onboarding flow is documented in
[`docs/RTI-TEST-INTEGRATION.md`](docs/RTI-TEST-INTEGRATION.md), with a portable
catalog schema generated with `hla-lab-schema compliance_test_catalog` (from
the Pydantic model in [`hla_lab/schemas.py`](hla_lab/schemas.py))
and an example in
[`examples/compliance-test-catalog.json`](examples/compliance-test-catalog.json).
The verifier's JSON `coverage` object provides requirement, transition, API,
and binding testing totals, percentages, uncovered IDs, and a
`fully_verified` result.
Declared tests and raw adapter results never promote themselves: verified
evidence requires a separate accepted review mark and a real execution mode;
mocked or simulated tests remain visible but cannot satisfy full verification.

Authoritative requirement records and their transition relationships live in
`semantic/requirements.json` and `semantic/requirement-links.json`. Requirement
links and implementation links are bidirectional and validated at load time.
A corpus-level report can include all three documents:

```console
python -m hla_lab.traceability.compliance topics/ieee/hla-1516-2025 topics/ieee/hla-1516.1-2025 topics/ieee/hla-1516.2-2025 --json
```

After reviewing a candidate, promote it with the source-only workflow. The
default transition coverage requires a reciprocal transition link; use
`--coverage-kind` and `--coverage-note` for a reviewed requirement that is
cross-cutting or document-wide:

```console
python -m hla_lab.traceability.promote_requirement topics/ieee/hla-1516.1-2025 <candidate-id> --transition <transition-id> --dry-run
```

The deterministic coverage dashboard is stdout-only and keeps candidates,
reviewed records, mappings, and remaining gaps separate:

```console
python -m hla_lab.reports.semantic_dashboard --json
```

`ReferenceTarget` records provide the cross-document target contract, and
`load_corpus()` resolves those targets against the loaded document set. The
report remains stdout-only; no audit or verification output is part of the
tracked source tree.

Run the complete contract suite with pytest:

```console
pytest tests
```

The discovered suites are organized directly by durable capability in
`tests/test_*.py`. They are not tied to historical delivery phases or command
endpoints.

Invalid state targets, local unresolved semantic references, duplicate IDs, and
missing clause ownership fail model validation. Cross-document targets that
cannot be resolved are returned as typed error issues by the corpus report.
Coverage gaps such as orphan requirements and unmapped transitions remain
queryable as typed findings while their backlog is visible.

The compliance-facing corpus exposes `ComplianceCorpus.compliance_report()`
and related typed queries for state/sequence implications, table/definition
dependencies, missing implementation mappings, and planned-versus-concrete
implementation evidence. Use `--corpus-report --json` with
`hla_lab.traceability.compliance` to expose that projection without writing a report file.

The compliance publication builder also emits ignored, normalized CSV
projections under
`topics/ieee/hla-rti-compliance-2025/output/compliance/csv/`: requirements,
transitions, implementation mappings, and one-to-many requirement/transition
mapping link tables. The JSON manifest remains canonical; use the standalone
export option when working from an existing semantic model:

```console
python -m hla_lab.publication.compliance_publication topics/ieee/hla-semantic-derivative-2025/output/semantic/semantic-model.json topics/ieee/hla-rti-compliance-2025/semantic/publication.json --csv-output topics/ieee/hla-rti-compliance-2025/output/compliance/csv
```

Cross-edition requirements traceability is source-controlled separately in
`data/semantic/edition-lineage.json`. It supports reviewed `unchanged`,
`revised`, `split`, `merged`, `added`, and `removed` relations between
document-qualified semantic IDs, so the 2010 semantic corpus can later be
compared with the 2025 corpus without matching on wording or clause number. See
[`docs/EDITION-LINEAGE.md`](docs/EDITION-LINEAGE.md).

The hierarchy generator is authoritative in
`hla_lab/generation/generate_semantic_blocks.py`. It writes ignored LaTeX output from
semantic IDs, including anchors/bookmarks and cross-document links. The first
1516 definition migrations are `def-accuracy` and
`def-available-directed-interactions`: their authored records live in
`topics/ieee/hla-1516-2025/semantic/definitions.json`, and their page fragments
no longer own duplicate hand-written definitions. The latter migration also
keeps its source page's zero-gap layout as a local adapter detail.

The 1516.1 tranche now includes a text-based federate-lifetime state-machine
source under `topics/ieee/hla-1516.1-2025/semantic/`. Its JSON is semantic
source, not a generated audit or a binary analogue.

The current content slices are complete: 1516 generates selected Clause 3 summary
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

```console
python topics/ieee/hla-semantic-derivative-2025/build.py build
```

The independent RTI compliance requirements publication is at
`topics/ieee/hla-rti-compliance-2025/`. It produces a readable requirements
catalogue, transition matrix, implementation-evidence registry, gap queue, and
machine-readable Pydantic manifest from the same cross-document corpus. It
deliberately distinguishes planned mapping seams from concrete and verified
RTI implementation evidence. Build it with:

```console
python topics/ieee/hla-rti-compliance-2025/build.py build
```

The full release smoke check covers the six currently ingested faithful PDFs,
both derivatives, and the one-page non-HLA portability fixture:

```console
python -m hla_lab.publication.release_check --manifest data/release/documents.json --diagram-manifest data/state_machines/manifest.json --authority-manifest data/semantic/authority.json --json
```

Capture a fresh, stdout-only semantic baseline with:

```console
python -m hla_lab.reports.semantic_metrics
```

Coordinate-heavy source can be inspected separately from semantic records:

```console
python -m hla_lab.adapters.layout_model topics/ieee/hla-1516.1-2025
```

On Windows with MiKTeX, enable one-time automatic installation of missing LaTeX packages with:

```powershell
initexmf --enable-installer
```

The document `latexmkrc` files opt into this setting for Windows builds. MiKTeX also exposes the same
setting in MiKTeX Console under the package installation preferences.

Document build scripts should write generated files to their local `output/` directory and keep source inputs in the
document directory (or its `src/` and `assets/` subdirectories).

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

```console
python -m hla_lab.traceability.semantic_authority --check-generated --json
```

State-machine diagrams can be exported as source-only DOT and Mermaid files:

```console
python -m hla_lab.diagrams.export_state_machine topics/ieee/hla-1516.1-2025/semantic/federate-lifetime.json --output .tmp/state-machines --format both
```

Generic relationship, hierarchy, conceptual, and protocol-layer diagrams use
the same source-only contract and can be exported as TikZ or Mermaid:

```console
python -m hla_lab.diagrams.export_graph_diagram topics/ieee/hla-1516.1-2025/semantic/graph-diagrams.json --output .tmp/graph-diagrams --format both
```

The faithful 1516.1 figure-surface gate and RTI-oriented coverage report are:

```console
python -m hla_lab.diagrams.diagram_surface_qa --surface-manifest data/semantic/diagram-surfaces.json --models topics/ieee/hla-1516.1-2025/semantic --generated topics/ieee/hla-1516.1-2025/output/semantic --expected-figures 33 --json
python -m hla_lab.diagrams.rti_diagram_check topics/ieee/hla-1516.1-2025 --json
```

Visual review packets are likewise ignored and retain their generated TikZ,
DOT, and Mermaid sources. Add `--graphviz` to render an SVG when Graphviz's
`dot` executable is installed:

```console
python -m hla_lab.diagrams.review_state_machines --manifest data/state_machines/manifest.json --models topics/ieee/hla-1516.1-2025/semantic --reviews reviews --artifacts review-artifacts --graphviz
```

The pinned PlantUML release renderer is documented in
[`tools/plantuml/README.md`](tools/plantuml/README.md).

## Adding a document

1. Create `topics/<topic>/<document>/`.
2. Add a document-local `build.py`.
3. Keep the build reproducible and avoid committing generated output.
4. Add notes about provenance, source material, and known differences to the document's README.
