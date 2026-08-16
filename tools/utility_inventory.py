"""Inventory private helper definitions and report exact duplicate bodies.

Run with ``python -m tools.utility_inventory`` from the repository root.  The
report is intentionally conservative: similar-looking helpers with different
semantics remain visible to a human rather than being declared duplicates by
an overly broad heuristic.
"""

from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

@dataclass(frozen=True)
class HelperDefinition:
    name: str
    path: str
    line: int

@dataclass(frozen=True)
class DuplicateHelper:
    name: str
    locations: tuple[str, ...]

def _python_files(root: Path) -> tuple[Path, ...]:
    paths = [
        path
        for directory in (root / "hla_lab", root / "tools", root / "topics")
        if directory.is_dir()
        for path in directory.rglob("*.py")
        if "__pycache__" not in path.parts
    ]
    return tuple(sorted(paths))

def inventory(root: Path) -> tuple[tuple[HelperDefinition, ...], tuple[DuplicateHelper, ...]]:
    """Return helper definitions and exact duplicate implementation groups."""

    definitions: list[HelperDefinition] = []
    bodies: dict[tuple[str, str], list[str]] = defaultdict(list)
    for path in _python_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            continue
        relative = path.relative_to(root).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("_"):
                continue
            location = f"{relative}:{node.lineno}"
            definitions.append(HelperDefinition(node.name, relative, node.lineno))
            body = ast.dump(node, annotate_fields=False, include_attributes=False)
            bodies[(node.name, body)].append(location)
    duplicates = tuple(
        DuplicateHelper(name=name, locations=tuple(sorted(locations)))
        for (name, _body), locations in sorted(bodies.items())
        if len(locations) > 1
    )
    ordered = tuple(sorted(definitions, key=lambda item: (item.name, item.path, item.line)))
    return ordered, duplicates

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    definitions, duplicates = inventory(args.root.resolve())
    payload = {
        "helper_definition_count": len(definitions),
        "duplicate_implementation_count": len(duplicates),
        "duplicate_implementations": [asdict(item) for item in duplicates],
    }
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"helper definitions: {payload['helper_definition_count']}")
        print(f"exact duplicate implementations: {payload['duplicate_implementation_count']}")
        for item in duplicates:
            print(f"- {item.name}: {', '.join(item.locations)}")
    return 1 if duplicates else 0

if __name__ == "__main__":
    raise SystemExit(main())
