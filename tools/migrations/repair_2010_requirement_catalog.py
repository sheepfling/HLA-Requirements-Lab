"""Repair the source/provenance surface of the three 2010 requirement catalogs.

The first 2010 promotion was intentionally conservative, but its line-local
extractor preserved layout markers, stale source lines, and incomplete
sentences.  This migration keeps existing requirement IDs where they can be
matched, reconstructs the framework's sentence-level records, and attaches
the resulting IDs to the source-owned content blocks and elements consumed by
the RTI-facing adapters.

The migration is deliberately separate from the closed promotion migration:
rerunning it is safe, while the completed promotion remains read-only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from hla_lab.core.io import write_json
from hla_lab.core.parsing import line_number, try_balanced_group
from hla_lab.core.semantic_model import RequirementApiBindingFile
from hla_lab.corpus.api_crosswalk import build_requirement_api_bindings
from hla_lab.corpus.hla_2010_semantic import _plain
from hla_lab.corpus.hla_semantic import load_hla_document_model
from hla_lab.paths import RESOURCES, DocumentResources

ROOTS = tuple(
    RESOURCES.document(document).root
    for document in ("hla-1516-2010", "hla-1516.1-2010", "hla-1516.2-2010")
)
FRAMEWORK = "hla-1516-2010"
_BREAK = re.compile(r"\\(?:linebreak|newline|newpage)\b")
_COMMAND_BOUNDARY = re.compile(
    r"^\\(?:clause|subclause|subsubclause|federationrulesubclause|"
    r"federaterulesubclause|annexsection|annexsubsection|annexdesignation|"
    r"annexstatus|annextitle)\b"
)
_SENTENCE_END = re.compile(r"[.!?](?=\s+[A-Z0-9`\"(\[]|$)")
_INCOMPLETE_END = re.compile(
    r"(?:a|an|and|as|at|be|by|can|for|from|if|in|into|is|of|on|or|that|the|"
    r"their|these|this|to|under|was|were|which|with|shall|must)$",
    re.IGNORECASE,
)
_STOP_WORDS = {
    "about",
    "after",
    "also",
    "among",
    "and",
    "any",
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


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


@dataclass(frozen=True)
class Candidate:
    path: str
    line: int
    end_line: int
    offset: int
    statement: str
    kind: str


def _clean(value: str) -> str:
    """Turn a legacy source slice into stable plain text."""

    value = re.sub(r"(?m)^\s*%.*$", " ", value)
    value = re.sub(r"(?m)(?<!\\)%.*$", " ", value)
    value = _BREAK.sub(" ", value)
    value = value.replace(r"\\", " ")
    value = re.sub(r"\\(?:vspace|hspace|addvspace)\*?\s*\{[^{}]*\}", " ", value)
    value = _plain(value)
    value = value.replace("\\", " ")
    return re.sub(r"\s+", " ", value).strip(" ;")


def _tokens(value: str) -> tuple[str, ...]:
    return tuple(
        token
        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", value.casefold())
        if token not in _STOP_WORDS
    )


def _source_lines(text: str) -> tuple[str, ...]:
    return tuple(text.splitlines())


def _find_anchor_line(text: str, statement: str, original_line: int) -> int:
    """Find the authored line even when a fidelity pass shifted old spans."""

    lines = _source_lines(text)
    wanted = _tokens(statement)[:6]
    if not wanted:
        return max(1, min(original_line, len(lines)))
    best: tuple[int, int, int] | None = None
    for number, raw in enumerate(lines, 1):
        cleaned = _clean(raw).casefold()
        score = sum(token in cleaned for token in wanted)
        if score < min(2, len(wanted)):
            continue
        distance = abs(number - original_line)
        candidate = (score, -distance, -number)
        if best is None or candidate > best:
            best = candidate
    return -best[2] if best is not None else max(1, min(original_line, len(lines)))


def _joined_lines(lines: list[tuple[int, str]]) -> tuple[str, tuple[int, ...]]:
    pieces: list[str] = []
    mapping: list[int] = []
    for number, raw in lines:
        cleaned = _clean(raw)
        if not cleaned:
            continue
        if pieces:
            pieces.append(" ")
            mapping.append(number)
        pieces.append(cleaned)
        mapping.extend([number] * len(cleaned))
    return "".join(pieces), tuple(mapping)


def _sentences(lines: list[tuple[int, str]], path: str, offset: int) -> tuple[Candidate, ...]:
    joined, mapping = _joined_lines(lines)
    if not joined:
        return ()
    starts = [0]
    starts.extend(match.end() for match in _SENTENCE_END.finditer(joined))
    candidates: list[Candidate] = []
    for start, end in zip(starts, (*starts[1:], len(joined)), strict=True):
        statement = joined[start:end].strip()
        if not re.search(r"\b(?:shall|must)\b", statement, re.IGNORECASE):
            continue
        left = start + len(joined[start:end]) - len(joined[start:end].lstrip())
        right = end - len(joined[start:end]) + len(joined[start:end].rstrip())
        if right <= left or not mapping:
            continue
        span_lines = mapping[max(0, left) : min(len(mapping), right)]
        if not span_lines:
            continue
        candidates.append(
            Candidate(
                path=path,
                line=min(span_lines),
                end_line=max(span_lines),
                offset=offset + start,
                statement=statement,
                kind="detailed",
            )
        )
    return tuple(candidates)


def _paragraphs(path: Path, text: str) -> tuple[list[tuple[int, str]], ...]:
    lines = _source_lines(text)
    result: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    for number, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if not stripped:
            # Blank lines are layout spacing in the legacy source.  Keeping
            # them inside a section lets a sentence continue over a page
            # break or a fidelity-only paragraph gap.
            continue
        if _COMMAND_BOUNDARY.match(stripped):
            if current:
                result.append(current)
                current = []
            continue
        # A page break in the middle of a source paragraph is whitespace, not
        # an ownership boundary.  This repairs the 2010 Rule 2 split.
        current.append((number, raw))
    if current:
        result.append(current)
    return tuple(result)


def _framework_candidates(root: Path, path: Path, text: str) -> tuple[Candidate, ...]:
    relative = path.relative_to(root).as_posix()
    candidates: list[Candidate] = []

    for match in re.finditer(r"\\textit\s*\{", text):
        parsed = try_balanced_group(text, match.end() - 1)
        if parsed is None:
            continue
        body, end = parsed
        statement = _clean(body)
        if not re.search(r"\b(?:shall|must)\b", statement, re.IGNORECASE):
            continue
        candidates.append(
            Candidate(
                path=relative,
                line=line_number(text, match.start()),
                end_line=line_number(text, end),
                offset=match.start(),
                statement=statement,
                kind="detailed",
            )
        )

    if relative == "clauses/04-summary-hla-rules.tex":
        items = list(re.finditer(r"\\item\b", text))
        for index, match in enumerate(items):
            next_start = (
                items[index + 1].start()
                if index + 1 < len(items)
                else text.find(r"\end{hlarules}", match.end())
            )
            if next_start < 0:
                next_start = len(text)
            statement = _clean(text[match.end() : next_start])
            if not re.search(r"\b(?:shall|must)\b", statement, re.IGNORECASE):
                continue
            candidates.append(
                Candidate(
                    path=relative,
                    line=line_number(text, match.start()),
                    end_line=line_number(text, max(match.end(), next_start - 1)),
                    offset=match.start(),
                    statement=statement,
                    kind="summary",
                )
            )

    for paragraph in _paragraphs(path, text):
        candidates.extend(
            _sentences(
                paragraph,
                relative,
                sum(len(line) + 1 for line in text.splitlines()[: paragraph[0][0] - 1]),
            )
        )

    # The direct rule and paragraph scanners intentionally overlap.  Keep the
    # strongest source span for each normalized statement.
    unique: dict[str, Candidate] = {}
    for candidate in candidates:
        key = _normalize(candidate.statement)
        prior = unique.get(key)
        if prior is None or (candidate.kind == "summary", candidate.end_line - candidate.line) < (
            prior.kind == "summary",
            prior.end_line - prior.line,
        ):
            unique[key] = candidate
    return tuple(sorted(unique.values(), key=lambda item: (item.line, item.offset)))


def _generic_repair(root: Path, requirement: dict[str, object]) -> tuple[str, int, int]:
    source = requirement["source"]
    assert isinstance(source, dict)
    path = str(source["path"])
    text = (root / path).read_text(encoding="utf-8")
    statement = str(requirement.get("statement", ""))
    anchor = _find_anchor_line(text, statement, int(source["line"]))
    lines = _source_lines(text)
    end = anchor
    cleaned = _clean(statement)
    if _INCOMPLETE_END.search(cleaned.split()[-1] if cleaned.split() else ""):
        pieces = [_clean(lines[anchor - 1])] if lines else [cleaned]
        while end < len(lines) and end - anchor < 60:
            next_line = _clean(lines[end])
            if next_line:
                pieces.append(next_line)
            end += 1
            if re.search(r"[.!?]\s*$", " ".join(pieces)):
                break
        cleaned = " ".join(piece for piece in pieces if piece).strip(" ;")
    return cleaned, anchor, max(anchor, end)


def _candidate_score(requirement: dict[str, object], candidate: Candidate) -> tuple[int, int, int]:
    source = requirement["source"]
    assert isinstance(source, dict)
    old_line = int(source["line"])
    wanted = set(_tokens(str(requirement.get("statement", ""))))
    actual = set(_tokens(candidate.statement))
    overlap = len(wanted & actual)
    exact = int(
        _normalize(_clean(str(requirement.get("statement", ""))))
        in _normalize(candidate.statement)
    )
    return exact, overlap, -abs(candidate.line - old_line)


def _framework_rule_group(path: str, statement: str, line: int | None = None) -> str:
    if line is not None:
        if path == "clauses/04-summary-hla-rules.tex":
            rule = {
                12: 1,
                13: 2,
                15: 3,
                17: 4,
                19: 5,
                27: 6,
                28: 7,
                30: 8,
                32: 9,
                34: 10,
            }.get(line)
            if rule is not None:
                return f"framework-rule-{rule}"
        if path == "clauses/05-federation-rules.tex":
            rule = 1 if line < 33 else 2 if line < 48 else 3 if line < 73 else 4 if line < 86 else 5
            return f"framework-rule-{rule}"
        if path == "clauses/06-federate-rules.tex":
            rule = (
                6 if line < 24 else 7 if line < 36 else 8 if line < 47 else 9 if line < 60 else 10
            )
            return f"framework-rule-{rule}"
    if path == "clauses/05-federation-rules.tex":
        return "m2010.clause.5"
    if path == "clauses/06-federate-rules.tex":
        return "m2010.clause.6"
    if path == "clauses/annex-a-rationale.tex" and line is not None:
        rule = {
            21: 1,
            34: 2,
            55: 3,
            69: 4,
            84: 5,
            90: 5,
            103: 6,
            126: 7,
            136: 8,
            148: 9,
            159: 10,
            178: 10,
        }.get(line)
        if rule is not None:
            return f"framework-rule-{rule}"
    if path.startswith("clauses/0"):
        number = path.split("/")[1].split("-")[0].lstrip("0") or "0"
        return f"m2010.clause.{number}"
    return "m2010.unclassified"


def _update_content_links(
    root: Path, requirement_ids_by_path: dict[str, tuple[str, ...]]
) -> tuple[int, int]:
    semantic = DocumentResources(root).semantic
    blocks_path = semantic / "content-blocks.json"
    elements_path = semantic / "content-elements.json"
    blocks_payload = json.loads(blocks_path.read_text(encoding="utf-8"))
    elements_payload = json.loads(elements_path.read_text(encoding="utf-8"))
    source_paths = tuple(requirement_ids_by_path)

    def ids_for(path: str) -> tuple[str, ...]:
        path_obj = Path(path)
        stem = path_obj.stem
        related = tuple(
            requirement_ids_by_path[item]
            for item in source_paths
            if item != path
            and Path(item).parent == path_obj.parent
            and (stem.startswith(Path(item).stem) or Path(item).stem.startswith(stem))
        )
        exact = requirement_ids_by_path.get(path, ())
        identifiers = (identifier for group in related for identifier in group)
        return tuple(dict.fromkeys((*exact, *identifiers)))

    block_count = 0
    for block in blocks_payload["content_blocks"]:
        additions = ids_for(str(block["source"]["path"]))
        if not additions:
            continue
        values = tuple(dict.fromkeys((*block.get("record_ids", []), *additions)))
        if list(values) != block.get("record_ids", []):
            block["record_ids"] = list(values)
            block_count += 1
    element_count = 0
    for element in elements_payload["content_elements"]:
        additions = ids_for(str(element["source"]["path"]))
        if not additions:
            continue
        values = tuple(dict.fromkeys((*element.get("record_ids", []), *additions)))
        if list(values) != element.get("record_ids", []):
            element["record_ids"] = list(values)
            element_count += 1
    write_json(blocks_path, blocks_payload)
    write_json(elements_path, elements_payload)
    return block_count, element_count


def repair(root: Path, *, dry_run: bool = False) -> dict[str, object]:
    semantic = DocumentResources(root).semantic
    requirements_path = semantic / "requirements.json"
    payload = json.loads(requirements_path.read_text(encoding="utf-8"))
    requirements = list(payload["requirements"])
    original_count = len(requirements)
    candidates_by_path: dict[str, tuple[Candidate, ...]] = {}
    if root.name == FRAMEWORK:
        for path in sorted(root.rglob("*.tex")):
            if path.name == "main.tex" or "output" in path.parts:
                continue
            candidates_by_path[path.relative_to(root).as_posix()] = _framework_candidates(
                root, path, path.read_text(encoding="utf-8")
            )

    repaired: list[dict[str, object]] = []
    used_candidates: set[tuple[str, int]] = set()
    fallback_ids: list[str] = []
    for requirement in requirements:
        source = requirement["source"]
        assert isinstance(source, dict)
        path = str(source["path"])
        candidate: Candidate | None = None
        if root.name == FRAMEWORK:
            available = [
                item
                for item in candidates_by_path.get(path, ())
                if (item.path, item.offset) not in used_candidates
            ]
            if available:
                candidate = max(available, key=lambda item: _candidate_score(requirement, item))
                # Do not assign a low-overlap sentence merely because it is
                # nearby; the fallback below keeps the record traceable.
                if _candidate_score(requirement, candidate)[1] < 2:
                    candidate = None
        if candidate is None:
            statement, line, end_line = _generic_repair(root, requirement)
            fallback_ids.append(str(requirement["id"]))
        else:
            used_candidates.add((candidate.path, candidate.offset))
            statement, line, end_line = candidate.statement, candidate.line, candidate.end_line
        requirement["statement"] = statement
        requirement["machine_statement"] = statement
        requirement["source"] = {"path": path, "line": line, "end_line": end_line}
        requirement["title"] = f"Normative statement at {path}:{line}"
        if root.name == FRAMEWORK:
            if path == "clauses/04-summary-hla-rules.tex":
                requirement["kind"] = "summary"
            if path == "clauses/annex-a-rationale.tex":
                requirement.update(
                    {
                        "coverage_kind": "not-applicable",
                        "coverage_note": (
                            "Informative Annex A rationale quotation retained for source "
                            "traceability; it is not a normative implementation obligation."
                        ),
                        "api_surface_scope": "not-applicable",
                        "api_surface_note": "Informative rationale has no direct API surface.",
                    }
                )
            requirement["semantic_group_id"] = _framework_rule_group(path, statement, line)
        repaired.append(requirement)

    # The line-local extractor collapsed the two normative sentences on Rule
    # 3's responsibility line into one record. Add only genuinely unassigned
    # clause-5/6 sentences, preserving all existing IDs.
    if root.name == FRAMEWORK:
        existing = {_normalize(str(item["statement"])) for item in repaired}
        for path in ("clauses/05-federation-rules.tex", "clauses/06-federate-rules.tex"):
            for candidate in candidates_by_path.get(path, ()):
                normalized = _normalize(candidate.statement)
                if normalized in existing or (
                    candidate.path,
                    candidate.offset,
                ) in used_candidates:
                    continue
                identifier = (
                    "req-"
                    f"{hashlib.sha1(f'{candidate.path}:{candidate.offset}'.encode()).hexdigest()[:12]}"
                )
                if any(item["id"] == identifier for item in repaired):
                    continue
                clause = "5" if path.startswith("clauses/05") else "6"
                repaired.append(
                    {
                        "id": identifier,
                        "title": f"Normative statement {path}:{candidate.line}",
                        "statement": candidate.statement,
                        "kind": "detailed",
                        "clause": clause,
                        "clause_id": f"clause-{clause}",
                        "machine_statement": candidate.statement,
                        "transition_ids": [],
                        "coverage_kind": "cross-cutting",
                        "coverage_note": (
                            "Source-derived normative statement retained at clause scope; "
                            "no modeled state transition was asserted."
                        ),
                        "extraction": "explicit",
                        "semantic_group_id": _framework_rule_group(
                            path, candidate.statement, candidate.line
                        ),
                        "source": {
                            "path": path,
                            "line": candidate.line,
                            "end_line": candidate.end_line,
                        },
                    }
                )
                existing.add(normalized)

    # Keep the catalog itself in source order; consumers use IDs as joins, not
    # as an implicit ordering key.
    source_paths = {str(item["source"]["path"]) for item in repaired}
    source_order = {path: index for index, path in enumerate(sorted(source_paths))}
    repaired.sort(
        key=lambda item: (
            source_order[str(item["source"]["path"])],
            int(item["source"]["line"]),
            str(item["id"]),
        )
    )
    requirement_ids_by_path: dict[str, tuple[str, ...]] = {}
    for item in repaired:
        path = str(item["source"]["path"])
        requirement_ids_by_path.setdefault(path, ())
        requirement_ids_by_path[path] += (str(item["id"]),)

    blocks = elements = 0
    if not dry_run:
        write_json(
            requirements_path,
            {
                "schema_version": payload.get("schema_version", 1),
                "requirements": repaired,
            },
        )
        blocks, elements = _update_content_links(root, requirement_ids_by_path)
        if root.name == "hla-1516.1-2010":
            model = load_hla_document_model(root)
            write_json(
                semantic / "api-requirement-bindings.json",
                RequirementApiBindingFile(
                    schema_version=1,
                    bindings=build_requirement_api_bindings(model),
                ).model_dump(mode="json"),
            )
    return {
        "document": root.name,
        "requirements_before": original_count,
        "requirements_after": len(repaired),
        "fallbacks": tuple(fallback_ids),
        "content_blocks_updated": blocks,
        "content_elements_updated": elements,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="*", type=Path, default=ROOTS)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    for root in args.roots:
        result = repair(root, dry_run=args.dry_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
