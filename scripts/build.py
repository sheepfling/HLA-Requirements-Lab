"""Build and clean document recreations from the repository root."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "topics"


def documents() -> list[Path]:
    return (
        sorted(
            path.parent
            for path in TOPICS.rglob("build.py")
            if "_template" not in path.parts and len(path.parent.relative_to(TOPICS).parts) == 2
        )
        if TOPICS.exists()
        else []
    )


def resolve_targets(value: str) -> list[Path]:
    if value.lower() == "all":
        return documents()

    target = (ROOT / value).resolve()
    if not target.is_dir() or ROOT not in target.parents:
        raise SystemExit(f"Invalid target: {value}")
    if (target / "build.py").exists():
        return [target]
    return [path for path in documents() if target in path.parents]


def run_document(path: Path, action: str) -> None:
    print(f"[{action}] {path.relative_to(ROOT)}")
    subprocess.run([sys.executable, "build.py", action], cwd=path, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="list discovered documents")
    build = subparsers.add_parser("build", help="build one or more documents")
    build.add_argument("target", help="all, a topic path, or a document path")
    subparsers.add_parser("clean", help="clean every discovered document")
    args = parser.parse_args()

    if args.command == "list":
        for path in documents():
            print(path.relative_to(ROOT))
        return 0

    action = "build" if args.command == "build" else "clean"
    targets = resolve_targets(args.target) if args.command == "build" else documents()
    for path in targets:
        run_document(path, action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
