"""Repair the 1516-2025 opener's display title line breaking."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "topics" / "ieee" / "hla-1516-2025" / "semantic" / "content-blocks.json"


def main() -> None:
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    block = next(item for item in payload["content_blocks"] if item["id"] == "content-1-normative-001")
    old = r"""HLA Requirements Lab\linebreak
HLA 1516 family\linebreak
2025-source compilation\linebreak
Framework and Rules"""
    new = r"""HLA Requirements Lab\\
HLA 1516 family\\
2025-source compilation\\
Framework and Rules"""
    if block["layout_body"].count(old) != 1:
        raise ValueError("1516-2025 opener title text is not unique")
    block["layout_body"] = block["layout_body"].replace(old, new, 1)
    old_font = r"\RLFixedSans\bfseries\fontsize{19.98pt}{23.02pt}\selectfont"
    new_font = old_font + r"\raggedright"
    if block["layout_body"].count(old_font) != 1:
        raise ValueError("1516-2025 opener title font declaration is not unique")
    block["layout_body"] = block["layout_body"].replace(old_font, new_font, 1)
    PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
