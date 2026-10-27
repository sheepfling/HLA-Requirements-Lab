"""Trace a federation continuation requirement across its printed page break."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_base import SourceRef
from hla_lab.core.semantic_model import (
    RequirementApiBindingFile,
    RequirementFile,
    load_document_model,
)
from hla_lab.core.semantic_text import _machine_statement
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.workspace import document_root

FIRST = "requirement-candidate-content-clauses-04-federation-management-page-049-l163-52"
SECOND = "requirement-candidate-content-clauses-04-federation-management-page-050-l6-1"
FIRST_STATEMENT = (
    "If a fault divides the federation into multiple independent segments capable of continuing, "
    "the RTI shall select exactly one segment to continue the federation execution."
)
SECOND_STATEMENT = "Federates contained in all other segments shall be considered lost."


def repair(root: Path) -> None:
    requirement_path = root / "semantic/requirements.json"
    binding_path = root / "semantic/api-requirement-bindings.json"
    requirements = RequirementFile.model_validate_json(requirement_path.read_text(encoding="utf-8"))
    bindings = RequirementApiBindingFile.model_validate_json(
        binding_path.read_text(encoding="utf-8")
    )
    sources = {}
    changed = []
    for requirement in requirements.requirements:
        if requirement.id == FIRST:
            source = requirement.source.model_copy(update={"line": 160, "end_line": 165})
            changed.append(
                requirement.model_copy(
                    update={
                        "statement": FIRST_STATEMENT,
                        "machine_statement": _machine_statement(FIRST_STATEMENT, HLA_SOURCE),
                        "source": source,
                        "additional_sources": (
                            SourceRef(
                                path="content/clauses/04-federation-management-page-050.tex",
                                line=6,
                                end_line=8,
                            ),
                        ),
                    }
                )
            )
            sources[FIRST] = source
        elif requirement.id == SECOND:
            source = requirement.source.model_copy(update={"line": 6, "end_line": 8})
            changed.append(
                requirement.model_copy(
                    update={
                        "statement": SECOND_STATEMENT,
                        "machine_statement": _machine_statement(SECOND_STATEMENT, HLA_SOURCE),
                        "source": source,
                    }
                )
            )
            sources[SECOND] = source
        else:
            changed.append(requirement)
    if set(sources) != {FIRST, SECOND}:
        raise ValueError("Cross-page requirement records are missing")
    requirement_path.write_text(
        json.dumps(
            requirements.model_copy(update={"requirements": tuple(changed)}).model_dump(
                mode="json", exclude_unset=True
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    updated_bindings = [
        binding.model_copy(update={"source": sources[binding.requirement_id]})
        if binding.requirement_id in sources
        else binding
        for binding in bindings.bindings
    ]
    binding_path.write_text(
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
    rebuilt = build_requirement_api_bindings(load_document_model(root, HLA_SOURCE))
    binding_path.write_text(
        json.dumps(
            bindings.model_copy(update={"bindings": rebuilt}).model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print("Repaired two federation-continuation requirements with cross-page tracing")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    repair(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
