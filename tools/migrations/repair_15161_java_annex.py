"""Repair reviewed Java API annex requirements split across PDF text boxes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import RequirementApiBindingFile, RequirementFile, load_document_model
from hla_lab.core.semantic_text import _machine_statement
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.workspace import document_root

PREFIX = "requirement-candidate-content-clauses-11-management-object-model-page-"

# Suffix, source-faithful atomic obligation, first/last layout-body source line.
REPAIRS: dict[str, tuple[str, int, int]] = {
    "373-l269-88": ("The RTI implementer’s implementation of AttributeHandleValueMap shall adhere to the constraints in §12.11.6.16.", 260, 271),
    "373-l287-94": ("If an AttributeHandleValueMap key is not an AttributeHandle, IllegalArgumentException shall be thrown.", 275, 292),
    "373-l308-101": ("If an AttributeHandleValueMap value is not a byte array, IllegalArgumentException shall be thrown.", 296, 313),
    "373-l323-106": ("All java.util.Map operations shall be implemented for AttributeHandleValueMap; none are optional.", 317, 325),
    "373-l344-113": ("The AttributeHandleValueMapFactory interface shall be implemented.", 338, 346),
    "373-l353-116": ("The implementation class for AttributeHandleValueMap shall be hidden from the federate programmer.", 347, 355),
    "374-l10-2": ("The federate programmer shall obtain a reference to an AttributeHandleValueMapFactory instance through the getAttributeHandleValueMapFactory() method on RTIambassador.", 7, 54),
    "374-l97-31": ("The RTI implementer’s implementation of ParameterHandleValueMap shall adhere to the constraints in §12.11.6.17.", 91, 102),
    "374-l118-38": ("If a ParameterHandleValueMap key is not a ParameterHandle, IllegalArgumentException shall be thrown.", 106, 123),
    "374-l139-45": ("If a ParameterHandleValueMap value is not a byte array, IllegalArgumentException shall be thrown.", 127, 144),
    "374-l154-50": ("All java.util.Map operations shall be implemented for ParameterHandleValueMap; none are optional.", 148, 156),
    "374-l175-57": ("The ParameterHandleValueMapFactory interface shall be implemented.", 169, 177),
    "374-l184-60": ("The implementation class for ParameterHandleValueMap shall be hidden from the federate programmer.", 178, 184),
    "374-l379-125": ("If an RTI implementation allows an additional transportation type, it shall accept that transportation type name in the FDD.", 376, 381),
    "374-l382-126": ("If an RTI implementation allows an additional transportation type, it shall return a valid Transportation Type Handle for the Get Transportation Type Handle service.", 376, 401),
    "375-l315-103": ("The RTI implementer’s implementation of AttributeSetRegionSetPairList shall adhere to the constraints in §12.11.6.23.", 315, 320),
    "375-l354-116": ("If an AttributeSetRegionSetPairList element is not an AttributeRegionAssociation, IllegalArgumentException shall be thrown.", 324, 356),
    "375-l366-120": ("All java.util.List operations shall be implemented for AttributeSetRegionSetPairList; none are optional.", 360, 368),
    "375-l384-126": ("No AttributeSetRegionSetPairList operation shall accept an incommensurate type.", 384, 386),
    "375-l390-128": ("If an AttributeSetRegionSetPairList operation receives an incommensurate type, IllegalArgumentException shall be thrown.", 384, 395),
    "375-l429-141": ("The LogicalTime and LogicalTimeInterval interfaces shall have a toString() method that yields a representation suitable for printing.", 420, 440),
    "375-l468-154": ("The LogicalTime.hashCode() method shall return an equal integer value for any two LogicalTime instances for which equals() returns true.", 462, 482),
    "375-l489-161": ("The LogicalTime.encodedLength() method shall return the size of the buffer required to encode the object.", 483, 491),
    "376-l19-5": ("The LogicalTime.encode() method shall encode the object into a byte array at the supplied offset position.", 7, 30),
    "376-l49-15": ("The LogicalTimeInterval.hashCode() method shall return an equal integer value for any two instances for which equals() returns true.", 43, 63),
    "376-l70-22": ("The LogicalTimeInterval.encodedLength() method shall return the size of the buffer required to encode the object.", 64, 72),
    "376-l85-27": ("The LogicalTimeInterval.encode() method shall encode the object into a byte array at the supplied offset position.", 73, 96),
    "376-l229-75": ("A time implementation shall register as a service by creating a file in the services subdirectory of the META-INF directory in the JAR file containing that implementation.", 229, 234),
    "376-l232-76": ("The registration file shall be named hla.rti1516_2025.LogicalTimeFactory and contain a line specifying the class that implements the LogicalTimeFactory interface.", 232, 249),
    "376-l319-105": ("The getName() methods of the HLAinteger64TimeFactory and HLAfloat64TimeFactory implementations shall return the symbolic names ‘HLAinteger64Time’ and ‘HLAfloat64Time’, respectively.", 301, 323),
    "376-l397-131": ("When the federate supplies an interface to LogicalTimeFactoryFactory instead of a symbolic name, the returned time factory shall implement that interface.", 343, 399),
}

ADDED: dict[str, tuple[str, str, int, int]] = {
    "374-l184-60-rti-factory": (
        "374-l184-60",
        "The RTI shall provide the federate programmer a reference to a ParameterHandleValueMapFactory instance through the getParameterHandleValueMapFactory() method on RTIambassador.",
        184, 229,
    ),
    "374-l382-126-return-name": (
        "374-l382-126",
        "If an RTI implementation allows an additional transportation type, it shall return a valid Transportation Type Name for the Get Transportation Type Name service.",
        376, 420,
    ),
}


def repair(root: Path) -> None:
    requirement_path = root / "semantic/requirements.json"
    binding_path = root / "semantic/api-requirement-bindings.json"
    content_path = root / "semantic/content-blocks.json"
    requirements = RequirementFile.model_validate_json(requirement_path.read_text(encoding="utf-8"))
    bindings = RequirementApiBindingFile.model_validate_json(binding_path.read_text(encoding="utf-8"))
    found: set[str] = set()
    changed = []
    added_ids = {PREFIX + suffix for suffix in ADDED}
    existing_ids = {item.id for item in requirements.requirements}
    source_by_id = {}
    for requirement in requirements.requirements:
        suffix = requirement.id.removeprefix(PREFIX)
        if not requirement.id.startswith(PREFIX) or suffix not in REPAIRS:
            changed.append(requirement)
            continue
        statement, start, end = REPAIRS[suffix]
        source = requirement.source.model_copy(update={"line": start, "end_line": end})
        extras = requirement.additional_sources
        if suffix == "374-l10-2":
            extras = (requirement.source.model_copy(update={
                "path": "content/clauses/11-management-object-model-page-373.tex",
                "line": 353,
                "end_line": 355,
            }),)
        changed.append(requirement.model_copy(update={
            "statement": statement,
            "machine_statement": _machine_statement(statement, HLA_SOURCE),
            "source": source,
            "additional_sources": extras,
        }))
        source_by_id[requirement.id] = source
        found.add(suffix)
        for new_suffix, (base_suffix, new_statement, new_start, new_end) in ADDED.items():
            if suffix != base_suffix or PREFIX + new_suffix in existing_ids:
                continue
            new_source = source.model_copy(update={"line": new_start, "end_line": new_end})
            changed.append(requirement.model_copy(update={
                "id": PREFIX + new_suffix,
                "title": f"Normative statement at {new_source.path}:{new_source.line}",
                "statement": new_statement,
                "machine_statement": _machine_statement(new_statement, HLA_SOURCE),
                "source": new_source,
                "semantic_group_id": requirement.semantic_group_id,
            }))
            source_by_id[PREFIX + new_suffix] = new_source
    if found != REPAIRS.keys():
        raise ValueError(f"Missing Java annex records: {sorted(REPAIRS.keys() - found)}")
    requirement_path.write_text(
        json.dumps(requirements.model_copy(update={"requirements": tuple(changed)}).model_dump(mode="json", exclude_unset=True), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    content = json.loads(content_path.read_text(encoding="utf-8"))
    for block in content["content_blocks"]:
        if block["id"] != "content-15161-page-374":
            continue
        for new_suffix, (base_suffix, _, _, _) in ADDED.items():
            new_id = PREFIX + new_suffix
            if PREFIX + base_suffix in block["record_ids"] and new_id not in block["record_ids"]:
                block["record_ids"].append(new_id)
    content_path.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    updated_bindings = [
        binding.model_copy(update={"source": source_by_id[binding.requirement_id]})
        if binding.requirement_id in source_by_id else binding
        for binding in bindings.bindings
    ]
    binding_path.write_text(
        json.dumps(bindings.model_copy(update={"bindings": tuple(updated_bindings)}).model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    rebuilt = build_requirement_api_bindings(load_document_model(root, HLA_SOURCE))
    binding_path.write_text(
        json.dumps(bindings.model_copy(update={"bindings": rebuilt}).model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Repaired {len(found)} Java annex fragments and added {len(added_ids - existing_ids)} obligations")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    repair(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
