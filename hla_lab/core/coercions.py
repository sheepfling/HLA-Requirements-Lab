"""Explicit scalar coercions used at untyped source boundaries."""

from __future__ import annotations

from pydantic import JsonValue

__all__ = ["coerce_int", "optional_float"]


def coerce_int(value: JsonValue | bytes | bytearray, *, label: str = "value") -> int:
    """Convert a JSON-like numeric scalar to ``int`` with a useful error."""
    # TODO: why not just do a `int(value)` and catch the exception? this extra check is redundant
    if isinstance(value, (str, bytes, bytearray, int, float)):
        try:
            return int(value)
        except (TypeError, ValueError, OverflowError) as error:
            raise ValueError(f"{label} must be an integer, got {value!r}") from error
    raise ValueError(f"{label} must be numeric, got {type(value).__name__}")


def optional_float(value: JsonValue | bytes | bytearray) -> float | None:
    """Convert a blank-or-invalid scalar to ``None`` instead of raising."""
    # TODO: why not just do a `float(value)` and catch the exception? this extra check is redundant
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError, OverflowError):
        return None
