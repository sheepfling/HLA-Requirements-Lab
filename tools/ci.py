"""Run the repository's CI checks locally and in GitHub Actions."""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from hla_lab.paths import RESOURCES

__all__ = ["ci_commands", "main", "quality_commands", "release_commands", "run_command"]

ROOT = RESOURCES.root
HLA_TOPIC = RESOURCES.document("hla-1516.1-2025").root
SURFACE_MANIFEST = RESOURCES.diagram_surfaces_manifest
STATE_MACHINE_MANIFEST = RESOURCES.state_machine_manifest
AUTHORITY_MANIFEST = RESOURCES.authority_manifest
RELEASE_MANIFEST = RESOURCES.release_manifest

def _python(python: str, *arguments: object) -> tuple[str, ...]:
    return (python, *(str(argument) for argument in arguments))

def _tool(name: str) -> str:
    """Find a console tool in PATH or beside the active Python executable."""
    executable = shutil.which(name)
    if executable is not None:
        return executable
    for suffix in (".exe", ""):
        sibling = Path(sys.executable).with_name(f"{name}{suffix}")
        if sibling.is_file():
            return str(sibling)
    return name

def quality_commands(
    python: str = sys.executable,
    *,
    fix: bool = False,
) -> tuple[tuple[str, ...], ...]:
    """Return the ordered quality commands used by the quality CI job."""
    ruff_check = _python(python, "-m", "ruff", "check")
    if fix:
        ruff_check += ("--fix",)
    ruff_check += ("hla_lab", "tools", "tests", "topics")

    ruff_format = _python(python, "-m", "ruff", "format")
    if not fix:
        ruff_format += ("--check",)
    ruff_format += ("hla_lab", "tools", "tests", "topics")

    rumdl_format = (_tool("rumdl"), "fmt")
    if not fix:
        rumdl_format += ("--check",)
    rumdl_format += (".",)
    rumdl_check = (_tool("rumdl"), "check", ".")

    commands = (
        _python(python, "-m", "hla_lab.cli", "check", "--json"),
        rumdl_format,
        rumdl_check,
        (_tool("mdrepo"), "check", ".", "--format", "github"),
        ruff_check,
        ruff_format,
        _python(python, "-m", "compileall", "-q", "hla_lab", "tools", "topics"),
        _python(python, "-m", "hla_lab.cli", "test", "--parallel"),
        _python(python, "-m", "hla_lab.build.build", "list"),
        _python(python, "-m", "hla_lab.reports.semantic_metrics", "--json"),
        _python(python, "-m", "hla_lab.reports.semantic_dashboard", "--json"),
        _python(python, "-m", "hla_lab.traceability.semantic_coverage", "--check", "--json"),
        _python(
            python,
            "-m",
            "hla_lab.traceability.api_traceability",
            "--check",
            "--require-complete",
            "--json",
        ),
        _python(python, "-m", "hla_lab.traceability.spec_readiness", "--root", "."),
        _python(python, "-m", "tools.check_module_layout"),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.export_state_machine",
            f"{HLA_TOPIC}/semantic/federate-lifetime.json",
            "--output",
            ".tmp/ci-state-machines",
            "--format",
            "both",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.export_sequence_diagram",
            f"{HLA_TOPIC}/semantic/sequence-diagrams.json",
            "--output",
            ".tmp/ci-sequence-diagrams",
            "--format",
            "both",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.export_graph_diagram",
            f"{HLA_TOPIC}/semantic/graph-diagrams.json",
            "--output",
            ".tmp/ci-graph-diagrams",
            "--format",
            "both",
        ),
        _python(python, "-m", "hla_lab.build.topic", "generate", "--root", HLA_TOPIC),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.review_state_machines",
            "--manifest",
            STATE_MACHINE_MANIFEST,
            "--models",
            f"{HLA_TOPIC}/semantic",
            "--reviews",
            ".tmp/ci-reviews",
            "--artifacts",
            ".tmp/ci-review-artifacts",
            "--graphviz",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.diagram_qa",
            "--models",
            f"{HLA_TOPIC}/semantic",
            "--artifacts",
            ".tmp/ci-review-artifacts",
            "--json",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.diagram_surface_qa",
            "--surface-manifest",
            SURFACE_MANIFEST,
            "--models",
            f"{HLA_TOPIC}/semantic",
            "--generated",
            f"{HLA_TOPIC}/output/semantic",
            "--expected-figures",
            "33",
            "--json",
        ),
        _python(python, "-m", "hla_lab.diagrams.rti_diagram_check", HLA_TOPIC, "--json"),
    )
    if not fix:
        commands += (("git", "diff", "--exit-code"),)
    return commands

def release_commands(python: str = sys.executable) -> tuple[tuple[str, ...], ...]:
    """Return the ordered document-release commands."""
    return (
        _python(
            python,
            "-m",
            "hla_lab.diagrams.review_state_machines",
            "--manifest",
            STATE_MACHINE_MANIFEST,
            "--models",
            f"{HLA_TOPIC}/semantic",
            "--reviews",
            ".tmp/release-reviews",
            "--artifacts",
            ".tmp/release-review-artifacts",
            "--graphviz",
            "--compile",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.diagram_qa",
            "--models",
            f"{HLA_TOPIC}/semantic",
            "--artifacts",
            ".tmp/release-review-artifacts",
            "--require-previews",
            "--json",
        ),
        _python(python, "-m", "hla_lab.build.topic", "generate", "--root", HLA_TOPIC),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.diagram_surface_qa",
            "--surface-manifest",
            SURFACE_MANIFEST,
            "--models",
            f"{HLA_TOPIC}/semantic",
            "--generated",
            f"{HLA_TOPIC}/output/semantic",
            "--expected-figures",
            "33",
            "--json",
        ),
        _python(python, "-m", "hla_lab.diagrams.rti_diagram_check", HLA_TOPIC, "--json"),
        _python(python, "-m", "hla_lab.reports.semantic_dashboard", "--json"),
        _python(
            python,
            "-m",
            "hla_lab.traceability.api_traceability",
            "--check",
            "--require-complete",
            "--json",
        ),
        _python(
            python,
            "-m",
            "hla_lab.publication.release_check",
            "--build",
            "--manifest",
            RELEASE_MANIFEST,
            "--diagram-manifest",
            STATE_MACHINE_MANIFEST,
            "--authority-manifest",
            AUTHORITY_MANIFEST,
            "--json",
        ),
        _python(python, "-m", "pytest", "tests/integration/test_release_check.py", "-q"),
        ("git", "diff", "--exit-code"),
    )

def ci_commands(
    job: str = "quality",
    python: str = sys.executable,
    *,
    fix: bool = False,
) -> tuple[tuple[str, ...], ...]:
    """Return commands for one CI job or the complete local CI sequence."""
    if job == "quality":
        return quality_commands(python, fix=fix)
    if job == "release":
        if fix:
            raise ValueError("--fix is only supported for the quality job")
        return release_commands(python)
    if job == "all":
        if fix:
            raise ValueError("--fix is only supported for the quality job")
        return quality_commands(python) + release_commands(python)
    raise ValueError(f"unknown CI job: {job}")

def run_command(command: Sequence[str]) -> int:
    """Run one CI command from the repository root and return its exit code."""
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(ROOT), existing_pythonpath) if path
    )
    try:
        completed = subprocess.run(command, cwd=ROOT, env=environment, check=False)
    except OSError as error:
        print(f"CI command could not start: {shlex.join(command)}: {error}", file=sys.stderr)
        return 1
    return completed.returncode

def main(argv: Sequence[str] | None = None) -> int:
    """Run CI checks in order, stopping at the first failure."""
    parser = argparse.ArgumentParser(
        description="Run the repository's checks in the same order as GitHub Actions.",
        epilog=(
            "Examples:\n"
            "  python -m tools.ci quality\n"
            "  python -m tools.ci quality --fix\n"
            "  python -m tools.ci release\n"
            "  python -m tools.ci all"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "job",
        choices=("quality", "release", "all"),
        nargs="?",
        default="quality",
        help="CI job to run (default: quality)",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="allow Ruff and rumdl to rewrite files during the quality job",
    )
    args = parser.parse_args(argv)
    try:
        commands = ci_commands(args.job, fix=args.fix)
    except ValueError as error:
        parser.error(str(error))
    for command in commands:
        print(f"$ {shlex.join(command)}", flush=True)
        return_code = run_command(command)
        if return_code:
            return return_code
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
