"""Validate scheduler-only token minting rules."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, List

from .file_validator import ValidationIssue, ValidationReport

META = {
    "tier": "rootfile",
    "layer": "tools",
    "operator_type": "kernel_law_validator",
}


class KernelLawValidator:
    """Check that execution-token construction stays in authority/scheduler modules."""

    DEFAULT_ALLOWED = (
        "core/authority/execution_token.py",
        "taep/scheduler/execution_token.py",
        "trading/kernel/scheduler.py",
    )

    def __init__(self, allowed_paths: Iterable[str] | None = None):
        self.allowed_paths = {Path(path).as_posix() for path in (allowed_paths or self.DEFAULT_ALLOWED)}

    def validate_file(self, path: str | Path, root: str | Path | None = None) -> ValidationReport:
        path = Path(path)
        root = Path(root) if root else None
        if root:
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                rel = path.as_posix()
        else:
            rel = path.as_posix()
        text = path.read_text(encoding="utf-8")
        issues: List[ValidationIssue] = []
        if "ExecutionToken(" in text and rel not in self.allowed_paths:
            issues.append(ValidationIssue(rel, "ExecutionToken minted outside scheduler/authority"))
        return ValidationReport(not issues, issues)
