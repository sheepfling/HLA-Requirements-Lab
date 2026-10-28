"""Install the repository-pinned PlantUML renderer."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path


def install(root: Path) -> Path:
    """Download and verify the pinned PlantUML jar under ``root``."""
    lock_path = root / "tools" / "plantuml" / "plantuml.lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    version = lock["version"]
    url = lock["url"]
    expected_sha256 = lock["sha256"].lower()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError(f"Invalid SHA-256 in {lock_path}")

    jar = root / ".tools" / "plantuml" / f"plantuml-{version}.jar"
    if jar.is_file() and hashlib.sha256(jar.read_bytes()).hexdigest() == expected_sha256:
        return jar

    with urllib.request.urlopen(url, timeout=120) as response:
        content = response.read()
    actual_sha256 = hashlib.sha256(content).hexdigest()
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"PlantUML checksum mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    jar.parent.mkdir(parents=True, exist_ok=True)
    temporary = jar.with_suffix(".jar.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(jar)
    finally:
        temporary.unlink(missing_ok=True)
    return jar


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    print(install(args.root.resolve()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
