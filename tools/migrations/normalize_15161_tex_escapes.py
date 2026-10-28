"""Remove presentation-only TeX escapes from semantic requirement wording."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import (
    RequirementApiBindingFile,
    RequirementFile,
    load_document_model,
)
from hla_lab.core.semantic_text import _machine_statement
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.workspace import document_root


def normalize(root: Path) -> int:
    path = root / "semantic/requirements.json"
    document = RequirementFile.model_validate_json(path.read_text(encoding="utf-8"))
    updated = []
    count = 0
    for requirement in document.requirements:
        if (
            r"\ " not in requirement.statement
            and r"\_" not in requirement.statement
            and not requirement.statement.endswith("\\")
        ):
            updated.append(requirement)
            continue
        statement = _machine_statement(requirement.statement, HLA_SOURCE).rstrip("\\").rstrip()
        updated.append(
            requirement.model_copy(
                update={
                    "statement": statement,
                    "machine_statement": statement,
                }
            )
        )
        count += 1
    if count:
        path.write_text(
            json.dumps(
                document.model_copy(update={"requirements": tuple(updated)}).model_dump(
                    mode="json", exclude_unset=True
                ),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        binding_path = root / "semantic/api-requirement-bindings.json"
        binding_file = RequirementApiBindingFile.model_validate_json(
            binding_path.read_text(encoding="utf-8")
        )
        model = load_document_model(root, HLA_SOURCE)
        binding_path.write_text(
            json.dumps(
                binding_file.model_copy(
                    update={"bindings": build_requirement_api_bindings(model)}
                ).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    print(f"Normalized {count} requirement statements")
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    normalize(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
