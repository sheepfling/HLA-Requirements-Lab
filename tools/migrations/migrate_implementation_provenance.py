"""Attach source provenance to authored implementation mapping records."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from hla_lab.core.io import write_json

def _record_lines(path: Path) -> dict[str, int]:
    lines = path.read_text(encoding="utf-8").splitlines()
    result: dict[str, int] = {}
    for line_number, line in enumerate(lines, start=1):
        match = re.search(r'^\s*"id":\s*"([^"]+)"', line)
        if match:
            result[match.group(1)] = line_number
    return result

def migrate(path: Path, *, check: bool = False) -> int:
    payload = json.loads(path.read_text(encoding="utf-8"))
    line_numbers = _record_lines(path)
    missing = [item["id"] for item in payload["implementations"] if item.get("source") is None]
    if check:
        print(f"{path}: {len(missing)} implementation records lack source provenance")
        return 1 if missing else 0
    for item in payload["implementations"]:
        if item.get("source") is not None:
            continue
        record_id = item["id"]
        item["source"] = {
            "path": path.parent.name + "/" + path.name,
            "line": line_numbers[record_id],
        }
    write_json(path, payload)
    print(f"{path}: attached provenance to {len(missing)} implementation records")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return migrate(args.path, check=args.check)

if __name__ == "__main__":
    raise SystemExit(main())
