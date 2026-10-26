"""Repair sentence boundaries missed by the clause-attribution pass."""

from __future__ import annotations

from tools.migrations.backflow_common import (
    DDM,
    OWNERSHIP,
    SUPPORT,
    TIME,
    _read_requirements,
    _set_statement,
    _write_requirements,
)


def repair_clipped_clause_statements() -> None:
    """Restore full sentences from the pinned page layouts, retaining stable IDs."""
    payload = _read_requirements()
    by_id = {item.id: item for item in payload.requirements}
    corrections = {
        OWNERSHIP + "153-l15-4": (
            "When a joined federate invokes the Attribute Ownership Acquisition service "
            "invocation, this request shall remain pending until the instance attribute is "
            "acquired (as indicated "
            "by an invocation of the Attribute Ownership Acquisition Notification service), "
            "acquisition of the instance attribute is denied (as indicated by an invocation of the "
            "Attribute Ownership Unavailable service), or the joined federate successfully cancels "
            "the acquisition request.",
            12,
            25,
        ),
        OWNERSHIP + "153-l30-9": (
            "The Cancel Attribute Ownership Acquisition service is not guaranteed to be "
            "successful. If it is successful, the RTI shall indicate this success to the "
            "canceling joined federate "
            "by invoking the Confirm Attribute Ownership Acquisition Cancellation service.",
            27,
            37,
        ),
        OWNERSHIP + "153-l36-11": (
            "If it fails, the RTI shall indicate this failure to the canceling joined federate "
            "by invoking the Attribute Ownership Acquisition Notification service, thereby "
            "granting ownership of the instance attribute to the joined federate.",
            36,
            43,
        ),
        OWNERSHIP + "153-l45-14": (
            "An Attribute Ownership Acquisition service invocation shall override an Attribute "
            "Ownership Acquisition If Available service invocation. In other words, a joined "
            "federate that has invoked the Attribute Ownership Acquisition If Available service "
            "may, before it receives an invocation of either the Attribute Ownership Acquisition "
            "Notification service or the Attribute Ownership Unavailable service, invoke the "
            "Attribute Ownership Acquisition service.",
            45,
            59,
        ),
        OWNERSHIP + "153-l60-19": (
            "In this case, the Attribute Ownership Acquisition If Available service request shall "
            "be implicitly canceled, and the Attribute Ownership Acquisition service request shall "
            "remain pending until the instance attribute is acquired, acquisition of the instance "
            "attribute is denied, or the joined federate successfully cancels the acquisition "
            "request.",
            57,
            67,
        ),
        OWNERSHIP + "153-l75-24": (
            "A joined federate that has invoked the Attribute Ownership Acquisition service, but "
            "has not yet received an invocation of the Attribute Ownership Acquisition "
            "Notification "
            "service, the Attribute Ownership Unavailable service, or the Confirm Attribute "
            "Ownership Acquisition Cancellation service, shall not invoke the Attribute Ownership "
            "Acquisition If Available service.",
            66,
            79,
        ),
        OWNERSHIP + "153-l84-26": (
            "All object classes shall have an available attribute called "
            "HLAprivilegeToDeleteObject.",
            84,
            86,
        ),
        OWNERSHIP + "153-l87-27": (
            "As with all other available attributes, a joined federate shall be publishing the "
            "HLAprivilegeToDeleteObject class attribute at the known class of an object instance "
            "in order to be eligible for ownership of a corresponding HLAprivilegeToDeleteObject "
            "instance attribute.",
            85,
            94,
        ),
        OWNERSHIP + "153-l96-30": (
            "A HLAprivilegeToDeleteObject instance attribute shall be transferable among joined "
            "federates.",
            96,
            98,
        ),
        OWNERSHIP + "153-l99-31": (
            "All ownership management services for HLAprivilegeToDeleteObject instance "
            "attributes shall act the same as they are for all other instance attributes.",
            98,
            103,
        ),
        OWNERSHIP + "153-l108-34": (
            "Ownership of a typical instance attribute shall give a joined federate the privilege "
            "to provide new values for that instance attribute.",
            105,
            110,
        ),
        OWNERSHIP + "153-l123-38": (
            "These arguments shall be provided as a mechanism for conducting information between "
            "joined federates that could be used to implement priority or other schemes.",
            120,
            126,
        ),
        OWNERSHIP + "153-l129-40": (
            "Although the content and use of these tags are outside of the scope of this "
            "specification, the RTI shall pass these user-supplied tags from joined federates "
            "that are trying to acquire an instance attribute to the joined federate that owns "
            "the instance attribute and from the joined federate that is trying to divest itself "
            "of an instance attribute to the joined federates that are able to acquire the "
            "instance attribute.",
            126,
            139,
        ),
        DDM + "220-l8-2": (
            "Any region specifications used to generate region realizations associated with an "
            "instance attribute for update shall contain only dimensions that are a subset of "
            "the available dimensions of that instance attribute.",
            5,
            11,
        ),
        DDM + "220-l11-3": (
            "The resulting region realizations shall have the same property.",
            11,
            13,
        ),
        DDM + "220-l14-4": (
            "A joined federate shall use a region for update of an instance attribute to assert "
            "properties of that instance attribute.",
            14,
            18,
        ),
        DDM + "220-l17-5": (
            "These properties shall be used to limit reflection of the instance attributes when "
            "the joined federate invokes the Update Attribute Values service.",
            17,
            21,
        ),
        DDM + "220-l26-8": (
            "If a region other than the default region is used for update of a particular "
            "instance attribute by a joined federate and the joined federate loses ownership of "
            "that instance attribute, that region shall no longer be used for update of that "
            "instance attribute.",
            20,
            30,
        ),
        DDM + "220-l35-11": (
            "A joined federate may create and modify update region associations with an instance "
            "attribute that is owned by another joined federate or that is unowned. These "
            "associations shall not take effect until the joined federate making the associations "
            "has acquired ownership of the specified instance attribute.",
            32,
            42,
        ),
        DDM + "220-l41-13": (
            "These associations shall take effect immediately upon acquiring ownership of the "
            "specified instance attributes.",
            41,
            45,
        ),
        DDM + "220-l50-16": (
            "In all cases, if a joined federate divests ownership of an instance attribute with "
            "which an update region is associated, that association shall be lost, as if the "
            "Unassociate Regions For Updates service had been invoked for that (object instance, "
            "region, attribute) triple.",
            47,
            54,
        ),
        DDM + "220-l56-18": (
            "Update region associations that are lost shall not come into effect if the joined "
            "federate subsequently acquires ownership of the instance attribute unless the "
            "joined federate explicitly recreates the association.",
            53,
            60,
        ),
        DDM + "220-l65-21": (
            "A region realization other than the default region shall be used for subscription "
            "of a class attribute if the joined federate has used the class attribute and a "
            "given object class and the region specification from which the region realization "
            "was derived as arguments in the Subscribe Object Class Attributes With Regions "
            "service.",
            65,
            75,
        ),
        DDM + "220-l77-25": (
            "Subsequently invoking the Unsubscribe Object Class Attributes With Regions "
            "service for the same (object class, region, attribute) triple shall cause the "
            "region not to be used for subscription of that class attribute.",
            74,
            81,
        ),
        DDM + "220-l86-28": (
            "Invoking the Subscribe Object Class Attributes With Regions service or the "
            "Unsubscribe Object Class Attributes With Regions service with an empty set of "
            "regions shall make no changes to the set of subscriptions with region of the class "
            "attribute.",
            80,
            87,
        ),
        DDM + "220-l92-30": (
            "Any region specifications used to generate region realizations associated with a "
            "class attribute for subscription shall contain only dimensions that are a subset "
            "of the available dimensions of that class attribute.",
            89,
            95,
        ),
        DDM + "220-l95-31": (
            "The resulting region realizations shall have the same property.",
            95,
            97,
        ),
        DDM + "220-l98-32": (
            "The default region shall be used for subscription of a class attribute if and only "
            "if that class attribute has available dimensions, there is no other region "
            "realization used for subscription of that class attribute, and the joined federate "
            "is subscribed to that class attribute.",
            98,
            105,
        ),
        DDM + "220-l107-35": (
            "Subsequently invoking the Unsubscribe Object Class Attributes service for the "
            "same object class and attribute shall cause the default region not to be used "
            "for subscription of that class attribute.",
            104,
            111,
        ),
        DDM + "225-l96-30": (
            "No change to the range values of the region realization from which the copy "
            "was made shall cause a change to the range values of the copy as long as the "
            "Reflect Attribute Values service or the Receive Interaction service invocation "
            "is still in progress.",
            95,
            102,
        ),
        TIME + "180-l21-5": (
            "Invocation of the Update Attribute Values service, Send Interaction service, Send "
            "Interaction with Regions service, or Delete Object Instance service by a joined "
            "federate shall be called sending a message.",
            18,
            24,
        ),
        TIME + "180-l27-7": (
            "Invocation of the Update Attribute Values service may actually result in the sending "
            "of multiple messages as each passel resulting from the invocation shall be considered "
            "a separate message.",
            23,
            30,
        ),
        TIME + "180-l39-11": (
            "Invocation of the Reflect Attribute Values service, Receive Interaction service, "
            "or Remove Object Instance service at a joined federate shall be called receiving a "
            "message.",
            36,
            40,
        ),
        TIME + "180-l45-13": (
            "The mapping from one sent message to one or more received messages shall follow "
            "the descriptions for Update Attribute Values service (see 6.10), Reflect Attribute "
            "Values service (see 6.11), Send Interaction service (see 6.12), Received Interaction "
            "service (see 6.13), Delete Object Instance service (see 6.16), Remove Object Instance "
            "service (see 6.17), and Send Interaction With Regions service (see 9.12).",
            44,
            57,
        ),
        TIME + "180-l57-17": (
            "For example, a sent message representing an Update Attribute Values service "
            "invocation shall result only in received messages representing Reflect Attribute "
            "Values service invocations at the appropriate joined federates depending on the "
            "normal ownership/subscription properties.",
            56,
            63,
        ),
        TIME + "180-l69-20": (
            "Each message, sent or received, shall be either a timestamp order (TSO) message "
            "or a receive order (RO) message (see 8.1.11).",
            69,
            72,
        ),
        TIME + "180-l72-21": (
            "The order type of a message shall be determined by several factors:",
            71,
            74,
        ),
        TIME + "180-l78-23": (
            "The preferred order type of a message shall be the same as the preferred order "
            "type of the data contained in the message (instance attribute values or "
            "interactions).",
            78,
            81,
        ),
        TIME + "180-l132-41": (
            "Whether a joined federate is time-regulating shall determine whether a joined "
            "federate can send TSO messages.",
            132,
            135,
        ),
        TIME + "180-l138-43": (
            "Whether a joined federate is time-constrained shall determine whether the joined "
            "federate can receive TSO messages.",
            135,
            138,
        ),
        TIME + "181-l118-3": (
            "Table 3 illustrates how the order type of a received message shall be determined.",
            118,
            120,
        ),
        TIME + "181-l121-4": (
            "The order type of a received message shall be determined by whether that joined "
            "federate is time-constrained and by the order type of the corresponding sent message. "
            "As shown in these two tables, a message retraction designator is provided to both "
            "the sender and the receiver if the sent message order type is TSO, regardless of "
            "the order type of the received message.",
            118,
            130,
        ),
        TIME + "181-l133-8": (
            "Because of the above rule defining the order type of a received message, the RTI "
            "shall sometimes convert a sent TSO message to a received RO message at some "
            "receiving joined federates.",
            133,
            136,
        ),
        TIME + "181-l139-10": (
            "The need for such conversions shall be considered on a per-joined-federate basis. "
            "Thus, the received messages at different joined federates that correspond to the "
            "same sent message may be of different order types.",
            135,
            142,
        ),
        TIME + "181-l145-12": (
            "Sent RO messages shall never be converted to received TSO messages.",
            142,
            145,
        ),
        TIME + "181-l148-13": (
            "Except when the Flush Queue Request service is used, messages that are received "
            "as TSO messages shall be received only by a given joined federate in TSO, regardless "
            "of the joined federates from which the messages originate and regardless of the "
            "sequence in which the messages were sent.",
            148,
            154,
        ),
        TIME + "181-l157-16": (
            "Thus, two TSO messages with different timestamps shall always be received by each "
            "joined federate in the same order. Multiple TSO messages having the same timestamp "
            "may be received in an indeterminate order.",
            153,
            160,
        ),
        TIME + "182-l7-1": (
            "Only time-regulating joined federates may send TSO messages.",
            7,
            9,
        ),
        TIME + "182-l10-2": (
            "A joined federate shall request to become time-regulating by invoking the Enable "
            "Time Regulation service. The RTI shall subsequently make the joined federate "
            "time-regulating by invoking the Time Regulation Enabled service at that joined "
            "federate.",
            7,
            13,
        ),
        TIME + "182-l19-5": (
            "Each time-regulating joined federate shall provide a lookahead when becoming "
            "time-regulating.",
            19,
            21,
        ),
        TIME + "182-l22-6": (
            "Lookahead shall be a logical time interval that establishes the lowest value of "
            "timestamps that can be sent in TSO messages by the joined federate.",
            19,
            25,
        ),
        TIME + "182-l37-11": (
            "A time-regulating joined federate with a lookahead of zero shall be subject to "
            "an additional restriction.",
            37,
            40,
        ),
        TIME + "182-l43-13": (
            "If such a joined federate has advanced its logical time by use of Time Advance "
            "Request or Next Message Request service, it shall not send TSO messages that "
            "contain timestamps less than or equal to its logical time (plus its lookahead, "
            "which is zero), rather than the usual less-than restriction. Subsequent use of "
            "a time advancement service that moves the joined federate's logical time forward "
            "lifts this additional restriction (and imposes the restriction of the subsequent "
            "advancement service).",
            37,
            52,
        ),
        TIME + "182-l73-23": (
            "A time-regulating joined federate that has advanced its logical time via the "
            "Flush Queue Grant service as a result of using the Flush Queue Request service "
            "shall be further restricted from sending a TSO message with a timestamp less "
            "than its optimistic logical time plus the lookahead it would have if granted "
            "to the optimistic logical time. The lookahead the federate would have if "
            "actually granted to the optimistic logical time is referred to as the optimistic "
            "lookahead (OL).",
            70,
            82,
        ),
        TIME + "182-l88-28": (
            "A time-regulating joined federate need not send TSO messages in TSO, but all "
            "TSO messages that it sends shall be received by other joined federates in "
            "timestamped order (if they are received as TSO messages) except when the Flush "
            "Queue Request service is used.",
            85,
            91,
        ),
        TIME + "182-l97-30": (
            "Only time-constrained joined federates can receive messages as TSO messages.",
            97,
            99,
        ),
        TIME + "182-l100-31": (
            "A joined federate shall request to become time-constrained by invoking the "
            "Enable Time Constrained service. The RTI shall subsequently make the joined "
            "federate time-constrained by invoking the Time Constrained Enabled service at "
            "that joined federate.",
            99,
            106,
        ),
        TIME + "182-l112-35": (
            "In order to ensure that a time-constrained joined federate shall never receive "
            "a TSO message with a timestamp less than its logical time, a bound is placed "
            "on each time-constrained joined federate that limits how far it can advance its "
            "logical time. The bound ensures that a time-constrained joined federate cannot "
            "advance its logical time past a point at which TSO messages could still be sent "
            "by another joined federate.",
            112,
            121,
        ),
        TIME + "182-l127-40": (
            "If a time-constrained joined federate requests to advance its logical time beyond "
            "its bound, the time advance shall not be granted until its bound has increased "
            "beyond the logical time to be granted.",
            120,
            127,
        ),
        TIME + "182-l133-42": (
            "This bound on advancement is expressed in terms of a value called the Greatest "
            "Available Logical Time (GALT). Each joined federate shall have a GALT that "
            "expresses the greatest logical time to which the RTI guarantees it can grant "
            "an advance without having to wait for other joined federates to advance.",
            130,
            136,
        ),
        TIME + "193-l31-6": (
            "The joined federate has been notified that it may now receive TSO messages "
            "(the request is no longer pending), and its logical time advances are constrained "
            "so that the joined federate's logical time shall never exceed the GALT computed "
            "by the RTI for the joined federate.",
            25,
            33,
        ),
        TIME + "193-l34-7": (
            "The joined federate's logical time shall be set to the value specified as the "
            "argument to this service.",
            33,
            35,
        ),
        TIME + "193-l58-12": (
            "Invocation of the Disable Time Constrained service shall indicate that the "
            "joined federate is no longer time-constrained.",
            58,
            61,
        ),
        TIME + "193-l61-13": (
            "All enqueued and subsequent TSO messages shall be delivered to the joined "
            "federate as RO messages.",
            60,
            64,
        ),
        TIME + "202-l104-28": (
            "Invocation of the Flush Queue Grant service shall indicate that a prior request "
            "to flush the TSO queue and advance the joined federate's logical time has been "
            "honored.",
            104,
            107,
        ),
        TIME + "202-l107-29": (
            "The logical time argument shall indicate that the logical time of the joined "
            "federate has been advanced to this value. The OLT is the minimum of the time "
            "supplied in the Flush Queue Request and the timestamps of any TSO messages "
            "delivered in response to the Flush Queue Request. It indicates the logical time "
            "that the joined federate would have been granted if the RTI could have guaranteed "
            "that no other TSO messages with a timestamp less than it would be received in the "
            "future. In other words, the RTI's generation of the OLT optimistically assumes "
            "that even though there could be TSO messages in transit or yet to be sent, none "
            "of these TSO messages will have a timestamp less than the OLT.",
            106,
            128,
        ),
        TIME + "203-l95-25": (
            "Invocation of the Time Advance Grant service shall indicate that a prior request "
            "to advance the joined federate's logical time has been honored. The argument "
            "of this service shall indicate that the logical time for the joined federate "
            "has been advanced to this value.",
            92,
            98,
        ),
        TIME + "203-l104-28": (
            "If the grant is issued in response to invocation of a Next Message Request or "
            "Time Advance Request service, the RTI shall guarantee that no additional TSO "
            "messages shall be delivered in the future with timestamps less than or equal "
            "to this value.",
            101,
            107,
        ),
        TIME + "203-l113-31": (
            "If the grant is in response to an invocation of a Time Advance Request "
            "Available, Next Message Request Available, or Flush Queue Request service, "
            "the RTI shall guarantee that no additional TSO messages shall be delivered "
            "in the future with timestamps less than the value of the grant.",
            110,
            116,
        ),
        TIME + "204-l74-21": (
            "If this service is invoked in response to a Time Advance Request or Next Message "
            "Request service, no additional TSO messages shall be delivered with timestamps "
            "less than or equal to the supplied logical time.",
            71,
            77,
        ),
        TIME + "204-l86-25": (
            "If this service is invoked in response to a Time Advance Request Available or "
            "Next Message Request Available service, no additional TSO messages shall be "
            "delivered with timestamps less than the supplied logical time.",
            83,
            89,
        ),
        TIME + "206-l26-3": (
            "The Query GALT service shall request the invoking joined federate's current GALT.",
            26,
            29,
        ),
        TIME + "206-l29-4": (
            "The first returned argument shall indicate whether GALT is defined for the joined "
            "federate.",
            28,
            31,
        ),
        TIME + "206-l32-5": (
            "If the argument indicates that GALT is defined for the joined federate, then "
            "the optional returned argument shall be supplied to indicate the joined "
            "federate's current GALT.",
            29,
            35,
        ),
        TIME + "207-l109-27": (
            "The Query LITS service shall request the invoking joined federate's current LITS.",
            109,
            112,
        ),
        TIME + "207-l112-28": (
            "The first returned argument shall indicate whether LITS is defined for the joined "
            "federate.",
            111,
            114,
        ),
        TIME + "207-l115-29": (
            "If the argument indicates that LITS is defined for the joined federate, then "
            "the optional returned argument shall be supplied to indicate the joined "
            "federate's current LITS.",
            112,
            118,
        ),
        SUPPORT + "259-l144-44": (
            "The Get Dimension Handle service shall return the dimension handle associated "
            "with the supplied dimension name.",
            138,
            147,
        ),
    }
    for requirement_id, (statement, line, end_line) in corrections.items():
        _set_statement(by_id[requirement_id], statement, line, end_line)
    _write_requirements(payload)
