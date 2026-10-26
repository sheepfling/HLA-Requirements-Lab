"""Build the source-owned requirement catalogs for both HLA editions.

The 2025 catalogs already contain reviewed source refinements.  This migration
keeps those records and canonicalizes their order.  The legacy 2010 adapters
now expose sentence- and table-row-level candidates; this migration matches
those candidates to existing records where possible, preserves stable IDs,
and promotes only the genuinely new source obligations.

The migration is intentionally deterministic and safe to rerun.  Requirement
IDs remain consumer join keys; catalog order is derived from clause ownership
and source order and is presentation metadata only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from types import MappingProxyType

from pydantic import BaseModel, ConfigDict

from hla_lab.core.io import write_json
from hla_lab.core.semantic_model import Requirement, RequirementFile
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from hla_lab.corpus.hla_2010_semantic import _requirements, _surface_inputs
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import DocumentResources
from tools.migrations.workspace import document_root

DOCUMENTS = (
    "hla-1516-2010",
    "hla-1516.1-2010",
    "hla-1516.2-2010",
    "hla-1516-2025",
    "hla-1516.1-2025",
    "hla-1516.2-2025",
)


class _RequirementCatalogBuildReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    document: str
    before: int
    source_candidates: int | None = None
    after: int | None = None
    dry_run: bool | None = None
    canonical_count: int | None = None
    preserved_ids: int | None = None
    new_ids: int | None = None
    unmatched_candidates: int | None = None
    aliases: int | None = None


_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9-]{2,}")
_STOP_WORDS = frozenset(
    {
        "about",
        "after",
        "also",
        "among",
        "and",
        "are",
        "because",
        "been",
        "being",
        "during",
        "from",
        "have",
        "into",
        "must",
        "shall",
        "that",
        "the",
        "their",
        "these",
        "this",
        "those",
        "through",
        "under",
        "using",
        "which",
        "with",
    }
)
_2010_API_DISPOSITIONS: dict[str, dict[str, str]] = MappingProxyType(
    {
        "req-4035a87fed87": {
            "api_surface_resolution": "all-overloads",
            "api_surface_note": (
                "The named callback is represented by all reviewed overload declarations."
            ),
        },
        "req-4718f44df6e8": {
            "api_surface_scope": "cross-cutting",
            "api_surface_note": (
                "Behavioral state invariant; no direct language API declaration is asserted."
            ),
        },
        "req-5421cc4829a9": {
            "api_surface_scope": "cross-cutting",
            "api_surface_note": (
                "Behavioral state invariant; no direct language API declaration is asserted."
            ),
        },
        "req-625332dd1f54": {
            "api_surface_scope": "cross-cutting",
            "api_surface_note": (
                "Behavioral state invariant; no direct language API declaration is asserted."
            ),
        },
        "req-6a8c0463fc94": {
            "api_surface_scope": "cross-cutting",
            "api_surface_note": (
                "Federation lifecycle invariant; no direct language API declaration is asserted."
            ),
        },
        "req-959bfe345492": {
            "api_surface_scope": "cross-cutting",
            "api_surface_note": (
                "Federation lifecycle invariant; no direct language API declaration is asserted."
            ),
        },
        "req-f39daa299f9c": {
            "api_surface_scope": "cross-cutting",
            "api_surface_note": (
                "Object-model state invariant; no direct language API declaration is asserted."
            ),
        },
    }
)


def _tokens(value: str) -> frozenset[str]:
    return frozenset(
        token for token in _TOKEN.findall(value.casefold()) if token not in _STOP_WORDS
    )


def _source_key(record: Requirement) -> tuple[str, int]:
    return record.source.path, record.source.line


def _match_score(candidate: Requirement, existing: Requirement) -> tuple[int, int, int, int]:
    if candidate.source.path != existing.source.path:
        return (-1, -1, -1, -1)
    candidate_tokens = _tokens(candidate.statement)
    existing_tokens = _tokens(existing.statement)
    overlap = len(candidate_tokens & existing_tokens)
    exact = int(
        candidate.statement.casefold() in existing.statement.casefold()
        or existing.statement.casefold() in candidate.statement.casefold()
    )
    line_distance = abs(candidate.source.line - existing.source.line)
    return exact, overlap, -line_distance, -abs(len(candidate.statement) - len(existing.statement))


def _match_existing(
    candidates: tuple[Requirement, ...],
    existing: tuple[Requirement, ...],
) -> tuple[dict[str, Requirement], set[str], set[str]]:
    """Match old records to new source candidates without reusing an ID."""

    edges: list[tuple[tuple[int, int, int, int], str, str]] = []
    for candidate in candidates:
        for old in existing:
            score = _match_score(candidate, old)
            if score[1] >= 2:
                edges.append((score, candidate.id, old.id))
    edges.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    candidate_to_old: dict[str, Requirement] = {}
    used_candidates: set[str] = set()
    used_old: set[str] = set()
    for _score, candidate_id, old_id in edges:
        if candidate_id in used_candidates or old_id in used_old:
            continue
        old = next(item for item in existing if item.id == old_id)
        candidate_to_old[candidate_id] = old
        used_candidates.add(candidate_id)
        used_old.add(old_id)
    return candidate_to_old, used_candidates, used_old


def _new_id(document: str, candidate: Requirement) -> str:
    digest = hashlib.sha1(
        f"{document}:{candidate.source.path}:{candidate.source.line}:"
        f"{candidate.source.end_line}:{candidate.id}:{candidate.statement}".encode()
    ).hexdigest()[:12]
    return f"req-{digest}"


def _promote_2010(root: Path) -> _RequirementCatalogBuildReport:
    semantic = DocumentResources(root).semantic
    requirement_path = semantic / "requirements.json"
    existing_payload = RequirementFile.model_validate_json(
        requirement_path.read_text(encoding="utf-8")
    )
    existing = existing_payload.requirements
    candidates = _requirements(root, _surface_inputs(root))
    candidate_to_old, matched_candidates, matched_old = _match_existing(candidates, existing)
    aliases_path = semantic / "requirement-id-aliases.json"
    prior_aliases = (
        json.loads(aliases_path.read_text(encoding="utf-8")).get("aliases", [])
        if aliases_path.is_file()
        else []
    )
    aliases: list[dict[str, str]] = list(prior_aliases)
    for old in existing:
        if old.id in matched_old:
            continue
        same_path = tuple(item for item in candidates if item.source.path == old.source.path)
        if not same_path:
            raise ValueError(
                f"{root.name}: cannot disposition legacy requirement without a source path: "
                f"{old.id}"
            )
        target = max(
            same_path,
            key=lambda item: _match_score(item, old),
        )
        canonical_id = (
            candidate_to_old[target.id].id
            if target.id in candidate_to_old
            else _new_id(root.name, target)
        )
        if old.id == canonical_id:
            continue
        aliases.append(
            {
                "alias_id": old.id,
                "canonical_id": canonical_id,
                "relation": "merged",
                "reason": (
                    "Legacy line-local record was merged into the improved sentence/table-row "
                    "candidate while preserving an explicit consumer alias."
                ),
            }
        )

    records: list[Requirement] = []
    for candidate in candidates:
        old = candidate_to_old.get(candidate.id)
        if old is None:
            payload = candidate.model_copy(
                update={
                    "id": _new_id(root.name, candidate),
                    "title": (
                        f"Normative statement at {candidate.source.path}:{candidate.source.line}"
                    ),
                    "machine_statement": candidate.statement,
                    "coverage_kind": "cross-cutting",
                    "coverage_note": (
                        "Source-derived normative statement retained at clause scope; "
                        "no modeled state transition was asserted."
                    ),
                    "api_surface_scope": "cross-cutting",
                    "api_surface_note": "The source statement has no direct API mapping asserted.",
                    "extraction": "explicit",
                }
            )
        else:
            update = {
                "statement": candidate.statement,
                "machine_statement": candidate.statement,
                "title": f"Normative statement at {candidate.source.path}:{candidate.source.line}",
                "clause": candidate.clause,
                "clause_id": candidate.clause_id,
                "source": candidate.source,
                "extraction": "explicit",
            }
            payload = old.model_copy(update=update)
        records.append(payload)

    if root.name == "hla-1516.1-2010":
        records = [
            item.model_copy(update=_2010_API_DISPOSITIONS[item.id])
            if item.id in _2010_API_DISPOSITIONS
            else item
            for item in records
        ]

    if len(records) != len(candidates) or len({item.id for item in records}) != len(records):
        raise ValueError(
            f"{root.name}: generated requirement IDs are not a unique candidate closure"
        )
    write_json(
        requirement_path,
        RequirementFile(
            schema_version=existing_payload.schema_version,
            requirements=tuple(records),
        ).model_dump(mode="json"),
    )
    unique_aliases = {str(item["alias_id"]): item for item in aliases}
    write_json(
        aliases_path,
        {"schema_version": 1, "aliases": list(unique_aliases.values())},
    )
    return _RequirementCatalogBuildReport(
        document=root.name,
        before=len(existing),
        source_candidates=len(candidates),
        after=len(records),
        preserved_ids=len(matched_old),
        new_ids=len(records) - len(matched_candidates),
        unmatched_candidates=len(candidates) - len(matched_candidates),
        aliases=len(unique_aliases),
    )


def _update_ownership(root: Path) -> None:
    """Attach every catalog ID to its authored content block and element."""

    semantic = DocumentResources(root).semantic
    requirements = RequirementFile.model_validate_json(
        (semantic / "requirements.json").read_text(encoding="utf-8")
    ).requirements
    ids_by_path: dict[str, tuple[str, ...]] = defaultdict(tuple)
    for item in requirements:
        ids_by_path[item.source.path] = (*ids_by_path[item.source.path], item.id)
    aliases_path = semantic / "requirement-id-aliases.json"
    removed_ids = (
        {
            str(item["alias_id"])
            for item in json.loads(aliases_path.read_text(encoding="utf-8")).get("aliases", [])
        }
        if aliases_path.is_file()
        else set()
    )
    # A prior interrupted run may have written the promoted requirements before
    # it could write the alias file.  Treat any orphaned requirement-shaped ID
    # as retired as well; non-requirement record IDs remain untouched.
    requirement_ids = {item.id for item in requirements}

    blocks_path = semantic / "content-blocks.json"
    blocks_payload = json.loads(blocks_path.read_text(encoding="utf-8"))
    for block in blocks_payload.get("content_blocks", []):
        path = str(block["source"]["path"])
        additions = ids_by_path.get(path, ())
        values = tuple(
            dict.fromkeys(
                item
                for item in (*block.get("record_ids", []), *additions)
                if item not in removed_ids
                and not (item.startswith("req-") and item not in requirement_ids)
            )
        )
        block["record_ids"] = list(values)
    write_json(blocks_path, blocks_payload)

    elements_path = semantic / "content-elements.json"
    elements_payload = json.loads(elements_path.read_text(encoding="utf-8"))
    block_ids = {
        str(block["id"]): tuple(block.get("record_ids", []))
        for block in blocks_payload.get("content_blocks", [])
    }
    for element in elements_payload.get("content_elements", []):
        additions = block_ids.get(str(element.get("block_id")), ())
        values = tuple(
            dict.fromkeys(
                item
                for item in (*element.get("record_ids", []), *additions)
                if item not in removed_ids
                and not (item.startswith("req-") and item not in requirement_ids)
            )
        )
        element["record_ids"] = list(values)
    write_json(elements_path, elements_payload)


def _canonicalize(root: Path) -> int:
    if root.name == "hla-1516.1-2010":
        # The API binding file is validated together with the document model;
        # prune legacy aliases before loading the model so an interrupted
        # promotion can be resumed safely.
        semantic = DocumentResources(root).semantic
        requirements = RequirementFile.model_validate_json(
            (semantic / "requirements.json").read_text(encoding="utf-8")
        ).requirements
        requirement_ids = {item.id for item in requirements}
        bindings_path = semantic / "api-requirement-bindings.json"
        bindings_payload = json.loads(bindings_path.read_text(encoding="utf-8"))
        bindings_payload["bindings"] = [
            item
            for item in bindings_payload.get("bindings", [])
            if item.get("requirement_id") in requirement_ids
        ]
        write_json(bindings_path, bindings_payload)
    model = load_hla_document_model(root)
    ordered = model.ordered_requirements()
    semantic = DocumentResources(root).semantic
    path = semantic / "requirements.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    write_json(
        path,
        RequirementFile(
            schema_version=payload.get("schema_version", 1), requirements=ordered
        ).model_dump(mode="json"),
    )
    aliases_path = semantic / "requirement-id-aliases.json"
    if not aliases_path.is_file():
        write_json(aliases_path, {"schema_version": 1, "aliases": []})
    if root.name == "hla-1516.1-2010":
        write_json(
            semantic / "api-requirement-bindings.json",
            {
                "schema_version": 1,
                "bindings": [
                    item.model_dump(mode="json")
                    for item in build_requirement_api_bindings(load_hla_document_model(root))
                ],
            },
        )
    return len(ordered)


def build(
    roots: tuple[Path, ...] | None = None, *, dry_run: bool = False
) -> tuple[_RequirementCatalogBuildReport, ...]:
    roots = roots if roots is not None else tuple(document_root(document) for document in DOCUMENTS)
    reports: list[_RequirementCatalogBuildReport] = []
    for root in roots:
        if root.name.endswith("-2010"):
            if dry_run:
                model = load_hla_document_model(root)
                candidates = _requirements(root, _surface_inputs(root))
                reports.append(
                    _RequirementCatalogBuildReport(
                        document=root.name,
                        before=len(model.requirements),
                        source_candidates=len(candidates),
                        after=len(candidates),
                        dry_run=True,
                    )
                )
                continue
            report = _promote_2010(root)
            _update_ownership(root)
            reports.append(report.model_copy(update={"canonical_count": _canonicalize(root)}))
        else:
            if not dry_run:
                reports.append(
                    _RequirementCatalogBuildReport(
                        document=root.name,
                        before=len(load_hla_document_model(root).requirements),
                        canonical_count=_canonicalize(root),
                    )
                )
            else:
                reports.append(
                    _RequirementCatalogBuildReport(
                        document=root.name,
                        before=len(load_hla_document_model(root).requirements),
                        dry_run=True,
                    )
                )
    return tuple(reports)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            [
                report.model_dump(mode="json", exclude_unset=True)
                for report in build(
                    tuple(root.resolve() for root in args.roots) if args.roots else None,
                    dry_run=args.dry_run,
                )
            ],
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
