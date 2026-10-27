"""Review-backed, atomic requirements for IEEE 1516.1 page 48."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.semantic_model import (
    ContentBlockFile,
    RequirementApiBindingFile,
    RequirementFile,
)
from hla_lab.core.semantic_text import _machine_statement
from hla_lab.core.hla_profile import HLA_SOURCE
from tools.migrations.workspace import document_root

PAGE_PATH = "content/clauses/04-federation-management-page-048.tex"
PREFIX = "requirement-candidate-content-clauses-04-federation-management-page-048-"

# Stable suffix -> (source-faithful atomic statement, source start, source end).
REPAIRS: dict[str, tuple[str, int, int]] = {
    "l6-1": (
        "When the Create Federation Execution service is invoked, the RTI shall initialize the federation execution using FDD first from the MIM and then from the specified FOM modules.", 6, 11,
    ),
    "l12-3": (
        "A user-extended MIM may be provided; otherwise, the RTI shall provide the standard MIM automatically.", 9, 14,
    ),
    "l21-6": (
        "The FOM module designator arguments supplied to the Create Federation Execution service and the Join Federation Execution service shall designate compliant FOM modules (IEEE Std 1516-2025 and IEEE Std 1516.2-2025).", 18, 26,
    ),
    "l24-7": (
        "Create Federation Execution and Join Federation Execution service invocations shall reject, issuing an exception, any entity that is not a compliant FOM module.", 24, 29,
    ),
    "l33-10": (
        "The RTI shall combine the FDD data of the MIM and FOM modules according to the rules for combining FOM data in IEEE Std 1516.2-2025 when the Create Federation Execution service is invoked as well as whenever the set of FOM modules has changed due to an invocation of the Join Federation Execution service.", 33, 44,
    ),
    "l42-13": (
        "The RTI shall consider only the FDD when combining FOM modules.", 42, 44,
    ),
    "l48-15": (
        "After combining switches from all FDD provided during the Create Federation Execution service, if a switch remains unspecified, the RTI shall provide a default value for the switch in the current FOM as specified in IEEE Std 1516.2-2025.", 42, 50,
    ),
    "l54-17": (
        "In case the FDD of the FOM modules provided in such a service call cannot be successfully combined or the invocation fails for any other reason, the FDD provided in the call shall not be included in the current FOM.", 48, 56,
    ),
    "l57-18": (
        "The RTI shall reject, issuing an exception, any attempt to load a FOM module for the following cases:", 57, 59,
    ),
    "l129-42": (
        "If a FOM module or MIM contains any definition that is rejected by the RTI, the RTI shall reject the FOM module or MIM in its entirety.", 129, 134,
    ),
    "l132-43": (
        "If a FOM module or MIM contains any definition that is rejected by the RTI, the RTI shall not add any element to the FDD.", 129, 134,
    ),
    "l138-45": (
        "The union of all FOM modules in a given Create Federation Execution or Join Federation Execution service when added to the previously existing current FOM shall not result in any object class or interaction class not having a full definition.", 135, 143,
    ),
    "l141-46": (
        "If the union of FOM modules would result in an object class or interaction class without a full definition, the entire service invocation shall fail.", 135, 143,
    ),
    "l144-47": (
        "In case any of the FOM modules provided was rejected by the RTI, the entire service invocation shall also fail.", 141, 146,
    ),
    "l150-49": (
        "After a Create Federation Execution or Join Federation Execution service has completed successfully, all the provided FOM modules shall be available in the current FOM.", 147, 155,
    ),
    "l153-50": (
        "After a Create Federation Execution or Join Federation Execution service has completed successfully, the corresponding MOM information shall be updated to reflect the provided FOM modules.", 147, 155,
    ),
}

# The seven list items inherit the "shall reject" obligation from line 57.
REJECTION_CASES: dict[str, tuple[str, int, int]] = {
    "attribute-conflict": ("a named object class attribute has different transportation or order from an existing named attribute with the same name in the same object class of the current FOM", 63, 71),
    "interaction-conflict": ("a named interaction class has different transportation or order from an existing named interaction class with the same qualified name in the current FOM", 75, 83),
    "dimension-conflict": ("a named dimension has a different upper bound or value when unspecified from an existing named dimension in the current FOM", 87, 92),
    "transport-conflict": ("a named transportation type has different reliability from an existing named transportation type in the current FOM", 96, 104),
    "update-rate-conflict": ("a named update rate has a different maximum rate from an existing named update rate in the current FOM", 108, 113),
    "switch-conflict": ("a named switch has a different definition from an existing named switch in the current FOM", 117, 122),
    "noncompliant-module": ("the MIM or FOM module is noncompliant", 126, 128),
}


def repair(root: Path) -> None:
    requirements_path = root / "semantic/requirements.json"
    bindings_path = root / "semantic/api-requirement-bindings.json"
    blocks_path = root / "semantic/content-blocks.json"
    requirements = RequirementFile.model_validate_json(requirements_path.read_text(encoding="utf-8"))
    bindings = RequirementApiBindingFile.model_validate_json(bindings_path.read_text(encoding="utf-8"))
    blocks = ContentBlockFile.model_validate_json(blocks_path.read_text(encoding="utf-8"))
    updated_requirements = []
    source_by_id = {}
    found = set()
    new_ids = {f"req-fom-module-reject-{case}" for case in REJECTION_CASES}
    template = next(item for item in requirements.requirements if item.id == PREFIX + "l57-18")
    binding_template = next(item for item in bindings.bindings if item.requirement_id == template.id)
    for requirement in requirements.requirements:
        if requirement.id in new_ids:
            continue
        if requirement.id == PREFIX + "l129-42":
            for case, (condition, start, end) in REJECTION_CASES.items():
                identifier = f"req-fom-module-reject-{case}"
                statement = f"The RTI shall reject, issuing an exception, an attempt to load a FOM module when {condition}."
                source = template.source.model_copy(update={"path": PAGE_PATH, "line": start, "end_line": end})
                source_by_id[identifier] = source
                updated_requirements.append(template.model_copy(update={
                    "id": identifier,
                    "title": f"Reject FOM module: {case.replace('-', ' ')}",
                    "statement": statement,
                    "machine_statement": _machine_statement(statement, HLA_SOURCE),
                    "source": source,
                }))
        if not requirement.id.startswith(PREFIX):
            updated_requirements.append(requirement)
            continue
        suffix = requirement.id.removeprefix(PREFIX)
        statement, start, end = REPAIRS[suffix]
        source = requirement.source.model_copy(update={"line": start, "end_line": end})
        source_by_id[requirement.id] = source
        found.add(suffix)
        updated_requirements.append(requirement.model_copy(update={
            "statement": statement,
            "machine_statement": _machine_statement(statement, HLA_SOURCE),
            "source": source,
        }))
    if found != REPAIRS.keys():
        raise ValueError(f"Page 48 record drift: {sorted(REPAIRS.keys() - found)}")
    updated_bindings = [
        binding.model_copy(update={"source": source_by_id[binding.requirement_id]})
        if binding.requirement_id in source_by_id else binding
        for binding in bindings.bindings if binding.requirement_id not in new_ids
    ]
    for case in REJECTION_CASES:
        identifier = f"req-fom-module-reject-{case}"
        updated_bindings.append(binding_template.model_copy(update={
            "id": f"binding.{identifier}.no-api",
            "requirement_id": identifier,
            "source": source_by_id[identifier],
        }))
    updated_bindings.sort(key=lambda item: item.id)
    updated_blocks = []
    for block in blocks.content_blocks:
        if block.id == "content-15161-page-048":
            extra = tuple(f"req-fom-module-reject-{case}" for case in REJECTION_CASES)
            existing = tuple(item for item in block.record_ids if item not in extra)
            position = existing.index(PREFIX + "l129-42")
            block = block.model_copy(update={"record_ids": (*existing[:position], *extra, *existing[position:])})
        updated_blocks.append(block)
    requirements_path.write_text(
        json.dumps(requirements.model_copy(update={"requirements": tuple(updated_requirements)}).model_dump(mode="json", exclude_unset=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    bindings_path.write_text(
        json.dumps(bindings.model_copy(update={"bindings": tuple(updated_bindings)}).model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    blocks_path.write_text(
        json.dumps(blocks.model_copy(update={"content_blocks": tuple(updated_blocks)}).model_dump(mode="json", exclude_unset=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Repaired {len(found)} page 48 requirements and added {len(REJECTION_CASES)} atomic rejection cases")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    repair(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
