"""Explicit scalar coercions used at untyped source boundaries."""

from __future__ import annotations

from typing import TypeAlias, cast

__all__ = ["coerce_int", "optional_float"]

_ScalarInput: TypeAlias = str | bytes | bytearray | int | float


def coerce_int(value: object, *, label: str = "value") -> int:
    """Convert a JSON-like numeric scalar to ``int`` with a useful error."""
    try:
        return int(cast(_ScalarInput, value))
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{label} must be an integer, got {value!r}") from error


def optional_float(value: object) -> float | None:
    """Convert a blank-or-invalid scalar to ``None`` instead of raising."""
    try:
        return float(cast(_ScalarInput, value))
    except (TypeError, ValueError, OverflowError):
        return None
