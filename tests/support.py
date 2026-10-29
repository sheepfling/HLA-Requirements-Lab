"""Common paths and helpers for repository-bound tests."""

from __future__ import annotations

import os
from pathlib import Path

TEST_REPO_ROOT = Path(os.environ["HLA_LAB_ROOT"]).resolve()
