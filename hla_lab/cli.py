"""The stable command-line interface for the HLA Requirements Lab."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console
from rich.table import Table

from hla_lab.traceability import semantic_coverage, spec_readiness

from .paths import document_entry_for_path, document_ids, document_roots, repository_root, resources
from .publication.publication_registry import load_release_manifest
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


def _mapping_records(
    root: Path, filename: str, key: str, workspace: Path, *, required: bool = True
) -> list[Mapping[str, object]] | None:
    path = root / "semantic" / filename
    if not path.is_file():
        if required:
            raise FileNotFoundError(f"missing canonical mapping file {path.relative_to(workspace)}")
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(records, list) or any(not isinstance(record, Mapping) for record in records):
        raise ValueError(f"expected a JSON array named '{key}' in {path.relative_to(workspace)}")
    return records


def _map_command(args: argparse.Namespace) -> int:
    workspace = repository_root()
    try:
        documents = []
        for root in document_roots(workspace, args.document):
            filenames = {
                "requirements": "requirements.json",
                "links": "requirement-links.json",
                "implementations": "implementations.json",
                "api_surfaces": "api-surfaces.json",
                "api_crosswalks": "api-crosswalk.json",
                "api_bindings": "api-requirement-bindings.json",
            }
            records = {
                "requirements": _mapping_records(
                    root, "requirements.json", "requirements", workspace
                ),
                "links": _mapping_records(
                    root, "requirement-links.json", "links", workspace, required=False
                ),
                "implementations": _mapping_records(
                    root, "implementations.json", "implementations", workspace, required=False
                ),
                "api_surfaces": _mapping_records(
                    root, "api-surfaces.json", "api_surfaces", workspace, required=False
                ),
                "api_crosswalks": _mapping_records(
                    root, "api-crosswalk.json", "api_crosswalks", workspace, required=False
                ),
                "api_bindings": _mapping_records(
                    root, "api-requirement-bindings.json", "bindings", workspace, required=False
                ),
            }

            def counts(items):
                return (
                    dict(
                        sorted(
                            Counter(
                                str(item.get("status", "unspecified")) for item in items
                            ).items()
                        )
                    )
                    if items is not None
                    else None
                )

            documents.append(
                {
                    "document": document_entry_for_path(root, workspace).document_id,
                    "root": root.relative_to(workspace).as_posix(),
                    "requirements": len(records["requirements"]),
                    "requirement_links": len(records["links"])
                    if records["links"] is not None
                    else None,
                    "implementations": counts(records["implementations"]),
                    "api_surfaces": len(records["api_surfaces"])
                    if records["api_surfaces"] is not None
                    else None,
                    "api_crosswalks": counts(records["api_crosswalks"]),
                    "requirement_api_bindings": counts(records["api_bindings"]),
                    "semantic_files_present": [
                        f"semantic/{filenames[name]}"
                        for name, items in records.items()
                        if items is not None
                    ],
                    "semantic_files_missing": [
                        f"semantic/{filenames[name]}"
                        for name, items in records.items()
                        if items is None
                    ],
                }
            )
    except (FileNotFoundError, ValueError) as error:
        print(f"Cannot read semantic mapping: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(
            json.dumps(
                {
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
                            "planned and partial are mapping plans, not verified "
                            "implementation evidence"
                        ),
                        "api_crosswalk": (
                            "maps an implementation mapping to an API binding or projection"
                        ),
                        "requirement_api_binding": (
                            "separate requirement-to-language-API relationship"
                        ),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    Console().print(
        "[dim]Planned and partial implementations are mapping plans, not verified implementation "
        "evidence. API crosswalks and requirement-to-API bindings are separate relationships.[/dim]"
    )
    table = Table(title="Semantic mapping overview")
    for column in (
        "Document",
        "Requirements",
        "Req → transitions",
        "Implementation mappings",
        "API surfaces",
        "API crosswalks",
        "Requirement API bindings",
    ):
        table.add_column(
            column,
            justify="right"
            if column in ("Requirements", "Req → transitions", "API surfaces")
            else "left",
        )
    for item in documents:
        table.add_row(
            f"{item['document']} ({item['root']})",
            str(item["requirements"]),
            str(
                item["requirement_links"]
                if item["requirement_links"] is not None
                else "not present"
            ),
            json.dumps(item["implementations"]),
            str(item["api_surfaces"] if item["api_surfaces"] is not None else "not present"),
            json.dumps(item["api_crosswalks"]),
            json.dumps(item["requirement_api_bindings"]),
        )
    Console().print(table)
    for item in documents:
        Console().print(
            f"{item['document']} semantic sources: "
            + (", ".join(item["semantic_files_present"]) or "none")
        )
        if item["semantic_files_missing"]:
            Console().print(
                "  optional mapping files absent: " + ", ".join(item["semantic_files_missing"])
            )
    return 0


def _matrix_command(args: argparse.Namespace) -> int:
    workspace = repository_root()
    project_id = f"hla-rti-compliance-requirements-{args.edition}"
    try:
        project = load_release_manifest(resources(workspace).release_manifest).project(project_id)
    except (FileNotFoundError, ValueError) as error:
        print(f"Cannot resolve matrix project {project_id}: {error}", file=sys.stderr)
        return 2
    if project.build is None or project.build.strategy != "compliance":
        print(
            f"Release project {project_id} is not configured for compliance generation",
            file=sys.stderr,
        )
        return 2
    root = workspace / project.root
    if not root.is_dir():
        print(f"Compliance project root is missing: {root}", file=sys.stderr)
        return 2
    result = _delegate(
        "hla_lab.build.topic", ("generate", "--root", str(root), "--workspace-root", str(workspace))
    )
    if result:
        return result
    output = root / "output" / "compliance"
    expected = (
        output / "compliance-manifest.json",
        output / "compliance-requirements.tex",
        *(
            output / "csv" / name
            for name in (
                "requirements.csv",
                "transitions.csv",
                "implementation-mappings.csv",
                "requirement-mapping-links.csv",
                "transition-mapping-links.csv",
            )
        ),
    )
    missing = [path for path in expected if not path.is_file()]
    if missing:
        print(
            "Generation omitted expected files: "
            + ", ".join(str(p.relative_to(workspace)) for p in missing),
            file=sys.stderr,
        )
        return 1
    print(f"Requirements matrix generated under {output.relative_to(workspace)}")
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
            "  hla-lab --root . map hla-1516.1-2025\n"
            "  hla-lab --root . generate topics/ieee/hla-1516.1-2025\n"
            "  hla-lab --root . matrix --edition 2025\n"
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
    generate.set_defaults(handler=_build_command)

    mapping = subparsers.add_parser("map", help="show semantic requirements and mapping coverage")
    mapping.add_argument("documents", nargs="*", metavar="ID")
    mapping.add_argument("--json", action="store_true")
    mapping.add_argument("--corpus-root", type=Path, help=argparse.SUPPRESS)
    mapping.set_defaults(handler=_map_command)

    matrix = subparsers.add_parser("matrix", help="generate compliance manifest and CSV matrices")
    matrix.add_argument("--edition", choices=("2010", "2025"), default="2025")
    matrix.add_argument("--corpus-root", type=Path, help=argparse.SUPPRESS)
    matrix.set_defaults(handler=_matrix_command)

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
    if args.command == "map":
        args.document = args.documents or None
    if not getattr(args, "command", None):
        build_parser().print_help()
        return 0
    selected_root = args.root or getattr(args, "corpus_root", None)
    if selected_root is None:
        return args.handler(args)
    previous_root = os.environ.get("HLA_LAB_ROOT")
    os.environ["HLA_LAB_ROOT"] = str(selected_root.expanduser().resolve())
    try:
        return args.handler(args)
    finally:
        if previous_root is None:
            os.environ.pop("HLA_LAB_ROOT", None)
        else:
            os.environ["HLA_LAB_ROOT"] = previous_root


if __name__ == "__main__":
    raise SystemExit(main())
