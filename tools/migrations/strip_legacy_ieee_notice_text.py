"""Remove legacy IEEE notice boilerplate from HLA Lab semantic source."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCUMENTS = (
    "hla-1516-2010",
    "hla-1516.1-2010",
    "hla-1516.2-2010",
    "hla-1516-2025",
    "hla-1516.1-2025",
    "hla-1516.2-2025",
)

OMIT_BLOCKS = {
    "hla-1516-2010": {
        "content-frontmatter-01-external-cover-tex",
        "content-frontmatter-04-copyright-abstract-tex",
        "content-frontmatter-03-title-page-tex",
        "content-frontmatter-05-ieee-notices-tex",
        "content-frontmatter-07-updating-participants-tex",
        "content-frontmatter-08-participants-ballot-tex",
        "content-frontmatter-09-standards-board-tex",
    },
    "hla-1516.1-2010": {
        "content-frontmatter-title-tex",
        "content-frontmatter-publication-tex",
        "content-frontmatter-standards-notice-tex",
        "content-frontmatter-introduction-tex",
        "content-frontmatter-participants-tex",
    },
    "hla-1516-2025": {
        "content-front-matter-context-001",
        "content-front-matter-normative-001",
        "content-front-matter-context-003",
        "content-front-matter-context-004",
        "content-front-matter-normative-002",
        "content-front-matter-context-002",
    },
    "hla-1516.1-2025": {
        "content-15161-page-003",
        "content-15161-page-004",
        "content-15161-page-005",
        "content-15161-page-006",
        "content-15161-page-007",
        "content-15161-page-008",
    },
    "hla-1516.2-2025": {
        "content-15162-page-002",
        "content-15162-page-003",
        "content-15162-page-004",
        "content-15162-page-005",
        "content-15162-page-006",
        "content-15162-page-007",
        "content-15162-page-008",
        "content-15162-page-009",
        "content-15162-page-010",
    },
}

NOTICE_BLOCKS_2010 = {
    "hla-1516-2010": {"content-clauses-01-overview-tex"},
    "hla-1516.1-2010": {"content-clauses-01-overview-tex"},
    "hla-1516.2-2010": {"content-frontmatter-standard-title-tex"},
}


PUBLISHER_TEXT_PATTERNS = (
    re.compile(
        r"IEEE publications are available .*?standards\.ieee\.org[^)]*\)?\.?",
        re.IGNORECASE,
    ),
    re.compile(
        r"ANSI publications are available from .*?https?://www\.ansi\.org/[^)]*\)?\.?",
        re.IGNORECASE,
    ),
    re.compile(
        r"This document is available (?:at|from) .*?https?://[^)]*\)?\.?",
        re.IGNORECASE,
    ),
    re.compile(
        r"The IEEE standards or products referred to .*?trademarks .*?(?:Incorporated|Inc\.)\.?",
        re.IGNORECASE,
    ),
    re.compile(
        r"Copyright\s+(?:\\textcopyright\{\}|©)?\s*\d{4}\s+IEEE\.\s*All rights reserved\.",
        re.IGNORECASE,
    ),
    re.compile(
        r"No part of this publication .*?publisher\.", re.IGNORECASE | re.DOTALL
    ),
    re.compile(
        r"The IEEE hereby grants .*?(?:stds?-ipr|stdsipr)@ieee\.org\)?\.?",
        re.IGNORECASE | re.DOTALL,
    ),
)


def _balanced_group_end(value: str, start: int, opening: str = "{") -> int | None:
    """Return the end of a balanced TeX group beginning at ``start``."""
    closing = "}" if opening == "{" else "]"
    if start >= len(value) or value[start] != opening:
        return None
    depth = 0
    escaped = False
    for index in range(start, len(value)):
        char = value[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return index + 1
    return None


def _remove_matching_tex_commands(value: str) -> str:
    """Remove publisher/legal TeX commands without disturbing other layout."""
    command_names = {"footnote", "footnotetext", "HLAFixedBlock", "HLARotatedLine"}
    markers = (
        "IEEE publications are available",
        "ANSI publications are available",
        "This document is available",
        "trademarks",
        "Copyright ",
        "No part of this publication",
    )
    cursor = 0
    while True:
        match = re.search(r"\\([A-Za-z]+)", value[cursor:])
        if not match:
            break
        command = match.group(1)
        start = cursor + match.start()
        if command not in command_names:
            cursor = cursor + match.end()
            continue

        position = cursor + match.end()
        if position < len(value) and value[position] == "[":
            optional_end = _balanced_group_end(value, position, "[")
            if optional_end is None:
                cursor = position
                continue
            position = optional_end
        argument_ends: list[int] = []
        while position < len(value):
            whitespace = re.match(r"\s*", value[position:])
            position += whitespace.end() if whitespace else 0
            if position >= len(value) or value[position] != "{":
                break
            group_end = _balanced_group_end(value, position)
            if group_end is None:
                break
            argument_ends.append(group_end)
            position = group_end

        end = argument_ends[-1] if argument_ends else position
        candidate = value[start:end]
        if any(marker.lower() in candidate.lower() for marker in markers):
            value = value[:start] + value[end:]
            cursor = max(0, start - 1)
        else:
            cursor = end
    return value


def strip_publisher_text(value: str) -> str:
    """Remove inherited publisher, copyright, permission, and address text."""
    value = _remove_matching_tex_commands(value)
    for pattern in PUBLISHER_TEXT_PATTERNS:
        value = pattern.sub("", value)
    value = re.sub(
        r"(?:©|\\textcopyright\{\})\s*20\d{2}(?:\s+20\d{2})?\s+IEEE",
        "Lab example",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\\textsuperscript\{,\}", "", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    value = re.sub(r"\n[ \t]+\n", "\n\n", value)
    return value if not value.strip() else value.strip()


def clean_semantic_strings(value: object) -> object:
    """Clean user-visible semantic strings while preserving record structure."""
    if isinstance(value, dict):
        return {key: clean_semantic_strings(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean_semantic_strings(item) for item in value]
    if isinstance(value, str):
        return strip_publisher_text(value)
    return value


def strip_2010_layout(value: str) -> str:
    """Remove the two legacy notice paragraphs while preserving the title."""
    marker = "IMPORTANT NOTICE: This standard is not intended"
    while marker in value:
        notice_start = value.index(marker)
        block_start = value.rfind(r"\vspace", 0, notice_start)
        if block_start < 0:
            block_start = notice_start

        first_end = value.find(r"\par}", notice_start)
        if first_end < 0:
            break
        second_start = value.find("This IEEE document is made available", first_end)
        if second_start < 0:
            value = value[:block_start] + value[first_end + len(r"\par}") :]
            continue
        second_end = value.find(r"\par}", second_start)
        if second_end < 0:
            break
        value = value[:block_start] + value[second_end + len(r"\par}") :]
    return value


def strip_2010_text(value: str) -> str:
    value = re.sub(
        r"\s*IMPORTANT NOTICE: This standard is not intended to ensure safety.*?"
        r"regulatory requirements\.\s*",
        " ",
        value,
        flags=re.DOTALL,
    )
    value = re.sub(
        r"\s*This IEEE document is made available for use subject to important "
        r"notices and legal disclaimers\..*?"
        r"Important Notices and Disclaimers Concerning IEEE Documents\.?\s*",
        " ",
        value,
        flags=re.DOTALL,
    )
    return re.sub(r"\s{2,}", " ", value).strip()


def clean_document(name: str) -> None:
    semantic = ROOT / "topics" / "ieee" / name / "semantic"
    blocks_path = semantic / "content-blocks.json"
    elements_path = semantic / "content-elements.json"
    blocks_payload = json.loads(blocks_path.read_text(encoding="utf-8"))
    elements_payload = json.loads(elements_path.read_text(encoding="utf-8"))

    omitted = OMIT_BLOCKS.get(name, set())
    notice_blocks = NOTICE_BLOCKS_2010.get(name, set())
    cleaned_blocks = 0
    kept_blocks = []
    for block in blocks_payload["content_blocks"]:
        block_id = str(block["id"])
        if block_id in omitted:
            cleaned_blocks += 1
            continue
        elif block_id in notice_blocks:
            block["text"] = strip_2010_text(str(block.get("text", "")))
            layout_body = block.get("layout_body")
            if isinstance(layout_body, str):
                block["layout_body"] = strip_2010_layout(layout_body)
            cleaned_blocks += 1
        for key in ("text", "layout_body"):
            if isinstance(block.get(key), str):
                block[key] = strip_publisher_text(block[key])
        kept_blocks.append(block)

    if name == "hla-1516.2-2025":
        for block in kept_blocks:
            if block.get("id") != "content-15162-page-016":
                continue
            layout_body = str(block.get("layout_body", ""))
            marker = r"\HLAStableID{m3.p016.b16}"
            if marker in layout_body:
                layout_body = layout_body.split(marker, 1)[0]
                for footnote_marker in ("9", "10,", "11", "12"):
                    layout_body = layout_body.replace(
                        rf"\HLATextSup{{{footnote_marker}}}", ""
                    )
                block["layout_body"] = layout_body + r"\end{HLAClauseSemanticPage}"

    elements_payload["content_elements"] = [
        element
        for element in elements_payload["content_elements"]
        if str(element.get("block_id", "")) not in omitted
    ]
    block_ids = {str(block["id"]) for block in kept_blocks}
    elements_payload["content_elements"] = [
        element
        for element in elements_payload["content_elements"]
        if str(element.get("block_id", "")) in block_ids
    ]
    element_ids = {
        str(element["id"]) for element in elements_payload["content_elements"]
    }
    blocks_payload["content_blocks"] = kept_blocks
    for block in blocks_payload["content_blocks"]:
        if isinstance(block.get("element_ids"), list):
            block["element_ids"] = [
                element_id
                for element_id in block["element_ids"]
                if str(element_id) in element_ids
            ]

    for element in elements_payload["content_elements"]:
        block_id = str(element.get("block_id", ""))
        if block_id in notice_blocks:
            element["text"] = strip_2010_text(str(element.get("text", "")))
        if isinstance(element.get("text"), str):
            element["text"] = strip_publisher_text(element["text"])

    for json_path in semantic.glob("*.json"):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        cleaned_payload = clean_semantic_strings(payload)
        json_path.write_text(
            json.dumps(cleaned_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    blocks_path.write_text(
        json.dumps(blocks_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    elements_path.write_text(
        json.dumps(elements_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"{name}: cleaned {cleaned_blocks} notice blocks")


def clean_navigation() -> None:
    """Drop navigation entries and links belonging to omitted publisher pages."""
    path = ROOT / "topics" / "ieee" / "hla-1516.2-2025" / "canonical" / "source-navigation.json"
    if not path.exists():
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["outline"] = [
        entry for entry in payload.get("outline", []) if entry[1] != "Title page"
    ]
    payload["links"] = [
        link for link in payload.get("links", []) if link.get("source_page", 99) > 6
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for name in DOCUMENTS:
        clean_document(name)
    clean_navigation()


if __name__ == "__main__":
    main()
