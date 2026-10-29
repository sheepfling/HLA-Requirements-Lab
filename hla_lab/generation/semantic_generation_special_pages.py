"""Render specialized service, factory, API, and prose pages."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    MutableSequence,
    Sequence,
)
from dataclasses import (
    dataclass,
)
from pathlib import (
    PureWindowsPath,
)

from hla_lab.adapters.latex_renderer import (
    semantic_macro_name,
    tex_escape,
)
from hla_lab.core.semantic_model import (
    ContentBlock,
    DocumentModel,
)
from hla_lab.core.semantic_text import (
    _command_events,
)


def _semantic_content_body(block: ContentBlock, model: DocumentModel) -> str | None:
    """Render a layout-free prose block from its typed content elements."""
    if block.layout_body is not None:
        return None
    elements = {item.id: item for item in model.content_elements if item.block_id == block.id}
    values = [
        f"\\{semantic_macro_name('ContentElement', element.id, 'Text')}"
        for element_id in block.element_ids
        if (element := elements.get(element_id)) is not None
        and element.kind in {"paragraph", "note", "footnote", "list-item"}
    ]
    return "\n\n".join(values) if values else None


def _service_flow_text(value: str) -> str:
    """Remove source-page line wrapping before placing text in normal flow."""

    # The fixed-page adapter uses percent signs as TeX line-continuation
    # markers. They are not authored prose and would comment out a closing
    # brace when the same argument is moved into a flow macro.
    normalized = re.sub(r"\\linebreak\s*%?", " ", value).replace("%", "").strip()
    # Some extracted source lines end in ``\\ %``. Once the percent marker is
    # removed, the remaining control-space slash must not escape the flow
    # macro's closing brace.
    return re.sub(r"\\\s*$", "", normalized).strip()


def _service_flow_events(
    body: str,
) -> tuple[list[tuple[int, int, str, tuple[str, ...]]], bool, bool]:
    service_events = [
        (offset, end, "service", args)
        for offset, args, end in _command_events(body, "HLAServiceHeadingAt", 2)
    ]
    section_events = [
        (offset, end, "section", args)
        for offset, args, end in _command_events(body, "HLAServiceComponentHeadingAt", 2)
    ]
    block_events = [
        (offset, end, "block", args)
        for offset, args, end in _command_events(body, "HLAFixedBlock", 7)
    ]
    events = sorted((*service_events, *section_events, *block_events), key=lambda item: item[0])
    return events, bool(service_events), bool(block_events)


def _render_service_flow_event(
    event: tuple[int, int, str, tuple[str, ...]],
    rendered: MutableSequence[str],
    pending_label: str | None,
) -> str | None:
    _offset, _end, kind, args = event
    if kind == "service":
        heading = _service_flow_text(args[1])
        direction = (
            r"RTI $\rightarrow$ FEDERATE"
            if "textdagger" in heading or "dagger" in heading
            else r"FEDERATE $\rightarrow$ RTI"
        )
        rendered.append(f"\\HLAServiceFlowHeading{{{heading}}}{{{direction}}}")
        return None
    if kind == "section":
        if pending_label is not None:
            rendered.append(f"\\HLAServiceFlowParagraph{{{pending_label}}}")
        rendered.append(f"\\HLAServiceFlowSection{{{_service_flow_text(args[1])}}}")
        return None
    x_position = float(args[0])
    content = _service_flow_text(args[6])
    if x_position < 115:
        if pending_label is not None:
            rendered.append(f"\\HLAServiceFlowParagraph{{{pending_label}}}")
        return content
    if pending_label is not None:
        rendered.append(f"\\HLAServiceFlowItem{{{pending_label}}}{{{content}}}")
        return None
    rendered.append(f"\\HLAServiceFlowParagraph{{{content}}}")
    return None


def _render_service_flow_events(
    events: Sequence[tuple[int, int, str, tuple[str, ...]]], lead: str, tail: str
) -> str:
    rendered = [lead.rstrip()]
    pending_label: str | None = None
    for event in events:
        pending_label = _render_service_flow_event(event, rendered, pending_label)
    if pending_label is not None:
        rendered.append(f"\\HLAServiceFlowParagraph{{{pending_label}}}")
    cleaned_tail = re.sub(r"(?m)^\s*\\draw\[[^\n]*\][^\n;]*;\s*$", "", tail)
    rendered.append(cleaned_tail.lstrip())
    return "\n".join(rendered)


def _modern_service_flow_page(body: str) -> str:
    """Convert one fixed source service page into the contract grammar."""
    events, has_services, has_blocks = _service_flow_events(body)
    if not has_services or not has_blocks:
        return body
    first_offset = events[0][0]
    last_end = max(item[1] for item in events)
    lead = body[:first_offset]
    tail = body[last_end:]
    if r"\begin{hlafixedpage}" not in lead or r"\end{hlafixedpage}" not in tail:
        return body
    lead = lead.replace(r"\begin{hlafixedpage}", r"\begin{HLAServiceFlowPage}", 1)
    tail = tail.replace(r"\end{hlafixedpage}", r"\end{HLAServiceFlowPage}", 1)
    return _render_service_flow_events(events, lead, tail)


def _factory_fixed_lines(body: str) -> list[tuple[float, str]]:
    """Collect one reading-order line from the fixed API source blocks."""

    records: list[tuple[float, float, str]] = []
    for _offset, args, _end in _command_events(body, "HLAFixedBlock", 7):
        try:
            x = float(args[0])
            y = float(args[1])
        except (IndexError, ValueError):
            continue
        text = re.sub(r"\\linebreak\s*%?", " ", args[6])
        text = text.replace("%", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if text and re.match(re.escape(r"\\draw"), text) is None:
            records.append((y, x, text))
    records.sort(key=lambda item: (item[0], item[1]))

    # Inline bold tokens are separate fixed blocks, commonly offset by less
    # than one point from the surrounding line. Recombine them by baseline so
    # the reflowed paragraph reads naturally while retaining the token macro.
    lines: list[tuple[float, list[tuple[float, str]]]] = []
    for y, x, text in records:
        if lines and abs(y - lines[-1][0]) <= 1.0:
            lines[-1][1].append((x, text))
        else:
            lines.append((y, [(x, text)]))
    result = [
        (y, " ".join(text for _x, text in sorted(parts, key=lambda item: item[0])))
        for y, parts in lines
    ]
    normalized: list[tuple[float, str]] = []
    for y, text in result:
        if (
            normalized
            and normalized[-1][1].endswith("-")
            and re.match(r"^[A-Za-z]", text)
            and y - normalized[-1][0] <= 18
        ):
            previous_y, previous_text = normalized[-1]
            normalized[-1] = (previous_y, previous_text[:-1] + text)
        else:
            normalized.append((y, text))
    return normalized


def _fixed_flow_page_parts(
    body: str,
    environment: str,
) -> tuple[list[tuple[float, str]], str, str] | None:
    """Return source lines and a validated flow-page frame."""
    lines = _factory_fixed_lines(body)
    if not lines:
        return None
    events = [(offset, end) for offset, _args, end in _command_events(body, "HLAFixedBlock", 7)]
    if not events:
        return None
    first_offset = min(offset for offset, _end in events)
    last_end = max(end for _offset, end in events)
    lead = body[:first_offset]
    tail = body[last_end:]
    start = r"\begin{hlafixedpage}"
    finish = r"\end{hlafixedpage}"
    if start not in lead or finish not in tail:
        return None
    lead = lead.replace(start, rf"\begin{{{environment}}}", 1)
    tail = tail.replace(finish, rf"\end{{{environment}}}", 1)
    return lines, lead, tail


def _merge_factory_api_tokens(value: str) -> str:
    for _ in range(3):
        value = re.sub(
            r"\\HLAAPIToken\{([^{}]*)-\}\s*\\HLAAPIToken\{([^{}]*)\}",
            lambda match: rf"\HLAAPIToken{{{match.group(1)}{match.group(2)}}}",
            value,
        )
    return value


def _factory_unescape(text: str) -> str:
    """Remove fixed-page TeX escapes before code/listing presentation."""

    return (
        text.replace(r"\char95{}", "_")
        .replace(r"\_", "_")
        .replace(r"\char92{}", "\\")
        .replace(r"\textbackslash{}", "\\")
        .replace(r"\texttrademark", "™")
        .replace(
            "The RTI shall provide the IEEE Std 1516.1-2025 Java API classes",
            "The RTI shall provide the HLA 1516.1 Java API classes",
        )
        .replace("IEEE Std 1516.1-2025", "this document")
        .replace("This standard provides", "This compilation provides")
        .replace("provided with the standard", "provided with this compilation")
        .replace("CTRL_TERMINATE SESSION", "CTRL_TERMINATE_SESSION")
        .replace(" ()", "()")
    )


def _factory_plain_text(text: str) -> str:
    text = _factory_unescape(text)
    for _ in range(3):
        updated = re.sub(r"\\(?:textbf|textit|emph)\{([^{}]*)\}", r"\1", text)
        if updated == text:
            break
        text = updated
    return text.strip()


def _factory_inline_tokens(text: str) -> str:
    """Apply the API token role to bold source identifiers in prose."""

    text = _factory_unescape(text)
    text = re.sub(
        r"\\textbf\{([^{}]+)\}",
        lambda match: rf"\HLAAPIToken{{{match.group(1)}}}",
        text,
    )
    for _ in range(3):
        text = re.sub(
            r"\\HLAAPIToken\{([^{}]*)-\}\s*\\HLAAPIToken\{([^{}]*)\}",
            lambda match: rf"\HLAAPIToken{{{match.group(1)}{match.group(2)}}}",
            text,
        )
    tokens: list[str] = []

    def protect(match: re.Match[str]) -> str:
        tokens.append(match.group(0))
        return f"APITOKENPLACEHOLDER{len(tokens) - 1}"

    def split_long_qualified_token(match: re.Match[str]) -> str:
        token = match.group(1)
        if len(token) < 36:
            return match.group(0)
        scope_index = token.find("::")
        call_index = token.find("(")
        # Do not treat a namespace qualifier inside a function argument such
        # as ``std::wstring`` as the line-break boundary.  Only the scope
        # qualifier that precedes the callable/member itself is eligible.
        if call_index >= 0 and scope_index > call_index:
            return match.group(0)
        head, tail = token.split("::", 1)
        # Keep the identifier semantically intact while giving TeX one
        # meaningful break opportunity between a C++ scope qualifier and its
        # member.  HLAAPIToken itself is intentionally an unbreakable box so
        # identifiers are never split at arbitrary characters.
        return rf"\HLAAPIToken{{{head}::}}\allowbreak\HLAAPIToken{{{tail}}}"

    # Protect source-derived token macros before adding the plain-text token
    # pass so one API identifier cannot become nested inside another.
    text = re.sub(
        r"\\HLAAPIToken\{([^{}]*::[^{}]*)\}",
        split_long_qualified_token,
        text,
    )
    text = re.sub(r"\\HLAAPIToken\{[^{}]*\}", protect, text)
    # Source pages use bold as their only semantic signal for many API names,
    # but package names, protocol symbols, and a few Java platform identifiers
    # are plain source text.  Keep those technical tokens in the same role
    # without making ordinary narrative words monospace.
    explicit_patterns = (
        r"(?<![\w])(?:hla\.rti1516_2025(?:\.[A-Za-z_][\w]*)*)(?![\w])",
        r"(?<![\w])(?:CTRL|HLA|RTI|FED)_[A-Z0-9_]+(?![\w])",
        r"(?<![\w])(?:ServiceLoader|META-INF/services|"
        r"java\.base/java/util/ServiceLoader\.html|META-INF|CLASSPATH|PATH|hashCode\(\))(?![\w])",
    )
    for pattern in explicit_patterns:
        text = re.sub(
            pattern,
            lambda match: rf"\HLAAPIToken{{{match.group(0)}}}",
            text,
        )

    text = re.sub(r"\\HLAAPIToken\{[^{}]*\}", protect, text)

    # Let hyperref break source download URLs on natural-flow annex pages.
    def protect_url(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,;")
        tokens.append(rf"\url{{{url}}}")
        return f"APITOKENPLACEHOLDER{len(tokens) - 1}"

    text = re.sub(r"(?<![\\{])https?://[^\s{}]+", protect_url, text)
    text = text.replace("_", r"\HLAUnderscore{}")
    for index, token in enumerate(tokens):
        text = text.replace(f"APITOKENPLACEHOLDER{index}", token)
    return text


def _is_factory_literal_code(plain: str) -> bool:
    code_prefixes = (
        "RtiFactoryFactory.",
        "LogicalTimeFactoryFactory.",
        "AuthorizerFactoryFactory.",
        "RTIambassador.",
        "Set<RtiFactory>",
        "org.someorganization.",
        "new ",
        "#include",
        "static std::",
        "C++ time class name",
        "C++ interval class name",
        "C++ time factory class name",
    )
    return (
        plain.startswith(code_prefixes)
        or bool(
            re.fullmatch(
                r"(?:EncoderFactory|String)\s+[A-Za-z_][A-Za-z0-9_]*\([^)]*\)",
                plain,
            )
        )
        or plain.endswith((";", " =", "="))
    )


def _is_factory_qualified_code(plain: str) -> bool:
    if not plain.startswith(("std::", "makeLogicalTimeFactory")):
        return False
    return ". " not in plain and not re.search(
        r"\b(?:The|This|In|is|are|used|with|that|to|of)\b", plain
    )


def _is_factory_wrapped_code(
    plain: str, code_lines: Sequence[str], code_y: float | None, y: float
) -> bool:
    return bool(
        code_lines
        and code_y is not None
        and y - code_y <= 18
        and plain.startswith(("=", ".", "&", "*"))
    )


def _factory_code_candidate(
    plain: str, code_lines: Sequence[str], code_y: float | None, y: float
) -> bool:
    return (
        _is_factory_literal_code(plain)
        or _is_factory_qualified_code(plain)
        or _is_factory_wrapped_code(plain, code_lines, code_y, y)
    )


def _modern_java_factory_page(body: str) -> str:
    """Reflow an API source page into prose, API tokens, and code blocks.

    The helper name is retained for the acceptance-slice API, but the same
    grammar is now used across the full programming-language mapping run.
    """

    parts = _fixed_flow_page_parts(body, "HLAAPIFlowPage")
    if parts is None:
        return body
    lines, lead, tail = parts

    rendered: list[str] = [
        lead.rstrip(),
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{5pt}",
    ]
    code_lines: list[str] = []
    prose_lines: list[str] = []
    prose_y: float | None = None
    code_y: float | None = None

    def flush_code() -> None:
        nonlocal code_y
        if not code_lines:
            return
        rendered.append(r"\begin{RLCodeBlock}")
        rendered.extend(code_lines)
        rendered.append(r"\end{RLCodeBlock}")
        code_lines.clear()
        code_y = None

    def flush_prose() -> None:
        if prose_lines:
            joined = " ".join(prose_lines).strip()
            joined = re.sub(r"(?<=[A-Za-z0-9_])-\s+(?=[A-Za-z])", "", joined)
            rendered.append(joined + r"\par")
            prose_lines.clear()

    for y, raw in lines:
        plain = _factory_plain_text(raw)
        heading = re.fullmatch(r"(?:\\textbf\{)?(\d+(?:\.\d+)+\s+[^{}]+)(?:\})?", raw)
        if heading:
            flush_prose()
            flush_code()
            rendered.append(rf"\HLASubsubclause{{{_factory_unescape(heading.group(1))}}}")
            prose_y = None
            continue
        code_candidate = plain.endswith((".java", ".h")) or _factory_code_candidate(
            plain, code_lines, code_y, y
        )
        if code_candidate:
            flush_prose()
            code_lines.append(plain)
            code_y = y
            prose_y = None
            continue
        flush_code()
        # A source line with a large baseline gap starts a new paragraph; the
        # natural-flow paragraph keeps the content selectable and lets the
        # page break at a real typographic boundary.
        if prose_y is not None and y - prose_y > 18:
            flush_prose()
        prose_lines.append(_factory_inline_tokens(raw))
        prose_y = y
    flush_prose()
    flush_code()
    rendered.append(tail.lstrip())
    return _merge_factory_api_tokens("\n".join(rendered))


def _modern_api_manifest_page(body: str) -> str:
    """Render Java/C++ file manifests as selectable directory listings."""

    parts = _fixed_flow_page_parts(body, "HLAAPIFlowPage")
    if parts is None:
        return body
    lines, lead, tail = parts
    rendered: list[str] = [
        lead.rstrip(),
        r"\setlength{\parindent}{0pt}",
        r"\setlength{\parskip}{5pt}",
    ]
    code_lines: list[str] = []
    prose_lines: list[str] = []

    def flush_code() -> None:
        if not code_lines:
            return
        rendered.append(r"\begin{RLCodeBlock}")
        rendered.extend(code_lines)
        rendered.append(r"\end{RLCodeBlock}")
        code_lines.clear()

    def flush_prose() -> None:
        if prose_lines:
            rendered.append(" ".join(prose_lines).strip() + r"\par")
            prose_lines.clear()

    for _y, raw in lines:
        plain = _factory_plain_text(raw)
        heading = re.fullmatch(r"(Annex\s+[A-Z]|\d+(?:\.\d+)+)\s+.+", plain)
        if heading:
            flush_prose()
            flush_code()
            rendered.append(rf"\HLASubsubclause{{{_factory_unescape(plain)}}}")
            continue
        path = PureWindowsPath(plain)
        path_parts = path.parts
        is_path = (
            path.suffix.casefold() in {".java", ".h"}
            or plain.endswith(":")
            or bool(
                path_parts
                and path_parts[0].casefold() in {"hla", "auth", "encoding", "exceptions", "time"}
            )
            or re.search(r"[/\\]$", plain) is not None
        )
        if is_path:
            flush_prose()
            code_lines.append(plain)
        else:
            flush_code()
            prose_lines.append(_factory_inline_tokens(raw))
    flush_prose()
    flush_code()
    rendered.append(tail.lstrip())
    return "\n".join(rendered)


@dataclass(slots=True)
class _ProtocolProseState:
    rendered: list[str]
    prose_lines: list[str]
    list_label: str | None
    list_lines: list[str]
    list_y: float | None
    prose_y: float | None
    bullet_lines: list[str]
    bullet_y: float | None


def _protocol_join_lines(values: Sequence[str]) -> str:
    joined = " ".join(values).strip()
    return re.sub(r"(?<=[A-Za-z0-9_])-\s+(?=[A-Za-z])", "", joined)


def _flush_protocol_prose(state: _ProtocolProseState) -> None:
    if state.prose_lines:
        state.rendered.append(
            _factory_inline_tokens(_protocol_join_lines(state.prose_lines)) + r"\par"
        )
        state.prose_lines.clear()
    state.prose_y = None


def _flush_protocol_list(state: _ProtocolProseState) -> None:
    if state.list_label is not None:
        state.rendered.append(
            rf"\HLAProtocolRule{{{tex_escape(state.list_label)}}}"
            rf"{{{_factory_inline_tokens(_protocol_join_lines(state.list_lines))}}}"
        )
    state.list_label = None
    state.list_lines.clear()
    state.list_y = None


def _flush_protocol_bullet(state: _ProtocolProseState) -> None:
    if state.bullet_lines:
        bullet = _factory_inline_tokens(_protocol_join_lines(state.bullet_lines))
        state.rendered.append(rf"\HLAProtocolBullet{{{bullet}}}")
        state.bullet_lines.clear()
    state.bullet_y = None


def _flush_protocol_sections(state: _ProtocolProseState) -> None:
    _flush_protocol_prose(state)
    _flush_protocol_list(state)
    _flush_protocol_bullet(state)


def _consume_protocol_marker(state: _ProtocolProseState, y: float, plain: str) -> bool:
    heading = re.fullmatch(r"(\d+(?:\.\d+)+)\s+.+", plain)
    if heading:
        _flush_protocol_sections(state)
        state.rendered.append(rf"\HLASubsubclause{{{_factory_unescape(plain)}}}")
        return True
    if plain == "---" or plain.startswith("--- "):
        _flush_protocol_sections(state)
        state.bullet_lines.append(plain[3:].strip())
        state.bullet_y = y
        return True
    marker = re.match(r"^([a-z]|\d+)\)\s*(.*)$", plain)
    if marker:
        _flush_protocol_sections(state)
        state.list_label = marker.group(1) + ")"
        state.list_lines.append(marker.group(2))
        state.list_y = y
        return True
    return False


def _consume_protocol_continuation(
    state: _ProtocolProseState,
    y: float,
    plain: str,
) -> bool:
    if state.list_label is not None:
        if state.list_y is not None and y - state.list_y > 18:
            _flush_protocol_list(state)
        else:
            state.list_lines.append(plain)
            state.list_y = y
            return True
    if state.bullet_lines:
        if state.bullet_y is not None and y - state.bullet_y > 18:
            _flush_protocol_bullet(state)
        else:
            state.bullet_lines.append(plain)
            state.bullet_y = y
            return True
    return False


def _consume_protocol_prose_line(
    state: _ProtocolProseState,
    y: float,
    raw: str,
) -> None:
    plain = _factory_plain_text(raw)
    if _consume_protocol_marker(state, y, plain):
        return
    if _consume_protocol_continuation(state, y, plain):
        return
    if state.prose_y is not None and y - state.prose_y > 18:
        _flush_protocol_prose(state)
    state.prose_lines.append(raw)
    state.prose_y = y


def _modern_protocol_prose_page(body: str) -> str:
    """Reflow protocol narrative and rules while preserving message tokens."""
    parts = _fixed_flow_page_parts(body, "HLAProtocolFlowPage")
    if parts is None:
        return body
    lines, lead, tail = parts
    state = _ProtocolProseState(
        rendered=[lead.rstrip()],
        prose_lines=[],
        list_label=None,
        list_lines=[],
        list_y=None,
        prose_y=None,
        bullet_lines=[],
        bullet_y=None,
    )
    for y, raw in lines:
        _consume_protocol_prose_line(state, y, raw)
    _flush_protocol_sections(state)
    state.rendered.append(tail.lstrip())
    return "\n".join(state.rendered)


def _modernize_2010_service_surface(body: str) -> str:
    """Release source-page service clauses as normal flowing content.

    The 2010.1 source adapter contains many deliberate ``\\clearpage`` and
    large source-positioning ``\\vspace*`` commands.  Those commands are
    useful while reconstructing a scanned page, but they create empty
    continuation pages once the body contains generated vector figures and
    modern page furniture.  Remove only those layout-only commands from
    blocks that contain actual service headings; the authored prose, lists,
    numbering, and deferred native charts remain unchanged.
    """

    service_headings = [
        args[0]
        for _offset, args, _end in _command_events(body, "subsection", 1)
        if "service" in args[0].lower()
    ]
    if not service_headings:
        return body
    body = re.sub(r"(?m)^\s*\\clearpage\s*$", "", body)
    body = re.sub(r"(?m)^\s*\\newpage\s*$", "", body)
    # These are source-page placement offsets, not editorial spacing. Keep
    # ordinary point-sized paragraph spacing and local table rhythm intact.
    body = re.sub(r"\\vspace\*\{[-+]?\d+(?:\.\d+)?(?:in|pt)\}", "", body)

    # Keep the numbered subsection and its PDF bookmark, but add the same
    # explicit federate/RTI direction used by the 2025 service grammar.  The
    # source title carries the RTI-initiated marker when applicable.
    service_events = [
        (offset, args, end)
        for offset, args, end in _command_events(body, "subsection", 1)
        if "service" in args[0].lower()
    ]
    for offset, args, end in reversed(service_events):
        title = args[0]
        direction = (
            r"RTI $\rightarrow$ FEDERATE"
            if "rtiinitiated" in title.lower() or "dagger" in title.lower()
            else r"FEDERATE $\rightarrow$ RTI"
        )
        original = body[offset:end]
        replacement = original + "\n" + f"\\HLAServiceDirectionLine{{{direction}}}"
        body = body[:offset] + replacement + body[end:]
    return body
