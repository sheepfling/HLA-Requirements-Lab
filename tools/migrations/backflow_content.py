"""Focused 1516.1 backflow repair operations."""

from __future__ import annotations

from tools.migrations.backflow_common import (
    DDM,
    FEDERATION,
    OBJECTS,
    PAGE_216,
    TIME,
    _read,
    _set_clause,
    _set_statement,
    _write,
)


def repair_page_216() -> None:
    """Repair DDM page ownership and split definition statements."""
    requirements = _read("requirements.json")
    by_id = {item["id"]: item for item in requirements["requirements"]}
    corrections = {
        "66-19": (
            "A range shall be a continuous semi-open interval on a dimension. "
            "The interval is defined by an ordered pair of values.",
            66,
            71,
        ),
        "69-20": (
            "The first component of the pair shall be called range lower bound, "
            "and the second component shall be called range upper bound.",
            69,
            74,
        ),
        "72-21": (
            "The range upper bound shall be strictly greater than the range lower bound.",
            72,
            77,
        ),
        "78-23": (
            "The minimum possible difference between a range lower bound and a range upper bound "
            "shall be 1 (one).",
            75,
            80,
        ),
        "84-25": (
            "A region specification shall be a set of ranges.",
            84,
            86,
        ),
        "87-26": (
            "The dimensions contained in a region specification shall be the dimensions of "
            "the ranges that are included in the region specification.",
            84,
            89,
        ),
        "90-27": (
            "A region specification shall contain at most one range for any given dimension.",
            89,
            92,
        ),
        "93-28": (
            "Each range in a region specification shall be defined in terms of the bounds "
            "[0, the corresponding dimension\u2019s upper bound).",
            90,
            98,
        ),
    }
    for item in requirements["requirements"]:
        if not item["id"].startswith(PAGE_216):
            continue
        _set_clause(item, "9.1.1")
    for suffix, (statement, line, end_line) in corrections.items():
        record = by_id[PAGE_216 + suffix]
        _set_statement(record, statement, line, end_line)
    omitted_facets = {
        "66-19": "bound order, strict upper-greater-than-lower, and minimum unit span",
        "69-20": "the semi-open interval, strict upper-greater-than-lower, and minimum unit span",
        "72-21": "the semi-open interval, bound order, and minimum unit span",
        "78-23": (
            "the semi-open interval, bound order, and strict upper-greater-than-lower relation"
        ),
    }
    for suffix, missing in omitted_facets.items():
        record = by_id[PAGE_216 + suffix]
        record["semantic_group_id"] = "m16.range-definition.9.1.1"
        record["coverage_note"] = (
            "One facet of the continuous §9.1.1 range definition. Claim complete range "
            "semantics only when evidence covers all four consecutive stable candidate IDs, "
            f"including {missing}."
        )
    _write("requirements.json", requirements)

    for name, key in (
        ("content-blocks.json", "content_blocks"),
        ("content-elements.json", "content_elements"),
    ):
        payload = _read(name)
        affected = [item for item in payload[key] if "page-216" in item["id"]]
        if len(affected) != 1:
            raise ValueError(f"Expected one page-216 item in {name}, found {len(affected)}")
        affected[0]["clause_id"] = "clause-9"
        _write(name, payload)


def repair_page_219_region_relationships() -> None:
    """Keep the region rules before the 9.1.3.2 heading complete and in 9.1.3.1."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    corrections = {
        "11-3": (
            "A region specification may contain an empty set of ranges. The region realization "
            "derived from such a region specification shall contain only the dimensions for "
            "which the FDD defines a default range and that are available dimensions of the "
            "instance attribute, class attribute, interaction class, or sent interaction with "
            "which the region specification is being associated.",
            9,
            18,
        ),
        "23-7": (
            "A region specification with an empty set of ranges may result in a region "
            "realization that contains no dimensions if all available dimensions have the "
            "excluded indicator specified in the FDD; such a region realization shall not "
            "overlap with any other region realization, even the default region.",
            18,
            28,
        ),
        "50-16": (
            "If a federate invokes the Create Region service and then does not invoke the Set "
            "Range Bounds service or invokes the Set Range Bounds service for only some, but "
            "not all, of the dimensions that were specified when the region was created, "
            "followed by an invocation of the Commit Region Modifications service for that "
            "region, the Commit Region Modifications service shall throw the “Invalid region” "
            "exception because each region designator that is passed to the Commit Region "
            "Modifications service is required to have had the Set Range Bounds service "
            "invoked at least once for all of its dimensions.",
            42,
            60,
        ),
        "62-20": (
            "The effects of the Set Range Bounds service invocations that were made, if any, "
            "are still pending. They shall take effect if and when the Set Range Bounds "
            "service has been invoked at least once for all of the dimensions of the region, "
            "followed by the invocation of the Commit Region Modifications service for that "
            "region.",
            60,
            70,
        ),
        "86-28": (
            "If a federate invokes the Create Region service, followed by at least one Set "
            "Range Bounds service invocation for every one of the dimensions that were "
            "specified when the region was created, but does not invoke the Commit Region "
            "Modifications service, the region continues to be only a region template, not "
            "a region specification. The effects of the Set Range Bounds service invocations "
            "are still pending and shall take effect if and when the Commit Region "
            "Modifications service is successfully invoked for that region.",
            75,
            91,
        ),
    }
    for suffix, (statement, line, end_line) in corrections.items():
        record = by_id[DDM + "219-l" + suffix]
        _set_clause(record, "9.1.3.1")
        _set_statement(record, statement, line, end_line)
    _write("requirements.json", payload)


def repair_page_192_service_narrative() -> None:
    """Complete the Time Constrained Enabled prose before the 8.6.1 heading."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    corrections = {
        "93-27": (
            "When a joined federate changes to be time-constrained, TSO messages stored in "
            "the RTI\u2019s internal queues that have timestamps greater than or equal to the "
            "joined federate\u2019s logical time shall be delivered in TSO.",
            90,
            95,
        ),
        "99-29": (
            "TSO messages delivered to the joined federate before it becomes time-constrained, "
            "possibly including messages with timestamps greater than or equal to the joined "
            "federate\u2019s current logical time, shall be delivered as RO messages.",
            96,
            104,
        ),
    }
    for suffix, (statement, line, end_line) in corrections.items():
        record = by_id[TIME + "192-l" + suffix]
        _set_clause(record, "8.6")
        _set_statement(record, statement, line, end_line)
    _write("requirements.json", payload)


def repair_service_prose() -> None:
    """Restore complete service statements and the headings visible at each span."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    corrections = {
        FEDERATION + "040-l33-8": (
            "If a federate is forced to leave the joined state for any reason other than calling "
            "the Resign Federation Execution service, the Federate Resigned service notifies "
            "the federate that a fault has been detected and that it has been forced into the "
            "Not Joined state.",
            "4.1.1",
            43,
            53,
        ),
        FEDERATION + "040-l54-15": (
            "When a federate has resigned and has no further intent to join or create federation "
            "executions, it shall perform a Disconnect.",
            "4.1.1",
            51,
            56,
        ),
        FEDERATION + "044-l15-4": (
            "When a joined federate receives an Initiate Federate Save service invocation and "
            "subsequently saves its state, it shall use the federation save label (that was "
            "specified by the joined federate requesting the save in the Request Federation "
            "Save service), its federate type (that it specified when it joined the federation "
            "execution), and its federate designator (that was returned when it joined the "
            "federation execution) to distinguish the saved information.",
            "4.1.2",
            12,
            26,
        ),
        FEDERATION + "044-l27-8": (
            "Once a federation execution save has begun, an RTI shall save all queued messages "
            "that have not been delivered to the intended joined federates (e.g., future "
            "timestamp order (TSO) messages or receive order (RO) messages that were sent by "
            "other joined federates not yet in the Federate Save in Progress state).",
            "4.1.2",
            27,
            35,
        ),
        FEDERATION + "044-l36-11": (
            "All saved information (by both the RTI and the joined federates) shall be "
            "persistent, i.e., it is stored onto disk or some other persistent medium, and it "
            "remains intact even after the federation execution is destroyed.",
            "4.1.2",
            33,
            41,
        ),
        FEDERATION + "044-l54-17": (
            "Once a restore has begun, any messages that have not been delivered to the "
            "intended joined federates in the restoring federation execution shall be lost. "
            "After a restore is complete, the RTI shall deliver all related saved messages as "
            "appropriate to the joined federates in the restored federation execution (e.g., "
            "TSO messages at the federate\u2019s appropriate logical time position or RO messages "
            "as soon as possible in wall-clock time).",
            "4.1.2",
            48,
            62,
        ),
        FEDERATION + "044-l72-23": (
            "The number of federates of each federate type that are joined to the federation "
            "execution, however, shall be the same.",
            "4.1.2",
            69,
            74,
        ),
        FEDERATION + "044-l78-25": (
            "Declaring a federate to be of a given type shall be equivalent to asserting that "
            "the joined federate can be restored using the state information saved by any "
            "other joined federate of that type.",
            "4.1.2",
            75,
            83,
        ),
        OBJECTS + "143-l156-42": (
            "The Report Attribute Transportation Type service shall be used to provide the "
            "transportation type that is in use for the specified instance and instance attribute.",
            "6.29",
            156,
            161,
        ),
        OBJECTS + "143-l162-44": (
            "If the instance attribute is unowned, the transportation type specified in the "
            "FDD shall be reported. This service shall be invoked by the RTI at a joined "
            "federate in response to a Query Attribute Transportation Type service invocation "
            "by the same joined federate.",
            "6.29",
            159,
            167,
        ),
        TIME + "191-l73-17": (
            "The Enable Time Constrained service shall request that the joined federate "
            "invoking the service become time-constrained.",
            "8.5",
            73,
            78,
        ),
        TIME + "191-l76-18": (
            "The RTI shall indicate that the joined federate is time-constrained by invoking "
            "the Time Constrained Enabled service.",
            "8.5",
            76,
            81,
        ),
    }
    for requirement_id, (statement, clause, line, end_line) in corrections.items():
        record = by_id[requirement_id]
        _set_statement(record, statement, line, end_line)
        _set_clause(record, clause)
    _set_clause(by_id[FEDERATION + "044-l108-35"], "4.1.3")
    _write("requirements.json", payload)
