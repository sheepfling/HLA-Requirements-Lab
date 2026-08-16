"""Minimal language-neutral adapter example.

Replace the TODO symbol discovery and test execution with calls into an RTI
implementation.  The adapter protocol is JSON on stdin/stdout, so an RTI can
implement the same contract in C++, Java, Python, or another language.
"""

from __future__ import annotations

import json
import sys

def main() -> None:
    request = json.load(sys.stdin)
    bindings = []
    for document in request["documents"]:
        for expected in document["bindings"]:
            bindings.append(
                {
                    "id": (
                        f"template.{document['document_id']}."
                        f"{expected['implementation_mapping_id']}.{expected['target']}"
                    ),
                    "document_id": document["document_id"],
                    "implementation_mapping_id": expected["implementation_mapping_id"],
                    "target": expected["target"],
                    "symbol": f"TODO:{expected['interface_name']}",
                    "language": expected["language"],
                    "status": "planned",
                    "api_surface_ids": [],
                    "evidence_ids": [],
                    "notes": "Replace this template with RTI symbol discovery and test execution.",
                }
            )
    json.dump(
        {
            "schema_version": 1,
            "request_id": request["request_id"],
            "adapter_id": "template",
            "repository": "replace-with-rti-repository",
            "coverage_mode": "partial",
            "bindings": bindings,
            "evidence": [],
        },
        sys.stdout,
        ensure_ascii=False,
    )

if __name__ == "__main__":
    main()
