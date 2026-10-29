# HLA Requirements Lab architecture

## Stable repository shape

```text
hla_lab/
  core/              semantic model, profiles, and source adapters
  corpus/            edition ingestion, inventory, graph, and crosswalks
  traceability/      authority, coverage, readiness, and state traces
  generation/        semantic generation and publication projections
  adapters/           LaTeX and document-layout adapters
  publication/       release, registry, and external compliance products
  diagrams/          state-machine and diagram products
  reports/            semantic metrics and dashboards
  build/              repository build/discovery orchestration
tools/migrations/    one-time corpus migrations retained for reproducibility
topics/ieee/         source corpus, semantic records, and document adapters
data/                authority, inventory, release, and cross-edition manifests
hla_lab/schemas.py    Pydantic contracts and generated JSON Schema export
tests/               capability-oriented contract tests
docs/                scope, method, and product contracts
examples/            external-consumer examples
```

The `hla_lab` package is the public boundary and owns reusable domain behavior.
The installable `tools` package retains CI and one-time migration entry points.
`HLA_LAB_ROOT` or the global `hla-lab --root` option selects the corpus
workspace explicitly. The package does not infer it from the installation or
current directory. JSON Schema is generated from Pydantic models through
`hla-lab-schema`; generated copies are not maintained in source control.
New code and user workflows should enter through `hla-lab` or a module under
`hla_lab`. One-time migrations are explicitly isolated under
`tools/migrations/`.

## Dependency direction

```text
source corpus and manifests
            ↓
semantic model and source adapters
            ↓
authority, coverage, graph, and readiness checks
            ↓
reports, external contracts, and publication projections
            ↓
faithful LaTeX/diagram adapters
```

The semantic model must not depend on LaTeX layout, publication output, or
concrete RTI code. Planned implementation mappings may depend on semantic IDs,
but they must not be presented as implementation evidence.

## Data ownership

The source-controlled manifests are the authoritative registry layer:

- `data/semantic/edition-lineage.json` owns document identity, roots, edition
  metadata, source-profile selection, and migration ownership;
- `data/semantic/source-profiles.json` owns edition-specific faithful diagram
  bindings and page geometry;
- `data/publications.json` owns publication membership and source-document
  selection;
- `data/release/documents.json` owns build strategy, output paths, generation
  selections, and release expectations.

Document-local `build.py` files are intentionally thin launchers. The shared
`hla_lab.build.topic` runner consumes those declarations and supplies the
semantic, derivative, compliance, or faithful adapter strategy. Algorithms,
parsers, validators, and rendering engines remain code; the facts they consume
remain data.

The shared runner exposes three durable actions: `generate` materializes the
ignored semantic build inputs, `build` produces the document, and `clean`
removes build products. CI invokes the same manifest-resolved `generate` action
before diagram and release checks so fresh checkouts do not depend on generated
files from another job.

## Public workflows

```console
hla-lab                  # show the workflow menu
hla-lab --root . docs             # list document roots
hla-lab --root . status           # validate the complete corpus
hla-lab --root . build            # build all products
hla-lab --root . publish          # list publications
hla-lab --root . test --parallel  # run the contract suite in parallel
hla-lab --root . quality          # run the ordered CI-quality workflow
```

`status` accepts `--document`, `--json`, `--require-api-contract`, and
`--require-concrete` when a narrower or stricter gate is needed. `build`
defaults to all document products, and `publish <id>` builds one declared
publication. The underlying module entry points remain available for advanced
operations and automation.

Install the project with `python -m pip install -e .` to place `hla-lab` on
`PATH`. `uv sync --dev` and `uv run hla-lab ...` are optional contributor
conveniences, not requirements for using the entry point.

The ordered repository validation contract lives in `tools/ci.py`, not in the
workflow YAML. Run the same checks locally with:

```console
python -m tools.ci quality --root .
python -m tools.ci release --root .
python -m tools.ci all --root .
```

`.github/workflows/ci.yml` provisions the platform-specific toolchain and
delegates the quality and document-release jobs to that script.

## Migration rules

1. Put reusable domain behavior in a package module, not in a one-off command.
2. Expose a stable orchestration path from `hla_lab.cli` for user workflows.
3. Keep source paths, record IDs, and JSON schemas backward-compatible unless
   a scope change explicitly requires a versioned migration.
4. Add or update a capability contract test with every new semantic surface.
5. Keep publication and faithful-rendering code downstream of the semantic
   source, never as a second source of truth.

## Consolidation sequence

The architecture is intentionally incremental:

1. establish scope and the `hla-lab` command boundary — complete;
2. move shared path/configuration helpers into `hla_lab` — complete;
3. group implementation modules into domain packages — complete;
4. remove the temporary compatibility package — complete;
5. make CI invoke the public lab checks and capability-oriented pytest suite;
6. make document identities, faithful mappings, and build orchestration
   manifest-driven — complete.
