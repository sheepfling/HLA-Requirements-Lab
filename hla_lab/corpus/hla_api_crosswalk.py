"""Generate HLA edition API crosswalks from generic semantic records."""

from __future__ import annotations

import argparse
from pathlib import Path

from hla_lab.corpus.api_crosswalk import ApiTarget, build_api_crosswalk, write_api_crosswalk
from hla_lab.corpus.hla_semantic import load_hla_document_model

HLA_OWNER_BY_INTERFACE = {
    "service": "RTIambassador",
    "callback": "FederateAmbassador",
    "adapter": "FedProDataTypes",
}

def hla_api_targets(edition: str) -> tuple[ApiTarget, ...]:
    """Return the binding/projection targets for one HLA API edition."""
    targets = [
        ApiTarget(
            name="cpp",
            binding_kind="native",
            language="cpp",
            owner_by_interface=HLA_OWNER_BY_INTERFACE,
        ),
        ApiTarget(
            name="java",
            binding_kind="native",
            language="java",
            owner_by_interface=HLA_OWNER_BY_INTERFACE,
        ),
        ApiTarget(
            name="python",
            binding_kind="language-adapter",
            language="python",
            projection=True,
        ),
    ]
    if edition == "2010":
        targets.append(
            ApiTarget(
                name="wsdl",
                binding_kind="protocol",
                language="wsdl",
                protocol="wsdl",
            )
        )
    else:
        targets.extend(
            (
                ApiTarget(
                    name="fedpro",
                    binding_kind="protocol",
                    language="fedpro",
                    protocol="protobuf",
                    owner_by_interface=HLA_OWNER_BY_INTERFACE,
                ),
                ApiTarget(
                    name="grpc",
                    binding_kind="transport",
                    language="grpc",
                    protocol="grpc",
                    projection=True,
                ),
            )
        )
    return tuple(targets)

def generate(root: Path, edition: str, output: Path) -> int:
    """Load an HLA document and write its crosswalk manifest."""
    model = load_hla_document_model(root)
    rows = build_api_crosswalk(model, hla_api_targets(edition))
    write_api_crosswalk(output, rows)
    print(f"wrote {len(rows)} API crosswalks to {output}")
    return len(rows)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("2010", "2025"), required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.root, args.edition, args.output)

if __name__ == "__main__":
    main()
