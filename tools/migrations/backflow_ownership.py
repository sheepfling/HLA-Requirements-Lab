"""Focused 1516.1 backflow repair operations."""

from __future__ import annotations

from tools.migrations.backflow_common import (
    FEDERATION,
    OWNERSHIP,
    TIME,
    _read_requirement_file,
    _read_requirements,
    _set_statement,
    _write_requirement_file,
    _write_requirements,
    omt_semantic_root,
)


def repair_ownership_overview() -> None:
    """Make the Clause 7 ownership overview candidates complete."""
    payload = _read_requirements()
    by_id = {item.id: item for item in payload.requirements}
    corrections = {
        "16-3": (
            "The ability to transfer ownership of instance attributes among joined federates "
            "shall be required to support the cooperative modeling of a given object instance "
            "across a federation.",
            16,
            23,
        ),
        "22-5": (
            "Only the joined federate that owns an instance attribute shall invoke the Update "
            "Attribute Values service to provide a new value for that instance attribute, "
            "receive invocations of the Provide Attribute Value Update service for that "
            "instance attribute, and receive invocations of the Turn Updates On For Object "
            "Instance and Turn Updates Off For Object Instance services pertaining to that "
            "instance attribute.",
            22,
            45,
        ),
        "52-15": (
            "The RTI shall generate exceptions if illegal ownership operations are invoked.",
            49,
            56,
        ),
        "58-17": (
            "An instance attribute shall not be owned by more than one joined federate.",
            58,
            61,
        ),
        "61-18": (
            "An instance attribute may be unowned by all joined federates. The RTI shall be "
            "responsible for attempting to find an owner for instance attributes that are "
            "left unowned as a result of a joined federate resignation or unconditional "
            "divestiture.",
            58,
            68,
        ),
        "70-21": (
            "The RTI shall invoke the Request Attribute Ownership Assumption service once at "
            "each joined federate that is both eligible to own the instance attribute and "
            "eligible to receive a Request Attribute Ownership Assumption service invocation "
            "for that instance attribute until the instance attribute becomes owned.",
            70,
            80,
        ),
        "82-25": (
            "From a given joined federate\u2019s perspective, every instance attribute shall "
            "be either owned or unowned; the owned and unowned states are exclusive.",
            79,
            86,
        ),
        "88-27": (
            "Upon registration of an object instance, the registering joined federate shall "
            "own all instance attributes of that object instance for which the joined federate "
            "is publishing the corresponding class attributes at the registered class of "
            "the object instance.",
            88,
            97,
        ),
        "94-29": (
            "All other instance attributes of that object instance shall be unowned by all "
            "joined federates.",
            94,
            99,
        ),
        "100-31": (
            "As a result of a new FOM Module merge, if new instance attributes of an existing "
            "object are created, those instance attributes shall be unowned by all joined "
            "federates.",
            97,
            103,
        ),
        "103-32": (
            "Upon discovery of an object instance, the discovering joined federate shall "
            "not own any instance attributes of that object instance.",
            103,
            107,
        ),
        "106-33": (
            "If a joined federate does not own an instance attribute, it shall not own that "
            "instance attribute until it has received an Attribute Ownership Acquisition "
            "Notification service invocation for it.",
            106,
            111,
        ),
        "112-35": (
            "Ownership of an instance attribute shall be transferred from one joined federate "
            "to another either by the owning joined federate requesting to divest itself of "
            "the instance attribute or by a non-owning joined federate requesting to acquire it.",
            112,
            120,
        ),
        "121-38": (
            "Regardless of whether an instance attribute changes ownership as a result of "
            "being divested by its owner or acquired by a non-owner, the instance attribute "
            "shall change ownership only as a result of explicit service invocations by the "
            "owning and acquiring joined federates.",
            118,
            126,
        ),
        "124-39": (
            "The RTI shall not take ownership away from, nor give it to, a joined federate "
            "without the joined federate\u2019s consent, except through the following MOM "
            "interactions: HLAmanager.HLAfederate.HLAadjust.HLAmodifyAttributeState; "
            "HLAmanager.HLAfederate.HLAservice.HLAunpublishObjectClassAttributes; "
            "HLAmanager.HLAfederate.HLAservice.HLAunconditionalAttributeOwnershipDivestiture; "
            "and HLAmanager.HLAfederate.HLAservice.HLAresignFederationExecution.",
            124,
            157,
        ),
    }
    for suffix, (statement, line, end_line) in corrections.items():
        _set_statement(by_id[OWNERSHIP + "148-l" + suffix], statement, line, end_line)
    _write_requirements(payload)


def repair_time_order_and_acquisition() -> None:
    """Restore complete rules for FQR, order type, and acquisition."""
    payload = _read_requirements()
    by_id = {item.id: item for item in payload.requirements}
    corrections = {
        TIME + "200-l131-38": (
            "The Flush Queue Request service shall request that all messages queued in the RTI "
            "that the joined federate will receive as TSO messages be delivered now.",
            131,
            136,
        ),
        TIME + "200-l134-39": (
            "The RTI shall deliver all such messages as soon as possible, despite the fact "
            "that it may not be able to guarantee that no future messages containing smaller "
            "timestamps could arrive.",
            134,
            142,
        ),
        TIME + "200-l140-41": (
            "The RTI shall advance the joined federate\u2019s logical time to the smallest of "
            "the specified logical time, the joined federate\u2019s GALT value, and the smallest "
            "timestamp of all TSO messages delivered by the RTI in response to this Flush "
            "Queue Request invocation.",
            140,
            163,
        ),
        TIME + "200-l164-49": (
            "The RTI shall also provide an optimistic logical time that it would grant the "
            "federate if the logical time were not constrained by the federate\u2019s GALT.",
            164,
            169,
        ),
        TIME + "200-l170-51": (
            "If GALT is not the determining value in advancing the joined federate\u2019s "
            "logical time, the logical time and optimistic logical time shall be the same.",
            167,
            172,
        ),
        TIME + "200-l173-52": (
            "Invocation of the Flush Queue Request service shall cause all messages queued "
            "in the RTI that the joined federate will receive as RO or TSO messages to be "
            "delivered to the joined federate.",
            173,
            188,
        ),
        TIME + "213-l76-20": (
            "Upon a federate gaining ownership of an instance attribute (either through "
            "registration or ownership transfer), the instance attribute\u2019s order type shall "
            "be initialized using the federate\u2019s corresponding class attribute default "
            "order type.",
            73,
            81,
        ),
        TIME + "213-l79-21": (
            "For each federate when joining, a class attribute\u2019s default order type shall "
            "be initialized from the corresponding class attribute description in the current FDD.",
            79,
            84,
        ),
        TIME + "213-l88-24": (
            "When changing a default order type, a class attribute shall be specified using "
            "a class handle for which the class attribute is available along with the class "
            "attribute\u2019s handle.",
            85,
            92,
        ),
        TIME + "213-l94-26": (
            "Invoking the Change Default Attribute Order Type service on a class attribute "
            "shall affect the order type of a federate\u2019s future instance attributes of the "
            "class attribute irrespective of the object class used in the invocation. "
            "Existing owned object instances will not change their current order type, nor "
            "will the class attribute default order type of other federates.",
            91,
            102,
        ),
        OWNERSHIP + "161-l152-45": (
            "If a specified instance attribute is owned by another joined federate that is "
            "in the Waiting for a New Owner to be Found state, the RTI shall not invoke the "
            "Request Attribute Ownership Release service for that instance attribute at the "
            "owning joined federate, but it shall invoke the Request Divestiture Confirmation "
            "service for that instance attribute at the owning joined federate.",
            149,
            162,
        ),
        OWNERSHIP + "161-l158-47": (
            "The joined federate may receive one or more Attribute Ownership Acquisition "
            "Notification invocations for each invocation of the Attribute Ownership "
            "Acquisition service.",
            158,
            166,
        ),
        OWNERSHIP + "161-l167-50": (
            "A request to acquire ownership shall remain pending until the request is granted "
            "via Attribute Ownership Acquisition Notification, the acquisition is denied via "
            "Attribute Ownership Unavailable, or the requesting joined federate successfully "
            "cancels the request via Cancel Attribute Ownership Acquisition and Confirm "
            "Attribute Ownership Acquisition Cancellation services.",
            167,
            173,
        ),
    }
    for requirement_id, (statement, line, end_line) in corrections.items():
        _set_statement(by_id[requirement_id], statement, line, end_line)
    continuation_note = (
        " The final denial and cancellation alternatives continue in "
        "content/clauses/07-ownership-management-page-162.tex:7-10."
    )
    record = by_id[OWNERSHIP + "161-l167-50"]
    if continuation_note.strip() not in record.coverage_note:
        record.coverage_note += continuation_note
    _write_requirements(payload)


def repair_cross_page_statements() -> None:
    """Join statements whose last source line is on the next physical page."""
    payload = _read_requirements()
    by_id = {item.id: item for item in payload.requirements}
    save = by_id[FEDERATION + "065-l109-26"]
    _set_statement(
        save,
        "If a valid optional timestamp argument is present, the RTI shall instruct each "
        "time-constrained joined federate to save state (via the Initiate Federate Save "
        "service) as soon as the joined federate has received all messages that it will "
        "receive as TSO messages that have timestamps less than or equal to the timestamp "
        "of the scheduled save and either the joined federate is in the Time Advancing "
        "state as a result of invocation of a Time Advance Request Available, Next "
        "Message Request Available, or Flush Queue Request service and the timestamp "
        "of the next grant is greater than the timestamp of the scheduled save, or the "
        "joined federate is in the Time Advancing state as a result of invocation of "
        "either a Time Advance Request or Next Message Request service and the timestamp "
        "of the next grant is greater than or equal to the timestamp of the scheduled save.",
        109,
        131,
    )
    grant = by_id[TIME + "198-l192-57"]
    _set_statement(
        grant,
        "The RTI shall not guarantee delivery of all messages with timestamps equal to "
        "T when a Time Advance Grant service invocation to logical time T is issued, "
        "and after the joined federate receives a Time Advance Grant service invocation "
        "to logical time T, it can send additional messages with timestamps equal to T "
        "if the joined federate's lookahead is zero.",
        192,
        197,
    )
    note = (
        " The second bullet continues in "
        "output/semantic/content-block-content-15161-page-199.tex:14-17."
    )
    if note.strip() not in grant.coverage_note:
        grant.coverage_note += note
    _write_requirements(payload)

    path = omt_semantic_root() / "requirements.json"
    omt = _read_requirement_file(path)
    record = next(
        item
        for item in omt.requirements
        if item.id == "requirement-candidate-sections-semantic-clause-7-annexes-a-c-page-110-l90-20"
    )
    _set_statement(
        record,
        "The following applies for each named variant record data type using the "
        "HLAextendableVariantRecord encoding: Alternatives of variant record, with "
        "sub-elements alternative type and alternative semantics shall be merged. For "
        "a named alternative of a variant record, all discriminant enumerators shall be "
        "merged. If the same named discriminant enumerator is specified for more than one "
        "named alternative, either as a single enumerator or part of a range, the merge "
        "shall fail. In case a variant record data type with HLAextendableVariantRecord "
        "includes an alternative using HLAother, the merge shall also fail.",
        89,
        89,
    )
    note = (
        " The final conditions continue in "
        "output/semantic/content-block-content-15162-page-111.tex:37-38."
    )
    if note.strip() not in record.coverage_note:
        record.coverage_note += note
    _write_requirement_file(path, omt)
