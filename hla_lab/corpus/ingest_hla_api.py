"""Ingest HLA API declarations into text-only semantic surface records.

The importer reads API archives in ``inbox`` without copying or baselining the
archives themselves.  It emits Pydantic-validated JSON records with provenance
pointing back to the archive entry, so the committed semantic source remains
textual and independently reviewable.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from hla_lab.core.io import write_json
from hla_lab.core.semantic_model import ApiParameter, ApiSurface, ApiSurfaceFile, SourceRef
from hla_lab.core.text import normalize_whitespace, slugify
from hla_lab.paths import REPO_ROOT, resources

ROOT = REPO_ROOT
OWNER_BY_FILE = {
    "RTIambassador": ("RTIambassador", "service"),
    "FederateAmbassador": ("FederateAmbassador", "callback"),
}


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _source(path: str, line: int) -> SourceRef:
    return SourceRef(path=path, line=max(line, 1))


def _normalize(value: str) -> str:
    return normalize_whitespace(value)


def _stable_id(edition: str, binding: str, owner: str, name: str, signature: str) -> str:
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    owner_slug = slugify(owner, fallback="owner")
    name_slug = slugify(name, fallback="name")
    return f"api.{edition}.{binding}.{owner_slug}.{name_slug}.{digest}"


def _split_top_level(value: str) -> tuple[str, ...]:
    parts: list[str] = []
    start = 0
    angle = paren = bracket = brace = 0
    for index, char in enumerate(value):
        if char == "<":
            angle += 1
        elif char == ">" and angle:
            angle -= 1
        elif char == "(":
            paren += 1
        elif char == ")" and paren:
            paren -= 1
        elif char == "[":
            bracket += 1
        elif char == "]" and bracket:
            bracket -= 1
        elif char == "{":
            brace += 1
        elif char == "}" and brace:
            brace -= 1
        elif char == "," and not any((angle, paren, bracket, brace)):
            parts.append(value[start:index].strip())
            start = index + 1
    tail = value[start:].strip()
    if tail:
        parts.append(tail)
    return tuple(parts)


def _clause_id(comments: str) -> str | None:
    for line in reversed(comments.splitlines()):
        cleaned = re.sub(r"^[\s/*#-]+", "", line).strip()
        match = re.match(r"(?P<number>\d+(?:\.\d+)*)\b", cleaned)
        if match:
            return f"clause-{match.group('number')}"
    return None


def _throws(comments: str, declaration: str) -> tuple[str, ...]:
    values = re.findall(r"@throws\s+([A-Za-z_][\w.]*)", comments)
    for block in re.findall(r"\bthrows\s+(.*?)(?:;|$)", declaration, re.DOTALL):
        values.extend(item.strip() for item in _split_top_level(block) if item.strip())
    values.extend(
        item.strip()
        for block in re.findall(r"\bthrow\s*\((.*?)\)", declaration, re.DOTALL)
        for item in _split_top_level(block)
        if item.strip()
    )
    return tuple(dict.fromkeys(values))


def _parameter(value: str, *, language: str, ordinal: int, direction: str = "in") -> ApiParameter:
    raw = _normalize(value).rstrip(";")
    raw = re.sub(r"\s*=\s*.*$", "", raw).strip()
    raw = re.sub(r"\b(final|const|volatile|register)\b\s*", "", raw).strip()
    match = re.match(
        r"(?P<type>.+?)(?:\s+|\s*)(?P<name>[A-Za-z_]\w*(?:\[\])?)$",
        raw,
    )
    if match is None:
        name = f"arg{ordinal}"
        type_name = raw or "unspecified"
    else:
        name = match.group("name")
        type_name = match.group("type").strip()
    return ApiParameter(
        id=f"parameter-{ordinal}",
        name=name,
        type=type_name,
        direction=direction,  # type: ignore[arg-type]
        optional="=" in value or "Optional" in value,
        description=f"{language} declaration parameter",
    )


def _parameters(value: str, *, language: str, direction: str = "in") -> tuple[ApiParameter, ...]:
    if not value.strip():
        return ()
    return tuple(
        _parameter(item, language=language, ordinal=index, direction=direction)
        for index, item in enumerate(_split_top_level(value), start=1)
    )


def _matching_paren(value: str, opening: int) -> int:
    depth = 0
    for index in range(opening, len(value)):
        if value[index] == "(":
            depth += 1
        elif value[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    return -1


def _cxx_declarations(
    text: str,
    *,
    archive_path: Path,
    entry: str,
    edition: str,
    owner: str,
    interface_kind: str,
) -> tuple[ApiSurface, ...]:
    records: list[ApiSurface] = []
    comments: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*", "*/")):
            comments.append(stripped)
            index += 1
            continue
        if not re.search(r"\bvirtual\b", stripped) or "(" not in stripped:
            if stripped and not stripped.startswith(("#", "public:", "protected:", "private:")):
                comments = comments[-12:]
            index += 1
            continue
        start_line = index + 1
        declaration_lines = [line]
        while ";" not in "\n".join(declaration_lines) and index + 1 < len(lines):
            index += 1
            declaration_lines.append(lines[index])
        declaration = "\n".join(declaration_lines)
        match = re.search(
            r"\bvirtual\s+(?P<return>.+?)\s+(?P<name>~?[A-Za-z_]\w*)\s*\(",
            declaration,
            re.DOTALL,
        )
        if match and not match.group("name").startswith("~") and match.group("name") != owner:
            opening = declaration.find("(", match.start())
            closing = _matching_paren(declaration, opening)
            if closing >= 0:
                name = match.group("name")
                signature = _normalize(declaration).rstrip(";")
                records.append(
                    ApiSurface(
                        id=_stable_id(edition, "cpp", owner, name, signature),
                        name=name,
                        interface_kind=interface_kind,  # type: ignore[arg-type]
                        binding_kind="native",
                        owner=owner,
                        language="cpp",
                        signature=signature,
                        parameters=_parameters(declaration[opening + 1 : closing], language="cpp"),
                        result_type=_normalize(match.group("return")),
                        exception_types=_throws("\n".join(comments), declaration),
                        clause_ids=tuple(
                            item for item in (_clause_id("\n".join(comments)),) if item is not None
                        ),
                        source=_source(f"{_relative(archive_path)}#{entry}", start_line),
                        notes="Extracted from the supplied IEEE C++ API declaration.",
                    )
                )
        comments = []
        index += 1
    return tuple(records)


def _java_declarations(
    text: str,
    *,
    archive_path: Path,
    entry: str,
    edition: str,
    owner: str,
    interface_kind: str,
) -> tuple[ApiSurface, ...]:
    records: list[ApiSurface] = []
    comments: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*", "*/")):
            comments.append(stripped)
            index += 1
            continue
        if "(" not in stripped or stripped.startswith(("@", "if ", "for ", "while ")):
            index += 1
            continue
        start_line = index + 1
        declaration_lines = [line]
        while ";" not in "\n".join(declaration_lines) and index + 1 < len(lines):
            index += 1
            declaration_lines.append(lines[index])
        declaration = "\n".join(declaration_lines)
        match = re.search(
            r"(?P<return>[A-Za-z_][\w.<>?, \[\]]*?)\s+(?P<name>[A-Za-z_]\w*)\s*\(",
            declaration,
            re.DOTALL,
        )
        if match and match.group("name") not in {"if", "for", "while", "switch"}:
            opening = declaration.find("(", match.start())
            closing = _matching_paren(declaration, opening)
            if closing >= 0:
                name = match.group("name")
                signature = _normalize(declaration).rstrip(";")
                records.append(
                    ApiSurface(
                        id=_stable_id(edition, "java", owner, name, signature),
                        name=name,
                        interface_kind=interface_kind,  # type: ignore[arg-type]
                        binding_kind="native",
                        owner=owner,
                        language="java",
                        signature=signature,
                        parameters=_parameters(declaration[opening + 1 : closing], language="java"),
                        result_type=_normalize(match.group("return")),
                        exception_types=_throws("\n".join(comments), declaration),
                        clause_ids=tuple(
                            item for item in (_clause_id("\n".join(comments)),) if item is not None
                        ),
                        source=_source(f"{_relative(archive_path)}#{entry}", start_line),
                        notes="Extracted from the supplied IEEE Java API declaration.",
                    )
                )
        comments = []
        index += 1
    return tuple(records)


def _proto_messages(
    text: str,
    *,
    archive_path: Path,
    entry: str,
    edition: str,
    owner: str,
    interface_kind: str,
) -> tuple[ApiSurface, ...]:
    records: list[ApiSurface] = []
    for match in re.finditer(r"(?m)^\s*message\s+(?P<name>[A-Za-z_]\w*)\s*\{", text):
        name = match.group("name")
        opening = text.find("{", match.start())
        depth = 0
        closing = -1
        for index in range(opening, len(text)):
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
                if depth == 0:
                    closing = index
                    break
        if closing < 0:
            continue
        body = text[opening + 1 : closing]
        direction = "return" if name.endswith("Response") else "in"
        fields: list[ApiParameter] = []
        for field_index, field in enumerate(
            re.finditer(
                r"(?m)^\s*(?:(?:repeated|optional)\s+)?(?P<type>[.\w]+)\s+"
                r"(?P<name>[A-Za-z_]\w*)\s*=\s*\d+\s*(?:\[[^\]]*\])?;",
                body,
            ),
            start=1,
        ):
            fields.append(
                _parameter(
                    f"{field.group('type')} {field.group('name')}",
                    language="fedpro",
                    ordinal=field_index,
                    direction=direction,
                )
            )
        signature = f"message {name}"
        records.append(
            ApiSurface(
                id=_stable_id(edition, "fedpro", owner, name, signature),
                name=name,
                interface_kind=interface_kind,  # type: ignore[arg-type]
                binding_kind="protocol",
                owner=owner,
                language="fedpro",
                protocol="protobuf",
                signature=signature,
                parameters=tuple(fields),
                result_type=None,
                source=_source(
                    f"{_relative(archive_path)}#{entry}",
                    text.count("\n", 0, match.start()) + 1,
                ),
                notes=(
                    "FedPro protobuf message contract; no gRPC service/rpc declaration was present."
                ),
            )
        )
    return tuple(records)


def _wsdl_operations(path: Path, edition: str) -> tuple[ApiSurface, ...]:
    namespace = "http://schemas.xmlsoap.org/wsdl/"
    root = ET.parse(path).getroot()
    records: list[ApiSurface] = []
    for port_type in root.findall(f"{{{namespace}}}portType"):
        owner = port_type.attrib.get("name", "WSAmbassador")
        for operation in port_type.findall(f"{{{namespace}}}operation"):
            name = operation.attrib.get("name", "operation")
            signature = f"wsdl operation {name}"
            records.append(
                ApiSurface(
                    id=_stable_id(edition, "wsdl", owner, name, signature),
                    name=name,
                    interface_kind="service",
                    binding_kind="protocol",
                    owner=owner,
                    language="wsdl",
                    protocol="wsdl",
                    signature=signature,
                    source=_source(_relative(path), 1),
                    notes="Extracted from the supplied IEEE WSDL API definition.",
                )
            )
    return tuple(records)


def _read_zip_entry(path: Path, entry: str) -> str:
    with ZipFile(path) as archive:
        return archive.read(entry).decode("utf-8", errors="replace")


def _unique(records: tuple[ApiSurface, ...]) -> tuple[ApiSurface, ...]:
    """Keep one record for repeated source declarations with identical signatures."""
    unique: dict[str, ApiSurface] = {}
    for record in records:
        unique.setdefault(record.id, record)
    return tuple(unique.values())


def _find_entry(path: Path, suffix: str) -> str:
    with ZipFile(path) as archive:
        matches = [name for name in archive.namelist() if name.endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one {suffix} entry in {path}, found {matches}")
    return matches[0]


def ingest_2010(root: Path) -> tuple[ApiSurface, ...]:
    inbox = resources(root).inbox
    cpp = inbox / "1516.1-2010_downloads" / "IEEE1516-2010_C++_API.zip"
    java = inbox / "1516.1-2010_downloads" / "IEEE1516-2010_Java_API.zip"
    wsdl = inbox / "1516.1-2010_downloads" / "hla1516e.wsdl"
    records: list[ApiSurface] = []
    for archive, language, suffixes in (
        (cpp, "cpp", ("RTI/RTIambassador.h", "RTI/FederateAmbassador.h")),
        (java, "java", ("/RTIambassador.java", "/FederateAmbassador.java")),
    ):
        for suffix in suffixes:
            entry = _find_entry(archive, suffix)
            text = _read_zip_entry(archive, entry)
            owner_key = "RTIambassador" if "RTIambassador" in entry else "FederateAmbassador"
            owner, interface_kind = OWNER_BY_FILE[owner_key]
            parser = _cxx_declarations if language == "cpp" else _java_declarations
            records.extend(
                parser(
                    text,
                    archive_path=archive,
                    entry=entry,
                    edition="2010",
                    owner=owner,
                    interface_kind=interface_kind,
                )
            )
    records.extend(_wsdl_operations(wsdl, "2010"))
    return _unique(tuple(records))


def ingest_2025(root: Path) -> tuple[ApiSurface, ...]:
    archive = resources(root).inbox_file(
        "1516.1-2025_downloads", "1516-2025_API_XML_2025_08_14.zip"
    )
    records: list[ApiSurface] = []
    for suffix in (
        "/cpp/RTI/RTIambassador.h",
        "/cpp/RTI/FederateAmbassador.h",
        "/java/hla/rti1516_2025/RTIambassador.java",
        "/java/hla/rti1516_2025/FederateAmbassador.java",
        "/protobuf/RTIambassador.proto",
        "/protobuf/FederateAmbassador.proto",
        "/protobuf/datatypes.proto",
    ):
        entry = _find_entry(archive, suffix)
        text = _read_zip_entry(archive, entry)
        if suffix.endswith(".h"):
            owner_key = "RTIambassador" if "RTIambassador" in suffix else "FederateAmbassador"
            owner, interface_kind = OWNER_BY_FILE[owner_key]
            records.extend(
                _cxx_declarations(
                    text,
                    archive_path=archive,
                    entry=entry,
                    edition="2025",
                    owner=owner,
                    interface_kind=interface_kind,
                )
            )
        elif suffix.endswith(".java"):
            owner_key = "RTIambassador" if "RTIambassador" in suffix else "FederateAmbassador"
            owner, interface_kind = OWNER_BY_FILE[owner_key]
            records.extend(
                _java_declarations(
                    text,
                    archive_path=archive,
                    entry=entry,
                    edition="2025",
                    owner=owner,
                    interface_kind=interface_kind,
                )
            )
        else:
            if suffix.endswith("datatypes.proto"):
                owner, interface_kind = "FedProDataTypes", "adapter"
            else:
                owner_key = "RTIambassador" if "RTIambassador" in suffix else "FederateAmbassador"
                owner, interface_kind = OWNER_BY_FILE[owner_key]
            records.extend(
                _proto_messages(
                    text,
                    archive_path=archive,
                    entry=entry,
                    edition="2025",
                    owner=owner,
                    interface_kind=interface_kind,
                )
            )
    return _unique(tuple(records))


def write_records(output: Path, records: tuple[ApiSurface, ...]) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = ApiSurfaceFile(schema_version=1, api_surfaces=records).model_dump(mode="json")
    write_json(output, payload)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("2010", "2025"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    records = ingest_2010(args.root) if args.edition == "2010" else ingest_2025(args.root)
    write_records(args.output, records)
    print(f"wrote {len(records)} API surfaces to {args.output}")


if __name__ == "__main__":
    main()
