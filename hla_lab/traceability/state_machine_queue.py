"""Show the next extracted diagrams to classify or review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--document")
    parser.add_argument("--status", default="unmodeled")
    args = parser.parse_args()
    payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    entries = [item for item in payload.get("diagrams", []) if item.get("status") == args.status]
    if args.document:
        entries = [item for item in entries if item.get("document") == args.document]
    entries.sort(
        key=lambda item: (item.get("document", ""), item.get("page", 0), item.get("xref", ""))
    )
    print(f"queue: {len(entries)} entries with status={args.status}")
    for item in entries[: args.limit]:
        print(
            f"{item.get('diagram_id')}: document={item.get('document')} "
            f"page={item.get('page')} type={item.get('diagram_type')} "
            f"source={item.get('source_image')}"
        )

if __name__ == "__main__":
    main()
