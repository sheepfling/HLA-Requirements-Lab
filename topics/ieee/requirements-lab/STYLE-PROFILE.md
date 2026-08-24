# HLA Requirements Lab style profile

## Canonical specimen

`topics/ieee/hla-1516.2-2025/` is the canonical style specimen for the six
HLA Requirements Lab source compilations. Its visual decisions are the source
of the shared profile, not a claim that the resulting compilations are IEEE
publications.

The specimen establishes:

- Noto Serif for readable prose;
- Inter for navigation, headings, labels, and page furniture;
- DejaVu Sans Mono for identifiers and technical values;
- deep blue/ink readable text and blue-gray rules and table bands;
- orange only for non-semantic geometry and small family markers;
- restrained one-line headers, visible folios, and stable footer furniture;
- compact clause hierarchy and table treatment;
- contained 2010 geometry and layered/extensible 2025 geometry;
- distinct framework, federate-interface, and OMT family graphics.

## Shared implementation

The natural-flow implementation is composed by
`requirements-lab/class/requirements-lab.cls`. Fixed-coordinate source
adapters use `style/rl-fixed-page.sty` for the same header, footer, folio, and
accent-rule contract. `style/rl-publication.sty` maps each product's neutral
HLA metadata into the shared profile.

The six products are deliberately not forced into one body-layout class. The
2010 and 2025 source sets have different pagination and source geometry; the
shared style contract governs the visible system while each adapter preserves
content order and measured layout until it has passed render QA.

## Measured adapter rules

The five source-faithful legacy adapters set `\\RLSerifScale` to `0.82` while
using the canonical Noto Serif reading face. This keeps their source-derived
line membership and page geometry stable while removing the old reading-font
dependency. The modern 1516.2-2025 interior remains at the native scale.

Natural-flow products reserve the shared header band explicitly. The 2010
framework and federate-interface products use a 19 pt header height; the 2010
OMT product uses 20 pt because its header stack is one line denser. These are
measured layout parameters, not product-specific visual exceptions.

Technical TikZ labels also use the canonical Inter family. Legacy `phv` and
`qhv` NFSS role names are not part of the baseline, so figure-local font
changes cannot silently reintroduce unavailable or substituted reading roles.

## Product matrix

| Product | Edition | Family | Body strategy | Shared profile |
| --- | --- | --- | --- | --- |
| HLA 1516 | 2010 | framework | source-faithful adapter | yes |
| HLA 1516 | 2025 | framework | source-faithful adapter | yes |
| HLA 1516.1 | 2010 | federate interface | source-faithful adapter | yes |
| HLA 1516.1 | 2025 | federate interface | source-faithful adapter | yes |
| HLA 1516.2 | 2010 | OMT | source-faithful adapter | yes |
| HLA 1516.2 | 2025 | OMT | source-faithful adapter | yes |

The shared profile is an implementation boundary and quality gate. It does
not carry temporary review identifiers, ballot history, publisher identity, legacy legal
notices, or source-study rights statements.
