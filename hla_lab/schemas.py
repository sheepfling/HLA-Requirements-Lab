"""Pydantic-owned JSON contracts for corpus and adapter integrations.

The models are the source of truth. JSON Schema is generated only when an
external consumer needs it; no hand-maintained schema copies are loaded.
"""

from __future__ import annotations

import argparse
import importlib
import json
from collections.abc import Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Any, cast

from pydantic import BaseModel, JsonValue

__all__ = ["SCHEMA_NAMES", "main", "model_for", "schema_for", "validate_payload", "write_schema"]

_MODELS = MappingProxyType(
    {
        "adapter_request": ("hla_lab.traceability.compliance_contract", "AdapterRequest"),
        "compliance_test_catalog": (
            "hla_lab.traceability.compliance_contract",
            "ComplianceTestCatalog",
        ),
        "corpus_bundle": ("hla_lab.traceability.compliance_contract", "CorpusBundle"),
        "graph_diagram": ("hla_lab.core.semantic_model", "GraphDiagramFile"),
        "implementation_mapping": ("hla_lab.core.semantic_model", "ImplementationFile"),
        "requirement_links": ("hla_lab.core.semantic_model", "RequirementLinkFile"),
        "requirements": ("hla_lab.core.semantic_model", "RequirementFile"),
        "sequence_diagram": ("hla_lab.core.semantic_model", "SequenceDiagramFile"),
        "state_machine": ("hla_lab.core.semantic_model", "StateMachineFile"),
    }
)
SCHEMA_NAMES = tuple(sorted(_MODELS))


def model_for(name: str) -> type[BaseModel]:
    """Return the runtime validation model for a public contract name."""
    try:
        module_name, class_name = _MODELS[name]
    except KeyError as error:
        choices = ", ".join(SCHEMA_NAMES)
        raise ValueError(f"unknown contract {name!r}; choose from {choices}") from error
    model = getattr(importlib.import_module(module_name), class_name)
    return cast(type[BaseModel], model)


def validate_payload(name: str, payload: Any) -> BaseModel:
    """Validate JSON-compatible data with its package-owned Pydantic model."""
    return model_for(name).model_validate(payload)


def schema_for(name: str) -> dict[str, JsonValue]:
    """Generate the current JSON Schema for an external adapter or editor."""
    schema = model_for(name).model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://document-recreation.local/schemas/{name}.schema.json",
        **schema,
    }


def write_schema(name: str, destination: Path) -> Path:
    """Export one generated schema without keeping a second authored contract."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(schema_for(name), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return destination


def main(argv: Sequence[str] | None = None) -> int:
    """Export Pydantic schemas from an installed package without corpus access."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", nargs="?", choices=SCHEMA_NAMES)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.list:
        print("\n".join(SCHEMA_NAMES))
        return 0
    if args.all:
        if args.output_dir is None:
            parser.error("--all requires --output-dir")
        for name in SCHEMA_NAMES:
            write_schema(name, args.output_dir / f"{name}.schema.json")
        return 0
    if args.name is None:
        parser.error("supply a contract name or --list")
    if args.output is not None:
        write_schema(args.name, args.output)
    else:
        print(json.dumps(schema_for(args.name), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
