# Requirements Lab publishing system

This directory is the shared Design System v0.1 layer for HLA Requirements Lab
publications.

The design system owns presentation: typography, page furniture, headings,
tables, code/XML, mathematics, notes, links, and front matter. Semantic source
and provenance remain in the document products and their machine-readable
models.

Orange is reserved for decorative geometry, rules, dots, borders, and other
non-semantic accents. Readable labels and text use the blue, ink, or mid-tone
tokens for print and screen contrast.

The style specimen and the `hla-1516.2-2025-modern-acceptance` slice are the
visual contract for the modern interior. The complete 1516.2-2025 body remains
a separate content-integrated legacy-layout build until that slice is approved;
the migrated body should load `class/requirements-lab.cls` and use these
components rather than restyling individual generated pages.

The supplied OMT interior and family-graphics studies are preserved for
traceability in `prototype-reference/`. The production-facing graphics
adapter is `style/rl-graphics.sty`, which keeps the family and edition cues
without carrying source-study or publisher identity into new documents.
