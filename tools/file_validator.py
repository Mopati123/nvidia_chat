"""Validate rootfile metadata headers."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

META = {
    "tier": "rootfile",
    "layer": "tools",
    "operator_type": "file_validator",
}


@dataclass
class ValidationIssue:
    """A single structural validation issue."""

    path: str
    message: str


@dataclass
class ValidationReport:
    """Validation report returned by rootfile tools."""

    valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)


class FileValidator:
    """Check that rootfile Python modules declare META dictionaries."""

    DEFAULT_ROOTS = (
        "core",
        "data_core",
        "backend_api",
        "tachyonic_chain",
        "tools",
        "infra",
        "registry",
    )

    def __init__(self, roots: Iterable[str] | None = None):
        self.roots = tuple(roots or self.DEFAULT_ROOTS)

    def validate_file(self, path: str | Path) -> ValidationReport:
        path = Path(path)
        issues: List[ValidationIssue] = []
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as exc:
            return ValidationReport(False, [ValidationIssue(str(path), f"syntax error: {exc}")])

        has_meta = any(
            isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "META" for target in node.targets)
            for node in tree.body
        )
        if not has_meta:
            issues.append(ValidationIssue(str(path), "missing META dictionary"))
        return ValidationReport(not issues, issues)

    def validate_tree(self, root: str | Path) -> ValidationReport:
        root = Path(root)
        issues: List[ValidationIssue] = []
        for prefix in self.roots:
            base = root / prefix
            if not base.exists():
                continue
            for path in base.rglob("*.py"):
                report = self.validate_file(path)
                issues.extend(report.issues)
        return ValidationReport(not issues, issues)

