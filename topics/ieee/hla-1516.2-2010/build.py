"""Manifest-driven build entry point for IEEE 1516.2-2010."""

from __future__ import annotations

from pathlib import Path

from hla_lab.build.topic import main

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__":
    raise SystemExit(main(root=ROOT))
