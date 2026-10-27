"""Measure source-line fragments that can be rebuilt as whole sentences."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from itertools import pairwise
from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import RequirementFile
from hla_lab.core.semantic_model_authored import _load_authored_content_blocks
from hla_lab.core.semantic_model_records import (
    _command_events,
    _heading_context_by_file,
    _load_requirement_candidates,
    _requirement_candidate_units,
)
from hla_lab.core.semantic_text import _machine_statement
from tools.migrations.workspace import document_root


def sentence_matches(root: Path) -> tuple[list[dict[str, object]], Counter[str]]:
    requirements = RequirementFile.model_validate_json(
        (root / "semantic/requirements.json").read_text(encoding="utf-8")
    )
    candidates = _load_requirement_candidates(root, HLA_SOURCE)
    by_path = defaultdict(list)
    for item in candidates:
        by_path[item.source.path].append(item)
    units = {
        path.relative_to(root).as_posix(): body
        for path, body, _ in _requirement_candidate_units(
            root,
            HLA_SOURCE,
            _heading_context_by_file(root, HLA_SOURCE),
            _load_authored_content_blocks(root),
        )
    }
    events = {}
    for path, body in units.items():
        by_line = {}
        for offset, args, end in _command_events(body, HLA_SOURCE.fixed_text_block, 7):
            line = body.count("\n", 0, offset) + 1
            by_line[line] = (args, body.count("\n", 0, end) + 1)
        events[path] = by_line

    rows = []
    counts: Counter[str] = Counter()
    for requirement in requirements.requirements:
        if not requirement.id.startswith("requirement-candidate-content-clauses-"):
            continue
        path = requirement.source.path
        anchor = requirement.source.line
        matched = [
            item
            for item in by_path[path]
            if item.source.line <= anchor <= (item.source.end_line or item.source.line)
        ]
        if len(matched) != 1 or anchor not in events[path]:
            counts["no_unique_passage"] += 1
            continue
        passage = matched[0]
        blocks = [
            (line, args, end)
            for line, (args, end) in events[path].items()
            if passage.source.line <= line <= (passage.source.end_line or passage.source.line)
        ]
        blocks.sort()
        text_parts = []
        intervals = []
        position = 0
        for line, args, end in blocks:
            piece = _machine_statement(args[-1], HLA_SOURCE)
            piece = re.sub(r"\s*%", " ", piece).strip()
            if not piece:
                continue
            text_parts.append(piece)
            intervals.append((position, position + len(piece), line, end, piece))
            position += len(piece) + 1
        passage_text = " ".join(text_parts)
        anchored = next((item for item in intervals if item[2] == anchor), None)
        if anchored is None:
            counts["no_anchor"] += 1
            continue
        shall = re.search(r"\bshall\b", anchored[4], re.IGNORECASE)
        if shall is None:
            counts["no_shall_on_anchor"] += 1
            continue
        target = anchored[0] + shall.start()
        cuts = [
            0,
            *[m.end() for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z(])", passage_text)],
            len(passage_text),
        ]
        sentence = next(
            ((start, end) for start, end in pairwise(cuts) if start <= target < end), None
        )
        if sentence is None:
            counts["no_sentence"] += 1
            continue
        start, end = sentence
        wording = passage_text[start:end].strip()
        covered = [item for item in intervals if item[0] < end and item[1] > start]
        if not covered:
            counts["no_covered_blocks"] += 1
            continue
        row = {
            "id": requirement.id,
            "path": path,
            "old_statement": requirement.statement,
            "new_statement": wording,
            "old_source": requirement.source.model_dump(mode="json"),
            "new_source": {"path": path, "line": covered[0][2], "end_line": covered[-1][3]},
            "passage_id": passage.id,
        }
        rows.append(row)
        counts["mapped"] += 1
    by_sentence = Counter(
        (
            row["path"],
            row["new_source"]["line"],
            row["new_source"]["end_line"],
            row["new_statement"],
        )
        for row in rows
    )
    for row in rows:
        row["duplicate_count"] = by_sentence[
            row["path"],
            row["new_source"]["line"],
            row["new_source"]["end_line"],
            row["new_statement"],
        ]
    counts["unique_sentences"] = sum(row["duplicate_count"] == 1 for row in rows)
    counts["duplicate_sentences"] = sum(row["duplicate_count"] > 1 for row in rows)
    return rows, counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows, counts = sentence_matches(document_root("hla-1516.1-2025", args.workspace_root))
    args.output.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(dict(counts))


if __name__ == "__main__":
    main()
