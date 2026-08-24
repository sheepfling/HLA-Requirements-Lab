# HLA Requirements Lab abstract family graphic system v0.1

This prototype is intentionally vector-only and designed for direct LaTeX/TikZ use.

## Visual grammar

- **Framework and Rules / IEEE 1516**: whole-system topology held inside a governing frame.
- **Federate Interface / IEEE 1516.1**: bidirectional service and callback paths across a boundary.
- **OMT / IEEE 1516.2**: wireframe schema/lattice with linked model elements.
- **2010 edition**: contained, single-plane construction representing the established baseline.
- **2025 edition**: layered, offset construction with an explicit extension beyond the original frame.

Volume identity is carried by both geometry and accent color, so the family remains distinguishable in
color and in grayscale. Edition identity is primarily geometric, not merely a changed year label.

## Files

- `contact_sheet.tex`: six-up comparison matrix.
- `cover_studies.tex`: six full-size cover studies.
- `rl_graphics.tex`: shared colors, metadata, and reusable TikZ glyph/cover macros.

Compile with LuaLaTeX from this directory:

```bash
lualatex contact_sheet.tex
lualatex cover_studies.tex
```
