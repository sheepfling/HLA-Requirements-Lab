"""Small parsing primitives shared by LaTeX source adapters."""

from __future__ import annotations

__all__ = ["balanced_group", "balanced_span", "line_number", "try_balanced_group"]

def balanced_group(
    text: str,
    opening: int,
    left: str = "{",
    right: str = "}",
    *,
    skip_whitespace: bool = False,
) -> tuple[str, int]:
    """Read one balanced group and return its body and exclusive end offset.

    A backslash escapes the following character while scanning.  This is the
    common behavior needed by the source adapters for nested LaTeX groups.
    """

    if skip_whitespace:
        while opening < len(text) and text[opening].isspace():
            opening += 1
    if opening >= len(text) or text[opening] != left:
        raise ValueError(f"Expected {left!r} at offset {opening}")
    depth = 0
    escaped = False
    for index in range(opening, len(text)):
        char = text[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == left:
            depth += 1
        elif char == right:
            depth -= 1
            if depth == 0:
                return text[opening + 1: index], index + 1
    raise ValueError(f"Unclosed {left!r} group at offset {opening}")

def try_balanced_group(
    text: str,
    opening: int,
    left: str = "{",
    right: str = "}",
    *,
    skip_whitespace: bool = False,
) -> tuple[str, int] | None:
    """Best-effort counterpart to :func:`balanced_group`."""

    try:
        return balanced_group(
            text,
            opening,
            left,
            right,
            skip_whitespace=skip_whitespace,
        )
    except ValueError:
        return None

def balanced_span(
    text: str,
    opening: int,
    left: str = "{",
    right: str = "}",
    *,
    skip_whitespace: bool = False,
) -> tuple[int, int] | None:
    """Return the body span of a balanced group, excluding delimiters."""

    if skip_whitespace:
        while opening < len(text) and text[opening].isspace():
            opening += 1
    parsed = try_balanced_group(text, opening, left, right)
    if parsed is None:
        return None
    _body, end = parsed
    return opening + 1, end - 1

def line_number(text: str, offset: int) -> int:
    """Return the one-based source line containing an offset."""

    return text.count("\n", 0, offset) + 1
