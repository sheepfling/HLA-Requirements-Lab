"""Contract tests for diagram-surface QA report models."""

from __future__ import annotations

from pathlib import Path

from hla_lab.core.semantic_diagram_types import StateMachineFile
from hla_lab.core.semantic_model import DiagramSurface, DiagramSurfaceFile, StateMachine
from hla_lab.diagrams.diagram_surface_qa import validate


def test_diagram_surface_qa_uses_validated_report_and_record_shapes(tmp_path: Path) -> None:
    surface_manifest = tmp_path / "diagram-surfaces.json"
    surface_manifest.write_text(
        DiagramSurfaceFile(
            schema_version=1,
            surfaces=(
                DiagramSurface(
                    id="surface-state-machine-a",
                    document_id="demo",
                    page=1,
                    figure_number=1,
                    status="generated",
                    record_kind="state_machine",
                    record_id="state-machine-a",
                ),
            ),
        ).model_dump_json(),
        encoding="utf-8",
    )
    models_dir = tmp_path / "models"
    models_dir.mkdir()
    state_machine_file = StateMachineFile(
        schema_version=2,
        state_machines=(
            StateMachine(
                id="state-machine-a",
                title="State machine A",
                states=(),
                transitions=(),
            ),
        ),
    )
    (models_dir / "state-machines.json").write_text(
        state_machine_file.model_dump_json(), encoding="utf-8"
    )
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    (generated_dir / "content-block-state-machine-a.tex").write_text(
        r"\input{output/semantic/state-machine-state-machine-a}" + "\n",
        encoding="utf-8",
    )

    report = validate(surface_manifest, models_dir, generated_dir, expected_figures=1)

    assert report.passed
    assert report.generated_record_ids == ("state-machine-a",)
    assert report.model_dump(mode="json") == {
        "passed": True,
        "failures": [],
        "generated_figure_count": 1,
        "embedded_diagram_count": 1,
        "non_generatable_asset_count": 0,
        "generated_record_ids": ["state-machine-a"],
    }
