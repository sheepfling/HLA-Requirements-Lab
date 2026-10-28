"""Align product opening pages with the HLA Requirements Lab identity."""

from __future__ import annotations

from pathlib import Path
from types import MappingProxyType

from hla_lab.core.semantic_model import ContentBlock, ContentBlockFile
from tools.migrations.workspace import migration_root


def _replace_once(body: str, old: str, new: str, *, label: str) -> str:
    count = body.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one opening title, found {count}")
    return body.replace(old, new, 1)


NATURAL_FLOW_REPLACEMENTS = MappingProxyType(
    {
        "hla-1516-2010": (
            "content-clauses-01-overview-tex",
            r"""{\sffamily\bfseries\fontsize{24pt}{26pt}\selectfont
IEEE Standard for\\
Modeling and Simulation (M\&S)\\
High Level Architecture (HLA)---\\
Framework and Rules\par}""",
            r"""\RLDocumentOpeningTitle{1516}{2010}{Framework and Rules}""",
        ),
        "hla-1516.1-2010": (
            "content-clauses-01-overview-tex",
            r"""{\sffamily\bfseries\fontsize{18}{21}\selectfont
IEEE Standard for\\
Modeling and Simulation (M\&S)\\
High Level Architecture (HLA)---\\
Federate Interface Specification\par}""",
            r"""\RLDocumentOpeningTitle{1516.1}{2010}{Federate Interface Specification}""",
        ),
        "hla-1516.2-2010": (
            "content-frontmatter-standard-title-tex",
            r"""{\fontfamily{Arimo-TLF}\bfseries\fontsize{22}{25}\selectfont
IEEE Standard for\\
Modeling and Simulation (M\&S)\\
High Level Architecture (HLA)---\\
Object Model Template (OMT)\\
Specification\par}""",
            r"""\RLDocumentOpeningTitle{1516.2}{2010}{Object Model Template """
            r"""(OMT)\\Specification}""",
        ),
    }
)


FIXED_PAGE_REPLACEMENTS = MappingProxyType(
    {
        "hla-1516-2025": (
            "content-1-normative-001",
            r"""{\HLAFacSans\bfseries\fontsize{19.98pt}{23.02pt}\selectfont
IEEE Standard for Modeling and Simulation\linebreak
(M\&S) High Level Architecture (HLA)---\linebreak
Framework and Rules\par}""",
            r"""{\RLFixedSans\bfseries\fontsize{19.98pt}{23.02pt}\selectfont
HLA Requirements Lab\linebreak
HLA 1516 family\linebreak
2025-source compilation\linebreak
Framework and Rules\par}""",
        ),
        "hla-1516.1-2025": (
            "content-15161-page-016",
            r"""{\sffamily\bfseries\fontsize{24pt}{26pt}\selectfont
 IEEE Standard for\\
 Modeling and Simulation (M\&S)\\
 High Level Architecture (HLA)---\\
 Federate Interface Specification\par
}""",
            r"""{\RLFixedSans\bfseries\fontsize{21pt}{24pt}\selectfont
 HLA Requirements Lab\\
 HLA 1516.1 family\\
 2025-source compilation\\
 Federate Interface Specification\par
}""",
        ),
    }
)


def _load_blocks(name: str) -> tuple[Path, ContentBlockFile]:
    path = migration_root() / "topics" / "ieee" / name / "semantic" / "content-blocks.json"
    payload = ContentBlockFile.model_validate_json(path.read_text(encoding="utf-8"))
    return path, payload


def _write_opening_identity_json(path: Path, payload: ContentBlockFile) -> None:
    path.write_text(payload.model_dump_json(indent=2, exclude_unset=True) + "\n", encoding="utf-8")


def _replace_block(
    payload: ContentBlockFile,
    block_id: str,
    *,
    layout_body: str,
    text: str | None = None,
) -> ContentBlockFile:
    blocks = list(payload.content_blocks)
    index = next(index for index, item in enumerate(blocks) if item.id == block_id)
    updates = {"layout_body": layout_body}
    if text is not None:
        updates["text"] = text
    updated_block = blocks[index].model_copy(update=updates)
    blocks[index] = ContentBlock.model_validate(
        updated_block.model_dump(mode="python", exclude_unset=True)
    )
    return ContentBlockFile(schema_version=payload.schema_version, content_blocks=tuple(blocks))


def main() -> None:
    for name, (block_id, old, new) in NATURAL_FLOW_REPLACEMENTS.items():
        path, payload = _load_blocks(name)
        block = next(item for item in payload.content_blocks if item.id == block_id)
        if block.layout_body is None:
            raise ValueError(f"{name}/{block_id}: content block has no layout body")
        payload = _replace_block(
            payload,
            block_id,
            layout_body=_replace_once(block.layout_body, old, new, label=f"{name}/{block_id}"),
        )
        _write_opening_identity_json(path, payload)

    for name, (block_id, old, new) in FIXED_PAGE_REPLACEMENTS.items():
        path, payload = _load_blocks(name)
        block = next(item for item in payload.content_blocks if item.id == block_id)
        if block.layout_body is None:
            raise ValueError(f"{name}/{block_id}: content block has no layout body")
        layout_body = _replace_once(block.layout_body, old, new, label=f"{name}/{block_id}")
        text = None
        if name == "hla-1516-2025":
            text = block.text.replace(
                r"IEEE Standard for Modeling and Simulation (M\&S) "
                r"High Level Architecture (HLA)--- Framework and Rules",
                "HLA Requirements Lab HLA 1516 family 2025-source compilation Framework and Rules",
            )
        payload = _replace_block(payload, block_id, layout_body=layout_body, text=text)
        _write_opening_identity_json(path, payload)


if __name__ == "__main__":
    main()
