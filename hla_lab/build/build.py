"""Build and clean document recreations from the repository root."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from hla_lab.paths import repository_root, resources
from hla_lab.publication.publication_registry import (
    load_publication_registry,
    load_release_manifest,
    publication_projects,
)


def documents() -> list[Path]:
    """Return every document root declared by the release manifest."""
    workspace = repository_root()
    manifest = load_release_manifest(resources(workspace).release_manifest)
    return [workspace / project.root for project in manifest.projects]


def resolve_targets(value: str) -> list[Path]:
    """Resolve ``all`` or a repository-relative document target."""
    if value.lower() == "all":
        return documents()
    workspace = repository_root()
    target = (workspace / value).resolve()
    if not target.is_dir() or workspace not in target.parents:
        raise SystemExit(f"Invalid target: {value}")
    if (target / "build.py").exists():
        return [target]
    return [path for path in documents() if target in path.parents]


def publication_targets(identifier: str) -> list[Path]:
    """Resolve one declared publication to its independent document roots."""
    workspace = repository_root()
    registry = load_publication_registry(resources(workspace).publications_manifest)
    release_manifest = load_release_manifest(resources(workspace).release_manifest)
    return [
        workspace / project.root
        for project in publication_projects(registry, release_manifest, identifier)
    ]


def run_document(path: Path, action: str) -> None:
    """Run a document-local build entry point."""
    workspace = repository_root()
    manifest = load_release_manifest(resources(workspace).release_manifest)
    relative_root = path.resolve().relative_to(workspace).as_posix()
    project = next(
        item for item in manifest.projects if item.root.replace("\\", "/") == relative_root
    )
    if project.build is None:
        # Fixtures are part of the corpus and must remain discoverable, but
        # they intentionally do not participate in the publication build.
        print(f"[skip {action}] {path.relative_to(workspace)} (no release build settings)")
        return
    print(f"[{action}] {path.relative_to(workspace)}")
    # Keep the shared package importable when the selected topic is outside the
    # repository root.  The old document-local launcher relied on the current
    # directory being on sys.path, which made `build all` fail before the first
    # PDF was compiled even though direct topic builds worked.
    subprocess.run(
        [sys.executable, "-m", "hla_lab.build.topic", action, "--root", str(path)],
        cwd=workspace,
        check=True,
    )


def _configure_workspace(root: Path | None) -> None:
    if root is not None:
        os.environ["HLA_LAB_ROOT"] = str(root.expanduser().resolve())


def main() -> int:
    """Run the repository build command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="explicit corpus workspace root")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("list", help="list discovered documents")
    build = subparsers.add_parser("build", help="build one or more documents")
    build.add_argument("target", help="all, a topic path, or a document path")
    subparsers.add_parser("clean", help="clean every discovered document")
    publication = subparsers.add_parser(
        "publication", help="list, build, or clean an independently declared publication"
    )
    publication.add_argument("action", choices=("list", "build", "clean"))
    publication.add_argument("id", nargs="?")
    args = parser.parse_args()
    _configure_workspace(args.root)
    workspace = repository_root()

    if args.command == "list":
        for path in documents():
            print(path.relative_to(workspace))
        return 0

    if args.command == "publication":
        registry = load_publication_registry(resources(workspace).publications_manifest)
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
