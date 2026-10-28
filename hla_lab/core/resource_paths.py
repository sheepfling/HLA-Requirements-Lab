"""Small filesystem path bundles shared across semantic package layers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DocumentResources:
    """Repository-owned paths belonging to one document product."""

    root: Path

    @property
    def canonical(self) -> Path:
        return self.root / "canonical"

    @property
    def semantic(self) -> Path:
        return self.root / "semantic"

    @property
    def sections(self) -> Path:
        return self.root / "sections"

    @property
    def output(self) -> Path:
        return self.root / "output"

    @property
    def output_semantic(self) -> Path:
        return self.output / "semantic"

    @property
    def build(self) -> Path:
        return self.root / "build"

    @property
    def dist(self) -> Path:
        return self.root / "dist"

    @property
    def main_tex(self) -> Path:
        return self.root / "main.tex"

    def canonical_file(self, name: str) -> Path:
        return self.canonical / name

    def semantic_file(self, name: str) -> Path:
        return self.semantic / name

    def output_file(self, name: str) -> Path:
        return self.output / name

    def output_semantic_file(self, name: str) -> Path:
        return self.output_semantic / name
