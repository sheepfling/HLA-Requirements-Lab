"""Contracts for selecting a corpus root independently of the CLI checkout."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from hla_lab.build.topic import project_config
from hla_lab.cli import main
from hla_lab.core.hla_profile import source_profile_for_document
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import DOCUMENT_IDS, RESOURCES, document_roots, resources


def _write_document_manifest(root: Path, *, profile_id: str | None = None) -> None:
    path = root / "data" / "semantic" / "edition-lineage.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "documents": [
                    {
                        "document_id": "alternate-standard-9",
                        "standard_id": "ALT-9",
                        "edition": "2030",
                        "title": "Alternate Standard 9",
                        "root": "topics/alternate/standard-9",
                        "profile_id": profile_id,
                    }
                ],
                "relations": [],
            }
        ),
        encoding="utf-8",
    )


def _write_map_inputs(root: Path) -> Path:
    document = root / "topics" / "alternate" / "standard-9"
    semantic = document / "semantic"
    semantic.mkdir(parents=True)
    inputs = {
        "requirements.json": {"requirements": [{"id": "alt.req.1"}]},
        "requirement-links.json": {"links": []},
        "implementations.json": {"implementations": [{"status": "planned"}]},
        "api-surfaces.json": {"api_surfaces": []},
        "api-crosswalk.json": {"api_crosswalks": []},
        "api-requirement-bindings.json": {"bindings": []},
    }
    for name, payload in inputs.items():
        (semantic / name).write_text(json.dumps(payload), encoding="utf-8")
    return document


def _write_compliance_project(root: Path) -> Path:
    project = root / "topics" / "alternate" / "compliance-2025"
    project.mkdir(parents=True)
    release_manifest = root / "data" / "release" / "documents.json"
    release_manifest.parent.mkdir(parents=True, exist_ok=True)
    release_manifest.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "projects": [
                    {
                        "id": "hla-rti-compliance-requirements-2025",
                        "publication_id": "alt-compliance-publication",
                        "root": "topics/alternate/compliance-2025",
                        "pdf": "dist/compliance.pdf",
                        "log": "build/main.log",
                        "kind": "requirements-publication",
                        "build": {
                            "strategy": "compliance",
                            "graph_metadata": "data/semantic/graph.json",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    registry = root / "data" / "publications.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "publications": [
                    {
                        "id": "alt-compliance-publication",
                        "kind": "requirements-publication",
                        "title": "Alternate Compliance Matrix",
                        "description": "Temporary test corpus.",
                        "project_ids": ["hla-rti-compliance-requirements-2025"],
                        "source_document_ids": ["alternate-standard-9"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return project


def test_document_resources_and_identities_come_from_selected_catalog(tmp_path: Path) -> None:
    _write_document_manifest(tmp_path)

    assert resources(tmp_path).document("alternate-standard-9").root == (
        tmp_path / "topics" / "alternate" / "standard-9"
    )
    (tmp_path / "topics" / "alternate" / "standard-9").mkdir(parents=True)
    assert document_roots(tmp_path) == (tmp_path / "topics" / "alternate" / "standard-9",)
    assert DOCUMENT_IDS != ("alternate-standard-9",)


def test_hla_loader_uses_catalog_identity_when_directory_name_differs(tmp_path: Path) -> None:
    _write_document_manifest(tmp_path, profile_id="alternate-hla-profile")
    document_root = tmp_path / "topics" / "alternate" / "standard-9"
    document_root.mkdir(parents=True)

    with (
        patch(
            "hla_lab.corpus.hla_semantic.source_profile_for_document", return_value=object()
        ) as profile,
        patch("hla_lab.corpus.hla_semantic.load_document_model", return_value=object()),
        patch(
            "hla_lab.corpus.hla_semantic.build_hla_surface_contract",
            side_effect=lambda model: model,
        ),
    ):
        load_hla_document_model(document_root, workspace_root=tmp_path)

    profile.assert_called_once_with("alternate-standard-9", tmp_path)


def test_alternate_document_identity_resolves_its_selected_source_profile(tmp_path: Path) -> None:
    _write_document_manifest(tmp_path, profile_id="alternate-hla-profile")
    source_profiles = json.loads(RESOURCES.source_profiles_manifest.read_text(encoding="utf-8"))
    source_profiles["profiles"][0]["id"] = "alternate-hla-profile"
    source_profiles["command_vocabulary"]["content_marker"] = "AlternateContentMarker"
    target = tmp_path / "data" / "semantic" / "source-profiles.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(source_profiles), encoding="utf-8")

    assert source_profile_for_document("alternate-standard-9", tmp_path).content_marker == (
        "AlternateContentMarker"
    )


def test_map_cli_reads_selected_corpus_and_preserves_default_json_shape(
    tmp_path: Path, capsys
) -> None:
    _write_document_manifest(tmp_path)
    _write_map_inputs(tmp_path)

    assert main(["map", "alternate-standard-9", "--corpus-root", str(tmp_path), "--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["documents"][0]["document"] == "alternate-standard-9"
    assert payload["documents"][0]["root"] == "topics/alternate/standard-9"
    assert payload["documents"][0]["requirements"] == 1
    assert payload["status_notes"]["implementation"]


def test_map_cli_reports_missing_selected_manifest_and_mapping_input(
    tmp_path: Path, capsys
) -> None:
    assert main(["map", "--corpus-root", str(tmp_path)]) == 2
    assert "missing document manifest" in capsys.readouterr().err

    _write_document_manifest(tmp_path)
    (tmp_path / "topics" / "alternate" / "standard-9").mkdir(parents=True)
    assert main(["map", "--corpus-root", str(tmp_path)]) == 2
    error = capsys.readouterr().err
    assert "missing canonical mapping file" in error
    assert "topics/alternate/standard-9/semantic/requirements.json" in error


def test_matrix_generator_resolves_release_publication_and_source_roots_from_selected_corpus(
    tmp_path: Path,
) -> None:
    _write_document_manifest(tmp_path, profile_id="hla-2025")
    source_profiles = (
        Path(__file__).resolve().parents[1] / "data" / "semantic" / "source-profiles.json"
    )
    selected_profiles = tmp_path / "data" / "semantic" / "source-profiles.json"
    selected_profiles.parent.mkdir(parents=True, exist_ok=True)
    selected_profiles.write_bytes(source_profiles.read_bytes())
    source_root = tmp_path / "topics" / "alternate" / "standard-9"
    source_root.mkdir(parents=True)
    project_root = _write_compliance_project(tmp_path)

    config = project_config(project_root, tmp_path)
    assert config.semantic_generator is not None
    with (
        patch("hla_lab.build.topic.load_hla_corpus") as load_corpus,
        patch("hla_lab.build.topic.load_compliance_publication_profile", return_value=object()),
        patch("hla_lab.build.topic.load_document_metadata", return_value={}) as load_metadata,
        patch("hla_lab.build.topic.build_corpus_graph", return_value=object()),
        patch("hla_lab.build.topic.write_compliance_publication", return_value="generated"),
    ):
        assert config.semantic_generator() == "generated"

    load_corpus.assert_called_once_with((source_root,), workspace_root=tmp_path)
    load_metadata.assert_called_once_with(tmp_path / "data" / "semantic" / "graph.json")


def test_matrix_cli_routes_to_project_declared_by_selected_release_manifest(
    tmp_path: Path, capsys
) -> None:
    _write_compliance_project(tmp_path)
    calls = []

    def generate(arguments: list[str], **kwargs: object):
        calls.append((arguments, kwargs))
        project_root = Path(arguments[arguments.index("--root") + 1])
        output = project_root / "output" / "compliance"
        for name in (
            "compliance-manifest.json",
            "compliance-requirements.tex",
            "csv/requirements.csv",
            "csv/transitions.csv",
            "csv/implementation-mappings.csv",
            "csv/requirement-mapping-links.csv",
            "csv/transition-mapping-links.csv",
        ):
            path = output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("generated", encoding="utf-8")
        return type("Result", (), {"returncode": 0})()

    with patch("hla_lab.cli.subprocess.run", side_effect=generate):
        assert main(["matrix", "--corpus-root", str(tmp_path)]) == 0

    arguments, options = calls[0]
    assert Path(arguments[arguments.index("--root") + 1]) == (
        tmp_path / "topics" / "alternate" / "compliance-2025"
    )
    assert Path(arguments[arguments.index("--workspace-root") + 1]) == tmp_path
    assert options["cwd"] == tmp_path
    assert "topics/alternate/compliance-2025/output/compliance/csv/requirements.csv" in (
        capsys.readouterr().out
    )


def test_matrix_cli_reports_missing_selected_release_manifest(tmp_path: Path, capsys) -> None:
    assert main(["matrix", "--corpus-root", str(tmp_path)]) == 2
    assert "missing release manifest" in capsys.readouterr().err
