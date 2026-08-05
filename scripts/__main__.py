"""Show the repository's module-based script entry points."""

from __future__ import annotations

import argparse

CLI_MODULES = (
    "build",
    "compliance",
    "export_state_machine",
    "generate_semantic_blocks",
    "inventory_state_machines",
    "layout_model",
    "reconcile_state_machine_manifest",
    "render_state_machine",
    "review_state_machine",
    "review_state_machines",
    "semantic_metrics",
    "semantic_model",
    "state_machine_metrics",
    "state_machine_queue",
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Use a repository utility as `python -m scripts.<module>`."
    )
    parser.add_argument(
        "module",
        nargs="?",
        choices=CLI_MODULES,
        help="Optional module to look up; invoke it separately with its arguments.",
    )
    args = parser.parse_args()
    if args.module:
        print(f"Run: python -m scripts.{args.module} --help")
        return
    parser.print_help()
    print("\nAvailable modules:")
    for module in CLI_MODULES:
        print(f"  python -m scripts.{module} --help")


if __name__ == "__main__":
    main()
