"""Validate rootfile law metadata against the canonical manifest."""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List

from core.meta import normalize_meta
from core.rootfile_manifest import LAWS, validate_manifest_paths


@dataclass
class RootfileValidationIssue:
    """A single rootfile manifest validation issue."""

    path: str
    message: str


@dataclass
class RootfileValidationReport:
    """Rootfile metadata validation report."""

    valid: bool
    issues: List[RootfileValidationIssue] = field(default_factory=list)


DEFAULT_ROOTS = ("core", "trading", "tachyonic_chain", "tools")
OPERATOR_META_FIELDS = ("tier", "layer", "operator_type", "canonical_law")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _operator_meta_call(node: ast.AST) -> dict | None:
    if not isinstance(node, ast.Call) or _call_name(node.func) != "OperatorMeta":
        return None

    values: dict = {}
    try:
        for index, arg in enumerate(node.args):
            if index >= len(OPERATOR_META_FIELDS):
                return {"__invalid__": "OperatorMeta has too many positional arguments"}
            values[OPERATOR_META_FIELDS[index]] = ast.literal_eval(arg)

        for keyword in node.keywords:
            if keyword.arg is None:
                return {"__invalid__": "OperatorMeta does not support **kwargs in META"}
            values[keyword.arg] = ast.literal_eval(keyword.value)
    except (ValueError, SyntaxError):
        return {"__invalid__": "OperatorMeta META values must be literal"}

    return values


def _literal_meta(path: Path) -> dict | None:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == "META" for target in node.targets):
            continue
        call_meta = _operator_meta_call(node.value)
        if call_meta is not None:
            return call_meta
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            return {"__invalid__": "META must be literal for rootfile validation"}
        return value if isinstance(value, dict) else {"__invalid__": "META must be a dict"}
    return None


def validate_file(path: str | Path, *, strict_missing: bool = False) -> RootfileValidationReport:
    """Validate one Python file's optional rootfile metadata."""
    path = Path(path)
    issues: List[RootfileValidationIssue] = []
    try:
        meta = _literal_meta(path)
    except SyntaxError as exc:
        return RootfileValidationReport(False, [RootfileValidationIssue(str(path), f"syntax error: {exc}")])

    if meta is None:
        if strict_missing:
            issues.append(RootfileValidationIssue(str(path), "missing META"))
        return RootfileValidationReport(not issues, issues)

    if "__invalid__" in meta:
        issues.append(RootfileValidationIssue(str(path), str(meta["__invalid__"])))
        return RootfileValidationReport(False, issues)

    normalized = normalize_meta(meta)
    if normalized.canonical_law and normalized.canonical_law not in LAWS:
        issues.append(
            RootfileValidationIssue(
                str(path),
                f"unknown canonical_law: {normalized.canonical_law}",
            )
        )

    return RootfileValidationReport(not issues, issues)


def validate_tree(
    repo_root: str | Path = ".",
    roots: Iterable[str] = DEFAULT_ROOTS,
    *,
    strict_missing: bool = False,
) -> RootfileValidationReport:
    """Validate manifest directories and Python metadata under selected roots."""
    repo_root = Path(repo_root)
    issues = [
        RootfileValidationIssue(str(repo_root), f"manifest path missing: {missing}")
        for missing in validate_manifest_paths(repo_root)
    ]

    for prefix in roots:
        base = repo_root / prefix
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            report = validate_file(path, strict_missing=strict_missing)
            issues.extend(report.issues)

    return RootfileValidationReport(not issues, issues)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate rootfile canonical law metadata")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--strict-missing", action="store_true")
    args = parser.parse_args(argv)

    report = validate_tree(args.repo_root, strict_missing=args.strict_missing)
    for issue in report.issues:
        print(f"{issue.path}: {issue.message}")
    return 0 if report.valid else 1


if __name__ == "__main__":
    sys.exit(main())
