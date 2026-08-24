# Requirements Lab publishing system

This directory is the shared Design System v0.1 layer for HLA Requirements Lab
publications. The HLA 1516.2-2025 source compilation is the canonical style
specimen: it demonstrates the intended typography, page furniture, table
hierarchy, restrained color use, and fixed-page compatibility treatment.

The design system owns presentation: typography, page furniture, headings,
tables, code/XML, mathematics, notes, links, and front matter. Semantic source
and provenance remain in the document products and their machine-readable
models.

Orange is reserved for decorative geometry, rules, dots, borders, and other
non-semantic accents. Readable labels and text use the blue, ink, or mid-tone
tokens for print and screen contrast.

The `hla-1516.2-2025-modern-acceptance` slice is the detailed natural-flow
acceptance fixture for that specimen. The complete 1516.2-2025 body remains a
content-integrated fixed-layout build, but now consumes the shared
`style/rl-publication.sty` profile and `style/rl-fixed-page.sty` furniture.
The other five products use the same profile seam so their source-faithful
body geometry can be migrated incrementally without reintroducing document-
specific typography or page-furniture forks.

The style boundary is deliberate:

- `style/rl-brand.sty`, `rl-type.sty`, `rl-headings.sty`, `rl-tables.sty`, and
  the related modules own reusable visual tokens and components;
- `style/rl-fixed-page.sty` owns the fixed-page compatibility furniture used by
  source-faithful adapters;
- `style/rl-publication.sty` maps HLA publication metadata into that shared
  surface for all six products;
- topic `main.tex` files own only publication metadata and source/body inputs.

No source-study, IEEE publisher, ballot, or legacy rights language belongs in
this style layer.

The supplied OMT interior and family-graphics studies are preserved for
traceability in `prototype-reference/`. The production-facing graphics
adapter is `style/rl-graphics.sty`, which keeps the family and edition cues
without carrying source-study or publisher identity into new documents.
