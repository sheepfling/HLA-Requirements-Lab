# HLA Requirements Lab — 1516.2 build

This builds the independent HLA Requirements Lab 1516.2 source compilation. Supplied source material is retained
for traceability; the output is not presented as a publisher-issued standard.

## Requirements

- Python 3.11+
- XeLaTeX and `latexmk`
- Checked-in Inter, Noto Serif, and DejaVu Sans Mono fonts

Install the Python dependencies from the repository root:

```console
python -m pip install -e .
```

## Build

From this directory:

```console
python build.py build
python build.py clean
```

The named output is written to `dist/`. Build products, PDFs, comparison material, and verification reports
are local-only and ignored by the repository policy.

The source compilation uses `canonical/lab-navigation.json`. Its bookmarks
are checked against headings visible on the actual generated pages. The
historical `source-navigation.json` remains source evidence for the earlier
124-page edition, not navigation to inject into this 113-page build. The
omitted historical front-matter pages and coordinate-based link overlays are
not part of the Lab compilation.
