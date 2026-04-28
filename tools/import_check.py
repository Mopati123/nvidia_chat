"""Check import direction across rootfile layers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import List

from .file_validator import ValidationIssue, ValidationReport

META = {
    "tier": "rootfile",
    "layer": "tools",
    "operator_type": "import_check",
}


class ImportCheck:
    """Validate simple downward-causality import rules for rootfile packages."""

    LAYER_RANK = {
        "registry": 0,
        "config": 0,
        "data_core": 1,
        "core.simulation": 2,
        "core.orchestration": 3,
        "core.authority": 3,
        "core.execution": 4,
        "backend_api": 5,
        "tachyonic_chain": 6,
        "tools": 7,
        "infra": 7,
    }

    def _module_layer(self, module: str | None) -> str | None:
        if not module:
            return None
        parts = module.split(".")
        if parts[0] == "core" and len(parts) > 1:
            return ".".join(parts[:2])
        return parts[0]

    def validate_file(self, path: str | Path, module_name: str) -> ValidationReport:
        path = Path(path)
        current_layer = self._module_layer(module_name)
        current_rank = self.LAYER_RANK.get(current_layer or "", 99)
        issues: List[ValidationIssue] = []

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            imported = None
            if isinstance(node, ast.ImportFrom):
                imported = node.module
            elif isinstance(node, ast.Import) and node.names:
                imported = node.names[0].name
            imported_layer = self._module_layer(imported)
            if imported_layer not in self.LAYER_RANK:
                continue
            imported_rank = self.LAYER_RANK[imported_layer]
            if imported_rank > current_rank:
                issues.append(
                    ValidationIssue(
                        str(path),
                        f"illegal upward import from {current_layer} to {imported_layer}",
                    )
                )
        return ValidationReport(not issues, issues)

