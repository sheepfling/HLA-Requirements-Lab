"""Normalize self-references for the independent HLA Requirements Lab edition."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "topics" / "ieee" / "hla-1516.2-2025" / "semantic" / "content-blocks.json"
OLD = "IEEE Std 1516.2-2025"
NEW = "this specification"
TITLE_REPLACEMENTS = (
    (r"\mbox{\textbf{IEEE Standard for}}", r"\mbox{\textbf{HLA Requirements Lab}}"),
    (
        r"\mbox{\textbf{Modeling and Simulation (M\&S)}}",
        r"\mbox{\textbf{HLA 1516.2 family}}",
    ),
    (
        r"\mbox{\textbf{High Level Architecture (HLA)—}}",
        r"\mbox{\textbf{2025-source compilation}}",
    ),
)


def main() -> None:
    import json

    payload = json.loads(TARGET.read_text(encoding="utf-8"))
    count = 0
    title_count = 0
    for block in payload["content_blocks"]:
        for key in ("text", "layout_body"):
            if isinstance(block.get(key), str):
                count += block[key].count(OLD)
                block[key] = block[key].replace(OLD, NEW)
        if block.get("id") == "content-15162-page-013":
            for old, new in TITLE_REPLACEMENTS:
                occurrences = block["layout_body"].count(old)
                title_count += occurrences
                block["layout_body"] = block["layout_body"].replace(old, new)
    if count not in (0, 6):
        raise SystemExit(f"expected 0 or 6 self-references, found {count}")
    if title_count not in (0, len(TITLE_REPLACEMENTS)):
        raise SystemExit(
            f"expected 0 or {len(TITLE_REPLACEMENTS)} title replacements, found {title_count}"
        )
    TARGET.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"normalized {count} self-references and {title_count} title fragments in {TARGET}")


if __name__ == "__main__":
    main()
