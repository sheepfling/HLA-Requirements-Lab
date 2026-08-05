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
```

Each document is intentionally self-contained. A document directory is considered buildable when it contains `build.py`. The top-level builder can build one document, one topic, or every document in the repository.

The current IEEE ingestion lives at:

```text
topics/ieee/hla-1516.1-2025/
topics/ieee/hla-1516.2-2025/
topics/ieee/hla-1516-2025/
```

Those projects expose thin document-level wrappers backed by the shared Python builder.

## Source-of-truth policy

The repository should generally baseline the reconstruction source and provenance notes, not rendered or extracted binaries. PDFs, raster image files, archives, and build outputs are ignored by default. Use TikZ/LaTeX and Python to regenerate document visuals and rendered artifacts from committed text-based sources.

Binary files may remain in a local working tree when an upstream build or visual comparison needs them, but they should not be force-added to Git without an explicit reason.

## Analogue and comparison boundary

An existing document, PDF, scan, rendered page, or extracted image may be used as an analogue while recreating a document. It is working reference material—not the recreation baseline. Keep that material outside the committed source tree or under an ignored `.local/`, `reference/`, or `comparison/` directory.

The baseline should contain the independently authored reconstruction: LaTeX/TikZ source, Python generators and validators, text-based metadata, tests, and provenance notes. Comparison artifacts may inform implementation and verification, but they should not become the implementation itself.

## Build commands

From the repository root:

```powershell
python -m pip install -e .
python scripts/build.py list
python scripts/build.py build all
python scripts/build.py build topics/siso/example-document
python scripts/build.py clean
```

On Windows with MiKTeX, enable one-time automatic installation of missing LaTeX packages with:

```powershell
initexmf --enable-installer
```

The document `latexmkrc` files opt into this setting for Windows builds. MiKTeX also exposes the same
setting in MiKTeX Console under the package installation preferences.

Document build scripts should write generated files to their local `output/` directory and keep source inputs in the document directory (or its `src/` and `assets/` subdirectories).

## Adding a document

1. Create `topics/<topic>/<document>/`.
2. Add a document-local `build.py`.
3. Keep the build reproducible and avoid committing generated output.
4. Add notes about provenance, source material, and known differences to the document's README.
