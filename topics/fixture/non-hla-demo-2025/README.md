# Non-HLA semantic profile fixture

This tiny document is the M13 portability proof. It uses the shared
Pydantic model, source loader, semantic generator, LaTeX renderer, and common
document builder with a document-local vocabulary defined in
`fixture_profile.py`.

The source-shaped semantic input is `source/semantic.tex`. `main.tex` contains
only layout and generated semantic inputs. The fixture deliberately includes
a hierarchy, definition, requirement, table, and reference so generic queries
can be exercised without importing an HLA profile.

Build it from this directory with:

```powershell
python build.py build
```

The PDF and LaTeX intermediates are ignored. The profile is intentionally
small: a real document family can add its own command vocabulary and dialect
without changing `hla_lab/core/semantic_model.py`, `hla_lab/generation/semantic_generation.py`,
or `hla_lab/adapters/latex_renderer.py`.
