"""Extract fixed-coordinate LaTeX blocks into a separate layout model."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

if __package__:
    from scripts.semantic_model import SourceRef, _commands, _files, _latex_text, _source
    from scripts.source_adapter import LatexSourceProfile
else:
    from semantic_model import SourceRef, _commands, _files, _latex_text, _source
    from source_adapter import LatexSourceProfile


@dataclass(frozen=True)
class LayoutBlock:
    """A layout primitive with its geometry kept separate from semantic text."""

    kind: str
    x: float | None
    y: float | None
    width: float | None
    style: str
    font_size: float | None
    line_height: float | None
    text: str
    source: SourceRef


def _number(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _block(
    root: Path,
    path: Path,
    text: str,
    command: str,
    args: tuple[str, ...],
    offset: int,
    source: LatexSourceProfile,
) -> LayoutBlock:
    if len(args) == 7:
        x, y, width, style, font_size, line_height, body = args
    else:
        x, y, width, body = args
        style = ""
        font_size = ""
        line_height = ""
    return LayoutBlock(
        command,
        _number(x),
        _number(y),
        _number(width),
        style,
        _number(font_size),
        _number(line_height),
        _latex_text(body, source),
        _source(root, path, text, offset),
    )


def load_layout_model(root: Path, source: LatexSourceProfile) -> tuple[LayoutBlock, ...]:
    """Load layout blocks without making their coordinates semantic records."""
    blocks: list[LayoutBlock] = []
    for path in _files(root):
        text = path.read_text(encoding="utf-8")
        for command, argument_count in source.layout_text_block_commands:
            for offset, args in _commands(text, command, argument_count):
                blocks.append(_block(root, path, text, command, args, offset, source))
    return tuple(sorted(blocks, key=lambda item: (item.source.path, item.source.line)))


def inventory(root: Path, source: LatexSourceProfile) -> dict[str, object]:
    """Return a compact in-memory inventory suitable for progress checks."""
    blocks = load_layout_model(root, source)
    return {
        "document": root.as_posix(),
        "layout_blocks": len(blocks),
        "nonempty_text_blocks": sum(bool(item.text) for item in blocks),
        "text_characters": sum(len(item.text) for item in blocks),
        "kinds": {
            kind: sum(item.kind == kind for item in blocks)
            for kind, _ in source.layout_text_block_commands
        },
    }


def main() -> None:
    if __package__:
        from scripts.hla_profile import HLA_SOURCE
    else:
        from hla_profile import HLA_SOURCE

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Document source directory")
    parser.add_argument("--json", action="store_true", help="Print the block inventory as JSON")
    args = parser.parse_args()
    result = inventory(args.root.resolve(), HLA_SOURCE)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
