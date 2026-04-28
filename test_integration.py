#!/usr/bin/env python
"""Root entrypoint for the deterministic core-runtime smoke test."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "validation" / "legacy" / "test_integration.py"),
        run_name="__main__",
    )
