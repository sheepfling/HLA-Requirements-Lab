"""Tests for the repository-owned filesystem resource registry."""

from pathlib import Path

from hla_lab.paths import (
    DOCUMENT_MANIFEST,
    RESOURCES,
    DocumentResources,
    RepositoryResources,
    resources,
)


def test_default_registry_exposes_named_manifests() -> None:
    assert RESOURCES.root == Path(__file__).resolve().parents[1]
    assert RESOURCES.edition_lineage_manifest == DOCUMENT_MANIFEST
    assert RESOURCES.release_manifest.name == "documents.json"
    assert RESOURCES.authority_manifest.name == "authority.json"
    assert RESOURCES.source_profiles_manifest.name == "source-profiles.json"
    assert RESOURCES.state_machine_manifest.name == "manifest.json"


def test_document_resources_keep_document_layout_together() -> None:
    document = RESOURCES.document("hla-1516.1-2025")

    assert isinstance(document, DocumentResources)
    assert document.root == RESOURCES.ieee_topics / "hla-1516.1-2025"
    assert document.semantic_file("requirements.json") == document.semantic / "requirements.json"
    assert document.output_semantic_file("manifest.tex") == (
        document.output / "semantic" / "manifest.tex"
    )
    assert document.main_tex == document.root / "main.tex"


def test_registry_can_target_an_isolated_repository_root(tmp_path: Path) -> None:
    manifest = tmp_path / "data" / "semantic" / "edition-lineage.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '{"schema_version":1,"documents":[{"document_id":"hla-1516-2025",'
        '"standard_id":"IEEE 1516","edition":"2025","title":"Framework",'
        '"root":"topics/ieee/hla-1516-2025"}],"relations":[]}',
        encoding="utf-8",
    )
    isolated = resources(tmp_path)

    assert isinstance(isolated, RepositoryResources)
    assert isolated.release_manifest == tmp_path / "data" / "release" / "documents.json"
    assert isolated.document("hla-1516-2025").root == (
        tmp_path / "topics" / "ieee" / "hla-1516-2025"
    )
