"""Separate reviewed obligations that share one printed source sentence."""

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

# Each pair retains its ID, repeats the source condition, and expresses one
# normative effect. Source spans cover the complete printed sentence.
REPAIRS: dict[str, tuple[str, int, int]] = {
    "04-federation-management-page-050-l24-7": (
        "The last known time position shall be determined by the RTI for a lost federate.",
        24,
        32,
    ),
    "04-federation-management-page-050-l27-8": (
        "TSO messages sent by a lost federate with timestamps less than or equal to its last known time position shall be delivered to the subscribed joined federates that remain in the federation.",
        24,
        32,
    ),
    "04-federation-management-page-073-l160-46": (
        "Should more than one joined federate attempt to restore the federation at a given point, at most one joined federate shall receive a positive indication through this service.",
        157,
        165,
    ),
    "04-federation-management-page-073-l163-47": (
        "Should more than one joined federate attempt to restore the federation at a given point, all other joined federates shall receive a negative indication through this service.",
        157,
        165,
    ),
    "04-federation-management-page-076-l18-2": (
        "If the restore was successful, the joined federate shall be in the state that either it or some other joined federate of its type was in when the federation save associated with the label occurred.",
        18,
        29,
    ),
    "04-federation-management-page-076-l24-4": (
        "If the restore was successful, the joined federate shall be waiting for an invocation of the Federation Restored service.",
        18,
        29,
    ),
    "04-federation-management-page-076-l156-41": (
        "The Federation Restored service shall inform the joined federate that the federation restore process is complete.",
        156,
        161,
    ),
    "04-federation-management-page-076-l159-42": (
        "The Federation Restored service shall indicate to the joined federate whether the federation restore process completed successfully.",
        156,
        161,
    ),
    "04-federation-management-page-077-l71-21": (
        "If a joined federate that received an invocation of the Federation Restore Begun service resigns before the Federation Restored service is invoked, the resignation shall be considered a failure of the federation restoration.",
        65,
        76,
    ),
    "04-federation-management-page-077-l74-22": (
        "If a joined federate that received an invocation of the Federation Restore Begun service resigns before the Federation Restored service is invoked, the Federation Restored service shall be invoked with a restore-success indicator of failure.",
        65,
        76,
    ),
    "05-declaration-management-page-090-l22-4": (
        "If no update rate is specified, the attributes shall be considered to be subscribed with the default update rate.",
        22,
        27,
    ),
    "05-declaration-management-page-090-l25-5": (
        "If no update rate is specified, no update rate reduction shall take place.",
        22,
        27,
    ),
    "05-declaration-management-page-091-l127-37": (
        "The joined federate shall lose ownership of all owned instance attributes whose corresponding class attributes are unpublished by the service invocation.",
        127,
        135,
    ),
    "05-declaration-management-page-091-l130-38": (
        "When the corresponding class attributes are unpublished by the service invocation, the joined federate shall no longer be able to update those instance attributes.",
        127,
        135,
    ),
    "05-declaration-management-page-097-l23-5": (
        "If no update rate is specified, the attributes shall be considered to be subscribed with the default update rate.",
        23,
        28,
    ),
    "05-declaration-management-page-097-l26-6": (
        "If no update rate is specified, no update rate reduction shall take place.",
        23,
        28,
    ),
    "06-object-management-page-118-l34-7": (
        "An object instance handle shall be uniform throughout the federation execution.",
        34,
        42,
    ),
    "06-object-management-page-118-l37-8": (
        "For a particular object instance, the handle provided to the joined federate that registers it shall be the same handle provided to all joined federates that discover it.",
        34,
        42,
    ),
    "06-object-management-page-118-l58-15": (
        "If the optional object instance name argument is supplied, that name shall have been successfully reserved by the registering federate as indicated by the Object Instance Name Reserved or Multiple Object Instance Names Reserved service.",
        58,
        66,
    ),
    "06-object-management-page-118-l64-17": (
        "If the optional object instance name argument is supplied, that name shall be coadunated with the object instance.",
        58,
        66,
    ),
    "06-object-management-page-118-l67-18": (
        "If the optional object instance name argument is not supplied, the RTI shall create a federation execution-wide unique name.",
        64,
        72,
    ),
    "06-object-management-page-118-l70-19": (
        "If the optional object instance name argument is not supplied, the name created by the RTI shall be coadunated with the object instance.",
        64,
        72,
    ),
    "07-ownership-management-page-154-l99-31": (
        "If one instance attribute supplied to an ownership management service invocation violates the service preconditions, an exception shall be generated.",
        93,
        104,
    ),
    "07-ownership-management-page-154-l102-32": (
        "If one instance attribute supplied to an ownership management service invocation violates the service preconditions, the entire service invocation shall fail.",
        93,
        104,
    ),
    "07-ownership-management-page-154-l156-49": (
        "As long as the instance attribute remains unowned, the RTI shall try to identify joined federates other than the divesting joined federate that are willing to own it.",
        156,
        167,
    ),
    "07-ownership-management-page-154-l162-51": (
        "Once the instance attribute becomes owned, the RTI shall not invoke the Request Attribute Ownership Assumption service at any additional joined federates.",
        156,
        167,
    ),
    "07-ownership-management-page-162-l22-6": (
        "If a joined federate invokes Attribute Ownership Acquisition for an instance attribute for which it is in the Acquiring state, it shall continue to be in the Acquiring state with respect to that attribute.",
        19,
        30,
    ),
    "07-ownership-management-page-162-l28-8": (
        "If a joined federate invokes Attribute Ownership Acquisition for an instance attribute for which it is in the Acquiring state, the joined federate that owns the instance attribute shall not receive a corresponding Request Attribute Ownership Release invocation.",
        19,
        30,
    ),
    "07-ownership-management-page-162-l52-16": (
        "If a joined federate invokes Attribute Ownership Acquisition for an instance attribute for which it is in the Trying to Cancel Acquisition state, it shall continue to be in the Trying to Cancel Acquisition state with respect to that attribute.",
        49,
        63,
    ),
    "07-ownership-management-page-162-l58-18": (
        "If a joined federate invokes Attribute Ownership Acquisition for an instance attribute for which it is in the Trying to Cancel Acquisition state, the joined federate that owns the instance attribute shall not receive a corresponding Request Attribute Ownership Release invocation.",
        49,
        63,
    ),
    "08-time-management-page-178-l81-24": (
        "The Time Advance Grant service shall be used to grant an advance for all forms of request to advance logical time except Flush Queue Request.",
        81,
        86,
    ),
    "08-time-management-page-178-l84-25": (
        "A Flush Queue Request shall be granted by the Flush Queue Grant service.",
        81,
        86,
    ),
    "08-time-management-page-178-l87-26": (
        "Both the Time Advance Grant and Flush Queue Grant services shall provide a logical time as an argument.",
        87,
        92,
    ),
    "08-time-management-page-178-l90-27": (
        "The logical time provided by the Time Advance Grant or Flush Queue Grant service shall be the joined federate’s new time position.",
        87,
        92,
    ),
    "09-data-distribution-management-page-229-l23-6": (
        "If the optional object instance name argument is supplied, that name shall have been successfully reserved as indicated by the Object Instance Name Reserved service.",
        23,
        28,
    ),
    "09-data-distribution-management-page-229-l26-7": (
        "If the optional object instance name argument is supplied, that name shall be coadunated with the object instance.",
        23,
        28,
    ),
    "09-data-distribution-management-page-229-l29-8": (
        "If the optional object instance name argument is not supplied, the RTI shall create a federation execution-wide unique name.",
        29,
        34,
    ),
    "09-data-distribution-management-page-229-l32-9": (
        "If the optional object instance name argument is not supplied, the name created by the RTI shall be coadunated with the object instance.",
        29,
        34,
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
        suffix = requirement.id.removeprefix(PREFIX)
        if suffix not in REPAIRS or not requirement.id.startswith(PREFIX):
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
        raise ValueError(f"Missing shared-sentence records: {sorted(REPAIRS.keys() - found)}")
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
    changed_bindings = [
        binding.model_copy(update={"source": sources[binding.requirement_id]})
        if binding.requirement_id in sources
        else binding
        for binding in bindings.bindings
    ]
    binding_path.write_text(
        json.dumps(
            bindings.model_copy(update={"bindings": tuple(changed_bindings)}).model_dump(
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
    print(f"Repaired {len(found)} shared-sentence obligations")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    repair(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
