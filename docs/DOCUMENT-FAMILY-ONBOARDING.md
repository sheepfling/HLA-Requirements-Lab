# Document-family onboarding

This repository uses a profile boundary so a new document family can reuse
the semantic model and builder without adding its vocabulary to the generic
layers.

## Required document shape

Create a directory below `topics/<topic>/<document>/` with:

```text
build.py              # thin wrapper around hla_lab.adapters.document_builder
main.tex              # layout and generated-input entry point
latexmkrc             # writes build products below build/
source/               # source-shaped LaTeX or other family inputs
fixture_profile.py    # family-local source commands and LaTeX dialect
README.md             # provenance, build instructions, known differences
```

Generated `output/`, `build/`, and `dist/` contents are ignored. Semantic
source files under `semantic/` are tracked when a record has been promoted
out of source-shaped input.

Do not add page projections under `sections/generated/`. Canonical page and
requirement data belongs under `semantic/`; generated TeX belongs under the
ignored `output/semantic/` directory. A small exceptional layout adapter, such
as a hand-reviewed cover drawing, belongs with the authored `frontmatter/` or
`figures/` source instead.

## Profile contract

The family profile supplies a `LatexSourceProfile` implementation from
`hla_lab/core/source_adapter.py`. It declares the names used by the family's
source syntax: clause headings, definition environments, requirement markers,
references, notes, figures, table cells, and optional layout wrappers. It also
declares `table_domain` as `generic` or `omt`; a numbered table is not assumed
to be HLA/OMT merely because it has a number.

The profile separately supplies a `LatexDialect` from
`hla_lab/adapters/latex_renderer.py`, mapping semantic records to the family's visible
heading, definition, and requirement commands. Keep family constants in the
profile module. Do not import the HLA profile from the semantic model,
semantic generator, or neutral renderer.

## Build contract

The document's release-manifest entry declares its strategy, selections, and
output path. The document-local wrapper only delegates to the shared runner:

```python
from hla_lab.build.topic import main

if __name__ == "__main__":
    raise SystemExit(main(root=ROOT))
```

Add the corresponding `build` object to
`data/release/documents.json`; use `strategy: "faithful"` for a page-faithful
document or the shared derivative/compliance strategies for generated products.

`main.tex` should input the generated semantic manifest and generated record
blocks. The manifest also loads the generated hierarchy index; the complete
machine-readable hierarchy graph is emitted beside it as `hierarchy.json`.
Page adapters receive stable semantic anchors from the shared generator, while
the family remains responsible for exceptional layout formatting. `main.tex`
should not become the second semantic owner of definitions, requirements,
clause order, or table data.

## M13 reference fixture

`topics/fixture/non-hla-demo-2025/` is the smallest complete example. It has
two hierarchy nodes, one definition, one requirement, one generic table, one
reference, a family-local profile, and a one-page build. Its tests exercise
canonical hierarchy navigation, definition search, requirement matching, table
search, reference lookup, Pydantic round trips, generated faithful inputs,
the generic derivative renderer, and HLA-profile isolation.

Run it directly or through the top-level builder:

```console
python topics/fixture/non-hla-demo-2025/build.py build
hla-lab build topics/fixture/non-hla-demo-2025
uv run pytest tests/test_portability_contracts.py -q
```

Use this fixture as the onboarding template for a second document family;
copy its profile boundary and replace its source vocabulary and semantic
records rather than modifying the generic model for family-specific commands.
