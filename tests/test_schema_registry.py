"""The package's Pydantic models own every published JSON contract."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from hla_lab.schemas import (
    SCHEMA_NAMES,
    main,
    model_for,
    schema_for,
    validate_payload,
    write_schema,
)
from tests.support import TEST_REPO_ROOT


def test_every_contract_has_a_pydantic_model_and_exportable_schema(tmp_path: Path) -> None:
    assert len(SCHEMA_NAMES) == 9
    for name in SCHEMA_NAMES:
        model = model_for(name)
        schema = schema_for(name)
        assert schema["title"] == model.__name__
        assert urlsplit(schema["$id"]).path == f"/schemas/{name}.schema.json"
        destination = write_schema(name, tmp_path / f"{name}.schema.json")
        assert json.loads(destination.read_text(encoding="utf-8")) == schema


def test_runtime_validation_uses_the_same_model_as_schema_export() -> None:
    root = TEST_REPO_ROOT
    payload = json.loads(
        (root / "examples/compliance-test-catalog.json").read_text(encoding="utf-8")
    )
    catalog = validate_payload("compliance_test_catalog", payload)
    assert catalog.tests
    with pytest.raises(ValueError, match="unknown contract"):
        model_for("missing")


def test_standalone_schema_command_exports_without_corpus_root(tmp_path: Path) -> None:
    output = tmp_path / "requirements.schema.json"
    assert main(["requirements", "--output", str(output)]) == 0
    assert json.loads(output.read_text(encoding="utf-8"))["title"] == "RequirementFile"
