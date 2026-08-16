"""Contract tests for the thin CI delegator."""

from __future__ import annotations

from tools import ci


def test_quality_commands_match_the_repository_contract() -> None:
    commands = ci.quality_commands(python="python")

    assert commands[0] == ("python", "-m", "hla_lab.cli", "check", "--json")
    assert any(command[1:3] == ("fmt", "--check") for command in commands)
    assert any(command[1:3] == ("check", ".") for command in commands)
    assert ("python", "-m", "hla_lab.cli", "test", "--parallel") in commands
    assert (
        "python",
        "-m",
        "hla_lab.traceability.api_traceability",
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
        str(ci.HLA_TOPIC),
    ) in commands
    assert commands[-1] == ("git", "diff", "--exit-code")


def test_fix_mode_omits_the_clean_worktree_gate() -> None:
    commands = ci.quality_commands(python="python", fix=True)

    assert ("git", "diff", "--exit-code") not in commands
    assert any("--fix" in command for command in commands)
    assert any(command[1:3] == ("fmt", ".") for command in commands)


def test_release_commands_include_the_full_release_gate() -> None:
    commands = ci.release_commands(python="python")

    assert commands[0][0:3] == ("python", "-m", "hla_lab.diagrams.review_state_machines")
    assert (
        "python",
        "-m",
        "hla_lab.traceability.api_traceability",
        "--check",
        "--require-complete",
        "--json",
    ) in commands
    assert ("python", "-m", "pytest", "tests/integration/test_release_check.py", "-q") in commands
    assert commands[-1] == ("git", "diff", "--exit-code")


def test_main_stops_at_the_first_failed_command(monkeypatch) -> None:
    executed: list[tuple[str, ...]] = []

    def fail_first(command: tuple[str, ...]) -> int:
        executed.append(command)
        return 1

    monkeypatch.setattr(ci, "run_command", fail_first)

    assert ci.main(["quality"]) == 1
    assert len(executed) == 1
