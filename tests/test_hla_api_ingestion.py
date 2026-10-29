"""Contracts for the text-only HLA API declaration ingestion."""

from __future__ import annotations

import json
import unittest
from collections import Counter

from hla_lab.core.semantic_model import ApiSurfaceFile
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.corpus.ingest_hla_api import ingest_2010, ingest_2025
from tests.support import TEST_REPO_ROOT

ROOT = TEST_REPO_ROOT
INBOX = ROOT / "inbox"
HAS_2010_ARCHIVES = all(
    (INBOX / "1516.1-2010_downloads" / name).is_file()
    for name in (
        "IEEE1516-2010_C++_API.zip",
        "IEEE1516-2010_Java_API.zip",
        "hla1516e.wsdl",
    )
)
HAS_2025_ARCHIVE = (INBOX / "1516.1-2025_downloads" / "1516-2025_API_XML_2025_08_14.zip").is_file()


class HlaApiIngestionTests(unittest.TestCase):
    @unittest.skipUnless(
        HAS_2010_ARCHIVES,
        "requires the optional IEEE 1516-2010 API archives under inbox/",
    )
    def test_2010_ingestion_contains_native_and_wsdl_surfaces(self) -> None:
        records = ingest_2010(ROOT)
        self.assertGreater(len(records), 500)
        self.assertEqual(Counter(item.language for item in records)["cpp"], 212)
        self.assertEqual(Counter(item.language for item in records)["java"], 236)
        self.assertEqual(Counter(item.language for item in records)["wsdl"], 154)
        self.assertTrue(all(item.source for item in records))
        self.assertTrue(
            all(
                item.source and "#" in item.source.path
                for item in records
                if item.language in {"cpp", "java"}
            )
        )
        self.assertTrue(
            all(
                item.source and "#" not in item.source.path
                for item in records
                if item.language == "wsdl"
            )
        )
        self.assertTrue(all(item.binding_kind in {"native", "protocol"} for item in records))

    @unittest.skipUnless(
        HAS_2025_ARCHIVE,
        "requires the optional IEEE 1516-2025 API archive under inbox/",
    )
    def test_2025_ingestion_contains_native_and_fedpro_surfaces(self) -> None:
        records = ingest_2025(ROOT)
        self.assertGreater(len(records), 900)
        self.assertEqual(Counter(item.language for item in records)["fedpro"], 470)
        self.assertEqual(Counter(item.language for item in records)["cpp"], 243)
        self.assertEqual(Counter(item.language for item in records)["java"], 268)
        fedpro = tuple(item for item in records if item.language == "fedpro")
        self.assertTrue(all(item.protocol == "protobuf" for item in fedpro))
        self.assertEqual(sum(bool(item.parameters) for item in fedpro), 322)
        self.assertEqual(sum(item.notes.find("no gRPC service/rpc") >= 0 for item in fedpro), 470)

    def test_authored_records_round_trip_through_pydantic(self) -> None:
        for document_id in ("hla-1516.1-2010", "hla-1516.1-2025"):
            path = ROOT / "topics" / "ieee" / document_id / "semantic" / "api-surfaces.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            restored = ApiSurfaceFile.model_validate(payload)
            self.assertGreater(len(restored.api_surfaces), 500)

    def test_loaded_editions_keep_semantic_seams_and_exact_bindings(self) -> None:
        for document_id, expected_semantic in (
            ("hla-1516.1-2010", 212),
            ("hla-1516.1-2025", 283),
        ):
            model = load_hla_document_model(ROOT / "topics" / "ieee" / document_id)
            self.assertEqual(
                sum(item.binding_kind == "semantic" for item in model.api_surfaces),
                expected_semantic,
            )
            self.assertGreater(
                sum(item.binding_kind != "semantic" for item in model.api_surfaces),
                500,
            )


if __name__ == "__main__":
    unittest.main()
