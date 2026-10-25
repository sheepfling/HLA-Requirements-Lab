"""Focused 1516.1 backflow repair operations."""

from __future__ import annotations

from tools.migrations.backflow_common import (
    TIME,
    _read,
    _set_statement,
    _write,
)


def repair_table_5_records() -> None:
    """Put complete Table 5 types on their parent rows and label member fragments."""
    payload = _read("requirements.json")
    rows = {item["id"]: item for item in payload["requirements"]}

    def set_row(page: int, ordinal: int, title: str, statement: str) -> None:
        row = rows[f"requirement-candidate-table-5-p{page}-r{ordinal:03d}"]
        row["title"] = f"Table 5 {title}"
        row["statement"] = statement
        row["machine_statement"] = statement
        row["coverage_note"] = (
            "Structured Table 5 type, field, or enumerant; example values illustrate "
            "the source and do not create a lexical requirement."
        )

    set_row(
        295,
        1,
        "AdditionalSettingsResultCode",
        "Table 5 defines AdditionalSettingsResultCode as Enumeration<SETTINGS_IGNORED, "
        "SETTINGS_FAILED_TO_PARSE, SETTINGS_APPLIED>; its example is SETTINGS_APPLIED.",
    )
    for ordinal, name in ((2, "SETTINGS_FAILED_TO_PARSE"), (3, "SETTINGS_APPLIED")):
        set_row(
            295,
            ordinal,
            f"AdditionalSettingsResultCode enumerant {name}",
            f"{name} is an enumerant of the Table 5 AdditionalSettingsResultCode type.",
        )

    set_row(
        296,
        1,
        "ConfigurationResult",
        "Table 5 defines ConfigurationResult as Record<configurationUsed:Boolean, "
        "addressUsed:Boolean, additionalSettingsResultCode:AdditionalSettingsResultCode, "
        "message:String>. The printed example uses configurationUsed=true, addressUsed=true, "
        'addtionalSettingsResultCode=SETTINGS_APPLIED, and message=""; its '
        "addtionalSettingsResultCode spelling differs from the type field name.",
    )
    config_fields = (
        (2, "configurationUsed:Boolean", '"configurationUsed": true'),
        (3, "addressUsed:Boolean", '"addressUsed": true'),
        (
            4,
            "additionalSettingsResultCode:AdditionalSettingsResultCode",
            '"addtionalSettingsResultCode": "SETTINGS_APPLIED"',
        ),
        (5, "message:String", '"message": ""'),
    )
    for ordinal, field, example in config_fields:
        set_row(
            296,
            ordinal,
            f"ConfigurationResult field {field}",
            f"{field} is a field of ConfigurationResult; the printed example is {example}.",
        )

    set_row(
        296,
        6,
        "Credentials",
        "Table 5 defines Credentials as Record<Type:String, Data:BinaryData>; the "
        'printed example has Type="HLAplainTextPassword" and Data="xFDcMA".',
    )
    set_row(
        296,
        7,
        "Credentials field Type",
        "Type:String is a field of Credentials; "
        'the printed example is "Type": "HLAplainTextPassword".',
    )
    set_row(
        296,
        8,
        "Credentials field Data",
        'Data:BinaryData is a field of Credentials; the printed example is "Data": "xFDcMA".',
    )

    factory_names = [
        "ATTRIBUTE_HANDLE_FACTORY",
        "ATTRIBUTE_HANDLE_SET_FACTORY",
        "ATTRIBUTE_HANDLE_VALUE_MAP_FACTORY",
        "ATTRIBUTE_SET_REGION_SET_PAIR_LIST_FACTORY",
        "DIMENSION_HANDLE_FACTORY",
        "DIMENSION_HANDLE_SET_FACTORY",
        "FEDERATE_HANDLE_FACTORY",
        "FEDERATE_HANDLE_SET_FACTORY",
        "INTERACTION_CLASS_HANDLE_FACTORY",
        "OBJECT_CLASS_HANDLE_FACTORY",
        "OBJECT_INSTANCE_HANDLE_FACTORY",
        "PARAMETERHANDLEFACTORY",
        "PARAMETER_HANDLE_VALUE_MAP_FACTORY",
        "REGION_HANDLE_SET_FACTORY",
        "TRANSPORTATION_TYPE_HANDLE_FACTORY",
        "REGION_HANDLE_FACTORY",
        "MESSAGE_RETRACTION_HANDLE_FACTORY",
        "LOGICAL_TIME_FACTORY",
    ]
    for ordinal, name in enumerate(factory_names[1:], start=12):
        set_row(
            296,
            ordinal,
            f"FactoryClass enumerant {name}",
            f"{name} is an enumerant of the Table 5 FactoryClass type.",
        )
    set_row(
        296,
        11,
        "FactoryClass",
        "Table 5 defines FactoryClass as Enumeration<"
        + ", ".join(factory_names)
        + ">; its printed example is ATTRIBUTE_HANDLE_FACTORY.",
    )

    federate_fields = (
        "HLAfederateHandle:FederateHandle",
        "HLAfederateName:String",
        "HLAfederateType:String",
        "HLAfederateHost:String",
        "HLAFOMmoduleDesignatorList:FomDesignatorSet",
    )
    set_row(
        296,
        30,
        "FederateAttributes",
        "Table 5 defines FederateAttributes as Record<"
        + ", ".join(federate_fields)
        + ">; the source encoding column ends with a trailing comma after the final field.",
    )
    for ordinal, field in zip(range(31, 35), federate_fields[1:], strict=True):
        set_row(
            296,
            ordinal,
            f"FederateAttributes field {field}",
            f"{field} is a field of FederateAttributes, not a separate Table 5 type.",
        )

    set_row(
        296,
        36,
        "FederateHandleSaveStatusPair",
        "Table 5 defines FederateHandleSaveStatusPair as "
        "Record<handle:FederateHandle, status:SaveStatus>; the printed example "
        'is "handle": "FederateHandle<12>", "status": "FEDERATE_SAVING".',
    )
    set_row(
        296,
        37,
        "FederateHandleSaveStatusPair field status",
        "status:SaveStatus is a field of FederateHandleSaveStatusPair, "
        "not a separate Table 5 type.",
    )

    set_row(
        297,
        3,
        "FederateRestoreStatus",
        "Table 5 defines FederateRestoreStatus as "
        "Record<preRestoreHandle:FederateHandle, postRestoreHandle:FederateHandle, "
        "status:RestoreStatus>; the printed example has preRestoreHandle=federate<81>, "
        "postRestoreHandle=federate<11>, and status=FEDERATE_RESTORING.",
    )
    for ordinal, field in (
        (4, "preRestoreHandle:FederateHandle"),
        (5, "postRestoreHandle:FederateHandle"),
        (6, "status:RestoreStatus"),
    ):
        set_row(
            297,
            ordinal,
            f"FederateRestoreStatus field {field}",
            f"{field} is a field of FederateRestoreStatus, not a separate Table 5 type.",
        )
    set_row(
        297,
        7,
        "FederateHandleRestoreStatusSet source discrepancy",
        "Table 5 prints FederateHandleRestoreStatusSet with encoding "
        "Array<FederateHandleRestoreStatus>. Its example depicts two restore-status "
        "records but has malformed field punctuation in the pinned source.",
    )
    rows["requirement-candidate-table-5-p297-r007"]["coverage_note"] = (
        "Source discrepancy: IEEE 1516.2-2025 MIM names "
        "FederateRestoreStatus (type 19) and FederateRestoreStatusSet (type 20); "
        "it has no FederateHandleRestoreStatus identifier. Preserve the Table 5 "
        "literal as provenance and do not infer a type-20 mapping from it."
    )

    # Source lines address semantic/content-blocks.json layout_body, where a
    # rotated-table value follows its \HLARotatedLine command by one line.
    # The original row spans often started two lines after the printed type or
    # member; parent spans also stopped before their printed examples.
    spans = {
        (295, 1): (30, 42),
        (295, 2): (36, 36),
        (295, 3): (39, 39),
        (296, 1): (18, 48),
        (296, 2): (24, 39),
        (296, 3): (27, 42),
        (296, 4): (30, 45),
        (296, 5): (33, 48),
        (296, 6): (54, 72),
        (296, 7): (60, 69),
        (296, 8): (63, 72),
        (296, 11): (96, 153),
        (296, 30): (165, 180),
        (296, 36): (228, 243),
        (296, 37): (234, 234),
        (297, 3): (72, 96),
        (297, 7): (102, 141),
    }
    spans.update({(296, ordinal): (102 + 3 * (ordinal - 12),) * 2 for ordinal in range(12, 29)})
    spans.update({(296, ordinal): (171 + 3 * (ordinal - 31),) * 2 for ordinal in range(31, 35)})
    spans.update({(297, ordinal): (78 + 3 * (ordinal - 4),) * 2 for ordinal in range(4, 7)})
    for (page, ordinal), (line, end_line) in spans.items():
        rows[f"requirement-candidate-table-5-p{page}-r{ordinal:03d}"]["source"].update(
            line=line, end_line=end_line
        )
    _write("requirements.json", payload)


def repair_time_table_and_caption() -> None:
    """Restore the TAR bound and remove a caption fragment from the catalog."""
    payload = _read("requirements.json")
    by_id = {item["id"]: item for item in payload["requirements"]}
    _set_statement(
        by_id[TIME + "178-l45-12"],
        "For Time Advance Request with zero lookahead, the joined federate shall not "
        "send any TSO messages that have a timestamp less than or equal to the "
        "federation time requested by the joined federate.",
        45,
        49,
    )
    _set_statement(
        by_id[TIME + "180-l156-49"],
        "The order type of a sent message shall be determined by the preferred order "
        "type of the message at the sending joined federate, regardless of whether "
        "that joined federate is time-regulating and whether a timestamp was supplied "
        "in the service invocation that sends the message.",
        156,
        161,
    )
    order_rule = by_id[TIME + "180-l156-49"]
    continuation = (
        " The final sentence continues in content/clauses/08-time-management-page-181.tex:112."
    )
    if continuation not in order_rule["coverage_note"]:
        order_rule["coverage_note"] += continuation
    obsolete = TIME + "181-l115-2"
    if obsolete not in by_id:
        candidate = dict(by_id[TIME + "180-l156-49"])
        candidate["id"] = obsolete
        payload["requirements"].append(candidate)
    else:
        candidate = by_id[obsolete]
    candidate["title"] = "Non-normative Table 2 introduction"
    candidate["statement"] = (
        "Table 2 illustrates how the order type of a sent message shall be determined."
    )
    candidate["machine_statement"] = candidate["statement"]
    candidate["extraction"] = "candidate"
    candidate["coverage_note"] = "Layout prose introducing Table 2; reviewed as non-normative."
    candidate["source"] = {
        "path": "content/clauses/08-time-management-page-181.tex",
        "line": 112,
        "end_line": 115,
    }
    _write("requirements.json", payload)
    for name, key in (
        ("content-blocks.json", "content_blocks"),
        ("content-elements.json", "content_elements"),
    ):
        content = _read(name)
        if key == "content_blocks":
            targets = [item for item in content[key] if item["id"] == "content-15161-page-181"]
        else:
            targets = [
                item for item in content[key] if item["block_id"] == "content-15161-page-181"
            ]
        for item in targets:
            if obsolete not in item["record_ids"]:
                item["record_ids"].append(obsolete)
        _write(name, content)
    reviews = _read("requirement-review.json")
    if not any(item["requirement_id"] == obsolete for item in reviews["reviews"]):
        reviews["reviews"].append(
            {
                "requirement_id": obsolete,
                "status": "non-normative",
                "reason": (
                    "Table 2 introduction is explanatory layout prose, not a standalone obligation."
                ),
                "source": candidate["source"],
            }
        )
    else:
        next(item for item in reviews["reviews"] if item["requirement_id"] == obsolete)[
            "source"
        ] = candidate["source"]
    _write("requirement-review.json", reviews)
    bindings = _read("api-requirement-bindings.json")
    if not any(item["requirement_id"] == obsolete for item in bindings["bindings"]):
        bindings["bindings"].append(
            {
                "id": f"binding.{obsolete}.no-api",
                "requirement_id": obsolete,
                "api_surface_id": None,
                "candidate_api_surface_ids": [],
                "language": "unspecified",
                "relationship": "cross-cutting",
                "status": "reviewed",
                "rationale": "Explanatory Table 2 introduction reviewed as non-normative.",
                "source": candidate["source"],
            }
        )
    else:
        for item in bindings["bindings"]:
            if item["requirement_id"] == obsolete:
                item["source"] = candidate["source"]
    _write("api-requirement-bindings.json", bindings)


def restore_missing_service_flow_candidates() -> None:
    """Add the omitted NMRA and Get Dimension Handle flow items."""
    requirements = _read("requirements.json")
    by_id = {item["id"]: item for item in requirements["requirements"]}
    surfaces = _read("api-surfaces.json")
    by_surface = {item["id"]: item for item in surfaces["api_surfaces"]}
    specs = (
        (
            "requirement-service-flow-nmra-current-time-precondition",
            "8.11.3",
            "08-time-management-page-199.tex",
            145,
            147,
            "The specified logical time for Next Message Request Available must be "
            "greater than or equal to the joined federate's logical time.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            199,
        ),
        (
            "requirement-service-flow-nmra-time-passed-exception",
            "8.11.5",
            "08-time-management-page-200.tex",
            62,
            62,
            "Next Message Request Available lists Logical Time Already Passed as "
            "an exception when the requested logical time is behind the joined federate's time.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            200,
        ),
        (
            "requirement-service-flow-nmra-not-advancing-precondition",
            "8.11.3",
            "08-time-management-page-200.tex",
            11,
            11,
            "For Next Message Request Available, the joined federate must not be "
            "in the Time Advancing state.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            200,
        ),
        (
            "requirement-service-flow-nmra-advancing-exception",
            "8.11.5",
            "08-time-management-page-200.tex",
            74,
            74,
            "Next Message Request Available lists Joined Federate in Time Advancing "
            "State as an exception.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            200,
        ),
        (
            "requirement-service-flow-get-dimension-handle-name-not-found",
            "10.23.5",
            "10-support-services-page-260.tex",
            35,
            35,
            "Get Dimension Handle lists a dimension not defined in the FDD as an "
            "exception; the C++ getDimensionHandle declaration names this NameNotFound.",
            "api.2025.cpp.rtiambassador.getdimensionhandle.7a343b0ace0a",
            260,
        ),
    )
    blocks = _read("content-blocks.json")
    elements = _read("content-elements.json")
    for requirement_id, clause, path, line, end_line, statement, api_id, page in specs:
        source = {"path": "content/clauses/" + path, "line": line, "end_line": end_line}
        if requirement_id not in by_id:
            record = {
                "id": requirement_id,
                "title": f"Service-flow item at {source['path']}:{line}",
                "statement": statement,
                "kind": "detailed",
                "clause": clause,
                "clause_id": f"clause-{clause}",
                "machine_statement": statement,
                "transition_ids": [],
                "coverage_kind": "cross-cutting",
                "coverage_note": (
                    "Explicit service-flow precondition or exception from the pinned 2025 source."
                ),
                "api_surface_scope": "required",
                "api_surface_note": (
                    "Reviewed against the official 2025 C++ RTIambassador declaration."
                ),
                "api_surface_resolution": "strict",
                "extraction": "explicit",
                "semantic_group_id": f"m17.service-flow.{clause}",
                "source": source,
            }
            requirements["requirements"].append(record)
            by_id[requirement_id] = record
        else:
            record = by_id[requirement_id]
            record["source"] = source
            record["title"] = f"Service-flow item at {source['path']}:{line}"
            record["statement"] = statement
            record["machine_statement"] = statement
        surface = by_surface[api_id]
        if requirement_id not in surface["requirement_ids"]:
            surface["requirement_ids"].append(requirement_id)
        block = next(
            item for item in blocks["content_blocks"] if item["id"] == f"content-15161-page-{page}"
        )
        if requirement_id not in block["record_ids"]:
            block["record_ids"].append(requirement_id)
        element = next(
            item for item in elements["content_elements"] if item["block_id"] == block["id"]
        )
        if requirement_id not in element["record_ids"]:
            element["record_ids"].append(requirement_id)
    _write("requirements.json", requirements)
    _write("api-surfaces.json", surfaces)
    _write("content-blocks.json", blocks)
    _write("content-elements.json", elements)
