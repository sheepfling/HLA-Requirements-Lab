"""Focused 1516.1 backflow repair operations."""

from __future__ import annotations

from hla_lab.core.semantic_model import SourceAnomaly, SourceAnomalyLedger, SourceRef
from tools.migrations.backflow_common import (
    TIME,
    _MutableRequirement,
    _MutableRequirementApiBinding,
    _MutableRequirementReview,
    _read_api_surfaces,
    _read_content_blocks,
    _read_content_elements,
    _read_requirement_api_bindings,
    _read_requirement_reviews,
    _read_requirements,
    _set_statement,
    _write_api_surfaces,
    _write_content_blocks,
    _write_content_elements,
    _write_requirement_api_bindings,
    _write_requirement_reviews,
    _write_requirements,
    semantic_root,
)


def repair_table_5_records() -> None:
    """Put complete Table 5 types on their parent rows and label member fragments."""
    payload = _read_requirements()
    rows = {item.id: item for item in payload.requirements}

    def set_row(page: int, ordinal: int, title: str, statement: str) -> None:
        row = rows[f"requirement-candidate-table-5-p{page}-r{ordinal:03d}"]
        row.title = f"Table 5 {title}"
        row.statement = statement
        row.machine_statement = statement
        row.coverage_note = (
            "Structured Table 5 type, field, or enumerant; example values illustrate "
            "the source and do not create a lexical requirement."
        )

    def set_coverage_note(requirement_id: str, note: str) -> None:
        rows[requirement_id].coverage_note = note

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
    rows["requirement-candidate-table-5-p297-r007"].coverage_note = (
        "Source discrepancy: IEEE 1516.2-2025 MIM names "
        "FederateRestoreStatus (type 19) and FederateRestoreStatusSet (type 20); "
        "it has no FederateHandleRestoreStatus identifier. Use "
        "FederateRestoreStatusSet (type 20) for the independently corroborated "
        "implementation mapping, while preserving the Table 5 literal as provenance "
        "and leaving it without a direct type-20 binding."
    )

    # Table 5 rows from pages 297–304 were exported as one candidate per
    # visually detected line. Rotated encodings wrap across several lines, so
    # those stable candidate IDs need reviewed semantic roles: one complete
    # parent row, followed by explicit field/enumerant facets or a pagination
    # continuation. Do not delete/re-number the historical candidates.
    reviewed_rows = (
        (
            297,
            8,
            "FederationAttributes",
            "Table 5 defines FederationAttributes as Record<"
            "HLAfederationName:String, HLARTIversion:String, "
            "HLAMIMDesignator:FOMDesignator, "
            "HLAFOMmoduleDesignatorList:FomDesignatorSet, "
            "HLAtimeImplementationName:String, HLAautoProvide:Boolean>. "
            'The printed example uses HLAfederationName="TestDogFight", '
            'HLARTIversion="FooBar1.0", an empty HLAMIMDesignator, the RPR FOM and '
            'DogFightExtensions designators, HLAtimeImplementationName="HLAfloat64Time", '
            "and HLAautoProvide=true.",
        ),
        (
            297,
            9,
            "FederationAttributes field HLARTIversion:String",
            'HLARTIversion:String is a field of FederationAttributes; the printed example is '
            '"HLARTIversion": "FooBar1.0". It is not a separate Table 5 type.',
        ),
        (
            297,
            10,
            "FederationAttributes field HLAMIMDesignator:FOMDesignator",
            'HLAMIMDesignator:FOMDesignator is a field of FederationAttributes; the printed '
            'example is "HLAMIMDesignator": "". It is not a separate Table 5 type.',
        ),
        (
            297,
            11,
            "FederationAttributes field HLAFOMmoduleDesignatorList:FomDesignatorSet",
            'HLAFOMmoduleDesignatorList:FomDesignatorSet is a field of FederationAttributes; '
            'the printed example contains "http://www.sisostds.org/RPR.fom" and '
            '"/foms/DogFightExtensions.xml". It is not a separate Table 5 type.',
        ),
        (
            297,
            12,
            "FederationAttributes field HLAtimeImplementationName:String",
            'HLAtimeImplementationName:String is a field of FederationAttributes; the printed '
            'example is "HLAtimeImplementationName": "HLAfloat64Time". It is not a separate '
            'Table 5 type.',
        ),
        (
            297,
            13,
            "FederationAttributes field HLAautoProvide:Boolean",
            'HLAautoProvide:Boolean is a field of FederationAttributes; the printed example is '
            '"HLAautoProvide": true. It is not a separate Table 5 type.',
        ),
        (
            297,
            14,
            "FederationExecutionInformation",
            "Table 5 defines FederationExecutionInformation as Record<"
            "federationExecutionName:string, logicalTimeImplementationName:string>. "
            'The printed example uses federationExecutionName="Federation1" and '
            'logicalTimeImplementationName="HLAfloat64Time".',
        ),
        (
            297,
            15,
            "FederationExecutionInformation field federationExecutionName:string",
            'federationExecutionName:string is a field of FederationExecutionInformation; '
            'the printed example is "federationExecutionName": "Federation1". It is not a '
            'separate Table 5 type.',
        ),
        (
            297,
            16,
            "FederationExecutionInformation field logicalTimeImplementationName:string",
            'logicalTimeImplementationName:string is a field of FederationExecutionInformation; '
            'the printed example is "logicalTimeImplementationName": "HLAfloat64Time". It is '
            'not a separate Table 5 type.',
        ),
        (
            298,
            2,
            "FederationExecutionMemberInformation",
            "Table 5 defines FederationExecutionMemberInformation as Record<"
            "federateName:string, federateType:string>. The printed example uses "
            'federateName="Federate1" and federateType="Logger".',
        ),
        (
            298,
            3,
            "FederationExecutionMemberInformation field federateName:string",
            'federateName:string is a field of FederationExecutionMemberInformation; the printed '
            'example is "federateName": "Federate1". It is not a separate Table 5 type.',
        ),
        (
            298,
            4,
            "FederationExecutionMemberInformation field federateType:string",
            'federateType:string is a field of FederationExecutionMemberInformation; the printed '
            'example is "federateType": "Logger". It is not a separate Table 5 type.',
        ),
        (
            298,
            5,
            "FederationExecutionMemberInformationSet",
            "Table 5 defines FederationExecutionMemberInformationSet as "
            "Array<FederationExecutionMemberInformation>. Its printed example contains two "
            "records: (Federate1, Logger) and (Federate2, Aircraft Simulator).",
        ),
        (
            298,
            6,
            "FederationExecutionMemberInformationSet name continuation",
            "The printed fragment ‘mationSet’ completes the wrapped type name "
            "FederationExecutionMemberInformationSet on page 298. It is not a separate Table 5 "
            "type or requirement.",
        ),
        (
            298,
            8,
            "FomDesignatorSet",
            "Table 5 defines FomDesignatorSet as Array<FomDesignator>. Its printed example "
            'contains "http://www.sisostds.org/RPR.fom" and '
            '"/foms/DogFightExtensions.xml" in that order.',
        ),
        (
            298,
            9,
            "HLAargument",
            "Table 5 defines HLAargument as Record<HLAargumentType:number, "
            "HLAargumentName:String, HLAargumentValue:String>. The page-298 example is "
            'HLAargumentType=58, HLAargumentName="UserSuppliedTag", and '
            'HLAargumentValue="xFDcMa"; preserve this value as a source-local example.',
        ),
        (
            298,
            10,
            "HLAargument field HLAargumentName:String",
            'HLAargumentName:String is a field of HLAargument; the page-298 example is '
            '"HLAargumentName": "UserSuppliedTag". It is not a separate Table 5 type.',
        ),
        (
            298,
            11,
            "HLAargument field HLAargumentValue:String",
            'HLAargumentValue:String is a field of HLAargument; the page-298 example is '
            '"HLAargumentValue": "xFDcMa". It is not a separate Table 5 type.',
        ),
        (
            298,
            12,
            "HLAreturnedArgument",
            "Table 5 defines HLAreturnedArgument as Record<HLAargumentType:number, "
            "HLAargumentValue:String>. The page-298 example is HLAargumentType=24 and "
            'HLAargumentValue="InteractionClassHandle<201>"; preserve this source-local value.',
        ),
        (
            298,
            13,
            "HLAreturnedArgument field HLAargumentValue:String",
            'HLAargumentValue:String is a field of HLAreturnedArgument; the page-298 example is '
            '"HLAargumentValue": "InteractionClassHandle<201>". It is not a separate Table 5 '
            "type.",
        ),
        (
            298,
            19,
            "MessageRetractionReturn",
            "Table 5 defines MessageRetractionReturn as Record<retractionHandleIsValid:Boolean, "
            "handle:MessageRetractionHandle>. Its printed example uses true and "
            '"MessageRetractionHandle<2345>".',
        ),
        (
            298,
            20,
            "MessageRetractionReturn field handle:MessageRetractionHandle",
            'handle:MessageRetractionHandle is a field of MessageRetractionReturn; the printed '
            'example is "handle": "MessageRetractionHandle<2345>". It is not a separate '
            "Table 5 type.",
        ),
        (
            300,
            1,
            "SaveFailureReason",
            "Table 5 defines SaveFailureReason as Enumeration<RTI_UNABLE_TO_SAVE, "
            "FEDERATE_REPORTED_FAILURE_DURING_SAVE, FEDERATE_RESIGNED_DURING_SAVE, "
            "RTI_DETECTED_FAILURE_DURING_SAVE, SAVE_TIME_CANNOT_BE_HONORED, SAVE_ABORTED>. "
            "Its printed example is RTI_UNABLE_TO_SAVE.",
        ),
        (
            300,
            2,
            "SaveFailureReason enumerant FEDERATE_REPORTED_FAILURE_DURING_SAVE",
            "FEDERATE_REPORTED_FAILURE_DURING_SAVE is an enumerant of SaveFailureReason, not a "
            "separate Table 5 type.",
        ),
        (
            300,
            3,
            "SaveFailureReason enumerant FEDERATE_RESIGNED_DURING_SAVE",
            "FEDERATE_RESIGNED_DURING_SAVE is an enumerant of SaveFailureReason, not a separate "
            "Table 5 type.",
        ),
        (
            300,
            4,
            "SaveFailureReason enumerant RTI_DETECTED_FAILURE_DURING_SAVE",
            "RTI_DETECTED_FAILURE_DURING_SAVE is an enumerant of SaveFailureReason, not a "
            "separate Table 5 type.",
        ),
        (
            300,
            5,
            "SaveFailureReason final enumerants",
            "SAVE_TIME_CANNOT_BE_HONORED and SAVE_ABORTED are the final enumerants of "
            "SaveFailureReason, not separate Table 5 types.",
        ),
        (
            300,
            6,
            "SaveStatus",
            "Table 5 defines SaveStatus as Enumeration<NO_SAVE_IN_PROGRESS, "
            "FEDERATE_INSTRUCTED_TO_SAVE, FEDERATE_SAVING, "
            "FEDERATE_WAITING_FOR_FEDERATION_TO_SAVE>. Its printed example is "
            "NO_SAVE_IN_PROGRESS.",
        ),
        (
            300,
            7,
            "SaveStatus enumerant FEDERATE_INSTRUCTED_TO_SAVE",
            "FEDERATE_INSTRUCTED_TO_SAVE is an enumerant of SaveStatus, not a separate Table 5 "
            "type.",
        ),
        (
            300,
            8,
            "SaveStatus enumerant FEDERATE_SAVING",
            "FEDERATE_SAVING is an enumerant of SaveStatus, not a separate Table 5 type.",
        ),
        (
            300,
            9,
            "SaveStatus enumerant FEDERATE_WAITING_FOR_FEDERATION_TO_SAVE",
            "FEDERATE_WAITING_FOR_FEDERATION_TO_SAVE is an enumerant of SaveStatus, not a "
            "separate Table 5 type.",
        ),
        (
            300,
            10,
            "ServiceGroup",
            "Table 5 defines ServiceGroup as Enumeration<FEDERATION_MANAGEMENT, "
            "DECLARATION_MANAGEMENT, OBJECT_MANAGEMENT, OWNERSHIP_MANAGEMENT, TIME_MANAGEMENT, "
            "DATA_DISTRIBUTION_MANAGEMENT, SUPPORT_SERVICES>. Its printed example is "
            "FEDERATION_MANAGEMENT.",
        ),
        (
            300,
            11,
            "ServiceGroup enumerant DECLARATION_MANAGEMENT",
            "DECLARATION_MANAGEMENT is an enumerant of ServiceGroup, not a separate Table 5 "
            "type.",
        ),
        (
            300,
            12,
            "ServiceGroup enumerants OBJECT_MANAGEMENT and OWNERSHIP_MANAGEMENT",
            "OBJECT_MANAGEMENT and OWNERSHIP_MANAGEMENT are enumerants of ServiceGroup, not "
            "separate Table 5 types.",
        ),
        (
            300,
            13,
            "ServiceGroup enumerant TIME_MANAGEMENT",
            "TIME_MANAGEMENT is an enumerant of ServiceGroup, not a separate Table 5 type.",
        ),
        (
            300,
            14,
            "ServiceGroup enumerant DATA_DISTRIBUTION_MANAGEMENT",
            "DATA_DISTRIBUTION_MANAGEMENT is an enumerant of ServiceGroup, not a separate "
            "Table 5 type.",
        ),
        (
            300,
            15,
            "ServiceGroup enumerant SUPPORT_SERVICES",
            "SUPPORT_SERVICES is an enumerant of ServiceGroup, not a separate Table 5 type.",
        ),
        (
            300,
            16,
            "ServiceReportInitialRecord",
            "Table 5 defines ServiceReportInitialRecord as Record<"
            "RtiConfiguration:RtiConfiguration, "
            "HLAmanager.HLAfederation:FederationAttributes, "
            "HLAmanager.HLAfederate:FederateAttributes>. Its printed JSON example contains the "
            "configuration, federation attributes, and joined-federate attributes as nested "
            "objects.",
        ),
        (
            300,
            17,
            "ServiceReportInitialRecord field HLAmanager.HLAfederation:FederationAttributes",
            "HLAmanager.HLAfederation:FederationAttributes is a field of "
            "ServiceReportInitialRecord, not a separate Table 5 type.",
        ),
        (
            300,
            18,
            "ServiceReportInitialRecord field HLAmanager.HLAfederate:FederateAttributes",
            "HLAmanager.HLAfederate:FederateAttributes is a field of "
            "ServiceReportInitialRecord, not a separate Table 5 type.",
        ),
        (
            301,
            1,
            "ServiceReportRecord",
            "Table 5 defines ServiceReportRecord as Record<HLAserialNumber:Number, "
            "HLAreturnedArgument:ReturnArgument, HLAservice:String, "
            "HLAsuppliedArguments:SuppliedArgumentList, HLAsuccessIndicator:Boolean, "
            "HLAexception:String>. The encoding spells this field HLAservce, while the same-row "
        "example uses HLAservice; use HLAservice as the semantic field name and preserve the "
        "encoding typo in the source-anomaly ledger. The example continues on page 302.",
        ),
        (
            301,
            2,
            "ServiceReportRecord field HLAreturnedArgument:ReturnArgument",
            "HLAreturnedArgument:ReturnArgument is a field of ServiceReportRecord, not a separate "
            "Table 5 type.",
        ),
        (
            301,
            3,
            "ServiceReportRecord field HLAservce:String source spelling",
            "The ServiceReportRecord encoding literally spells the field HLAservce:String, "
            "while the same-row example names it HLAservice. The semantic field is HLAservice; "
            "HLAservce is retained as source evidence and is not an independent Table 5 type.",
        ),
        (
            301,
            4,
            "ServiceReportRecord field HLAsuppliedArguments:SuppliedArgumentList",
            "HLAsuppliedArguments:SuppliedArgumentList is a field of ServiceReportRecord, not a "
            "separate Table 5 type.",
        ),
        (
            301,
            5,
            "ServiceReportRecord field HLAsuccessIndicator:Boolean",
            "HLAsuccessIndicator:Boolean is a field of ServiceReportRecord, not a separate Table "
            "5 type.",
        ),
        (
            301,
            6,
            "ServiceReportRecord field HLAexception:String",
            "HLAexception:String is a field of ServiceReportRecord, not a separate Table 5 type.",
        ),
        (
            302,
            1,
            "ServiceReportRecord example continuation",
            "The page-302 ‘ServiceReportRecord (cont.)’ entry continues the example for the "
            "ServiceReportRecord row begun on page 301; it does not define a separate Table 5 "
            "type or requirement.",
        ),
        (
            303,
            1,
            "SuppliedArgumentList",
            "Table 5 defines SuppliedArgumentList as Array<HLAargument>. The page-303 example "
            "begins with InteractionClassHandle, Parameters, UserSuppliedTag, SentOrderType, and "
            "TransportationType arguments; the same example continues on page 304. Its printed "
            "argument type numbers remain source-local examples.",
        ),
        (
            304,
            1,
            "SuppliedArgumentList example continuation",
            "The page-304 ‘SuppliedArgumentList (cont.)’ entry continues the page-303 array "
            "example with ProducingFederateHandle, TimeStamp, ReceiveOrderType, "
            "MessageRetractionDesignator, and SentRegionDesignators. It is not a separate Table 5 "
            "type or requirement.",
        ),
        (
            304,
            2,
            "SynchronizationPointFailureReason",
            "Table 5 defines SynchronizationPointFailureReason as "
            "Enumeration<SYNCHRONIZATION_POINT_LABEL_NOT_UNIQUE, "
            "SYNCHRONIZATION_SET_MEMBER_NOT_JOINED>. Its printed example is "
            "SYNCHRONIZATION_SET_MEMBER_NOT_JOINED.",
        ),
        (
            304,
            3,
            "SynchronizationPointFailureReason wrapped enumerant continuation",
            "The fragment ‘NIQUE’ completes the wrapped enumerant "
            "SYNCHRONIZATION_POINT_LABEL_NOT_UNIQUE in the Table 5 encoding. It is not a "
            "separate Table 5 type or enumerant.",
        ),
        (
            304,
            4,
            "SynchronizationPointFailureReason enumerant SYNCHRONIZATION_SET_MEMBER_NOT_JOINED",
            "SYNCHRONIZATION_SET_MEMBER_NOT_JOINED is an enumerant of "
            "SynchronizationPointFailureReason, not a separate Table 5 type.",
        ),
        (
            304,
            5,
            "TimeIntervalQueryReturn",
            "Table 5 defines TimeIntervalQueryReturn as Record<intervalIsValid:Boolean, "
            "interval:LogicalTimeInterval>. The printed example uses intervalIsValid=true and "
            'interval="HLAfloat64TimeInterval<0.05>".',
        ),
        (
            304,
            6,
            "TimeIntervalQueryReturn field interval:LogicalTimeInterval",
            "interval:LogicalTimeInterval is a field of TimeIntervalQueryReturn, not a separate "
            "Table 5 type.",
        ),
        (
            304,
            7,
            "TimeQueryReturn",
            "Table 5 defines TimeQueryReturn as Record<timeIsValid:Boolean, time:LogicalTime>. "
            'The printed example uses timeIsValid=true and time="HLAfloat64Time<1.0>".',
        ),
        (
            304,
            8,
            "TimeQueryReturn field time:LogicalTime",
            "time:LogicalTime is a field of TimeQueryReturn, not a separate Table 5 type.",
        ),
    )
    for page, ordinal, title, statement in reviewed_rows:
        set_row(page, ordinal, title, statement)

    # Conflicting numeric example values remain literal, scoped evidence. They
    # remain distinct from the canonical enumerants explicitly defined in Table 14.
    set_coverage_note(
        "requirement-candidate-table-5-p298-r009",
        "Structured Table 5 type, field, or enumerant; example values illustrate the source "
        "and do not create a lexical requirement. Table 14 assigns UserSuppliedTag=60; "
        "preserve the page-298 HLAargumentType=58 as conflicting example evidence.",
    )
    set_coverage_note(
        "requirement-candidate-table-5-p298-r012",
        "Structured Table 5 type, field, or enumerant; example values illustrate the source "
        "and do not create a lexical requirement. Table 14 assigns "
        "InteractionClassHandle=27; preserve the page-298 HLAargumentType=24 as conflicting "
        "example evidence.",
    )
    set_coverage_note(
        "requirement-candidate-table-5-p303-r001",
        "Structured Table 5 type, field, or enumerant; example values illustrate the source "
        "and do not create a lexical requirement. The page-303 InteractionClassHandle=27 "
        "agrees with Table 14; preserve UserSuppliedTag=63 as a conflicting example value.",
    )
    set_coverage_note(
        "requirement-candidate-table-5-p299-r008",
        "Structured Table 5 row candidate; it records the wire-shape source without promoting "
        "the example to a normative lexical rule. BinaryData is base-64-encoded per the "
        "page-292 definition; preserve xFDcMa and R6lkHla as printed examples without "
        "generalizing them as valid encoding behavior.",
    )
    set_coverage_note(
        "requirement-candidate-table-5-p301-r001",
        "Structured Table 5 type, field, or enumerant; example values illustrate the source "
        "and do not create a lexical requirement. Use HLAservice as the semantic field name "
        "because the same-row example uses that spelling; retain HLAservce as source evidence.",
    )
    set_coverage_note(
        "requirement-candidate-table-5-p301-r003",
        "Structured Table 5 type, field, or enumerant; example values illustrate the source "
        "and do not create a lexical requirement. HLAservce is a source spelling variant of "
        "the HLAservice field, not an independently named semantic field.",
    )

    # Point each repaired parent at the printed type label and include its
    # complete source row. Child and continuation records point at the exact
    # printed field, enumerant, or continuation token that they describe.
    spans = {
        (297, 8): (144, 199),
        (297, 9): (150, 150),
        (297, 10): (153, 153),
        (297, 11): (156, 156),
        (297, 12): (159, 159),
        (297, 13): (162, 162),
        (297, 14): (204, 225),
        (297, 15): (210, 210),
        (297, 16): (213, 213),
        (298, 2): (54, 78),
        (298, 3): (63, 63),
        (298, 4): (66, 66),
        (298, 5): (81, 117),
        (298, 6): (84, 84),
        (298, 8): (129, 150),
        (298, 9): (153, 177),
        (298, 10): (159, 159),
        (298, 11): (162, 162),
        (298, 12): (180, 198),
        (298, 13): (186, 186),
        (298, 19): (246, 264),
        (298, 20): (252, 252),
        (300, 1): (18, 36),
        (300, 2): (24, 24),
        (300, 3): (27, 27),
        (300, 4): (30, 30),
        (300, 5): (33, 33),
        (300, 6): (39, 54),
        (300, 7): (45, 45),
        (300, 8): (48, 48),
        (300, 9): (51, 51),
        (300, 10): (57, 78),
        (300, 11): (63, 63),
        (300, 12): (66, 66),
        (300, 13): (69, 69),
        (300, 14): (72, 72),
        (300, 15): (75, 75),
        (300, 16): (81, 201),
        (300, 17): (87, 87),
        (300, 18): (90, 90),
        (301, 1): (18, 179),
        (301, 2): (24, 24),
        (301, 3): (27, 27),
        (301, 4): (30, 30),
        (301, 5): (33, 33),
        (301, 6): (36, 36),
        (302, 1): (18, 84),
        (303, 1): (18, 115),
        (304, 1): (18, 105),
        (304, 2): (108, 120),
        (304, 3): (114, 114),
        (304, 4): (117, 117),
        (304, 5): (123, 141),
        (304, 6): (129, 129),
        (304, 7): (144, 162),
        (304, 8): (150, 150),
    }
    for (page, ordinal), (line, end_line) in spans.items():
        row = rows[f"requirement-candidate-table-5-p{page}-r{ordinal:03d}"]
        row.source = SourceRef(path=row.source.path, line=line, end_line=end_line)

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
        row = rows[f"requirement-candidate-table-5-p{page}-r{ordinal:03d}"]
        row.source = SourceRef(path=row.source.path, line=line, end_line=end_line)
    _write_requirements(payload)

    ledger_path = semantic_root() / "source-anomaly-ledger.json"
    ledger = SourceAnomalyLedger.model_validate_json(ledger_path.read_text(encoding="utf-8"))
    anomaly_records = (
        SourceAnomaly(
            source_id="hla15161-table-5-hlaargument-example-type-codes",
            related_issue_id="RL-399",
            location="Table 5, pages 298, 301, and 303, HLAargument examples",
            source_text=(
                "Table 14 defines HLAargumentType enumerants UserSuppliedTag=60 and "
                "InteractionClassHandle=27. Table 5 examples instead print 58 and 24 on page "
                "298, 63 for UserSuppliedTag on pages 301 and 303, and 27 for "
                "InteractionClassHandle on pages 301 and 303. The 1516.2 MIM agrees with the "
                "Table 14 enumerants."
            ),
            rendered_text=(
                "Use Table 14's HLAargumentType enumerants as the semantic mapping: "
                "InteractionClassHandle=27 and UserSuppliedTag=60. Preserve each differing "
                "Table 5 example number verbatim and label it as conflicting example evidence."
            ),
            classification="SOURCE_ANOMALY",
            reason=(
                "Table 14 directly defines the enum values and the source states that "
                "HLAargumentType follows that table. The conflicting Table 5 examples therefore "
                "do not leave the semantic type mapping ambiguous, although the example defect "
                "itself remains unresolved."
            ),
            review_status="DISPOSITIONED",
            resolution=(
                "Map argument types from Table 14: InteractionClassHandle=27 and "
                "UserSuppliedTag=60. Preserve Table 5 example values 24, 58, and 63 with their "
                "page and record provenance; do not normalize or promote them to enum values."
            ),
            mapping_effect=(
                "Consumers can map the canonical enum values from Table 14 while retaining "
                "conflicting Table 5 example literals as source anomalies."
            ),
            evidence_refs=(
                "content-15161-page-298",
                "content-15161-page-301",
                "content-15161-page-303",
                "content-15161-page-325",
                "content-15161-page-326",
                "1516.1 Table 14, HLAargumentType enumerants, pp. 325-326",
                "Umbra third_party/ieee1516.2-2025/resources/mim/HLAstandardMIM-2025.xml:3323-3324,3455-3456",
            ),
        ),
        SourceAnomaly(
            source_id="hla15161-table-5-binary-data-examples",
            related_issue_id="RL-403",
            location="Table 5, page 299, ParameterHandleValueMap example",
            source_text=(
                "The ParameterHandleValueMap example prints xFDcMa and R6lkHla as values "
                "for Binary Data. The page-292 Binary Data definition describes base-64 "
                "encoded data. These example literals omit base-64 padding and do not encode "
                "canonical zero pad bits."
            ),
            rendered_text=(
                "Map BinaryData as base-64-encoded data. Preserve xFDcMa and R6lkHla as "
                "printed examples, but do not treat their malformed/non-canonical spelling as "
                "an executable encoder contract."
            ),
            classification="SOURCE_ANOMALY",
            reason=(
                "The captured definition specifies base-64 while the printed examples omit "
                "padding and have non-zero pad bits under the standard base-64 alphabet. The "
                "source text does not authorize this alternate lexical form."
            ),
            review_status="DISPOSITIONED",
            resolution=(
                "Retain the exact example literals as conflicting source examples. Validate "
                "BinaryData against the base-64 definition using independently valid values; "
                "do not invent an unpadded/non-canonical encoding profile to fit the examples."
            ),
            mapping_effect=(
                "The PairList<ParameterHandle:BinaryData> structure and base-64 semantic type "
                "are mapped; only the conformance of the printed example strings remains open."
            ),
            evidence_refs=(
                "content-15161-page-292",
                "content-15161-page-295",
                "content-15161-page-299",
                "data/hla-backflow-2026-11-23.json#RL-403 upstream_record",
            ),
        ),
        SourceAnomaly(
            source_id="hla15161-table-5-servicereportrecord-field-spelling",
            related_issue_id="RL-407",
            location="Table 5, page 301, ServiceReportRecord row",
            source_text=(
                "The encoding column prints HLAservce:String, while the example object "
                "prints the corresponding key as HLAservice."
            ),
            rendered_text=(
                "Use HLAservice as the semantic field name, matching the same-row JSON example "
                "and the document's repeated identifier spelling. Preserve HLAservce:String as "
                "the printed encoding typo in this anomaly record."
            ),
            classification="SOURCE_ANOMALY",
            reason=(
                "The encoding and example in the same captured row disagree by one omitted "
                "letter; the example and the rest of the document consistently use HLAservice."
            ),
            review_status="DISPOSITIONED",
            resolution=(
                "Normalize the derived field identity to HLAservice:String because the same-row "
                "example key and document terminology corroborate it. Keep HLAservce:String "
                "verbatim in the source evidence; do not alter the captured source."
            ),
            mapping_effect=(
                "The ServiceReportRecord has one semantic HLAservice field. HLAservce is a "
                "source spelling anomaly, not a second field or API member."
            ),
            evidence_refs=("content-15161-page-301", "data/hla-backflow-2026-11-23.json#RL-407 upstream_record"),
        ),
    )
    # Reconcile by stable source ID, not just append-if-absent. These entries
    # predate the backflow review and already exist with unresolved dispositions;
    # leaving them in place would make the migration appear successful while
    # preserving the very ambiguity this migration is meant to close.
    replacements = {item.source_id: item for item in anomaly_records}
    updated = tuple(
        replacements.pop(item.source_id, item)
        for item in ledger.entries
    ) + tuple(replacements.values())
    reviewed_ledger = SourceAnomalyLedger(
        schema_version=ledger.schema_version,
        document_id=ledger.document_id,
        purpose=ledger.purpose,
        entries=updated,
    )
    ledger_path.write_text(
        reviewed_ledger.model_dump_json(indent=2, exclude_unset=True) + "\n",
        encoding="utf-8",
    )


def repair_time_table_and_caption() -> None:
    """Restore the TAR bound and remove a caption fragment from the catalog."""
    payload = _read_requirements()
    by_id = {item.id: item for item in payload.requirements}
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
    if continuation not in order_rule.coverage_note:
        order_rule.coverage_note += continuation
    obsolete = TIME + "181-l115-2"
    if obsolete not in by_id:
        candidate = _MutableRequirement.model_validate(
            by_id[TIME + "180-l156-49"].model_dump(mode="python", exclude_unset=True)
        )
        candidate.id = obsolete
        payload.requirements.append(candidate)
    else:
        candidate = by_id[obsolete]
    candidate.title = "Non-normative Table 2 introduction"
    candidate.statement = (
        "Table 2 illustrates how the order type of a sent message shall be determined."
    )
    candidate.machine_statement = candidate.statement
    candidate.extraction = "candidate"
    candidate.coverage_note = "Layout prose introducing Table 2; reviewed as non-normative."
    candidate.source = SourceRef(
        path="content/clauses/08-time-management-page-181.tex", line=112, end_line=115
    )
    _write_requirements(payload)

    blocks = _read_content_blocks()
    for item in blocks.content_blocks:
        if item.id == "content-15161-page-181" and obsolete not in item.record_ids:
            item.record_ids += (obsolete,)
    _write_content_blocks(blocks)

    elements = _read_content_elements()
    for item in elements.content_elements:
        if item.block_id == "content-15161-page-181" and obsolete not in item.record_ids:
            item.record_ids += (obsolete,)
    _write_content_elements(elements)

    reviews = _read_requirement_reviews()
    review = next((item for item in reviews.reviews if item.requirement_id == obsolete), None)
    if review is None:
        reviews.reviews.append(
            _MutableRequirementReview(
                requirement_id=obsolete,
                status="non-normative",
                reason=(
                    "Table 2 introduction is explanatory layout prose, not a standalone obligation."
                ),
                source=candidate.source,
            )
        )
    else:
        review.source = candidate.source
    _write_requirement_reviews(reviews)

    bindings = _read_requirement_api_bindings()
    binding = next((item for item in bindings.bindings if item.requirement_id == obsolete), None)
    if binding is None:
        bindings.bindings.append(
            _MutableRequirementApiBinding(
                id=f"binding.{obsolete}.no-api",
                requirement_id=obsolete,
                api_surface_id=None,
                candidate_api_surface_ids=(),
                language="unspecified",
                relationship="cross-cutting",
                status="reviewed",
                rationale="Explanatory Table 2 introduction reviewed as non-normative.",
                source=candidate.source,
            )
        )
    else:
        binding.source = candidate.source
    _write_requirement_api_bindings(bindings)


def restore_missing_service_flow_candidates() -> None:
    """Add the omitted NMRA and Get Dimension Handle flow items."""
    requirements = _read_requirements()
    by_id = {item.id: item for item in requirements.requirements}
    surfaces = _read_api_surfaces()
    by_surface = {item.id: item for item in surfaces.api_surfaces}
    specs = (
        (
            "requirement-service-flow-nmra-current-time-precondition",
            "8.11.3",
            "08-time-management-page-199.tex",
            146,
            148,
            "The specified logical time for Next Message Request Available must be "
            "greater than or equal to the joined federate's logical time.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            199,
        ),
        (
            "requirement-service-flow-nmra-time-passed-exception",
            "8.11.5",
            "08-time-management-page-200.tex",
            63,
            63,
            "Next Message Request Available lists Logical Time Already Passed as "
            "an exception when the requested logical time is behind the joined federate's time.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            200,
        ),
        (
            "requirement-service-flow-nmra-not-advancing-precondition",
            "8.11.3",
            "08-time-management-page-200.tex",
            12,
            12,
            "For Next Message Request Available, the joined federate must not be "
            "in the Time Advancing state.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            200,
        ),
        (
            "requirement-service-flow-nmra-advancing-exception",
            "8.11.5",
            "08-time-management-page-200.tex",
            75,
            75,
            "Next Message Request Available lists Joined Federate in Time Advancing "
            "State as an exception.",
            "api.2025.cpp.rtiambassador.nextmessagerequestavailable.53e69adb796b",
            200,
        ),
        (
            "requirement-service-flow-get-dimension-handle-name-not-found",
            "10.23.5",
            "10-support-services-page-260.tex",
            36,
            36,
            "Get Dimension Handle lists a dimension not defined in the FDD as an "
            "exception; the C++ getDimensionHandle declaration names this NameNotFound.",
            "api.2025.cpp.rtiambassador.getdimensionhandle.7a343b0ace0a",
            260,
        ),
    )
    blocks = _read_content_blocks()
    elements = _read_content_elements()
    for requirement_id, clause, path, line, end_line, statement, api_id, page in specs:
        source = SourceRef(path="content/clauses/" + path, line=line, end_line=end_line)
        if requirement_id not in by_id:
            record = _MutableRequirement(
                id=requirement_id,
                title=f"Service-flow item at {source.path}:{line}",
                statement=statement,
                kind="detailed",
                clause=clause,
                clause_id=f"clause-{clause}",
                machine_statement=statement,
                transition_ids=(),
                coverage_kind="cross-cutting",
                coverage_note=(
                    "Explicit service-flow precondition or exception from the pinned 2025 source."
                ),
                api_surface_scope="required",
                api_surface_note=(
                    "Reviewed against the official 2025 C++ RTIambassador declaration."
                ),
                api_surface_resolution="strict",
                extraction="explicit",
                semantic_group_id=f"m17.service-flow.{clause}",
                source=source,
            )
            requirements.requirements.append(record)
            by_id[requirement_id] = record
        else:
            record = by_id[requirement_id]
            record.source = source
            record.title = f"Service-flow item at {source.path}:{line}"
            record.statement = statement
            record.machine_statement = statement
        surface = by_surface[api_id]
        if requirement_id not in surface.requirement_ids:
            surface.requirement_ids += (requirement_id,)
        block = next(
            item for item in blocks.content_blocks if item.id == f"content-15161-page-{page}"
        )
        if requirement_id not in block.record_ids:
            block.record_ids += (requirement_id,)
        element = next(item for item in elements.content_elements if item.block_id == block.id)
        if requirement_id not in element.record_ids:
            element.record_ids += (requirement_id,)
    _write_requirements(requirements)
    _write_api_surfaces(surfaces)
    _write_content_blocks(blocks)
    _write_content_elements(elements)
