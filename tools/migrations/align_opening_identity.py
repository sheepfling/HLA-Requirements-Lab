"""Align product opening pages with the HLA Requirements Lab identity."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _replace_once(body: str, old: str, new: str, *, label: str) -> str:
    count = body.count(old)
    if count != 1:
        raise ValueError(f"{label}: expected one opening title, found {count}")
    return body.replace(old, new, 1)


NATURAL_FLOW_REPLACEMENTS = {
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
        r"""\RLDocumentOpeningTitle{1516.2}{2010}{Object Model Template (OMT)\\Specification}""",
    ),
}


FIXED_PAGE_REPLACEMENTS = {
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


def _load_blocks(name: str) -> tuple[Path, dict, list[dict]]:
    path = ROOT / "topics" / "ieee" / name / "semantic" / "content-blocks.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    return path, payload, payload["content_blocks"]


def _write_opening_identity_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for name, (block_id, old, new) in NATURAL_FLOW_REPLACEMENTS.items():
        path, payload, blocks = _load_blocks(name)
        block = next(item for item in blocks if item["id"] == block_id)
        block["layout_body"] = _replace_once(
            block["layout_body"], old, new, label=f"{name}/{block_id}"
        )
        _write_opening_identity_json(path, payload)

    for name, (block_id, old, new) in FIXED_PAGE_REPLACEMENTS.items():
        path, payload, blocks = _load_blocks(name)
        block = next(item for item in blocks if item["id"] == block_id)
        block["layout_body"] = _replace_once(
            block["layout_body"], old, new, label=f"{name}/{block_id}"
        )
        if name == "hla-1516-2025":
            block["text"] = block["text"].replace(
                r"IEEE Standard for Modeling and Simulation (M\&S) High Level Architecture (HLA)--- Framework and Rules",
                "HLA Requirements Lab HLA 1516 family 2025-source compilation Framework and Rules",
            )
        _write_opening_identity_json(path, payload)


if __name__ == "__main__":
    main()
