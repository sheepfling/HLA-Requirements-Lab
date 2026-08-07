"""Build and clean document recreations from the repository root."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    from scripts.publication_registry import (
        load_publication_registry,
        load_release_manifest,
        publication_projects,
    )
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from publication_registry import (
        load_publication_registry,
        load_release_manifest,
        publication_projects,
    )

ROOT = Path(__file__).resolve().parents[1]
TOPICS = ROOT / "topics"
PUBLICATION_MANIFEST = ROOT / "data" / "publications.json"
RELEASE_MANIFEST = ROOT / "data" / "release" / "documents.json"


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


def publication_targets(identifier: str) -> list[Path]:
    """Resolve one declared publication to its independent document roots."""
    registry = load_publication_registry(PUBLICATION_MANIFEST)
    release_manifest = load_release_manifest(RELEASE_MANIFEST)
    return [
        ROOT / project.root
        for project in publication_projects(registry, release_manifest, identifier)
    ]


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
    publication = subparsers.add_parser(
        "publication",
        help="list, build, or clean an independently declared publication",
    )
    publication.add_argument("action", choices=("list", "build", "clean"))
    publication.add_argument("id", nargs="?")
    args = parser.parse_args()

    if args.command == "list":
        for path in documents():
            print(path.relative_to(ROOT))
        return 0

    if args.command == "publication":
        registry = load_publication_registry(PUBLICATION_MANIFEST)
        if args.action == "list":
            if args.id is not None:
                parser.error("publication list does not accept an ID")
            for item in registry.publications:
                print(f"{item.id}\t{item.kind}\t{item.title}")
            return 0
        if args.id is None:
            parser.error(f"publication {args.action} requires an ID")
        for path in publication_targets(args.id):
            run_document(path, args.action)
        return 0

    action = "build" if args.command == "build" else "clean"
    targets = resolve_targets(args.target) if args.command == "build" else documents()
    for path in targets:
        run_document(path, action)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
