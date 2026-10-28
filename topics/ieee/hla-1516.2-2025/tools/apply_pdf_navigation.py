from __future__ import annotations

import argparse
from pathlib import Path
from typing import Annotated, Literal, TypeAlias

import fitz
from pydantic import BaseModel, ConfigDict, Field


class _NavigationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_page: Annotated[int, Field(ge=0)]
    source_kind: int
    rectangle: tuple[float, float, float, float]


class _UriLink(_NavigationRecord):
    type: Literal["uri"]
    uri: str


class _GotoLink(_NavigationRecord):
    type: Literal["goto"]
    target_page: Annotated[int, Field(ge=0)]
    target_point: tuple[float, float]
    zoom: float
    source_named_destination: str


class _NamedLink(_NavigationRecord):
    type: Literal["named"]
    name: str


_NavigationLink = Annotated[
    _UriLink | _GotoLink | _NamedLink,
    Field(discriminator="type"),
]


class _PageLabel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    startpage: Annotated[int, Field(ge=0)]
    prefix: str
    firstpagenum: Annotated[int, Field(ge=1)]
    style: str | None = None


class _NavigationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    page_count: Annotated[int, Field(gt=0)]
    outline: tuple[tuple[int, str, int], ...]
    page_labels: tuple[_PageLabel, ...]
    links: tuple[_NavigationLink, ...]


_PdfLinkValue: TypeAlias = int | float | str | fitz.Rect | fitz.Point


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


def insert_link(document: fitz.Document, record: _NavigationLink) -> None:
    page = document[record.source_page]
    link: dict[str, _PdfLinkValue] = {"from": fitz.Rect(record.rectangle)}
    if record.type == "uri":
        link["kind"] = fitz.LINK_URI
        link["uri"] = record.uri
    elif record.type == "goto":
        # The reference PDF expresses most internal jumps as named links.
        # Recreate resolved links as direct page destinations so the clean
        # source build does not depend on proprietary destination objects.
        link["kind"] = fitz.LINK_GOTO
        link["page"] = record.target_page
        link["to"] = fitz.Point(*record.target_point)
        link["zoom"] = record.zoom
    elif record.type == "named":
        # Retain the few unresolved named links that are already unresolved in
        # the reference publication, preserving annotation count and behavior.
        link["kind"] = fitz.LINK_NAMED
        link["name"] = record.name
    else:
        raise ValueError(f"Unsupported stored link type: {record.type}")
    page.insert_link(link)


def apply(input_pdf: Path, manifest_path: Path, output_pdf: Path) -> None:
    payload = _NavigationManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    with fitz.open(input_pdf) as document:
        expected_pages = payload.page_count
        if document.page_count != expected_pages:
            raise ValueError(
                "Page-count mismatch: "
                f"PDF has {document.page_count}, manifest expects {expected_pages}"
            )
        delete_existing_links(document)
        document.set_toc([list(item) for item in payload.outline])
        document.set_page_labels(
            [label.model_dump(exclude_none=True) for label in payload.page_labels]
        )
        for record in payload.links:
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
