"""Reviewed semantic corrections returned from HLA implementation work."""

from __future__ import annotations

import json
import re
import unittest
from collections import Counter
from pathlib import Path

from hla_lab.core.json_types import JsonObject
from hla_lab.core.semantic_model import ContentBlockFile
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
SEMANTIC = ROOT / "topics/ieee/hla-1516.1-2025/semantic"


def _read(name: str) -> JsonObject:
    return json.loads((SEMANTIC / name).read_text(encoding="utf-8"))


def _layout_by_source(path: Path) -> dict[str, list[str]]:
    payload = ContentBlockFile.model_validate_json(path.read_text(encoding="utf-8"))
    return {
        item.source.path: item.layout_body.splitlines()
        for item in payload.content_blocks
        if item.layout_body is not None
    }


class HlaBackflowTests(unittest.TestCase):
    def test_source_page_clause_owners_for_umbra_tck(self) -> None:
        expected = {
            "hla-1516.1-2025": {
                "043-l65-19": "4.1.2",
                "094-l111-29": "5.6",
                "094-l117-31": "5.6",
                "094-l123-33": "5.6",
                "095-l17-2": "5.6.4",
                "095-l74-19": "5.7",
                "095-l83-22": "5.7",
                "095-l86-23": "5.7",
                "095-l89-24": "5.7",
                "190-l64-15": "8.3.4",
                "190-l67-16": "8.3.4",
                "190-l76-19": "8.3.4",
                "190-l103-25": "8.4",
                "190-l106-26": "8.4",
            },
            "hla-1516.2-2025": {
                "110-l6-1": "C.2",
                "110-l18-4": "C.2",
                "110-l22-5": "C.2",
                "110-l26-6": "C.2",
                "110-l30-7": "C.2",
                "111-l6-1": "C.3",
            },
        }
        for document_id, owners in expected.items():
            records = json.loads(
                (
                    ROOT / "topics" / "ieee" / document_id / "semantic" / "requirements.json"
                ).read_text(encoding="utf-8")
            )["requirements"]
            for suffix, clause in owners.items():
                with self.subTest(document=document_id, source=suffix):
                    record = next(item for item in records if item["id"].endswith(suffix))
                    self.assertEqual(record["clause"], clause)
                    self.assertEqual(record["clause_id"], f"clause-{clause}")

    def test_corrected_candidates_have_complete_statement_boundaries(self) -> None:
        issues = json.loads(
            (ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
        )["issues"]
        catalogs = {
            document_id: {
                item["id"]: item
                for item in json.loads(
                    (
                        ROOT / "topics" / "ieee" / document_id / "semantic" / "requirements.json"
                    ).read_text(encoding="utf-8")
                )["requirements"]
            }
            for document_id in {
                issue["document_id"]
                for issue in issues
                if issue["resolution"] == "corrected-in-lab"
            }
        }
        layouts = {
            document_id: _layout_by_source(
                ROOT / "topics" / "ieee" / document_id / "semantic" / "content-blocks.json"
            )
            for document_id in catalogs
        }
        lower_case_table_fields = {
            "requirement-candidate-table-5-p296-r004",
            "requirement-candidate-table-5-p296-r005",
            "requirement-candidate-table-5-p296-r037",
            "requirement-candidate-table-5-p297-r004",
            "requirement-candidate-table-5-p297-r005",
            "requirement-candidate-table-5-p297-r006",
        }
        for issue in issues:
            if issue["resolution"] != "corrected-in-lab":
                continue
            for requirement_id in issue["affected_requirement_ids"]:
                with self.subTest(issue=issue["id"], requirement=requirement_id):
                    record = catalogs[issue["document_id"]][requirement_id]
                    statement = record["statement"]
                    self.assertTrue(statement)
                    self.assertEqual(statement, record["machine_statement"])
                    self.assertTrue(statement.endswith((".", ":", ".”")), statement)
                    if requirement_id not in lower_case_table_fields:
                        self.assertTrue(statement[0].isupper(), statement)
                    source = record["source"]
                    self.assertLessEqual(source["line"], source["end_line"])
                    self.assertIn(source["path"], layouts[issue["document_id"]])
                    self.assertLess(
                        source["end_line"],
                        len(layouts[issue["document_id"]][source["path"]]),
                    )

    def test_split_service_names_keep_the_full_condition(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        witnesses = {
            "requirement-candidate-content-clauses-07-ownership-management-page-153-l75-24": (
                "A joined federate that has invoked the Attribute Ownership Acquisition service",
                "shall not invoke the Attribute Ownership Acquisition If Available service",
            ),
            "requirement-candidate-content-clauses-08-time-management-page-203-l113-31": (
                "If the grant is in response to an invocation of a Time Advance Request Available",
                "timestamps less than the value of the grant",
            ),
            "requirement-candidate-content-clauses-08-time-management-page-204-l86-25": (
                "If this service is invoked in response to a Time Advance Request Available",
                "timestamps less than the supplied logical time",
            ),
        }
        for requirement_id, phrases in witnesses.items():
            with self.subTest(requirement=requirement_id):
                statement = by_id[requirement_id]["statement"]
                self.assertTrue(all(phrase in statement for phrase in phrases), statement)

    def test_snapshot_keeps_every_reported_issue(self) -> None:
        payload = json.loads(
            (ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
        )
        issue_ids = [item["id"] for item in payload["issues"]]
        expected_ids = {
            line.strip()
            for line in (ROOT / "data/hla-open-issue-ids-2026-10-24.txt")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip() and not line.startswith("#")
        }
        self.assertEqual(len(expected_ids), 89)
        self.assertEqual(len(issue_ids), len(expected_ids))
        self.assertEqual(set(issue_ids), expected_ids)
        self.assertEqual(
            Counter(item["resolution"] for item in payload["issues"]),
            {
                "corrected-in-lab": 84,
                "verified-in-umbra": 4,
                "source-conflict-dispositioned": 1,
            },
        )
        self.assertTrue(all(item["verification"] for item in payload["issues"]))
        catalogs: dict[str, set[str]] = {}
        for issue in payload["issues"]:
            document_id = issue["document_id"]
            if document_id not in catalogs:
                path = ROOT / "topics" / "ieee" / document_id / "semantic" / "requirements.json"
                catalogs[document_id] = {
                    item["id"]
                    for item in json.loads(path.read_text(encoding="utf-8"))["requirements"]
                }
            affected_ids = issue["affected_requirement_ids"]
            with self.subTest(issue=issue["id"]):
                self.assertEqual(len(affected_ids), issue["candidate_records"])
                self.assertTrue(set(affected_ids) <= catalogs[document_id])
                if issue["resolution"] != "verified-in-umbra":
                    test_names = re.findall(
                        r"tests/test_hla_backflow\.py::HlaBackflowTests::(test_[A-Za-z0-9_]+)",
                        issue["verification"],
                    )
                    self.assertTrue(test_names)
                    self.assertTrue(all(hasattr(type(self), name) for name in test_names))

    def test_every_clause_complaint_has_reviewed_attribution(self) -> None:
        # Reviewed against the visible page headings. The originating ledger is
        # broader or disagrees with those headings for RL-248, RL-265, RL-341,
        # RL-343, and RL-357; their dispositions remain in the snapshot notes.
        uniform = {
            "RL-177": "6.17.4",
            "RL-248": "9.9.3",
            "RL-259": "8.1.8",
            "RL-265": "11.2.1",
            "RL-267": "4.20",
            "RL-317": "6.11",
            "RL-323": "10.59.4",
            "RL-324": "6.25",
            "RL-325": "6.26",
            "RL-329": "7.10",
            "RL-330": "8.1.3",
            "RL-341": "9.5",
            "RL-342": "4.1.2",
            "RL-343": "8.14.4",
            "RL-344": "4.15",
            "RL-345": "9.1.7",
            "RL-347": "4.1.2",
            "RL-348": "4.11",
            "RL-349": "8.13",
            "RL-350": "8.1.5",
            "RL-351": "8.1.5",
            "RL-352": "8.1.6",
            "RL-356": "8.1.1",
            "RL-357": "4.8.1",
            "RL-360": "9.1.3.2",
            "RL-362": "8.6",
            "RL-370": "8.1.4",
            "RL-380": "9.1.1",
            "RL-384": "6.29",
            "RL-385": "8.5",
        }
        mixed = {
            "RL-328": (
                "5.1.3",
                "6.12",
                "6.12",
                "6.12",
                "8.5",
                "8.6",
                "8.8",
                "8.8",
                "8.17",
                "8.19",
                "10.59.4",
            ),
            "RL-331": ("7.1.2.2",) * 6 + ("7.1.3",) * 6,
            "RL-339": ("8.13.4", "8.13.4", "8.14", "8.14", "8.14"),
            "RL-340": ("9.5.3", "9.6.3"),
            "RL-346": ("8.6.4", "8.6.4", "8.7"),
        }
        issues = [
            item
            for item in json.loads(
                (ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
            )["issues"]
            if item["category"] == "Clause, subsection, and source-boundary attribution"
        ]
        self.assertEqual({item["id"] for item in issues}, set(uniform) | set(mixed))
        catalogs = {
            document_id: {
                item["id"]: item
                for item in json.loads(
                    (
                        ROOT / "topics" / "ieee" / document_id / "semantic" / "requirements.json"
                    ).read_text(encoding="utf-8")
                )["requirements"]
            }
            for document_id in {item["document_id"] for item in issues}
        }
        for issue in issues:
            requirement_ids = issue["affected_requirement_ids"]
            expected = mixed.get(issue["id"])
            if expected is None:
                expected = (uniform[issue["id"]],) * len(requirement_ids)
            self.assertEqual(len(expected), len(requirement_ids))
            for requirement_id, clause in zip(requirement_ids, expected, strict=True):
                with self.subTest(issue=issue["id"], requirement=requirement_id):
                    record = catalogs[issue["document_id"]][requirement_id]
                    self.assertEqual(record["clause"], clause)
                    self.assertEqual(record["clause_id"], f"clause-{clause}")

    def test_every_fragment_complaint_retains_its_missing_rule(self) -> None:
        # These witnesses name the substantive rule that the original candidate
        # clipped or conflated; punctuation and provenance are checked for every
        # affected record, including the other-document Annex C issue.
        witnesses = {
            "RL-249": ("Interaction I", "subscribed to either the sent class"),
            "RL-250": ("subscribed interaction class", "at most once"),
            "RL-251": (
                "Register Object Instance, Send Interaction, and Request Attribute Value Update",
            ),
            "RL-258": ("federation execution creation time", "not be modifiable"),
            "RL-263": ("shall not contain the new parameters",),
            "RL-264": ("neither sent nor received", "ignored by the RTI"),
            "RL-309": (
                "unowned by all joined federates",
                "Attribute Ownership Acquisition Notification",
            ),
            "RL-310": ("HLAmodifyAttributeState", "HLAresignFederationExecution"),
            "RL-311": ("requesting to divest", "instance attribute"),
            "RL-313": ("before granting", "request for time advancement"),
            "RL-314": ("service report log records",),
            "RL-315": ("Federation Saved service", "save-success indicator"),
            "RL-316": ("all messages queued", "timestamps equal to the specified logical time"),
            "RL-318": ("discovery of instantiated object instances", "analogously"),
            "RL-319": ("merge shall also fail",),
            "RL-320": (
                "abort the reservation of all names",
                "Multiple Object Instance Name Reserved",
            ),
            "RL-326": ("Time Advancing state",),
            "RL-327": ("timestamp of the scheduled save",),
            "RL-332": ("Delete Object Instance service invocation",),
            "RL-333": ("current logical time",),
            "RL-334": ("smallest possible logical time",),
            "RL-335": ("Time Advance Grant service invocation", "no TSO messages"),
            "RL-337": ("optimistic logical time", "GALT"),
            "RL-359": ("Invalid region", "all of its dimensions"),
            "RL-361": ("subset of the available dimensions", "default region"),
            "RL-373": ("Federate Resigned service",),
            "RL-374": ("Change Default Attribute Order Type service",),
            "RL-375": ("Unconditional Attribute Ownership Divestiture service",),
            "RL-376": ("Request Divestiture Confirmation", "remain pending"),
            "RL-377": ("exclusive", "Upon registration of an object instance"),
            "RL-378": ("optimistic logical time argument", "message delivery"),
            "RL-379": ("dimensions contained in a region specification",),
            "RL-381": (
                "continuous semi-open interval",
                "range upper bound shall be strictly greater",
            ),
            "RL-382": ("federation save label",),
            "RL-383": ("perform a Disconnect",),
            "RL-386": ("lookahead is zero",),
        }
        issues = [
            item
            for item in json.loads(
                (ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
            )["issues"]
            if item["category"] == "Incomplete, fragmented, or corrupted candidate text"
        ]
        self.assertEqual({item["id"] for item in issues}, set(witnesses))
        catalogs = {
            document_id: {
                item["id"]: item
                for item in json.loads(
                    (
                        ROOT / "topics" / "ieee" / document_id / "semantic" / "requirements.json"
                    ).read_text(encoding="utf-8")
                )["requirements"]
            }
            for document_id in {item["document_id"] for item in issues}
        }
        for issue in issues:
            records = [
                catalogs[issue["document_id"]][requirement_id]
                for requirement_id in issue["affected_requirement_ids"]
            ]
            joined = " ".join(record["statement"] for record in records)
            for witness in witnesses[issue["id"]]:
                with self.subTest(issue=issue["id"], witness=witness):
                    self.assertIn(witness, joined)
            for record in records:
                with self.subTest(issue=issue["id"], requirement=record["id"]):
                    statement = record["statement"]
                    self.assertTrue(statement.endswith((".", ":", ".”")))
                    self.assertEqual(record["machine_statement"], statement)
                    self.assertGreaterEqual(record["source"]["end_line"], record["source"]["line"])
                    self.assertNotIn("t7.98pt", statement)
                    self.assertNotIn(r"\HLAFixedBlock", statement)

    def test_page_216_ddm_ownership_and_definitions(self) -> None:
        blocks = [
            item
            for item in _read("content-blocks.json")["content_blocks"]
            if item["id"] == "content-15161-page-216"
        ]
        elements = [
            item
            for item in _read("content-elements.json")["content_elements"]
            if item["id"] == "content-element-content-15161-page-216-paragraph-001"
        ]
        self.assertEqual(blocks[0]["clause_id"], "clause-9")
        self.assertEqual(elements[0]["clause_id"], "clause-9")

        page = {
            item["id"].rsplit("-l", 1)[-1]: item
            for item in _read("requirements.json")["requirements"]
            if "page-216-l" in item["id"]
        }
        self.assertTrue(page)
        self.assertTrue(all(item["clause_id"] == "clause-9.1.1" for item in page.values()))
        self.assertEqual(
            {
                suffix
                for suffix, item in page.items()
                if item["semantic_group_id"] == "m16.range-definition.9.1.1"
            },
            {"66-19", "69-20", "72-21", "78-23"},
        )
        self.assertEqual(
            page["78-23"]["statement"],
            "The minimum possible difference between a range lower bound and a range upper bound "
            "shall be 1 (one).",
        )
        self.assertIn("second component", page["69-20"]["statement"])
        self.assertIn("dimensions contained", page["87-26"]["statement"])
        for suffix in ("66-19", "69-20", "72-21", "78-23"):
            with self.subTest(range_facet=suffix):
                note = page[suffix]["coverage_note"]
                self.assertIn("range definition", note)
                self.assertIn("all four consecutive stable candidate IDs", note)
        self.assertTrue(
            all(
                item["statement"].endswith((".", ":"))
                for suffix, item in page.items()
                if suffix
                in {"66-19", "69-20", "72-21", "78-23", "84-25", "87-26", "90-27", "93-28"}
            )
        )

    def test_page_219_region_rules_precede_instance_attribute_heading(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        expected = {
            "11-3": ("A region specification", "associated.", 8),
            "23-7": ("A region specification", "default region.", 17),
            "50-16": ("If a federate invokes", "all of its dimensions.", 42),
            "62-20": ("The effects", "for that region.", 59),
            "86-28": ("If a federate invokes", "for that region.", 74),
        }
        for suffix, (opening, ending, source_line) in expected.items():
            record = next(item for key, item in by_id.items() if f"page-219-l{suffix}" in key)
            with self.subTest(requirement=suffix):
                self.assertEqual(record["clause"], "9.1.3.1")
                self.assertEqual(record["clause_id"], "clause-9.1.3.1")
                self.assertEqual(record["semantic_group_id"], "m16.clause.9.1.3.1")
                self.assertTrue(record["statement"].startswith(opening))
                self.assertTrue(record["statement"].endswith(ending))
                self.assertEqual(record["machine_statement"], record["statement"])
                self.assertEqual(record["source"]["line"], source_line)
        invalid_region = next(item for key, item in by_id.items() if "page-219-l50-16" in key)
        pending_effects = next(item for key, item in by_id.items() if "page-219-l62-20" in key)
        self.assertIn("Invalid region", invalid_region["statement"])
        self.assertNotIn("still pending", invalid_region["statement"])
        self.assertIn("still pending", pending_effects["statement"])

    def test_missing_service_flow_items_have_source_and_direct_api_bindings(self) -> None:
        requirements = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        bindings = _read("api-requirement-bindings.json")["bindings"]
        api_surfaces = {item["id"]: item for item in _read("api-surfaces.json")["api_surfaces"]}
        required_pages = {
            "content-15161-page-199",
            "content-15161-page-200",
            "content-15161-page-260",
        }
        page_layouts = {
            item["id"]: item["layout_body"].splitlines()
            for item in _read("content-blocks.json")["content_blocks"]
            if item["id"] in required_pages
        }
        cases = {
            "requirement-service-flow-nmra-current-time-precondition": (
                "8.11.3",
                "199",
                "nextmessagerequestavailable",
                145,
                147,
                "greater than or equal to",
                "greater than or equal to",
                "LogicalTimeAlreadyPassed",
            ),
            "requirement-service-flow-nmra-time-passed-exception": (
                "8.11.5",
                "200",
                "nextmessagerequestavailable",
                62,
                62,
                "Logical time has already passed",
                "Logical Time Already Passed",
                "LogicalTimeAlreadyPassed",
            ),
            "requirement-service-flow-nmra-not-advancing-precondition": (
                "8.11.3",
                "200",
                "nextmessagerequestavailable",
                11,
                11,
                "not in the Time Advancing state",
                "must not be in the Time Advancing state",
                "InTimeAdvancingState",
            ),
            "requirement-service-flow-nmra-advancing-exception": (
                "8.11.5",
                "200",
                "nextmessagerequestavailable",
                74,
                74,
                "Joined federate in Time Advancing state",
                "Joined Federate in Time Advancing State",
                "InTimeAdvancingState",
            ),
            "requirement-service-flow-get-dimension-handle-name-not-found": (
                "10.23.5",
                "260",
                "getdimensionhandle",
                35,
                35,
                "dimension is not defined in the FDD",
                "NameNotFound",
                "NameNotFound",
            ),
        }
        for requirement_id, (
            clause,
            page,
            api_name,
            line,
            end_line,
            source_witness,
            statement_witness,
            exception_name,
        ) in cases.items():
            with self.subTest(requirement=requirement_id):
                record = requirements[requirement_id]
                self.assertEqual(record["clause"], clause)
                self.assertEqual(record["machine_statement"], record["statement"])
                self.assertIn(f"page-{page}.tex", record["source"]["path"])
                self.assertEqual(record["source"]["line"], line)
                self.assertEqual(record["source"]["end_line"], end_line)
                self.assertIn(
                    source_witness,
                    page_layouts[f"content-15161-page-{page}"][line],
                )
                self.assertIn(statement_witness, record["statement"])
                self.assertTrue(record["statement"].endswith("."))
                matching = [
                    item
                    for item in bindings
                    if item["requirement_id"] == requirement_id
                    and item["status"] == "matched"
                    and item["relationship"] == "direct"
                ]
                self.assertTrue(matching)
                self.assertTrue(any(api_name in item["api_surface_id"] for item in matching))
                self.assertTrue(
                    any(
                        exception_name in api_surfaces[item["api_surface_id"]]["exception_types"]
                        for item in matching
                    )
                )
        issues = {
            item["id"]: item
            for item in json.loads(
                (ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
            )["issues"]
        }
        created_by_issue = {
            "RL-253": ("requirement-service-flow-get-dimension-handle-name-not-found",),
            "RL-321": (
                "requirement-service-flow-nmra-current-time-precondition",
                "requirement-service-flow-nmra-time-passed-exception",
            ),
            "RL-322": (
                "requirement-service-flow-nmra-not-advancing-precondition",
                "requirement-service-flow-nmra-advancing-exception",
            ),
        }
        for issue_id, created_ids in created_by_issue.items():
            with self.subTest(issue=issue_id):
                self.assertEqual(issues[issue_id]["created_requirement_ids"], list(created_ids))
                self.assertTrue(set(created_ids) <= requirements.keys())

    def test_service_boundaries_follow_visible_headings(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        cases = {
            "04-federation-management-page-040-l33-8": ("4.1.1", "If a federate is forced"),
            "req-federate-disconnect-after-resign": ("4.1.1", "When a federate"),
            "04-federation-management-page-044-l15-4": ("4.1.2", "When a joined federate"),
            "04-federation-management-page-044-l27-8": ("4.1.2", "Once a federation"),
            "04-federation-management-page-044-l36-11": ("4.1.2", "All saved information"),
            "04-federation-management-page-044-l54-17": ("4.1.2", "Once a restore"),
            "04-federation-management-page-044-l72-23": ("4.1.2", "The number of federates"),
            "04-federation-management-page-044-l78-25": ("4.1.2", "Declaring a federate"),
            "04-federation-management-page-044-l108-35": ("4.1.3", "The RTI shall"),
            "06-object-management-page-143-l156-42": ("6.29", "The Report Attribute"),
            "06-object-management-page-143-l162-44": ("6.29", "If the instance"),
            "08-time-management-page-191-l73-17": ("8.5", "The Enable Time"),
            "08-time-management-page-191-l76-18": ("8.5", "The RTI shall"),
        }
        for suffix, (clause, opening) in cases.items():
            record = next(item for key, item in by_id.items() if key.endswith(suffix))
            with self.subTest(requirement=suffix):
                self.assertEqual(record["clause"], clause)
                self.assertTrue(record["statement"].startswith(opening))
                self.assertTrue(record["statement"].endswith("."))
                self.assertEqual(record["machine_statement"], record["statement"])

        # The page-44 bookmark anticipates the later heading. Its save and
        # restore prose visibly precedes §4.1.3 and continues §4.1.2 from p.43.
        body = next(
            item["layout_body"]
            for item in _read("content-blocks.json")["content_blocks"]
            if item["id"] == "content-15161-page-044"
        )
        self.assertLess(
            body.index("When a joined federate receives"),
            body.index(r"\textbf{4.1.3 Synchronization discussion}"),
        )

    def test_reviewed_clause_boundary_repairs(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        expected = {
            "page-067-l37-8": "4.20",
            "page-122-l61-17": "6.11",
            "page-122-l79-23": "6.11",
            "page-132-l107-30": "6.17.4",
            "page-132-l113-32": "6.17.4",
            "page-139-l150-40": "6.25",
            "page-141-l11-1": "6.26",
            "page-165-l14-1": "7.10",
            "page-187-l16-3": "8.1.8",
            "page-187-l22-5": "8.1.8",
            "page-236-l32-9": "9.9.3",
            "page-286-l20-3": "10.59.4",
            "page-288-l9-2": "11.2.1",
        }
        for suffix, clause in expected.items():
            record = next(item for key, item in by_id.items() if suffix in key)
            with self.subTest(requirement=suffix):
                self.assertEqual(record["clause"], clause)
                self.assertEqual(record["clause_id"], f"clause-{clause}")
                self.assertTrue(record["statement"].endswith("."))
        self.assertIn(
            "Time Advancing state",
            next(item["statement"] for key, item in by_id.items() if "page-067-l37-8" in key),
        )
        self.assertIn(
            "specified time",
            next(item["statement"] for key, item in by_id.items() if "page-132-l107-30" in key),
        )

    def test_cross_page_service_attribution(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        expected = {
            "page-057-l32-5": "4.11",
            "page-062-l28-6": "4.15",
            "page-084-l32-10": "5.1.3",
            "page-124-l41-12": "6.12",
            "page-153-l15-4": "7.1.2.2",
            "page-153-l84-26": "7.1.3",
            "page-180-l27-7": "8.1.3",
            "page-181-l148-13": "8.1.4",
            "page-182-l73-23": "8.1.5",
            "page-182-l100-31": "8.1.6",
            "page-192-l63-17": "8.6",
            "page-193-l31-6": "8.6.4",
            "page-193-l58-12": "8.7",
            "page-194-l27-5": "8.8",
            "page-202-l104-28": "8.13",
            "page-203-l47-12": "8.13.4",
            "page-203-l95-25": "8.14",
            "page-204-l74-21": "8.14.4",
            "page-206-l29-4": "8.17",
            "page-207-l112-28": "8.19",
            "page-225-l96-30": "9.1.7",
            "page-229-l20-5": "9.5",
            "page-229-l146-44": "9.5.3",
            "page-231-l100-28": "9.6.3",
        }
        for suffix, clause in expected.items():
            record = next(item for key, item in by_id.items() if suffix in key)
            with self.subTest(requirement=suffix):
                self.assertEqual(record["clause"], clause)
        self.assertEqual(
            next(item["statement"] for key, item in by_id.items() if "page-229-l20-5" in key),
            "If the joined federate subsequently acquires ownership of that instance "
            "attribute, the original association shall not be restored.",
        )

    def test_fragmented_obligations_have_complete_oracles(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        checks = {
            "page-069-l64-15": ("The Federation Saved service", "complete."),
            "page-069-l67-16": ("The Federation Saved service", "successfully."),
            "page-069-l70-17": ("A save-success indicator", "success."),
            "page-178-l93-28": ("The Flush Queue Grant service", "future."),
            "page-178-l108-33": ("The guarantee that the RTI", "descriptions."),
            "page-224-l89-29": ("The Receive Interaction service", "argument."),
            "page-224-l92-30": ("An interaction shall", "service."),
            "page-224-l137-44": ("A joined federate using DDM", "respectively."),
        }
        for suffix, (opening, ending) in checks.items():
            record = next(item for key, item in by_id.items() if suffix in key)
            with self.subTest(requirement=suffix):
                self.assertTrue(record["statement"].startswith(opening))
                self.assertTrue(record["statement"].endswith(ending))
                self.assertGreater(record["source"]["end_line"], record["source"]["line"])
        self.assertIn(
            "Request Attribute Value Update With Regions",
            next(item["statement"] for key, item in by_id.items() if "page-224-l137-44" in key),
        )

    def test_time_and_ddm_continuations(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        for suffix in ("page-175-l131-40", "page-175-l140-43", "page-175-l146-45"):
            item = next(item for key, item in by_id.items() if suffix in key)
            self.assertEqual(item["clause"], "8.1.1")
            self.assertTrue(item["statement"].endswith("."))
        for suffix in (
            "page-192-l63-17",
            "page-192-l66-18",
            "page-192-l69-19",
            "page-192-l72-20",
            "page-192-l78-22",
            "page-192-l84-24",
            "page-192-l93-27",
            "page-192-l99-29",
        ):
            item = next(item for key, item in by_id.items() if suffix in key)
            self.assertEqual(item["clause"], "8.6")
            self.assertTrue(item["statement"].endswith("."))
        tso = next(item for key, item in by_id.items() if "page-192-l93-27" in key)
        ro = next(item for key, item in by_id.items() if "page-192-l99-29" in key)
        self.assertTrue(tso["statement"].startswith("When a joined federate changes"))
        self.assertIn("shall be delivered in TSO.", tso["statement"])
        self.assertTrue(ro["statement"].startswith("TSO messages delivered"))
        self.assertIn("shall be delivered as RO messages.", ro["statement"])
        self.assertEqual((tso["source"]["line"], tso["source"]["end_line"]), (90, 95))
        self.assertEqual((ro["source"]["line"], ro["source"]["end_line"]), (96, 104))
        page_192 = next(
            item["layout_body"].splitlines()
            for item in _read("content-blocks.json")["content_blocks"]
            if item["id"] == "content-15161-page-192"
        )
        self.assertIn("When a joined federate changes", page_192[tso["source"]["line"]])
        self.assertIn("TSO messages delivered", page_192[ro["source"]["line"]])
        object_attributes = [
            item
            for key, item in by_id.items()
            if "page-220-l" in key and item["source"]["line"] < 122
        ]
        self.assertEqual(len(object_attributes), 17)
        self.assertTrue(all(item["clause"] == "9.1.3.2" for item in object_attributes))

        omt = json.loads(
            (ROOT / "topics/ieee/hla-1516.2-2025/semantic/requirements.json").read_text(
                encoding="utf-8"
            )
        )
        record = next(
            item
            for item in omt["requirements"]
            if item["id"] == "requirement-candidate-sections-semantic-clause-4b-page-058-l34-8"
        )
        self.assertEqual(record["clause"], "4.8.1")
        self.assertIn("HLAinteger64Time and HLAfloat64Time", record["statement"])
        self.assertIn("These types shall be provided by all RTIs.", record["statement"])
        self.assertEqual((record["source"]["line"], record["source"]["end_line"]), (33, 33))
        omt_blocks = json.loads(
            (ROOT / "topics/ieee/hla-1516.2-2025/semantic/content-blocks.json").read_text(
                encoding="utf-8"
            )
        )["content_blocks"]
        page_58 = next(item for item in omt_blocks if item["id"] == "content-15162-page-058")
        self.assertIn(
            "Two time representations",
            page_58["layout_body"].splitlines()[record["source"]["line"]],
        )

    def test_local_fragment_reconstruction(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        checks = {
            "page-290-l12-3": ("11.3.1", "Parameters may be added", "parameters."),
            "page-290-l75-24": ("11.3.1", "Classes of interaction", "RTI."),
            "page-290-l78-25": ("11.3.1", "These classes of interaction", "development."),
            "page-178-l51-14": ("8.1.2", "The third column", "advancement."),
            "page-178-l54-15": ("8.1.2", "Only messages", "advancement."),
            "page-294-l14-4": ("11.5.2.1", "The same JSON", "records."),
            "page-294-l17-5": ("11.5.2.1", "Each service report", "records."),
            "page-180-l93-28": ("8.1.4", "In the case", "instance."),
            "page-197-l98-29": ("8.10", "A Time Advance Grant", "delivered."),
            "page-197-l104-31": ("8.10", "The Time Advance Grant", "grant."),
            "page-150-l152-47": ("7.1.2.1", "The joined federate", "federates."),
        }
        for suffix, (clause, opening, ending) in checks.items():
            record = next(item for key, item in by_id.items() if suffix in key)
            with self.subTest(requirement=suffix):
                self.assertEqual(record["clause"], clause)
                self.assertTrue(record["statement"].startswith(opening))
                self.assertTrue(record["statement"].endswith(ending))

    def test_ownership_overview_has_complete_rules(self) -> None:
        records = [
            item
            for item in _read("requirements.json")["requirements"]
            if "page-148-l" in item["id"]
        ]
        by_suffix = {item["id"].rsplit("-l", 1)[-1]: item for item in records}
        repaired = {
            "16-3",
            "22-5",
            "52-15",
            "58-17",
            "61-18",
            "70-21",
            "82-25",
            "88-27",
            "94-29",
            "100-31",
            "103-32",
            "106-33",
            "112-35",
            "121-38",
            "124-39",
        }
        self.assertEqual(set(by_suffix), repaired)
        self.assertTrue(all(by_suffix[s]["statement"].endswith(".") for s in repaired))
        self.assertIn("HLAmodifyAttributeState", by_suffix["124-39"]["statement"])
        self.assertIn("HLAresignFederationExecution", by_suffix["124-39"]["statement"])

    def test_time_order_and_acquisition_groups(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        groups = {
            "page-200-l": {"131-38", "134-39", "140-41", "164-49", "170-51", "173-52"},
            "page-213-l": {"76-20", "79-21", "88-24", "94-26"},
            "page-161-l": {"152-45", "158-47", "167-50"},
        }
        for prefix, suffixes in groups.items():
            for suffix in suffixes:
                record = next(item for key, item in by_id.items() if prefix + suffix in key)
                with self.subTest(requirement=prefix + suffix):
                    self.assertTrue(record["statement"].endswith("."))
                    self.assertNotIn(" shall ", record["statement"][-12:])
        pending = next(item for key, item in by_id.items() if "page-161-l167-50" in key)
        self.assertIn("page-162.tex:7-10", pending["coverage_note"])

    def test_cross_page_statements_are_complete(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        save = next(item for key, item in by_id.items() if "page-065-l109-26" in key)
        self.assertIn(
            "greater than or equal to the timestamp of the scheduled save.",
            save["statement"],
        )
        grant = next(item for key, item in by_id.items() if "page-198-l192-57" in key)
        self.assertTrue(grant["statement"].endswith("lookahead is zero."))
        self.assertIn("page-199.tex:14-17", grant["coverage_note"])

        omt = json.loads(
            (ROOT / "topics/ieee/hla-1516.2-2025/semantic/requirements.json").read_text(
                encoding="utf-8"
            )
        )
        record = next(item for item in omt["requirements"] if "page-110-l90-20" in item["id"])
        self.assertTrue(record["statement"].endswith("merge shall also fail."))
        self.assertIn(
            "sections/semantic/clause-7-annexes-a-c/page-111.tex:5",
            record["coverage_note"],
        )
        self.assertIn("content-block-content-15162-page-111.tex:37-38", record["coverage_note"])
        self.assertEqual((record["source"]["line"], record["source"]["end_line"]), (89, 89))
        omt_blocks = json.loads(
            (ROOT / "topics/ieee/hla-1516.2-2025/semantic/content-blocks.json").read_text(
                encoding="utf-8"
            )
        )["content_blocks"]
        page_110 = next(item for item in omt_blocks if item["id"] == "content-15162-page-110")
        self.assertIn(
            "following",
            page_110["layout_body"].splitlines()[record["source"]["line"]],
        )
        page_111 = next(item for item in omt_blocks if item["id"] == "content-15162-page-111")
        continuation = page_111["layout_body"].splitlines()[5]
        self.assertIn("HLAother", continuation)
        self.assertIn("merge shall also", continuation)

    def test_cross_page_continuations_point_to_their_actual_rules(self) -> None:
        cases = (
            (
                "RL-387",
                "hla-1516.1-2025",
                "page-180-l156-49",
                "content/clauses/08-time-management-page-181.tex",
                112,
                112,
                ("timestamp was supplied", "message"),
            ),
            (
                "RL-319",
                "hla-1516.2-2025",
                "page-110-l90-20",
                "sections/semantic/clause-7-annexes-a-c/page-111.tex",
                5,
                5,
                ("HLAother", "merge shall also"),
            ),
            (
                "RL-376",
                "hla-1516.1-2025",
                "page-161-l167-50",
                "content/clauses/07-ownership-management-page-162.tex",
                7,
                10,
                ("Unavailable", "Cancel", "Confirm"),
            ),
            (
                "RL-386",
                "hla-1516.1-2025",
                "page-198-l192-57",
                "content/clauses/08-time-management-page-199.tex",
                7,
                13,
                ("Time Advance Grant", "lookahead is zero"),
            ),
        )
        catalogs: dict[str, dict[str, JsonObject]] = {}
        layouts: dict[str, dict[str, list[str]]] = {}
        for issue_id, document_id, suffix, path, start, end, phrases in cases:
            if document_id not in catalogs:
                semantic = ROOT / "topics" / "ieee" / document_id / "semantic"
                catalogs[document_id] = {
                    item["id"]: item
                    for item in json.loads(
                        (semantic / "requirements.json").read_text(encoding="utf-8")
                    )["requirements"]
                }
                layouts[document_id] = _layout_by_source(semantic / "content-blocks.json")
            with self.subTest(issue=issue_id):
                record = next(
                    item
                    for requirement_id, item in catalogs[document_id].items()
                    if suffix in requirement_id
                )
                citation = f"{path}:{start}" + (f"-{end}" if end != start else "")
                self.assertIn(citation, record["coverage_note"])
                source_text = " ".join(layouts[document_id][path][start : end + 1])
                self.assertTrue(all(phrase in source_text for phrase in phrases), source_text)

    def test_table_5_parent_rows_have_complete_shapes(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        checks = {
            "p295-r001": ("SETTINGS_IGNORED", "SETTINGS_FAILED_TO_PARSE", "SETTINGS_APPLIED"),
            "p296-r001": ("configurationUsed:Boolean", "message:String", "addtionalSettings"),
            "p296-r006": ("Type:String", "Data:BinaryData", "HLAplainTextPassword"),
            "p296-r011": (
                "ATTRIBUTE_HANDLE_FACTORY",
                "LOGICAL_TIME_FACTORY",
                "PARAMETERHANDLEFACTORY",
            ),
            "p296-r030": (
                "HLAfederateHandle:FederateHandle",
                "HLAFOMmoduleDesignatorList:FomDesignatorSet",
            ),
            "p296-r036": ("handle:FederateHandle", "status:SaveStatus"),
            "p297-r003": (
                "preRestoreHandle:FederateHandle",
                "postRestoreHandle:FederateHandle",
                "status:RestoreStatus",
            ),
            "p297-r007": (
                "FederateHandleRestoreStatusSet",
                "Array<FederateHandleRestoreStatus>",
            ),
        }
        for suffix, fragments in checks.items():
            statement = by_id["requirement-candidate-table-5-" + suffix]["statement"]
            with self.subTest(row=suffix):
                self.assertTrue(all(fragment in statement for fragment in fragments))
        self.assertIn(
            "is an enumerant of the Table 5 FactoryClass type",
            by_id["requirement-candidate-table-5-p296-r012"]["statement"],
        )
        self.assertIn(
            "is a field of FederateAttributes",
            by_id["requirement-candidate-table-5-p296-r031"]["statement"],
        )
        self.assertIn(
            "use FederateRestoreStatusSet (type 20)",
            by_id["requirement-candidate-table-5-p297-r007"]["coverage_note"],
        )

    def test_table_5_fragmented_children_keep_their_parent_type(self) -> None:
        issues = {
            item["id"]: item
            for item in json.loads(
                (ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
            )["issues"]
        }
        requirements = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        for issue_id, expected_count in (("RL-358", 3), ("RL-365", 18)):
            ids = issues[issue_id]["affected_requirement_ids"]
            self.assertEqual(len(ids), expected_count)
            parent, *children = (requirements[item_id]["statement"] for item_id in ids)
            values = parent.split("Enumeration<", 1)[1].split(">", 1)[0].split(", ")
            with self.subTest(issue=issue_id):
                self.assertEqual(len(values), expected_count)
                self.assertEqual(
                    set(values[1:]),
                    {child.split(" is an enumerant", 1)[0] for child in children},
                )

        for issue_id, expected_fields, expected_children in (
            (
                "RL-366",
                (
                    "HLAfederateHandle:FederateHandle",
                    "HLAfederateName:String",
                    "HLAfederateType:String",
                    "HLAfederateHost:String",
                    "HLAFOMmoduleDesignatorList:FomDesignatorSet",
                ),
                (
                    "HLAfederateName:String",
                    "HLAfederateType:String",
                    "HLAfederateHost:String",
                    "HLAFOMmoduleDesignatorList:FomDesignatorSet",
                ),
            ),
            (
                "RL-367",
                ("handle:FederateHandle", "status:SaveStatus"),
                ("status:SaveStatus",),
            ),
            (
                "RL-368",
                (
                    "preRestoreHandle:FederateHandle",
                    "postRestoreHandle:FederateHandle",
                    "status:RestoreStatus",
                ),
                (
                    "preRestoreHandle:FederateHandle",
                    "postRestoreHandle:FederateHandle",
                    "status:RestoreStatus",
                ),
            ),
        ):
            ids = issues[issue_id]["affected_requirement_ids"]
            parent, *children = (requirements[item_id]["statement"] for item_id in ids)
            with self.subTest(issue=issue_id):
                self.assertEqual(len(ids), len(expected_children) + 1)
                self.assertTrue(all(field in parent for field in expected_fields))
                self.assertEqual(
                    [child.split(" is a field of", 1)[0] for child in children],
                    list(expected_children),
                )
                self.assertTrue(all("not a separate Table 5 type" in child for child in children))

    def test_table_5_sources_point_to_printed_values_and_examples(self) -> None:
        issues = json.loads(
            (ROOT / "data/hla-backflow-2026-10-24.json").read_text(encoding="utf-8")
        )["issues"]
        table_ids = {
            requirement_id
            for issue in issues
            for requirement_id in issue["affected_requirement_ids"]
            if "requirement-candidate-table-5-" in requirement_id
        }
        self.assertEqual(len(table_ids), 37)
        requirements = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        pages = _layout_by_source(SEMANTIC / "content-blocks.json")
        bindings = _read("api-requirement-bindings.json")["bindings"]
        examples = {
            "p295-r001": ('"SETTINGS_APPLIED"',),
            "p296-r001": (
                '"configurationUsed": true',
                '"addtionalSettingsResultCode": "SETTINGS_APPLIED"',
                '"message": ""',
            ),
            "p296-r006": ('"Type": "HLAplainTextPassword"', '"Data": "xFDcMA"'),
            "p296-r011": ('"ATTRIBUTE_HANDLE_FACTORY"',),
            "p296-r036": ('"status": "FEDERATE_SAVING"',),
            "p297-r003": ('"status": "FEDERATE_RESTORING"',),
            "p297-r007": ("Array<FederateHandleRestoreStatus>", r"\{preRestoreHandle"),
        }
        for requirement_id in sorted(table_ids):
            with self.subTest(requirement=requirement_id):
                record = requirements[requirement_id]
                source = record["source"]
                lines = pages[source["path"]]
                self.assertLess(source["end_line"], len(lines))
                opening = record["statement"].split(" is ", 1)[0]
                opening = re.sub(r"^Table 5 (?:defines|prints) ", "", opening)
                anchor = opening.split(" as ", 1)[0].split(" with encoding ", 1)[0]
                self.assertIn(anchor, lines[source["line"]].replace(r"\_", "_"))
                excerpt = " ".join(lines[source["line"] : source["end_line"] + 1])
                excerpt = excerpt.replace(r"\_", "_")
                for suffix, printed_example in examples.items():
                    if requirement_id.endswith(suffix):
                        for witness in printed_example:
                            self.assertIn(witness, excerpt)
                self.assertTrue(
                    any(
                        item["requirement_id"] == requirement_id and item["source"] == source
                        for item in bindings
                    )
                )

    def test_table_5_source_conflicts_remain_explicit(self) -> None:
        anomalies = {
            item["source_id"]: item for item in _read("source-anomaly-ledger.json")["entries"]
        }
        configuration = anomalies["hla15161-table-5-configuration-result-example"]
        restore_set = anomalies["hla15161-table-5-restore-status-set-name"]
        self.assertEqual(configuration["review_status"], "DISPOSITIONED")
        self.assertIn("addtionalSettingsResultCode", configuration["source_text"])
        self.assertIn("additionalSettingsResultCode", configuration["source_text"])
        self.assertEqual(restore_set["review_status"], "DISPOSITIONED")
        self.assertIn("FederateHandleRestoreStatusSet", restore_set["source_text"])
        self.assertIn("FederateRestoreStatusSet", restore_set["reason"])
        self.assertIn("likely typographical error", restore_set["rendered_text"])
        self.assertIn("FederateRestoreStatusSet (MIM type 20)", restore_set["rendered_text"])
        self.assertIn("FederateRestoreStatus (type 19)", restore_set["rendered_text"])
        self.assertIn("type 20", restore_set["mapping_effect"])
        table_14_page = next(
            item
            for item in _read("content-blocks.json")["content_blocks"]
            if item["id"] == "content-15161-page-324"
        )["layout_body"]
        table_14_row = table_14_page[table_14_page.index("FederateRestoreStatusSet") :]
        self.assertIn("20%", table_14_row[:180])
        self.assertNotIn("FederateHandleRestoreStatusSet", table_14_page)
        api_surfaces = _read("api-surfaces.json")["api_surfaces"]
        restore_api = [
            item
            for item in api_surfaces
            if item.get("name") == "federationRestoreStatusResponse"
            and item.get("language") in {"java", "cpp"}
        ]
        self.assertEqual(len(restore_api), 2)
        self.assertTrue(all("FederateRestoreStatus" in item["signature"] for item in restore_api))
        self.assertTrue(
            all("FederateHandleRestoreStatus" not in item["signature"] for item in restore_api)
        )
        literal = next(
            item
            for item in _read("requirements.json")["requirements"]
            if item["id"] == "requirement-candidate-table-5-p297-r007"
        )
        bindings = [
            item
            for item in _read("api-requirement-bindings.json")["bindings"]
            if item["requirement_id"] == literal["id"]
        ]
        self.assertEqual(len(bindings), 1)
        self.assertIsNone(bindings[0]["api_surface_id"])
        self.assertEqual(bindings[0]["candidate_api_surface_ids"], [])
        self.assertEqual(bindings[0]["source"], literal["source"])

    def test_time_table_and_caption(self) -> None:
        by_id = {item["id"]: item for item in _read("requirements.json")["requirements"]}
        tar = next(item["statement"] for key, item in by_id.items() if "page-178-l45-12" in key)
        self.assertIn("zero lookahead", tar)
        self.assertIn("less than or equal to the federation time requested", tar)
        self.assertNotIn("t7.98pt", tar)
        self.assertNotIn("third column", tar.lower())
        self.assertIn(
            "timestamp was supplied",
            next(item["statement"] for key, item in by_id.items() if "page-180-l156-49" in key),
        )
        order_rule = next(item for key, item in by_id.items() if "page-180-l156-49" in key)
        self.assertIn("page-181.tex:112", order_rule["coverage_note"])
        caption = next(item for key, item in by_id.items() if "page-181-l115-2" in key)
        self.assertEqual(caption["extraction"], "candidate")
        self.assertEqual(
            caption["statement"],
            "Table 2 illustrates how the order type of a sent message shall be determined.",
        )
        self.assertEqual((caption["source"]["line"], caption["source"]["end_line"]), (112, 117))
        page_181 = next(
            item["layout_body"].splitlines()
            for item in _read("content-blocks.json")["content_blocks"]
            if item["id"] == "content-15161-page-181"
        )
        self.assertIn("Table 2 illustrates", page_181[112])
        self.assertIn("type of a sent message shall be determined", page_181[115])
        reviews = _read("requirement-review.json")["reviews"]
        self.assertTrue(
            any(
                item["requirement_id"] == caption["id"]
                and item["status"] == "non-normative"
                and item["source"] == caption["source"]
                for item in reviews
            )
        )
        self.assertTrue(
            any(
                item["requirement_id"] == caption["id"] and item["source"] == caption["source"]
                for item in _read("api-requirement-bindings.json")["bindings"]
            )
        )


if __name__ == "__main__":
    unittest.main()
