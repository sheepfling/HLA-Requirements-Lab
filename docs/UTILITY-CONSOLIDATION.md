# Utility consolidation

This is the working inventory for small converters, coercers, identifier
builders, regex-backed parsers, and quoting helpers. The goal is one reviewed
implementation per behavior, with document-specific policy remaining at the
adapter boundary.

## Shared utilities

| Module                      | API                                                     | Replaces or centralizes                                               |
| --------------------------- | ------------------------------------------------------- | --------------------------------------------------------------------- |
| `hla_lab/core/text.py`      | `tex_escape`                                            | LaTeX escaping in the renderer and diagram exporters                  |
|                             | `safe_identifier`                                       | DOT/Mermaid/TikZ node aliases in state, sequence, and graph exporters |
|                             | `safe_filename`                                         | bounded generated semantic filenames                                  |
|                             | `slugify`                                               | repeated lower-case dash slugs and safe IDs                           |
|                             | `mermaid_text`, `dot_quote`                             | Mermaid label and Graphviz string quoting                             |
|                             | `format_number`                                         | deterministic diagram coordinate formatting                           |
|                             | `normalize_whitespace`                                  | source-boundary text normalization                                    |
| `hla_lab/core/parsing.py`   | `balanced_group`, `try_balanced_group`, `balanced_span` | repeated balanced LaTeX group scans                                   |
|                             | `line_number`                                           | source offset-to-line conversion                                      |
| `hla_lab/core/coercions.py` | `coerce_int`, `optional_float`                          | JSON profile integer conversion and layout coordinate conversion      |

## Intentionally local behavior

These are not duplicates even when their names look similar:

- HLA LaTeX text extraction (`_latex_text`) is profile-aware and belongs to
  the semantic model. It is not the same operation as escaping output text.
- Reflow/publication `_text` helpers apply product-specific Unicode and source
  punctuation policy before calling `tex_escape`.
- The legacy state-machine renderer has Unicode-aware TikZ text behavior that
  is not equivalent to plain TeX escaping.
- Migration scripts retain one-off matching and repair heuristics. They may
  consume the shared primitives, but they do not define the production API.

## Migration status

- [x] Add shared text/rendering primitives.
- [x] Add shared balanced-group and source-line primitives.
- [x] Add shared integer and optional-float coercions.
- [x] Migrate shared production callers and remove exact local duplicates.
- [x] Audit migration-only scripts; shared parsing, slug, and JSON-writing
  primitives are now reused there too.
- [x] Add `python -m tools.utility_inventory` as a repeatable duplicate-helper
  check. It currently reports zero exact duplicate private-helper bodies.

The inventory intentionally does not report every local helper as a defect.
For example, publication text normalization and legacy TikZ Unicode handling
are policy-bearing adapters, not interchangeable coercers.
