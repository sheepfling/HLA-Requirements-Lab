"""Contracts for independently selectable publication destinations."""

from __future__ import annotations

import unittest
from pathlib import Path

from hla_lab.build.build import publication_targets

from hla_lab.publication.publication_registry import (
    load_publication_registry,
    load_release_manifest,
    publication_projects,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "publications.json"
RELEASE_PATH = ROOT / "data" / "release" / "documents.json"


class PublicationRegistryTests(unittest.TestCase):
    def test_hla_publications_have_explicit_and_disjoint_project_membership(self) -> None:
        registry = load_publication_registry(REGISTRY_PATH)
        expected = {
            "hla-unofficial-faithful-reconstruction-2010": "faithful-reconstruction",
            "hla-unofficial-faithful-reconstruction-2025": "faithful-reconstruction",
            "hla-hierarchy-reconstruction-2010": "hierarchy-reconstruction",
            "hla-hierarchy-reconstruction-2025": "hierarchy-reconstruction",
            "hla-rti-compliance-requirements-2010": "requirements-publication",
            "hla-rti-compliance-requirements-2025": "requirements-publication",
        }
        self.assertEqual({item.id: item.kind for item in registry.publications}, expected)
        project_ids = [
            project_id for item in registry.publications for project_id in item.project_ids
        ]
        self.assertEqual(len(project_ids), len(set(project_ids)))

    def test_each_publication_resolves_to_its_own_build_roots(self) -> None:
        registry = load_publication_registry(REGISTRY_PATH)
        release_manifest = load_release_manifest(RELEASE_PATH)
        for publication in registry.publications:
            with self.subTest(publication=publication.id):
                projects = publication_projects(registry, release_manifest, publication.id)
                self.assertEqual(tuple(item.id for item in projects), publication.project_ids)
                self.assertTrue(all(item.publication_id == publication.id for item in projects))
                roots = publication_targets(publication.id)
                self.assertEqual(
                    tuple(path.relative_to(ROOT).as_posix() for path in roots),
                    tuple(item.root for item in projects),
                )
                self.assertTrue(all((path / "build.py").is_file() for path in roots))


if __name__ == "__main__":
    unittest.main()
