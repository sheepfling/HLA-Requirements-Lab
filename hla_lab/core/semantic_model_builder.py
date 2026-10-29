"""Assemble parsed source and authored records into a document model."""

from __future__ import (
    annotations,
)

import re
from collections.abc import (
    MutableSequence,
    Sequence,
)
from pathlib import (
    Path,
)

from hla_lab.core.semantic_document import (
    DocumentModel,
)
from hla_lab.core.semantic_model_authored import (
    _load_authored_api_crosswalks,
    _load_authored_api_surfaces,
    _load_authored_content_blocks,
    _load_authored_content_elements,
    _load_authored_cross_references,
    _load_authored_definitions,
    _load_authored_figures,
    _load_authored_implementations,
    _load_authored_notes,
    _load_authored_references,
    _load_authored_requirement_api_bindings,
    _load_authored_requirement_links,
    _load_authored_requirement_reviews,
    _load_authored_requirements,
    _load_authored_state_traces,
    _load_authored_table_families,
    _load_authored_tables,
    _load_authored_transition_coverage,
    _load_authored_verification_tests,
)
from hla_lab.core.semantic_model_cross_references import (
    _cross_reference_catalog,
    _derive_cross_references,
    _load_navigation_clauses,
)
from hla_lab.core.semantic_model_records import (
    _heading_context_by_file,
    _hierarchy_headings,
    _load_annexes,
    _load_diagram_surfaces,
    _load_examples,
    _load_figures,
    _load_graph_diagrams,
    _load_notes,
    _load_references,
    _load_requirement_candidates,
    _load_sequence_diagrams,
    _load_state_machines,
    _nearest_heading,
)
from hla_lab.core.semantic_model_resources import (
    _clause_shape,
    _files,
    _source,
    _source_key,
    _source_order,
)
from hla_lab.core.semantic_model_tables import (
    _derive_table_families,
    _link_table_cells_to_definitions,
    _link_table_cells_to_requirements,
    _load_tables,
)
from hla_lab.core.semantic_text import (
    _command_events,
    _commands,
    _definition_text,
    _environments,
    _latex_text,
    _machine_statement,
)
from hla_lab.core.semantic_types import (
    Annex,
    Clause,
    ContentBlock,
    CrossReference,
    Definition,
    DetailedHeading,
    Figure,
    HeadingEvent,
    ImplementationMapping,
    Note,
    Reference,
    Requirement,
    SourceRef,
    Table,
)
from hla_lab.core.source_adapter import (
    LatexSourceProfile,
)


class _DocumentModelBuilder:
    """Assemble the semantic projection in source and authority order."""

    def __init__(self, root: Path, source: LatexSourceProfile) -> None:
        self.root = root
        self.source = source
        self.clauses: dict[str, Clause] = {}
        self.definitions: dict[str, Definition] = {}
        self.requirements: dict[str, Requirement] = {}
        self.state_machines = _load_state_machines(root)
        self.sequence_diagrams = _load_sequence_diagrams(root)
        self.graph_diagrams = _load_graph_diagrams(root)
        self.diagram_surfaces = _load_diagram_surfaces(root)
        self.requirement_reviews = _load_authored_requirement_reviews(root)
        self.requirement_links = _load_authored_requirement_links(root)
        self.transition_coverage = _load_authored_transition_coverage(root)
        self.content_blocks = _load_authored_content_blocks(root)
        self.content_elements = _load_authored_content_elements(root)
        self.table_families = _load_authored_table_families(root)
        self.api_surfaces = _load_authored_api_surfaces(root)
        self.api_crosswalks = _load_authored_api_crosswalks(root)
        self.requirement_api_bindings = _load_authored_requirement_api_bindings(root)
        self.verification_tests = _load_authored_verification_tests(root)
        self.state_traces = _load_authored_state_traces(root)
        self.source_order = _source_order(root)
        self.heading_context = _heading_context_by_file(root, source)
        self.implementations: tuple[ImplementationMapping, ...] = ()
        self.annexes: tuple[Annex, ...] = ()
        self.references: list[Reference] = []
        self.tables: list[Table] = []
        self.notes: list[Note] = []
        self.figures: list[Figure] = []
        self.cross_references: list[CrossReference] = []

    def build(self) -> DocumentModel:
        self._load_page_sources()
        for item in _load_authored_definitions(self.root):
            self.definitions[item.id] = item
        self._load_authored_layout_blocks()
        self._apply_authored_requirements()
        self._materialize_missing_clause_ancestors()
        self._apply_annex_titles()
        self._load_references()
        self._load_tables_and_families()
        self._load_notes_and_figures()
        self._derive_cross_references()
        return self._document()

    def _load_page_sources(self) -> None:
        for path in _files(self.root):
            self._load_page_source(path)

    def _load_page_source(self, path: Path) -> None:
        text = path.read_text(encoding="utf-8")
        headings = list(self.heading_context[path])
        self._add_page_clauses(headings)
        headings.sort(key=lambda item: item[0])
        ordered_headings = tuple(headings)
        self._load_page_definitions(path, text, ordered_headings)
        self._load_page_requirements(path, text, ordered_headings)

    def _add_page_clauses(self, headings: Sequence[HeadingEvent]) -> None:
        for _, identifier, title, heading_source in headings:
            number, parent_id, level = _clause_shape(identifier)
            item = Clause(
                id=identifier,
                number=number,
                title=title,
                parent_id=parent_id,
                level=level,
                source=heading_source,
            )
            previous = self.clauses.get(identifier)
            if previous is None or previous.title.startswith("Content marker "):
                self.clauses[identifier] = item

    def _load_page_definitions(
        self,
        path: Path,
        text: str,
        headings: Sequence[HeadingEvent],
    ) -> None:
        source = self.source
        for offset, args, body_start in _environments(text, source.definition_environment, 2):
            end_marker = text.find(rf"\end{{{source.definition_environment}}}", body_start)
            end_offset = (
                end_marker + len(rf"\end{{{source.definition_environment}}}")
                if end_marker >= 0
                else None
            )
            item = Definition(
                id=args[0],
                term=_latex_text(args[1], source),
                text="",
                clause_id=_nearest_heading(headings, offset),
                source=_source(self.root, path, text, offset, end_offset),
            )
            if end_marker >= 0:
                item = Definition(
                    id=item.id,
                    term=item.term,
                    text=_definition_text(text[body_start:end_marker], source),
                    clause_id=item.clause_id,
                    source=item.source,
                )
            self.definitions.setdefault(item.id, item)

        for offset, args, end_offset in _command_events(text, source.definition_at, 2):
            anchor = _commands(args[1], source.definition_anchor, 1)
            term = _commands(args[1], source.definition_term, 1)
            if not anchor or not term:
                continue
            definition_id = anchor[0][1][0]
            self.definitions.setdefault(
                definition_id,
                Definition(
                    id=definition_id,
                    term=_latex_text(term[0][1][0], source),
                    text=_definition_text(args[1], source),
                    clause_id=_nearest_heading(headings, offset),
                    source=_source(self.root, path, text, offset, end_offset),
                ),
            )

    def _load_page_requirements(
        self,
        path: Path,
        text: str,
        headings: Sequence[HeadingEvent],
    ) -> None:
        detailed_headings = self._collect_page_detailed_headings(path, text)
        self._load_summary_candidates(path, text, headings)
        self._load_detailed_candidates(path, text, detailed_headings)

    def _collect_page_detailed_headings(
        self, path: Path, text: str
    ) -> list[tuple[int, int, str, str, SourceRef]]:
        detailed_headings: list[tuple[int, int, str, str, SourceRef]] = []
        for offset, args, end_offset in _command_events(text, self.source.detailed_rule_heading, 2):
            title = _latex_text(args[1], self.source)
            if not title:
                continue
            detailed_headings.append(
                (
                    offset,
                    end_offset,
                    args[0],
                    title,
                    _source(self.root, path, text, offset, end_offset),
                )
            )
        return detailed_headings

    def _load_summary_candidates(
        self,
        path: Path,
        text: str,
        headings: Sequence[HeadingEvent],
    ) -> None:
        source = self.source
        for offset, args, end_offset in _command_events(text, source.summary_rule, 2):
            prior_clause = [item for item in headings if item[0] < offset]
            clause = prior_clause[-1][1].removeprefix("clause-") if prior_clause else None
            statement = _latex_text(args[1], source)
            if not statement:
                continue
            item = Requirement(
                id=args[0],
                title=args[0].replace("-", " ").title(),
                statement=statement,
                kind="summary",
                clause=clause,
                machine_statement=_machine_statement(args[1], source),
                extraction="candidate",
                source=_source(self.root, path, text, offset, end_offset),
            )
            self.requirements.setdefault(item.id, item)

    def _load_detailed_candidates(
        self,
        path: Path,
        text: str,
        detailed_headings: Sequence[DetailedHeading],
    ) -> None:
        detailed_headings = sorted(detailed_headings, key=lambda item: item[0])
        for offset, args, end_offset in _command_events(
            text, self.source.normative_rule_statement, 1
        ):
            prior = [item for item in detailed_headings if item[0] < offset]
            if not prior:
                continue
            rule_offset, _, rule_id, title, _ = prior[-1]
            clause_match = re.match(r"([A-Za-z]?\d+(?:\.\d+)*)", title)
            statement = _latex_text(args[0], self.source)
            if not statement:
                continue
            item = Requirement(
                id=rule_id,
                title=title,
                statement=statement,
                kind="detailed",
                clause=clause_match.group(1) if clause_match else None,
                machine_statement=_machine_statement(args[0], self.source),
                extraction="candidate",
                source=_source(self.root, path, text, rule_offset, end_offset),
            )
            self.requirements.setdefault(item.id, item)

    def _load_authored_layout_blocks(self) -> None:
        for block in self.content_blocks:
            if block.layout_body is not None:
                self._load_authored_layout_block(block)

    def _load_authored_layout_block(self, block: ContentBlock) -> None:
        if block.layout_body is None:
            return
        virtual_path = self.root / block.source.path
        local_headings = list(
            _hierarchy_headings(self.root, virtual_path, block.layout_body, self.source)
        )
        self._append_pdf_bookmark_headings(block, virtual_path, local_headings)
        self._ensure_layout_block_heading(block, local_headings)
        self._load_layout_block_definitions(block, virtual_path, local_headings)
        self._load_layout_block_clauses(local_headings)

    def _append_pdf_bookmark_headings(
        self,
        block: ContentBlock,
        virtual_path: Path,
        local_headings: MutableSequence[HeadingEvent],
    ) -> None:
        assert block.layout_body is not None
        for offset, args, end_offset in _command_events(
            block.layout_body, self.source.pdf_bookmark, 2
        ):
            if not args[1].startswith("bookmark:clause:"):
                continue
            identifier = f"clause-{args[1].removeprefix('bookmark:clause:')}"
            local_headings.append(
                (
                    offset,
                    identifier,
                    _latex_text(args[0], self.source),
                    _source(self.root, virtual_path, block.layout_body, offset, end_offset),
                )
            )

    @staticmethod
    def _ensure_layout_block_heading(
        block: ContentBlock, local_headings: MutableSequence[HeadingEvent]
    ) -> None:
        if block.clause_id is None or any(item[1] == block.clause_id for item in local_headings):
            return
        local_headings.insert(
            0,
            (
                -1,
                block.clause_id,
                block.clause_id.removeprefix("clause-"),
                block.source,
            ),
        )

    def _load_layout_block_definitions(
        self,
        block: ContentBlock,
        virtual_path: Path,
        local_headings: Sequence[HeadingEvent],
    ) -> None:
        assert block.layout_body is not None
        definition_events = _command_events(block.layout_body, self.source.definition_at, 2)
        for event_index, (offset, args, end_offset) in enumerate(definition_events):
            anchor = _commands(args[1], self.source.definition_anchor, 1)
            term = _commands(args[1], self.source.definition_term, 1)
            if not anchor or not term:
                continue
            definition_id = anchor[0][1][0]
            definition_body = _definition_text(args[1], self.source)
            if not definition_body:
                following_definition = (
                    definition_events[event_index + 1][0]
                    if event_index + 1 < len(definition_events)
                    else len(block.layout_body)
                )
                definition_body = self._layout_definition_body(
                    block.layout_body, end_offset, following_definition
                )
            self.definitions.setdefault(
                definition_id,
                Definition(
                    id=definition_id,
                    term=_latex_text(term[0][1][0], self.source),
                    text=definition_body,
                    clause_id=_nearest_heading(tuple(sorted(local_headings)), offset),
                    source=_source(self.root, virtual_path, block.layout_body, offset, end_offset),
                ),
            )

    def _layout_definition_body(self, body: str, start: int, stop: int) -> str:
        """Recover prose placed in fixed-position blocks after a definition term."""
        layout_commands = (
            ("HLAFixedBlock", 7),
            ("HLAFixedAlphaList", 5),
            ("HLAFixedAlphaListFrom", 6),
        )
        fragments: list[tuple[int, str]] = []
        for command, argument_count in layout_commands:
            for offset, args, _ in _command_events(body, command, argument_count):
                if start <= offset < stop and args[-1].strip():
                    fragments.append((offset, _latex_text(args[-1], self.source)))
        fragments.sort(key=lambda item: item[0])
        return " ".join(text for _, text in fragments if text).strip()

    def _load_layout_block_clauses(self, local_headings: Sequence[HeadingEvent]) -> None:
        for _, identifier, title, heading_source in sorted(local_headings):
            number, parent_id, level = _clause_shape(identifier)
            self.clauses.setdefault(
                identifier,
                Clause(
                    id=identifier,
                    number=number,
                    title=title,
                    parent_id=parent_id,
                    level=level,
                    source=heading_source,
                ),
            )

    def _apply_authored_requirements(self) -> None:
        self.implementations = _load_authored_implementations(self.root)
        for item in _load_navigation_clauses(self.root):
            self.clauses[item.id] = item
        if not self.requirements:
            for item in _load_requirement_candidates(self.root, self.source):
                self.requirements.setdefault(item.id, item)
        for item in _load_authored_requirements(self.root):
            self.requirements[item.id] = item

    def _needed_clause_ids(self) -> set[str]:
        needed = {
            clause.parent_id for clause in self.clauses.values() if clause.parent_id is not None
        }
        needed.update(
            requirement.clause_id
            for requirement in self.requirements.values()
            if requirement.clause_id is not None
        )
        needed.update(
            machine.clause_id for machine in self.state_machines if machine.clause_id is not None
        )
        needed.update(
            transition.clause_id
            for machine in self.state_machines
            for transition in machine.transitions
            if transition.clause_id is not None
        )
        needed.update(
            clause_id
            for implementation in self.implementations
            for clause_id in implementation.clause_ids
        )
        return needed

    def _inferred_clause_source(self, identifier: str) -> SourceRef:
        return next(
            (
                item.source
                for item in (*self.clauses.values(), *self.requirements.values())
                if getattr(item, "parent_id", None) == identifier
                or getattr(item, "clause_id", None) == identifier
            ),
            SourceRef(path="inferred", line=1),
        )

    def _materialize_missing_clause_ancestors(self) -> None:
        needed_clause_ids = self._needed_clause_ids()
        while True:
            missing = sorted(
                identifier for identifier in needed_clause_ids if identifier not in self.clauses
            )
            if not missing:
                break
            for identifier in missing:
                number, parent_id, level = _clause_shape(identifier)
                self.clauses[identifier] = Clause(
                    id=identifier,
                    number=number,
                    title=f"Clause {number}",
                    parent_id=parent_id,
                    level=level,
                    source=self._inferred_clause_source(identifier),
                )
                if parent_id is not None:
                    needed_clause_ids.add(parent_id)

    def _apply_annex_titles(self) -> None:
        self.annexes = _load_annexes(self.root, self.source)
        for annex in self.annexes:
            clause_id = f"clause-{annex.letter}"
            clause = self.clauses.get(clause_id)
            if clause is None:
                continue
            status = f" ({annex.status})" if annex.status != "unknown" else ""
            self.clauses[clause_id] = clause.model_copy(
                update={"title": f"Annex {annex.letter}{status} {annex.title}"}
            )

    def _load_references(self) -> None:
        references = list(_load_references(self.root, self.source))
        authored = {item.id: item for item in _load_authored_references(self.root)}
        self.references = [authored.get(item.id, item) for item in references]
        self.references.extend(
            item
            for item in authored.values()
            if item.id not in {reference.id for reference in self.references}
        )

    def _load_tables_and_families(self) -> None:
        tables = list(_load_tables(self.root, self.source))
        authored = {item.id: item for item in _load_authored_tables(self.root)}
        self.tables = [authored.get(item.id, item) for item in tables]
        self.tables.extend(
            item for item in authored.values() if item.id not in {table.id for table in self.tables}
        )
        self.table_families = list(
            _derive_table_families(
                self.root.name,
                self.tables,
                self.table_families,
                self.content_blocks,
            )
        )
        family_by_table = {
            table_id: family.id for family in self.table_families for table_id in family.table_ids
        }
        self.tables = [
            table.model_copy(update={"family_id": family_by_table.get(table.id)})
            for table in self.tables
        ]
        self.tables = list(_link_table_cells_to_definitions(self.tables, self.definitions.values()))
        self.tables = list(
            _link_table_cells_to_requirements(self.tables, self.requirements.values())
        )

    def _load_notes_and_figures(self) -> None:
        notes = list(_load_notes(self.root, self.source))
        authored_notes = {item.id: item for item in _load_authored_notes(self.root)}
        self.notes = [authored_notes.get(item.id, item) for item in notes]
        self.notes.extend(
            item
            for item in authored_notes.values()
            if item.id not in {note.id for note in self.notes}
        )
        figures = list(_load_figures(self.root, self.source))
        authored_figures = {item.id: item for item in _load_authored_figures(self.root)}
        self.figures = [authored_figures.get(item.id, item) for item in figures]
        self.figures.extend(
            item
            for item in authored_figures.values()
            if item.id not in {figure.id for figure in self.figures}
        )

    def _derive_cross_references(self) -> None:
        examples = _load_examples(self.root, self.source)
        self.content_elements, derived = _derive_cross_references(
            self.root.name,
            self.content_elements,
            _cross_reference_catalog(
                clauses=self.clauses.values(),
                definitions=self.definitions.values(),
                requirements=self.requirements.values(),
                content_blocks=self.content_blocks,
                content_elements=self.content_elements,
                tables=self.tables,
                table_families=self.table_families,
                references=self.references,
                notes=self.notes,
                figures=self.figures,
                examples=examples,
                annexes=self.annexes,
                state_machines=self.state_machines,
                sequence_diagrams=self.sequence_diagrams,
                graph_diagrams=self.graph_diagrams,
                implementations=self.implementations,
                api_surfaces=self.api_surfaces,
                api_crosswalks=self.api_crosswalks,
                verification_tests=self.verification_tests,
                state_traces=self.state_traces,
            ),
            clauses=self.clauses.values(),
            definitions=self.definitions.values(),
            tables=self.tables,
            table_families=tuple(self.table_families),
            figures=self.figures,
        )
        authored = {item.id: item for item in _load_authored_cross_references(self.root)}
        self.cross_references = [authored.get(item.id, item) for item in derived]
        self.cross_references.extend(
            item
            for item in authored.values()
            if item.id not in {xref.id for xref in self.cross_references}
        )

    def _document(self) -> DocumentModel:
        return DocumentModel(
            document_id=self.root.name,
            clauses=tuple(
                sorted(self.clauses.values(), key=lambda item: _source_key(item, self.source_order))
            ),
            definitions=tuple(
                sorted(
                    self.definitions.values(), key=lambda item: _source_key(item, self.source_order)
                )
            ),
            requirements=tuple(
                sorted(
                    self.requirements.values(),
                    key=lambda item: _source_key(item, self.source_order),
                )
            ),
            requirement_reviews=self.requirement_reviews,
            requirement_links=self.requirement_links,
            transition_coverage=self.transition_coverage,
            content_blocks=self.content_blocks,
            content_elements=self.content_elements,
            state_machines=self.state_machines,
            sequence_diagrams=self.sequence_diagrams,
            graph_diagrams=self.graph_diagrams,
            diagram_surfaces=self.diagram_surfaces,
            implementations=self.implementations,
            api_surfaces=self.api_surfaces,
            api_crosswalks=self.api_crosswalks,
            requirement_api_bindings=self.requirement_api_bindings,
            verification_tests=self.verification_tests,
            state_traces=self.state_traces,
            tables=tuple(self.tables),
            table_families=tuple(self.table_families),
            references=tuple(self.references),
            cross_references=tuple(self.cross_references),
            notes=tuple(self.notes),
            figures=tuple(self.figures),
            examples=_load_examples(self.root, self.source),
            annexes=self.annexes,
        )
