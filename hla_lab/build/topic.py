"""Manifest-driven entry point for every configured document product."""

from __future__ import annotations

import argparse
import json
import shutil
from collections.abc import Sequence
from pathlib import Path

from hla_lab.adapters.document_builder import (
    BuildConfig,
)
from hla_lab.adapters.document_builder import (
    build as build_document,
)
from hla_lab.adapters.document_builder import (
    clean as clean_document,
)
from hla_lab.core.hla_profile import HLA_LATEX_DIALECT, source_profile_for_document
from hla_lab.core.semantic_model import load_document_model
from hla_lab.corpus.corpus_graph import build_corpus_graph, load_document_metadata
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.generation.contracts import GenerationRequest
from hla_lab.diagrams.plantuml_render import render_sources
from hla_lab.generation.faithful_renderer import load_faithful_layout_profile
from hla_lab.generation.generate_derivative import generate_from_hla
from hla_lab.generation.semantic_generation import generate as generate_semantic
from hla_lab.paths import REPO_ROOT, RESOURCES, DocumentResources, document_roots
from hla_lab.publication.compliance_publication import (
    load_compliance_publication_profile,
    write_compliance_publication,
)
from hla_lab.publication.publication_contract import load_publication_profile
from hla_lab.publication.publication_registry import (
    BuildSettings,
    ReleaseProject,
    load_publication_registry,
    load_release_manifest,
)

__all__ = ["generate", "main", "project_config"]

PUBLICATION_MANIFEST = RESOURCES.publications_manifest
RELEASE_MANIFEST = RESOURCES.release_manifest


def _selected_ids(model: object, field: str, selection: str, ordering: str) -> tuple[str, ...]:
    if selection == "none":
        return ()
    values = (
        getattr(model, f"ordered_{field}")() if ordering == "ordered" else getattr(model, field)
    )
    return tuple(item.id for item in values)


def _table_family_ids(model: object, selection: str) -> tuple[str, ...] | None:
    return None if selection == "all" else ()


def _faithful_generator(root: Path, project: ReleaseProject, settings: BuildSettings):
    document = DocumentResources(root)
    source = source_profile_for_document(project.id)
    layout_path = document.semantic_file("faithful-layout.json")
    layout = load_faithful_layout_profile(layout_path) if layout_path.is_file() else None

    def generate_blocks() -> object:
        model = load_document_model(root, source)
        return generate_semantic(
            GenerationRequest(
                root=root,
                output=document.output_semantic,
                source=source,
                dialect=HLA_LATEX_DIALECT,
                definition_ids=_selected_ids(
                    model, "definitions", settings.definition_selection, settings.definition_order
                ),
                requirement_ids=_selected_ids(
                    model,
                    "requirements",
                    settings.requirement_selection,
                    settings.requirement_order,
                ),
                content_block_ids=_selected_ids(
                    model, "content_blocks", settings.content_block_selection, "source"
                ),
                content_element_ids=_selected_ids(
                    model, "content_elements", settings.content_element_selection, "source"
                ),
                table_family_ids=_table_family_ids(model, settings.table_family_selection),
                include_table_cells=settings.include_table_cells,
                include_faithful_body=settings.include_faithful_body,
                faithful_layout_profile=layout,
                faithful_body_exclude_path_parts=settings.faithful_body_exclude_path_parts,
                use_generated_faithful_blocks=settings.use_generated_faithful_blocks,
                state_machine_renderer=settings.state_machine_renderer,
                service_page_renderer=settings.service_page_renderer,
            )
        )

    return generate_blocks


def _source_roots(project: ReleaseProject) -> tuple[Path, ...]:
    registry = load_publication_registry(PUBLICATION_MANIFEST)
    publication = registry.publication(project.publication_id)
    return document_roots(REPO_ROOT, publication.source_document_ids)


def _derivative_generator(root: Path, project: ReleaseProject):
    document = DocumentResources(root)
    source_roots = _source_roots(project)

    def generate_blocks() -> object:
        profile = load_publication_profile(document.semantic_file("publication.json"))
        metadata = load_document_metadata(document.semantic_file("corpus.json"))
        return generate_from_hla(
            source_roots, document.output_semantic, profile=profile, graph_metadata=metadata
        )

    return generate_blocks


def _compliance_generator(root: Path, project: ReleaseProject, settings: BuildSettings):
    document = DocumentResources(root)
    source_roots = _source_roots(project)
    if settings.graph_metadata is None:
        raise ValueError(f"compliance project {project.id} has no graph metadata path")
    metadata_path = REPO_ROOT / settings.graph_metadata

    def generate_blocks() -> object:
        corpus = load_hla_corpus(source_roots)
        profile = load_compliance_publication_profile(document.semantic_file("publication.json"))
        metadata = load_document_metadata(metadata_path)
        graph = build_corpus_graph(corpus, metadata=metadata)
        return write_compliance_publication(
            corpus,
            profile,
            document.output / "compliance",
            graph=graph,
            csv_output=document.output / "compliance" / "csv",
        )

    return generate_blocks


def _config(root: Path, project: ReleaseProject, settings: BuildSettings) -> BuildConfig:
    if settings.strategy == "faithful":
        generator = _faithful_generator(root, project, settings)
    elif settings.strategy == "semantic-derivative":
        generator = _derivative_generator(root, project)
    elif settings.strategy == "compliance":
        generator = _compliance_generator(root, project, settings)
    else:
        raise ValueError(
            f"{project.id} uses unsupported generic build strategy {settings.strategy}"
        )
    navigation_manifest = (
        root / settings.navigation_manifest if settings.navigation_manifest is not None else None
    )
    asset_generator = None
    if settings.state_machine_renderer == "plantuml":
        asset_generator = _plantuml_asset_generator(root)
    return BuildConfig(
        root=root,
        clean_before_build=settings.clean_before_build,
        navigation_manifest=navigation_manifest,
        output_pdf=root / project.pdf,
        semantic_generator=generator,
        asset_generator=asset_generator,
    )


def _plantuml_asset_generator(root: Path):
    """Return the pinned PlantUML asset step for a faithful document build."""

    document = DocumentResources(root)
    lock_path = REPO_ROOT / "tools" / "plantuml" / "plantuml.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    version = str(lock["version"])
    jar = REPO_ROOT / ".tools" / "plantuml" / f"plantuml-{version}.jar"

    def render_assets() -> object:
        sources = tuple(sorted(document.output_semantic.glob("state-machine-*.puml")))
        if not sources:
            raise RuntimeError(f"PlantUML build requested but no state-machine sources exist in {document.output_semantic}")
        if not jar.is_file():
            raise RuntimeError(f"Pinned PlantUML jar is missing: {jar}; see tools/plantuml/README.md")
        java = shutil.which("java")
        epstopdf = shutil.which("epstopdf")
        if java is None or epstopdf is None:
            raise RuntimeError("PlantUML asset build requires java and epstopdf on PATH")
        return render_sources(
            sources,
            java=java,
            epstopdf=epstopdf,
            jar=jar,
            output_dir=document.output_semantic,
        )

    return render_assets


def project_config(root: Path) -> BuildConfig:
    """Resolve one document root to its fully data-declared build config."""
    root = root.resolve()
    release_manifest = load_release_manifest(RELEASE_MANIFEST)
    relative_root = root.relative_to(REPO_ROOT).as_posix()
    try:
        project = next(
            item
            for item in release_manifest.projects
            if item.root.replace("\\", "/") == relative_root
        )
    except StopIteration as error:
        raise ValueError(f"no release project declares build root {relative_root}") from error
    if project.build is None:
        raise ValueError(f"release project {project.id} has no build settings")
    return _config(root, project, project.build)


def generate(root: Path) -> object:
    """Generate semantic build inputs for the product at ``root``."""
    config = project_config(root)
    if config.semantic_generator is None:
        raise ValueError(f"{root} has no semantic generator")
    result = config.semantic_generator()
    if config.asset_generator is not None:
        config.asset_generator()
    return result


def main(argv: Sequence[str] | None = None, *, root: Path | None = None) -> int:
    """Generate, build, or clean the product described in the release manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("generate", "build", "clean"))
    parser.add_argument(
        "--root", type=Path, help="document root when invoking the shared runner directly"
    )
    args = parser.parse_args(argv)
    resolved_root = (root or args.root or Path.cwd()).resolve()
    if args.action == "generate":
        generate(resolved_root)
        return 0
    if args.action == "clean":
        clean_document(resolved_root)
        return 0
    print(build_document(project_config(resolved_root)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
