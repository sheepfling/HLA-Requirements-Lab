# IEEE HLA 1516.1-2025 build

This is an unofficial, source-first LaTeX reconstruction. The separately held reference PDF is comparison
material only and is not required for a normal build.

## Requirements

- Python 3.11+
- XeLaTeX and `latexmk`
- Arimo, Tinos, Carlito, Noto Sans, and Noto Serif fonts

Install the Python dependencies from the repository root:

```powershell
python -m pip install -e .
```

## Build

From this directory:

```powershell
python build.py build
python build.py clean
```

The output is written to `build/`. Build products, PDFs, comparison material, and verification reports are
local-only and ignored by the repository policy.
