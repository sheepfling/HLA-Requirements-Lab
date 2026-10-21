"""Check that the 1516.2 PDF matches its canonical source navigation map."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pymupdf as fitz


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify page count, page labels, bookmarks, and links in the built PDF."
    )
    parser.add_argument("pdf", type=Path, help="built PDF to verify")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("canonical/source-navigation.json"),
        help="navigation manifest (default: canonical/source-navigation.json)",
    )
    return parser.parse_args()


def verify(pdf_path: Path, manifest_path: Path) -> dict[str, int]:
    payload: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    with fitz.open(pdf_path) as document:
        expected_pages = int(payload["page_count"])
        if document.page_count != expected_pages:
            raise ValueError(
                f"Page-count mismatch: PDF has {document.page_count}, "
                f"manifest expects {expected_pages}"
            )

        expected_outline = payload["outline"]
        outline = document.get_toc()
        if outline != expected_outline:
            raise ValueError(
                f"Outline mismatch: PDF has {len(outline)} entries, "
                f"manifest expects {len(expected_outline)}"
            )

        expected_labels = payload["page_labels"]
        labels = document.get_page_labels()
        if labels != expected_labels:
            raise ValueError("Page-label rules do not match canonical/source-navigation.json")

        expected_links = payload["links"]
        links = [link for page in document for link in page.get_links()]
        if len(links) != len(expected_links):
            raise ValueError(
                f"Link-count mismatch: PDF has {len(links)}, manifest expects {len(expected_links)}"
            )

        for index, record in enumerate(expected_links):
            source_page = int(record["source_page"])
            if not 0 <= source_page < document.page_count:
                raise ValueError(f"Link {index} has invalid source page {source_page}")
            if record["type"] == "goto":
                target_page = int(record["target_page"])
                if not 0 <= target_page < document.page_count:
                    raise ValueError(f"Link {index} has invalid target page {target_page}")

        first_page = document[0].get_text()
        if "IEEE Std 1516.2" not in first_page:
            raise ValueError("First PDF page is missing the reconstructed front cover")
        if document[0].get_label() != "Front Cover":
            raise ValueError("First PDF page is missing the Front Cover page label")
        body_lines = [line.strip() for line in document[12].get_text().splitlines() if line.strip()]
        if not body_lines or body_lines[0] != "12":
            raise ValueError("Physical page 13 is missing its printed footer number 12")
        back_page = document[123].get_text()
        if (
            document[123].get_label() != "Back Cover"
            or "RAISING THE" not in back_page
            or "not an IEEE publication" not in back_page
        ):
            raise ValueError("Last PDF page is missing the back-cover text or disclaimer")

        return {
            "pages": document.page_count,
            "outline_entries": len(outline),
            "page_label_rules": len(labels),
            "links": len(links),
        }


def main() -> None:
    arguments = parse_args()
    counts = verify(arguments.pdf, arguments.manifest)
    print(
        f"Verified {arguments.pdf}: {counts['pages']} pages, "
        f"{counts['outline_entries']} bookmarks, {counts['page_label_rules']} page-label rules, "
        f"{counts['links']} links."
    )


if __name__ == "__main__":
    main()
