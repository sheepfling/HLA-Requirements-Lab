# HLA OMT source-driven production pages

This preview has a single QA cover followed by source-driven
production pages. The interior uses the supplied prototype prose and exact
source structures for Table 16, Table 17, Table 29, Table 5, Table 10, Table
11, and Table 45.

The preview remains separate from the complete 1516.2-2025 body build while
the shared interior is migrated. Production pages do not repeat QA labels or
visible source-trace stamps, and they do not carry external publisher identity
or publication boilerplate.

Table 5 is presented as a selected portrait-page hierarchy slice so the tree
remains readable; parentage is represented by explicit source-derived edges,
not inferred from indentation. Every shown class name, relationship,
designation, and note marker is retained from the supplied source example.
Table 11 is likewise explicitly labeled as selected source rows and retains
the machine-significant `TimeStamp` value and selected dimension-bearing
branches.

The preview uses exact-transcription mode for source-derived table values,
identifiers, and note prose. Editorial normalization is not performed
silently; a future normalized edition must carry an explicit change record.

Build with:

```powershell
python build.py clean
python build.py build
```

The preview is written to `dist/` and uses the shared
`topics/ieee/requirements-lab/` system.

Its visual grammar is adapted from the supplied OMT interior prototype and
family-graphics study. The source studies are retained under
`topics/ieee/requirements-lab/prototype-reference/`; production documents load
the namespaced `rl-graphics.sty` adapter instead of copying source-study
identifiers into the publication text.
