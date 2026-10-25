"""Verify pinned observations in the official IEEE 1516.1-2025 auxiliary archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(archive_path: Path, evidence_path: Path) -> dict[str, object]:
    """Check archive identity, selected entries, and the issue-specific tokens."""
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    archive_bytes = archive_path.read_bytes()
    if _sha256(archive_bytes) != evidence["archive_sha256"]:
        raise ValueError("outer IEEE archive hash differs from the evidence record")
    with ZipFile(BytesIO(archive_bytes)) as outer:
        nested_bytes = outer.read(evidence["nested_archive"]["path"])
    if _sha256(nested_bytes) != evidence["nested_archive"]["sha256"]:
        raise ValueError("nested IEEE archive hash differs from the evidence record")
    verified = []
    with ZipFile(BytesIO(nested_bytes)) as nested:
        for entry in evidence["entries"]:
            content = nested.read(entry["path"])
            if _sha256(content) != entry["sha256"]:
                raise ValueError(f"entry hash differs from the evidence record: {entry['path']}")
            text = content.decode("utf-8")
            if entry["issue_id"] == "RL-256":
                lines = text.splitlines()
                for line_number in (17, 22, 28):
                    if "additionalSettingsResultCode" not in lines[line_number - 1]:
                        raise ValueError(f"RL-256 field absent at Java line {line_number}")
                if "addtionalSettingsResultCode" in text:
                    raise ValueError("RL-256 example typo appeared in the Java declaration")
            elif entry["issue_id"] == "RL-369":
                for name, value in (
                    ("FederateRestoreStatus", "19"),
                    ("FederateRestoreStatusSet", "20"),
                ):
                    pattern = rf"<name>{name}</name>\s*<value>{value}</value>"
                    if re.search(pattern, text) is None:
                        raise ValueError(f"RL-369 MIM value absent: {name}={value}")
                if "FederateHandleRestoreStatusSet" in text:
                    raise ValueError("disputed Table 5 name appeared in the MIM")
            else:
                raise ValueError(f"unexpected issue ID: {entry['issue_id']}")
            verified.append(entry["issue_id"])
    if sorted(verified) != ["RL-256", "RL-369"]:
        raise ValueError("auxiliary evidence did not cover both source questions")
    return {"archive_sha256": evidence["archive_sha256"], "verified_issue_ids": verified}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.archive, args.evidence), indent=2))


if __name__ == "__main__":
    main()
