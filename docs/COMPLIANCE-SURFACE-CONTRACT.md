# RTI compliance surface contract

The repository now has a specification-facing contract that can be completed
before an RTI implementation is selected. It is deliberately separate from
the faithful publication roots and from any future implementation repository.

## Three readiness levels

`specification_ready` means that the semantic corpus has complete structural
coverage:

- every requirement has a planned verification slot;
- every modeled transition has a planned verification slot;
- every modeled 1516.1 transition has an API surface record;
- every state machine has a trace seed;
- Pydantic validation rejects unresolved local IDs, invalid state targets,
  duplicate IDs, and broken references.

`api_contract_ready` is stricter. It requires every declared native or protocol
API surface to have a language and a parameter contract. The exact source
declarations are now present in `semantic/api-surfaces.json` for both `1516.1`
editions: native C++ and Java, 2010 WSDL, and 2025 FedPro protobuf messages.
Semantic mapping seams are intentionally excluded from this gate because they
are planned implementation boundaries, not callable API declarations; they
remain `language=unspecified` until they are crosswalked to exact callable
surfaces.
The Python adapter and a transport-level service definition are also still
future projections. FedPro currently supplies protobuf messages only: its
archives contain no `service` or `rpc` declarations, so protobuf must not be
reported as a complete gRPC API.

The semantic-to-binding crosswalk is recorded separately in
`semantic/api-crosswalk.json`. Each implementation mapping has one row per
target. Rows are explicitly classified as `matched`, `ambiguous`, `unmatched`,
or `planned`, with candidate and selected API-surface IDs. This keeps an
ambiguous overload or a missing transport declaration visible to compliance
queries instead of silently treating it as an implementation match.

The requirement-to-declaration path is recorded separately in
`semantic/api-requirement-bindings.json` in both `hla-1516.1-2010` and
`hla-1516.1-2025`. Every requirement has at least one explicit row. API-facing
rows identify the Java or C++ surface, relationship, review status, rationale,
and source provenance; cross-cutting or not-applicable requirements are
classified explicitly instead of being omitted. `Requirement.api_surface_scope`
is independent of transition coverage: a requirement can remain fully linked
to state-machine transitions while being reviewed as cross-cutting for the
native Java/C++ declaration path. Candidate, ambiguous, and unmatched rows
remain visible review gaps. When a standard service is represented by multiple
source overloads, `Requirement.api_surface_resolution="all-overloads"` records
the explicit reviewed decision to bind every overload in that service family;
the default remains strict matching.

Audit both editions with:

```console
python -m hla_lab.traceability.api_traceability --check --require-complete --json
```

The audit verifies manifest determinism, requirement coverage, language/source
compatibility, and declaration-shaped provenance. API source paths may use the
`archive.zip#path/to/declaration.h` form because the licensed comparison
archives are inputs and are intentionally not committed to the repository.
The repository gate uses `--require-complete`, so ambiguous and unmatched rows
cannot silently pass CI. Concrete RTI implementation evidence remains an
external integration concern.

`implementation_ready` is stricter again. It requires concrete implementation
references and implemented or verified statuses. The current mappings are
planned seams, not evidence of an RTI implementation.

This distinction prevents the semantic corpus from being mistaken for a
working RTI while still making it complete enough to drive implementation and
verification work.

## Typed records

The generic model in `hla_lab/core/semantic_model.py` provides:

- `ApiSurface` and `ApiParameter` for callable or event-facing boundaries;
- `VerificationTest` for requirement, transition, API, and trace evidence
  slots;
- `StateTrace` and `TraceStep` for replayable state-machine scenarios.

`DocumentModel` validates the references among all of these records. HLA
ownership vocabulary is isolated in `hla_lab/core/hla_surface_profile.py`, where
the current mapping kinds are projected to `RTIambassador`,
`FederateAmbassador`, RTI internal handlers, and integration adapters.

Requirement arrays use one canonical presentation order: document clause order,
then authoritative source/include order within each clause. The compliance
publication and portable bundle preserve that sequence for both the 2010 and
2025 editions. Requirement IDs remain stable semantic join keys; consumers must
not use an array position or presentation ordinal as identity.

## Executable trace contract

`hla_lab/traceability/state_trace.py` replays a `StateTrace` against any generic
`StateMachine`. A trace may name a transition directly, which is preferred for
diagram-derived transitions, or use an event label when exactly one transition
matches the current state. Ambiguous event matches, wrong source states, wrong
targets, and transitions without explicit targets are reported rather than
silently accepted.

## Readiness command

Run the source-only readiness check from the repository root:

```console
hla-lab status --require-api-contract
hla-lab status --require-api-contract --json
```

The current corpus reports `specification_ready: True` and
`api_contract_ready: True`. It correctly reports `implementation_ready: False`:
exact binding records exist, but semantic-to-binding crosswalks,
Python/transport projections, and concrete RTI evidence have not yet been
supplied.

Use `--require-language-contract` when the Java/C++ API extraction is required
for a gate, and `--require-concrete` only in an implementation repository that
contains source-addressable RTI evidence.

Inspect crosswalk gaps directly:

```console
python -m hla_lab.traceability.compliance topics/ieee/hla-1516.1-2025 --api-target fedpro --api-gaps --json
```

Query one requirement and receive its resolved Java/C++ declaration sources:

```console
python -m hla_lab.traceability.compliance topics/ieee/hla-1516.1-2025 --document hla-1516.1-2025 --api-binding-requirement-id req-federate-connection-lost --json
```
