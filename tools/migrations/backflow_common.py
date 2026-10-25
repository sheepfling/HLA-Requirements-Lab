"""Shared paths and JSON helpers for the 1516.1 backflow repair."""

from __future__ import annotations

import json
from pathlib import Path

from hla_lab.core.json_types import JsonObject
from hla_lab.paths import resources

PAGE_216 = "requirement-candidate-content-clauses-08-time-management-page-216-l"
FEDERATION = "requirement-candidate-content-clauses-04-federation-management-page-"
OBJECTS = "requirement-candidate-content-clauses-06-object-management-page-"
TIME = "requirement-candidate-content-clauses-08-time-management-page-"
DDM = "requirement-candidate-content-clauses-09-data-distribution-management-page-"
SUPPORT = "requirement-candidate-content-clauses-10-support-services-page-"
OWNERSHIP = "requirement-candidate-content-clauses-07-ownership-management-page-"
DECLARATION = "requirement-candidate-content-clauses-05-declaration-management-page-"
MOM = "requirement-candidate-content-clauses-11-management-object-model-page-"


def semantic_root(workspace_root: Path | None = None) -> Path:
    return resources(workspace_root).document("hla-1516.1-2025").semantic


def omt_semantic_root(workspace_root: Path | None = None) -> Path:
    return resources(workspace_root).document("hla-1516.2-2025").semantic


def _read(name: str) -> JsonObject:
    return json.loads((semantic_root() / name).read_text(encoding="utf-8"))


def _write(name: str, payload: JsonObject) -> None:
    (semantic_root() / name).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _set_statement(record: JsonObject, statement: str, line: int, end_line: int) -> None:
    record["statement"] = statement
    record["machine_statement"] = statement
    record["source"]["line"] = line
    record["source"]["end_line"] = end_line
    record["title"] = f"Normative statement at {record['source']['path']}:{line}"


def _set_clause(record: JsonObject, clause: str) -> None:
    record["clause"] = clause
    record["clause_id"] = f"clause-{clause}"
    record["semantic_group_id"] = f"m16.clause.{clause}"
