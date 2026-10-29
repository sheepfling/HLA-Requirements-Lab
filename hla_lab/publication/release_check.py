"""Run full document-release checks against the source-only build outputs."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Literal

import fitz
from pydantic import BaseModel, ConfigDict, Field

from hla_lab.diagrams.state_machine_inventory import StateMachineInventory
from hla_lab.paths import document_roots, repository_root, resources
from hla_lab.publication.hla_pdf_sniffer import sniff_hla_pdf
from hla_lab.publication.pdf_sniffer import PdfSniffReport
from hla_lab.publication.publication_registry import (
    Publication,
    ReleaseManifest,
    ReleaseProject,
    load_publication_registry,
    load_release_manifest,
    publication_projects,
)
from hla_lab.traceability.api_traceability import (
    ApiTraceabilityReport,
)
from hla_lab.traceability.api_traceability import (
    build_report as build_api_traceability_report,
)
from hla_lab.traceability.api_traceability import (
    default_roots as api_traceability_roots,
)
from hla_lab.traceability.semantic_authority import (
    AuthoritySurfaceReport,
    AuthorityValidationReport,
    validate_authority,
)
from hla_lab.traceability.semantic_coverage import (
    CoverageReport,
)
from hla_lab.traceability.semantic_coverage import (
    build_report as build_semantic_coverage,
)


class DiagramReviewReport(BaseModel):
    """Status counts and unresolved diagram review gaps."""

    model_config = ConfigDict(frozen=True)

    available: bool
    path: str | None = None
    statuses: Annotated[Mapping[str, int], Field(default_factory=dict)]
    review_gaps: tuple[str, ...] = ()


class ProjectReleaseReport(BaseModel):
    """PDF, build-log, and source-hygiene result for one release project."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: str
    pdf: str
    log: str
    expected_pages: int | None
    pages: int | None
    log_errors: tuple[str, ...]
    pdf_ignored: bool
    log_ignored: bool
    pdf_sniff: PdfSniffReport | None = None


class AuthorityUnavailableReport(BaseModel):
    """Result shape when a source workspace has no authority manifest."""

    model_config = ConfigDict(frozen=True)

    available: Literal[False] = False
    surfaces: tuple[AuthoritySurfaceReport, ...] = ()
    failures: tuple[str, ...] = ()
    passed: Literal[True] = True


ReleaseAuthorityReport = AuthorityValidationReport | AuthorityUnavailableReport


class ReleaseCheckReport(BaseModel):
    """Complete validated output from the release gate."""

    model_config = ConfigDict(frozen=True)

    manifest: str
    built: bool
    publication: Publication | None
    projects: tuple[ProjectReleaseReport, ...]
    diagram_review: DiagramReviewReport
    semantic_authority: ReleaseAuthorityReport
    semantic_coverage: CoverageReport
    api_traceability: ApiTraceabilityReport
    tracked_generated: tuple[str, ...]
    failures: tuple[str, ...]
    passed: bool


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
REFERENCE_PARTS = frozenset({"prototype-reference"})


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
            or (
                Path(path).suffix in GENERATED_SUFFIXES
                and not REFERENCE_PARTS.intersection(Path(path).parts)
            )
        )
    )


def _ignored(repo_root: Path, relative_path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--quiet", "--", relative_path],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


def _diagram_report(path: Path | None) -> DiagramReviewReport:
    if path is None:
        return DiagramReviewReport(available=False, statuses={})
    manifest = StateMachineInventory.model_validate_json(path.read_text(encoding="utf-8"))
    statuses: dict[str, int] = {}
    for item in manifest.diagrams:
        status = item.status
        statuses[status] = statuses.get(status, 0) + 1
    gaps = [
        item.diagram_id
        for item in manifest.diagrams
        if item.status in {"needs_review", "unmodeled"}
    ]
    return DiagramReviewReport(
        available=True,
        path=path.as_posix(),
        statuses=dict(sorted(statuses.items())),
        review_gaps=tuple(sorted(gaps)),
    )


def _selected_projects(
    manifest: ReleaseManifest,
    *,
    publication_id: str | None,
    publication_registry_path: Path,
) -> tuple[tuple[ReleaseProject, ...], Publication | None]:
    """Return all projects or the explicit membership of one publication."""
    if publication_id is None:
        return manifest.projects, None
    registry = load_publication_registry(publication_registry_path)
    publication = registry.publication(publication_id)
    return (
        publication_projects(registry, manifest, publication_id),
        publication,
    )


def _inspect_project(
    repo_root: Path,
    project: ReleaseProject,
) -> tuple[ProjectReleaseReport, list[str]]:
    root = repo_root / project.root
    pdf = root / project.pdf
    log = root / project.log
    relative_pdf = pdf.relative_to(repo_root).as_posix()
    relative_log = log.relative_to(repo_root).as_posix()
    log_errors = _log_errors(log, strict_layout=project.kind == "faithful")
    pages: int | None = None
    failures: list[str] = []
    pdf_sniff: PdfSniffReport | None = None
    if pdf.is_file():
        with fitz.open(pdf) as document:
            pages = len(document)
        if project.expected_pages is not None and pages != project.expected_pages:
            failures.append(f"{project.id}: expected {project.expected_pages} pages, got {pages}")
        if project.check_pdf_sniff:
            generated_tex = root / "output" / "semantic" / "reflowable.tex"
            pdf_sniff = sniff_hla_pdf(
                pdf,
                source_tex=generated_tex if generated_tex.is_file() else None,
                build_log=log if log.is_file() else None,
            )
            failures.extend(
                f"{project.id}: PDF sniffer {finding.code}"
                f"{f' on page {finding.page}' if finding.page is not None else ''}: "
                f"{finding.message}"
                for finding in pdf_sniff.findings
                if finding.severity == "error"
            )
    else:
        failures.append(f"{project.id}: missing PDF {relative_pdf}")
    failures.extend(log_errors)
    pdf_ignored = _ignored(repo_root, relative_pdf)
    log_ignored = _ignored(repo_root, relative_log)
    if not pdf_ignored:
        failures.append(f"{project.id}: PDF is not ignored by Git: {relative_pdf}")
    if not log_ignored:
        failures.append(f"{project.id}: build log is not ignored by Git: {relative_log}")
    report = ProjectReleaseReport(
        id=project.id,
        kind=project.kind,
        pdf=relative_pdf,
        log=relative_log,
        expected_pages=project.expected_pages,
        pages=pages,
        log_errors=tuple(log_errors),
        pdf_ignored=pdf_ignored,
        log_ignored=log_ignored,
        pdf_sniff=pdf_sniff,
    )
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
) -> ReleaseCheckReport:
    """Build when requested and return typed PDF/log/source-hygiene findings."""
    repo_root = repo_root.resolve()
    repo_resources = resources(repo_root)
    manifest_path = manifest_path.resolve()
    manifest = load_release_manifest(manifest_path)
    if publication_registry_path is None:
        publication_registry_path = repo_resources.publications_manifest
    selected_projects, publication = _selected_projects(
        manifest,
        publication_id=publication_id,
        publication_registry_path=publication_registry_path.resolve(),
    )
    if build:
        _run_build(repo_root, publication_id)

    if authority_manifest is None:
        candidate = repo_resources.authority_manifest
        authority_manifest = candidate if candidate.is_file() else None
    if authority_manifest is None:
        authority_payload: ReleaseAuthorityReport = AuthorityUnavailableReport()
        authority_failures: tuple[str, ...] = ()
    else:
        authority_report = validate_authority(
            document_roots(repo_root),
            authority_manifest.resolve(),
            check_generated=True,
            workspace_root=repo_root,
        )
        authority_payload = authority_report
        authority_failures = authority_report.failures
    semantic_coverage = build_semantic_coverage(document_roots(repo_root))
    api_traceability = build_api_traceability_report(api_traceability_roots(repo_root))

    projects: list[ProjectReleaseReport] = []
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
    return ReleaseCheckReport(
        manifest=manifest_path.relative_to(repo_root).as_posix(),
        built=build,
        publication=publication,
        projects=tuple(projects),
        diagram_review=_diagram_report(
            diagram_manifest.resolve() if diagram_manifest is not None else None
        ),
        semantic_authority=authority_payload,
        semantic_coverage=semantic_coverage,
        api_traceability=api_traceability,
        tracked_generated=tuple(tracked_generated),
        failures=tuple(failures),
        passed=not failures,
    )


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
        print(report.model_dump_json(indent=2))
    else:
        for project in report.projects:
            summary = f"{project.id}: {project.pages} pages"
            if project.pdf_sniff is not None:
                summary += f"; PDF findings={len(project.pdf_sniff.findings)}"
            print(summary)
        print(f"diagram review gaps: {len(report.diagram_review.review_gaps)}")
        print(f"tracked generated outputs: {len(report.tracked_generated)}")
        print(f"release checks: {'passed' if report.passed else 'failed'}")
        for failure in report.failures:
            print(f"failure: {failure}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
