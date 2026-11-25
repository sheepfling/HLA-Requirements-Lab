"""Scan generated PDFs for high-confidence text, link, and anchor defects."""

from __future__ import annotations

import argparse
import re
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal, cast

import pymupdf
from pydantic import BaseModel, ConfigDict

__all__ = [
    "PdfPageCheck",
    "PdfSniffFinding",
    "PdfSniffReport",
    "has_internal_link_for_text",
    "sniff_pdf",
]


class PdfSniffFinding(BaseModel):
    """One suspicious artifact or broken PDF navigation item."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: Literal["error", "warning"]
    message: str
    page: int | None = None


class PdfSniffReport(BaseModel):
    """Typed result from a PDF sniffer pass."""

    model_config = ConfigDict(frozen=True)

    pdf: str
    pages: int
    links: int
    findings: tuple[PdfSniffFinding, ...] = ()
    passed: bool


PdfPageCheck = Callable[[pymupdf.Page, int, str], Iterable[PdfSniffFinding]]


_TEXT_RULES: tuple[tuple[str, re.Pattern[str], Literal["error", "warning"], str], ...] = (
    (
        "replacement-character",
        re.compile("\ufffd"),
        "error",
        "replacement character may indicate a failed glyph or encoding repair",
    ),
    (
        "raw-tex-command",
        re.compile(
            r"\\(?:allowbreak|begin|char92|end|hspace|ldots|nolinkurl|textbf|texttt|section)\b"
        ),
        "error",
        "visible TeX command residue",
    ),
    (
        "raw-tex-math-delimiter",
        re.compile(r"\\(?:\(|\[)"),
        "error",
        "visible TeX math delimiter residue",
    ),
    (
        "ellipsis-command-residue",
        re.compile(r"(?i)(?<!\w)\\?ldots\b"),
        "error",
        "ellipsis command appears as plain text",
    ),
    (
        "empty-brackets",
        re.compile(r"(?<!\w)\[\s*\](?!\w)"),
        "warning",
        "empty square brackets may be a leaked source marker",
    ),
    (
        "comment-note-residue",
        re.compile(r"(?i)%\s*NOTE\s*(?:---|[\u2014\u2013-])"),
        "error",
        "TeX comment marker appears before a note",
    ),
    (
        "raw-tex-percent-escape",
        re.compile(r"\\%"),
        "error",
        "visible TeX percent escape residue",
    ),
    (
        "stray-percent-residue",
        re.compile(r"(?<!\d)%"),
        "warning",
        "percent sign is not attached to a numeric percentage",
    ),
    (
        "layout-coordinate-residue",
        re.compile(
            r"\b\d{1,3}\s+\d{1,3}\.\d{1,3}\s+\d{2,3}\s+"
            r"\d{1,2}(?:\.\d{1,2})?\s+\d{1,2}(?:\.\d{1,2})?"
            r"(?:\s+\d{1,2}(?:\.\d{1,2})?)?\s+[A-Z]"
        ),
        "warning",
        "text resembles captured layout coordinates",
    ),
    (
        "nbsp-escape-residue",
        re.compile(r"(?i)\"00A0\b|\\char\s*\"00A0\b"),
        "error",
        "source nonbreaking-space escape appears literally",
    ),
    (
        "source-extraction-marker",
        re.compile(r"(?m)(?<!\S)!\s+(?:[A-Z]\b|<)"),
        "warning",
        "standalone exclamation marker may be extraction residue",
    ),
    (
        "duplicated-list-bullet",
        re.compile(r"(?m)^\s*[•▪●]\s*\d+\)\s+"),
        "warning",
        "a bullet is followed by an already-numbered list label",
    ),
    (
        "empty-alpha-list-item",
        re.compile(r"(?m)^\s*[a-z]\)\s*[.,;:]?\s*$", re.IGNORECASE),
        "warning",
        "alphabetic list marker has no visible item text",
    ),
    (
        "space-before-punctuation",
        re.compile(r"(?<=[\w)\]])[ \t]+[,.;:]"),
        "warning",
        "unexpected space appears before punctuation",
    ),
)
_CODE_SPAN = re.compile(
    r"(?<![\w.])[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*"
    r"\([^()]*\)"
)
_JAVA_DECLARATION_SPAN = re.compile(
    r"\b(?:package\s+[A-Za-z_][A-Za-z0-9_.]*;|"
    r"public\s+final\s+class\s+[A-Za-z_$][A-Za-z0-9_$]*\s+implements\s+"
    r"[A-Za-z_$][A-Za-z0-9_.$]*)"
)


def _has_code_like_span(text: str) -> bool:
    for match in _CODE_SPAN.finditer(text):
        callable_name = match.group(0).split("(", 1)[0]
        arguments = match.group(0).split("(", 1)[1][:-1].strip()
        if re.fullmatch(r"s", arguments, re.IGNORECASE):
            continue
        if (
            "." in callable_name
            or re.search(r"[a-z][A-Z]|[_$0-9]", callable_name)
            or not arguments
            or "," in arguments
            or callable_name.casefold() in {"get", "memcpy"}
        ):
            return True
    return False


_URL_SPAN = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
_ANCHOR = re.compile(r"\\hypertarget\{([^{}]+)\}\{\}")
_LOG_ERRORS = (
    (
        "invalid-tex-character",
        re.compile(r"(?i)Text line contains an invalid character"),
        "TeX rejected a character in generated document content",
    ),
    (
        "latex-error",
        re.compile(r"(?m)^!(?: LaTeX| Package .+ Error:| Emergency stop)"),
        "LaTeX reported a compilation error",
    ),
    (
        "duplicate-pdf-destination",
        re.compile(r"xdvipdfmx:warning: Object @.* already defined", re.IGNORECASE),
        "PDF destination was emitted more than once",
    ),
    (
        "out-of-page-annotation",
        re.compile(r"Annotation out of page boundary", re.IGNORECASE),
        "PDF link annotation extends beyond its page",
    ),
)
_LOG_WARNINGS = (
    (
        "missing-font-character",
        re.compile(r"(?m)Missing character: There is no .+? in font .+"),
        "TeX could not render a character in the selected font",
    ),
)
_OVERFULL_BOX = re.compile(
    r"(?i)Overfull \\(?P<direction>[hv])box "
    r"\((?P<amount>[\d.]+)pt too (?:wide|high)\) in "
    r"(?P<context>paragraph|alignment) at lines "
    r"(?P<start>\d+)--(?P<end>\d+)"
)


def _overfull_box_finding(log_text: str) -> PdfSniffFinding | None:
    """Summarize overfull boxes with their largest widths and generated-source lines."""
    matches = tuple(_OVERFULL_BOX.finditer(log_text))
    if not matches:
        return None
    largest = sorted(matches, key=lambda match: float(match.group("amount")), reverse=True)[:5]
    examples = "; ".join(
        f"{match.group('amount')} pt at lines {match.group('start')}-{match.group('end')} "
        f"({match.group('context')})"
        for match in largest
    )
    maximum = float(largest[0].group("amount"))
    return PdfSniffFinding(
        code="overfull-tex-box",
        severity="warning",
        message=(
            f"TeX reported {len(matches)} overfull box(es); maximum overflow "
            f"{maximum:.2f} pt. Largest locations: {examples}"
        ),
    )


def _add_page_text_findings(
    text: str,
    page_number: int,
    findings: list[PdfSniffFinding],
    seen: set[tuple[str, int | None]],
) -> None:
    lines = text.splitlines()
    candidates = [text, *lines]
    for code, pattern, severity, description in _TEXT_RULES:
        for candidate in candidates:
            match = pattern.search(candidate)
            if match is None:
                continue
            key = (code, page_number)
            if key not in seen:
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
                seen.add(key)
            break

    for line in lines:
        stripped = line.strip()
        if stripped == "%" or (stripped.endswith("%") and not re.search(r"\d%$", stripped)):
            key = ("line-final-percent", page_number)
            if key not in seen:
                findings.append(
                    PdfSniffFinding(
                        code=key[0],
                        severity="warning",
                        page=page_number,
                        message=f"line ends in a percent sign: {' '.join(stripped.split())[:140]}",
                    )
                )
                seen.add(key)
            break


def _overlap_examples(page: pymupdf.Page) -> tuple[int, tuple[str, ...]]:
    """Find materially intersecting words sharing the same text line."""
    word_records = cast(
        Iterable[tuple[float, float, float, float, str]],
        page.get_text("words"),
    )
    words = sorted(word_records, key=lambda item: (item[0], item[1]))
    active: list[tuple[float, float, float, float, str]] = []
    overlaps = 0
    examples: list[str] = []
    for word in words:
        x0, y0, x1, y1, text = word[:5]
        word_height = max(y1 - y0, 0.1)
        active = [other for other in active if other[2] > x0 + 0.5]
        for other in active:
            ox0, oy0, ox1, oy1, other_text = other
            vertical_overlap = min(y1, oy1) - max(y0, oy0)
            other_height = max(oy1 - oy0, 0.1)
            if vertical_overlap / min(word_height, other_height) < 0.7:
                continue
            horizontal_overlap = min(x1, ox1) - max(x0, ox0)
            if horizontal_overlap < 2:
                continue
            if horizontal_overlap / min(max(x1 - x0, 0.1), max(ox1 - ox0, 0.1)) < 0.2:
                continue
            overlaps += 1
            if len(examples) < 3:
                examples.append(f"{other_text!r} / {text!r}")
        active.append((x0, y0, x1, y1, text))
    return overlaps, tuple(examples)


def _duplicate_table_headers(page: pymupdf.Page) -> tuple[str, ...]:
    """Flag repeated bold labels near a table caption for semantic review."""
    text_dict = cast(dict[str, Any], page.get_text("dict"))
    spans = [
        span
        for block in text_dict.get("blocks", ())
        for line in block.get("lines", ())
        for span in line.get("spans", ())
    ]
    captions = [
        span for span in spans if re.search(r"\bTABLE\s+\d+\b", span["text"], re.IGNORECASE)
    ]
    findings: list[str] = []
    for caption in captions:
        caption_y = caption["bbox"][1]
        candidates: dict[tuple[str, int], list[tuple[float, float]]] = defaultdict(list)
        for span in spans:
            x0, y0, x1, _y1 = span["bbox"]
            text = re.sub(r"\s+", " ", span["text"]).strip()
            if not (
                caption_y <= y0 <= caption_y + 120
                and re.search(r"bold|semibold|demi", span["font"], re.IGNORECASE)
            ):
                continue

            # A wrapped header such as "OMT component clause" is emitted as
            # separate PDF text spans. Include same-column continuation lines
            # before comparing labels, or the prefix can look like a duplicate.
            continuation_y = span["bbox"][3]
            for _ in range(3):
                continuations = [
                    candidate
                    for candidate in spans
                    if abs(candidate["bbox"][0] - x0) <= 1.5
                    and -0.5 <= candidate["bbox"][1] - continuation_y <= 5
                    and re.search(r"bold|semibold|demi", candidate["font"], re.IGNORECASE)
                    and candidate["font"] == span["font"]
                    and candidate["text"].strip()
                ]
                if not continuations:
                    break
                continuation = min(continuations, key=lambda item: item["bbox"][1])
                text = f"{text} {continuation['text'].strip()}"
                continuation_y = continuation["bbox"][3]

            key = re.sub(r"[^a-z0-9]+", "", text.casefold())
            if len(key) >= 8:
                candidates[(key, round(y0 / 2))].append((x0, x1))
        for (key, _line), positions in candidates.items():
            ordered = sorted(positions)
            if len(ordered) < 2:
                continue
            if any(
                right_x0 - left_x1 > 100
                for (_left_x0, left_x1), (right_x0, _right_x1) in pairwise(ordered)
            ):
                findings.append(key)
    return tuple(sorted(set(findings)))


def has_internal_link_for_text(
    page: pymupdf.Page,
    page_links: Iterable[dict[str, Any]],
    query: str,
    line_bbox: tuple[float, float, float, float],
) -> bool:
    """Return whether a text label is covered by a same-document PDF link."""
    text_rects = page.search_for(query, clip=pymupdf.Rect(line_bbox))
    internal_links = tuple(
        pymupdf.Rect(link["from"])
        for link in page_links
        if link.get("kind") in {pymupdf.LINK_GOTO, pymupdf.LINK_NAMED}
        and link.get("page") is not None
        and link.get("from") is not None
    )
    for text_rect in text_rects:
        text_area = max(text_rect.get_area(), 0.01)
        for link_rect in internal_links:
            overlap = text_rect & link_rect
            if not overlap.is_empty and overlap.get_area() / text_area >= 0.5:
                return True
    return False


def sniff_pdf(
    pdf_path: Path,
    *,
    source_tex: Path | None = None,
    build_log: Path | None = None,
    page_checks: Iterable[PdfPageCheck] = (),
) -> PdfSniffReport:
    """Inspect visible text, PDF links, and optional generated-source anchors.

    The sniffer reports likely text artifacts as warnings when valid prose can
    resemble the pattern. Broken glyphs, raw TeX, overlapping text, invalid
    destinations, and out-of-page content or links are errors. Visual review
    remains necessary for semantic column meaning and overall hierarchy.
    """

    pdf_path = pdf_path.resolve()
    page_checks = tuple(page_checks)
    findings: list[PdfSniffFinding] = []
    seen: set[tuple[str, int | None]] = set()
    link_count = 0
    with pymupdf.open(pdf_path) as document:
        page_count = len(document)
        for page_index in range(page_count):
            page = document.load_page(page_index)
            page_number = page_index + 1
            page_text = cast(str, page.get_text("text"))
            _add_page_text_findings(page_text, page_number, findings, seen)
            for page_check in page_checks:
                findings.extend(page_check(page, page_number, page_text))
            bounds = page.rect
            outside_words = 0
            outside_example: str | None = None
            for word in cast(
                Iterable[tuple[float, float, float, float, str]],
                page.get_text("words"),
            ):
                x0, y0, x1, y1, token = word[:5]
                if (
                    x0 < bounds.x0 - 0.5
                    or y0 < bounds.y0 - 0.5
                    or x1 > bounds.x1 + 0.5
                    or y1 > bounds.y1 + 0.5
                ):
                    outside_words += 1
                    outside_example = outside_example or token
            if outside_words:
                findings.append(
                    PdfSniffFinding(
                        code="text-outside-page",
                        severity="error",
                        page=page_number,
                        message=(
                            f"{outside_words} word box(es) extend beyond the page; "
                            f"first: {outside_example!r}"
                        ),
                    )
                )

            overlap_count, overlap_examples = _overlap_examples(page)
            if overlap_count >= 2:
                findings.append(
                    PdfSniffFinding(
                        code="overlapping-text",
                        severity="error",
                        page=page_number,
                        message=(
                            f"{overlap_count} same-line word box overlaps; "
                            f"examples: {', '.join(overlap_examples)}"
                        ),
                    )
                )

            duplicate_headers = _duplicate_table_headers(page)
            if duplicate_headers:
                findings.append(
                    PdfSniffFinding(
                        code="repeated-table-header",
                        severity="warning",
                        page=page_number,
                        message=(
                            "repeated bold table heading(s) appear in separate columns; "
                            f"review: {', '.join(duplicate_headers[:5])}"
                        ),
                    )
                )

            page_links = cast(list[dict[str, Any]], page.get_links())
            unlinked_url_seen = False
            text_dict = cast(dict[str, Any], page.get_text("dict"))
            for block in text_dict.get("blocks", ()):
                for line in block.get("lines", ()):
                    for span in line.get("spans", ()):
                        if _URL_SPAN.search(span["text"]):
                            span_rect = pymupdf.Rect(span["bbox"])
                            has_uri_link = any(
                                link.get("kind") == pymupdf.LINK_URI
                                and link.get("from") is not None
                                and pymupdf.Rect(link["from"]).intersects(span_rect)
                                for link in page_links
                            )
                            if not has_uri_link and not unlinked_url_seen:
                                findings.append(
                                    PdfSniffFinding(
                                        code="unlinked-url",
                                        severity="warning",
                                        page=page_number,
                                        message=(
                                            "visible URL has no PDF hyperlink: "
                                            f"{span['text'][:120]}"
                                        ),
                                    )
                                )
                                unlinked_url_seen = True
                        if not (
                            _has_code_like_span(span["text"])
                            or _JAVA_DECLARATION_SPAN.search(span["text"])
                        ):
                            continue
                        if re.search(r"mono|typewriter|courier|cmtt", span["font"], re.IGNORECASE):
                            continue
                        findings.append(
                            PdfSniffFinding(
                                code="code-not-monospace",
                                severity="warning",
                                page=page_number,
                                message=(
                                    f"code-like text uses font {span['font']}: {span['text'][:120]}"
                                ),
                            )
                        )

            for link in page_links:
                link_count += 1
                rect = link.get("from")
                if rect is not None and (
                    rect.x0 < bounds.x0 - 0.5
                    or rect.y0 < bounds.y0 - 0.5
                    or rect.x1 > bounds.x1 + 0.5
                    or rect.y1 > bounds.y1 + 0.5
                ):
                    findings.append(
                        PdfSniffFinding(
                            code="link-outside-page",
                            severity="error",
                            page=page_number,
                            message=f"link rectangle extends beyond the page: {rect}",
                        )
                    )
                target_page = link.get("page")
                if (
                    link.get("kind") in {pymupdf.LINK_GOTO, pymupdf.LINK_NAMED}
                    and target_page is not None
                    and not 0 <= target_page < page_count
                ):
                    findings.append(
                        PdfSniffFinding(
                            code="invalid-link-destination",
                            severity="error",
                            page=page_number,
                            message=f"link targets missing zero-based PDF page {target_page}",
                        )
                    )

    if source_tex is not None:
        source_tex = source_tex.resolve()
        if not source_tex.is_file():
            findings.append(
                PdfSniffFinding(
                    code="missing-source-tex",
                    severity="error",
                    message=f"generated TeX source does not exist: {source_tex}",
                )
            )
        else:
            anchors = _ANCHOR.findall(source_tex.read_text(encoding="utf-8", errors="replace"))
            duplicates = sorted(
                (target, count) for target, count in Counter(anchors).items() if count > 1
            )
            if duplicates:
                examples = ", ".join(f"{target} ({count}x)" for target, count in duplicates[:5])
                findings.append(
                    PdfSniffFinding(
                        code="duplicate-semantic-anchor",
                        severity="error",
                        message=(
                            f"{len(duplicates)} semantic destinations are repeated; "
                            f"examples: {examples}"
                        ),
                    )
                )

    if build_log is not None:
        build_log = build_log.resolve()
        if not build_log.is_file():
            findings.append(
                PdfSniffFinding(
                    code="missing-build-log",
                    severity="warning",
                    message=f"build log does not exist: {build_log}",
                )
            )
        else:
            log_text = build_log.read_text(encoding="utf-8", errors="replace")
            for code, pattern, description in _LOG_ERRORS:
                matches = pattern.findall(log_text)
                if matches:
                    findings.append(
                        PdfSniffFinding(
                            code=code,
                            severity="error",
                            message=f"{description} ({len(matches)} log occurrence(s))",
                        )
                    )
            for code, pattern, description in _LOG_WARNINGS:
                matches = pattern.findall(log_text)
                if matches:
                    findings.append(
                        PdfSniffFinding(
                            code=code,
                            severity="warning",
                            message=f"{description} ({len(matches)} log occurrence(s))",
                        )
                    )
            overfull_finding = _overfull_box_finding(log_text)
            if overfull_finding is not None:
                findings.append(overfull_finding)

    return PdfSniffReport(
        pdf=pdf_path.as_posix(),
        pages=page_count,
        links=link_count,
        findings=tuple(findings),
        passed=not any(item.severity == "error" for item in findings),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--source-tex", type=Path)
    parser.add_argument("--build-log", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = sniff_pdf(args.pdf, source_tex=args.source_tex, build_log=args.build_log)
    if args.json:
        print(report.model_dump_json(indent=2))
    else:
        print(f"pages: {report.pages}; links: {report.links}")
        print(f"PDF sniff: {'passed' if report.passed else 'failed'}")
        for finding in report.findings:
            location = f" page {finding.page}" if finding.page is not None else ""
            print(f"{finding.severity.upper()} {finding.code}{location}: {finding.message}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
