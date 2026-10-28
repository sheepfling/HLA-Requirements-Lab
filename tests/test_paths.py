"""Tests for the repository-owned filesystem resource registry."""

import os
import subprocess
import sys
from pathlib import Path
from shutil import copyfile

import pytest

from hla_lab.paths import (
    DOCUMENT_MANIFEST,
    RESOURCES,
    repository_root,
    resources,
)


def test_default_registry_exposes_named_manifests() -> None:
    assert RESOURCES.root == repository_root()
    assert RESOURCES.edition_lineage_manifest == DOCUMENT_MANIFEST
    assert RESOURCES.release_manifest.name == "documents.json"
    assert RESOURCES.authority_manifest.name == "authority.json"
    assert RESOURCES.source_profiles_manifest.name == "source-profiles.json"
    assert RESOURCES.state_machine_manifest.name == "manifest.json"


def test_document_resources_keep_document_layout_together() -> None:
    document = RESOURCES.document("hla-1516.1-2025")

    assert document.root == RESOURCES.ieee_topics / "hla-1516.1-2025"
    assert document.semantic_file("requirements.json") == document.semantic / "requirements.json"
    assert document.output_semantic_file("manifest.tex") == (
        document.output / "semantic" / "manifest.tex"
    )
    assert document.main_tex == document.root / "main.tex"


def test_registry_can_target_an_isolated_repository_root(tmp_path: Path) -> None:
    manifest = tmp_path / "data" / "semantic" / "edition-lineage.json"
    manifest.parent.mkdir(parents=True)
    copyfile(DOCUMENT_MANIFEST, manifest)
    isolated = resources(tmp_path)

    assert isolated.release_manifest == tmp_path / "data" / "release" / "documents.json"
    assert isolated.document("hla-1516-2025").root == (
        tmp_path / "topics" / "ieee" / "hla-1516-2025"
    )


def test_workspace_root_can_be_selected_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("HLA_LAB_ROOT", "C:/tmp/another-hla-workspace")
    assert repository_root() == Path("C:/tmp/another-hla-workspace").resolve()
    assert repository_root("C:/tmp/explicit") == Path("C:/tmp/explicit").resolve()


def test_workspace_root_never_falls_back_to_install_or_process_directory(monkeypatch) -> None:
    monkeypatch.delenv("HLA_LAB_ROOT", raising=False)
    with pytest.raises(RuntimeError, match="pass a path or set HLA_LAB_ROOT"):
        repository_root()


def test_source_profiles_load_from_package_data_without_workspace_root() -> None:
    environment = os.environ.copy()
    environment.pop("HLA_LAB_ROOT", None)
    subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from hla_lab.core.hla_profile import HLA_SOURCE, HLA_SOURCE_2010; "
                "assert HLA_SOURCE.stable_id == 'HLAStableID'; "
                "assert HLA_SOURCE_2010.stable_id == 'HLAStableID'"
            ),
        ],
        cwd=repository_root(),
        env=environment,
        check=True,
    )
