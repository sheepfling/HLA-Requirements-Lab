"""Focused 1516.1 backflow repair operations."""

from __future__ import annotations

import json

from tools.migrations.backflow_common import (
    DDM,
    DECLARATION,
    FEDERATION,
    MOM,
    OBJECTS,
    OWNERSHIP,
    SUPPORT,
    TIME,
    _read,
    _set_clause,
    _set_statement,
    _write,
    omt_semantic_root,
)


def repair_clause_boundaries() -> None:
    """Correct candidates attributed to a later heading on their source page."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    clause_groups = {
        "4.20": [
            FEDERATION + "067-l" + suffix
            for suffix in ("16-1", "22-3", "25-4", "34-7", "37-8", "40-9", "52-13")
        ],
        "6.11": [OBJECTS + "122-l61-17", OBJECTS + "122-l79-23"],
        "6.17.4": [OBJECTS + "132-l107-30", OBJECTS + "132-l113-32"],
        "6.25": [OBJECTS + "139-l150-40"],
        "6.26": [OBJECTS + "141-l11-1"],
        "7.10": [OWNERSHIP + "165-l14-1"],
        "8.1.8": [
            TIME + "187-l" + suffix for suffix in ("10-1", "16-3", "22-5", "25-6", "40-11", "46-13")
        ],
        "9.9.3": [DDM + "236-l32-9"],
        "10.59.4": [SUPPORT + "286-l20-3"],
        "11.2.1": [SUPPORT + "288-l9-2"],
    }
    for clause, ids in clause_groups.items():
        for requirement_id in ids:
            _set_clause(by_id[requirement_id], clause)

    corrections = {
        FEDERATION + "067-l16-1": (
            "The Initiate Federate Save service shall instruct the joined federate to save state.",
            16,
            18,
        ),
        FEDERATION + "067-l22-3": (
            "The label provided to the RTI when the save was requested, via the Request Federation "
            "Save service, shall be supplied to the joined federate.",
            19,
            27,
        ),
        FEDERATION + "067-l25-4": (
            "The joined federate shall use this label, the name of the federation execution, "
            "its joined federate designator, and its federate type, which it supplied when it "
            "invoked the Join Federation Execution service, to distinguish the saved state "
            "information.",
            25,
            33,
        ),
        FEDERATION + "067-l34-7": (
            "If a joined federate is not time constrained, it shall expect to receive an "
            "Initiate Federate Save service invocation at any point.",
            31,
            36,
        ),
        FEDERATION + "067-l37-8": (
            "If a joined federate is time-constrained, it shall expect to receive an Initiate "
            "Federate Save service invocation only when it is in the Time Advancing state.",
            34,
            42,
        ),
        FEDERATION + "067-l40-9": (
            "The joined federate shall stop providing new information to the federation "
            "immediately after receiving the Initiate Federate Save service invocation. "
            "The joined federate may resume providing new information to the federation "
            "only after receiving the Federation Saved service invocation.",
            40,
            48,
        ),
        OBJECTS + "132-l107-30": (
            "If a timestamp is provided, the receive message order type is TSO, and the message "
            "is the result of a Flush Queue Request service invocation, then once the joined "
            "federate advances its time position to or past the specified time, the object "
            "instance shall no longer be known by the joined federate (and will no longer "
            "exist as far as the joined federate is concerned).",
            101,
            112,
        ),
        OBJECTS + "132-l113-32": (
            "If the joined federate successfully disables time-constrained then the object "
            "instance shall immediately become unknown by the joined federate (and will no "
            "longer exist as far as the joined federate is concerned).",
            110,
            118,
        ),
        OBJECTS + "139-l150-40": (
            "If the invoking joined federate loses ownership of an instance attribute after "
            "changing its transportation type and later acquires ownership of that instance "
            "attribute again, the transportation type shall be changed to the class "
            "attribute\u2019s default transportation type in the newly owning federate.",
            144,
            155,
        ),
        TIME + "187-l10-1": (
            "The federation execution-wide Delay Subscription Evaluation Switch indicates "
            "how the RTI shall filter a TSO or RO message based on the receiving joined "
            "federate\u2019s current subscriptions.",
            10,
            15,
        ),
        TIME + "187-l16-3": (
            "The setting for this switch shall come from the FDD at federation execution "
            "creation time. If no value is specified for this switch, then the RTI will "
            "provide default values based on the switches table defaults table in IEEE Std "
            "1516.2-2025.",
            13,
            24,
        ),
        TIME + "187-l22-5": (
            "This switch setting shall not be modifiable during a federation execution.",
            22,
            24,
        ),
        DDM + "236-l32-9": (
            "If a region designator specified is not a designator of a region specification, "
            "the Invalid region exception shall be generated.",
            29,
            37,
        ),
    }
    for requirement_id, (statement, line, end_line) in corrections.items():
        _set_statement(by_id[requirement_id], statement, line, end_line)
    _write("requirements.json", payload)


def repair_more_clause_boundaries() -> None:
    """Correct additional service and subsection boundaries reported by Umbra."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    groups = {
        "4.11": [FEDERATION + "057-l32-5", FEDERATION + "057-l44-6"],
        "4.11.1": [FEDERATION + "057-l56-8"],
        "4.15": [FEDERATION + "062-l11-1", FEDERATION + "062-l28-6"],
        "5.1.3": [DECLARATION + "084-l32-10"],
        "6.12": [OBJECTS + "124-l" + s for s in ("41-12", "47-14", "53-16")],
        "7.1.2.2": [
            OWNERSHIP + "153-l" + s for s in ("15-4", "30-9", "36-11", "45-14", "60-19", "75-24")
        ],
        "7.1.3": [
            OWNERSHIP + "153-l" + s
            for s in ("84-26", "87-27", "96-30", "99-31", "108-34", "111-35")
        ],
        "8.1.3": [TIME + "180-l" + s for s in ("9-1", "21-5", "27-7", "39-11", "45-13", "57-17")],
        "8.1.4": [
            item["id"] for item in payload["requirements"] if item["id"].startswith(TIME + "181-l")
        ],
        "8.1.5": [
            item["id"]
            for item in payload["requirements"]
            if item["id"].startswith(TIME + "182-l") and item["source"]["line"] < 97
        ],
        "8.1.6": [
            item["id"]
            for item in payload["requirements"]
            if item["id"].startswith(TIME + "182-l") and item["source"]["line"] >= 97
        ],
        "8.6": [TIME + "192-l63-17"],
        "8.6.4": [TIME + "193-l31-6", TIME + "193-l34-7"],
        "8.7": [TIME + "193-l58-12", TIME + "193-l61-13"],
        "8.8": [TIME + "194-l" + s for s in ("21-3", "27-5", "45-11", "69-19")],
        "8.13": [TIME + "202-l104-28", TIME + "202-l107-29"],
        "8.13.4": [TIME + "203-l47-12", TIME + "203-l68-19"],
        "8.14": [TIME + "203-l" + s for s in ("92-24", "95-25", "104-28", "113-31")],
        "8.14.4": [TIME + "204-l" + s for s in ("38-9", "74-21", "86-25")],
        "8.17": [TIME + "206-l26-3", TIME + "206-l29-4", TIME + "206-l32-5"],
        "8.19": [TIME + "207-l109-27", TIME + "207-l112-28", TIME + "207-l115-29"],
        "9.1.6": [DDM + "225-l9-2"],
        "9.1.7": [
            item["id"]
            for item in payload["requirements"]
            if item["id"].startswith(DDM + "225-l") and 18 <= item["source"]["line"] < 108
        ],
        "9.5": [DDM + "229-l17-4", DDM + "229-l20-5"],
        "9.5.3": [DDM + "229-l146-44"],
        "9.6.3": [DDM + "231-l100-28"],
    }
    for clause, ids in groups.items():
        for requirement_id in ids:
            _set_clause(by_id[requirement_id], clause)
    corrections = {
        DDM + "229-l17-4": (
            "If a joined federate loses ownership of an instance attribute that it had "
            "associated with an update region, the association shall be lost.",
            14,
            19,
        ),
        DDM + "229-l20-5": (
            "If the joined federate subsequently acquires ownership of that instance "
            "attribute, the original association shall not be restored.",
            17,
            22,
        ),
        DDM + "229-l146-44": (
            "If a region designator specified is not a designator of a region specification, "
            "the Invalid region exception shall be generated.",
            143,
            151,
        ),
        DDM + "231-l100-28": (
            "If a region designator specified is not a designator of a region specification, "
            "the Invalid region exception shall be generated.",
            97,
            105,
        ),
    }
    for requirement_id, (statement, line, end_line) in corrections.items():
        _set_statement(by_id[requirement_id], statement, line, end_line)
    _write("requirements.json", payload)


def repair_fragmented_statements() -> None:
    """Split adjacent line fragments into source-complete requirement statements."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    corrections = {
        DDM + "224-l89-29": (
            "The Receive Interaction service shall be invoked at a joined federate only "
            "with a subscribed interaction class as an argument.",
            89,
            94,
        ),
        DDM + "224-l92-30": (
            "An interaction shall be received at the joined federate at most once, regardless "
            "of another subscription to the interaction class using the Subscribe Interaction "
            "Class service.",
            92,
            100,
        ),
        DDM + "224-l137-44": (
            "A joined federate using DDM services shall interpret all uses of Register Object "
            "Instance, Send Interaction, and Request Attribute Value Update by any joined "
            "federate in the federation execution (including itself) as special cases of "
            "Register Object Instance With Regions, Send Interaction With Regions, and Request "
            "Attribute Value Update With Regions, respectively.",
            137,
            181,
        ),
        FEDERATION + "069-l64-15": (
            "The Federation Saved service shall inform the joined federate that the federation "
            "save process is complete.",
            64,
            68,
        ),
        FEDERATION + "069-l67-16": (
            "The Federation Saved service shall indicate whether the federation save process "
            "completed successfully.",
            64,
            69,
        ),
        FEDERATION + "069-l70-17": (
            "A save-success indicator argument indicating success shall mean that all joined "
            "federates at which the Initiate Federate Save service was invoked have invoked "
            "the Federate Save Complete service with a save-success indicator that indicated "
            "success.",
            67,
            75,
        ),
        TIME + "178-l93-28": (
            "The Flush Queue Grant service shall provide a supplemental optimistic logical time "
            "argument (OLT) that is the minimum of the logical time supplied in the preceding "
            "Flush Queue Request and the timestamps of any TSO messages delivered in response "
            "to that Flush Queue Request. The optimistic logical time indicates the logical time "
            "that the joined federate would have been granted if the RTI could have guaranteed "
            "that no other TSO messages with a timestamp less than it would be received in the "
            "future.",
            90,
            107,
        ),
        TIME + "178-l108-33": (
            "The guarantee that the RTI makes about message delivery relative to the provided "
            "logical time shall depend on the type of request to advance time; the specific "
            "guarantees are provided in the service descriptions.",
            105,
            113,
        ),
    }
    for requirement_id, (statement, line, end_line) in corrections.items():
        _set_statement(by_id[requirement_id], statement, line, end_line)
    _write("requirements.json", payload)


def repair_remaining_section_continuations() -> None:
    """Repair time and DDM paragraphs crossing semantic page boundaries."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    for item in payload["requirements"]:
        if item["id"].startswith(DDM + "220-l") and item["source"]["line"] < 122:
            _set_clause(item, "9.1.3.2")
        if item["id"].startswith(TIME + "192-l") and 63 <= item["source"]["line"] <= 84:
            _set_clause(item, "8.6")
        if item["id"].startswith(OWNERSHIP + "175-l") and item["source"]["line"] >= 131:
            _set_clause(item, "8.1.1")
    corrections = {
        OWNERSHIP + "175-l131-40": (
            "The representation of logical time shall be specified to the RTI via the time "
            "representation abstract data type (TRADT) (see 4.7 of IEEE Std 1516.2-2025) "
            "and should be documented in the time representation table of the federation "
            "execution\u2019s FDD.",
            131,
            139,
        ),
        OWNERSHIP + "175-l140-43": (
            "Federation executions requiring multiple time representations within a single "
            "execution (e.g., logical time and wall-clock time values) shall realize this "
            "functionality explicitly within their TRADT definition, e.g., by using a time "
            "type field to differentiate between different types of time values.",
            137,
            147,
        ),
        OWNERSHIP + "175-l146-45": (
            "An RTI shall support the standardized time representations shown in Table 21.",
            146,
            148,
        ),
        TIME + "192-l63-17": (
            "Invocation of the Time Constrained Enabled service shall indicate that a prior "
            "request to become time-constrained has been honored.",
            63,
            68,
        ),
        TIME + "192-l66-18": (
            "The value of this service\u2019s argument shall indicate the new logical time "
            "of the joined federate.",
            66,
            70,
        ),
        TIME + "192-l69-19": (
            "If the joined federate is time-regulating, the argument shall equal the joined "
            "federate\u2019s current logical time.",
            69,
            73,
        ),
        TIME + "192-l72-20": (
            "The RTI shall provide the joined federate with the smallest possible logical "
            "time that is greater than or equal to the logical time of the joined federate "
            "and for which all other constraints necessary to ensure TSO message delivery "
            "are satisfied.",
            72,
            79,
        ),
        TIME + "192-l78-22": (
            "In general, the provided federation time shall be less than or equal to the "
            "joined federate\u2019s GALT.",
            78,
            83,
        ),
        TIME + "192-l84-24": (
            "If the joined federate\u2019s current logical time is greater than its GALT, "
            "then the joined federate shall not become time-constrained until the joined "
            "federate\u2019s GALT advances beyond its logical time.",
            81,
            88,
        ),
    }
    for requirement_id, (statement, line, end_line) in corrections.items():
        _set_statement(by_id[requirement_id], statement, line, end_line)
    _write("requirements.json", payload)

    omt_path = omt_semantic_root() / "requirements.json"
    omt = json.loads(omt_path.read_text(encoding="utf-8"))
    record = next(
        item
        for item in omt["requirements"]
        if item["id"] == "requirement-candidate-sections-semantic-clause-4b-page-058-l34-8"
    )
    _set_clause(record, "4.8.1")
    record["semantic_group_id"] = "m17.clause-4.8.1"
    record["coverage_note"] = (
        "Source-derived HLA time-representation support requirement in §4.8.1; "
        "cross-cutting document content with no modeled RTI state transition."
    )
    _set_statement(
        record,
        "Two time representations, HLAinteger64Time and HLAfloat64Time, are required "
        "to be supported by the HLA and are described in detail in IEEE Std 1516.1-2025. "
        "These types shall be provided by all RTIs. Federations may choose to use these "
        "default data types, supply their own time representations, or not supply any time "
        "representation (e.g., NA).",
        33,
        33,
    )
    omt_path.write_text(json.dumps(omt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def repair_local_fragments() -> None:
    """Restore self-contained statements from adjacent source lines."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    corrections = {
        MOM + "290-l12-3": (
            "Parameters may be added to any MOM interaction class. Interactions of these "
            "classes that are sent by the RTI shall not contain the new parameters.",
            "11.3",
            9,
            14,
        ),
        MOM + "290-l75-24": (
            "Classes of interaction in this category shall be neither sent nor received "
            "by the RTI.",
            "11.3",
            75,
            79,
        ),
        MOM + "290-l78-25": (
            "These classes of interaction shall be ignored by the RTI and may be formed in "
            "any way that is consistent with IEEE 1516.2 federation object model "
            "(FOM) development.",
            "11.3",
            75,
            83,
        ),
        TIME + "178-l51-14": (
            "The third column summarizes what messages the RTI shall deliver to the advancing "
            "joined federate before granting the joined federate\u2019s request for time "
            "advancement.",
            "8",
            48,
            55,
        ),
        TIME + "178-l54-15": (
            "Only messages described in the third column shall be delivered before the RTI "
            "grants the joined federate\u2019s request for time advancement.",
            "8",
            51,
            56,
        ),
        MOM + "294-l14-4": (
            "The same JSON formatting used for service report parameters and arguments shall "
            "be used for service report log records.",
            "11.5.2.1",
            14,
            19,
        ),
        MOM + "294-l17-5": (
            "Each service report log record shall be enclosed in a set of braces with no "
            "separator between records.",
            "11.5.2.1",
            17,
            20,
        ),
        MOM + "294-l20-6": (
            "The service report log file shall begin with an initial record containing "
            "information about the federate\u2019s connection configuration, the joined "
            "federation\u2019s HLAfederation object, and the joined federate's HLAfederate "
            "object (see ServiceReportInitialRecord in Table 5). The initial record shall "
            "be followed by one or more service report records (see ServiceReportRecord "
            "in Table 5).",
            "11.5.2.1",
            17,
            30,
        ),
        TIME + "180-l84-25": (
            "Each class attribute and interaction class shall be provided with a preferred "
            "order type in the FDD that indicates the order type (TSO or RO) to use when "
            "sending messages carrying values for instances of these classes.",
            "8.1.4",
            81,
            91,
        ),
        TIME + "180-l87-26": (
            "The preferred order type indicated in the FDD shall be used when sending messages "
            "carrying values for instances of the class attribute or interaction class.",
            "8.1.4",
            83,
            91,
        ),
        TIME + "180-l93-28": (
            "In the case of sent messages representing a Delete Object Instance service "
            "invocation, the preferred order type of the message shall be based on the preferred "
            "order type of the HLAprivilegeToDeleteObject attribute of the specified "
            "object instance.",
            "8.1.4",
            89,
            97,
        ),
        TIME + "197-l98-29": (
            "A Time Advance Grant service invocation shall complete this request and indicate "
            "to the joined federate that it has advanced its logical time to the timestamp "
            "of the TSO messages that are delivered, if any, or to the specified logical time "
            "if no TSO messages were delivered.",
            "8.10.2",
            98,
            105,
        ),
        TIME + "197-l104-31": (
            "The Time Advance Grant service invocation shall also indicate that no TSO "
            "messages will be delivered to the joined federate in the future with timestamps "
            "less than or equal to the logical time of the grant.",
            "8.10.2",
            104,
            111,
        ),
        OWNERSHIP + "150-l152-47": (
            "The joined federate may invoke the Unconditional Attribute Ownership Divestiture "
            "service, in which case the instance attribute shall immediately become unowned "
            "by that joined federate and, in fact, by all joined federates.",
            "7.1.2.1",
            149,
            157,
        ),
    }
    for requirement_id, (statement, clause, line, end_line) in corrections.items():
        record = by_id[requirement_id]
        _set_clause(record, clause)
        _set_statement(record, statement, line, end_line)
    _write("requirements.json", payload)


def repair_contextual_fragments() -> None:
    """Recover missing subjects, lists, and neighboring sentence boundaries."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    corrections = {
        OBJECTS + "109-l10-1": (
            "Interaction I shall have a candidate received class at joined federate F if "
            "joined federate F is subscribed to either the sent class of I or to a superclass "
            "of the sent class of I.",
            "6.1.9",
            10,
            18,
        ),
        OBJECTS + "109-l25-6": (
            "If an interaction has a candidate received class at a joined federate, the "
            "candidate received class of the interaction at that joined federate shall be "
            "the interaction\u2019s sent class if subscribed to by the joined federate. Otherwise, "
            "the candidate received class of the interaction shall be the closest superclass "
            "of the interaction\u2019s sent class to which the joined federate is subscribed.",
            "6.1.9",
            22,
            33,
        ),
        TIME + "195-l137-40": (
            "Invocation of the Time Advance Request Available service shall cause the following "
            "messages to be delivered to the joined federate: all messages queued in the RTI "
            "that the joined federate will receive as RO messages; all messages that the joined "
            "federate will receive as TSO messages with timestamps less than the specified "
            "logical time; and any messages queued in the RTI that the joined federate will "
            "receive as TSO messages with timestamps equal to the specified logical time.",
            "8.9",
            137,
            163,
        ),
        OBJECTS + "115-l101-27": (
            "The supplied name set shall not be empty.",
            "6.5.3",
            101,
            104,
        ),
        OBJECTS + "115-l104-28": (
            "The name values in the supplied name set argument shall not begin with "
            "\u201cHLA.\u201d",
            "6.5.3",
            104,
            107,
        ),
        OBJECTS + "115-l107-29": (
            "Any one illegal name shall abort the reservation of all names in the set.",
            "6.5.3",
            104,
            109,
        ),
        OBJECTS + "115-l110-30": (
            "The RTI shall provide the result of the reservation attempt via the Multiple "
            "Object Instance Name Reserved service. The Object Instance Name Reserved service "
            "shall not be used to provide the result for any single name.",
            "6.5.3",
            107,
            115,
        ),
        DDM + "233-l30-7": (
            "The Subscribe Object Class Attributes With Regions service shall specify an "
            "object class for which the RTI shall begin notifying the joined federate of "
            "discovery of instantiated object instances when at least one of that object "
            "instance\u2019s instance attributes is in scope.",
            "9.8",
            30,
            38,
        ),
        DDM + "233-l33-8": (
            "The RTI shall begin notifying the joined federate of discovery of instantiated "
            "object instances when at least one of that object instance\u2019s instance attributes "
            "is in scope.",
            "9.8",
            30,
            38,
        ),
        DDM + "233-l36-9": (
            "This service and subsequent related RTI operations shall behave analogously to "
            "the Subscribe Object Class Attributes service as described in 5.8 and its "
            "subsequent related RTI operations.",
            "9.8",
            36,
            44,
        ),
        DDM + "233-l42-11": (
            "This service shall provide additional functionality in that the overlap of the "
            "relevant subscription and update region sets affects the subsequent RTI "
            "operations, as described in 9.1.5.",
            "9.8",
            42,
            47,
        ),
        DDM + "219-l92-30": (
            "The effects of invocation of the Set Range Bounds service for a given region "
            "(template or specification) shall remain pending until the Commit Region "
            "Modifications service is subsequently invoked for that region.",
            "9.1.3.1",
            92,
            98,
        ),
        DDM + "219-l104-34": (
            "If a federate invokes the Set Range Bounds service repeatedly for a given "
            "dimension of a given region before invoking the Commit Region Modifications "
            "service for that region, the range values provided in the most recent invocation "
            "of the Set Range Bounds service shall become the range values for that dimension "
            "of that region specification.",
            "9.1.3.1",
            95,
            109,
        ),
        DDM + "220-l140-45": (
            "Any region associated with a sent interaction shall contain only dimensions "
            "that are a subset of the available dimensions of the sent interaction.",
            "9.1.3.3",
            140,
            145,
        ),
        DDM + "220-l143-46": (
            "The default region shall be used for sending an interaction of such a class "
            "during an invocation of the Send Interaction service.",
            "9.1.3.3",
            143,
            149,
        ),
    }
    for requirement_id, (statement, clause, line, end_line) in corrections.items():
        record = by_id[requirement_id]
        _set_clause(record, clause)
        _set_statement(record, statement, line, end_line)
    _write("requirements.json", payload)

    # The 2025 semantic transcription lost a short conditional phrase in a
    # fixed-layout line. The corresponding 2010 clause confirms the wording.
    damaged = "Fned federate Fscribed"
    restored = "if joined federate F is subscribed"
    for name, key in (
        ("content-blocks.json", "content_blocks"),
        ("content-elements.json", "content_elements"),
    ):
        source = _read(name)
        item = next(x for x in source[key] if "page-109" in x["id"])
        field = "layout_body" if name == "content-blocks.json" else "text"
        if damaged in item[field]:
            item[field] = item[field].replace(damaged, restored)
        elif restored not in item[field]:
            raise ValueError(f"Expected damaged page-109 phrase in {name}")
        _write(name, source)
