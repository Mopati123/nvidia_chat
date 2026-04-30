"""Tests for rootfile structural validators."""

from pathlib import Path

from tools.file_validator import FileValidator
from tools.import_check import ImportCheck
from tools.kernel_law_validator import KernelLawValidator
from tools.token_flow_validator import TokenFlowValidator


def test_file_validator_flags_missing_meta(tmp_path: Path):
    path = tmp_path / "module.py"
    path.write_text("VALUE = 1\n", encoding="utf-8")

    report = FileValidator().validate_file(path)

    assert not report.valid
    assert "missing META" in report.issues[0].message


def test_import_check_flags_upward_import(tmp_path: Path):
    path = tmp_path / "state_prep.py"
    path.write_text("from backend_api.telegram import handler\n", encoding="utf-8")

    report = ImportCheck().validate_file(path, "data_core.ingestion.state_prep")

    assert not report.valid
    assert "illegal upward import" in report.issues[0].message


def test_token_flow_validator_flags_unguarded_execution(tmp_path: Path):
    path = tmp_path / "unsafe_execution.py"
    path.write_text(
        "def execute_trade(symbol):\n"
        "    return place_order(symbol)\n",
        encoding="utf-8",
    )

    report = TokenFlowValidator().validate_file(path)

    assert not report.valid
    assert "validate_token" in report.issues[0].message


def test_kernel_law_validator_flags_token_minting_outside_authority(tmp_path: Path):
    path = tmp_path / "random_module.py"
    path.write_text("token = ExecutionToken('TRADE', 1.0, 9999999999.0)\n", encoding="utf-8")

    report = KernelLawValidator(allowed_paths=()).validate_file(path)

    assert not report.valid
    assert "outside scheduler/authority" in report.issues[0].message


def test_valid_rootfile_adapter_passes_metadata_check(tmp_path: Path):
    path = tmp_path / "adapter.py"
    path.write_text(
        "META = {'tier': 'rootfile', 'layer': 'core.execution', 'operator_type': 'adapter'}\n",
        encoding="utf-8",
    )

    report = FileValidator().validate_file(path)

    assert report.valid

