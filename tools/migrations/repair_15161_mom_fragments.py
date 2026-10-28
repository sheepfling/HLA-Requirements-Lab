"""Repair source-line fragments in the MOM interaction prose and list items."""

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

PREFIX = "requirement-candidate-content-clauses-"
REPAIRS: dict[str, tuple[str, int, int]] = {
    "289-l14-4": (
        "Interaction classes that are subclasses of HLAmanager.HLAfederate.HLAadjust and HLAmanager.HLAfederation.HLAadjust shall be acted on by the RTI.",
        8,
        16,
    ),
    "289-l26-8": (
        "Interaction classes that are subclasses of HLAmanager.HLAfederate.HLArequest shall be acted on by the RTI.",
        23,
        31,
    ),
    "289-l38-12": (
        "Interaction classes that are subclasses of HLAmanager.HLAfederate.HLAreport shall be sent by the RTI.",
        35,
        43,
    ),
    "289-l53-17": (
        "Interaction classes that are subclasses of HLAmanager.HLAfederate.HLAservice shall be acted on by the RTI.",
        50,
        58,
    ),
    "289-l56-18": (
        "Interaction classes that are subclasses of HLAmanager.HLAfederate.HLAservice shall invoke HLA services on behalf of another federate and shall cause the RTI to react as if that other federate had invoked the service.",
        50,
        64,
    ),
    "289-l80-26": (
        "The RTI shall publish at the MOM leaf-class level, for example HLAmanager.HLAfederate.HLAreport.HLAreportException.",
        80,
        85,
    ),
    "289-l101-33": (
        "If joined federates subscribe to the class of which an extension is a subclass, the interaction shall be promoted to the subscribed class and any new parameters shall be lost.",
        98,
        103,
    ),
    "290-l18-5": (
        "The RTI shall receive interaction classes that are subclasses of HLAmanager.HLAfederate.HLAadjust, HLAmanager.HLAfederate.HLArequest, HLAmanager.HLAfederate.HLAservice, and HLAmanager.HLAfederation.HLAadjust.",
        18,
        32,
    ),
    "290-l54-17": (
        "If a joined federate sends an interaction of this class, the RTI shall receive a promoted version containing only the parameters of the predefined interaction class.",
        51,
        59,
    ),
    "290-l66-21": (
        "If a joined federate sends an interaction with extra parameters, the RTI shall receive the new parameters but shall ignore them and process only the predefined parameters.",
        63,
        71,
    ),
    "290-l96-31": (
        "The RTI shall publish all leaf object classes in Table 6 that are designated with a P.",
        96,
        101,
    ),
    "290-l111-36": (
        "The RTI shall publish all leaf interaction classes in Table 7 that are designated with a P.",
        111,
        116,
    ),
    "290-l120-39": (
        "In response to an interaction of class HLAmanager.HLAfederate.HLArequest where the requested information does not exist at the designated federate, the RTI shall send the corresponding HLAmanager.HLAfederate.HLAreport interaction with values indicating a NULL response.",
        117,
        128,
    ),
    "290-l156-51": (
        "The RTI shall be actively subscribed to all leaf interaction classes in Table 7 that are designated with an S.",
        156,
        164,
    ),
    "290-l174-57": (
        "The RTI shall update the values of all attributes of instances of HLAmanager.HLAfederate found in Table 8 using an update region set that contains a single region.",
        174,
        179,
    ),
    "291-l8-2": (
        "The RTI shall send all HLAmanager.HLAfederate.HLAreport.HLAreportServiceInvocation interactions using an update region set that contains a single region.",
        8,
        13,
    ),
    "291-l47-15": (
        "The RTI shall send all other interactions that are subclasses of HLAmanager.HLAfederate.HLAreport in Table 7 using an update region set that contains a single region.",
        47,
        52,
    ),
    "291-l74-24": (
        "Other than registering and deleting object instances, updating instance attributes, and sending and receiving interactions, the RTI shall not engage in any other activity with regard to MOM.",
        71,
        76,
    ),
    "291-l77-25": ("An RTI shall never perform any of the following MOM activities:", 77, 82),
    "291-l113-37": (
        "A federate shall not be required to supply parameters of an HLAmanager.HLAfederate.HLAservice interaction that correspond to optional arguments of the HLA service that the interaction is intended to invoke on behalf of another federate.",
        113,
        136,
    ),
    "291-l146-48": (
        "A federate shall supply at least one parameter of the HLAmanager.HLAfederate.HLAadjust.HLAsetSwitches interaction.",
        143,
        178,
    ),
}


def repair(root: Path) -> None:
    requirement_path = root / "semantic/requirements.json"
    binding_path = root / "semantic/api-requirement-bindings.json"
    requirements = RequirementFile.model_validate_json(requirement_path.read_text(encoding="utf-8"))
    bindings = RequirementApiBindingFile.model_validate_json(
        binding_path.read_text(encoding="utf-8")
    )
    found = set()
    sources = {}
    changed = []
    for requirement in requirements.requirements:
        if not requirement.id.startswith(PREFIX):
            changed.append(requirement)
            continue
        suffix = requirement.id.rsplit("page-", 1)[-1]
        if suffix not in REPAIRS:
            changed.append(requirement)
            continue
        statement, start, end = REPAIRS[suffix]
        source = requirement.source.model_copy(update={"line": start, "end_line": end})
        sources[requirement.id] = source
        found.add(suffix)
        changed.append(
            requirement.model_copy(
                update={
                    "statement": statement,
                    "machine_statement": _machine_statement(statement, HLA_SOURCE),
                    "source": source,
                }
            )
        )
    if found != REPAIRS.keys():
        raise ValueError(f"Missing MOM records: {sorted(REPAIRS.keys() - found)}")
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
    print(f"Repaired {len(found)} MOM source-line fragments")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    repair(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
