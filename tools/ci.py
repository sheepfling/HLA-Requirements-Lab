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

from hla_lab.paths import repository_root, resources

__all__ = ["ci_commands", "main", "quality_commands", "release_commands", "run_command"]


def _python(python: str, *arguments: object) -> tuple[str, ...]:
    return (python, *(str(argument) for argument in arguments))


def _tool(name: str) -> str:
    """Resolve installed console tools through the active environment's PATH."""
    return shutil.which(name) or name


def quality_commands(
    python: str = sys.executable,
    *,
    fix: bool = False,
    root: Path | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Return the ordered quality commands used by the quality CI job."""
    workspace = resources(root)
    hla_topic = workspace.document("hla-1516.1-2025").root
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
        _python(python, "-m", "pyright", "--pythonpath", python),
        _python(python, "-m", "compileall", "-q", "hla_lab", "tools", "topics"),
        _python(python, "-m", "hla_lab.build.build", "list"),
        _python(python, "-m", "hla_lab.reports.semantic_metrics", "--json"),
        _python(python, "-m", "hla_lab.reports.semantic_dashboard", "--json"),
        _python(python, "-m", "hla_lab.traceability.semantic_coverage", "--check", "--json"),
        _python(
            python,
            "-m",
            "hla_lab.traceability.api_traceability",
            "--workspace-root",
            workspace.root,
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
            f"{hla_topic}/semantic/federate-lifetime.json",
            "--output",
            ".tmp/ci-state-machines",
            "--format",
            "both",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.export_sequence_diagram",
            f"{hla_topic}/semantic/sequence-diagrams.json",
            "--output",
            ".tmp/ci-sequence-diagrams",
            "--format",
            "both",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.export_graph_diagram",
            f"{hla_topic}/semantic/graph-diagrams.json",
            "--output",
            ".tmp/ci-graph-diagrams",
            "--format",
            "both",
        ),
        _python(
            python,
            "-m",
            "hla_lab.build.topic",
            "generate",
            "--root",
            hla_topic,
            "--skip-assets",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.review_state_machines",
            "--manifest",
            workspace.state_machine_manifest,
            "--models",
            f"{hla_topic}/semantic",
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
            f"{hla_topic}/semantic",
            "--artifacts",
            ".tmp/ci-review-artifacts",
            "--json",
        ),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.diagram_surface_qa",
            "--surface-manifest",
            workspace.diagram_surfaces_manifest,
            "--models",
            f"{hla_topic}/semantic",
            "--generated",
            f"{hla_topic}/output/semantic",
            "--expected-figures",
            "33",
            "--json",
        ),
        _python(python, "-m", "hla_lab.diagrams.rti_diagram_check", hla_topic, "--json"),
        # Tests consume generated semantic table and diagram artifacts. Prepare
        # those outputs above so a clean CI checkout behaves like a built workspace.
        _python(python, "-m", "hla_lab.cli", "test", "--parallel"),
    )
    if not fix:
        commands += (("git", "diff", "--exit-code"),)
    return commands


def release_commands(
    python: str = sys.executable, *, root: Path | None = None
) -> tuple[tuple[str, ...], ...]:
    """Return the ordered document-release commands."""
    workspace = resources(root)
    hla_topic = workspace.document("hla-1516.1-2025").root
    return (
        _python(
            python,
            "-m",
            "hla_lab.diagrams.review_state_machines",
            "--manifest",
            workspace.state_machine_manifest,
            "--models",
            f"{hla_topic}/semantic",
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
            f"{hla_topic}/semantic",
            "--artifacts",
            ".tmp/release-review-artifacts",
            "--require-previews",
            "--json",
        ),
        _python(python, "-m", "hla_lab.build.topic", "generate", "--root", hla_topic),
        _python(
            python,
            "-m",
            "hla_lab.diagrams.diagram_surface_qa",
            "--surface-manifest",
            workspace.diagram_surfaces_manifest,
            "--models",
            f"{hla_topic}/semantic",
            "--generated",
            f"{hla_topic}/output/semantic",
            "--expected-figures",
            "33",
            "--json",
        ),
        _python(python, "-m", "hla_lab.diagrams.rti_diagram_check", hla_topic, "--json"),
        _python(python, "-m", "hla_lab.reports.semantic_dashboard", "--json"),
        _python(
            python,
            "-m",
            "hla_lab.traceability.api_traceability",
            "--workspace-root",
            workspace.root,
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
            workspace.release_manifest,
            "--diagram-manifest",
            workspace.state_machine_manifest,
            "--authority-manifest",
            workspace.authority_manifest,
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
    root: Path | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Return commands for one CI job or the complete local CI sequence."""
    if job == "quality":
        return quality_commands(python, fix=fix, root=root)
    if job == "release":
        if fix:
            raise ValueError("--fix is only supported for the quality job")
        return release_commands(python, root=root)
    if job == "all":
        if fix:
            raise ValueError("--fix is only supported for the quality job")
        return quality_commands(python, root=root) + release_commands(python, root=root)
    raise ValueError(f"unknown CI job: {job}")


def run_command(command: Sequence[str], *, root: Path) -> int:
    """Run one CI command from the repository root and return its exit code."""
    workspace_root = repository_root(root)
    environment = os.environ.copy()
    environment["HLA_LAB_ROOT"] = str(workspace_root)
    try:
        completed = subprocess.run(command, cwd=workspace_root, env=environment, check=False)
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
            "  python -m tools.ci quality --root .\n"
            "  python -m tools.ci quality --fix --root .\n"
            "  python -m tools.ci release --root .\n"
            "  python -m tools.ci all --root ."
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
    parser.add_argument(
        "--root",
        type=Path,
        help="explicit corpus workspace root; defaults to HLA_LAB_ROOT",
    )
    args = parser.parse_args(argv)
    try:
        workspace_root = repository_root(args.root)
        commands = ci_commands(args.job, fix=args.fix, root=workspace_root)
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    for command in commands:
        print(f"$ {shlex.join(command)}", flush=True)
        return_code = run_command(command, root=workspace_root)
        if return_code:
            return return_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
