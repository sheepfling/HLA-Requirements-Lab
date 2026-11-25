"""Restore omitted service-flow records and their source/API ownership."""

from __future__ import annotations

from pathlib import Path

from hla_lab.core.hla_profile import HLA_SOURCE
from hla_lab.core.semantic_model import load_document_model
from hla_lab.core.semantic_types import SourceRef
from hla_lab.corpus.api_crosswalk import (
    build_requirement_api_bindings,
    write_requirement_api_bindings,
)
from tools.migrations.backflow_common import (
    _MutableRequirement,
    _MutableRequirementFile,
    _read_api_surfaces,
    _read_content_blocks,
    _read_content_elements,
    _read_requirements,
    _write_api_surfaces,
    _write_content_blocks,
    _write_content_elements,
    _write_requirements,
    semantic_root,
)

TAR_PRECONDITION = "requirement-service-flow-tar-current-time-precondition"
TAR_EXCEPTION = "requirement-service-flow-tar-time-passed-exception"
TARA_EQUAL_TIME_PERMISSION = "requirement-service-flow-tara-equal-time-send-permission"
RECEIVE_INTERACTION_TAG = (
    "requirement-candidate-content-clauses-06-object-management-page-125-l82-23"
)


def _ensure_record(
    requirements: _MutableRequirementFile,
    *,
    requirement_id: str,
    title: str,
    statement: str,
    clause: str,
    source: SourceRef,
    semantic_group_id: str,
) -> _MutableRequirement:
    by_id = {item.id: item for item in requirements.requirements}
    record = by_id.get(requirement_id)
    if record is None:
        record = _MutableRequirement(
            id=requirement_id,
            title=title,
            statement=statement,
            kind="detailed",
            clause=clause,
            clause_id=f"clause-{clause}",
            machine_statement=statement,
            transition_ids=(),
            coverage_kind="cross-cutting",
            coverage_note=(
                "Explicit service-flow behavior or precondition from the pinned 2025 source."
            ),
            api_surface_scope="required",
            api_surface_note=(
                "Reviewed against the corresponding 2025 API declaration and service clause."
            ),
            api_surface_resolution="strict",
            extraction="explicit",
            semantic_group_id=semantic_group_id,
            source=source,
        )
        requirements.requirements.append(record)
    else:
        record.title = title
        record.statement = statement
        record.machine_statement = statement
        record.clause = clause
        record.clause_id = f"clause-{clause}"
        record.semantic_group_id = semantic_group_id
        record.source = source
    return record


def _attach_record(requirement_id: str, page: int) -> None:
    block_id = f"content-15161-page-{page}"
    blocks = _read_content_blocks()
    block = next((item for item in blocks.content_blocks if item.id == block_id), None)
    if block is None:
        raise ValueError(f"missing source content block {block_id}")
    if requirement_id not in block.record_ids:
        block.record_ids += (requirement_id,)
    _write_content_blocks(blocks)

    elements = _read_content_elements()
    matching = [item for item in elements.content_elements if item.block_id == block_id]
    if not matching:
        raise ValueError(f"missing typed source content element for {block_id}")
    for element in matching:
        if requirement_id not in element.record_ids:
            element.record_ids += (requirement_id,)
    _write_content_elements(elements)


def _attach_api(requirement_id: str, surface_ids: tuple[str, ...]) -> None:
    surfaces = _read_api_surfaces()
    by_id = {item.id: item for item in surfaces.api_surfaces}
    for surface_id in surface_ids:
        surface = by_id.get(surface_id)
        if surface is None:
            raise ValueError(f"missing declared API surface {surface_id}")
        if requirement_id not in surface.requirement_ids:
            surface.requirement_ids += (requirement_id,)
    _write_api_surfaces(surfaces)


def _add_service_flow(
    requirements: _MutableRequirementFile,
    *,
    requirement_id: str,
    title: str,
    statement: str,
    clause: str,
    page: int,
    line: int,
    end_line: int,
    api_surface_ids: tuple[str, ...],
) -> None:
    source = SourceRef(
        path=f"content/clauses/08-time-management-page-{page}.tex",
        line=line,
        end_line=end_line,
    )
    record = _ensure_record(
        requirements,
        requirement_id=requirement_id,
        title=title,
        statement=statement,
        clause=clause,
        source=source,
        semantic_group_id=f"m17.service-flow.{clause}",
    )
    _attach_record(record.id, page)
    _attach_api(record.id, api_surface_ids)


def repair_tar_tara_and_receive_tag_flows(
    workspace_root: Path | None = None,
) -> tuple[str, ...]:
    """Restore TAR/TARA service-flow items and the Receive Interaction tag subject."""
    semantic = semantic_root(workspace_root)
    document_root = semantic.parent
    requirements = _read_requirements()
    blocks = _read_content_blocks()
    block_by_id = {item.id: item for item in blocks.content_blocks}

    # Keep each new record tied to a visible source span before writing anything.
    expected_spans = {
        194: ((127, "specified logical time"),),
        195: (
            (42, "Logical time already passed"),
            (132, "can send additional messages with timestamps equal to"),
        ),
        125: ((80, "user-supplied tag argument"),),
    }
    for page, spans in expected_spans.items():
        block = block_by_id.get(f"content-15161-page-{page}")
        if block is None or not block.layout_body:
            raise ValueError(f"missing layout source for page {page}")
        lines = block.layout_body.splitlines()
        for line, witness in spans:
            if line > len(lines) or witness not in lines[line - 1]:
                raise ValueError(
                    f"source witness missing at page {page} line {line}: {witness}"
                )

    page_194 = block_by_id["content-15161-page-194"].layout_body.splitlines()
    page_195 = block_by_id["content-15161-page-195"].layout_body.splitlines()
    page_125 = block_by_id["content-15161-page-125"].layout_body.splitlines()

    _add_service_flow(
        requirements,
        requirement_id=TAR_PRECONDITION,
        title="Time Advance Request current-time precondition",
        statement=(
            "For Time Advance Request, the specified logical time shall be greater than "
            "or equal to the joined federate's logical time."
        ),
        clause="8.8.3",
        page=194,
        line=127,
        end_line=127,
        api_surface_ids=(
            "api.2025.cpp.rtiambassador.timeadvancerequest.1bad7a98bd8a",
            "api.2025.java.rtiambassador.timeadvancerequest.48efe3b050d6",
        ),
    )
    _add_service_flow(
        requirements,
        requirement_id=TAR_EXCEPTION,
        title="Time Advance Request passed-time exception",
        statement=(
            "Time Advance Request declares Logical Time Already Passed as an exception "
            "when its specified logical time is behind the joined federate's logical time."
        ),
        clause="8.8.5",
        page=195,
        line=42,
        end_line=42,
        api_surface_ids=(
            "api.2025.cpp.rtiambassador.timeadvancerequest.1bad7a98bd8a",
            "api.2025.java.rtiambassador.timeadvancerequest.48efe3b050d6",
        ),
    )
    _add_service_flow(
        requirements,
        requirement_id=TARA_EQUAL_TIME_PERMISSION,
        title="Time Advance Request Available equal-time send permission",
        statement=(
            "After receiving a Time Advance Grant to logical time T in response to Time "
            "Advance Request Available, the joined federate may send additional messages "
            "timestamped T if its actual lookahead is zero."
        ),
        clause="8.9",
        page=195,
        line=129,
        end_line=135,
        api_surface_ids=(
            "api.2025.cpp.rtiambassador.timeadvancerequestavailable.44aebf48db58",
            "api.2025.java.rtiambassador.timeadvancerequestavailable.797b74875983",
        ),
    )

    tag_id = RECEIVE_INTERACTION_TAG
    tag = next((item for item in requirements.requirements if item.id == tag_id), None)
    if tag is None:
        raise ValueError(f"missing Receive Interaction tag candidate {tag_id}")
    tag.statement = (
        "The user-supplied tag argument supplied to the corresponding Send Interaction "
        "or Send Interaction With Regions service invocation shall be provided with all "
        "corresponding Receive Interaction service invocations."
    )
    tag.machine_statement = tag.statement
    tag.source = SourceRef(
        path="content/clauses/06-object-management-page-125.tex",
        line=80,
        end_line=87,
    )
    if tag.id not in block_by_id["content-15161-page-125"].record_ids:
        block_by_id["content-15161-page-125"].record_ids += (tag.id,)
        _write_content_blocks(blocks)

    # The bookmark is navigation metadata. The visible source heading on the
    # preceding page establishes §8.1.7, “Putting it all together”; this page's
    # TSO continuation must not reopen the earlier Lookahead subsection.
    page_185 = block_by_id.get("content-15161-page-185")
    if page_185 is None or not page_185.layout_body:
        raise ValueError("missing page-185 navigation source")
    stale_bookmark = r"\HLAServiceBookmark{8.1.6}{2}{Lookahead}"
    correct_bookmark = r"\HLAServiceBookmark{8.1.7}{2}{Putting it all together}"
    if stale_bookmark not in page_185.layout_body and correct_bookmark not in page_185.layout_body:
        raise ValueError("page-185 navigation bookmark differs from the reviewed source")
    if stale_bookmark in page_185.layout_body:
        page_185.layout_body = page_185.layout_body.replace(stale_bookmark, correct_bookmark)
        _write_content_blocks(blocks)

    _write_requirements(requirements)

    model = load_document_model(document_root, HLA_SOURCE)
    write_requirement_api_bindings(
        semantic / "api-requirement-bindings.json",
        build_requirement_api_bindings(model),
    )
    return TAR_PRECONDITION, TAR_EXCEPTION, TARA_EQUAL_TIME_PERMISSION, tag_id
