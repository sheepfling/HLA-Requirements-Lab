"""Replace HLA 1516 page-local definition bodies with generated inputs."""

from __future__ import annotations

import re
from pathlib import Path

from hla_lab.paths import RESOURCES

DEFINITION_PATTERN = re.compile(
    r"\\begin\{hladefinition\}(?:\[[^\]]+\])?\{([^{}]+)\}\{[^{}]+\}"
    r".*?\\end\{hladefinition\}",
    re.DOTALL,
)


def promote(root: Path) -> tuple[Path, ...]:
    """Rewrite definition environments while retaining page order and layout."""
    changed: list[Path] = []
    directory = root / "sections" / "semantic" / "definitions"
    for path in sorted(directory.glob("page-*.tex")):
        original = path.read_text(encoding="utf-8")

        def replacement(match: re.Match[str]) -> str:
            identifier = match.group(1)
            return (
                f"% Generated from Definition record {identifier}; "
                "the page remains a faithful layout adapter.\n"
                f"\\input{{output/semantic/definition-{identifier}}}"
            )

        rewritten = DEFINITION_PATTERN.sub(replacement, original)
        if rewritten != original:
            path.write_text(rewritten, encoding="utf-8")
            changed.append(path)
    return tuple(changed)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=RESOURCES.document("hla-1516-2025").root)
    args = parser.parse_args()
    for path in promote(args.root):
        print(path)
