# IEEE HLA 1516.2-2025 build

This is an unofficial, source-first LaTeX reconstruction. The separately held reference PDF is comparison
material only and is not required for a normal build.

## Requirements

- Python 3.11+
- XeLaTeX and `latexmk`
- Graphviz (`dot`)
- Arimo, Tinos, Carlito, Noto Sans, and Noto Serif fonts

Install the Python dependencies from the repository root:

```console
python -m pip install -e .
```

On Debian or Ubuntu, install the system build tools and fonts from the
distribution package archive:

```console
sudo apt-get update
sudo apt-get install fonts-croscore fonts-crosextra-carlito fonts-noto-core fonts-lmodern graphviz latexmk texlive-fonts-recommended texlive-latex-extra texlive-xetex
```

The official [Debian package records](https://packages.debian.org/bookworm/fonts-croscore)
list Arimo and Tinos in `fonts-croscore`, [Carlito](https://packages.debian.org/bookworm/fonts-crosextra-carlito)
in `fonts-crosextra-carlito`, and [Noto Sans and Noto Serif](https://packages.debian.org/bookworm/fonts-noto-core)
in `fonts-noto-core`. Debian's [XeLaTeX](https://packages.debian.org/bookworm/texlive-xetex),
[`latexmk`](https://packages.debian.org/bookworm/latexmk),
[Graphviz](https://packages.debian.org/bookworm/graphviz), and TeX packages
[`texlive-fonts-recommended`](https://packages.debian.org/bookworm/texlive-fonts-recommended),
[`texlive-latex-extra`](https://packages.debian.org/bookworm/texlive-latex-extra), and
[`fonts-lmodern`](https://packages.debian.org/bookworm/fonts-lmodern) supply the
remaining build tools. On other Linux distributions, install the corresponding
packages from that distribution's repositories.

If XeLaTeX reports `The font "Tinos" cannot be found` (or names another font
above), install the missing font package, refresh the system font cache if your
distribution requires it, then retry the build. The 1516.1 styles have
font fallbacks; the 1516.2 style requires the named fonts. A font-resolution
failure is a local build prerequisite issue.

## Build

From this directory:

```console
python build.py build
python build.py clean
```

From the repository root, the same PDF workflow is available as
`hla-lab generate topics/ieee/hla-1516.2-2025`. It regenerates semantic inputs
first and prints the configured PDF output path.

The named output is written to `dist/`. Build products, PDFs, comparison material, and verification reports
are local-only and ignored by the repository policy.
