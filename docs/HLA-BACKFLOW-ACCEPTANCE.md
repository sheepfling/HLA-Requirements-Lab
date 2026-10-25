# HLA implementation backflow acceptance

This branch reviews the 89 Requirements Lab issues that were open in the
2026-10-24 Umbra queue. The [frozen ID list](../data/hla-open-issue-ids-2026-10-24.txt)
guards against omission. The [issue snapshot](../data/hla-backflow-2026-10-24.json)
records each complaint, its affected candidate IDs, the local disposition, and
its verification pointer. Umbra's `compliance/requirements-lab/known-issues.json`
remains authoritative for upstream status; this branch does not change that
register or resynchronize an unchanged pinned export.

A read-only comparison on 2026-10-25 found the Umbra register still has 139
records, including 89 marked open. For those 89, the IDs, document IDs, and
ordered affected-requirement ID lists match this snapshot exactly. The local
dispositions below therefore describe repairs and verification in this branch;
they are not upstream status changes.

## Current local dispositions

| Disposition             | Count | Evidence and remaining action                                                                                                                                          |
| ----------------------- | ----: | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Corrected in Lab branch |    84 | Local semantic repairs and issue-specific regression checks; review and publish through the Lab export before upstream closure.                                        |
| Verified in Umbra       |     4 | Read-only 2026-10-25 checks no longer reproduce RL-261, RL-268, RL-354, or RL-371; reconcile their status in Umbra.                                                    |
| Source conflict open    |     1 | RL-369 retains the literal Table 5 spelling and does not infer a MIM type-20 mapping; adjudicate against the licensed 1516.1-2025 page or an authoritative correction. |

The [backflow regression tests](../tests/test_hla_backflow.py) compare the
snapshot to the frozen queue, validate every affected candidate ID, check all
99 candidate attributions named by the 35 clause complaints, and check all 36
fragment complaints for the missing rule, sentence integrity, and source spans.
An additional boundary audit checks every candidate touched by the 84 locally
corrected issues. It caught 26 clause-attribution candidates with clipped ends
and several more with clipped starts; those statements now preserve complete
sentences from the pinned page layouts, including the ownership rules on page
153 and the region rules on page 220. The tests also cover the
structured Table 5 parent and child rows, missing service-flow candidates,
and the two unresolved source spellings. RL-381 keeps its four stable page-216
IDs as complete sentence-level facets in the dedicated
`m16.range-definition.9.1.1` semantic group; each candidate tells mapping
consumers to cover all four before claiming the full §9.1.1 range definition.

RL-321 and RL-322 now cite the page-199 line-145 and page-200 lines 11, 62,
and 74 service-flow items; RL-253's new exception item cites page-260 line 35.
The regression checks those exact layout lines and the corresponding C++
exception declarations. Earlier exception spans pointed to unrelated list
items, including the page-200 line-23 precondition cited in the input ledger.
The snapshot preserves the original affected-ID lists and separately names
the five requirement IDs created for these three complaints.
RL-387's Table 2 introduction is reviewed as non-normative; its requirement,
review, and binding now cite the full page-181 lines 112-115 sentence.
The source-span audit then checked every issue-linked Table 5 row against the
printed page-layout line. It corrected rotated-table child spans that cited
layout commands and parent spans that omitted their type name or example;
the regression now checks all 37 issue-linked rows and their binding sources.
The two page-192 time-management rules now start at the lines printing their
opening words. The two corrected 1516.2 candidates likewise cite their
paragraph content rather than the following closing brace. The order-type
rule begun on page 180 records its final sentence on page 181 as a continuation.
An additional source-span audit found that RL-319's note conflated source
layout and generated-output line numbers. The variant-record `HLAother`
continuation is on source page 111 line 5 and generated output lines 37–38;
the corrected note and regression check both locations. The regression also
checks the cited continuation text for RL-376, RL-386, and RL-387.

Run the tests with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_hla_backflow.py -q
```

The 2026-10-25 complete suite passed with 332 tests, 2 skips, and 935
subtests using four parallel workers. This run includes the 84 corrected
issue dispositions, the export-delta report, and the cross-page source checks.
The six-document check and complete 2025 API traceability audit passed after
the RL-319 citation correction. The package also built an offline source
distribution and wheel;
its installed command, Pydantic schema listing, and explicit-root document
listing worked from outside the repository directory.
The CI module and CLI help also load from outside the checkout without
`PYTHONPATH`; CI now receives `--root .` explicitly and passes the selected
workspace root to its child commands.
An outside-workspace import sweep loaded all 105 installed `hla_lab` modules
with both `PYTHONPATH` and `HLA_LAB_ROOT` unset. A portability regression test
now checks this import boundary. The inventory, edition-diff, utility-inventory,
and module-layout commands also show help without a configured root; the latter
two ran from outside the checkout with an explicit `--root`. A further external
run found and repaired missing root propagation through source-profile and
inventory registry lookups. The corpus-inventory command now takes
`--workspace-root` separately from repeatable document `--root` paths; both
corpus inventory and edition diff completed from outside the checkout with no
root environment variable. The installed `hla-lab-model` command also ran
from outside the checkout with an explicit `--workspace-root`. The targeted
portability, inventory, and edition diff tests passed after this change. The
Umbra handoff exporter now passes `--corpus-root` through its model loader; an
outside-workspace export produced all three 2025 documents without a root
environment variable. The installed `hla-lab --root <workspace> check --json`
command also completed for all six documents from that external directory.

The 502-page 1516.1-2025 PDF build also passed a publication check. Page 270
keeps the region rule and following heading separate. The Table 5 source pages
295–297 render on PDF pages 357–359 with continuation fields in the Encoding
column and readable examples. The
[Table 5 rendering test](../tests/test_table5_rendering.py) guards that column
assignment.

The local `topics/ieee/hla-1516.1-2025/semantic/source-anomaly-ledger.json`
records RL-256's ConfigurationResult example spelling and RL-369's
restore-status set name as unresolved source anomalies. The corrected
requirement candidates preserve the printed examples as provenance; example
spelling is not promoted into a new lexical obligation. The
[IEEE SA 2025 auxiliary evidence](../data/hla-15161-official-auxiliary-evidence-2026-10-25.json)
confirms `additionalSettingsResultCode` in the Java `ConfigurationResult`
declaration. This closes the RL-256 candidate repair locally while the printed
example remains an unresolved source anomaly. The same official download's
MIM XML names `FederateRestoreStatus` as type 19 and
`FederateRestoreStatusSet` as type 20, matching the supplied 1516.1-2025
Table 14 on page 324 and the supplied 1516.2-2025 MIM.
1516.1 Table 5 instead prints `FederateHandleRestoreStatusSet` and
`Array<FederateHandleRestoreStatus>`.
The Table 5 candidate has one reviewed binding with no selected or candidate
API surface; the regression checks that no direct API mapping is promoted from
the disputed name.
No additional licensed page or authoritative correction is available for the
RL-369 Table 5 name conflict. The public
[IEEE SA 1516.1-2025 listing](https://standards.ieee.org/ieee/1516.1/6688/)
offers purchase or subscription access and does not display the disputed
Table 5 page or an adjudication of these spellings. Its linked auxiliary
downloads do not contain the disputed Table 5 page.
The auxiliary archive and its selected entries are pinned by SHA-256 in the
evidence record. After downloading the archive from the IEEE SA listing, run:

```powershell
.\.venv\Scripts\python.exe -m tools.verify_ieee_aux_evidence --archive .compliance\1516.1-2025_downloads.zip --evidence data\hla-15161-official-auxiliary-evidence-2026-10-25.json
```

RL-268's original eight plan findings no longer appear when Umbra runs
`tools/requirements_lab.py check-plan`. That command still exits nonzero for a
separate historical RL-001..RL-157 observation-baseline drift. This remains a
separate Umbra quality finding and is not evidence that RL-268 recurred.

## Upstream acceptance

No Umbra issue status was changed by this branch. The read-only evidence
supports proposing `resolved-in-umbra` for RL-261, RL-268, RL-354, and RL-371
when that repository's ledger is reconciled. RL-371's historical
`umbra-cpp-connect-requirement-traceability` row no longer exists; the current
`umbra-cpp-connect-integration` row was inspected and explicitly
identifies RL-045 as absent. The 84 Lab-content issues should retain their
upstream `open` status until the corrected export is reviewed and pinned there.

### Reproducible export comparison

Umbra's `requirements-lab.lock.json` still pins Lab commit
`4bafa0619cf8c777a79294c9e0e78f2a38ee55b4` (`v0.1.0.a1`). Its ignored
`.compliance/corpus-bundle.json` reports that same revision. On 2026-10-25,
the Lab exporter produced a six-document, working-tree preview with Umbra's
`umbra-hla-requirements` bundle ID. Umbra's read-only `resync --edition all`
found no bundle ordinal-integrity errors in either export. It found these
document changes:

| Document          | Stable-ID comparison with pinned bundle                                                                                                                                                                                                           |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hla-1516.1-2025` | 297 existing requirement records changed beyond their ordinal; five new requirement IDs, zero removed IDs; 1,159 existing ordinals moved. Fifteen transitions, one mapping, one API surface, five crosswalks, and ten API binding IDs were added. |
| `hla-1516.2-2025` | Two existing requirements changed beyond their ordinal; zero requirement IDs added or removed.                                                                                                                                                    |
| `hla-1516.1-2010` | Twenty-two existing transition endpoints changed; zero transition IDs added or removed.                                                                                                                                                           |

The other three documents were unchanged. All 203 distinct original
requirement IDs referenced by the 84 corrected Lab complaints are present in
both exports and have a non-ordinal change. The five new requirement IDs are
listed under RL-253, RL-321, and RL-322 in the issue snapshot. The 2010
transition changes are additional branch changes; the two changed 1516.2
requirements are part of the corrected complaints. Of the 297 changed
1516.1-2025 requirement records, 201 belong to the corrected complaints,
three are cited by other queue issues, and 93 are not cited by any of the 89
issues. These 93 records are enumerated in the export-delta report with changed
fields and before/after hashes. Review them, as well as the 2010 transitions,
separately before updating a six-document Umbra pin.

The [per-issue export delta](../data/hla-backflow-export-delta-2026-10-25.json)
records the changed fields and before/after record hashes for every affected
stable ID across all 89 issues. It omits ordinal-only movement and includes
readable before/after values for clause, source, extraction, and grouping
metadata. Its 84 corrected issues cover 211 affected rows (203 distinct IDs)
and five newly created IDs. RL-369 remains source-conflict-open regardless of
its candidate delta. The report also lists all 93 changed requirements that
have no queue-issue attribution, so collateral export changes stay visible.
A regression checks that the delta names every snapshot issue, each corrected
candidate, and the unattributed changes.

To reproduce this preview from the Lab checkout, with the sibling Umbra
checkout and its existing ignored baseline bundle available:

```powershell
.\.venv\Scripts\python.exe -m hla_lab.publication.export_compliance_bundle --corpus-root . --edition all --revision working-tree-backflow-2026-10-25 --bundle-id umbra-hla-requirements --output .compliance/backflow-candidate-bundle.json
.\.venv\Scripts\python.exe -B ..\umbra\tools\requirements_lab.py resync --baseline ..\umbra\.compliance\corpus-bundle.json --candidate .compliance\backflow-candidate-bundle.json --edition all
.\.venv\Scripts\python.exe -m tools.backflow_export_delta --snapshot data/hla-backflow-2026-10-24.json --baseline ..\umbra\.compliance\corpus-bundle.json --candidate .compliance\backflow-candidate-bundle.json --output data/hla-backflow-export-delta-2026-10-25.json
```

The baseline bundle's SHA-256 is
`4e0160b1e2dd81ba3df4f36911735f2cb04848d3ea3f45e1652943c6a0f255c2`;
the preview bundle's is
`b3981c99a891fab33b38654f28cbe744d451a97290b3105fc3abec48f65a8a9c`.
These ignored files are comparison inputs, not a new pin. After this Lab
branch is reviewed and committed, export with that commit SHA, rerun `resync`,
review the changes to all three affected documents, then update Umbra's lock
and issue ledger with the reviewed revision.

Before changing any Lab-content issue status, review the new Lab export
against its pinned source and retain the stable candidate IDs. Resolve
RL-369 only with primary-source evidence; keep its direct type-20 mapping
withheld until then. The `.tex` page paths on some historical candidates are
generated adapters that input semantic page content, so their line numbers do
not independently locate the prose in the adapter. Use the semantic page
layout and the candidate's source span together when reviewing those rows.
