"""Shared test runner configuration."""

from __future__ import annotations

import os

from pytest import Config


def pytest_configure(config: Config) -> None:
    """Expose pytest's selected project root to repository-bound tests."""
    os.environ["HLA_LAB_ROOT"] = str(config.rootpath)
