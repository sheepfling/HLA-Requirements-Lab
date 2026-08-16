"""The stable command-line interface for the HLA Requirements Lab."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass

from hla_lab.traceability.semantic_coverage import build_report
from hla_lab.traceability.spec_readiness import assess_corpus
from .paths import DOCUMENT_IDS, REPO_ROOT, RESOURCES, document_roots

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
class TestCommand:
    """Validated options for the ``test`` command."""

    parallel: bool = False
    pytest_args: tuple[str, ...] = ()

DEFAULT_TEST_WORKERS = "4"

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
    return subprocess.run(pytest_command, cwd=REPO_ROOT, check=False).returncode

def _delegate(module: str, arguments: Sequence[str]) -> int:
    """Run an owning module behind the stable user-facing command."""
    return subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=REPO_ROOT,
        check=False,
    ).returncode

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
            "  hla-lab status --require-api-contract\n"
            "  hla-lab build\n"
            "  hla-lab publish\n"
            "  hla-lab test --parallel\n"
            "  hla-lab quality"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
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
    values = list(argv) if argv is not None else sys.argv[1:]
    if values[:1] == ["test"]:
        args, forwarded = build_parser().parse_known_args(values)
        args.pytest_args.extend(forwarded)
    else:
        args = build_parser().parse_args(values)
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
    if args.command in {"build", "make"}:
        return _delegate("hla_lab.build.build", ("build", args.target))
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
