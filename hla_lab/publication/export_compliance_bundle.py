"""Export a portable semantic bundle for an external implementation repo."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from hla_lab.core.semantic_model import DocumentModel
from hla_lab.corpus.hla_semantic import load_hla_corpus
from hla_lab.paths import resources
from hla_lab.traceability.compliance_contract import (
    BundleCrosswalk,
    BundleDocument,
    BundleMapping,
    BundleParameter,
    BundleRequirement,
    BundleRequirementApiBinding,
    BundleSource,
    BundleSurface,
    BundleTransition,
    CorpusBundle,
)

def edition_roots(corpus_root: Path, edition: str) -> tuple[Path, ...]:
    """Resolve one or both HLA edition tranches from a corpus checkout."""
    years = ("2010", "2025") if edition == "all" else (edition,)
    repo_resources = resources(corpus_root)
    return tuple(
        repo_resources.ieee_topics / f"hla-{suffix}-{year}"
        for year in years
        for suffix in ("1516", "1516.1", "1516.2")
    )

def _document(model: DocumentModel) -> BundleDocument:
    transitions = tuple(
        BundleTransition(
            id=transition.id,
            machine_id=machine.id,
            event=transition.event,
            source_state=transition.source_state,
            target_state=transition.target_state,
            requirement_ids=transition.requirement_ids,
        )
        for machine in model.state_machines
        for transition in machine.transitions
    )
    return BundleDocument(
        document_id=model.document_id,
        requirements=tuple(
            BundleRequirement(
                id=item.id,
                clause_id=item.clause_id,
                title=item.title,
                statement=item.statement,
            )
            for item in model.requirements
        ),
        transitions=transitions,
        mappings=tuple(
            BundleMapping(
                id=item.id,
                interface_kind=item.interface_kind,
                interface_name=item.interface_name,
                requirement_ids=item.requirement_ids,
                transition_ids=item.transition_ids,
            )
            for item in model.implementations
        ),
        api_surfaces=tuple(
            BundleSurface(
                id=item.id,
                name=item.name,
                binding_kind=item.binding_kind,
                owner=item.owner,
                language=item.language,
                protocol=item.protocol,
                signature=item.signature,
                parameters=tuple(
                    BundleParameter(
                        id=parameter.id,
                        name=parameter.name,
                        type=parameter.type,
                        direction=parameter.direction,
                        optional=parameter.optional,
                    )
                    for parameter in item.parameters
                ),
                result_type=item.result_type,
                exception_types=item.exception_types,
                source=(
                    BundleSource(
                        path=item.source.path,
                        line=item.source.line,
                        end_line=item.source.end_line,
                    )
                    if item.source is not None
                    else None
                ),
            )
            for item in model.api_surfaces
        ),
        api_crosswalks=tuple(
            BundleCrosswalk(
                id=item.id,
                implementation_mapping_id=item.implementation_mapping_id,
                target=item.target,
                binding_kind=item.binding_kind,
                language=item.language,
                protocol=item.protocol,
                status=item.status,
                candidate_api_surface_ids=item.candidate_api_surface_ids,
                selected_api_surface_ids=item.selected_api_surface_ids,
            )
            for item in model.api_crosswalks
        ),
        requirement_api_bindings=tuple(
            BundleRequirementApiBinding(
                id=item.id,
                requirement_id=item.requirement_id,
                api_surface_id=item.api_surface_id,
                candidate_api_surface_ids=item.candidate_api_surface_ids,
                language=item.language,
                relationship=item.relationship,
                status=item.status,
                rationale=item.rationale,
                source=BundleSource(
                    path=item.source.path,
                    line=item.source.line,
                    end_line=item.source.end_line,
                ),
            )
            for item in model.requirement_api_bindings
        ),
    )

def export_bundle(
    roots: tuple[Path, ...],
    *,
    bundle_id: str,
    corpus_revision: str,
    output: Path,
) -> CorpusBundle:
    """Load HLA sources and emit a validated portable bundle."""
    corpus = load_hla_corpus(roots)
    bundle = CorpusBundle(
        schema_version=1,
        bundle_id=bundle_id,
        corpus_revision=corpus_revision,
        documents=tuple(_document(model) for model in corpus.documents),
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return bundle

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--edition", choices=("2010", "2025", "all"), default="all")
    parser.add_argument("--revision", default="working-tree")
    parser.add_argument("--bundle-id", default="hla-semantic-corpus")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = export_bundle(
        edition_roots(args.corpus_root, args.edition),
        bundle_id=args.bundle_id,
        corpus_revision=args.revision,
        output=args.output,
    )
    print(f"wrote {len(bundle.documents)} documents to {args.output}")

if __name__ == "__main__":
    main()
