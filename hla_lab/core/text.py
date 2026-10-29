"""Shared text, identifier, quoting, and numeric-rendering utilities.

These helpers are deliberately format-oriented and do not know anything about
HLA records.  Semantic extraction and document-family adapters can therefore
share the boring edge-case handling without importing one another.
"""

from __future__ import annotations

import hashlib
import re

__all__ = [
    "dot_quote",
    "format_number",
    "mermaid_text",
    "normalize_whitespace",
    "safe_filename",
    "safe_identifier",
    "slugify",
    "tex_escape",
]

_IDENTIFIER_RE = re.compile(r"[^a-zA-Z0-9]+")
_SLUG_RE = re.compile(r"[^a-z0-9]+")
_FILENAME_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_TEX_SPECIAL_RE = re.compile(r"[\\&#%_${}]")


def normalize_whitespace(value: object) -> str:
    """Return text with line endings and runs of whitespace normalized."""

    return " ".join(str(value).replace("\r", "").split())


def slugify(
    value: object,
    *,
    fallback: str = "record",
    separator: str = "-",
) -> str:
    """Create a stable lower-case, dash-separated slug."""

    slug = _SLUG_RE.sub(separator, str(value).casefold()).strip(separator)
    return slug or fallback


def safe_identifier(
    value: object,
    *,
    prefix: str = "node",
    fallback: str = "node",
) -> str:
    """Create an identifier accepted by DOT, Mermaid, or TikZ node syntax.

    The prefix is omitted when empty, which makes this function suitable for
    both renderer aliases and output filenames.
    """

    safe = _IDENTIFIER_RE.sub("_", str(value)).strip("_") or fallback
    if safe[0].isdigit():
        safe = f"n_{safe}"
    return f"{prefix}_{safe}" if prefix else safe


def safe_filename(value: object, *, max_length: int = 120) -> str:
    """Create a bounded filesystem component while retaining uniqueness."""

    original = str(value)
    safe = _FILENAME_RE.sub("-", original).strip("-")
    if len(safe) <= max_length:
        return safe
    digest = hashlib.sha1(original.encode("utf-8")).hexdigest()[:12]
    return f"{safe[: max_length - 13].rstrip('-')}-{digest}"


def tex_escape(value: object) -> str:
    """Escape plain text for insertion into ordinary LaTeX text."""

    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "#": r"\#",
        "$": r"\$",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return _TEX_SPECIAL_RE.sub(lambda match: replacements[match.group()], str(value))


def mermaid_text(value: object) -> str:
    """Quote-safe one-line text for Mermaid labels."""

    return str(value).replace("\\", "\\\\").replace('"', "'").replace("\n", " ")


def dot_quote(value: object) -> str:
    """Return a Graphviz double-quoted string literal."""

    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace(chr(10), "\\n")
    return f'"{escaped}"'


def format_number(value: float | int, *, precision: int = 3) -> str:
    """Render a diagram coordinate without binary-float noise."""

    rendered = f"{value:.{precision}f}".rstrip("0").rstrip(".")
    return rendered or "0"
