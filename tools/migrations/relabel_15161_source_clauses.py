"""Align promoted 1516.1 requirements with visible source headings.

Page metadata and PDF bookmarks can describe sections that begin later on a
page. Requirement ownership follows the most recent visible heading instead.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import RequirementFile, load_document_model
from hla_lab.core.semantic_model_authored import _load_authored_content_blocks
from hla_lab.core.semantic_model_records import (
    _heading_context_by_file,
    _requirement_candidate_units,
)
from tools.migrations.workspace import document_root


def source_clause_owners(root: Path) -> dict[tuple[str, int], str]:
    """Return a clause owner for each source line covered by a visible heading."""
    blocks = _load_authored_content_blocks(root)
    units = _requirement_candidate_units(
        root, HLA_SOURCE, _heading_context_by_file(root, HLA_SOURCE), blocks
    )
    owners: dict[tuple[str, int], str] = {}
    for path, body, headings in units:
        relative = path.relative_to(root).as_posix()
        offset = 0
        heading_index = 0
        active: str | None = None
        for line_number, line in enumerate(body.splitlines(keepends=True), start=1):
            while heading_index < len(headings) and headings[heading_index][0] <= offset:
                active = headings[heading_index][1].removeprefix("clause-")
                heading_index += 1
            if active is not None:
                owners[relative, line_number] = active
            offset += len(line)
    return owners


def relabel(root: Path, *, check: bool) -> int:
    path = root / "semantic/requirements.json"
    document = RequirementFile.model_validate_json(path.read_text(encoding="utf-8"))
    valid = {clause.id for clause in load_document_model(root, HLA_SOURCE).clauses}
    owners = source_clause_owners(root)
    changed = []
    for requirement in document.requirements:
        if not requirement.id.startswith(
            ("requirement-candidate-content-clauses-", "requirement-source-refinement-")
        ):
            changed.append(requirement)
            continue
        clause = owners.get((requirement.source.path, requirement.source.line))
        if clause is None or clause == requirement.clause:
            changed.append(requirement)
            continue
        if f"clause-{clause}" not in valid:
            raise ValueError(f"Unknown source clause {clause} for {requirement.id}")
        changed.append(
            requirement.model_copy(
                update={
                    "clause": clause,
                    "clause_id": f"clause-{clause}",
                    "semantic_group_id": f"m16.clause.{clause}",
                }
            )
        )
    count = sum(
        before.clause != after.clause
        for before, after in zip(document.requirements, changed, strict=True)
    )
    if not check and count:
        payload = document.model_copy(update={"requirements": tuple(changed)}).model_dump(
            mode="json", exclude_unset=True
        )
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{count} requirement clause labels {'need updates' if check else 'updated'}")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    relabel(document_root("hla-1516.1-2025", args.workspace_root), check=args.check)


if __name__ == "__main__":
    main()
