"""Deterministic file-writing helpers for generated source and JSON."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

__all__ = ["write_json", "write_text"]


def write_text(path: Path, content: str) -> None:
    """Create parent directories and write one normalized trailing newline."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    """Write a JSON-compatible value, including Pydantic model values."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2))
