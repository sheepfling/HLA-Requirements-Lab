"""Modernize diagram and table source surfaces for generated documents."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    Sequence,
)

from hla_lab.adapters.latex_renderer import (
    tex_escape,
)
from hla_lab.core.semantic_model import (
    Table,
)
from hla_lab.generation.semantic_generation_diagrams import _remove_latex_macro_invocations
from hla_lab.generation.semantic_generation_mom import _modern_mom_page
from hla_lab.generation.semantic_generation_protocol import _modern_protocol_page
from hla_lab.generation.semantic_generation_special_pages import (
    _modern_api_manifest_page,
    _modern_java_factory_page,
    _modern_protocol_prose_page,
)
from hla_lab.generation.semantic_generation_tables import _modern_table5_page

_FIGURE_TABLE_ROWS_2025: tuple[tuple[int, str], ...] = (
    (1, "Basic states of the federation execution"),
    (2, "Overall view of federate-to-RTI relationship"),
    (3, "Lifetime of a federate"),
    (4, "Joined federate state"),
    (5, "Normal Activity Permitted state"),
    (6, "Federation execution and sync points"),
    (7, "Global synch label (L)"),
    (8, "Awaiting synchronization (s, L)"),
    (9, "Local synch label (s, L)"),
    (10, "Object class (i)"),
    (11, "Class attribute (i, j)"),
    (12, "Class attribute (i, HLAprivilegeToDeleteObject)"),
    (13, "Interaction class (m)"),
    (14, "Object instance (i, k) known"),
    (15, "Implications of ownership of instance attribute (i, k, j)"),
    (16, "Establishing ownership of instance attribute (i, k, j)"),
    (17, "Temporal state"),
    (18, "Region of two dimensions"),
    (19, "MOM object class structure"),
    (20, "MOM interaction class structure"),
    (21, "HLA Federate Protocol layers"),
    (22, "Federate and RTI message sequence numbers"),
    (23, "Response messages"),
    (24, "Federate Connection and Reconnection States"),
    (25, "RTI Connection and Reconnection States"),
    (26, "Successful reconnection"),
    (27, "Federate Session Startup State Diagram"),
    (28, "Federate Resume State Diagram"),
    (29, "Federate Exception State Diagram"),
    (30, "RTI Port Handling State Diagram"),
    (31, "RTI Startup State Diagram"),
    (32, "RTI Resume State Diagram"),
    (33, "RTI Exception Handling State Diagram"),
)


def _modern_figure_table_page(sequence: int) -> str:
    """Render Annex H from figure labels rather than source-page integers."""

    start = 0 if sequence == 435 else 17
    rows = _FIGURE_TABLE_ROWS_2025[start : start + (17 if sequence == 435 else 16)]
    # RLInlineTableCaption supplies the table number; keep the title itself
    # free of a second ``Table H.1`` prefix.
    title = "Figure numbers" if sequence == 435 else "Figure numbers (continued)"
    rendered_rows = "\n".join(
        " & ".join(
            (
                f"\\hyperlink{{figure:{number}}}{{Figure {number}, {tex_escape(caption)}}}",
                f"page~\\pageref{{figure:{number}}}",
            )
        )
        + r" \\"
        + (r"\RLProductionRowRule" if index + 1 < len(rows) else "")
        for index, (number, caption) in enumerate(rows)
    )
    return f"""\\HLASourcePage{{{sequence + 1}}}{{{sequence}}}
\\begin{{RLLandscapePage}}
\\thispagestyle{{rl}}
\\noindent
{{\\RLSans\\bfseries\\fontsize{{13.2pt}}{{15.6pt}}\\selectfont Annex H}}\\par
\\vspace{{2pt}}
{{\\RLSans\\fontsize{{8.6pt}}{{10pt}}\\selectfont (informative)}}\\par
\\vspace{{11pt}}
\\RLInlineTableCaption{{H.1}}{{{tex_escape(title)}}}
\\begingroup
\\setlength{{\\tabcolsep}}{{5pt}}
\\renewcommand{{\\arraystretch}}{{1.12}}
\\begin{{tabularx}}{{\\linewidth}}{{@{{}}YL{{0.22\\linewidth}}@{{}}}}
\\RLProductionTopRule
\\RLProductionHeaderBand
\\RLTableHeaderCell{{Figure number and name}} & \\RLTableHeaderCell{{Requirements Lab page}} \\\\
\\RLProductionHeaderRule
{rendered_rows}
\\RLProductionBottomRule
\\end{{tabularx}}
\\endgroup
\\end{{RLLandscapePage}}
"""


def _inject_figure_caption_anchors(body: str) -> str:
    """Give legacy fixed captions the same page label as generated figures."""

    anchored = set(re.findall(r"\\HLAFigureAnchor\{(\d+)\}", body))

    def replace(match: re.Match[str]) -> str:
        number = match.group(1)
        if number in anchored:
            return match.group(0)
        anchored.add(number)
        return f"\\HLAFigureAnchor{{{number}}}{match.group(0)}"

    # Legacy fixed-page captions use either the three-hyphen source form or
    # the Unicode em dash form.  Anchor only caption-like occurrences so
    # prose references such as “depicted in Figure 19” remain untouched.
    return re.sub(r"Figure\s+(\d+)(?:---|—)", replace, body)


def _modernize_2025_flow_page(body: str, sequence: int) -> str | None:
    if sequence in {435, 436}:
        return _modern_figure_table_page(sequence)
    if sequence == 360 or 354 <= sequence <= 394:
        return _modern_java_factory_page(body)
    if 416 <= sequence <= 421:
        return _modern_api_manifest_page(body)
    if sequence in {395, 396, 397, 398, 399, 400, 401, 403, 408}:
        return _modern_protocol_prose_page(body)
    return None


def _modernize_2025_semantic_table_page(
    body: str,
    sequence: int,
    tables: Sequence[Table],
) -> str | None:
    if 305 <= sequence <= 352:
        page_tables = tuple(table for table in tables if table.id.endswith(f"-p{sequence}"))
        return _modern_mom_page(page_tables, sequence=sequence, source_body=body)
    if sequence in {402, 404, 405, 406, 407}:
        page_tables = tuple(table for table in tables if table.id.endswith(f"-p{sequence}"))
        if page_tables:
            return _modern_protocol_page(page_tables, sequence=sequence, source_body=body)
    if 295 <= sequence <= 304:
        table_id = f"table-5-p{sequence}"
        table = next((item for item in tables if item.id == table_id), None)
        if table is not None:
            return _modern_table5_page(table, sequence=sequence)
    return None


def _modernize_2025_source_surface(
    body: str,
    *,
    sequence: int,
    tables: Sequence[Table] = (),
) -> str:
    """Remove inherited publisher furniture from the 2025 Lab surface.

    The 2025 interface corpus is used as source material for a new Lab
    compilation.  A few source pages are still authored as rotated fixed
    surfaces, so their old masthead and folio would otherwise survive even
    after the surrounding document has been modernized.  Keep the semantic
    table/figure payload for the staged migration, but remove that publisher
    furniture and correct source markup that would otherwise be visible as
    LaTeX commands in the released PDF.
    """

    body = _remove_latex_macro_invocations(
        body,
        "HLAInvisibleFixedCenteredBlock",
        7,
    )
    body = _inject_figure_caption_anchors(body)

    flow_page = _modernize_2025_flow_page(body, sequence)
    if flow_page is not None:
        return flow_page
    semantic_table_page = _modernize_2025_semantic_table_page(body, sequence, tables)
    if semantic_table_page is not None:
        return semantic_table_page

    if sequence == 179:
        # Source page 180 contains a dense four-column time-advancement
        # summary.  Its source coordinates are internally consistent for the
        # original page, but the fixed-position adapter makes the cells
        # collide at Lab typography.  Preserve the source values and caption,
        # while giving the table a real landscape, content-driven layout.
        return "\n".join(
            (
                "\\HLASourcePage{180}{179}",
                "\\begin{RLLandscapePage}",
                "\\thispagestyle{rl}",
                "\\noindent",
                (
                    "{\\RLSans\\bfseries\\fontsize{10.2pt}{12pt}\\selectfont 8.1.2 Time a"
                    "dvancement summary}\\par"
                ),
                "\\vspace{5pt}",
                "\\RaggedRight",
                (
                    "A joined federate is permitted to advance its logical time only "
                    "by requesting a time advancement from the RTI. Its logical time "
                    "shall not actually be advanced until the RTI responds with a \\em"
                    "ph{Time Advance Grant}\\textdagger{} or \\emph{Flush Queue Grant}\\"
                    "textdagger{} service invocation at that joined federate. The int"
                    "erval between these service invocations is the Time Advancing st"
                    "ate shown in Figure 17."
                ),
                "\\par\\vspace{4pt}",
                (
                    "Each service takes a specific logical time $t_R$ as an argument "
                    "and requests different coordination from the RTI. The summary be"
                    "low preserves the source distinctions between the Time Advancing"
                    " and Time Granted states."
                ),
                "\\par\\vspace{5pt}",
                "\\RLInlineTableCaption{1}{Service descriptions}",
                "\\setlength{\\tabcolsep}{4pt}",
                "\\renewcommand{\\arraystretch}{1.14}",
                (
                    "\\begin{longtable}{@{}p{0.20\\linewidth}p{0.25\\linewidth}p{0.29\\li"
                    "newidth}p{0.22\\linewidth}@{}}"
                ),
                "\\RLProductionTopRule",
                "\\RLProductionHeaderBand",
                "\\RLTableHeaderCell{Time advancement service} &",
                "\\RLTableHeaderCell{Cannot send while advancing} &",
                "\\RLTableHeaderCell{Messages delivered before grant} &",
                "\\RLTableHeaderCell{Constraint after grant}\\\\",
                "\\RLProductionHeaderRule",
                (
                    "\\texttt{Time Advance Request} & $ts < t_R + \\mathrm{lookahead}$ "
                    "& All queued RO messages; all TSO messages with $ts \\leq t_R$ & "
                    "$ts < LT + \\mathrm{lookahead}$\\\\"
                ),
                "\\RLProductionRowRule",
                (
                    "\\texttt{Time Advance Request} (zero lookahead) & $ts \\leq t_R$ &"
                    " All queued RO messages; all TSO messages with $ts \\leq t_R$ & $"
                    "ts \\leq LT$\\\\"
                ),
                "\\RLProductionRowRule",
                (
                    "\\texttt{Time Advance Request Available} & $ts < t_R + \\mathrm{lo"
                    "okahead}$ & All queued RO messages; all TSO messages with $ts < "
                    "t_R$ & $ts < LT + \\mathrm{lookahead}$\\\\"
                ),
                "\\RLProductionRowRule",
                (
                    "\\texttt{Next Message Request} & $ts < t_R + \\mathrm{lookahead}$ "
                    "& The TSO message with the smallest timestamp that will ever be "
                    "received for which $ts \\leq t_R$; all other TSO messages with th"
                    "e same $ts$ & $ts < LT + \\mathrm{lookahead}$\\\\"
                ),
                "\\RLProductionRowRule",
                (
                    "\\texttt{Next Message Request} (zero lookahead) & $ts < t_R$ & Th"
                    "e TSO message with the smallest timestamp that will ever be rece"
                    "ived for which $ts \\leq t_R$; all other TSO messages with the sa"
                    "me $ts$ & $ts < LT$\\\\"
                ),
                "\\RLProductionRowRule",
                (
                    "\\texttt{Next Message Request Available} & $ts < t_R + \\mathrm{lo"
                    "okahead}$ & The TSO message with the smallest timestamp that wil"
                    "l ever be received for which $ts \\leq t_R$; all other queued TSO"
                    " messages with the same $ts$ & $ts < LT + \\mathrm{lookahead}$\\\\"
                ),
                "\\RLProductionRowRule",
                (
                    "\\texttt{Flush Queue Request} & $ts < t_R + \\mathrm{lookahead}$ &"
                    " All queued TSO messages & $ts < OLT + OL$\\\\"
                ),
                "\\RLProductionBottomRule",
                "\\end{longtable}",
                "\\vspace{3pt}",
                (
                    "{\\fontsize{7.8pt}{9.2pt}\\selectfont\\textdagger{} The Time Advanc"
                    "e Grant service is used for all forms of time advance request ex"
                    "cept Flush Queue Request, which is granted by Flush Queue Grant."
                    "}\\par"
                ),
                "\\end{RLLandscapePage}",
                "",
            )
        )
    if sequence >= 0:
        for pattern in (
            r"\s*\\HLARotatedLine\{30\.258\}\{435\.300\}.*?\n \}\n",
            r"\s*\\HLARotatedLine\{40\.278\}\{543\.000\}.*?\n \}\n",
            r"\s*\\HLARotatedLine\{50\.297\}\{451\.920\}.*?\n \}\n",
            r"\s*\\HLARotatedLine\{546\.226\}\{406\.560\}.*?\n \}\n",
        ):
            body = re.sub(pattern, "\n", body, flags=re.DOTALL)

    body = body.replace(
        r"\textbf{\{\textbackslash{}ldots\{\}\}}",
        r"\textbf{\{\dots\}}",
    )
    body = body.replace(r"\textbackslash{}ldots\{\}", r"\dots")
    body = body.replace(r"\textbackslash{}", r"\char92{}")
    body = body.replace(r"\_", r"\char95{}")
    body = body.replace(
        r"IEEE Std 1516.1\texttrademark-2025",
        "this document",
    )
    body = body.replace("IEEE Std 1516.1-2025", "this document")
    body = body.replace(
        "This standard, this document, provides",
        "This source compilation provides",
    )
    body = body.replace(
        "The RTI shall provide the this document Java API classes",
        "The RTI shall provide the HLA 1516.1 Java API classes",
    )
    body = body.replace(
        "IEEE Std 1516-2025, this standard, and IEEE Std\\linebreak 1516.2-2025",
        "the supplied HLA source set and this Requirements Lab compilation",
    )
    body = body.replace(
        "as prescribed in this document. See also",
        "as prescribed in this document. See also",
    )
    if sequence in {89, 150, 180, 187}:
        # These are the first portrait source pages after true landscape
        # insertions (Figures 11/12, 16/17, and the rebuilt Table 1).  Use the
        # fixed Lab furniture directly so no landscape page-style state can
        # affect their footer position.
        body = body.replace(
            r"\thispagestyle{hla-body}",
            r"\thispagestyle{empty}\RLFixedFurniture",
            1,
        )
    return body


def _modernize_2025_generated_tex(text: str) -> str:
    """Keep source tokens readable in the released PDF text layer."""

    return (
        text.replace(r"\textbackslash{}", r"\char92{}")
        .replace(r"\_", r"\char95{}")
        # Source captions sometimes contain an already escaped underscore
        # (``CTRL\_NEW``).  The first escape is source markup, not part of the
        # published protocol identifier.
        .replace(r"\char92{}\char95{}", r"\char95{}")
    )
