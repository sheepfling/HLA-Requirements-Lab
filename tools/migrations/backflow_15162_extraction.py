"""Repair source-backed 1516.2 candidate boundaries and clause ownership."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _record(records: list[dict[str, Any]], record_id: str) -> dict[str, Any]:
    for item in records:
        if item["id"] == record_id:
            return item
    raise ValueError(f"Missing semantic record: {record_id}")


def _source(path: str, line: int, end_line: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"path": path, "line": line}
    if end_line is not None:
        result["end_line"] = end_line
    return result


def _append_source(requirement: dict[str, Any], source: dict[str, Any]) -> None:
    sources = requirement.setdefault("additional_sources", [])
    if source not in sources:
        sources.append(source)


def _new_companion(
    template: dict[str, Any],
    *,
    record_id: str,
    title: str,
    statement: str,
    source_path: str,
    source_line: int,
    semantic_group_id: str | None = None,
) -> dict[str, Any]:
    companion = deepcopy(template)
    companion.update(
        {
            "id": record_id,
            "title": title,
            "statement": statement,
            "machine_statement": statement,
            "source": _source(source_path, source_line, source_line),
            "additional_sources": [],
        }
    )
    if semantic_group_id is not None:
        companion["semantic_group_id"] = semantic_group_id
    return companion


def _insert_after(records: list[dict[str, Any]], anchor_id: str, new_record: dict[str, Any]) -> None:
    records[:] = [item for item in records if item["id"] != new_record["id"]]
    anchor = next(index for index, item in enumerate(records) if item["id"] == anchor_id)
    records.insert(anchor + 1, new_record)


def _link_elements(
    elements: list[dict[str, Any]],
    *,
    page: str,
    target_record_ids: set[str],
    links: dict[str, tuple[str, ...]],
    clause_by_element: dict[str, str] | None = None,
) -> None:
    clause_by_element = clause_by_element or {}
    for element in elements:
        if page not in element.get("id", ""):
            continue
        existing = [
            record_id
            for record_id in element.get("record_ids", [])
            if record_id not in target_record_ids
        ]
        element["record_ids"] = existing + list(links.get(element["id"], ()))
        if element["id"] in clause_by_element:
            element["clause_id"] = clause_by_element[element["id"]]


def _extend_block_records(
    blocks: list[dict[str, Any]], block_id: str, record_ids: tuple[str, ...]
) -> None:
    block = next((item for item in blocks if item["id"] == block_id), None)
    if block is None:
        raise ValueError(f"Missing content block: {block_id}")
    for record_id in record_ids:
        if record_id not in block["record_ids"]:
            block["record_ids"].append(record_id)


def repair_15162_backflow(repository_root: Path) -> None:
    """Apply idempotent source corrections for RL-438/439/440/446/449/452."""

    semantic_root = repository_root / "topics/ieee/hla-1516.2-2025/semantic"
    requirements_payload = _read(semantic_root / "requirements.json")
    elements_payload = _read(semantic_root / "content-elements.json")
    blocks_payload = _read(semantic_root / "content-blocks.json")
    requirements: list[dict[str, Any]] = requirements_payload["requirements"]
    elements: list[dict[str, Any]] = elements_payload["content_elements"]
    blocks: list[dict[str, Any]] = blocks_payload["content_blocks"]

    # RL-438: the two page-113 update-rate criteria inherit Annex C.7 from
    # page 112; the page-level Clause 7 source file spans several annex clauses.
    c7_ids = (
        "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l10-2",
        "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-113-l18-4",
    )
    for record_id in c7_ids:
        requirement = _record(requirements, record_id)
        requirement.update(
            {
                "clause": "C.7",
                "clause_id": "clause-C.7",
                "semantic_group_id": "m17.clause-C.7",
                "coverage_note": (
                    "Source-derived normative statement owned by Annex C.7. The C.7 heading on "
                    "page 112 governs this page-113 continuation before the C.8 heading."
                ),
            }
        )
    _link_elements(
        elements,
        page="content-element-content-15162-page-113",
        target_record_ids=set(c7_ids),
        links={
            "content-element-content-15162-page-113-list-item-004": (c7_ids[0],),
            "content-element-content-15162-page-113-paragraph-007": (c7_ids[1],),
        },
    )

    # RL-439: separate Table 4 hierarchy, naming, SOM marker values, and FOM
    # classification obligations while preserving the original candidate IDs.
    p40_path = "sections/semantic/clause-4a/page-040.tex"
    p40_hierarchy = (
        "The object class structure template of Table 4 provides a format for representing "
        "the class-subclass hierarchy of object classes. It shall be populated by first "
        "entering the root class of all object classes in the left-most column; this object "
        "class is named ‘HLAobjectRoot.’ Then, the most general object classes shall be entered "
        "in the next column, followed by all of their immediate subclasses in the next column, "
        "and then further levels of subclasses, as required. The number of intermediate columns "
        "used depends on the needs of the federate or federation. A federate or federation that "
        "uses a deeper hierarchy than illustrated by the template of the table shall add columns "
        "as needed. Finally, the most specific object classes shall be specified in the "
        "right-most column."
    )
    p40_names = "Object class names shall adhere to HLA naming conventions (see 3.3.1)."
    p40_markers = (
        "For a SOM or SOM module, valid entries for <p/s> shall be as follows: P (Publish): "
        "the federate is capable of publishing at least one attribute of the object class; "
        "S (Subscribe): the federate is capable of subscribing to at least one attribute of the "
        "object class; PS (PublishSubscribe): the federate is capable of publishing at least one "
        "attribute and subscribing to at least one attribute of the object class; and N (Neither): "
        "the federate is incapable of either publishing or subscribing to any attributes of the "
        "object class."
    )
    p40_fom = (
        "For a FOM or FOM module, the same entries for <p/s> are valid. However, an object class "
        "is classified as Publish or Subscribe in the federation if at least one federate is "
        "capable of publishing or subscribing to at least one attribute in the context of the "
        "object class."
    )
    p40_instances = (
        "Classes designated as Subscribe or Neither can have no registered instances, but they "
        "can have subclasses that can be registered."
    )
    p40_hierarchy_id = "requirement-candidate-sections-semantic-clause-4a-page-040-l18-3"
    p40_markers_id = "requirement-candidate-sections-semantic-clause-4a-page-040-l30-6"
    hierarchy = _record(requirements, p40_hierarchy_id)
    hierarchy.update(
        {
            "title": "Object class structure table shall represent the full class hierarchy",
            "statement": p40_hierarchy,
            "machine_statement": p40_hierarchy,
        }
    )
    markers = _record(requirements, p40_markers_id)
    markers.update(
        {
            "title": "SOM object class entries shall describe publish and subscribe capability",
            "statement": p40_markers,
            "machine_statement": p40_markers,
        }
    )

    p40_name_id = p40_hierarchy_id + "-naming"
    p40_fom_id = p40_markers_id + "-fom-classification"
    p40_instance_id = p40_markers_id + "-instance-eligibility"
    _insert_after(
        requirements,
        p40_hierarchy_id,
        _new_companion(
            hierarchy,
            record_id=p40_name_id,
            title="Object class names follow HLA naming conventions",
            statement=p40_names,
            source_path=p40_path,
            source_line=18,
            semantic_group_id=hierarchy["semantic_group_id"],
        ),
    )
    _insert_after(
        requirements,
        p40_markers_id,
        _new_companion(
            markers,
            record_id=p40_fom_id,
            title="FOM publication and subscription markers use federation-wide capability",
            statement=p40_fom,
            source_path=p40_path,
            source_line=50,
            semantic_group_id=markers["semantic_group_id"],
        ),
    )
    _insert_after(
        requirements,
        p40_fom_id,
        _new_companion(
            markers,
            record_id=p40_instance_id,
            title="Subscribe and Neither classes may have registered subclasses",
            statement=p40_instances,
            source_path=p40_path,
            source_line=54,
            semantic_group_id=markers["semantic_group_id"],
        ),
    )

    p40_targets = {
        p40_hierarchy_id,
        p40_name_id,
        "requirement-candidate-sections-semantic-clause-4a-page-040-l22-4",
        "requirement-candidate-sections-semantic-clause-4a-page-040-l26-5",
        p40_markers_id,
        p40_fom_id,
        p40_instance_id,
    }
    p40_links: dict[str, tuple[str, ...]] = {
        "content-element-content-15162-page-040-paragraph-003": (p40_hierarchy_id, p40_name_id),
        "content-element-content-15162-page-040-paragraph-004": (
            "requirement-candidate-sections-semantic-clause-4a-page-040-l22-4",
        ),
        "content-element-content-15162-page-040-paragraph-005": (
            "requirement-candidate-sections-semantic-clause-4a-page-040-l26-5",
        ),
        "content-element-content-15162-page-040-paragraph-006": (p40_markers_id,),
        "content-element-content-15162-page-040-list-007": (p40_markers_id,),
        "content-element-content-15162-page-040-list-item-008": (p40_markers_id,),
        "content-element-content-15162-page-040-list-009": (p40_markers_id,),
        "content-element-content-15162-page-040-list-item-010": (p40_markers_id,),
        "content-element-content-15162-page-040-list-011": (p40_markers_id,),
        "content-element-content-15162-page-040-list-item-012": (p40_markers_id,),
        "content-element-content-15162-page-040-list-013": (p40_markers_id,),
        "content-element-content-15162-page-040-list-item-014": (p40_markers_id,),
        "content-element-content-15162-page-040-paragraph-015": (p40_fom_id,),
        "content-element-content-15162-page-040-paragraph-016": (p40_instance_id,),
    }
    _link_elements(
        elements,
        page="content-element-content-15162-page-040",
        target_record_ids=p40_targets,
        links=p40_links,
    )
    _extend_block_records(
        blocks,
        "content-15162-page-040",
        (p40_name_id, p40_fom_id, p40_instance_id),
    )

    # RL-440: join the page-break continuation to the page-52 interaction-table
    # rule and retain the final all-classes instruction as its own complete item.
    p52_id = "requirement-candidate-sections-semantic-clause-4b-page-052-l54-10"
    p53_id = "requirement-candidate-sections-semantic-clause-4b-page-053-l35-1"
    p52 = _record(requirements, p52_id)
    p52_statement = (
        "The first column (Interaction) shall contain names of interaction classes from the "
        "interaction class structure table. Interaction class names shall include the parentage "
        "(superclasses) of the class to the depth necessary to uniquely identify the class in this "
        "table and may include the full parentage of the class. In general, to reduce redundancy, "
        "parameters should be specified for classes at the highest point in the hierarchy in which "
        "they represent useful information, although this is not required. For example, if all "
        "weapon firings include a parameter that defines the infrared signature of the platform at "
        "the time the firing occurs, some redundancy would be avoided if this parameter is specified "
        "just once at the uppermost level of a WeaponFires class. Given that all interaction "
        "subclasses inherit the parameter types of their superclasses, the subclasses of "
        "WeaponFires, such as TankFires and Shipfires, also have this parameter with its specified "
        "characteristics."
    )
    p52.update(
        {
            "title": "Parameter table shall identify interaction classes and their parameter inheritance",
            "statement": p52_statement,
            "machine_statement": p52_statement,
        }
    )
    _append_source(
        p52,
        _source("sections/semantic/clause-4b/page-053.tex", 35, 35),
    )
    p53 = _record(requirements, p53_id)
    p53_statement = (
        "All interaction classes shall be included in this table so that transportation and order "
        "can be specified."
    )
    p53.update(
        {
            "title": "All interaction classes shall be included to specify transportation and order",
            "statement": p53_statement,
            "machine_statement": p53_statement,
            "clause": "4.6.2",
            "clause_id": "clause-4.6.2",
            "semantic_group_id": p52["semantic_group_id"],
        }
    )
    _link_elements(
        elements,
        page="content-element-content-15162-page-052",
        target_record_ids={p52_id},
        links={"content-element-content-15162-page-052-paragraph-009": (p52_id,)},
    )
    _link_elements(
        elements,
        page="content-element-content-15162-page-053",
        target_record_ids={p53_id},
        links={"content-element-content-15162-page-053-paragraph-001": (p52_id, p53_id)},
    )
    _extend_block_records(blocks, "content-15162-page-053", (p52_id, p53_id))

    # RL-446: fixed-record requirements belong to the explicit 4.14.10.1
    # heading, including the page-81 continuation before 4.14.10.2 begins.
    fixed_record_ids = (
        "requirement-candidate-sections-semantic-clause-4c-page-080-l69-6",
        "requirement-candidate-sections-semantic-clause-4c-page-080-l73-7",
        "requirement-candidate-sections-semantic-clause-4c-page-081-l36-2",
    )
    for record_id in fixed_record_ids:
        requirement = _record(requirements, record_id)
        if record_id == fixed_record_ids[0]:
            requirement["title"] = "Fixed record components shall follow declaration order and begin at offset zero"
        elif record_id == fixed_record_ids[1]:
            requirement["title"] = "Fixed record components shall be padded to satisfy alignment"
        else:
            requirement["title"] = "Fixed record shall not add padding after its last component"
        requirement.update(
            {
                "clause": "4.14.10.1",
                "clause_id": "clause-4.14.10.1",
                "semantic_group_id": "m17.clause-4.14.10.1",
                "coverage_note": (
                    "Source-derived normative statement owned by Clause 4.14.10.1, HLAfixedRecord. "
                    "The page-81 continuation remains in this subsection until the 4.14.10.2 heading."
                ),
            }
        )
    _link_elements(
        elements,
        page="content-element-content-15162-page-080",
        target_record_ids=set(fixed_record_ids[:2]),
        links={
            "content-element-content-15162-page-080-paragraph-012": (fixed_record_ids[0],),
            "content-element-content-15162-page-080-paragraph-013": (fixed_record_ids[1],),
        },
        clause_by_element={
            "content-element-content-15162-page-080-paragraph-012": "clause-4.14.10.1",
            "content-element-content-15162-page-080-paragraph-013": "clause-4.14.10.1",
        },
    )
    _link_elements(
        elements,
        page="content-element-content-15162-page-081",
        target_record_ids={fixed_record_ids[2]},
        links={"content-element-content-15162-page-081-paragraph-002": (fixed_record_ids[2],)},
        clause_by_element={
            "content-element-content-15162-page-081-paragraph-002": "clause-4.14.10.1"
        },
    )

    # RL-449: join the page-78 continuation to the stable page-77 requirement.
    variant_encoding_id = "requirement-candidate-sections-semantic-clause-4c-page-077-l86-9"
    variant_encoding = _record(requirements, variant_encoding_id)
    variant_encoding_statement = (
        "The eighth column (Encoding) shall describe, in detail, the encoding of the variant "
        "record data type (e.g., the location of the discriminant) as delivered to and received "
        "from the RTI. Encoding of fields in a variant record is determined by the data type "
        "specified in the Alternative type column. Encoding of the variant record is determined "
        "by the encoding specified in the Encoding column. Record data should be interpreted first "
        "through the record encoding scheme and then through the encoding scheme of the field’s "
        "data type."
    )
    variant_encoding.update(
        {
            "title": "Variant record Encoding shall describe record and field encodings",
            "statement": variant_encoding_statement,
            "machine_statement": variant_encoding_statement,
        }
    )
    _append_source(
        variant_encoding,
        _source("sections/semantic/clause-4c/page-078.tex", 52, 52),
    )
    _link_elements(
        elements,
        page="content-element-content-15162-page-078",
        target_record_ids={variant_encoding_id},
        links={"content-element-content-15162-page-078-paragraph-001": (variant_encoding_id,)},
    )
    _extend_block_records(blocks, "content-15162-page-078", (variant_encoding_id,))

    # RL-452: retain the previous-page sentence that completes the word
    # "alternatives" and the complete Table 39 format statement.
    variant_table_id = "requirement-candidate-sections-semantic-clause-4c-page-077-l54-1"
    variant_table = _record(requirements, variant_table_id)
    variant_table_statement = (
        "The non-extendable encoding does not allow the addition of new alternatives, and all "
        "FOM/SOM modules shall provide the same alternatives. The two encodings are further "
        "described in 4.14.10. Table 39 illustrates the format that shall be used for the variant "
        "record data type table."
    )
    variant_table.update(
        {
            "title": "Variant record table format and non-extendable alternatives",
            "statement": variant_table_statement,
            "machine_statement": variant_table_statement,
        }
    )
    _append_source(
        variant_table,
        _source("sections/semantic/clause-4c/page-076.tex", 80, 80),
    )
    _link_elements(
        elements,
        page="content-element-content-15162-page-076",
        target_record_ids={variant_table_id},
        links={"content-element-content-15162-page-076-paragraph-008": (variant_table_id,)},
    )
    _extend_block_records(blocks, "content-15162-page-076", (variant_table_id,))

    _write(semantic_root / "requirements.json", requirements_payload)
    _write(semantic_root / "content-elements.json", elements_payload)
    _write(semantic_root / "content-blocks.json", blocks_payload)


if __name__ == "__main__":
    repair_15162_backflow(Path(__file__).resolve().parents[2])
