"""Compatibility helpers for importing Torch on Windows test hosts."""

from __future__ import annotations

import os


def prepare_torch_import() -> None:
    """Avoid Python 3.14 Windows WMI hangs during ``torch`` platform probing."""
    if os.name != "nt":
        return
    try:
        import platform

        if getattr(platform, "_uname_cache", None) is None:
            machine = os.environ.get("PROCESSOR_ARCHITECTURE") or "AMD64"
            platform._uname_cache = platform.uname_result("Windows", "", "10", "", machine)
    except Exception:
        return
