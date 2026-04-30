#!/usr/bin/env python
"""Root entrypoint for the acceleration and fallback integration check."""

from __future__ import annotations

import runpy
from pathlib import Path


if __name__ == "__main__":
    runpy.run_path(
        str(Path(__file__).resolve().parent / "validation" / "legacy" / "test_integration_final.py"),
        run_name="__main__",
    )
