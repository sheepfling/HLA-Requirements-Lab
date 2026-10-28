"""Stable ordering rules for semantic clause identifiers."""

from __future__ import annotations

import re

from hla_lab.core.semantic_types import Clause


def _clause_sort_key(item: Clause) -> tuple[tuple[tuple[int, int | str], ...], int, str]:
    """Sort numeric clauses before annex-like identifiers, stably."""
    parts = re.findall(r"\d+|[A-Za-z]+", item.number)
    number_key = tuple((0, int(part)) if part.isdigit() else (1, part.casefold()) for part in parts)
    return number_key, item.level, item.id
