"""The stable command-line interface for the HLA Requirements Lab."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hla_lab.publication.hla_pdf_sniffer import sniff_hla_pdf
from hla_lab.publication.pdf_sniffer import PdfSniffReport
from hla_lab.traceability import semantic_coverage, spec_readiness

from .paths import document_ids, document_roots, repository_root, resources
from .schemas import SCHEMA_NAMES, schema_for, write_schema


def _document_ids(value: Sequence[str] | None) -> tuple[str, ...]:
    return tuple(value or document_ids())


@dataclass(frozen=True, slots=True)
class CheckCommand:
    """Validated options for the ``check`` command."""

    document_ids: tuple[str, ...]
    json_output: bool = False
    require_api_contract: bool = False
    require_concrete: bool = False


@dataclass(frozen=True, slots=True)
class DocumentsCommand:
    """Validated options for the ``documents`` command."""

    document_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TestCommand:
    """Validated options for the ``test`` command."""

    parallel: bool = False
    pytest_args: tuple[str, ...] = ()


DEFAULT_TEST_WORKERS = "4"


def _test_workers() -> str:
    """Return a bounded default while allowing explicit CI tuning."""
    return os.environ.get("HLA_LAB_TEST_WORKERS", DEFAULT_TEST_WORKERS)


def _check(command: CheckCommand) -> int:
    root = repository_root()
    roots = document_roots(root, command.document_ids)
    readiness = spec_readiness.assess_corpus(roots)
    coverage = semantic_coverage.build_report(roots)
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
                "mappings="
                f"planned:{item.planned_mapping_count}/concrete:{item.concrete_mapping_count}"
            )
    if not readiness.specification_ready or not coverage.passed:
        return 1
    if command.require_api_contract and not readiness.api_contract_ready:
        return 1
    if command.require_concrete and not readiness.implementation_ready:
        return 1
    return 0


def _documents(command: DocumentsCommand) -> int:
    root = repository_root()
    registry = resources(root)
    for document_id in command.document_ids:
        path = registry.document(document_id).root
        status = "available" if path.is_dir() else "missing"
        print(f"{document_id}\t{status}\t{path.relative_to(root)}")
    return 0


def _test(command: TestCommand) -> int:
    root = repository_root()
    parallel_root = resources(root).temporary / "pytest-parallel"
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
    return subprocess.run(pytest_command, cwd=root, check=False).returncode


def _delegate(module: str, arguments: Sequence[str]) -> int:
    """Run an owning module behind the stable user-facing command."""
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=repository_root(),
        check=False,
    ).returncode


def _add_check_arguments(command: argparse.ArgumentParser) -> None:
    command.add_argument("--document", action="append", metavar="ID")
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


def _documents_command(args: argparse.Namespace) -> int:
    return _documents(DocumentsCommand(document_ids=_document_ids(args.document)))


def _check_command(args: argparse.Namespace) -> int:
    return _check(
        CheckCommand(
            document_ids=_document_ids(args.document),
            json_output=args.json,
            require_api_contract=args.require_api_contract,
            require_concrete=args.require_concrete,
        )
    )


def _build_command(args: argparse.Namespace) -> int:
    return _delegate("hla_lab.build.build", ("build", args.target))


def _clean_command(_args: argparse.Namespace) -> int:
    return _delegate("hla_lab.build.build", ("clean",))


def _publish_command(args: argparse.Namespace) -> int:
    if args.publication_id is None:
        return _delegate("hla_lab.build.build", ("publication", "list"))
    action = "clean" if args.clean else "build"
    return _delegate(
        "hla_lab.build.build",
        ("publication", action, args.publication_id),
    )


def _quality_command(args: argparse.Namespace) -> int:
    arguments = ("quality", "--fix") if args.fix else ("quality",)
    return _delegate("tools.ci", arguments)


def _schema_command(args: argparse.Namespace) -> int:
    if args.list:
        print("\n".join(SCHEMA_NAMES))
        return 0
    if args.all:
        if args.output_dir is None:
            raise SystemExit("schema --all requires --output-dir")
        for name in SCHEMA_NAMES:
            write_schema(name, args.output_dir / f"{name}.schema.json")
        return 0
    if args.name is None:
        raise SystemExit("schema requires a contract name or --list")
    if args.output is not None:
        write_schema(args.name, args.output)
    else:
        print(json.dumps(schema_for(args.name), ensure_ascii=False, indent=2))
    return 0


def _sniff_pdf_command(args: argparse.Namespace) -> int:
    root = repository_root()

    def rooted(path: Path) -> Path:
        if path.is_absolute():
            return path
        return root / path

    def optional_rooted(path: Path | None) -> Path | None:
        return rooted(path) if path is not None else None

    report = sniff_hla_pdf(
        rooted(args.pdf),
        source_tex=optional_rooted(args.source_tex),
        build_log=optional_rooted(args.build_log),
    )
    _print_pdf_sniff_report(report, json_output=args.json)
    return 0 if report.passed else 1


def _print_pdf_sniff_report(report: PdfSniffReport, *, json_output: bool) -> None:
    if json_output:
        print(report.model_dump_json(indent=2))
        return
    print(f"pages: {report.pages}; links: {report.links}")
    print(f"PDF sniff: {'passed' if report.passed else 'failed'}")
    for finding in report.findings:
        location = f" page {finding.page}" if finding.page is not None else ""
        print(f"{finding.severity.upper()} {finding.code}{location}: {finding.message}")


def _test_command(args: argparse.Namespace) -> int:
    if args.pytest_args[:1] == ["--"]:
        args.pytest_args = args.pytest_args[1:]
    return _test(TestCommand(parallel=args.parallel, pytest_args=tuple(args.pytest_args)))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hla-lab",
        description="Inspect, validate, and test the HLA Requirements Lab corpus.",
        epilog=(
            "Common workflows:\n"
            "  hla-lab --root . status --require-api-contract\n"
            "  hla-lab --root . build\n"
            "  hla-lab --root . publish\n"
            "  hla-lab --root . test --parallel\n"
            "  hla-lab --root . quality"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="explicit corpus workspace root; defaults to HLA_LAB_ROOT",
    )
    subparsers = parser.add_subparsers(dest="command")

    documents = subparsers.add_parser(
        "documents", aliases=("docs",), help="list corpus document roots"
    )
    documents.add_argument("--document", action="append", metavar="ID")
    documents.set_defaults(handler=_documents_command)

    check = subparsers.add_parser(
        "check",
        aliases=("status",),
        help="run the specification-readiness and semantic-coverage gates",
    )
    _add_check_arguments(check)
    check.set_defaults(handler=_check_command)

    build = subparsers.add_parser("build", help="build documents; defaults to all products")
    build.add_argument(
        "target",
        nargs="?",
        default="all",
        help="all, a document path, or a topic path (default: all)",
    )
    build.set_defaults(handler=_build_command)

    clean = subparsers.add_parser("clean", help="remove generated products from all documents")
    clean.set_defaults(command="clean", handler=_clean_command)

    publish = subparsers.add_parser(
        "publish",
        aliases=("publication",),
        help="build a declared publication, or list publications when no ID is given",
    )
    publish.add_argument("publication_id", nargs="?")
    publish.add_argument("--clean", action="store_true", help="clean instead of build")
    publish.set_defaults(handler=_publish_command)

    quality = subparsers.add_parser(
        "quality", aliases=("ci",), help="run the ordered local quality workflow"
    )
    quality.add_argument("--fix", action="store_true", help="allow formatters to rewrite files")
    quality.set_defaults(handler=_quality_command)

    sniff_pdf_command = subparsers.add_parser(
        "sniff-pdf",
        help="scan a generated PDF for text artifacts, collisions, and broken navigation",
    )
    sniff_pdf_command.add_argument("pdf", type=Path)
    sniff_pdf_command.add_argument("--source-tex", type=Path)
    sniff_pdf_command.add_argument("--build-log", type=Path)
    sniff_pdf_command.add_argument("--json", action="store_true")
    sniff_pdf_command.set_defaults(handler=_sniff_pdf_command)

    test = subparsers.add_parser("test", aliases=("tests",), help="run the pytest contract suite")
    test.add_argument(
        "--parallel",
        action="store_true",
        help="run independent test workers via pytest-xdist",
    )
    test.add_argument("pytest_args", nargs=argparse.REMAINDER)
    test.set_defaults(handler=_test_command)

    schema = subparsers.add_parser(
        "schema", help="print or export a JSON Schema generated from a Pydantic model"
    )
    schema.add_argument("name", nargs="?", choices=SCHEMA_NAMES)
    schema.add_argument("--list", action="store_true", help="list available contract names")
    schema.add_argument("--output", type=Path, help="write one generated schema to this path")
    schema.add_argument("--all", action="store_true", help="export every contract schema")
    schema.add_argument("--output-dir", type=Path, help="directory used with --all")
    schema.set_defaults(handler=_schema_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    values = list(argv) if argv is not None else sys.argv[1:]
    if values[:1] == ["test"]:
        args, forwarded = build_parser().parse_known_args(values)
        args.pytest_args.extend(forwarded)
    else:
        args = build_parser().parse_args(values)
    if args.root is not None:
        os.environ["HLA_LAB_ROOT"] = str(args.root.expanduser().resolve())
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 0
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
