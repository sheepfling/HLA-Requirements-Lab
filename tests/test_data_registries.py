"""Contracts preventing domain facts from drifting back into build code."""

from __future__ import annotations

import unittest
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE_PROFILES, source_profile_for_document
from hla_lab.paths import REPO_ROOT, document_catalog, document_ids, document_roots
from hla_lab.publication.publication_registry import load_release_manifest


class DataRegistryTests(unittest.TestCase):
    def test_document_identity_and_source_profiles_are_manifest_driven(self) -> None:
        catalog = document_catalog()
        supported_ids = document_ids()
        self.assertEqual(
            supported_ids,
            tuple(item.document_id for item in catalog.documents),
        )
        roots = document_roots(REPO_ROOT)
        self.assertEqual(tuple(path.name for path in roots), supported_ids)
        self.assertTrue(all(path.is_dir() for path in roots))
        self.assertTrue(all(item.profile_id in HLA_SOURCE_PROFILES for item in catalog.documents))
        self.assertTrue(
            all(source_profile_for_document(item.document_id) for item in catalog.documents)
        )
        self.assertTrue(all(item.migration in {"M9", "M10", "M11"} for item in catalog.documents))

    def test_release_projects_declare_shared_build_settings(self) -> None:
        manifest = load_release_manifest(REPO_ROOT / "data" / "release" / "documents.json")
        for project in manifest.projects:
            with self.subTest(project=project.id):
                root = REPO_ROOT / Path(project.root)
                self.assertTrue((root / "build.py").is_file())
                if project.kind != "fixture":
                    self.assertIsNotNone(project.build)


if __name__ == "__main__":
    unittest.main()
