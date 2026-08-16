from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import fitz

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply a stored outline, page labels, and links to a generated PDF."
    )
    parser.add_argument("input_pdf", type=Path)
    parser.add_argument("navigation_manifest", type=Path)
    parser.add_argument("output_pdf", type=Path)
    return parser.parse_args()

def delete_existing_links(document: fitz.Document) -> None:
    for page in document:
        for link in list(page.get_links()):
            page.delete_link(link)

def insert_link(document: fitz.Document, record: dict[str, Any]) -> None:
    page = document[int(record["source_page"])]
    link_type = str(record["type"])
    link: dict[str, Any] = {"from": fitz.Rect(record["rectangle"])}
    if link_type == "uri":
        link["kind"] = fitz.LINK_URI
        link["uri"] = str(record["uri"])
    elif link_type == "goto":
        # The reference PDF expresses most internal jumps as named links.
        # Recreate resolved links as direct page destinations so the clean
        # source build does not depend on proprietary destination objects.
        link["kind"] = fitz.LINK_GOTO
        link["page"] = int(record["target_page"])
        target = record.get("target_point")
        if target is not None:
            link["to"] = fitz.Point(float(target[0]), float(target[1]))
        link["zoom"] = float(record.get("zoom", 0.0))
    elif link_type == "named":
        # Retain the few unresolved named links that are already unresolved in
        # the reference publication, preserving annotation count and behavior.
        link["kind"] = fitz.LINK_NAMED
        link["name"] = str(record["name"])
    else:
        raise ValueError(f"Unsupported stored link type: {link_type}")
    page.insert_link(link)

def apply(input_pdf: Path, manifest_path: Path, output_pdf: Path) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    with fitz.open(input_pdf) as document:
        expected_pages = int(payload["page_count"])
        if document.page_count != expected_pages:
            raise ValueError(
                "Page-count mismatch: "
                f"PDF has {document.page_count}, manifest expects {expected_pages}"
            )
        delete_existing_links(document)
        document.set_toc(payload["outline"])
        document.set_page_labels(payload["page_labels"])
        for record in payload["links"]:
            insert_link(document, record)
        output_pdf.parent.mkdir(parents=True, exist_ok=True)
        document.save(output_pdf, garbage=4, deflate=True)

def main() -> None:
    arguments = parse_args()
    apply(
        arguments.input_pdf.resolve(),
        arguments.navigation_manifest.resolve(),
        arguments.output_pdf.resolve(),
    )
    print(f"Wrote navigation-complete PDF to {arguments.output_pdf}")

if __name__ == "__main__":
    main()
