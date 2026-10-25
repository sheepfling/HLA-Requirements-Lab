"""Run full document-release checks against the source-only build outputs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import fitz
from pydantic import JsonValue

from hla_lab.paths import document_roots, repository_root, resources
from hla_lab.publication.publication_registry import (
    load_publication_registry,
    load_release_manifest,
    publication_projects,
)
from hla_lab.traceability.api_traceability import (
    build_report as build_api_traceability_report,
)
from hla_lab.traceability.api_traceability import (
    default_roots as api_traceability_roots,
)
from hla_lab.traceability.semantic_authority import validate_authority
from hla_lab.traceability.semantic_coverage import build_report as build_semantic_coverage

ERROR_PATTERNS = (
    # TeX diagnostic lines begin with ``! ``. Do not mistake a wrapped math
    # glyph such as ``!$`` in an overfull/underfull box report for a fatal
    # diagnostic.
    re.compile(r"^!(?:\s|$)", re.MULTILINE),
    re.compile(r"Fatal error", re.IGNORECASE),
    re.compile(r"Emergency stop", re.IGNORECASE),
    re.compile(r"Runaway argument", re.IGNORECASE),
    re.compile(r"No pages of output", re.IGNORECASE),
)
LAYOUT_ERROR_PATTERNS = (
    re.compile(r"Overfull \\hbox", re.MULTILINE),
    re.compile(r"Missing character:", re.MULTILINE),
    re.compile(r"headheight.*too small", re.IGNORECASE),
)
GENERATED_SUFFIXES = frozenset(
    {
        ".aux",
        ".bbl",
        ".bcf",
        ".blg",
        ".fdb_latexmk",
        ".fls",
        ".log",
        ".out",
        ".pdf",
        ".run.xml",
        ".synctex.gz",
        ".toc",
        ".xdv",
    }
)
GENERATED_PARTS = frozenset({"build", "dist", "output", ".tmp", "reviews", "review-artifacts"})
SOURCE_BUILD_PATH = ("hla_lab", "build")


def _load_manifest(path: Path) -> dict[str, JsonValue]:
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid release manifest: {path}")
    projects: JsonValue = payload.get("projects")
    if not isinstance(projects, list):
        raise ValueError(f"invalid release manifest: {path}")
    return payload


def _run_build(repo_root: Path, publication_id: str | None = None) -> None:
    command = [sys.executable, "-m", "hla_lab.build.build", "build", "all"]
    if publication_id is not None:
        command = [
            sys.executable,
            "-m",
            "hla_lab.build.build",
            "publication",
            "build",
            publication_id,
        ]
    subprocess.run(
        command,
        cwd=repo_root,
        check=True,
    )


def _log_errors(path: Path, *, strict_layout: bool = False) -> list[str]:
    if not path.is_file():
        return [f"missing log: {path.as_posix()}"]
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    patterns = ERROR_PATTERNS + (LAYOUT_ERROR_PATTERNS if strict_layout else ())
    return [
        f"{path.as_posix()}:{index}: {line.strip()}"
        for index, line in enumerate(lines, start=1)
        if any(pattern.search(line) for pattern in patterns)
    ]


def _tracked_generated(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    tracked = result.stdout.decode("utf-8", errors="replace").split("\0")
    return sorted(
        path
        for path in tracked
        if path
        and (
            (
                Path(path).parts[: len(SOURCE_BUILD_PATH)] != SOURCE_BUILD_PATH
                and GENERATED_PARTS.intersection(Path(path).parts)
            )
            or Path(path).suffix in GENERATED_SUFFIXES
        )
    )


def _ignored(repo_root: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "--", relative_path],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


def _diagram_report(path: Path | None) -> dict[str, JsonValue]:
    if path is None:
        return {"available": False, "statuses": {}, "review_gaps": []}
    payload: JsonValue = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"invalid diagram manifest: {path}")
    raw_diagrams: JsonValue = payload.get("diagrams")
    if not isinstance(raw_diagrams, list):
        raise ValueError(f"invalid diagram manifest: {path}")
    diagrams: list[JsonValue] = raw_diagrams
    diagram_records: list[dict[str, JsonValue]] = []
    statuses: dict[str, int] = {}
    for raw_item in diagrams:
        item: JsonValue = raw_item
        if not isinstance(item, dict):
            raise ValueError(f"invalid diagram manifest row: {path}")
        diagram_records.append(item)
        status = str(item.get("status", "unknown"))
        statuses[status] = statuses.get(status, 0) + 1
    gaps = [
        str(item.get("diagram_id", "unknown"))
        for item in diagram_records
        if item.get("status") in {"needs_review", "unmodeled"}
    ]
    return {
        "available": True,
        "path": path.as_posix(),
        "statuses": dict(sorted(statuses.items())),
        "review_gaps": sorted(gaps),
    }


def _selected_projects(
    manifest: Mapping[str, JsonValue],
    manifest_path: Path,
    *,
    publication_id: str | None,
    publication_registry_path: Path,
) -> tuple[list[dict[str, JsonValue]], dict[str, JsonValue] | None]:
    """Return all projects or the explicit membership of one publication."""
    raw_projects: JsonValue = manifest["projects"]
    if not isinstance(raw_projects, list):
        raise ValueError(f"invalid release manifest: {manifest_path}")
    project_values: list[JsonValue] = raw_projects
    projects: list[dict[str, JsonValue]] = []
    for raw_project in project_values:
        project: JsonValue = raw_project
        if not isinstance(project, dict):
            raise ValueError(f"invalid project entry in release manifest: {manifest_path}")
        projects.append(project)
    if publication_id is None:
        return projects, None
    registry = load_publication_registry(publication_registry_path)
    release_manifest = load_release_manifest(manifest_path)
    publication = registry.publication(publication_id)
    selected_ids = tuple(
        item.id for item in publication_projects(registry, release_manifest, publication_id)
    )
    raw_by_id = {str(item["id"]): item for item in projects}
    return [raw_by_id[identifier] for identifier in selected_ids], publication.model_dump(
        mode="json"
    )


def _inspect_project(
    repo_root: Path,
    project: Mapping[str, JsonValue],
) -> tuple[dict[str, JsonValue], list[str]]:
    root = repo_root / str(project["root"])
    pdf = root / str(project["pdf"])
    log = root / str(project["log"])
    relative_pdf = pdf.relative_to(repo_root).as_posix()
    relative_log = log.relative_to(repo_root).as_posix()
    report: dict[str, JsonValue] = {
        "id": project["id"],
        "kind": project.get("kind", "document"),
        "pdf": relative_pdf,
        "log": relative_log,
        "expected_pages": project.get("expected_pages"),
        "pages": None,
        "log_errors": _log_errors(log, strict_layout=project.get("kind") == "faithful"),
        "pdf_ignored": _ignored(repo_root, relative_pdf),
        "log_ignored": _ignored(repo_root, relative_log),
    }
    failures: list[str] = []
    if pdf.is_file():
        with fitz.open(pdf) as document:
            report["pages"] = len(document)
        expected = project.get("expected_pages")
        if expected is not None and report["pages"] != expected:
            failures.append(f"{project['id']}: expected {expected} pages, got {report['pages']}")
    else:
        failures.append(f"{project['id']}: missing PDF {relative_pdf}")
    failures.extend(report["log_errors"])
    if not report["pdf_ignored"]:
        failures.append(f"{project['id']}: PDF is not ignored by Git: {relative_pdf}")
    if not report["log_ignored"]:
        failures.append(f"{project['id']}: build log is not ignored by Git: {relative_log}")
    return report, failures


def check_release(
    repo_root: Path,
    manifest_path: Path,
    *,
    build: bool = False,
    diagram_manifest: Path | None = None,
    authority_manifest: Path | None = None,
    publication_id: str | None = None,
    publication_registry_path: Path | None = None,
) -> dict[str, JsonValue]:
    """Build when requested and return typed PDF/log/source-hygiene findings."""
    repo_root = repo_root.resolve()
    repo_resources = resources(repo_root)
    manifest_path = manifest_path.resolve()
    manifest = _load_manifest(manifest_path)
    if publication_registry_path is None:
        publication_registry_path = repo_resources.publications_manifest
    selected_projects, publication = _selected_projects(
        manifest,
        manifest_path,
        publication_id=publication_id,
        publication_registry_path=publication_registry_path.resolve(),
    )
    if build:
        _run_build(repo_root, publication_id)

    if authority_manifest is None:
        candidate = repo_resources.authority_manifest
        authority_manifest = candidate if candidate.is_file() else None
    if authority_manifest is None:
        authority_payload: dict[str, JsonValue] = {
            "available": False,
            "surfaces": [],
            "failures": [],
            "passed": True,
        }
        authority_failures: tuple[str, ...] = ()
    else:
        authority_report = validate_authority(
            document_roots(repo_root),
            authority_manifest.resolve(),
            check_generated=True,
        )
        authority_payload = authority_report.model_dump(mode="json")
        authority_failures = authority_report.failures
    semantic_coverage = build_semantic_coverage(document_roots(repo_root))
    api_traceability = build_api_traceability_report(api_traceability_roots(repo_root))

    projects: list[dict[str, JsonValue]] = []
    failures: list[str] = []
    for project in selected_projects:
        project_report, project_failures = _inspect_project(repo_root, project)
        failures.extend(project_failures)
        projects.append(project_report)

    tracked_generated = _tracked_generated(repo_root)
    if tracked_generated:
        failures.append("tracked generated outputs: " + ", ".join(tracked_generated))
    failures.extend(f"semantic authority: {failure}" for failure in authority_failures)
    failures.extend(f"semantic coverage: {failure}" for failure in semantic_coverage.failures)
    failures.extend(f"API traceability: {failure}" for failure in api_traceability.failures)
    return {
        "manifest": manifest_path.relative_to(repo_root).as_posix(),
        "built": build,
        "publication": publication,
        "projects": projects,
        "diagram_review": _diagram_report(
            diagram_manifest.resolve() if diagram_manifest is not None else None
        ),
        "semantic_authority": authority_payload,
        "semantic_coverage": semantic_coverage.model_dump(mode="json"),
        "api_traceability": api_traceability.model_dump(mode="json"),
        "tracked_generated": tracked_generated,
        "failures": failures,
        "passed": not failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        help="Release project manifest",
    )
    parser.add_argument("--diagram-manifest", type=Path)
    parser.add_argument(
        "--authority-manifest",
        type=Path,
        help="Semantic authority manifest",
    )
    parser.add_argument("--publication", help="Check only one publication destination")
    parser.add_argument(
        "--publication-manifest",
        type=Path,
        help="Publication destination registry",
    )
    parser.add_argument("--root", type=Path, help="explicit corpus workspace root")
    parser.add_argument("--build", action="store_true", help="Build every manifest project first")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON")
    args = parser.parse_args()
    repo_root = repository_root(args.root)
    registry_paths = resources(repo_root)
    report = check_release(
        repo_root,
        args.manifest or registry_paths.release_manifest,
        build=args.build,
        diagram_manifest=args.diagram_manifest,
        authority_manifest=args.authority_manifest or registry_paths.authority_manifest,
        publication_id=args.publication,
        publication_registry_path=args.publication_manifest or registry_paths.publications_manifest,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for project in report["projects"]:
            print(f"{project['id']}: {project['pages']} pages")
        print(f"diagram review gaps: {len(report['diagram_review']['review_gaps'])}")
        print(f"tracked generated outputs: {len(report['tracked_generated'])}")
        print(f"release checks: {'passed' if report['passed'] else 'failed'}")
        for failure in report["failures"]:
            print(f"failure: {failure}")
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
