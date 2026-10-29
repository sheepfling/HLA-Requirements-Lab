"""Compatibility facade for HLA semantic block generation."""

from __future__ import annotations

import argparse
from pathlib import Path

from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, HLA_SOURCE
from hla_lab.generation.contracts import GenerationRequest, GenerationResult
from hla_lab.generation.semantic_generation import generate as _generate


def generate(
    root: Path,
    output: Path,
    *,
    definition_ids: tuple[str, ...] = (),
    requirement_ids: tuple[str, ...] = (),
    include_outline: bool = False,
) -> GenerationResult:
    """Generate HLA blocks through the generic profile-driven generator."""
    return _generate(
        GenerationRequest(
            root=root,
            output=output,
            source=HLA_SOURCE,
            dialect=HLA_LATEX_DIALECT,
            definition_ids=definition_ids,
            requirement_ids=requirement_ids,
            include_outline=include_outline,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="HLA document source directory")
    parser.add_argument("output", type=Path, help="Ignored generated LaTeX directory")
    parser.add_argument("--definition", dest="definitions", action="append", default=[])
    parser.add_argument("--requirement", dest="requirements", action="append", default=[])
    parser.add_argument("--outline", action="store_true", help="Generate the clause outline")
    args = parser.parse_args()
    generate(
        args.root,
        args.output,
        definition_ids=tuple(args.definitions),
        requirement_ids=tuple(args.requirements),
        include_outline=args.outline,
    )


if __name__ == "__main__":
    main()
