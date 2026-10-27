"""Repair requirement fragments after reviewing their printed source sentences."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_base import SourceRef
from hla_lab.core.semantic_model import (
    RequirementApiBindingFile,
    RequirementFile,
    load_document_model,
)
from hla_lab.core.semantic_text import _machine_statement
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from tools.migrations.complete_15161_m16 import _source_refinement_requirements
from tools.migrations.workspace import document_root

PREFIX = "requirement-candidate-content-clauses-"
MERGED_DISCONNECT_CANDIDATE = PREFIX + "04-federation-management-page-040-l54-15"
MERGED_DISCONNECT_REQUIREMENT = "req-federate-disconnect-after-resign"
TABLE_POINTER_CANDIDATES = {
    PREFIX + "08-time-management-page-181-l115-2": "Table 2",
    PREFIX + "08-time-management-page-181-l118-3": "Table 3",
}


def _semantic_title(statement: str) -> str:
    sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", " ".join(statement.split()))
    lead = next((part for part in sentences if re.search(r"\bshall\b", part, re.I)), sentences[0])
    lead = lead.strip().rstrip(".:;!?")
    return lead or "Source-derived requirement"


REPAIRS: dict[str, tuple[str, int, int]] = {
    "11-management-object-model-page-292-l117-38": (
        "HLAargumentValue argument encoding shall use a JSON-like Unicode format with Character Sequence, Null, Number, Boolean, Binary Data, and String basic element forms.",
        117,
        174,
    ),
    "11-management-object-model-page-356-l326-108": (
        "The Authorizer interface shall provide a method to obtain the authorization service’s string name.",
        326,
        335,
    ),
    "11-management-object-model-page-357-l34-10": (
        "The AuthorizerFactory interface shall provide a method to obtain the authorization service’s string name.",
        32,
        43,
    ),
    "11-management-object-model-page-357-l115-37": (
        "The predefined HLAauthorizer authorization service shall provide implementations of both AuthorizerFactory and Authorizer.",
        115,
        155,
    ),
    "11-management-object-model-page-357-l151-49": (
        "The predefined HLAauthorizer Authorizer implementation shall support authorization of HLAplainTextPassword credentials.",
        143,
        155,
    ),
    "08-time-management-page-180-l72-21": (
        "A message’s order type shall be determined from its preferred order type, timestamp presence, the sender’s and receiver’s time properties, and the corresponding sent message’s order type.",
        71,
        153,
    ),
    "12-programming-language-mappings-page-403-l4-1": (
        "A protocol message header shall contain, in order, packet size, sequence number, session ID, last received message number, message type, and payload.",
        4,
        96,
    ),
    "12-programming-language-mappings-page-426-l220-73": (
        "An update to an instance attribute by its owning joined federate shall be reflected only by joined federates subscribed to the corresponding class attribute from each subscriber’s perspective.",
        217,
        228,
    ),
    "11-management-object-model-page-358-l190-62": (
        "An RTI implementer shall provide a concrete implementation of the RTIambassador interface.",
        188,
        195,
    ),
    "11-management-object-model-page-371-l250-82": (
        "An RTI implementation of each handle set shall enforce the corresponding handle element type and implement all defined set operations.",
        250,
        304,
    ),
    "11-management-object-model-page-377-l228-74": (
        "The C++ API shall be based on C++14.",
        228,
        231,
    ),
    "11-management-object-model-page-378-l48-15": (
        "C++ RTI implementations and federates shall use the standard Annex C headers, identically named dynamic link libraries, and compatible platforms.",
        48,
        78,
    ),
    "12-programming-language-mappings-page-402-l17-5": (
        "The RTI parameters listed in Table 31 shall be configurable in the RID.",
        17,
        20,
    ),
    "12-programming-language-mappings-page-402-l20-6": (
        "The federate parameters listed in Table 32 shall be configurable.",
        20,
        23,
    ),
    "12-programming-language-mappings-page-402-l26-8": (
        "Protocol message headers and payloads shall use the format specified in Table 33.",
        26,
        29,
    ),
    "12-programming-language-mappings-page-415-l13-4": (
        "The files enumerated in normative Annex B shall comprise the HLA Java API and be distributed in IEEE1516-2025_Java_API.zip.",
        13,
        20,
    ),
    "12-programming-language-mappings-page-420-l13-4": (
        "The files enumerated in normative Annex C shall comprise the HLA C++ API and be distributed in the Annex C API ZIP archive.",
        13,
        20,
    ),
    "annexes-page-434-l13-4": (
        "The MIM shall be defined in HLAstandardMIM.xml as supplied with normative Annex G.",
        13,
        18,
    ),
    "10-support-services-page-287-l90-29": (
        "The MOM object classes shall include HLAmanager.HLAfederate and HLAmanager.HLAfederation as defined in §11.2 and Figure 19.",
        90,
        127,
    ),
    "10-support-services-page-288-l24-7": (
        "The RTI shall not subscribe to any MOM object class.",
        24,
        29,
    ),
    "10-support-services-page-288-l96-31": (
        "The MOM interaction classes shall include the HLAadjust, HLArequest, HLAreport, and HLAservice subclass families shown in Figure 20.",
        96,
        102,
    ),
    "11-management-object-model-page-290-l36-11": (
        "The RTI shall receive MOM interactions at the leaf class and process all predefined parameters for that class, subject to the exceptions in the MOM Parameters Definition Table.",
        33,
        46,
    ),
    "11-management-object-model-page-291-l77-25": (
        "An RTI shall never engage in ownership transfer of MOM instance attributes.",
        77,
        85,
    ),
    "11-management-object-model-page-291-l101-33": (
        "Unless Table 20 specifies otherwise, a federate sending a MOM interaction shall supply all predefined parameters available at that interaction class and no more, subject to the exceptions in §11.4.1.",
        101,
        109,
    ),
    "11-management-object-model-page-291-l185-61": (
        "During federate save or restore, a joined federate shall be allowed to send the MOM interactions specified in §11.4.2 when the required publications are in place.",
        182,
        204,
    ),
    "09-data-distribution-management-page-218-l12-1": (
        "The DDM relationships of §9.1.2 shall govern region specifications and region realizations established through DDM services.",
        12,
        17,
    ),
    "09-data-distribution-management-page-219-l113-36": (
        "The DDM relationships of §9.1.2 shall govern object classes, class attributes, object instances, and instance attributes.",
        113,
        118,
    ),
    "09-data-distribution-management-page-220-l122-39": (
        "The DDM relationships of §9.1.2 shall govern interaction classes, parameters, and interactions.",
        122,
        127,
    ),
    "09-data-distribution-management-page-222-l23-6": (
        "A joined federate using DDM services shall interpret Subscribe Object Class Attributes as the corresponding Subscribe Object Class Attributes With Regions service invoked with the default region.",
        23,
        87,
    ),
    "07-ownership-management-page-150-l74-23": (
        "A joined federate shall not stop publishing a class attribute at the known class of an object instance while its corresponding instance attribute remains under an unresolved Attribute Ownership Acquisition request.",
        74,
        98,
    ),
    "07-ownership-management-page-152-l74-23": (
        "The RTI shall provide both Attribute Ownership Acquisition and Attribute Ownership Acquisition If Available as ways for a publishing joined federate to acquire an analogous instance attribute at its known class.",
        74,
        107,
    ),
    "08-time-management-page-216-l48-13": (
        "DDM services shall use the dimensions, ranges, region specifications, and related concepts defined in §9.1.1.",
        48,
        93,
    ),
    "08-time-management-page-216-l153-48": (
        "A collection of attribute-designator-set and region-designator-set pairs shall be interpreted as the union of each pair’s cross product, yielding a set of attribute-designator and region-designator pairs.",
        153,
        182,
    ),
    "08-time-management-page-217-l101-32": (
        "The FDD’s dimension relationships shall govern available dimensions, DDM eligibility, and default ranges as specified in §9.1.2.",
        101,
        145,
    ),
    "04-federation-management-page-058-l112-33": (
        "The Resign Federation Execution service shall indicate the requested cessation of federation participation.",
        112,
        114,
    ),
    "05-declaration-management-page-096-l105-32": (
        "The optional passive subscription indicator shall determine whether each specified class attribute is subscribed actively or passively at the object class.",
        105,
        122,
    ),
    "05-declaration-management-page-101-l104-29": (
        "The optional universal subscription indicator shall determine whether each specified directed interaction class is subscribed by ownership or universally at the object class.",
        104,
        123,
    ),
    "06-object-management-page-112-l84-25": (
        "When a joined federate subscribes at an update rate other than the default, the RTI shall enforce the rate according to the attribute’s transportation type.",
        81,
        108,
    ),
    "09-data-distribution-management-page-233-l120-37": (
        "The optional passive subscription indicator shall apply separately to each subscription triple of object class, class attribute, and region.",
        120,
        149,
    ),
    "09-data-distribution-management-page-237-l43-13": (
        "The optional passive subscription indicator shall apply separately to each subscribed interaction class and region pair.",
        43,
        68,
    ),
    "05-declaration-management-page-081-l44-12": (
        "DM and DDM services, together with object and ownership management and the FDD class hierarchies, shall determine the object classes at which object instances may be registered.",
        38,
        52,
    ),
    "05-declaration-management-page-081-l98-29": (
        "The FDD’s static properties shall establish the vocabulary used by Declaration Management.",
        98,
        101,
    ),
    "05-declaration-management-page-082-l35-10": (
        "The DM definitions and constraints of §5.1.2 shall apply to object classes and class attributes declared in the FDD class hierarchy.",
        35,
        40,
    ),
    "05-declaration-management-page-083-l152-49": (
        "The DM definitions and constraints of §5.1.3 shall apply to interaction classes and parameters declared in the FDD interaction class hierarchy.",
        152,
        157,
    ),
    "05-declaration-management-page-084-l131-42": (
        "The DM definitions and constraints of §5.1.4 shall apply to object classes and class directed interactions declared in the FDD class hierarchy.",
        131,
        136,
    ),
    "08-time-management-page-180-l9-1": (
        "Invoking Update Attribute Values, Send Interaction, Send Interaction with Regions, or Delete Object Instance shall be called sending a message.",
        16,
        32,
    ),
    "08-time-management-page-194-l27-5": (
        "Time Advance Request shall cause delivery of all queued RO messages for the joined federate and all TSO messages with timestamps less than or equal to the specified logical time.",
        27,
        45,
    ),
    "08-time-management-page-197-l29-6": (
        "Next Message Request shall cause delivery of all queued RO messages for the joined federate and the earliest TSO message with a timestamp no greater than the specified logical time, together with all TSO messages at that same timestamp.",
        29,
        49,
    ),
    "08-time-management-page-199-l16-4": (
        "Next Message Request Available shall cause delivery of all queued RO messages for the joined federate and the earliest queued TSO message with a timestamp no greater than the specified logical time, together with other queued TSO messages at that same timestamp.",
        16,
        39,
    ),
    "04-federation-management-page-062-l11-1": (
        "If synchronization point registration fails, the failure reason argument shall identify why. Possible reasons include a label already in use or a synchronization set member that is not a joined federate.",
        11,
        27,
    ),
    "04-federation-management-page-069-l76-19": (
        "If federation save fails, the optional failure reason argument shall identify why. Possible reasons include RTI inability to save, a federate reporting save failure, a federate resigning, RTI detection of federate failure, an unhonorable optional timestamp, or an aborted save.",
        76,
        132,
    ),
    "04-federation-management-page-077-l11-1": (
        "If federation restore fails, the optional failure reason argument shall identify why. Possible reasons include RTI inability to restore, a federate reporting restore failure, a federate resigning, RTI detection of federate failure, or an aborted restore.",
        11,
        61,
    ),
    "12-programming-language-mappings-page-399-l74-24": (
        "The RTI and federate shall maintain message history buffers from which lost messages can be resent after a connection fault. Potentially recoverable faults include a broken socket or an exceeded FED_TIMEOUT_HEART or RTI_TIMEOUT_HEART.",
        72,
        92,
    ),
    "12-programming-language-mappings-page-401-l70-23": (
        "The RTI shall determine whether all lost messages can be resent by checking both that federate messages missing at the RTI remain in the federate history buffer (LRF is not older than OAF) and that RTI messages missing at the federate remain in the RTI history buffer (LRR is not older than OAR).",
        70,
        91,
    ),
    "12-programming-language-mappings-page-429-l136-45": (
        "The RTI shall advance the joined federate’s logical time to the smallest of the specified logical time, the joined federate’s GALT, and the smallest timestamp of all TSO messages the RTI delivered in response to the Flush Queue Request invocation.",
        136,
        165,
    ),
    "04-federation-management-page-072-l26-4": (
        "A joined federate save status shall be one of: No federate save in progress, Federate instructed to save, Federate saving, or Federate waiting for federation to save.",
        26,
        55,
    ),
    "04-federation-management-page-079-l116-29": (
        "A restore status descriptor shall include a pre-restore joined federate designator, a post-restore joined federate designator, and a restore status.",
        116,
        136,
    ),
    "04-federation-management-page-079-l158-43": (
        "A joined federate restore status shall be one of: No federate restore in progress, Federate restore request pending, Federate waiting for restore to begin, Federate prepared to restore, Federate restoring, or Federate waiting for federation to restore.",
        158,
        166,
    ),
    "04-federation-management-page-047-l17-4": (
        "The FDD retained and combined by the RTI from FOM modules shall include a complete object class structure table.",
        17,
        28,
    ),
    "04-federation-management-page-048-l57-18": (
        "The RTI shall reject a FOM module by exception when it conflicts with the current FOM or is noncompliant.",
        57,
        127,
    ),
    "04-federation-management-page-049-l19-4": (
        "The RTI shall provide access to the current FDD, the content of individual FOM modules, and the MIM.",
        19,
        23,
    ),
    "06-object-management-page-111-l25-6": (
        "The RTI shall always support HLAreliable as the default reliable transportation type.",
        25,
        33,
    ),
    "08-time-management-page-188-l69-21": (
        "The RTI shall support only TSO and RO order types.",
        69,
        83,
    ),
    "11-management-object-model-page-392-l232-75": (
        "The RTI shall provide the RTI_RELIABLE transportation type enumeration.",
        232,
        237,
    ),
    "12-programming-language-mappings-page-412-l51-16": (
        "When using TLS 1.3, the RTI and federate shall support a mode without certificate validation for encryption only.",
        48,
        59,
    ),
    "01-overview-page-018-l58-7": (
        "Federation execution names shall be case-sensitive.",
        58,
        63,
    ),
    "12-programming-language-mappings-page-411-l20-6": (
        "TCP/IP shall be supported as a transport protocol.",
        20,
        25,
    ),
    "01-overview-page-018-l4-1": (
        "At any point during a federation execution, at most one federate or the RTI shall have the privilege to update the value of a given object instance attribute.",
        4,
        7,
    ),
    "01-overview-page-018-l18-2": (
        "Each object instance shall have a designator.",
        18,
        19,
    ),
    "04-federation-management-page-038-l21-4": (
        "Before interacting with an RTI to create or join a federation execution, an unjoined federate shall perform Connect.",
        21,
        24,
    ),
    "04-federation-management-page-038-l27-5": (
        "In the IMMEDIATE callback model, the RTI shall invoke callbacks when they are available unless callbacks have been disabled through Disable Callbacks.",
        27,
        36,
    ),
    "04-federation-management-page-044-l54-17": (
        "Once a restore has begun, messages not yet delivered to intended joined federates in the restoring federation execution shall be lost.",
        48,
        55,
    ),
    "05-declaration-management-page-081-l104-31": (
        "Every class shall have at most one immediate superclass.",
        104,
        106,
    ),
    "06-object-management-page-110-l10-2": (
        "This switch setting shall be modifiable during a federation execution via the HLAmanager.HLAfederation.HLAadjust.HLAsetSwitches MOM interaction.",
        10,
        15,
    ),
    "09-data-distribution-management-page-221-l71-22": (
        "Two ranges in the same dimension A = [a_lower, a_upper) and B = [b_lower, b_upper) shall overlap if and only if either a_lower = b_lower, or (a_lower < b_upper and b_lower < a_upper), or the Allow Relaxed DDM switch is enabled and the RTI implementation determines that the ranges are sufficiently close to warrant an expanded interpretation of one or both ranges; neither range may ever be reduced.",
        71,
        85,
    ),
    "11-management-object-model-page-376-l256-84": (
        "An RTI implementation shall provide implementations of the standardized time types as classes implementing HLAinteger64Time, HLAinteger64Interval, HLAinteger64TimeFactory, HLAfloat64Time, HLAfloat64Interval, and HLAfloat64TimeFactory.",
        256,
        300,
    ),
    "12-programming-language-mappings-page-408-l47-15": (
        "For every CTRL_NEW_SESSION message received by the RTI, it shall send a corresponding CTRL_NEW_SESSION_STATUS message.",
        47,
        52,
    ),
    "12-programming-language-mappings-page-408-l56-18": (
        "For every CTRL_HEARTBEAT message received by the RTI, it shall send a corresponding CTRL_HEARTBEAT_RESPONSE message.",
        56,
        61,
    ),
    "12-programming-language-mappings-page-408-l122-40": (
        "For every HLA_CALL_REQUEST message received by the RTI, it shall send a corresponding HLA_CALL_RESPONSE that includes the sequence number of the HLA_CALL_REQUEST.",
        122,
        130,
    ),
    "12-programming-language-mappings-page-408-l143-47": (
        "For every HLA_CALLBACK_REQUEST message received by the federate, it shall send a corresponding HLA Callback Response that includes the sequence number of the HLA_CALLBACK_REQUEST.",
        143,
        151,
    ),
    "11-management-object-model-page-357-l130-42": (
        "The predefined HLAauthorizer AuthorizerFactory implementation shall create instances of the HLAauthorizer Authorizer implementation.",
        121,
        138,
    ),
    "11-management-object-model-page-358-l214-70": (
        "FederateAmbassador shall be implemented by the federate developer.",
        205,
        219,
    ),
    "11-management-object-model-page-358-l232-76": (
        "Java API classes such as RTIexception and ResignAction shall be included in each RTI implementation.",
        220,
        237,
    ),
    "11-management-object-model-page-359-l87-28": (
        "The HLA service shall include the specified Java API classes and interfaces.",
        87,
        90,
    ),
    "11-management-object-model-page-359-l363-120": (
        "The HLAauthorizer authorization service factories shall be listed in a provider configuration file.",
        351,
        374,
    ),
    "11-management-object-model-page-371-l289-95": (
        "Attempts to add an instance of an inappropriate type to a handle set shall elicit IllegalArgumentException.",
        253,
        297,
    ),
    "12-programming-language-mappings-page-396-l117-38": (
        "FOM module arguments over the federate protocol shall use a URL, the full module content, or a ZIP-compressed module.",
        108,
        140,
    ),
    "12-programming-language-mappings-page-396-l147-48": (
        "Time Representation arguments shall use the HLA time type name, such as HLAinteger64Time.",
        143,
        152,
    ),
    "12-programming-language-mappings-page-396-l159-52": (
        "Handle arguments other than Conveyed Regions shall contain the opaque encoded bytes resulting from the handle’s encode operation.",
        156,
        170,
    ),
    "12-programming-language-mappings-page-397-l12-3": (
        "Logical time, timestamps, and lookahead shall be encoded according to the format defined for the time type.",
        9,
        17,
    ),
    "12-programming-language-mappings-page-411-l50-16": (
        "The RID shall support alternative configuration of the RTI address and port.",
        38,
        52,
    ),
    "12-programming-language-mappings-page-426-l235-78": (
        "In the Annex E object instance example, an update to e1(x) by federate G shall be reflected by federate H because H subscribes to x at e1’s known class C.",
        229,
        256,
    ),
    "12-programming-language-mappings-page-426-l265-88": (
        "In the Annex E object instance example, updates to e1(y) or e1(u) by federate G shall not be reflected by federate H because H does not subscribe to y or u at e1’s known class C.",
        256,
        282,
    ),
    "11-management-object-model-page-358-l25-7": (
        "The RTI shall support concurrent joined federate-initiated service invocations to different RTIambassador instances.",
        25,
        30,
    ),
    "11-management-object-model-page-358-l181-59": (
        "The Java API shall be based on Java 11.",
        181,
        184,
    ),
    "11-management-object-model-page-360-l35-10": (
        "The RTI implementation’s provider configuration file shall be named hla.rti1516_2025.RtiFactory and contain the name of the class implementing RtiFactory.",
        23,
        51,
    ),
    "11-management-object-model-page-361-l140-44": (
        "The getName() methods of Authorizer and AuthorizerFactory implementations for the predefined service shall return the symbolic name HLAauthorizer.",
        125,
        143,
    ),
    "11-management-object-model-page-361-l212-68": (
        "To obtain an AuthorizerFactory implementation, the RTI shall use AuthorizerFactoryFactory with the symbolic name HLAauthorizer.",
        191,
        230,
    ),
    "11-management-object-model-page-372-l120-38": (
        "When a federate invokes connect(), it shall supply a CallbackModel enumeration value as an argument.",
        114,
        128,
    ),
    "11-management-object-model-page-379-l44-13": (
        "AuthorizerFactoryFactory shall forward requests for other authorizer types, including the standardized type, to HLAauthorizerFactoryFactory.",
        38,
        53,
    ),
    "11-management-object-model-page-379-l197-64": (
        "C++ handle interfaces shall implement hash() returning a long suitable as a handle hash-table value.",
        197,
        215,
    ),
    "11-management-object-model-page-381-l16-5": (
        "HLAvariantRecord shall support addMapping for associating encoders and decoders with discriminants, and setDiscriminant and getDiscriminant for selecting the variant.",
        16,
        22,
    ),
    "11-management-object-model-page-381-l22-7": (
        "The variant selected through HLAvariantRecord discriminant methods shall be used for composing, encoding, and decoding data elements.",
        16,
        24,
    ),
    "11-management-object-model-page-388-l4-1": (
        "The C++ Exception base class shall have an abstract name method whose derived implementation returns the unqualified derived exception type name.",
        4,
        9,
    ),
    "11-management-object-model-page-390-l282-92": (
        "When a federate invokes connect(), it shall supply a CallbackModel enumeration value as an argument.",
        276,
        290,
    ),
    "12-programming-language-mappings-page-394-l112-36": (
        "A C++ library implementing the logical time classes shall export a static method that allows an RTI implementation to create a LogicalTimeFactory instance.",
        112,
        159,
    ),
    "12-programming-language-mappings-page-396-l186-61": (
        "A handle received as a value in an attribute or parameter handle value map shall consist only of the opaque encoded bytes described in §12.13.3.3(c).",
        183,
        188,
    ),
    "12-programming-language-mappings-page-396-l198-65": (
        "Names, labels, and strings described in Clauses 4 through 10 shall be mapped to native strings using the encoding in Annex D.",
        192,
        200,
    ),
    "12-programming-language-mappings-page-397-l42-13": (
        "A Map shall not contain duplicate keys.",
        39,
        44,
    ),
    "12-programming-language-mappings-page-397-l45-14": (
        "Each Map key shall map to at most one value.",
        42,
        46,
    ),
    "12-programming-language-mappings-page-399-l23-7": (
        "If a federate has no messages to send for a period, it shall regularly send Heartbeat messages to maintain the connection.",
        20,
        28,
    ),
    "12-programming-language-mappings-page-400-l10-3": (
        "Control messages shall be ignored during recovery after a connection fault.",
        7,
        12,
    ),
    "12-programming-language-mappings-page-400-l13-4": (
        "Only HLA service messages shall be resent during recovery after a connection fault.",
        10,
        15,
    ),
    "12-programming-language-mappings-page-401-l58-19": (
        "Upon receiving a Resume Request, the RTI shall determine the sequence numbers of its Last Received Federate message and Oldest Available RTI message in its history buffer.",
        58,
        66,
    ),
    "12-programming-language-mappings-page-403-l22-7": (
        "Each protocol message shall have a sequence number provided by its sending component.",
        19,
        27,
    ),
    "12-programming-language-mappings-page-403-l52-17": (
        "The same Session ID shall be used for every message in a session.",
        49,
        55,
    ),
    "12-programming-language-mappings-page-412-l66-21": (
        "For server certificate validation, a server certificate and its corresponding private key shall be installed at the RTI.",
        63,
        68,
    ),
    "06-object-management-page-115-l104-28": (
        "Names in the supplied object instance name set shall not begin with the reserved prefix ‘HLA’.",
        104,
        107,
    ),
    "10-support-services-page-269-l167-52": (
        "The Set Attribute Relevance Advisory Switch value argument shall be Boolean.",
        164,
        170,
    ),
    "10-support-services-page-271-l67-19": (
        "The Set Attribute Scope Advisory Switch value argument shall be Boolean.",
        64,
        71,
    ),
    "10-support-services-page-272-l146-45": (
        "The Set Interaction Relevance Advisory Switch value argument shall be Boolean.",
        143,
        150,
    ),
    "10-support-services-page-274-l58-16": (
        "The Set Convey Region Designator Sets Switch value argument shall be Boolean.",
        55,
        62,
    ),
    "10-support-services-page-277-l31-7": (
        "The Set Service Reporting Switch value argument shall be Boolean.",
        28,
        35,
    ),
    "10-support-services-page-277-l37-9": (
        "If a joined federate is subscribed to HLAmanager.HLAfederate.HLAreport.HLAreportServiceInvocation, it shall not be able to enable its Service Reporting Switch.",
        34,
        39,
    ),
    "10-support-services-page-278-l113-34": (
        "The Set Exception Reporting Switch value argument shall be Boolean.",
        110,
        117,
    ),
    "10-support-services-page-285-l14-1": (
        "The Evoke Multiple Callbacks pending callback indicator argument shall have a Boolean value.",
        14,
        20,
    ),
    "10-support-services-page-287-l60-19": (
        "The RTI shall publish MOM object classes.",
        57,
        63,
    ),
    "10-support-services-page-287-l63-20": (
        "The RTI shall subscribe to and receive MOM interaction classes designated for RTI receipt.",
        60,
        67,
    ),
    "10-support-services-page-288-l66-21": (
        "A joined federate extending a MOM object class with new attributes shall update them on the same MOM object instance registered by the RTI.",
        57,
        72,
    ),
    "10-support-services-page-288-l69-22": (
        "The RTI shall never acquire ownership of new class attributes added to a MOM object class.",
        69,
        74,
    ),
    "11-management-object-model-page-293-l131-43": (
        "After its initial records, the service report file shall contain a record for each service report interaction generated while the Service Reporting and Send Service Reports to File switches were enabled.",
        131,
        136,
    ),
    "11-management-object-model-page-305-l11-3": (
        "The MOM table information in §11.6 shall appear in all compliant FOMs.",
        8,
        14,
    ),
    "11-management-object-model-page-305-l14-4": (
        "The MOM table information in §11.6 shall not be altered in a compliant FOM.",
        11,
        17,
    ),
    "08-time-management-page-216-l135-42": (
        "The default region realization shall not have a region specification.",
        135,
        138,
    ),
    "09-data-distribution-management-page-222-l89-28": (
        "Because joined federates cannot refer to the default region, a DDM service shall not be substitutable for its corresponding DM service through that region.",
        89,
        94,
    ),
    "09-data-distribution-management-page-222-l98-31": (
        "DM and corresponding DDM service invocations by a joined federate using the same object class and attribute or interaction class designators shall not interact in their subscription effects.",
        92,
        100,
    ),
    "09-data-distribution-management-page-223-l103-34": (
        "If a class attribute is subscribed at an object class, the joined federate shall subscribe to it either actively or passively, but not both.",
        103,
        109,
    ),
    "09-data-distribution-management-page-223-l118-39": (
        "From a joined federate’s perspective, an object class shall be subscribed if and only if it subscribes to at least one class attribute, with or without a region.",
        118,
        132,
    ),
    "09-data-distribution-management-page-224-l23-7": (
        "From a joined federate’s perspective, an interaction class shall be subscribed if and only if it has an active Subscribe Interaction Class invocation not later undone by Unsubscribe Interaction Class, or at least one active region subscription not later undone by Unsubscribe Interaction Class With Regions.",
        23,
        52,
    ),
    "09-data-distribution-management-page-224-l56-18": (
        "If an interaction class is subscribed, the joined federate shall subscribe to that interaction class either actively or passively, but not both.",
        56,
        61,
    ),
    "09-data-distribution-management-page-232-l19-3": (
        "If specified regions are associated with the specified instance attributes, they shall be unassociated by Unassociate Regions For Updates.",
        16,
        22,
    ),
    "09-data-distribution-management-page-232-l22-4": (
        "Specified regions not associated with the specified instance attributes shall be ignored by Unassociate Regions For Updates.",
        19,
        24,
    ),
    "09-data-distribution-management-page-233-l90-27": (
        "If Subscribe Object Class Attributes With Regions specifies a passive subscription, it shall not cause Start Registration For Object Class or Turn Updates On For Object Instance at another joined federate.",
        81,
        96,
    ),
    "09-data-distribution-management-page-235-l100-28": (
        "Unsubscribe Object Class Attributes With Regions shall require the RTI to remove the specified region from the specified class attribute’s subscription region set at the specified object class.",
        100,
        109,
    ),
    "09-data-distribution-management-page-235-l109-31": (
        "Unsubscribe Object Class Attributes With Regions shall confine the unsubscribe to subscriptions for the specified class attributes using the specified region.",
        109,
        114,
    ),
    "09-data-distribution-management-page-236-l143-42": (
        "Subscribe Interaction Class With Regions shall specify the interaction class whose interactions will be delivered to the joined federate, subject to the region.",
        143,
        149,
    ),
    "09-data-distribution-management-page-238-l181-54": (
        "Unsubscribe Interaction Class With Regions shall require the RTI to remove the specified region from the specified interaction class’s subscription region set.",
        181,
        187,
    ),
    "09-data-distribution-management-page-238-l187-56": (
        "If specified regions are absent from an interaction class’s subscription set, Unsubscribe Interaction Class With Regions shall make no changes to that set.",
        187,
        195,
    ),
    "09-data-distribution-management-page-240-l9-1": (
        "If a potential recipient is unsubscribed to the interaction class or its subscription region set does not overlap the sending region set, the RTI shall not invoke Receive Interaction there.",
        9,
        11,
    ),
    "09-data-distribution-management-page-241-l100-30": (
        "Provide Attribute Value Update invocations resulting from Request Attribute Value Update With Regions shall be consistent with the supplied region sets, requiring overlap with the updating federate’s update region set.",
        97,
        108,
    ),
    "07-ownership-management-page-152-l86-27": (
        "Attribute Ownership Acquisition shall inform the RTI that the joined federate seeks ownership of the designated instance attribute.",
        86,
        92,
    ),
    "07-ownership-management-page-152-l101-32": (
        "Attribute Ownership Acquisition If Available shall inform the RTI that the federate seeks the designated instance attribute only if it is unowned or its owner is divesting it.",
        98,
        106,
    ),
    "07-ownership-management-page-154-l42-13": (
        "The tag supplied to Unconditional Attribute Ownership Divestiture shall be present in resulting Request Attribute Ownership Assumption invocations.",
        39,
        44,
    ),
    "07-ownership-management-page-154-l51-16": (
        "The tag supplied to Attribute Ownership Acquisition If Available shall be present in resulting Request Divestiture Confirmation invocations.",
        48,
        53,
    ),
    "07-ownership-management-page-156-l8-1": (
        "The invoking joined federate shall continue its update responsibility for instance attributes specified in Negotiated Attribute Ownership Divestiture until it divests their ownership.",
        8,
        12,
    ),
    "07-ownership-management-page-168-l35-7": (
        "The return argument of Attribute Ownership Divestiture If Wanted shall identify the instance attributes whose ownership was actually divested.",
        35,
        40,
    ),
    "07-ownership-management-page-168-l38-8": (
        "For supplied instance attributes absent from the return argument, Attribute Ownership Divestiture If Wanted shall conclude the attempted divestiture without transferring them.",
        35,
        43,
    ),
    "07-ownership-management-page-173-l73-20": (
        "If Remove Object Instance is invoked for the queried instance attributes’ owner, the RTI shall nullify pending Inform Attribute Ownership calls for those attributes.",
        67,
        78,
    ),
    "07-ownership-management-page-173-l76-21": (
        "If Remove Object Instance is invoked for the queried instance attributes’ owner, pending Inform Attribute Ownership calls for those attributes shall not be invoked on the federate.",
        67,
        80,
    ),
    "07-ownership-management-page-177-l50-15": (
        "Each joined federate shall be assigned a logical time when it joins a federation execution.",
        50,
        54,
    ),
    "07-ownership-management-page-177-l62-19": (
        "To advance its time position, a joined federate shall explicitly request an advance.",
        59,
        65,
    ),
    "08-time-management-page-178-l27-6": (
        "Each time advance service shall take a requested logical time as an argument.",
        27,
        33,
    ),
    "08-time-management-page-183-l4-1": (
        "For Time Advance Request and Next Message Request, the joined federate shall be granted only to logical times less than its GALT.",
        4,
        9,
    ),
    "08-time-management-page-184-l91-26": (
        "When a time-regulating joined federate sends a TSO message in the Time Advancing state, its timestamp shall be constrained by its requested logical time plus lookahead rather than its current logical time plus lookahead.",
        88,
        101,
    ),
    "08-time-management-page-188-l75-23": (
        "The legal name of timestamp order (TSO) shall be ‘TimeStamp’.",
        69,
        78,
    ),
    "08-time-management-page-188-l81-25": (
        "The legal name of receive order (RO) shall be ‘Receive’.",
        69,
        84,
    ),
    "08-time-management-page-195-l119-34": (
        "For Time Advance Request Available to logical time T, the RTI shall not guarantee delivery of all messages timestamped T when Time Advance Grant to T is issued.",
        110,
        124,
    ),
    "08-time-management-page-196-l9-1": (
        "Time Advance Grant shall complete the Time Advance Request Available request and indicate advancement to the specified logical time.",
        9,
        14,
    ),
    "08-time-management-page-196-l12-2": (
        "After a Time Advance Grant, no additional TSO messages timestamped earlier than the grant’s logical time shall be delivered to that joined federate.",
        9,
        17,
    ),
    "08-time-management-page-203-l92-24": (
        "Time Advance Grant shall indicate that an earlier request to advance the joined federate’s logical time has been honored.",
        92,
        97,
    ),
    "08-time-management-page-208-l75-18": (
        "If requested lookahead is at least the joined federate’s actual lookahead, the change shall take effect immediately.",
        72,
        79,
    ),
    "08-time-management-page-208-l162-43": (
        "If requested lookahead is at least actual lookahead, the joined federate’s actual lookahead shall be set to the requested value.",
        159,
        164,
    ),
    "06-object-management-page-113-l21-3": (
        "At most one object instance at a time shall exist with a particular name.",
        15,
        24,
    ),
    "06-object-management-page-113-l24-4": (
        "The supplied object instance name argument shall not begin with ‘HLA’.",
        21,
        26,
    ),
    "06-object-management-page-118-l22-3": (
        "The RTI shall create an object instance handle unique across the federation execution.",
        22,
        25,
    ),
    "06-object-management-page-118-l43-10": (
        "The phrase ‘the same handle’ shall denote handle equality rather than handle identity.",
        40,
        45,
    ),
    "06-object-management-page-119-l97-27": (
        "The object instance handle supplied by Discover Object Instance shall be unique within the federation execution.",
        94,
        100,
    ),
    "06-object-management-page-119-l100-28": (
        "The object instance handle supplied by Discover Object Instance shall be uniform throughout the federation execution.",
        97,
        102,
    ),
    "06-object-management-page-121-l36-10": (
        "If a potential reflecting federate is subscribed to the instance attribute’s class attribute or has an overlapping subscription region set at the wall-clock time of update, the RTI shall invoke Reflect Attribute Values for that instance attribute there, subject to its preconditions and time management rules.",
        9,
        47,
    ),
    "06-object-management-page-121-l150-45": (
        "If an update and a time-stamped Delete Object Instance invocation apply to the same object instance, the update’s timestamp shall be less than or equal to the deletion timestamp.",
        141,
        152,
    ),
    "06-object-management-page-125-l127-38": (
        "The producing joined federate argument shall contain the designator of the federate that sent the interaction.",
        127,
        129,
    ),
    "06-object-management-page-126-l179-50": (
        "If a directed interaction’s preferred order type is TSO, the invoking joined federate is time-regulating, and a timestamp is supplied, Send Directed Interaction shall return a federation-unique message retraction designator.",
        176,
        181,
    ),
    "06-object-management-page-129-l132-37": (
        "Once a deleted object instance is removed from the federation execution, its object instance designator shall not be reused.",
        129,
        135,
    ),
    "06-object-management-page-129-l135-38": (
        "Once a deleted object instance is removed, joined federates that owned its attributes shall no longer own those attributes.",
        129,
        137,
    ),
    "06-object-management-page-130-l137-40": (
        "If Delete Object Instance uses RO sent message order, the object instance shall no longer be discovered at any other joined federate.",
        119,
        142,
    ),
    "06-object-management-page-130-l167-50": (
        "If Delete Object Instance uses TSO sent message order, the object instance shall cease to be known at the invoking joined federate when its time position reaches the deletion timestamp.",
        146,
        171,
    ),
    "06-object-management-page-132-l140-38": (
        "Local Delete Object Instance shall inform the RTI to treat the specified object instance as though it had never notified the invoking federate of its discovery.",
        140,
        146,
    ),
    "06-object-management-page-132-l146-40": (
        "A locally deleted object instance shall not be removed from the federation execution.",
        143,
        149,
    ),
    "04-federation-management-page-049-l118-37": (
        "The FOM module designator for HLAstandardMIM when the RTI supplies it automatically shall be ‘HLAstandardMIM’.",
        115,
        120,
    ),
    "04-federation-management-page-049-l133-42": (
        "When a federation execution is created, a logical time implementation shall be identified.",
        130,
        135,
    ),
    "04-federation-management-page-053-l50-8": (
        "The RTI shall load the supplied MIM when specified, or otherwise automatically load the standard MIM.",
        50,
        50,
    ),
    "04-federation-management-page-058-l147-40": (
        "If resignation directive 1, 4, or 5 leaves an instance attribute unowned and no joined federate is Acquiring or Willing to Acquire it, the RTI shall try to identify another joined federate willing to own it.",
        147,
        147,
    ),
    "04-federation-management-page-059-l8-1": (
        "As long as an instance attribute remains unowned following resignation, the RTI shall try to identify joined federates willing to own it.",
        8,
        8,
    ),
    "04-federation-management-page-060-l139-34": (
        "Register Federation Synchronization Point shall initiate registration of an upcoming synchronization point label.",
        139,
        139,
    ),
    "04-federation-management-page-061-l11-1": (
        "If the registering federate designates a subset of joined federates, only federation members named in that set shall be informed of the synchronization point label.",
        11,
        11,
    ),
    "04-federation-management-page-062-l140-35": (
        "Announce Synchronization Point shall inform a joined federate of the existence of a new synchronization point label.",
        140,
        140,
    ),
    "04-federation-management-page-063-l12-1": (
        "If no federate designator set was supplied when the synchronization point label was registered, the RTI shall announce that label to federates joining before it has established that all informed federates invoked Synchronization Point Achieved.",
        12,
        12,
    ),
    "05-declaration-management-page-085-l44-14": (
        "If Receive Directed Interaction is invoked at a joined federate, the received directed interaction shall have a received class at that joined federate.",
        41,
        47,
    ),
    "05-declaration-management-page-092-l124-39": (
        "If the joined federate no longer publishes any class attributes of the specified class, it shall not be able to register object instances of that object class.",
        121,
        127,
    ),
    "05-declaration-management-page-096-l57-16": (
        "Subscribe Object Class Attributes shall specify an object class at which the RTI will notify the joined federate of object instance discovery.",
        57,
        62,
    ),
    "05-declaration-management-page-096-l144-45": (
        "If the optional passive subscription indicator denotes a passive subscription, the invocation shall not cause Start Registration For Object Class to be invoked at another joined federate.",
        138,
        150,
    ),
    "05-declaration-management-page-097-l191-54": (
        "If Unsubscribe Object Class Attributes is used to unsubscribe a whole class, the RTI shall stop notifying the joined federate of object instance discovery at that class.",
        188,
        193,
    ),
    "05-declaration-management-page-098-l146-43": (
        "If no class attributes of the specified class remain subscribed by the joined federate, it shall receive no subsequent Discover Object Instance invocations for that class.",
        143,
        151,
    ),
    "05-declaration-management-page-099-l105-30": (
        "If the optional passive subscription indicator denotes a passive subscription, the invocation shall not cause Turn Interactions On to be invoked at another joined federate.",
        99,
        111,
    ),
    "05-declaration-management-page-082-l5-1": (
        "For a service taking an object instance and attribute designators, an attribute shall be available in that object instance’s known class at the invoking or invoked joined federate before it may be used in the designator set; availability alone does not guarantee it can be used.",
        5,
        10,
    ),
    "05-declaration-management-page-082-l59-18": (
        "From a joined federate’s perspective, the subscribed attributes of an object class shall be the class attributes it subscribed to through Subscribe Object Class Attributes and has not subsequently unsubscribed from individually or by unsubscribing the object class.",
        59,
        70,
    ),
    "05-declaration-management-page-082-l119-38": (
        "HLAprivilegeToDeleteObject shall be implicitly published for a joined federate and object class if and only if it has not been explicitly published since the object class’s most recent publication, has not been explicitly unpublished since that publication, and at least one class attribute is explicitly published by that joined federate.",
        119,
        154,
    ),
    "05-declaration-management-page-083-l17-5": (
        "If Discover Object Instance is invoked at a joined federate, the discovered object instance shall have a discovered class at that joined federate.",
        14,
        19,
    ),
    "05-declaration-management-page-083-l29-9": (
        "An object instance shall have at most one discovered class in each joined federate.",
        29,
        32,
    ),
    "05-declaration-management-page-083-l68-22": (
        "If a joined federate has registered or discovered an object instance and has not subsequently locally deleted it, deleted it, or received a Remove Object Instance invocation for it, that object instance shall be known to the joined federate and have a known class there.",
        47,
        73,
    ),
    "05-declaration-management-page-084-l44-14": (
        "If Receive Interaction is invoked at a joined federate, the received interaction shall have a received class at that joined federate.",
        41,
        46,
    ),
    "05-declaration-management-page-084-l161-52": (
        "From a joined federate’s perspective, the subscribed directed interaction classes of an object class shall be those subscribed through Subscribe Object Class Directed Interactions and not subsequently unsubscribed individually or by unsubscribing the whole object class.",
        158,
        169,
    ),
    "05-declaration-management-page-084-l185-60": (
        "From a joined federate’s perspective, the published directed interaction classes of an object class shall be those published through Publish Object Class Directed Interactions and not subsequently unpublished individually or by unpublishing the whole object class.",
        182,
        193,
    ),
    "06-object-management-page-107-l39-9": (
        "If a joined federate subscribes to an object instance’s registered class, the candidate discovery class of that object instance at the joined federate shall be its registered class.",
        36,
        44,
    ),
    "06-object-management-page-107-l51-13": (
        "Discover Object Instance shall be invoked at joined federate F for object instance O when O is not known at F and an instance attribute of O is owned by another federate or the RTI, and its corresponding class attribute is subscribed at O’s candidate discovery class, either directly or with overlapping update and subscription region sets.",
        51,
        99,
    ),
    "06-object-management-page-107-l141-42": (
        "An instance attribute of an object instance shall be in scope for joined federate F when the object instance is known to F, the attribute is owned by another joined federate or the RTI, and its corresponding class attribute is subscribed at the known class, either directly or with overlapping update and subscription region sets.",
        141,
        164,
    ),
    "07-ownership-management-page-159-l20-3": (
        "Once the joined federate confirms its intent to divest the specified instance attributes, ownership of those attributes shall be divested.",
        17,
        25,
    ),
    "07-ownership-management-page-159-l50-10": (
        "After a Confirm Divestiture invocation, the joined federate shall not own any of the specified instance attributes.",
        47,
        55,
    ),
    "07-ownership-management-page-159-l53-11": (
        "After a Confirm Divestiture invocation, the RTI shall give ownership of the specified instance attributes to another joined federate.",
        47,
        56,
    ),
    "08-time-management-page-201-l28-8": (
        "After a Flush Queue Grant invocation, the joined federate shall guarantee that it will not generate a TSO message timestamped earlier than the optimistic logical time of the grant plus the lookahead it would have if granted to that time.",
        28,
        35,
    ),
    "08-time-management-page-201-l40-12": (
        "A Flush Queue Grant invocation shall complete the Flush Queue Request and indicate that the joined federate has advanced to the grant’s logical time.",
        40,
        45,
    ),
    "08-time-management-page-201-l43-13": (
        "After a Flush Queue Grant, no additional TSO messages with timestamps earlier than the grant’s logical time shall be delivered to that joined federate.",
        40,
        48,
    ),
    "09-data-distribution-management-page-221-l26-8": (
        "The default region shall be used for subscription of an interaction class if and only if that class has available dimensions, no other region realization is used for its subscription, and the joined federate is subscribed to it.",
        26,
        35,
    ),
    "09-data-distribution-management-page-221-l35-11": (
        "Invoking Unsubscribe Interaction Class for that interaction class shall cause the default region to cease being used for its subscription.",
        32,
        40,
    ),
    "09-data-distribution-management-page-221-l89-28": (
        "The effects of DDM services shall be independent of the time axis and HLA time management services.",
        89,
        94,
    ),
    "10-support-services-page-244-l17-5": (
        "When an advisory switch is disabled, the RTI shall discard the relevant notifications instead of saving them for delivery when that switch is subsequently enabled.",
        14,
        22,
    ),
    "10-support-services-page-244-l158-51": (
        "Normalized handle values shall have no guarantee of uniqueness.",
        158,
        160,
    ),
    "10-support-services-page-244-l161-52": (
        "The normalized values of two equal handle instances shall also be equal.",
        158,
        163,
    ),
    "10-support-services-page-284-l71-20": (
        "If no callback is pending, an Evoke Callback invocation shall wait for the duration indicated by its supplied argument.",
        62,
        73,
    ),
    "10-support-services-page-284-l77-22": (
        "The pending callback indicator argument shall have a Boolean value.",
        77,
        83,
    ),
    "10-support-services-page-284-l80-23": (
        "A FALSE pending callback indicator shall indicate that no callbacks are pending.",
        77,
        83,
    ),
    "11-management-object-model-page-292-l18-5": (
        "The HLAreportServiceInvocation interaction shall be sent to subscribed federates if the Send Service Reports to File Switch is disabled for the joined federate.",
        18,
        23,
    ),
    "11-management-object-model-page-292-l21-6": (
        "If the Send Service Reports to File Switch is enabled for the joined federate, the HLAreportServiceInvocation interaction shall be recorded in a service report log file.",
        18,
        25,
    ),
    "11-management-object-model-page-292-l57-18": (
        "If a joined federate is subscribed to HLAmanager.HLAfederate.HLAreport.HLAreportServiceInvocation, all attempts to set its Service Reporting Switch shall fail.",
        54,
        59,
    ),
    "12-programming-language-mappings-page-402-l86-28": (
        "The federate shall send a heartbeat message unless it has sent another message during the configured heartbeat interval, whose default is 60 seconds.",
        83,
        98,
    ),
    "12-programming-language-mappings-page-402-l101-33": (
        "The federate shall use the configured missing-RTI-message timeout, whose default is 180 seconds, to detect that the RTI cannot be reached.",
        98,
        113,
    ),
    "12-programming-language-mappings-page-402-l116-38": (
        "The federate shall stop trying to reconnect after the configured reconnect timeout, whose default is 600 seconds.",
        113,
        124,
    ),
    "12-programming-language-mappings-page-408-l41-13": (
        "CTRL_NEW_SESSION_STATUS, CTRL_HEARTBEAT_RESPONSE, and CTRL_SESSION_TERMINATED messages shall only be sent by the RTI.",
        38,
        43,
    ),
    "12-programming-language-mappings-page-408-l86-28": (
        "Except for CTRL_NEW_SESSION, if the RTI or federate receives a message with an invalid Session ID or sequence number, it shall close the socket and abort the session.",
        83,
        90,
    ),
    "12-programming-language-mappings-page-408-l164-54": (
        "The RTI shall process one received HLA_CALLBACK_REQUEST at a time, including issuance of its response.",
        164,
        169,
    ),
    "11-management-object-model-page-353-l99-32": (
        "Handles shall be unique within a federation execution.",
        99,
        101,
    ),
    "11-management-object-model-page-353-l120-39": (
        "A handle sent as an attribute or parameter value shall be encoded before sending.",
        120,
        123,
    ),
    "11-management-object-model-page-353-l123-40": (
        "A handle sent as an attribute or parameter value shall be reconstituted by the receiver.",
        120,
        126,
    ),
    "11-management-object-model-page-354-l108-35": (
        "The LogicalTime and LogicalTimeInterval abstract interfaces shall provide methods for obtaining a string representation suitable for printing.",
        99,
        113,
    ),
    "11-management-object-model-page-354-l129-42": (
        "The LogicalTime, LogicalTimeInterval, and LogicalTimeFactory abstract interfaces shall support encoding logical time or interval instances into a compact network representation and creating them from that representation at a specified array offset.",
        114,
        175,
    ),
    "11-management-object-model-page-354-l183-60": (
        "The LogicalTimeFactory abstract interface shall provide methods to create LogicalTime instances with the user-defined initial and final values.",
        177,
        203,
    ),
    "11-management-object-model-page-354-l249-82": (
        "The HLAInteger64Time logical time implementation shall be based on HLAInteger64BE.",
        243,
        258,
    ),
    "11-management-object-model-page-354-l264-87": (
        "The HLAFloat64Time logical time implementation shall be based on HLAFloat64BE.",
        258,
        270,
    ),
    "11-management-object-model-page-355-l15-4": (
        "The HLAInteger64Time implementation shall provide the HLAInteger64Time, HLAInteger64TimeFactory, HLAInteger64TimeInterval, and HLAInteger64TimeIntervalFactory implementations described in §12.4.1.",
        9,
        17,
    ),
    "11-management-object-model-page-355-l147-48": (
        "Methods defined as returning or accepting a LogicalTimeInterval reference in the HLAInteger64Time implementation shall return or expect a reference to HLAInteger64TimeInterval.",
        141,
        156,
    ),
    "11-management-object-model-page-355-l189-62": (
        "All methods of HLAInteger64TimeIntervalFactory shall return references to HLAInteger64TimeInterval.",
        174,
        200,
    ),
    "11-management-object-model-page-355-l210-69": (
        "The HLAFloat64Time implementation shall provide the HLAFloat64Time, HLAFloat64TimeFactory, HLAFloat64TimeInterval, and HLAFloat64TimeIntervalFactory implementations described in §12.4.2.",
        204,
        212,
    ),
    "11-management-object-model-page-356-l38-12": (
        "Methods defined as returning or accepting a LogicalTimeInterval reference in the HLAFloat64Time implementation shall return or expect a reference to HLAFloat64TimeInterval.",
        32,
        47,
    ),
    "11-management-object-model-page-356-l134-44": (
        "All methods of HLAFloat64TimeIntervalFactory shall return references to HLAFloat64TimeInterval.",
        119,
        140,
    ),
    "11-management-object-model-page-356-l221-73": (
        "The Credentials class shall provide methods to obtain the credential type’s string name and a byte array containing the credentials data.",
        215,
        235,
    ),
    "11-management-object-model-page-356-l383-127": (
        "All Authorizer implementations shall support the predefined HLAnoCredentials credential type with an empty data value.",
        383,
        389,
    ),
    "11-management-object-model-page-357-l106-34": (
        "Authorization of HLAplainTextPassword credentials shall use a global plain text password.",
        106,
        108,
    ),
    "11-management-object-model-page-357-l127-41": (
        "The predefined HLAauthorizer implementation of AuthorizerFactory shall return the name HLAauthorizer.",
        121,
        132,
    ),
    "11-management-object-model-page-357-l148-48": (
        "The predefined HLAauthorizer implementation of Authorizer shall return the string name HLAauthorizer.",
        142,
        153,
    ),
    "11-management-object-model-page-357-l199-65": (
        "The RTI shall support concurrent joined federate-initiated service invocations to the same RTIambassador instance.",
        199,
        204,
    ),
    "11-management-object-model-page-363-l13-4": (
        "A get(index) method shall be supported for retrieving data elements from a complex encoder class instance.",
        10,
        15,
    ),
    "11-management-object-model-page-363-l16-5": (
        "HLAvariantRecord shall support setVariant to associate encoders and decoders with discriminants, and setDiscriminant and getDiscriminant to indicate the selected variant.",
        16,
        22,
    ),
    "11-management-object-model-page-363-l22-7": (
        "The variant indicated by setDiscriminant and getDiscriminant shall be used for composing, encoding, and decoding data elements.",
        16,
        24,
    ),
    "11-management-object-model-page-363-l28-9": (
        "The RTI shall supply an implementation of hla.rti1516_2025.encoding.EncoderFactory.",
        28,
        37,
    ),
    "11-management-object-model-page-363-l37-12": (
        "EncoderFactory shall provide methods for creating encoding helper instances.",
        31,
        40,
    ),
    "11-management-object-model-page-371-l28-8": (
        "Each handle interface’s encode() method shall place a compact, opaque representation suitable for network transmission into the provided byte array at the specified offset.",
        22,
        38,
    ),
    "11-management-object-model-page-371-l79-25": (
        "If a byte array cannot be decoded into a handle usable by the federation, decode() shall throw CouldNotDecode.",
        67,
        83,
    ),
    "11-management-object-model-page-371-l259-85": (
        "Members of each handle set shall be of the corresponding handle type, such as AttributeHandle for AttributeHandleSet.",
        253,
        289,
    ),
    "11-management-object-model-page-378-l54-17": (
        "All RTI implementations and federates shall be built against the standard C++ header files in Annex C.",
        54,
        57,
    ),
    "11-management-object-model-page-378-l57-18": (
        "The standard C++ header files shall be provided in a directory named RTI.",
        54,
        59,
    ),
    "11-management-object-model-page-378-l87-28": (
        "The RTI API library shall implement all non-pure-virtual functions and classes listed in the Annex C RTI C++ header files, excluding LogicalTimeFactoryFactory and AuthorizerFactoryFactory.",
        87,
        105,
    ),
    "11-management-object-model-page-378-l306-101": (
        "LogicalTimeFactoryFactory shall forward requests for other time types, including the standardized time types, to HLAlogicalTimeFactoryFactory.",
        300,
        318,
    ),
    "11-management-object-model-page-378-l339-112": (
        "The header file for the LogicalTimeFactoryFactory declaration shall be in the libfedtime subdirectory.",
        321,
        341,
    ),
    "06-object-management-page-112-l42-12": (
        "All instance attribute/value pairs in an Update Attribute Values invocation that have identical transportation type, sent message order type, and sent region designators shall be defined as one passel.",
        36,
        45,
    ),
    "06-object-management-page-112-l51-15": (
        "Elements shall not change passels.",
        51,
        54,
    ),
    "06-object-management-page-112-l75-22": (
        "The RTI shall not provide an update rate to a joined federate that exceeds the subscribed update rate.",
        75,
        78,
    ),
    "06-object-management-page-112-l81-24": (
        "No minimum update rate shall be guaranteed to a joined federate.",
        78,
        84,
    ),
    "06-object-management-page-112-l90-27": (
        "For attributes with best-effort transportation, messages shall not be delivered to a joined federate at an update rate higher than the subscribed update rate.",
        90,
        96,
    ),
    "07-ownership-management-page-151-l63-20": (
        "If the Attribute Ownership Divestiture If Wanted service returns the designated instance attribute among the released attributes, that instance attribute shall be unowned by the invoking joined federate.",
        60,
        66,
    ),
    "07-ownership-management-page-151-l84-27": (
        "If the joined federate stops publishing the corresponding class attribute at the instance attribute’s known class, the instance attribute shall immediately become unowned by all joined federates.",
        81,
        89,
    ),
    "07-ownership-management-page-151-l138-45": (
        "When Negotiated Attribute Ownership Divestiture or Attribute Ownership Divestiture If Wanted is used, the RTI shall guarantee immediate transfer of the instance attribute after the owning joined federate loses ownership.",
        135,
        143,
    ),
    "07-ownership-management-page-151-l141-46": (
        "When Negotiated Attribute Ownership Divestiture or Attribute Ownership Divestiture If Wanted is used, another joined federate shall be granted ownership of the instance attribute immediately after the owning joined federate loses ownership.",
        135,
        143,
    ),
    "08-time-management-page-217-l107-34": (
        "The available dimensions of a class attribute shall be the dimensions associated with that class attribute in the FDD.",
        107,
        112,
    ),
    "08-time-management-page-217-l119-38": (
        "The available dimensions of an interaction class shall be the dimensions associated with that interaction class in the FDD.",
        119,
        124,
    ),
    "08-time-management-page-217-l140-45": (
        "Each dimension in the FDD shall specify either a default range with bounds [0, the dimension’s upper bound) or an excluded indicator in the Value When Unspecified Field of the FDD Dimension Table.",
        140,
        146,
    ),
    "08-time-management-page-217-l143-46": (
        "If a dimension has a default range in the FDD and is omitted from a region specification, that dimension and its default range shall be added when the region realization is created.",
        140,
        152,
    ),
    "09-data-distribution-management-page-218-l162-51": (
        "When a region realization is created from a region specification, all specified dimensions of that region specification shall be included in the region realization.",
        150,
        168,
    ),
    "09-data-distribution-management-page-218-l165-52": (
        "When a region realization is created from a region specification, the range of each specified dimension in the realization shall equal the range in the region specification.",
        150,
        168,
    ),
    "09-data-distribution-management-page-218-l177-56": (
        "For each unspecified dimension of a region realization, if the FDD gives a default range rather than the excluded indicator, that default range shall be added to the region realization.",
        174,
        179,
    ),
    "09-data-distribution-management-page-218-l186-59": (
        "When a federate modifies a region specification from which region realizations were derived, the RTI shall fill in unspecified dimensions in those region realizations using the FDD default ranges.",
        183,
        189,
    ),
    "09-data-distribution-management-page-234-l14-3": (
        "Each (object class, class attribute, region) triple in a Subscribe Object Class Attributes With Regions invocation shall take the effect of that invocation’s optional passive/active subscription indicator.",
        11,
        19,
    ),
    "09-data-distribution-management-page-234-l26-7": (
        "If an existing (object class, class attribute, region) subscription matches a triple in the current Subscribe Object Class Attributes With Regions invocation, it shall take the effect of the current invocation’s optional active/passive subscription indicator.",
        17,
        31,
    ),
    "09-data-distribution-management-page-234-l38-11": (
        "Invoking Subscribe Object Class Attributes With Regions with an empty region set shall not change the active/passive nature of already subscribed (object class, class attribute, region) triples.",
        35,
        44,
    ),
    "09-data-distribution-management-page-234-l59-18": (
        "If no update rate is specified, the attributes shall be considered subscribed with the default update rate.",
        59,
        65,
    ),
    "09-data-distribution-management-page-234-l62-19": (
        "If no update rate is specified, no update rate reduction shall take place.",
        59,
        65,
    ),
    "09-data-distribution-management-page-237-l16-4": (
        "If the optional passive subscription indicator specifies a passive subscription, the service invocation shall not cause Turn Interactions On to be invoked at any other joined federate.",
        7,
        21,
    ),
    "09-data-distribution-management-page-237-l28-8": (
        "If the optional passive subscription indicator specifies a passive subscription and a specified region was previously subscribed actively, this service invocation shall change that subscription to passive.",
        7,
        31,
    ),
    "09-data-distribution-management-page-237-l49-15": (
        "Each interaction class subscribed with regions shall be subscribed either actively or passively with a given region, but not both.",
        49,
        54,
    ),
    "09-data-distribution-management-page-237-l76-24": (
        "If an existing (interaction class, region) subscription matches a pair in the current Subscribe Interaction Class With Regions invocation, it shall take the effect of the current invocation’s optional passive/active subscription indicator.",
        70,
        81,
    ),
    "09-data-distribution-management-page-237-l88-28": (
        "Invoking Subscribe Interaction Class With Regions with an empty region set shall not change the active/passive nature of already subscribed (interaction class, region) pairs.",
        85,
        93,
    ),
    "09-data-distribution-management-page-237-l94-30": (
        "Each Subscribe Interaction Class With Regions invocation shall add regions absent from the specified interaction class’s existing subscriptions.",
        91,
        101,
    ),
    "11-management-object-model-page-359-l21-6": (
        "The entire hla.rti1516_2025 Java API package and its subpackages shall be furnished without additions, deletions, or a change of package name as part of each implementation.",
        6,
        26,
    ),
    "11-management-object-model-page-359-l33-10": (
        "The Java interfaces that represent handles shall implement a hashCode() method returning an int suitable for use as a hash value when storing handles in a hash table.",
        33,
        50,
    ),
    "11-management-object-model-page-359-l219-72": (
        "The RtiFactory class shall be listed in a provider configuration file named hla.rti1516_2025.RtiFactory in the META-INF/services directory of the JAR.",
        210,
        234,
    ),
    "11-management-object-model-page-359-l234-77": (
        "The RtiFactory provider configuration file shall contain a line with the class name of the implementing class.",
        219,
        243,
    ),
    "11-management-object-model-page-359-l393-130": (
        "The provider configuration file named hla.rti1516_2025.AuthorizerFactory shall be in the META-INF/services directory of the JAR.",
        375,
        402,
    ),
    "12-programming-language-mappings-page-413-l42-13": (
        "An HLA-conforming RTI shall implement all joined federate-initiated services and invoke all RTI-initiated services as defined in this document.",
        42,
        45,
    ),
    "12-programming-language-mappings-page-413-l45-14": (
        "Mapping these interfaces to programming languages shall be done in accordance with Clause 12.",
        45,
        48,
    ),
    "12-programming-language-mappings-page-413-l48-15": (
        "At least one language-specific API shall be implemented.",
        45,
        48,
    ),
    "12-programming-language-mappings-page-413-l51-16": (
        "Conformance verification shall be done according to the language APIs implemented.",
        51,
        54,
    ),
    "12-programming-language-mappings-page-413-l54-17": (
        "Certified results shall reflect the language APIs verified.",
        51,
        56,
    ),
}

ADDED: dict[str, tuple[str, str, int, int]] = {
    "11-management-object-model-page-292-l117-38-composites": (
        "11-management-object-model-page-292-l117-38",
        "HLAargumentValue composite encoding shall include Enumeration, Record, Array, and PairList forms constructed from basic or composite elements.",
        45,
        95,
    ),
    "11-management-object-model-page-356-l326-108-connect": (
        "11-management-object-model-page-356-l326-108",
        "The Authorizer interface shall provide a method to authorize the Connect RTI operation using the federate’s credentials.",
        336,
        345,
    ),
    "11-management-object-model-page-356-l326-108-federation": (
        "11-management-object-model-page-356-l326-108",
        "The Authorizer interface shall provide a method to authorize Create Federation Execution or Destroy Federation Execution using the federate’s credentials and federation name.",
        348,
        368,
    ),
    "11-management-object-model-page-356-l326-108-join": (
        "11-management-object-model-page-356-l326-108",
        "The Authorizer interface shall provide a method to authorize Join Federation Execution using the federate’s credentials, federation name, federate type, and optional federate name.",
        369,
        383,
    ),
    "11-management-object-model-page-357-l34-10-create": (
        "11-management-object-model-page-357-l34-10",
        "The AuthorizerFactory interface shall provide a method to obtain an Authorizer implementation instance for the authorization service.",
        44,
        54,
    ),
    "11-management-object-model-page-291-l77-25-transport": (
        "11-management-object-model-page-291-l77-25",
        "An RTI shall never modify the transportation or order type of a MOM instance attribute or interaction class.",
        87,
        91,
    ),
    "11-management-object-model-page-291-l77-25-ddm": (
        "11-management-object-model-page-291-l77-25",
        "An RTI shall not use DDM services with MOM instance attributes or interaction classes except as noted in §11.4.",
        93,
        99,
    ),
    "09-data-distribution-management-page-222-l23-6-unsubscribe-object": (
        "09-data-distribution-management-page-222-l23-6",
        "A joined federate using DDM services shall interpret Unsubscribe Object Class Attributes as the corresponding Unsubscribe Object Class Attributes With Regions service invoked with the default region.",
        38,
        40,
    ),
    "09-data-distribution-management-page-222-l23-6-subscribe-interaction": (
        "09-data-distribution-management-page-222-l23-6",
        "A joined federate using DDM services shall interpret Subscribe Interaction Class as the corresponding Subscribe Interaction Class With Regions service invoked with the default region.",
        44,
        46,
    ),
    "09-data-distribution-management-page-222-l23-6-unsubscribe-interaction": (
        "09-data-distribution-management-page-222-l23-6",
        "A joined federate using DDM services shall interpret Unsubscribe Interaction Class as the corresponding Unsubscribe Interaction Class With Regions service invoked with the default region.",
        50,
        52,
    ),
    "07-ownership-management-page-150-l74-23-if-available": (
        "07-ownership-management-page-150-l74-23",
        "A joined federate shall not stop publishing a class attribute at the known class of an object instance while its corresponding instance attribute remains under an unresolved Attribute Ownership Acquisition If Available request.",
        99,
        112,
    ),
    "04-federation-management-page-058-l112-33-designator": (
        "04-federation-management-page-058-l112-33",
        "After a federate resigns, its federate designator shall not be reused in the same federation execution.",
        113,
        116,
    ),
    "04-federation-management-page-058-l112-33-actions": (
        "04-federation-management-page-058-l112-33",
        "Resign Federation Execution shall accept an action argument selecting a directive to divest all owned attributes, delete all deletable object instances, cancel pending ownership acquisitions, delete then divest, cancel then delete then divest, or perform no actions.",
        119,
        145,
    ),
    "05-declaration-management-page-081-l44-12-discovery": (
        "05-declaration-management-page-081-l44-12",
        "DM and DDM services, together with object and ownership management and the FDD class hierarchies, shall determine the object classes at which object instances are discovered.",
        54,
        58,
    ),
    "05-declaration-management-page-081-l44-12-attributes": (
        "05-declaration-management-page-081-l44-12",
        "DM and DDM services, together with object and ownership management and the FDD class hierarchies, shall determine the instance attributes available for update and reflection.",
        60,
        64,
    ),
    "05-declaration-management-page-081-l44-12-send": (
        "05-declaration-management-page-081-l44-12",
        "DM and DDM services, together with object and ownership management and the FDD class hierarchies, shall determine which interactions may be sent.",
        66,
        70,
    ),
    "05-declaration-management-page-081-l44-12-receive": (
        "05-declaration-management-page-081-l44-12",
        "DM and DDM services, together with object and ownership management and the FDD class hierarchies, shall determine the interaction classes at which interactions are received.",
        72,
        76,
    ),
    "05-declaration-management-page-081-l44-12-parameters": (
        "05-declaration-management-page-081-l44-12",
        "DM and DDM services, together with object and ownership management and the FDD class hierarchies, shall determine the parameters available for sending and receiving.",
        78,
        82,
    ),
    "05-declaration-management-page-081-l44-12-directed": (
        "05-declaration-management-page-081-l44-12",
        "DM and DDM services, together with object and ownership management and the FDD class hierarchies, shall determine the class directed interactions available for sending and receiving.",
        84,
        88,
    ),
    "08-time-management-page-180-l9-1-passels": (
        "08-time-management-page-180-l9-1",
        "Each passel produced by an Update Attribute Values invocation shall be considered a separate message.",
        25,
        32,
    ),
    "08-time-management-page-180-l9-1-receiving": (
        "08-time-management-page-180-l9-1",
        "Invoking Reflect Attribute Values, Receive Interaction, or Remove Object Instance at a joined federate shall be called receiving a message.",
        34,
        41,
    ),
    "04-federation-management-page-047-l17-4-interaction-structure": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include a complete interaction class structure table.",
        32,
        34,
    ),
    "04-federation-management-page-047-l17-4-directed-interaction": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include a complete directed interaction table.",
        38,
        40,
    ),
    "04-federation-management-page-047-l17-4-attributes": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include an attribute table with object, attribute, transportation, and order columns.",
        44,
        46,
    ),
    "04-federation-management-page-047-l17-4-parameters": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include a parameter table with interaction, parameter, transportation, and order columns.",
        50,
        52,
    ),
    "04-federation-management-page-047-l17-4-dimensions": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include a complete dimension table.",
        56,
        58,
    ),
    "04-federation-management-page-047-l17-4-transportation": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include a transportation type table with name and reliability columns.",
        62,
        64,
    ),
    "04-federation-management-page-047-l17-4-update-rates": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include an update rate table with name and maximum update rate columns.",
        68,
        70,
    ),
    "04-federation-management-page-047-l17-4-switches": (
        "04-federation-management-page-047-l17-4",
        "The FDD retained and combined by the RTI from FOM modules shall include a complete switches table.",
        74,
        76,
    ),
    "06-object-management-page-111-l25-6-best-effort": (
        "06-object-management-page-111-l25-6",
        "The RTI shall always support HLAbestEffort as the default best-effort transportation type.",
        34,
        39,
    ),
    "08-time-management-page-188-l69-21-tso-name": (
        "08-time-management-page-188-l69-21",
        "The legal name of the TSO order type shall be TimeStamp.",
        75,
        77,
    ),
    "08-time-management-page-188-l69-21-ro-name": (
        "08-time-management-page-188-l69-21",
        "The legal name of the RO order type shall be Receive.",
        81,
        83,
    ),
    "11-management-object-model-page-392-l232-75-best-effort": (
        "11-management-object-model-page-392-l232-75",
        "The RTI shall provide the RTI_BEST_EFFORT transportation type enumeration.",
        239,
        243,
    ),
    "12-programming-language-mappings-page-412-l51-16-server-validation": (
        "12-programming-language-mappings-page-412-l51-16",
        "When using TLS 1.3, the RTI and federate shall support server certificate validation.",
        48,
        70,
    ),
    "12-programming-language-mappings-page-412-l51-16-server-key": (
        "12-programming-language-mappings-page-412-l51-16",
        "In TLS 1.3 server certificate validation mode, a server certificate and corresponding private key shall be installed at the RTI.",
        63,
        68,
    ),
    "12-programming-language-mappings-page-412-l51-16-federate-validation": (
        "12-programming-language-mappings-page-412-l51-16",
        "In TLS 1.3 server certificate validation mode, the federate shall verify the server certificate and RTI identity using a trusted certificate.",
        63,
        70,
    ),
    "01-overview-page-018-l58-7-federate": (
        "01-overview-page-018-l58-7",
        "Federate names shall be case-sensitive.",
        64,
        64,
    ),
    "01-overview-page-018-l58-7-object-class": (
        "01-overview-page-018-l58-7",
        "Object class names shall be case-sensitive.",
        65,
        65,
    ),
    "01-overview-page-018-l58-7-attribute": (
        "01-overview-page-018-l58-7",
        "Attribute names shall be case-sensitive.",
        66,
        66,
    ),
    "01-overview-page-018-l58-7-object-instance": (
        "01-overview-page-018-l58-7",
        "Object instance names shall be case-sensitive.",
        67,
        67,
    ),
    "01-overview-page-018-l58-7-interaction-class": (
        "01-overview-page-018-l58-7",
        "Interaction class names shall be case-sensitive.",
        68,
        68,
    ),
    "01-overview-page-018-l58-7-parameter": (
        "01-overview-page-018-l58-7",
        "Parameter names shall be case-sensitive.",
        69,
        69,
    ),
    "01-overview-page-018-l58-7-order": (
        "01-overview-page-018-l58-7",
        "Order names shall be case-sensitive.",
        70,
        70,
    ),
    "01-overview-page-018-l58-7-transportation": (
        "01-overview-page-018-l58-7",
        "Transportation type names shall be case-sensitive.",
        71,
        71,
    ),
    "01-overview-page-018-l58-7-dimension": (
        "01-overview-page-018-l58-7",
        "Dimension names shall be case-sensitive.",
        72,
        72,
    ),
    "12-programming-language-mappings-page-411-l20-6-tls": (
        "12-programming-language-mappings-page-411-l20-6",
        "TLS 1.3 over TCP/IP shall be supported as a transport protocol for encrypted communication.",
        26,
        28,
    ),
    "12-programming-language-mappings-page-411-l20-6-websocket": (
        "12-programming-language-mappings-page-411-l20-6",
        "WebSocket over TCP/IP shall be supported as a transport protocol.",
        29,
        31,
    ),
    "12-programming-language-mappings-page-411-l20-6-secure-websocket": (
        "12-programming-language-mappings-page-411-l20-6",
        "Secure WebSocket over TLS 1.3 shall be supported as a transport protocol for encrypted communication.",
        32,
        34,
    ),
    "01-overview-page-018-l18-2-unique": (
        "01-overview-page-018-l18-2",
        "An object instance designator shall be unique within each federation execution.",
        19,
        20,
    ),
    "01-overview-page-018-l18-2-generated": (
        "01-overview-page-018-l18-2",
        "Object instance designators shall be generated dynamically by the RTI.",
        20,
        21,
    ),
    "04-federation-management-page-038-l21-4-disconnect": (
        "04-federation-management-page-038-l21-4",
        "After resigning with no further intent to join or create federation executions, a federate shall perform Disconnect.",
        23,
        25,
    ),
    "04-federation-management-page-038-l27-5-evoked": (
        "04-federation-management-page-038-l27-5",
        "In the EVOKED callback model, the RTI shall invoke callbacks only when the federate invokes Evoke Callback or Evoke Multiple Callbacks, unless callbacks have been disabled through Disable Callbacks.",
        32,
        34,
    ),
    "04-federation-management-page-038-l27-5-both": (
        "04-federation-management-page-038-l27-5",
        "RTIs shall implement both IMMEDIATE and EVOKED callback models.",
        34,
        36,
    ),
    "04-federation-management-page-044-l54-17-deliver": (
        "04-federation-management-page-044-l54-17",
        "After a restore completes, the RTI shall deliver related saved messages as appropriate to joined federates in the restored federation execution.",
        54,
        62,
    ),
    "05-declaration-management-page-081-l104-31-cycle": (
        "05-declaration-management-page-081-l104-31",
        "A class shall not be a superclass of a class that is its superclass.",
        105,
        109,
    ),
    "12-programming-language-mappings-page-397-l45-14-set": (
        "12-programming-language-mappings-page-397-l45-14",
        "A Set shall not contain duplicates.",
        45,
        47,
    ),
    "10-support-services-page-269-l167-52-effect": (
        "10-support-services-page-269-l167-52",
        "The RTI shall enable the Attribute Relevance Advisory Switch for TRUE and disable it for FALSE.",
        164,
        170,
    ),
    "10-support-services-page-271-l67-19-effect": (
        "10-support-services-page-271-l67-19",
        "The RTI shall enable the Attribute Scope Advisory Switch for TRUE and disable it for FALSE.",
        64,
        71,
    ),
    "10-support-services-page-272-l146-45-effect": (
        "10-support-services-page-272-l146-45",
        "The RTI shall enable the Interaction Relevance Advisory Switch for TRUE and disable it for FALSE.",
        143,
        150,
    ),
    "10-support-services-page-274-l58-16-effect": (
        "10-support-services-page-274-l58-16",
        "The RTI shall enable the Convey Region Designator Sets Switch for TRUE and disable it for FALSE.",
        55,
        62,
    ),
    "10-support-services-page-277-l31-7-effect": (
        "10-support-services-page-277-l31-7",
        "The RTI shall enable the Service Reporting Switch for TRUE and disable it for FALSE, subject to the subscription restriction.",
        28,
        39,
    ),
    "10-support-services-page-278-l113-34-effect": (
        "10-support-services-page-278-l113-34",
        "The RTI shall enable the Exception Reporting Switch for TRUE and disable it for FALSE.",
        110,
        117,
    ),
    "10-support-services-page-285-l14-1-true": (
        "10-support-services-page-285-l14-1",
        "A TRUE Evoke Multiple Callbacks pending callback indicator shall indicate that callbacks are pending.",
        14,
        17,
    ),
    "10-support-services-page-285-l14-1-false": (
        "10-support-services-page-285-l14-1",
        "A FALSE Evoke Multiple Callbacks pending callback indicator shall indicate that no callbacks are pending.",
        14,
        20,
    ),
    "10-support-services-page-287-l60-19-register": (
        "10-support-services-page-287-l60-19",
        "The RTI shall register MOM object instances and update their instance attribute values.",
        60,
        64,
    ),
    "10-support-services-page-287-l63-20-send": (
        "10-support-services-page-287-l63-20",
        "The RTI shall publish and send MOM interaction classes designated for RTI transmission.",
        63,
        67,
    ),
    "08-time-management-page-216-l135-42-no-reference": (
        "08-time-management-page-216-l135-42",
        "Joined federates shall have no way to refer to the default region.",
        135,
        140,
    ),
    "07-ownership-management-page-152-l86-27-release": (
        "07-ownership-management-page-152-l86-27",
        "After an Attribute Ownership Acquisition invocation, the RTI shall invoke Request Attribute Ownership Release at the federate that owns the designated instance attribute.",
        86,
        94,
    ),
    "07-ownership-management-page-177-l62-19-service": (
        "07-ownership-management-page-177-l62-19",
        "A joined federate shall request to advance its logical time only by invoking one of the time advance services listed in §8.1.2.",
        62,
        68,
    ),
    "06-object-management-page-113-l24-4-result": (
        "06-object-management-page-113-l24-4",
        "The RTI shall provide the result of an object instance name reservation attempt through Object Instance Name Reserved.",
        24,
        29,
    ),
    "06-object-management-page-118-l22-3-association": (
        "06-object-management-page-118-l22-3",
        "The RTI shall coadunate the new object instance handle with an instance of the supplied object class.",
        22,
        27,
    ),
    "06-object-management-page-118-l43-10-equality": (
        "06-object-management-page-118-l43-10",
        "Two handles shall be considered the same when the API’s comparison operator determines them to be equal.",
        43,
        51,
    ),
    "04-federation-management-page-058-l147-40-assumption": (
        "04-federation-management-page-058-l147-40",
        "To identify federates willing to own the unowned instance attribute, the RTI shall invoke Request Attribute Ownership Assumption at eligible federates that are neither Acquiring nor Willing to Acquire that attribute.",
        147,
        147,
    ),
    "04-federation-management-page-059-l8-1-owned": (
        "04-federation-management-page-059-l8-1",
        "Once the instance attribute becomes owned, the RTI shall not invoke Request Attribute Ownership Assumption at additional federates.",
        8,
        8,
    ),
    "04-federation-management-page-059-l8-1-last-federate": (
        "04-federation-management-page-059-l8-1",
        "If no other federates remain joined when a federate resigns, the RTI shall process resignation directive 2 regardless of the supplied arguments.",
        8,
        8,
    ),
    "04-federation-management-page-060-l139-34-announce": (
        "04-federation-management-page-060-l139-34",
        "When a synchronization point label is successfully registered, the RTI shall announce it to the designated joined federates.",
        139,
        139,
    ),
    "04-federation-management-page-060-l139-34-all": (
        "04-federation-management-page-060-l139-34",
        "If the optional federate designator set is empty or absent, all joined federates in the federation execution shall be informed of the synchronization point label.",
        139,
        139,
    ),
    "04-federation-management-page-061-l11-1-members": (
        "04-federation-management-page-061-l11-1",
        "For a synchronization point to be registered successfully, all designated joined federates shall be members of the federation execution.",
        11,
        11,
    ),
    "04-federation-management-page-061-l11-1-resigned": (
        "04-federation-management-page-061-l11-1",
        "If a designated federate has resigned before Confirm Synchronization Point Registration is invoked, registration shall fail.",
        11,
        11,
    ),
    "04-federation-management-page-061-l11-1-tag": (
        "04-federation-management-page-061-l11-1",
        "The user-supplied tag shall be announced together with the synchronization point label.",
        11,
        11,
    ),
    "04-federation-management-page-062-l140-35-invoke": (
        "04-federation-management-page-062-l140-35",
        "When a synchronization point label is registered, the RTI shall invoke Announce Synchronization Point at all joined federates or at the specified set of joined federates.",
        140,
        140,
    ),
    "04-federation-management-page-062-l140-35-set": (
        "04-federation-management-page-062-l140-35",
        "Joined federates informed of a synchronization point label through Announce Synchronization Point shall form that point’s synchronization set.",
        140,
        140,
    ),
    "04-federation-management-page-063-l12-1-new-joiners": (
        "04-federation-management-page-063-l12-1",
        "Federates that join and receive Announce Synchronization Point for an existing label shall become part of that point’s synchronization set.",
        12,
        12,
    ),
    "04-federation-management-page-063-l12-1-resignation": (
        "04-federation-management-page-063-l12-1",
        "Joined federates that resign after synchronization point announcement but before synchronization completes shall be removed from that point’s synchronization set.",
        12,
        12,
    ),
    "04-federation-management-page-063-l12-1-tag": (
        "04-federation-management-page-063-l12-1",
        "The tag supplied by Announce Synchronization Point shall equal the tag supplied to the corresponding Register Federation Synchronization Point invocation.",
        12,
        12,
    ),
    "04-federation-management-page-049-l133-42-defaults": (
        "04-federation-management-page-049-l133-42",
        "RTIs shall provide two default logical time implementations, one integer and one floating point.",
        133,
        138,
    ),
    "04-federation-management-page-053-l50-8-before-fom": (
        "04-federation-management-page-053-l50-8",
        "The MIM shall be loaded before any supplied FOM module.",
        50,
        50,
    ),
    "04-federation-management-page-053-l50-8-reserved-name": (
        "04-federation-management-page-053-l50-8",
        "If a MIM argument is supplied, its module designator shall not be ‘HLAstandardMIM’.",
        50,
        50,
    ),
    "09-data-distribution-management-page-221-l89-28-normalization": (
        "09-data-distribution-management-page-221-l89-28",
        "Normalization of federation data to [0, a dimension’s upper bound) for DDM services shall be left to the federation.",
        86,
        91,
    ),
    "10-support-services-page-284-l71-20-precision": (
        "10-support-services-page-284-l71-20",
        "The Evoke Callback wait-duration argument shall have a precision of at least 1 ms.",
        71,
        75,
    ),
    "10-support-services-page-284-l77-22-true": (
        "10-support-services-page-284-l77-22",
        "A TRUE pending callback indicator shall indicate that callbacks are pending.",
        77,
        83,
    ),
    "06-object-management-page-112-l42-12-delivery": (
        "06-object-management-page-112-l42-12",
        "The instance attributes that make up a passel shall be available for delivery in the same Reflect Attribute Values service invocation.",
        42,
        47,
    ),
    "06-object-management-page-112-l51-15-division": (
        "06-object-management-page-112-l51-15",
        "Passels shall not be divided.",
        51,
        54,
    ),
    "06-object-management-page-112-l51-15-combination": (
        "06-object-management-page-112-l51-15",
        "Passels shall not be combined with other passels.",
        51,
        54,
    ),
    "06-object-management-page-112-l75-22-owner-rate": (
        "06-object-management-page-112-l75-22",
        "The RTI shall not deliver more updates than the owning joined federate provides.",
        75,
        81,
    ),
}

# Each entry is a reviewed split of a printed paragraph into separately
# testable obligations.  Child spans can overlap when the source wraps two
# obligations onto one line; they still point at the printed rule itself.
COMPOUND_SPLITS: dict[str, tuple[tuple[str, str, int, int], ...]] = {
    "04-federation-management-page-050-l123-40": (
        ("base", "A service invocation that is not permitted shall fail.", 123, 125),
        (
            "exception",
            "When a service invocation is not permitted, the RTI shall throw an exception.",
            123,
            125,
        ),
    ),
    "07-ownership-management-page-153-l60-19": (
        (
            "base",
            "In this case, the Attribute Ownership Acquisition If Available request shall be implicitly canceled.",
            60,
            63,
        ),
        (
            "pending",
            "In this case, the Attribute Ownership Acquisition request shall remain pending until acquisition succeeds, acquisition is denied, or the joined federate successfully cancels it.",
            60,
            67,
        ),
    ),
    "07-ownership-management-page-161-l152-45": (
        (
            "base",
            "If the owning joined federate is Waiting for a New Owner to be Found, the RTI shall not invoke Request Attribute Ownership Release for that instance attribute.",
            152,
            158,
        ),
        (
            "confirm",
            "If the owning joined federate is Waiting for a New Owner to be Found, the RTI shall invoke Request Divestiture Confirmation for that instance attribute.",
            157,
            162,
        ),
    ),
    "07-ownership-management-page-166-l20-3": (
        (
            "base",
            "The Request Attribute Ownership Release service shall provide an object instance designator and a set of attribute designators.",
            20,
            29,
        ),
        (
            "acquisition-result",
            "Request Attribute Ownership Release shall be invoked only as the result of another joined federate's Attribute Ownership Acquisition invocation.",
            20,
            27,
        ),
    ),
    "11-management-object-model-page-363-l4-1": (
        (
            "base",
            "All complex encoder classes shall support the elements that make up the complex class.",
            4,
            7,
        ),
        (
            "element-types",
            "Both complex and noncomplex encoder class instances shall be usable as elements of a complex class instance.",
            4,
            9,
        ),
    ),
    "11-management-object-model-page-381-l4-1": (
        (
            "base",
            "All complex encoder classes shall support the elements that make up the complex class.",
            4,
            7,
        ),
        (
            "element-types",
            "Both complex and noncomplex encoder class instances shall be usable as elements of a complex class instance.",
            4,
            9,
        ),
    ),
    "11-management-object-model-page-290-l165-54": (
        ("base", "The RTI shall be neither time-regulating nor time-constrained.", 165, 167),
        (
            "no-metadata",
            "The RTI shall never provide timestamps or user-supplied tags with instance attribute updates, sent interactions, or object instance deletion.",
            165,
            170,
        ),
    ),
    "04-federation-management-page-039-l4-1": (
        (
            "base",
            "An RTI shall allow one application to participate in a federation as multiple joined federates.",
            9,
            12,
        ),
        (
            "multiple-federations",
            "An RTI shall allow one application to participate in multiple federations as a joined federate or federates.",
            9,
            12,
        ),
    ),
    "04-federation-management-page-051-l18-3": (
        ("base", "The configuration designated by the configuration name shall be used.", 18, 20),
        (
            "default",
            "The implementation's default configuration shall be used if no configuration name is specified or no configuration with the specified name is found.",
            20,
            22,
        ),
    ),
    "04-federation-management-page-053-l43-7": (
        (
            "base",
            "The Create Federation Execution service shall create a new federation execution and add it to the set of supported federation executions.",
            43,
            45,
        ),
        (
            "independence",
            "Each federation execution created by the Create Federation Execution service shall be independent of all other federation executions.",
            45,
            46,
        ),
        (
            "no-intercommunication",
            "There shall be no intercommunication within the RTI between federation executions.",
            46,
            47,
        ),
        (
            "authorization",
            "If the RTI is configured to require authorization, it shall require credentials supplied with Connect that permit creation of the named federation execution.",
            47,
            48,
        ),
    ),
    "04-federation-management-page-054-l101-29": (
        (
            "base",
            "The Destroy Federation Execution service shall remove the specified federation execution from the RTI set of supported federation executions.",
            101,
            103,
        ),
        (
            "stopped",
            "All federation activity shall have stopped before Destroy Federation Execution is invoked.",
            103,
            104,
        ),
        (
            "resigned",
            "All joined federates shall have resigned before Destroy Federation Execution is invoked, either explicitly or via MOM activity.",
            103,
            105,
        ),
        (
            "authorization",
            "If the RTI is configured to require authorization, it shall require credentials supplied with Connect that permit destruction of the named federation execution.",
            105,
            106,
        ),
    ),
    "04-federation-management-page-055-l34-5": (
        (
            "base",
            "The List Federation Executions service shall request the list of existing federation executions.",
            34,
            36,
        ),
        (
            "report",
            "The RTI shall provide federation execution member information by invoking Report Federation Executions.",
            36,
            38,
        ),
    ),
    "04-federation-management-page-056-l27-3": (
        (
            "base",
            "The List Federation Execution Members service shall request the member federates of an existing federation execution.",
            27,
            29,
        ),
        (
            "report",
            "The RTI shall provide member federate information by invoking Report Federation Execution Members.",
            29,
            31,
        ),
    ),
    "04-federation-management-page-057-l32-5": (
        (
            "base",
            "The Join Federation Execution service shall affiliate the federate with the specified federation execution.",
            32,
            34,
        ),
        (
            "intent",
            "Invocation of Join Federation Execution shall indicate the federate's intention to participate in the specified federation.",
            33,
            35,
        ),
        (
            "name-unique",
            "A federate name shall be unique within a federation execution at any given time.",
            35,
            36,
        ),
        (
            "name-assigned",
            "The RTI shall provide a unique federate name if none is supplied.",
            36,
            38,
        ),
        (
            "type",
            "The federate type argument shall distinguish federate categories for federation save and restore.",
            38,
            39,
        ),
        (
            "designator",
            "The returned joined federate designator shall be unique for the federation execution's lifetime while no restore is in progress at any federate.",
            39,
            40,
        ),
        (
            "authorization",
            "If the RTI is configured to require authorization, it shall require credentials supplied with Connect that permit joining the named federation execution with the supplied federate name and type.",
            40,
            42,
        ),
    ),
    "04-federation-management-page-061-l158-40": (
        (
            "base",
            "Confirm Synchronization Point Registration shall indicate to the requesting joined federate the status of its requested synchronization point registration.",
            158,
            161,
        ),
        (
            "response",
            "Confirm Synchronization Point Registration shall be invoked in response to Register Federation Synchronization Point.",
            161,
            163,
        ),
    ),
    "04-federation-management-page-063-l117-26": (
        (
            "base",
            "Synchronization Point Achieved shall inform the RTI that the joined federate has reached the specified synchronization point.",
            117,
            119,
        ),
        (
            "late-join",
            "Once all joined federates in a synchronization set have invoked Synchronization Point Achieved, the RTI shall not invoke Announce Synchronization Point at newly joining federates for that point.",
            119,
            122,
        ),
        (
            "default-success",
            "The RTI shall treat an absent synchronization-success indicator as successful synchronization by that joined federate.",
            122,
            124,
        ),
    ),
    "04-federation-management-page-064-l132-35": (
        (
            "base",
            "Federation Synchronized shall inform a joined federate that all joined federates in the point's synchronization set have invoked Synchronization Point Achieved.",
            132,
            135,
        ),
        (
            "all-members",
            "Federation Synchronized shall be invoked at every joined federate in the synchronization set for that point.",
            135,
            138,
        ),
        (
            "deregister",
            "Once every joined federate in the synchronization set has been notified by Federation Synchronized, the point shall no longer be registered.",
            138,
            141,
        ),
        (
            "remove-set",
            "Once every joined federate in the synchronization set has been notified by Federation Synchronized, the synchronization set for that point shall no longer exist.",
            138,
            141,
        ),
    ),
    "04-federation-management-page-066-l22-5": (
        ("base", "At most one requested federation save shall be outstanding.", 22, 24),
        (
            "replace",
            "A new federation save request shall replace any outstanding save request.",
            23,
            26,
        ),
    ),
    "06-object-management-page-115-l110-30": (
        (
            "base",
            "The RTI shall provide the result of the name reservation attempt via Multiple Object Instance Name Reserved.",
            107,
            112,
        ),
        (
            "no-single-name-callback",
            "Object Instance Name Reserved shall not be used to provide the result for any single name.",
            110,
            115,
        ),
    ),
    "06-object-management-page-143-l162-44": (
        (
            "base",
            "If the instance attribute is unowned, the transportation type specified in the FDD shall be reported.",
            162,
            164,
        ),
        (
            "response",
            "The RTI shall invoke the transportation type report at the joined federate in response to that federate's Query Attribute Transportation Type invocation.",
            159,
            167,
        ),
    ),
    "08-time-management-page-181-l163-18": (
        ("base", "RO messages shall be received in an arbitrary order.", 163, 165),
        (
            "timestamp",
            "A received RO message shall include a timestamp if one was specified when the message was sent.",
            163,
            168,
        ),
    ),
    "08-time-management-page-182-l10-2": (
        (
            "base",
            "A joined federate shall request time-regulating status by invoking Enable Time Regulation.",
            10,
            12,
        ),
        (
            "enabled",
            "The RTI shall subsequently make that joined federate time-regulating by invoking Time Regulation Enabled at the joined federate.",
            11,
            13,
        ),
    ),
    "08-time-management-page-182-l100-31": (
        (
            "base",
            "A joined federate shall request time-constrained status by invoking Enable Time Constrained.",
            100,
            103,
        ),
        (
            "enabled",
            "The RTI shall subsequently make that joined federate time-constrained by invoking Time Constrained Enabled at the joined federate.",
            100,
            106,
        ),
    ),
    "08-time-management-page-203-l95-25": (
        (
            "base",
            "Time Advance Grant shall indicate that a prior joined-federate request to advance logical time has been honored.",
            92,
            97,
        ),
        (
            "logical-time",
            "The Time Advance Grant argument shall indicate the joined federate's new logical time.",
            95,
            100,
        ),
    ),
    "08-time-management-page-216-l54-15": (
        ("base", "A dimension shall be a named interval of nonnegative integers.", 54, 56),
        (
            "ordered-pair",
            "The interval of a dimension shall be defined by an ordered pair of values, with a lower bound of zero and the FDD-specified upper bound for that dimension.",
            54,
            62,
        ),
    ),
    "09-data-distribution-management-page-227-l173-48": (
        ("base", "Delete Region shall delete the specified region.", 173, 175),
        (
            "in-use",
            "A region shall not be deleted while a derived region realization is used for update, class-attribute subscription, or interaction-class subscription.",
            173,
            181,
        ),
    ),
    "10-support-services-page-288-l75-24": (
        (
            "base",
            "The RTI shall not divest ownership of MOM instance attributes defined in this clause.",
            75,
            79,
        ),
        (
            "value-request",
            "In response to Request Attribute Value Update for a MOM object class or instance attribute defined in this clause, the RTI shall supply values through the normal instance-attribute update mechanism.",
            75,
            92,
        ),
    ),
    "11-management-object-model-page-294-l20-6": (
        (
            "base",
            "The service report log file shall begin with an initial record containing federate connection configuration, the joined federation's HLAfederation object, and the joined federate's HLAfederate object.",
            20,
            27,
        ),
        (
            "records",
            "One or more service report records shall follow the initial service report log record.",
            27,
            30,
        ),
    ),
}
for _base_suffix, _pieces in COMPOUND_SPLITS.items():
    for _piece_suffix, _statement, _start, _end in _pieces:
        if _piece_suffix == "base":
            REPAIRS[_base_suffix] = (_statement, _start, _end)
        else:
            ADDED[f"{_base_suffix}-{_piece_suffix}"] = (
                _base_suffix,
                _statement,
                _start,
                _end,
            )

# These printed repetitions inherit distinct conditions from their preceding
# paragraphs.  Keep both source occurrences and name their respective cases.
REPAIRS.update(
    {
        "07-ownership-management-page-162-l34-10": (
            "When a joined federate already in the Acquiring state invokes Attribute Ownership Acquisition, additional eligible instance attributes in that request shall enter the Acquiring state unless they are already Acquiring or Trying to Cancel Acquisition.",
            31,
            45,
        ),
        "07-ownership-management-page-162-l43-13": (
            "For those additional eligible instance attributes in an Acquiring-state request, the owning joined federate shall receive Request Attribute Ownership Release if appropriate.",
            43,
            48,
        ),
        "07-ownership-management-page-162-l64-20": (
            "When a joined federate already in the Trying to Cancel Acquisition state invokes Attribute Ownership Acquisition, additional eligible instance attributes in that request shall enter the Acquiring state unless they are already Acquiring or Trying to Cancel Acquisition.",
            61,
            75,
        ),
        "07-ownership-management-page-162-l76-24": (
            "For those additional eligible instance attributes in a Trying to Cancel Acquisition-state request, the owning joined federate shall receive Request Attribute Ownership Release if appropriate.",
            73,
            81,
        ),
        "09-data-distribution-management-page-220-l11-3": (
            "Region realizations generated for update of an instance attribute shall contain only dimensions available to that instance attribute.",
            5,
            13,
        ),
        "09-data-distribution-management-page-220-l95-31": (
            "Region realizations generated for subscription of a class attribute shall contain only dimensions available to that class attribute.",
            89,
            97,
        ),
        "01-overview-page-019-l11-2": (
            "All API implementations shall support the same semantics for pairs, sets, collections, constrained sets of pairs, and collections of pairs.",
            11,
            17,
        ),
        "04-federation-management-page-044-l108-35": (
            "The RTI shall keep track of each synchronization point separately.",
            108,
            112,
        ),
        "04-federation-management-page-065-l100-25": (
            "A supplied optional federation-save timestamp shall be greater than the time position of every time-constrained joined federate in the federation execution.",
            100,
            108,
        ),
        "07-ownership-management-page-175-l29-7": (
            "Logical time in the modeled system shall be represented in the federation as points along a time axis with an initial and final point.",
            29,
            34,
        ),
        "07-ownership-management-page-177-l110-35": (
            "Federates advancing through Flush Queue Grant shall receive a supplemental optimistic logical time in addition to a logical time.",
            110,
            115,
        ),
        "08-time-management-page-202-l107-29": (
            "The logical time argument shall indicate the joined federate's new logical time.",
            106,
            110,
        ),
        "09-data-distribution-management-page-223-l40-13": (
            "From a joined federate's perspective, the subscribed attributes of an object class shall be the class attributes previously supplied to Subscribe Object Class Attributes for that class and not subsequently unsubscribed.",
            40,
            51,
        ),
        "08-time-management-page-181-l115-2": (
            "Table 2 illustrates how the order type of a sent message shall be determined.",
            112,
            117,
        ),
        "08-time-management-page-181-l118-3": (
            "Table 3 illustrates how the order type of a received message shall be determined.",
            118,
            120,
        ),
    }
)
ADDED.update(
    {
        "04-federation-management-page-065-l100-25-eligible": (
            "04-federation-management-page-065-l100-25",
            "An optional federation-save timestamp may be supplied only if the joined federate is time-regulating or its GALT is defined.",
            100,
            104,
        ),
        "07-ownership-management-page-177-l110-35-next-advance": (
            "07-ownership-management-page-177-l110-35",
            "A federate advanced by Flush Queue Grant may request its next advance only to a logical time greater than or equal to its optimistic logical time.",
            129,
            136,
        ),
        "08-time-management-page-202-l107-29-olt": (
            "08-time-management-page-202-l107-29",
            "The optimistic logical time shall equal the minimum of the time supplied in Flush Queue Request and the timestamps of TSO messages delivered in response to that request.",
            110,
            118,
        ),
        "09-data-distribution-management-page-223-l40-13-available": (
            "09-data-distribution-management-page-223-l40-13",
            "A class attribute may be used in the listed subscribe, unsubscribe, publish, and unpublish service invocations for an object class if and only if it is an available attribute of that object class.",
            22,
            36,
        ),
    }
)

ADDED_SOURCE_PATHS = {
    "11-management-object-model-page-292-l117-38-composites": "content/clauses/11-management-object-model-page-293.tex",
}

_AUTHORED_REFINEMENT_IDS = {
    "requirement-source-refinement-object-state-completeness",
    "requirement-source-refinement-guard-and-cross-machine-state-constraints",
    "requirement-source-refinement-parallel-state-constraints",
    "requirement-source-refinement-save-admission-state-constraint",
}
AUTHORED_REFINEMENTS = {
    item.id: item.model_copy(
        update={
            "additional_sources": (
                SourceRef(
                    path="content/clauses/04-federation-management-page-042.tex",
                    line=4,
                    end_line=18,
                ),
            )
            if item.id == "requirement-source-refinement-save-admission-state-constraint"
            else (),
        }
    )
    for item in _source_refinement_requirements()
    if item.id in _AUTHORED_REFINEMENT_IDS
}

ADDITIONAL_SOURCES: dict[str, tuple[SourceRef, ...]] = {
    "08-time-management-page-181-l115-2": (
        SourceRef(path="content/clauses/08-time-management-page-181.tex", line=169, end_line=334),
    ),
    "08-time-management-page-181-l118-3": (
        SourceRef(path="content/clauses/08-time-management-page-181.tex", line=335, end_line=416),
    ),
    "07-ownership-management-page-162-l34-10": (
        SourceRef(
            path="content/clauses/07-ownership-management-page-162.tex", line=19, end_line=29
        ),
    ),
    "07-ownership-management-page-162-l43-13": (
        SourceRef(
            path="content/clauses/07-ownership-management-page-162.tex", line=19, end_line=29
        ),
    ),
    "07-ownership-management-page-162-l64-20": (
        SourceRef(
            path="content/clauses/07-ownership-management-page-162.tex", line=49, end_line=61
        ),
    ),
    "07-ownership-management-page-162-l76-24": (
        SourceRef(
            path="content/clauses/07-ownership-management-page-162.tex", line=49, end_line=61
        ),
    ),
    "10-support-services-page-288-l96-31": (
        SourceRef(path="content/clauses/10-support-services-page-289.tex", line=6, end_line=65),
    ),
    "04-federation-management-page-079-l158-43": (
        SourceRef(
            path="content/clauses/04-federation-management-page-080.tex", line=10, end_line=39
        ),
    ),
    "11-management-object-model-page-388-l4-1": (
        SourceRef(
            path="content/clauses/11-management-object-model-page-387.tex", line=215, end_line=225
        ),
    ),
    "10-support-services-page-285-l14-1": (
        SourceRef(path="content/clauses/10-support-services-page-284.tex", line=170, end_line=174),
    ),
    "11-management-object-model-page-293-l131-43": (
        SourceRef(
            path="content/clauses/11-management-object-model-page-294.tex", line=5, end_line=8
        ),
    ),
    "09-data-distribution-management-page-222-l98-31": (
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-223.tex", line=4, end_line=9
        ),
    ),
    "09-data-distribution-management-page-240-l9-1": (
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-239.tex",
            line=171,
            end_line=194,
        ),
    ),
    "07-ownership-management-page-156-l8-1": (
        SourceRef(
            path="content/clauses/07-ownership-management-page-155.tex", line=179, end_line=186
        ),
    ),
    "08-time-management-page-183-l4-1": (
        SourceRef(path="content/clauses/08-time-management-page-182.tex", line=130, end_line=140),
    ),
    "06-object-management-page-126-l179-50": (
        SourceRef(path="content/clauses/06-object-management-page-127.tex", line=7, end_line=10),
    ),
    "05-declaration-management-page-097-l191-54": (
        SourceRef(
            path="content/clauses/05-declaration-management-page-098.tex", line=8, end_line=10
        ),
    ),
    "05-declaration-management-page-082-l5-1": (
        SourceRef(
            path="content/clauses/05-declaration-management-page-081.tex", line=194, end_line=202
        ),
    ),
    "06-object-management-page-107-l141-42": (
        SourceRef(path="content/clauses/06-object-management-page-108.tex", line=8, end_line=31),
    ),
    "04-federation-management-page-058-l147-40": (
        SourceRef(path="content/clauses/04-federation-management-page-059.tex", line=8, end_line=8),
    ),
    "04-federation-management-page-061-l11-1": (
        SourceRef(
            path="content/clauses/04-federation-management-page-060.tex", line=139, end_line=139
        ),
    ),
    "04-federation-management-page-063-l12-1": (
        SourceRef(
            path="content/clauses/04-federation-management-page-062.tex", line=140, end_line=140
        ),
    ),
}

ADDED_ADDITIONAL_SOURCES: dict[str, tuple[SourceRef, ...]] = {
    "11-management-object-model-page-292-l117-38-composites": (
        SourceRef(
            path="content/clauses/11-management-object-model-page-292.tex", line=117, end_line=123
        ),
    ),
    "09-data-distribution-management-page-222-l23-6-unsubscribe-object": (
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-222.tex",
            line=65,
            end_line=67,
        ),
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-222.tex",
            line=80,
            end_line=87,
        ),
    ),
    "09-data-distribution-management-page-222-l23-6-subscribe-interaction": (
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-222.tex",
            line=71,
            end_line=73,
        ),
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-222.tex",
            line=80,
            end_line=87,
        ),
    ),
    "09-data-distribution-management-page-222-l23-6-unsubscribe-interaction": (
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-222.tex",
            line=77,
            end_line=79,
        ),
        SourceRef(
            path="content/clauses/09-data-distribution-management-page-222.tex",
            line=80,
            end_line=87,
        ),
    ),
    "04-federation-management-page-058-l112-33-actions": (
        SourceRef(
            path="content/clauses/04-federation-management-page-059.tex", line=16, end_line=59
        ),
    ),
    "04-federation-management-page-058-l147-40-assumption": ADDITIONAL_SOURCES[
        "04-federation-management-page-058-l147-40"
    ],
    "10-support-services-page-285-l14-1-true": ADDITIONAL_SOURCES[
        "10-support-services-page-285-l14-1"
    ],
    "10-support-services-page-285-l14-1-false": ADDITIONAL_SOURCES[
        "10-support-services-page-285-l14-1"
    ],
}

# List items keep a narrow primary span for canonical source order and the
# preceding list rule as an additional span for their inherited condition.
for stem, path, start, end in (
    ("01-overview-page-018-l58-7-", "01-overview-page-018", 58, 60),
    ("04-federation-management-page-047-l17-4-", "04-federation-management-page-047", 17, 22),
    ("05-declaration-management-page-081-l44-12-", "05-declaration-management-page-081", 38, 47),
    ("06-object-management-page-111-l25-6-", "06-object-management-page-111", 25, 27),
    ("07-ownership-management-page-150-l74-23-", "07-ownership-management-page-150", 74, 85),
    ("08-time-management-page-188-l69-21-", "08-time-management-page-188", 69, 71),
    ("11-management-object-model-page-291-l77-25-", "11-management-object-model-page-291", 77, 81),
    (
        "11-management-object-model-page-356-l326-108-",
        "11-management-object-model-page-356",
        324,
        329,
    ),
    ("11-management-object-model-page-357-l34-10-", "11-management-object-model-page-357", 31, 37),
    (
        "11-management-object-model-page-392-l232-75-",
        "11-management-object-model-page-392",
        232,
        234,
    ),
    (
        "12-programming-language-mappings-page-411-l20-6-",
        "12-programming-language-mappings-page-411",
        20,
        22,
    ),
    (
        "12-programming-language-mappings-page-412-l51-16-",
        "12-programming-language-mappings-page-412",
        48,
        52,
    ),
):
    for suffix in ADDED:
        if suffix.startswith(stem):
            ADDED_ADDITIONAL_SOURCES.setdefault(
                suffix,
                (SourceRef(path=f"content/clauses/{path}.tex", line=start, end_line=end),),
            )


def repair(root: Path) -> None:
    requirement_path = root / "semantic/requirements.json"
    binding_path = root / "semantic/api-requirement-bindings.json"
    requirements = RequirementFile.model_validate_json(requirement_path.read_text(encoding="utf-8"))
    bindings = RequirementApiBindingFile.model_validate_json(
        binding_path.read_text(encoding="utf-8")
    )
    existing_ids = {item.id for item in requirements.requirements}
    found: set[str] = set()
    sources = {}
    changed = []
    for requirement in requirements.requirements:
        if requirement.id == MERGED_DISCONNECT_CANDIDATE:
            continue  # The authored transition record carries this same printed rule.
        if requirement.id == MERGED_DISCONNECT_REQUIREMENT:
            source = requirement.source.model_copy(update={"line": 51, "end_line": 56})
            changed.append(requirement.model_copy(update={"source": source}))
            sources[requirement.id] = source
            continue
        if requirement.id in AUTHORED_REFINEMENTS:
            repaired = AUTHORED_REFINEMENTS[requirement.id]
            changed.append(repaired)
            sources[requirement.id] = repaired.source
            continue
        suffix = requirement.id.removeprefix(PREFIX)
        if requirement.id.startswith(PREFIX) and suffix in ADDED:
            _, statement, start, end = ADDED[suffix]
            source = requirement.source.model_copy(
                update={
                    "path": ADDED_SOURCE_PATHS.get(suffix, requirement.source.path),
                    "line": start,
                    "end_line": end,
                }
            )
            changed.append(
                requirement.model_copy(
                    update={
                        "statement": statement,
                        "machine_statement": _machine_statement(statement, HLA_SOURCE),
                        "source": source,
                        "additional_sources": ADDED_ADDITIONAL_SOURCES.get(
                            suffix, requirement.additional_sources
                        ),
                    }
                )
            )
            sources[requirement.id] = source
            continue
        if not requirement.id.startswith(PREFIX) or suffix not in REPAIRS:
            changed.append(requirement)
            continue
        statement, start, end = REPAIRS[suffix]
        source = requirement.source.model_copy(update={"line": start, "end_line": end})
        changed.append(
            requirement.model_copy(
                update={
                    "statement": statement,
                    "machine_statement": _machine_statement(statement, HLA_SOURCE),
                    "source": source,
                    "additional_sources": ADDITIONAL_SOURCES.get(
                        suffix, requirement.additional_sources
                    ),
                    "extraction": "candidate"
                    if requirement.id in TABLE_POINTER_CANDIDATES
                    else requirement.extraction,
                    "coverage_note": (
                        f"Explanatory pointer to {TABLE_POINTER_CANDIDATES[requirement.id]}; the table is preserved as a separate source-backed record."
                        if requirement.id in TABLE_POINTER_CANDIDATES
                        else requirement.coverage_note
                    ),
                }
            )
        )
        found.add(suffix)
        sources[requirement.id] = source
        for new_suffix, (base_suffix, new_statement, new_start, new_end) in ADDED.items():
            if suffix != base_suffix or PREFIX + new_suffix in existing_ids:
                continue
            new_source = source.model_copy(
                update={
                    "path": ADDED_SOURCE_PATHS.get(new_suffix, source.path),
                    "line": new_start,
                    "end_line": new_end,
                }
            )
            changed.append(
                requirement.model_copy(
                    update={
                        "id": PREFIX + new_suffix,
                        "title": f"Normative statement at {new_source.path}:{new_source.line}",
                        "statement": new_statement,
                        "machine_statement": _machine_statement(new_statement, HLA_SOURCE),
                        "source": new_source,
                        "semantic_group_id": requirement.semantic_group_id,
                        "additional_sources": ADDED_ADDITIONAL_SOURCES.get(new_suffix, ()),
                    }
                )
            )
            sources[PREFIX + new_suffix] = new_source
    if found != REPAIRS.keys():
        raise ValueError(f"Missing reviewed fragments: {sorted(REPAIRS.keys() - found)}")
    for identifier, item in AUTHORED_REFINEMENTS.items():
        if identifier not in existing_ids:
            changed.append(item)
            sources[identifier] = item.source
    changed = [
        item.model_copy(update={"title": _semantic_title(item.statement)})
        if item.id.startswith(PREFIX)
        else item
        for item in changed
    ]
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
    review_path = root / "semantic/requirement-review.json"
    reviews = json.loads(review_path.read_text(encoding="utf-8"))
    reviews["reviews"] = [
        {
            "requirement_id": identifier,
            "status": "non-normative",
            "reason": f"{label} introduction explains the adjacent table; its normative cases remain in the table record.",
            "source": next(
                item.source.model_dump(mode="json") for item in changed if item.id == identifier
            ),
        }
        for identifier, label in TABLE_POINTER_CANDIDATES.items()
    ]
    review_path.write_text(
        json.dumps(reviews, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    content_path = root / "semantic/content-blocks.json"
    content = json.loads(content_path.read_text(encoding="utf-8"))
    for block in content["content_blocks"]:
        if MERGED_DISCONNECT_CANDIDATE in block["record_ids"]:
            block["record_ids"].remove(MERGED_DISCONNECT_CANDIDATE)
        for identifier, item in AUTHORED_REFINEMENTS.items():
            if (
                block["source"]["path"] == item.source.path
                and identifier not in block["record_ids"]
            ):
                block["record_ids"].append(identifier)
        for new_suffix, (base_suffix, _, _, _) in ADDED.items():
            new_id = PREFIX + new_suffix
            owner_path = ADDED_SOURCE_PATHS.get(new_suffix)
            owns_new = (
                block["source"]["path"] == owner_path
                if owner_path is not None
                else PREFIX + base_suffix in block["record_ids"]
            )
            if owns_new and new_id not in block["record_ids"]:
                block["record_ids"].append(new_id)
    content_path.write_text(
        json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    element_path = root / "semantic/content-elements.json"
    elements = json.loads(element_path.read_text(encoding="utf-8"))
    for element in elements["content_elements"]:
        if MERGED_DISCONNECT_CANDIDATE in element["record_ids"]:
            element["record_ids"].remove(MERGED_DISCONNECT_CANDIDATE)
    element_path.write_text(
        json.dumps(elements, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    alias_path = root / "semantic/requirement-id-aliases.json"
    aliases = json.loads(alias_path.read_text(encoding="utf-8"))
    aliases["aliases"] = [
        item for item in aliases["aliases"] if item["alias_id"] != MERGED_DISCONNECT_CANDIDATE
    ] + [
        {
            "alias_id": MERGED_DISCONNECT_CANDIDATE,
            "canonical_id": MERGED_DISCONNECT_REQUIREMENT,
            "relation": "merged",
            "reason": "Exact duplicate of the authored Disconnect transition requirement; its full printed sentence is retained by the canonical record.",
        }
    ]
    alias_path.write_text(
        json.dumps(aliases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    changed_bindings = [
        binding.model_copy(update={"source": sources[binding.requirement_id]})
        if binding.requirement_id in sources
        else binding
        for binding in bindings.bindings
        if binding.requirement_id != MERGED_DISCONNECT_CANDIDATE
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
    print(f"Repaired {len(found)} reviewed source fragments")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    repair(document_root("hla-1516.1-2025", args.workspace_root))


if __name__ == "__main__":
    main()
