"""Contract tests for the thin CI delegator."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from tests.support import TEST_REPO_ROOT
from tools import ci


def test_quality_commands_match_the_repository_contract() -> None:
    commands = ci.quality_commands(python="python", root=TEST_REPO_ROOT)

    assert commands[0] == ("python", "-m", "hla_lab.cli", "check", "--json")
    assert any(command[1:3] == ("fmt", "--check") for command in commands)
    assert any(command[1:3] == ("check", ".") for command in commands)
    assert ("python", "-m", "hla_lab.cli", "test", "--parallel") in commands
    assert (
        "python",
        "-m",
        "hla_lab.traceability.api_traceability",
        "--workspace-root",
        str(TEST_REPO_ROOT),
        "--check",
        "--require-complete",
        "--json",
    ) in commands
    assert (
        "python",
        "-m",
        "hla_lab.build.topic",
        "generate",
        "--root",
        str(TEST_REPO_ROOT / "topics/ieee/hla-1516.1-2025"),
    ) in commands
    assert commands[-1] == ("git", "diff", "--exit-code")


def test_fix_mode_omits_the_clean_worktree_gate() -> None:
    commands = ci.quality_commands(python="python", fix=True, root=TEST_REPO_ROOT)

    assert ("git", "diff", "--exit-code") not in commands
    assert any("--fix" in command for command in commands)
    assert any(command[1:3] == ("fmt", ".") for command in commands)


def test_release_commands_include_the_full_release_gate() -> None:
    commands = ci.release_commands(python="python", root=TEST_REPO_ROOT)

    assert commands[0][0:3] == ("python", "-m", "hla_lab.diagrams.review_state_machines")
    assert (
        "python",
        "-m",
        "hla_lab.traceability.api_traceability",
        "--workspace-root",
        str(TEST_REPO_ROOT),
        "--check",
        "--require-complete",
        "--json",
    ) in commands
    assert ("python", "-m", "pytest", "tests/integration/test_release_check.py", "-q") in commands
    assert commands[-1] == ("git", "diff", "--exit-code")


def test_main_stops_at_the_first_failed_command(monkeypatch) -> None:
    executed: list[tuple[str, ...]] = []

    def fail_first(command: tuple[str, ...], *, root: object) -> int:
        executed.append(command)
        assert root == TEST_REPO_ROOT
        return 1

    monkeypatch.setattr(ci, "run_command", fail_first)

    assert ci.main(["quality", "--root", str(TEST_REPO_ROOT)]) == 1
    assert len(executed) == 1


def test_installed_ci_module_shows_help_outside_workspace() -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("HLA_LAB_ROOT", None)
    with tempfile.TemporaryDirectory() as workspace:
        result = subprocess.run(
            [sys.executable, "-m", "tools.ci", "--help"],
            cwd=workspace,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
    assert result.returncode == 0, result.stderr
    assert "--root ROOT" in result.stdout


def test_ci_child_gets_explicit_root_without_pythonpath_injection(monkeypatch) -> None:
    monkeypatch.delenv("PYTHONPATH", raising=False)
    observed: dict[str, object] = {}

    def fake_run(command: object, *, cwd: object, env: dict[str, str], check: bool) -> object:
        observed.update(command=command, cwd=cwd, env=env, check=check)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(ci.subprocess, "run", fake_run)
    assert ci.run_command(("python", "-m", "hla_lab.cli", "check"), root=TEST_REPO_ROOT) == 0
    assert observed["cwd"] == TEST_REPO_ROOT
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert environment["HLA_LAB_ROOT"] == str(TEST_REPO_ROOT)
    assert "PYTHONPATH" not in environment
