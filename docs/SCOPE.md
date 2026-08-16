# HLA Requirements Lab scope

## Mission

HLA Requirements Lab is a source-controlled laboratory for extracting,
validating, tracing, and publishing requirements from the IEEE HLA standards.
It makes normative meaning and conformance relationships queryable without
pretending that planned mappings are concrete implementation evidence.

The project is a requirements-engineering and traceability system. Faithful
document recreations, LaTeX builds, and diagrams are provenance and inspection
adapters that support that mission.

## In scope

- IEEE 1516, 1516.1, and 1516.2 semantic source records;
- clauses, definitions, requirements, tables, state machines, transitions, and
  API surfaces with explicit source provenance;
- requirement, transition, cross-document, edition, and implementation
  traceability;
- validation of authority, ownership, reciprocal links, and coverage;
- deterministic JSON, CSV, Markdown, and publication projections;
- source-only fixtures and faithful renderers when they protect semantic
  fidelity or provenance;
- planned, concrete, and verified evidence as distinct states.

## Out of scope for the current product

- becoming an official IEEE interpretation or compliance certification;
- claiming an RTI implementation is compliant because a mapping is planned;
- supporting arbitrary standards before the HLA contracts are stable;
- collecting or committing analogue PDFs, binaries, or audit artifacts;
- making page-perfect recreation the primary success metric;
- adding a new publication or diagram family without a requirements-lab use
  case.

## Definition of done

A change belongs in the lab when it makes at least one of these materially
better:

1. a requirement or relationship is more explicit and source-owned;
2. a query can explain coverage, ownership, or a gap deterministically;
3. an output can be regenerated from committed text sources;
4. a validation rule prevents semantic drift;
5. an external implementation can consume a portable contract without
   importing private repository code.

## Scope guardrails

- The six current edition roots—2010 and 2025 for 1516, 1516.1, and 1516.2—are
  the supported corpus boundary.
- New work starts from a requirements, traceability, validation, or evidence
  question; a visual or publication feature alone is not sufficient.
- Generated artifacts stay ignored. Committed data is source, authority,
  provenance, or a deliberately reviewed fixture.
- Document identity, edition/profile selection, faithful surface mappings, and
  publication build settings belong in reviewed manifests; Python should
  provide reusable algorithms and adapters rather than duplicate those facts.
- Milestone history may explain why a test exists, but capability contracts
  determine the public test and command structure.

## Product surfaces

| Surface         | Purpose                                                     |
|-----------------|-------------------------------------------------------------|
| Semantic corpus | Canonical typed records and source references               |
| Lab checks      | Readiness, authority, coverage, and relationship validation |
| Traceability    | Requirement, transition, edition, API, and evidence links   |
| Reports         | Deterministic JSON/CSV/Markdown projections                 |
| Adapters        | Faithful LaTeX, diagrams, and external sidecar boundaries   |

See [ARCHITECTURE.md](ARCHITECTURE.md) for ownership and dependency rules.
