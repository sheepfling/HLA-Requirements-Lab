# Publication products

The HLA semantic corpus supports three independent destinations. They share
typed source records, but none requires another publication's generated files
or PDF output.

| Publication | Purpose | Build roots |
| --- | --- | --- |
| `hla-unofficial-faithful-reconstruction-2025` | Non-authoritative, page-faithful recreations used for provenance and visual comparison. | 1516, 1516.1, 1516.2 faithful projects |
| `hla-hierarchy-reconstruction-2025` | Reflowable hierarchy-first reconstruction that exposes clauses, relationships, definitions, tables, and state behavior. | `hla-semantic-derivative-2025` |
| `hla-rti-compliance-requirements-2025` | Implementation-facing requirements, transitions, evidence, JSON, and normalized CSV projections. | `hla-rti-compliance-2025` |

The source-controlled [registry](../data/publications.json) maps a publication
to its explicit release-project IDs. Its members and expected PDFs are defined
in [the release manifest](../data/release/documents.json).

```powershell
# Inspect destinations.
python -m scripts.build publication list

# Build, clean, or release-check one destination only.
python -m scripts.build publication build hla-hierarchy-reconstruction-2025
python -m scripts.build publication clean hla-rti-compliance-requirements-2025
python -m scripts.release_check --publication hla-unofficial-faithful-reconstruction-2025 --json
```

To add a destination, add a document-local build root and release-project
record, then add one publication record naming that project. To remove a
destination, remove its publication record; its independent source tree may be
retained or removed separately. Generated output remains ignored in either
case.
