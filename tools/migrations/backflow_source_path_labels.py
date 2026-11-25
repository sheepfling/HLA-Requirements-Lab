"""Correct page-adapter source labels at the Clause 11/12 boundary."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from hla_lab.core.semantic_model import (
    ContentBlockFile,
    ContentElementFile,
    RequirementApiBindingFile,
    RequirementFile,
    SourceRef,
)
from tools.migrations.backflow_common import semantic_root

FIRST_PAGE = 353
LAST_PAGE = 393
OLD_NAME = "11-management-object-model-page-"
NEW_NAME = "12-programming-language-mappings-page-"


def _write(path: Path, model: BaseModel) -> None:
    path.write_text(
        json.dumps(model.model_dump(mode="json", exclude_unset=True), ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def _repath(source: SourceRef, replacements: dict[str, str]) -> SourceRef:
    path = replacements.get(source.path)
    return source if path is None else source.model_copy(update={"path": path})


def repair_programming_language_source_paths(
    workspace_root: Path | None = None,
) -> tuple[str, ...]:
    """Relabel source pages 353–393 as Clause 12 while retaining record IDs."""
    semantic = semantic_root(workspace_root)
    document_root = semantic.parent
    adapter_dir = document_root / "content/clauses"
    adapter_dir_resolved = adapter_dir.resolve()
    replacements = {
        f"content/clauses/{OLD_NAME}{page}.tex": f"content/clauses/{NEW_NAME}{page}.tex"
        for page in range(FIRST_PAGE, LAST_PAGE + 1)
    }
    source_paths = {
        **replacements,
        **{new: new for new in replacements.values()},
    }

    # Validate the complete rename set before changing any files.
    rename_pairs: list[tuple[Path, Path]] = []
    for old_relative, new_relative in replacements.items():
        old_path = document_root / old_relative
        new_path = document_root / new_relative
        if old_path.parent.resolve() != adapter_dir_resolved or new_path.parent.resolve() != adapter_dir_resolved:
            raise ValueError("source page adapter path escaped the clauses directory")
        old_exists = old_path.is_file()
        new_exists = new_path.is_file()
        if old_exists and new_exists:
            raise FileExistsError(f"both source adapters exist for {old_relative}")
        if not old_exists and not new_exists:
            raise FileNotFoundError(f"neither source adapter exists for {old_relative}")
        if old_exists:
            rename_pairs.append((old_path, new_path))

    blocks_path = semantic / "content-blocks.json"
    blocks = ContentBlockFile.model_validate_json(blocks_path.read_text(encoding="utf-8"))
    selected_blocks = {
        item.source.path: item
        for item in blocks.content_blocks
        if item.source.path in source_paths
    }
    selected_paths = set(selected_blocks)
    missing = {
        new
        for old, new in replacements.items()
        if old not in selected_paths and new not in selected_paths
    }
    if missing:
        raise ValueError(f"source page blocks are missing: {sorted(missing)}")
    updated_blocks = tuple(
        item.model_copy(
            update={
                "source": _repath(item.source, replacements),
                "clause_id": "clause-12",
            }
        )
        if item.source.path in source_paths
        else item
        for item in blocks.content_blocks
    )

    elements_path = semantic / "content-elements.json"
    elements = ContentElementFile.model_validate_json(elements_path.read_text(encoding="utf-8"))
    updated_elements = tuple(
        item.model_copy(
            update={"source": _repath(item.source, replacements), "clause_id": "clause-12"}
        )
        if item.source is not None and item.source.path in source_paths
        else item
        for item in elements.content_elements
    )

    requirements_path = semantic / "requirements.json"
    requirements = RequirementFile.model_validate_json(
        requirements_path.read_text(encoding="utf-8")
    )
    updated_requirements = tuple(
        item.model_copy(
            update={
                "source": _repath(item.source, replacements),
                "additional_sources": tuple(
                    _repath(source, replacements) for source in item.additional_sources
                ),
            }
        )
        if item.source.path in source_paths
        or any(source.path in source_paths for source in item.additional_sources)
        else item
        for item in requirements.requirements
    )

    bindings_path = semantic / "api-requirement-bindings.json"
    bindings = RequirementApiBindingFile.model_validate_json(
        bindings_path.read_text(encoding="utf-8")
    )
    updated_bindings = tuple(
        item.model_copy(update={"source": _repath(item.source, replacements)})
        if item.source is not None and item.source.path in source_paths
        else item
        for item in bindings.bindings
    )

    updated_blocks_model = blocks.model_copy(update={"content_blocks": updated_blocks})
    updated_elements_model = elements.model_copy(update={"content_elements": updated_elements})
    updated_requirements_model = requirements.model_copy(
        update={"requirements": updated_requirements}
    )
    updated_bindings_model = bindings.model_copy(update={"bindings": updated_bindings})

    for old_path, new_path in rename_pairs:
        old_path.rename(new_path)
    _write(blocks_path, updated_blocks_model)
    _write(elements_path, updated_elements_model)
    _write(requirements_path, updated_requirements_model)
    _write(bindings_path, updated_bindings_model)
    return tuple(replacements.values())
