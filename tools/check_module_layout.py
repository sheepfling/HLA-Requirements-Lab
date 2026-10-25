"""Enforce the repository's module-level public API layout conventions."""

from __future__ import annotations

import argparse
import ast
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from types import EllipsisType

from hla_lab.paths import repository_root

__all__ = ["check_paths", "main"]

DEFAULT_ROOTS = ("hla_lab", "tools", "tests", "topics")


def _is_all_assignment(node: ast.stmt) -> bool:
    if isinstance(node, ast.Assign):
        return any(
            isinstance(target, ast.Name) and target.id == "__all__" for target in node.targets
        )
    if isinstance(node, ast.AnnAssign):
        return isinstance(node.target, ast.Name) and node.target.id == "__all__"
    return (
        isinstance(node, ast.AugAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "__all__"
    )


def _is_module_docstring(node: ast.stmt, *, first: bool) -> bool:
    if not (first and isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)):
        return False
    constant_value: str | bytes | int | float | complex | bool | EllipsisType | None = (
        node.value.value
    )
    return isinstance(constant_value, str)


def _check_file(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignments = [
        (index, node) for index, node in enumerate(tree.body) if _is_all_assignment(node)
    ]
    if not assignments:
        return ()

    errors: list[str] = []
    if len(assignments) > 1:
        lines = ", ".join(str(node.lineno) for _, node in assignments)
        errors.append(f"{path}: __all__ must be assigned once (found lines {lines})")

    all_index, all_node = assignments[0]
    for index, node in enumerate(tree.body[:all_index]):
        statement: ast.stmt = node
        if isinstance(statement, (ast.Import, ast.ImportFrom)) or _is_module_docstring(
            statement, first=index == 0
        ):
            continue
        errors.append(
            f"{path}:{all_node.lineno}: __all__ must follow the module docstring and imports"
        )
        break
    return tuple(errors)


def check_paths(paths: Iterable[Path]) -> tuple[str, ...]:
    """Return module-layout violations for Python files below ``paths``."""

    errors: list[str] = []
    for root in paths:
        candidates = (root,) if root.is_file() else root.rglob("*.py")
        for path in sorted(candidates):
            if "__pycache__" not in path.parts:
                errors.extend(_check_file(path))
    return tuple(errors)


def main(argv: Sequence[str] | None = None) -> int:
    """Check module layout and return a process exit code."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="Repository root")
    parser.add_argument("paths", nargs="*", help="Repository-relative paths to inspect")
    args = parser.parse_args(argv)
    root = repository_root(args.root)
    roots = tuple(root / value for value in (args.paths or DEFAULT_ROOTS))
    errors = check_paths(roots)
    if errors:
        print("Module layout violations:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Module layout checks passed for {len(roots)} roots.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
