"""HLA Requirements Lab rules layered over the reusable PDF sniffer."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast

import pymupdf

from hla_lab.publication.pdf_sniffer import (
    PdfSniffFinding,
    PdfSniffReport,
    has_internal_link_for_text,
    sniff_pdf,
)

__all__ = ["sniff_hla_pdf"]


_HLA_TEXT_RULES: tuple[
    tuple[str, re.Pattern[str], str, str], ...
] = (
    (
        "renderer-placeholder",
        re.compile(r"@@hlabreak@@"),
        "error",
        "internal line-break placeholder leaked into PDF text",
    ),
    (
        "semantic-id-in-prose",
        re.compile(r"\b(?:requirement-candidate|content-element)-[a-z0-9][a-z0-9-]{20,}\b", re.I),
        "warning",
        "machine-oriented semantic identifier appears in reader-facing text",
    ),
    (
        "table-cell-dump",
        re.compile(r"(?i)cell contents,\s*left to right"),
        "warning",
        "table cells appear to be presented as a flattened source-row dump",
    ),
    (
        "generic-omt-table-family-label",
        re.compile(r"(?i)\bOMT table family\s+[A-Z]\d+\."),
        "warning",
        "a generated machine-oriented OMT family label appears in reader-facing text",
    ),
    (
        "layout-adapter-placeholder",
        re.compile(
            r"(?i)Layout adapter for content-\d+-page-\d+;\s*"
            r"no independent prose surface was present"
        ),
        "error",
        "internal page-adapter placeholder appears in reader-facing text",
    ),
    (
        "nested-brace-residue",
        re.compile(r"\{\s*\{|\}\s*\}"),
        "warning",
        "adjacent nested braces may be leaked HLA source notation",
    ),
    (
        "figure-caption-placeholder",
        re.compile(r"(?i)\bCaption (?:not recorded|unavailable in source data)\b"),
        "error",
        "an unresolved source figure-caption placeholder appears in the PDF",
    ),
    (
        "source-pdf-command-residue",
        re.compile(r"(?i)\b(?:pdf:put|@thispage|hla-empty)\b"),
        "error",
        "a source-PDF layout command or marker appears in reader-facing text",
    ),
)
_PARENTHETICAL_CLAUSE_REFERENCE = re.compile(
    r"\(\s*see(?:\s+also)?\s+(?:Clause\s+|§\s*)?(?P<number>\d+(?:\.\d+)+)\s*\)",
    re.IGNORECASE,
)
_REFERENCE_LIST_FIGURE = re.compile(
    r"^\s*[a-z]\)\s*Figure\s+(?P<number>\d+(?:\.\d+)*)\b",
    re.IGNORECASE,
)
_ALPHA_LIST_ITEM = re.compile(r"^\s*(?P<label>[a-z])\)\s+")
_LIST_INTRODUCTION_ENDINGS = (":", "either")


def _is_list_introduction(line_text: str) -> bool:
    """Recognize visible lead-ins that begin a distinct or nested list."""
    return " ".join(line_text.split()).casefold().endswith(_LIST_INTRODUCTION_ENDINGS)


def _hla_text_findings(text: str, page_number: int) -> list[PdfSniffFinding]:
    findings: list[PdfSniffFinding] = []
    candidates = [text, *text.splitlines()]
    for code, pattern, severity, description in _HLA_TEXT_RULES:
        for candidate in candidates:
            match = pattern.search(candidate)
            if match is None:
                continue
            start = max(0, match.start() - 50)
            end = min(len(candidate), match.end() + 80)
            snippet = " ".join(candidate[start:end].strip().split())[:140]
            findings.append(
                PdfSniffFinding(
                    code=code,
                    severity=severity,
                    page=page_number,
                    message=f"{description}: {snippet}",
                )
            )
            break
    return findings


def _missing_internal_reference_findings(
    page: pymupdf.Page,
    page_number: int,
) -> list[PdfSniffFinding]:
    """Check HLA clause and reference-list figure labels for internal PDF links."""
    text_dict = cast(dict[str, Any], page.get_text("dict"))
    page_links = cast(list[dict[str, Any]], page.get_links())
    findings: list[PdfSniffFinding] = []
    seen: set[str] = set()
    rules = (
        (
            "unlinked-clause-reference",
            _PARENTHETICAL_CLAUSE_REFERENCE,
            "number",
            "clause cross-reference",
        ),
        (
            "unlinked-figure-reference",
            _REFERENCE_LIST_FIGURE,
            "number",
            "figure reference",
        ),
    )
    for block in text_dict.get("blocks", ()):
        for line in block.get("lines", ()):
            line_text = re.sub(
                r"\s+",
                " ",
                " ".join(span["text"] for span in line.get("spans", ())),
            ).strip()
            if not line_text:
                continue
            line_bbox = cast(tuple[float, float, float, float], line["bbox"])
            for code, pattern, group_name, description in rules:
                if code in seen:
                    continue
                for match in pattern.finditer(line_text):
                    number = match.group(group_name)
                    if code == "unlinked-clause-reference" and re.match(
                        r"\s+of\s+IEEE\s+Std\b", line_text[match.end() :], re.IGNORECASE
                    ):
                        continue
                    link_text = "Figure " + number if code == "unlinked-figure-reference" else number
                    if has_internal_link_for_text(page, page_links, link_text, line_bbox):
                        continue
                    label = (
                        "see " + number
                        if code == "unlinked-clause-reference"
                        else "Figure " + number
                    )
                    snippet = " ".join(line_text.split())[:120]
                    findings.append(
                        PdfSniffFinding(
                            code=code,
                            severity="warning",
                            page=page_number,
                            message=f"{description} {label!r} has no internal PDF link: {snippet}",
                        )
                    )
                    seen.add(code)
                    break
    return findings


def _list_label_sequence_findings(page: pymupdf.Page, page_number: int) -> list[PdfSniffFinding]:
    """Warn about repeated labels in one uninterrupted HLA alphabetic list.

    Skipped labels are valid in provisions that replace only selected items
    from an earlier clause, so the PDF alone cannot treat a gap as an error.
    Bold subsection headings and paragraph starts terminate the current list.
    """
    if page.rect.width > page.rect.height:
        return []

    text_dict = cast(dict[str, Any], page.get_text("dict"))
    rows: list[tuple[float, float, float, str, bool]] = []
    for block in text_dict.get("blocks", ()):
        for line in block.get("lines", ()):
            spans = line.get("spans", ())
            line_text = " ".join(span["text"] for span in spans).strip()
            if line_text:
                x0, y0, _x1, y1 = line["bbox"]
                is_bold = any(
                    re.search(r"bold|semibold|demi", span.get("font", ""), re.IGNORECASE)
                    for span in spans
                )
                rows.append((x0, y0, y1, line_text, is_bold))
    rows.sort(key=lambda item: (item[1], item[0]))

    active: list[dict[str, Any]] = []
    anomalies: list[str] = []
    for x0, y0, y1, line_text, is_bold in rows:
        match = _ALPHA_LIST_ITEM.match(line_text)
        for group in active[:]:
            if y0 - group["last_y"] > 45 or (
                (is_bold or match is None)
                and x0 <= group["x"] + 4
            ) or (
                match is None and _is_list_introduction(line_text)
            ) or (
                x0 <= group["x"] + 4
                and not (match is not None and abs(x0 - group["x"]) <= 4)
            ):
                active.remove(group)
            elif x0 > group["x"] + 4:
                group["last_y"] = y1

        if match is None:
            continue

        label = match.group("label").lower()
        group = next((item for item in active if abs(x0 - item["x"]) <= 4), None)
        if group is None:
            active.append({"x": x0, "last": label, "count": 1, "last_y": y1})
            continue

        previous = group["last"]
        if label <= previous and group["count"] >= 2:
            detail = f"restarts from {previous}) to {label})"
            anomalies.append(f"{detail}: {' '.join(line_text.split())[:90]}")
            group["count"] = 1
        else:
            group["count"] += 1
        group["last"] = label
        group["last_y"] = y1

    if not anomalies:
        return []
    examples = "; ".join(anomalies[:3])
    extra = f"; plus {len(anomalies) - 3} more" if len(anomalies) > 3 else ""
    return [
        PdfSniffFinding(
            code="alphabetic-list-sequence",
            severity="warning",
            page=page_number,
            message=(
                "alphabetic list labels skip or restart at the same indentation; "
                f"review list grouping: {examples}{extra}"
            ),
        )
    ]


def _semantic_table_contract_findings(text: str, page_number: int) -> tuple[PdfSniffFinding, ...]:
    """Check that high-risk HLA tables expose their expected semantic structure."""
    normalized = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.casefold()).strip()
    contracts = (
        (
            "mom attribute table",
            (
                "order",
                "transportation",
                "availability",
                "update behavior",
                "data type",
                "attribute",
                "object class",
            ),
        ),
        ("mom object class hierarchy", ("hlaobjectroot",)),
        ("mom interaction class hierarchy", ("hlainteractionroot",)),
        (
            "table 18 mom interaction class definitions table",
            ("interaction class", "parent class", "semantics"),
        ),
        (
            "table 19 mom attribute definitions table",
            ("attribute", "semantics", "class"),
        ),
    )
    findings: list[PdfSniffFinding] = []
    for caption, required_labels in contracts:
        if caption not in normalized:
            continue
        missing = tuple(label for label in required_labels if label not in normalized)
        if missing:
            findings.append(
                PdfSniffFinding(
                    code="semantic-table-layout",
                    severity="error",
                    page=page_number,
                    message=(
                        f"{caption} is missing expected semantic label(s): " + ", ".join(missing)
                    ),
                )
            )
    return tuple(findings)


def _hla_page_check(
    page: pymupdf.Page,
    page_number: int,
    text: str,
) -> Iterable[PdfSniffFinding]:
    return (
        *_hla_text_findings(text, page_number),
        *_missing_internal_reference_findings(page, page_number),
        *_list_label_sequence_findings(page, page_number),
        *_semantic_table_contract_findings(text, page_number),
    )


def sniff_hla_pdf(
    pdf_path: Path,
    *,
    source_tex: Path | None = None,
    build_log: Path | None = None,
) -> PdfSniffReport:
    """Run reusable PDF checks plus HLA Requirements Lab semantic checks."""
    return sniff_pdf(
        pdf_path,
        source_tex=source_tex,
        build_log=build_log,
        page_checks=(_hla_page_check,),
    )
