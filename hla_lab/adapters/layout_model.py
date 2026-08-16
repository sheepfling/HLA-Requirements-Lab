"""Extract fixed-coordinate LaTeX blocks into a separate layout model."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from hla_lab.core.coercions import optional_float
from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import SourceRef, _commands, _files, _latex_text, _source
from hla_lab.core.source_adapter import LatexSourceProfile


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


class LayoutInventory(BaseModel):
    """Typed aggregate counts for one document's layout model."""

    model_config = ConfigDict(frozen=True)

    document: str
    layout_blocks: int
    nonempty_text_blocks: int
    text_characters: int
    kinds: dict[str, int]


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
        optional_float(x),
        optional_float(y),
        optional_float(width),
        style,
        optional_float(font_size),
        optional_float(line_height),
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


def inventory(root: Path, source: LatexSourceProfile) -> LayoutInventory:
    """Return a compact in-memory inventory suitable for progress checks."""
    blocks = load_layout_model(root, source)
    return LayoutInventory(
        document=root.as_posix(),
        layout_blocks=len(blocks),
        nonempty_text_blocks=sum(bool(item.text) for item in blocks),
        text_characters=sum(len(item.text) for item in blocks),
        kinds={
            kind: sum(item.kind == kind for item in blocks)
            for kind, _ in source.layout_text_block_commands
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="Document source directory")
    parser.add_argument("--json", action="store_true", help="Print the block inventory as JSON")
    args = parser.parse_args()
    result = inventory(args.root.resolve(), HLA_SOURCE)
    if args.json:
        print(result.model_dump_json(indent=2))
    else:
        for key, value in result.model_dump(mode="json").items():
            print(f"{key}: {value}")


if __name__ == "__main__":
    main()
