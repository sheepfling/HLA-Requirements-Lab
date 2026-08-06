"""Promote the HLA 1516 definition layout bodies into semantic source."""

from __future__ import annotations

import json
import re
from pathlib import Path

try:
    from scripts.hla_profile import HLA_SOURCE
    from scripts.semantic_model import Definition, SourceRef, load_document_model
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from hla_profile import HLA_SOURCE
    from semantic_model import Definition, SourceRef, load_document_model


DEFINITION_PATTERN = re.compile(
    r"\\begin\{hladefinition\}(?:\[([^\]]+)\])?\{([^{}]+)\}\{([^{}]+)\}"
    r"(.*?)\\end\{hladefinition\}",
    re.DOTALL,
)


def _source_definitions(root: Path) -> dict[str, tuple[str | None, str]]:
    found: dict[str, tuple[str | None, str]] = {}
    for path in sorted((root / "sections" / "semantic" / "definitions").glob("page-*.tex")):
        text = path.read_text(encoding="utf-8")
        for match in DEFINITION_PATTERN.finditer(text):
            leading_gap, identifier, _term, body = match.groups()
            if identifier in found:
                raise ValueError(f"duplicate definition source: {identifier}")
            found[identifier] = (leading_gap, body.strip("\n"))
    return found


def migrate(root: Path, output: Path) -> Path:
    """Write all parsed 1516 definitions as authored semantic source."""
    model = load_document_model(root, HLA_SOURCE)
    layout = _source_definitions(root)
    missing = sorted(
        item.id
        for item in model.definitions
        if item.id not in layout and item.source.path != "semantic/definitions.json"
    )
    extra = sorted(set(layout) - {item.id for item in model.definitions})
    if missing or extra:
        raise ValueError(f"definition source mismatch: missing={missing}, extra={extra}")

    records = []
    for item in model.ordered_definitions():
        leading_gap, body = layout.get(item.id, (None, None))
        records.append(
            Definition(
                id=item.id,
                term=item.term,
                text=item.text,
                layout_body=body,
                leading_gap=leading_gap,
                source=SourceRef(path="semantic/definitions.json", line=1),
                clause_id=item.clause_id,
            )
        )
    payload = {
        "schema_version": 1,
        "definitions": [item.model_dump(mode="json") for item in records],
    }
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    line_numbers = {
        identifier: index
        for index, line in enumerate(rendered.splitlines(), start=1)
        for identifier in [
            next((item.id for item in records if f'"id": "{item.id}"' in line), None)
        ]
        if identifier is not None
    }
    records = [
        item.model_copy(
            update={
                "source": SourceRef(path="semantic/definitions.json", line=line_numbers[item.id])
            }
        )
        for item in records
    ]
    payload["definitions"] = [item.model_dump(mode="json") for item in records]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("topics/ieee/hla-1516-2025"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("topics/ieee/hla-1516-2025/semantic/definitions.json"),
    )
    args = parser.parse_args()
    print(migrate(args.root, args.output))
