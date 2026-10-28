"""The stable command-line interface for the HLA Requirements Lab."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from hla_lab.traceability.semantic_coverage import build_report
from hla_lab.traceability.spec_readiness import assess_corpus

from .paths import (
    DOCUMENT_IDS,
    REPO_ROOT,
    RESOURCES,
    document_entry_for_path,
    document_roots,
    resources,
)
from .publication.publication_registry import load_release_manifest


def _document_ids(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(value or DOCUMENT_IDS)


@dataclass(frozen=True)
class CheckCommand:
    """Validated options for the ``check`` command."""

    document_ids: tuple[str, ...]
    json_output: bool = False
    require_api_contract: bool = False
    require_concrete: bool = False


@dataclass(frozen=True)
class DocumentsCommand:
    """Validated options for the ``documents`` command."""

    document_ids: tuple[str, ...]


@dataclass(frozen=True)
class MapCommand:
    """Validated options for the ``map`` command."""

    document_ids: tuple[str, ...] | None
    corpus_root: Path
    json_output: bool = False


@dataclass(frozen=True)
class TestCommand:
    """Validated options for the ``test`` command."""

    parallel: bool = False
    pytest_args: tuple[str, ...] = ()


DEFAULT_TEST_WORKERS = "4"
_VERBOSE = False


def _run_process(command: Sequence[str], *, cwd: Path = REPO_ROOT) -> int:
    if _VERBOSE:
        print(f"Running in {cwd}: {shlex.join(command)}", file=sys.stderr)
    return subprocess.run(command, cwd=cwd, check=False).returncode


def _test_workers() -> str:
    """Return a bounded default while allowing explicit CI tuning."""
    return os.environ.get("HLA_LAB_TEST_WORKERS", DEFAULT_TEST_WORKERS)


def _check(command: CheckCommand) -> int:
    roots = document_roots(REPO_ROOT, command.document_ids)
    readiness = assess_corpus(roots)
    coverage = build_report(roots)
    coverage_payload = coverage.model_dump(mode="json")
    payload = {
        "documents": [path.name for path in roots],
        "readiness": readiness.model_dump(mode="json"),
        "coverage": coverage_payload,
    }
    if command.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        coverage_by_document = {item.document: item for item in coverage.documents}
        print(f"documents: {', '.join(payload['documents'])}")
        print(f"specification_ready: {readiness.specification_ready}")
        print(f"api_contract_ready: {readiness.api_contract_ready}")
        print(f"implementation_ready: {readiness.implementation_ready}")
        print(f"coverage: {'passed' if coverage.passed else 'failed'}")
        for item in readiness.documents:
            document_coverage = coverage_by_document[item.document_id]
            transition_counts = document_coverage.transitions.coverage
            requirements_with_verification = item.requirement_count - len(
                item.requirements_without_verification
            )
            print(
                f"{item.document_id}: "
                f"requirements={item.requirement_count} "
                f"(with-verification={requirements_with_verification}), "
                f"transitions={item.transition_count} "
                f"(mapped={transition_counts['mapped']}, "
                f"unclassified={transition_counts['unclassified']}), "
                f"api_surfaces={item.api_surface_count}, "
                f"mappings=planned:{item.planned_mapping_count}/concrete:{item.concrete_mapping_count}"
            )
    if not readiness.specification_ready or not coverage.passed:
        return 1
    if command.require_api_contract and not readiness.api_contract_ready:
        return 1
    if command.require_concrete and not readiness.implementation_ready:
        return 1
    return 0


def _documents(command: DocumentsCommand) -> int:
    for document_id in command.document_ids:
        path = RESOURCES.document(document_id).root
        status = "available" if path.is_dir() else "missing"
        print(f"{document_id}\t{status}\t{path.relative_to(REPO_ROOT)}")
    return 0


def _map(command: MapCommand) -> int:
    """Print the canonical semantic mapping files and their current coverage."""
    try:
        roots = document_roots(command.corpus_root, command.document_ids)
        documents = []
        for root in roots:
            requirements = _mapping_records(
                root, "requirements.json", "requirements", command.corpus_root
            )
            assert requirements is not None
            links = _mapping_records(
                root, "requirement-links.json", "links", command.corpus_root, required=False
            )
            implementations = _mapping_records(
                root,
                "implementations.json",
                "implementations",
                command.corpus_root,
                required=False,
            )
            api_surfaces = _mapping_records(
                root,
                "api-surfaces.json",
                "api_surfaces",
                command.corpus_root,
                required=False,
            )
            api_crosswalks = _mapping_records(
                root,
                "api-crosswalk.json",
                "api_crosswalks",
                command.corpus_root,
                required=False,
            )
            api_bindings = _mapping_records(
                root,
                "api-requirement-bindings.json",
                "bindings",
                command.corpus_root,
                required=False,
            )
            source_records = {
                "requirements.json": requirements,
                "requirement-links.json": links,
                "implementations.json": implementations,
                "api-surfaces.json": api_surfaces,
                "api-crosswalk.json": api_crosswalks,
                "api-requirement-bindings.json": api_bindings,
            }
            documents.append(
                {
                    "document": document_entry_for_path(root, command.corpus_root).document_id,
                    "root": root.relative_to(command.corpus_root).as_posix(),
                    "requirements": len(requirements),
                    "requirement_links": len(links) if links is not None else None,
                    "implementations": (
                        _mapping_status_counts(implementations)
                        if implementations is not None
                        else None
                    ),
                    "api_surfaces": len(api_surfaces) if api_surfaces is not None else None,
                    "api_crosswalks": (
                        _mapping_status_counts(api_crosswalks)
                        if api_crosswalks is not None
                        else None
                    ),
                    "requirement_api_bindings": (
                        _mapping_status_counts(api_bindings) if api_bindings is not None else None
                    ),
                    "semantic_files_present": [
                        f"semantic/{name}"
                        for name, records in source_records.items()
                        if records is not None
                    ],
                    "semantic_files_missing": [
                        f"semantic/{name}"
                        for name, records in source_records.items()
                        if records is None
                    ],
                }
            )
    except (FileNotFoundError, ValueError) as error:
        print(f"Cannot read semantic mapping: {error}", file=sys.stderr)
        return 2

    payload = {
        "documents": documents,
        "semantic_files": [
            "semantic/requirements.json",
            "semantic/requirement-links.json",
            "semantic/implementations.json",
            "semantic/api-surfaces.json",
            "semantic/api-crosswalk.json",
            "semantic/api-requirement-bindings.json",
        ],
        "status_notes": {
            "implementation": (
                "planned and partial are mapping plans, not verified implementation evidence"
            ),
            "api_crosswalk": "maps an implementation mapping to an API binding or projection",
            "requirement_api_binding": "separate requirement-to-language-API relationship",
        },
    }
    if command.json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    console = Console()
    console.print(
        "[dim]Links connect requirements to transitions; implementation mappings describe "
        "seams, API crosswalks map seams to API bindings, and requirement API bindings are "
        "separate. Planned or partial mappings are not verified implementation evidence.[/dim]"
    )
    table = Table(title="Semantic mapping overview")
    table.add_column("Document", style="cyan", no_wrap=True)
    table.add_column("Requirements", justify="right")
    table.add_column("Req → transitions", justify="right")
    table.add_column("Implementation mappings")
    table.add_column("API surfaces", justify="right")
    table.add_column("API crosswalks")
    table.add_column("Requirement API bindings")
    for item in documents:
        table.add_row(
            f"{item['document']} ({item['root']})",
            str(item["requirements"]),
            _format_optional_count(item["requirement_links"]),
            _format_optional_counts(item["implementations"]),
            _format_optional_count(item["api_surfaces"]),
            _format_optional_counts(item["api_crosswalks"]),
            _format_optional_counts(item["requirement_api_bindings"]),
        )
    console.print(table)
    return 0


def _format_counts(values: Mapping[str, int]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.items()) or "none"


def _format_optional_count(value: int | None) -> str:
    return "not present" if value is None else str(value)


def _format_optional_counts(values: Mapping[str, int] | None) -> str:
    return "not present" if values is None else _format_counts(values)


def _mapping_records(
    root: Path,
    filename: str,
    key: str,
    corpus_root: Path = REPO_ROOT,
    *,
    required: bool = True,
) -> list[Mapping[str, object]] | None:
    """Load one canonical JSON array for the read-only mapping overview."""
    path = root / "semantic" / filename
    if not path.is_file():
        if not required:
            return None
        relative = path.relative_to(corpus_root).as_posix()
        raise FileNotFoundError(
            f"missing canonical mapping file {relative}; restore it from the source checkout"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(records, list) or any(not isinstance(record, Mapping) for record in records):
        relative = path.relative_to(corpus_root).as_posix()
        raise ValueError(f"expected a JSON array named '{key}' in {relative}")
    return records


def _mapping_status_counts(records: Sequence[Mapping[str, object]]) -> dict[str, int]:
    return dict(
        sorted(Counter(str(record.get("status", "unspecified")) for record in records).items())
    )


def _matrix(edition: str, corpus_root: Path = REPO_ROOT) -> int:
    """Generate the compliance manifest and normalized CSVs without compiling LaTeX."""
    repository = resources(Path(corpus_root).resolve())
    project_id = f"hla-rti-compliance-requirements-{edition}"
    try:
        release_manifest = load_release_manifest(repository.release_manifest)
        project = release_manifest.project(project_id)
    except FileNotFoundError:
        print(
            f"Cannot generate the {edition} requirements matrix: missing release manifest "
            f"{repository.release_manifest}. Select a corpus root containing data/release/.",
            file=sys.stderr,
        )
        return 2
    except ValueError as error:
        print(
            f"Cannot generate the {edition} requirements matrix from "
            f"{repository.release_manifest}: {error}",
            file=sys.stderr,
        )
        return 2

    if project.build is None or project.build.strategy != "compliance":
        print(
            f"Cannot generate the {edition} requirements matrix: release project {project_id} "
            "does not declare the compliance build strategy.",
            file=sys.stderr,
        )
        return 2

    root = repository.root / project.root
    if not root.is_dir():
        print(
            f"Cannot generate the {edition} requirements matrix: source project is missing at "
            f"{root.relative_to(repository.root)}. Check out the HLA corpus files and retry.",
            file=sys.stderr,
        )
        return 2

    result = _run_process(
        [
            sys.executable,
            "-m",
            "hla_lab.build.topic",
            "generate",
            "--root",
            str(root),
            "--repository-root",
            str(repository.root),
        ],
        cwd=REPO_ROOT,
    )
    if result:
        print(
            f"Matrix generation failed for {edition}; check the compliance profile, release "
            "manifest, and canonical semantic source files named in the error above.",
            file=sys.stderr,
        )
        return result.returncode

    output = root / "output" / "compliance"
    csv_output = output / "csv"
    expected = (
        output / "compliance-manifest.json",
        output / "compliance-requirements.tex",
        csv_output / "requirements.csv",
        csv_output / "transitions.csv",
        csv_output / "implementation-mappings.csv",
        csv_output / "requirement-mapping-links.csv",
        csv_output / "transition-mapping-links.csv",
    )
    missing = tuple(path for path in expected if not path.is_file())
    if missing:
        paths = ", ".join(path.relative_to(repository.root).as_posix() for path in missing)
        print(
            "Matrix generation finished without its expected outputs: "
            f"{paths}. Verify that this is a compliance project in data/release/documents.json.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Requirements matrix generated for {edition} under {output.relative_to(repository.root)}:"
    )
    for path in expected:
        print(f"  {path.relative_to(repository.root).as_posix()}")
    print("This writes the manifest, LaTeX source, and CSVs; it does not run XeLaTeX.")
    return 0


def _build_products(target: str) -> int:
    """Validate a document target, then use the repository's canonical builder."""
    result = _delegate("hla_lab.build.build", ("build", target))
    if result:
        print(
            "PDF generation failed. Check the latexmk error and the document's build/main.log; "
            "verify XeLaTeX, `latexmk`, Graphviz, TeX packages, and the required fonts. "
            "See topics/ieee/hla-1516.2-2025/BUILDING.md for system prerequisites.",
            file=sys.stderr,
        )
    return result


def _test(command: TestCommand) -> int:
    parallel_root = RESOURCES.temporary / "pytest-parallel"
    if command.parallel:
        parallel_root.parent.mkdir(parents=True, exist_ok=True)
    parallel = (
        [
            "-n",
            _test_workers(),
            "--basetemp",
            str(parallel_root),
        ]
        if command.parallel
        else []
    )
    pytest_command = [sys.executable, "-m", "pytest", *parallel, "tests", *command.pytest_args]
    return _run_process(pytest_command)


def _delegate(module: str, arguments: Sequence[str]) -> int:
    """Run an owning module behind the stable user-facing command."""
    return _run_process([sys.executable, "-m", module, *arguments])


def _add_check_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--document", action="append", choices=DOCUMENT_IDS)
    command.add_argument("--json", action="store_true")
    command.add_argument(
        "--require-api-contract",
        action="store_true",
        help="fail unless declared API surfaces are classifiable",
    )
    command.add_argument(
        "--require-concrete",
        action="store_true",
        help="fail unless implementation mappings have concrete evidence",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hla-lab",
        description="Inspect, validate, and test the HLA Requirements Lab corpus.",
        epilog=(
            "Common workflows:\n"
            "  hla-lab map hla-1516.1-2025\n"
            "  hla-lab generate topics/ieee/hla-1516.1-2025\n"
            "  hla-lab matrix --edition 2025\n"
            "  hla-lab status --require-api-contract\n"
            "  hla-lab build\n"
            "  hla-lab publish\n"
            "  hla-lab test --parallel\n"
            "  hla-lab quality"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="print subprocess commands")
    subparsers = parser.add_subparsers(dest="command")

    documents = subparsers.add_parser(
        "documents", aliases=("docs",), help="list corpus document roots"
    )
    documents.add_argument("--document", action="append", choices=DOCUMENT_IDS)

    check = subparsers.add_parser(
        "check",
        aliases=("status",),
        help="run the specification-readiness and semantic-coverage gates",
    )
    _add_check_arguments(check)

    build = subparsers.add_parser("build", help="build documents; defaults to all products")
    build.add_argument(
        "target",
        nargs="?",
        default="all",
        help="all, a document path, or a topic path (default: all)",
    )

    generate = subparsers.add_parser(
        "generate",
        help="regenerate semantic inputs and compile document PDFs (same as build)",
    )
    generate.add_argument(
        "target",
        nargs="?",
        default="all",
        help="all, a document path, or a topic path (default: all)",
    )

    mapping = subparsers.add_parser(
        "map",
        help="show where semantic requirements, implementation mappings, and API links live",
    )
    mapping.add_argument("documents", nargs="*", help="selected corpus document IDs")
    mapping.add_argument("--json", action="store_true", help="print machine-readable JSON")
    mapping.add_argument(
        "--corpus-root",
        type=Path,
        default=REPO_ROOT,
        help="corpus root containing data/ and topics/ (default: this checkout)",
    )

    matrix = subparsers.add_parser(
        "matrix",
        help="generate the compliance manifest and normalized requirements CSV matrix",
    )
    matrix.add_argument(
        "--edition",
        choices=("2010", "2025"),
        default="2025",
        help="HLA corpus edition (default: 2025)",
    )
    matrix.add_argument(
        "--corpus-root",
        type=Path,
        default=REPO_ROOT,
        help="corpus root containing data/ and topics/ (default: this checkout)",
    )

    clean = subparsers.add_parser("clean", help="remove generated products from all documents")
    clean.set_defaults(command="clean")

    publish = subparsers.add_parser(
        "publish",
        aliases=("publication",),
        help="build a declared publication, or list publications when no ID is given",
    )
    publish.add_argument("publication_id", nargs="?")
    publish.add_argument("--clean", action="store_true", help="clean instead of build")

    quality = subparsers.add_parser(
        "quality", aliases=("ci",), help="run the ordered local quality workflow"
    )
    quality.add_argument("--fix", action="store_true", help="allow formatters to rewrite files")

    test = subparsers.add_parser("test", aliases=("tests",), help="run the pytest contract suite")
    test.add_argument(
        "--parallel",
        action="store_true",
        help="run independent test workers via pytest-xdist",
    )
    test.add_argument("pytest_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    global _VERBOSE
    values = list(argv) if argv is not None else sys.argv[1:]
    if values[:1] == ["test"]:
        args, forwarded = build_parser().parse_known_args(values)
        args.pytest_args.extend(forwarded)
    else:
        args = build_parser().parse_args(values)
    _VERBOSE = args.verbose
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 0
    if args.command == "test" and args.pytest_args[:1] == ["--"]:
        args.pytest_args = args.pytest_args[1:]
    if args.command in {"documents", "docs"}:
        return _documents(DocumentsCommand(document_ids=_document_ids(args.document)))
    if args.command in {"check", "status"}:
        return _check(
            CheckCommand(
                document_ids=_document_ids(args.document),
                json_output=args.json,
                require_api_contract=args.require_api_contract,
                require_concrete=args.require_concrete,
            )
        )
    if args.command == "map":
        return _map(
            MapCommand(
                document_ids=tuple(args.documents) or None,
                corpus_root=args.corpus_root,
                json_output=args.json,
            )
        )
    if args.command == "matrix":
        return _matrix(args.edition, args.corpus_root)
    if args.command in {"build", "make", "generate"}:
        return _build_products(args.target)
    if args.command == "clean":
        return _delegate("hla_lab.build.build", ("clean",))
    if args.command in {"publish", "publication"}:
        if args.publication_id is None:
            return _delegate("hla_lab.build.build", ("publication", "list"))
        action = "clean" if args.clean else "build"
        return _delegate("hla_lab.build.build", ("publication", action, args.publication_id))
    if args.command in {"quality", "ci"}:
        arguments = ("quality", "--fix") if args.fix else ("quality",)
        return _delegate("tools.ci", arguments)
    return _test(TestCommand(parallel=args.parallel, pytest_args=tuple(args.pytest_args)))


if __name__ == "__main__":
    raise SystemExit(main())
