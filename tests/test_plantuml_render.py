"""Regression checks for PlantUML asset conversion failures."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import patch

from hla_lab.diagrams.plantuml_render import render_sources


def test_ghostscript_recovers_when_epstopdf_cannot_write(tmp_path: Path) -> None:
    source = tmp_path / "example.puml"
    source.write_text("@startuml\n[*] --> Ready\n@enduml\n", encoding="utf-8")
    output_dir = tmp_path / "rendered"
    output = output_dir / "example.pdf"
    commands: list[list[str]] = []

    def run(command: Sequence[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
        commands.append(list(command))
        if command[0] == "java":
            source.with_suffix(".eps").write_text(
                "%!PS-Adobe-3.0 EPSF-3.0\n%%BoundingBox: 0 0 1 1\n", encoding="latin-1"
            )
        elif command[0] == "epstopdf":
            output.write_bytes(b"incomplete output")
            raise subprocess.CalledProcessError(1, command)
        else:
            assert command[0] == "ghostscript"
            assert "-dEPSCrop" in command
            assert not output.exists()
            output.write_bytes(b"%PDF-1.4\n")
        return subprocess.CompletedProcess(command, 0, "", "")

    with patch("hla_lab.diagrams.plantuml_render.subprocess.run", side_effect=run):
        rendered = render_sources(
            (source,),
            output_dir,
            java="java",
            jar=tmp_path / "plantuml.jar",
            epstopdf="epstopdf",
            ghostscript="ghostscript",
        )

    assert rendered == (output,)
    assert output.read_bytes() == b"%PDF-1.4\n"
    assert [command[0] for command in commands] == ["java", "epstopdf", "ghostscript"]
