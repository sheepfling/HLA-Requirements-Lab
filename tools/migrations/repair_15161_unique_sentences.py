"""Repair unambiguous single-obligation PDF-line fragments from source text."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    RequirementApiBindingFile,
    RequirementFile,
    load_document_model,
)
from hla_lab.core.semantic_text import _machine_statement
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.audit_15161_fragments import sentence_matches
from tools.migrations.workspace import document_root


def _needs_repair(statement: str) -> bool:
    return bool(re.match(r"^[a-z]", statement)) or not statement.rstrip().endswith(
        (".", ":", "?", "!")
    )


def _safe_reconstruction(row: dict[str, object]) -> bool:
    old = str(row["old_statement"])
    new = re.sub(r"\s+", " ", str(row["new_statement"])).strip()
    return (
        row["duplicate_count"] == 1
        and _needs_repair(old)
        and bool(new)
        and new[0].isupper()
        and new.endswith((".", ":", "?", "!"))
        and len(re.findall(r"\bshall\b", old, re.IGNORECASE)) == 1
        and len(re.findall(r"\bshall\b", new, re.IGNORECASE)) == 1
        and "\\" not in new
        and "�" not in new
        and re.search(r"\w-\s+\w", new) is None
        and re.search(r"[.!?]\s+[A-Za-z0-9)]", new) is None
    )


def repair(root: Path, *, check: bool) -> int:
    rows, _ = sentence_matches(root)
    fixes = {str(row["id"]): row for row in rows if _safe_reconstruction(row)}
    if check:
        print(f"{len(fixes)} unambiguous line fragments need repair")
        return len(fixes)
    requirements_path = root / "semantic/requirements.json"
    bindings_path = root / "semantic/api-requirement-bindings.json"
    requirements = RequirementFile.model_validate_json(
        requirements_path.read_text(encoding="utf-8")
    )
    bindings = RequirementApiBindingFile.model_validate_json(
        bindings_path.read_text(encoding="utf-8")
    )
    source_by_id = {}
    updated_requirements = []
    for requirement in requirements.requirements:
        row = fixes.get(requirement.id)
        if row is None:
            updated_requirements.append(requirement)
            continue
        statement = re.sub(r"\s+", " ", str(row["new_statement"])).strip()
        source = requirement.source.model_copy(update=row["new_source"])
        source_by_id[requirement.id] = source
        updated_requirements.append(
            requirement.model_copy(
                update={
                    "statement": statement,
                    "machine_statement": _machine_statement(statement, HLA_SOURCE),
                    "source": source,
                }
            )
        )
    updated_bindings = [
        binding.model_copy(update={"source": source_by_id[binding.requirement_id]})
        if binding.requirement_id in source_by_id
        else binding
        for binding in bindings.bindings
    ]
    requirements_path.write_text(
        json.dumps(
            requirements.model_copy(
                update={"requirements": tuple(updated_requirements)}
            ).model_dump(mode="json", exclude_unset=True),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    bindings_path.write_text(
        json.dumps(
            bindings.model_copy(update={"bindings": tuple(updated_bindings)}).model_dump(
                mode="json"
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    # Wording changes can select a different exact language declaration. Keep
    # the generated manifest aligned with the reviewed requirement text.
    model = load_document_model(root, HLA_SOURCE)
    rebuilt = build_requirement_api_bindings(model)
    bindings_path.write_text(
        json.dumps(
            bindings.model_copy(update={"bindings": rebuilt}).model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Repaired {len(fixes)} unambiguous line fragments")
    return len(fixes)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    repair(document_root("hla-1516.1-2025", args.workspace_root), check=args.check)


if __name__ == "__main__":
    main()
