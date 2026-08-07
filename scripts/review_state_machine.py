"""Build a visual-review packet for a canonical state-machine record."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

if __package__:
    from .export_state_machine import render_dot, render_mermaid
    from .render_state_machine import _machine, render
    from .semantic_model import StateMachine
else:  # pragma: no cover - direct script execution
    from export_state_machine import render_dot, render_mermaid
    from render_state_machine import _machine, render
    from semantic_model import StateMachine


def _wrapper(machine_tex: str, title: str) -> str:
    return f"""\\documentclass[tikz,border=8pt]{{standalone}}
\\usepackage{{tikz}}
\\usetikzlibrary{{arrows.meta,calc,positioning}}
\\title{{{title}}}
\\begin{{document}}
{machine_tex}
\\end{{document}}
"""


def _run(command: list[str], cwd: Path, timeout: int, *, env: dict[str, str] | None = None) -> None:
    subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
    )


def _executable(path: str | Path) -> str:
    """Prefer native executables when a Windows command shim was supplied."""
    candidate = Path(path)
    if candidate.suffix.casefold() == ".cmd":
        native = candidate.with_suffix(".exe")
        if native.is_file():
            return str(native)
    return str(candidate)


def _review_record(
    machine: dict[str, Any],
    semantic_source: str,
    source_image: str,
    artifact_dir: Path,
    compile_note: str,
) -> str:
    machine_id = machine["id"]
    return f"""# Review: `{machine_id}`

## Provenance

- Source image: `{source_image}`
- Semantic source: `{semantic_source}`
- Generated TikZ: `{artifact_dir.as_posix()}/machine.tex`
- Generated Graphviz: `{artifact_dir.as_posix()}/machine.dot`
- Generated Mermaid: `{artifact_dir.as_posix()}/machine.mmd`
- Rendered preview: `{artifact_dir.as_posix()}/preview.png`

## Review status

- Status: `draft`
- Semantic transcription complete: [ ]
- All visible states represented: [ ]
- All visible transitions represented: [ ]
- Labels and direction verified: [ ]
- Nested/composite regions verified: [ ]
- Generated preview compared with source: [ ]
- Accepted: [ ]

{compile_note}

## Findings

    Record visual differences, uncertain labels, omitted details, or deliberate
semantic/layout choices here.
"""


def _merge_review_record(generated: str, previous: str) -> str:
    """Refresh generated provenance/compile fields without erasing review decisions."""
    if "## Review status\n" not in previous or "## Findings\n" not in previous:
        return generated
    generated_prefix, generated_status = generated.split("## Review status\n", 1)
    generated_status = generated_status.split("## Findings\n", 1)[0]
    previous_status = previous.split("## Review status\n", 1)[1].split("## Findings\n", 1)[0]
    previous_findings = previous.split("## Findings\n", 1)[1]
    compile_lines = [
        line for line in generated_status.splitlines() if line.startswith("Preview compilation")
    ]
    preserved_status = [
        line for line in previous_status.splitlines() if not line.startswith("Preview compilation")
    ]
    preserved_status = "\n".join(preserved_status).rstrip()
    if compile_lines:
        preserved_status += "\n\n" + "\n".join(compile_lines)
    return (
        generated_prefix
        + "## Review status\n"
        + preserved_status
        + "\n\n## Findings\n"
        + previous_findings.rstrip()
        + "\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Canonical state-machine JSON")
    parser.add_argument("--source-image", required=True, help="Repository-relative source image")
    parser.add_argument("--machine", help="Machine ID when the source contains multiple machines")
    parser.add_argument(
        "--artifacts", type=Path, required=True, help="Ignored build-artifact directory"
    )
    parser.add_argument(
        "--review-record", type=Path, required=True, help="Tracked Markdown review record"
    )
    parser.add_argument("--compile", action="store_true", help="Attempt the local LaTeX preview")
    parser.add_argument(
        "--graphviz",
        action="store_true",
        help="Render the exported DOT graph to SVG when Graphviz is installed",
    )
    parser.add_argument(
        "--timeout-seconds", type=int, default=45, help="Maximum time for each preview command"
    )
    parser.add_argument(
        "--miktex-user-root",
        type=Path,
        help="Writable MiKTeX user root used for local preview compilation",
    )
    parser.add_argument(
        "--pdftoppm",
        type=Path,
        help="Explicit pdftoppm executable when it is not available on PATH",
    )
    args = parser.parse_args()

    payload = json.loads(args.source.read_text(encoding="utf-8"))
    machine = _machine(payload, args.machine)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    machine_tex = render(machine)
    (args.artifacts / "machine.tex").write_text(machine_tex, encoding="utf-8")
    typed_machine = StateMachine.model_validate(machine)
    (args.artifacts / "machine.dot").write_text(render_dot(typed_machine), encoding="utf-8")
    (args.artifacts / "machine.mmd").write_text(render_mermaid(typed_machine), encoding="utf-8")
    (args.artifacts / "review.tex").write_text(
        _wrapper(machine_tex, machine["title"]), encoding="utf-8"
    )

    compiled = False
    compile_note = "Preview compilation was not requested."
    graphviz_note = "Graphviz rendering was not requested."
    if args.graphviz:
        dot = shutil.which("dot") or shutil.which("dot.exe")
        if dot:
            try:
                _run(
                    [dot, "-Tsvg", "machine.dot", "-o", "graphviz.svg"],
                    args.artifacts,
                    args.timeout_seconds,
                )
                graphviz_note = "Graphviz SVG rendering completed."
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                graphviz_note = f"Graphviz rendering failed: {type(exc).__name__}."
        else:
            graphviz_note = "Graphviz rendering skipped: dot was not found."
    if args.compile:
        pdflatex = shutil.which("pdflatex") or shutil.which("pdflatex.exe")
        pdftoppm = (
            _executable(args.pdftoppm)
            if args.pdftoppm
            else (shutil.which("pdftoppm.exe") or shutil.which("pdftoppm"))
        )
        if pdflatex and pdftoppm:
            compile_env = os.environ.copy()
            if args.miktex_user_root:
                user_root = args.miktex_user_root.resolve()
                compile_env.update(
                    {
                        "MIKTEX_USERROOT": str(user_root),
                        "MIKTEX_USERDATA": str(user_root / "data"),
                        "MIKTEX_USERCONFIG": str(user_root / "config"),
                    }
                )
                user_root.mkdir(parents=True, exist_ok=True)
            try:
                _run(
                    [
                        pdflatex,
                        "-disable-installer",
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        "-jobname=review",
                        "review.tex",
                    ],
                    args.artifacts,
                    args.timeout_seconds,
                    env=compile_env,
                )
                _run(
                    [pdftoppm, "-png", "-f", "1", "-singlefile", "review.pdf", "preview"],
                    args.artifacts,
                    args.timeout_seconds,
                    env=compile_env,
                )
                compiled = True
                compile_note = "Preview compilation completed."
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                compile_note = (
                    f"Preview compilation failed or timed out: {type(exc).__name__}. "
                    "Inspect the generated log before retrying."
                )
        else:
            compile_note = "Preview compilation skipped: pdflatex or pdftoppm was not found."

    args.review_record.parent.mkdir(parents=True, exist_ok=True)
    record = _review_record(
        machine,
        args.source.as_posix(),
        args.source_image,
        args.artifacts,
        f"{compile_note}\n{graphviz_note}",
    )
    if args.review_record.exists():
        record = _merge_review_record(record, args.review_record.read_text(encoding="utf-8"))
    args.review_record.write_text(record, encoding="utf-8")
    print(f"machine: {machine['id']}")
    print(f"artifacts: {args.artifacts}")
    print(f"compiled: {'yes' if compiled else 'no'}")
    print(f"review record: {args.review_record}")


if __name__ == "__main__":
    main()
