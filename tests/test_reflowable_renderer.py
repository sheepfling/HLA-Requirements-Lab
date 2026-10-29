"""Acceptance tests for the reflowable hierarchy-first renderer."""

from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import unittest
from types import SimpleNamespace
from pathlib import Path

from hla_lab.core.semantic_base import SourceRef
from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.generation.generate_derivative import generate_derivative
from hla_lab.generation.reflowable_renderer import (
    _clean_content_text,
    _clean_table_cell_text,
    _math_text,
    _merge_continuation_table_rows,
    _mom_interaction_table_rows,
    _printed_source_label,
    _render_alpha_list_segment,
    _table_family_rows,
    _text_with_semantic_links,
    render_reflowable_document,
)
from hla_lab.publication.publication_contract import default_publication_profile
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
FIXTURE_ROOT = ROOT / "topics" / "fixture" / "non-hla-demo-2025"


def _fixture_profile() -> object:
    path = FIXTURE_ROOT / "fixture_profile.py"
    spec = importlib.util.spec_from_file_location("m26_fixture_profile", path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"unable to load fixture profile: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReflowableRendererTests(unittest.TestCase):
    def test_shortened_figure_caption_keeps_its_number_clickable(self) -> None:
        model = SimpleNamespace(
            document_id="hla-example",
            clauses=(),
            figures=(
                SimpleNamespace(
                    number="10",
                    id="figure-10",
                    caption="Figure 10---Object class (i)",
                ),
            ),
            state_machines=(),
            graph_diagrams=(),
        )

        rendered = _text_with_semantic_links(model, "See Figure 10, Object class (i, k).")

        self.assertIn(r"\hyperlink{hla-example:figure-10}{Figure 10}", rendered)
        self.assertIn("Object class", rendered)

    def test_source_pdf_layout_commands_do_not_leak_into_prose(self) -> None:
        source = (
            "88 87 11 pdf:put @thispage <</Rotate 90>> hla-empty hlafixedpage "
            "129.234 140.364 358.272 477.432 "
            "assets/derived/source-p088-xref13882- -space.png "
            "490.826 418.020 9.96 Figure 11—Class attribute (i, j)"
        )

        cleaned = _clean_content_text(source)

        self.assertNotIn("pdf:put", cleaned)
        self.assertNotIn("@thispage", cleaned)
        self.assertNotIn("hla-empty", cleaned)
        self.assertNotIn("assets/derived", cleaned)
        self.assertIn("Figure 11—Class attribute (i, j)", cleaned)

    def test_inline_math_removes_nested_source_delimiter_artifacts(self) -> None:
        formula = r"[\([domain-domainCenter]/domainSize)+1\/2](DUB-1)"

        normalized = _math_text(formula)

        self.assertEqual(normalized, "[([domain-domainCenter]/domainSize)+1/2](DUB-1)")
        self.assertNotIn(r"\(", normalized)
        self.assertNotIn(r"\[", normalized)
        self.assertNotIn(r"\/", normalized)

    def test_table_continuation_uses_its_own_shifted_column_headers(self) -> None:
        def cell(record_id: str, row: int, column: int, text: str) -> SimpleNamespace:
            return SimpleNamespace(
                id=record_id,
                row=row,
                column=column,
                text=text,
                record_ids=(),
            )

        cells = (
            cell("semantics-header", 1, 8, "Semantics%"),
            cell("interaction-header", 1, 14, "Interaction%"),
            cell("semantics-value", 2, 11, "Request a report interaction."),
            cell("interaction-value", 2, 15, "HLArequestReport"),
            cell("parent-value", 2, 19, "HLAmanager.HLArequest"),
        )
        family = SimpleNamespace(id="table-family-example", title="Example table")
        table = SimpleNamespace(id="table-example", cells=cells)
        model = SimpleNamespace(
            document_id="hla-example",
            clauses=(),
            figures=(),
            state_machines=(),
            graph_diagrams=(),
        )

        rows = _table_family_rows(
            model,
            family,
            (table,),
            (("Semantics", 0, 4), ("Interaction", 5, 7)),
        )

        self.assertEqual(len(rows), 1)
        self.assertIn("Request a report interaction.", rows[0]["Semantics"])
        self.assertNotIn("Request a report interaction.", rows[0]["Interaction"])
        self.assertIn("HLArequest", rows[0]["Interaction"])
        self.assertIn("HLAmanager", rows[0]["Interaction"])

    def test_mom_interaction_table_rejoins_wrapped_rows_and_stops_at_next_table(self) -> None:
        def cell(
            record_id: str,
            row: int,
            column: int,
            text: str,
            source_line: int = 1,
        ) -> SimpleNamespace:
            return SimpleNamespace(
                id=record_id,
                row=row,
                column=column,
                text=text,
                record_ids=(),
                source=SimpleNamespace(line=source_line),
            )

        cells = (
            cell("semantics-header", 1, 1, "Semantics%"),
            cell("interaction-header", 1, 6, "Interaction%"),
            cell("first-description", 2, 4, "Request report data%", 20),
            cell("sentence-period", 2, 3, ".%", 21),
            cell("first-name", 2, 5, "HLArequestReports%", 22),
            cell("first-parent", 2, 7, "HLAmanager.HLAfederate%", 23),
            cell("description-continuation", 3, 4, "The returned values are current.%"),
            cell("second-description", 4, 4, "Request subscription data.%"),
            cell("second-name", 4, 5, "HLArequestSubscriptions%"),
            cell("second-parent", 4, 7, "HLAmanager.HLAfederate%"),
            cell("next-semantics-header", 5, 6, "Semantics%"),
            cell("next-attribute-header", 5, 14, "Attribute%"),
            cell("next-class-header", 5, 18, "Class%"),
            cell("next-table-semantics", 6, 11, "Attribute details belong to Table 19.%"),
            cell("next-table-attribute", 6, 13, "HLAfederateHandle%"),
            cell("next-table-class", 6, 15, "HLAmanager.HLAfederate%"),
        )
        family = SimpleNamespace(
            id="table-family-table-18",
            title="Table 18---MOM interaction class definitions table",
        )
        table = SimpleNamespace(id="table-18-p340", cells=cells)
        model = SimpleNamespace(
            document_id="hla-1516.1-2025",
            clauses=(),
            figures=(),
            state_machines=(),
            graph_diagrams=(),
        )

        headers, logical_rows = _mom_interaction_table_rows(model, (table,))

        self.assertEqual(len(logical_rows), 2)
        self.assertEqual(headers, ("Interaction class", "Parent class", "Semantics"))
        self.assertIn("The returned values are current.", logical_rows[0]["Semantics"])
        self.assertNotIn(
            "} \\hypertarget{hla-1516.1-2025:sentence-period}",
            logical_rows[0]["Semantics"],
        )
        self.assertIn("HLArequest", logical_rows[0]["Interaction class"])
        self.assertIn("Reports", logical_rows[0]["Interaction class"])
        self.assertIn("HLAmanager", logical_rows[0]["Parent class"])
        self.assertIn("Subscriptions", logical_rows[1]["Interaction class"])
        self.assertIn("HLAmanager", logical_rows[1]["Parent class"])
        self.assertNotIn("HLAfederateHandle", str(logical_rows))

    def test_mom_attribute_table_uses_body_columns_and_merges_semantic_fragments(self) -> None:
        def cell(
            record_id: str,
            row: int,
            column: int,
            text: str,
            source_line: int = 1,
        ) -> SimpleNamespace:
            return SimpleNamespace(
                id=record_id,
                row=row,
                column=column,
                text=text,
                record_ids=(),
                source=SimpleNamespace(line=source_line),
            )

        cells = (
            cell("semantics-header", 1, 5, "Semantics%"),
            cell("attribute-header", 1, 12, "Attribute%"),
            cell("class-header", 1, 14, "Class%"),
            cell("first-description", 2, 11, "Handle returned by a successful%", 20),
            cell("first-middle", 2, 7, "Join Federation Execution%", 21),
            cell("first-ending", 2, 2, "service invocation.%", 22),
            cell("semantic-hla-identifier", 2, 10, "HLAobjectClass is included in this value.%", 22),
            cell("first-attribute", 2, 13, "HLAfederateHandle%", 19),
            cell("first-class", 2, 15, "HLAmanager.HLAfederate%", 23),
            cell("description-continuation", 3, 11, "The handle identifies the joined federate.%", 30),
            cell("second-description", 4, 11, "Name supplied when joining.%"),
            cell("second-attribute", 4, 13, "HLAfederateName%"),
            cell("second-class", 4, 15, "HLAmanager.HLAfederate%"),
        )
        family = SimpleNamespace(
            id="table-family-table-19",
            title="Table 19---MOM attribute definitions table",
        )
        table = SimpleNamespace(id="table-19-p340", cells=cells)
        model = SimpleNamespace(
            document_id="hla-1516.1-2025",
            clauses=(),
            figures=(),
            state_machines=(),
            graph_diagrams=(),
        )

        physical_rows = _table_family_rows(
            model,
            family,
            (table,),
            (("Attribute", 11, 13), ("Semantics", 0, 10), ("Class", 14, 20)),
        )
        logical_rows = _merge_continuation_table_rows(
            family, ("Attribute", "Semantics", "Class"), physical_rows
        )

        self.assertEqual(len(logical_rows), 2)
        self.assertIn("HLAfederate", logical_rows[0]["Attribute"])
        self.assertIn("Handle", logical_rows[0]["Attribute"])
        self.assertIn("HLAmanager", logical_rows[0]["Class"])
        self.assertIn("HLAfederate", logical_rows[0]["Class"])
        self.assertIn("The handle identifies the joined federate.", logical_rows[0]["Semantics"])
        self.assertIn("HLAobject", logical_rows[0]["Semantics"])
        self.assertIn("is included in this value.", logical_rows[0]["Semantics"])
        self.assertLess(
            logical_rows[0]["Semantics"].index("Handle returned"),
            logical_rows[0]["Semantics"].index("Join Federation Execution"),
        )
        self.assertLess(
            logical_rows[0]["Semantics"].index("Join Federation Execution"),
            logical_rows[0]["Semantics"].index("service invocation"),
        )
        self.assertIn("HLAfederate", logical_rows[1]["Attribute"])
        self.assertIn("Name", logical_rows[1]["Attribute"])

    def test_rotated_mom_simple_data_table_preserves_semantics_reading_order(self) -> None:
        model = load_document_model(ROOT / "topics" / "ieee" / "hla-1516.1-2025", HLA_SOURCE)
        family = next(item for item in model.table_families if item.id == "table-family-table-12")
        tables = tuple(item for item in model.tables if item.id in family.table_ids)
        schema = (
            ("Name", 20, 21),
            ("Representation", 18, 19),
            ("Units", 16, 17),
            ("Resolution", 14, 15),
            ("Accuracy", 12, 13),
            ("Semantics", 0, 11),
        )
        physical_rows = _table_family_rows(model, family, tables, schema)
        logical_rows = _merge_continuation_table_rows(
            family,
            tuple(header for header, _lower, _upper in schema),
            physical_rows,
        )

        semantics = logical_rows[5]["Semantics"]
        semantics = re.sub(r"\\hypertarget\{[^{}]*\}\{\}", "", semantics)
        semantics = re.sub(r"\\hyperlink\{[^{}]*\}\{([^{}]*)\}", r"\1", semantics)
        semantics = semantics.replace(r"\newline ", " ").replace(r"\allowbreak{}", "")
        self.assertLess(semantics.index("returned by the"), semantics.index("Normalize Federate"))
        self.assertLess(semantics.index("Normalize Federate"), semantics.index("Handle service."))
        self.assertIn("range of the HLAfederate", semantics)

    def test_inline_reference_label_is_not_split_out_as_a_list_item(self) -> None:
        rendered = "\n".join(
            _render_alpha_list_segment(
                "a) First item. d) Handle value as stated in c) . F) is the federate label. "
                "e) Next item."
            )
        )

        self.assertIn("as stated in c).", rendered)
        self.assertIn("F)", rendered)
        self.assertNotIn("\\item[c)]", rendered)
        self.assertNotIn("\\item[F)]", rendered)

    def test_reflowable_view_uses_canonical_clause_order(self) -> None:
        profile = _fixture_profile()
        model = load_document_model(FIXTURE_ROOT, profile.DEMO_SOURCE)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "semantic"
            generate_derivative((model,), output)
            reflowable = (output / "reflowable.tex").read_text(encoding="utf-8")

        self.assertLess(reflowable.find("clause-1"), reflowable.find("clause-1.1"))
        self.assertIn("A reusable unit that accepts an input and produces a result.", reflowable)
        self.assertIn(
            "A widget provider shall validate the input before producing a result.", reflowable
        )
        self.assertIn("validated input", reflowable)
        self.assertIn("Source: source/semantic", reflowable)
        self.assertIn(r"\begin{minipage}{\linewidth}", reflowable)
        self.assertIn(r"\end{minipage}", reflowable)
        self.assertNotIn("DemoFixedBlock", reflowable)

    def test_printed_page_locator_uses_source_page_and_clause(self) -> None:
        source = SourceRef(
            path="content/clauses/08-time-management-page-181.tex", line=112, end_line=117
        )
        self.assertEqual(
            _printed_source_label(source, "8.1.4"),
            "§8.1.4, printed p. 181, lines 112\u2013117",
        )

    def test_semantic_mutation_reaches_reflowable_view(self) -> None:
        profile = _fixture_profile()
        model = load_document_model(FIXTURE_ROOT, profile.DEMO_SOURCE)
        payload = model.model_dump(mode="json")
        payload["requirements"][0]["statement"] = "reflow reflowable mutation sentinel."
        mutated = type(model).model_validate(payload)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "semantic"
            generate_derivative((mutated,), output)
            reflowable = (output / "reflowable.tex").read_text(encoding="utf-8")

        self.assertIn("reflow reflowable mutation sentinel.", reflowable)

    def test_reflowable_renderer_removes_page_adapter_residue(self) -> None:
        profile = _fixture_profile()
        model = load_document_model(FIXTURE_ROOT, profile.DEMO_SOURCE)
        payload = model.model_dump(mode="json")
        source = {"path": "fixture.tex", "line": 1}
        payload["content_blocks"] = [
            {
                "id": "fixture-block",
                "kind": "context",
                "text": "fixture",
                "clause_id": "clause-1",
                "element_ids": ["fixture-element"],
                "source": source,
            }
        ]
        payload["content_elements"] = [
            {
                "id": "fixture-element",
                "kind": "paragraph",
                "text": (
                    "page 1 hla-body 90.000 69.786 432.000 9.96 12.00 "
                    "reflow clean prose sentinel hlafixedpage"
                ),
                "clause_id": "clause-1",
                "block_id": "fixture-block",
                "source": source,
            }
        ]
        mutated = type(model).model_validate(payload)

        rendered = render_reflowable_document(
            (mutated,),
            default_publication_profile((mutated.document_id,)),
        )

        self.assertIn("reflow clean prose sentinel", rendered)
        self.assertNotIn("90.000", rendered)
        self.assertNotIn("hla-body", rendered)
        self.assertNotIn("hlafixedpage", rendered)

    def test_reflowable_tables_exclude_source_frontmatter(self) -> None:
        profile = _fixture_profile()
        model = load_document_model(FIXTURE_ROOT, profile.DEMO_SOURCE)
        source = {"path": "frontmatter/legacy.tex", "line": 1}
        payload = model.model_dump(mode="json")
        payload["tables"] = [
            {
                "id": "legacy-frontmatter-table",
                "title": "legacy source metadata",
                "caption": "legacy source metadata",
                "number": None,
                "continuation": False,
                "cells": [
                    {
                        "id": "legacy-frontmatter-cell",
                        "table_id": "legacy-frontmatter-table",
                        "text": "legacy source metadata",
                        "row": 0,
                        "column": 0,
                        "record_ids": [],
                        "source": source,
                    }
                ],
                "source": source,
                "logical_id": "legacy-frontmatter-table",
                "domain": "generic",
                "omt_kind": None,
                "continued_from": None,
                "family_id": "legacy-frontmatter-family",
            }
        ]
        payload["table_families"] = [
            {
                "id": "legacy-frontmatter-family",
                "title": "legacy source metadata",
                "table_ids": ["legacy-frontmatter-table"],
                "table_captions": {},
                "clause_id": None,
                "source": source,
            }
        ]
        mutated = type(model).model_validate(payload)

        rendered = render_reflowable_document(
            (mutated,),
            default_publication_profile((mutated.document_id,)),
        )

        self.assertNotIn("legacy source metadata", rendered)

    def test_reflowable_table_cells_remove_source_layout_tokens(self) -> None:
        self.assertEqual(
            _clean_table_cell_text("|>p4.65in|>p1.07in| 1|c| Figure number and name"),
            "Figure number and name",
        )


if __name__ == "__main__":
    unittest.main()
