# HLA Requirements Lab — 1516.2 source compilation

Ingested from `HLA-1516.2-2025-final-rerender-latex-bundle-v1.0.1.zip`.

The editable LaTeX/Python source is kept directly in this document directory. The document-level `build.py` provides the
repository-standard entry point.

This is an independent HLA Requirements Lab compilation built from supplied HLA source materials. Source
identifiers are retained where they are needed for technical traceability; this document is not presented as a
publisher-issued standard.

Rendered PDFs and raster assets remain local-only and are ignored by the repository policy. The intended long-term
source of truth is the text-based LaTeX/TikZ/Python reconstruction.

## Build

Requirements are documented in [`BUILDING.md`](BUILDING.md).

```console
python build.py build
python build.py clean
```
