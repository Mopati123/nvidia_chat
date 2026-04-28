"""Validate token checks around execution boundaries."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from .file_validator import ValidationIssue, ValidationReport

META = {
    "tier": "rootfile",
    "layer": "tools",
    "operator_type": "token_flow_validator",
}


class TokenFlowValidator:
    """Check dangerous execution functions mention token validation."""

    DANGEROUS_NAMES = {
        "execute_trade",
        "execute_shadow",
        "place_order",
        "place_contract",
    }

    def validate_file(self, path: str | Path) -> ValidationReport:
        path = Path(path)
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text)
        issues: List[ValidationIssue] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef) or node.name not in self.DANGEROUS_NAMES:
                continue
            arg_names = {arg.arg for arg in node.args.args + node.args.kwonlyargs}
            segment = ast.get_source_segment(text, node) or ""
            has_validation = "validate_token" in segment
            if "token" not in arg_names or not has_validation:
                issues.append(
                    ValidationIssue(
                        str(path),
                        f"{node.name} must accept token and call validate_token",
                    )
                )
        return ValidationReport(not issues, issues)

