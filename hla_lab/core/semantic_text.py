"""Shared LaTeX command and prose normalization helpers."""

from __future__ import annotations

import re
from collections.abc import Sequence

from hla_lab.core.parsing import balanced_group
from hla_lab.core.source_adapter import LatexSourceProfile


def _arguments(text: str, start: int, count: int) -> tuple[tuple[str, ...], int] | None:
    cursor = start
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    if cursor < len(text) and text[cursor] == "[":
        _, cursor = balanced_group(text, cursor, "[", "]")
    values: list[str] = []
    for _ in range(count):
        while cursor < len(text) and text[cursor].isspace():
            cursor += 1
        if cursor >= len(text) or text[cursor] != "{":
            return None
        value, cursor = balanced_group(text, cursor)
        values.append(value)
    return tuple(values), cursor


def _commands(text: str, name: str, count: int) -> list[tuple[int, tuple[str, ...]]]:
    return [(offset, args) for offset, args, _ in _command_events(text, name, count)]


def _command_events(text: str, name: str, count: int) -> list[tuple[int, tuple[str, ...], int]]:
    pattern = re.compile(rf"\\{re.escape(name)}\b")
    found: list[tuple[int, tuple[str, ...], int]] = []
    for match in pattern.finditer(text):
        parsed = _arguments(text, match.end(), count)
        if parsed is not None:
            found.append((match.start(), parsed[0], parsed[1]))
    return found


def _environments(text: str, name: str, count: int) -> list[tuple[int, tuple[str, ...], int]]:
    pattern = re.compile(rf"\\begin\{{{re.escape(name)}\}}")
    found: list[tuple[int, tuple[str, ...], int]] = []
    for match in pattern.finditer(text):
        parsed = _arguments(text, match.end(), count)
        if parsed is not None:
            found.append((match.start(), parsed[0], parsed[1]))
    return found


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.casefold()))


def _machine_statement(text: str, source: LatexSourceProfile | None = None) -> str:
    """Normalize a normative statement for machine-facing consumers."""
    normalized = _latex_text(text, source)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def _unwrap_commands(value: str, names: Sequence[str], count: int, body_index: int = 0) -> str:
    pattern = re.compile(rf"\\(?:{'|'.join(map(re.escape, names))})\b")
    replacements: list[tuple[int, int, str]] = []
    for match in pattern.finditer(value):
        parsed = _arguments(value, match.end(), count)
        if parsed is not None:
            replacements.append((match.start(), parsed[1], parsed[0][body_index]))
    for start, end, replacement in reversed(replacements):
        value = value[:start] + replacement + value[end:]
    return value


def _latex_text(value: str, source: LatexSourceProfile | None = None) -> str:
    value = re.sub(r"(?m)^\s*%.*$", "", value)
    value = value.replace(r"\ ", " ")
    value = re.sub(r"\\([&_#$%])", r"\1", value)
    value = value.replace("\\linebreak", " ").replace("\\par", " ")
    value = re.sub(r"\\(?:begin|end)\{[^{}]*\}", " ", value)
    value = re.sub(r"\\(?:addvspace|vspace|hspace)\*?\{[^{}]*\}", " ", value)
    value = re.sub(r"\\item\b", "; ", value)
    wrapper_names = (
        "textit",
        "textbf",
        "texttt",
        "emph",
        *(source.text_wrapper_commands if source is not None else ()),
    )
    note_names = source.text_note_commands if source is not None else ()
    wrapper_commands = "|".join(map(re.escape, wrapper_names))
    note_commands = "|".join(map(re.escape, note_names))
    for _ in range(6):
        previous = value
        value = _unwrap_commands(value, ("resizebox",), 3, 2)
        value = _unwrap_commands(value, ("mbox", "makebox", "hbox"), 1)
        value = _unwrap_commands(
            value,
            wrapper_names,
            1,
        )
        if value == previous:
            break
    value = re.sub(
        rf"\\(?:{wrapper_commands})\{{([^{{}}]*)\}}",
        r"\1",
        value,
    )
    if note_commands:
        value = re.sub(rf"\\(?:{note_commands})\{{([^{{}}]*)\}}", r"\1", value)
    value = re.sub(r"\\[a-zA-Z]+(?:\[[^]]*\])?", "", value)
    value = value.replace("{", "").replace("}", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _definition_text(value: str, source: LatexSourceProfile | None = None) -> str:
    """Extract definition prose while excluding anchors and presentation notes."""
    if source is not None:
        note_commands = "|".join(
            map(
                re.escape,
                (source.definition_note_at, *source.definition_note_commands),
            )
        )
        value = re.split(
            rf"\\(?:{note_commands})\b",
            value,
            maxsplit=1,
        )[0]
        value = re.sub(
            rf"\\(?:{re.escape(source.definition_anchor)}|"
            rf"{re.escape(source.definition_term)})\{{[^{{}}]*\}}",
            "",
            value,
        )
    return _latex_text(value, source).lstrip(": ")
