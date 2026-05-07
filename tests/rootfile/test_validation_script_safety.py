"""Validation CLI safety defaults."""

from __future__ import annotations

import scripts.validation.generate_validation_report as validation_report
import scripts.validation.preflight_check as preflight
import scripts.validation.run_full_validation as full_validation


def test_preflight_defaults_skip_broker_network_and_state_mutation(monkeypatch):
    calls = []
    monkeypatch.setattr(preflight, "check_paper_mode", lambda: True)
    monkeypatch.setattr(preflight, "check_risk_limits", lambda: True)
    monkeypatch.setattr(
        preflight,
        "check_broker_connections",
        lambda allow_network=False: calls.append(("broker", allow_network)) or True,
    )
    monkeypatch.setattr(
        preflight,
        "clear_stale_state",
        lambda allow_mutation=False: calls.append(("clear", allow_mutation)) or True,
    )
    monkeypatch.setattr(
        preflight,
        "initialize_backtest_logger",
        lambda allow_mutation=False: calls.append(("logger", allow_mutation)) or True,
    )

    assert preflight.main([]) == 0
    assert calls == [("broker", False), ("clear", False), ("logger", False)]


def test_preflight_opt_in_flags_enable_broker_and_state_actions(monkeypatch):
    calls = []
    monkeypatch.setattr(preflight, "check_paper_mode", lambda: True)
    monkeypatch.setattr(preflight, "check_risk_limits", lambda: True)
    monkeypatch.setattr(
        preflight,
        "check_broker_connections",
        lambda allow_network=False: calls.append(("broker", allow_network)) or True,
    )
    monkeypatch.setattr(
        preflight,
        "clear_stale_state",
        lambda allow_mutation=False: calls.append(("clear", allow_mutation)) or True,
    )
    monkeypatch.setattr(
        preflight,
        "initialize_backtest_logger",
        lambda allow_mutation=False: calls.append(("logger", allow_mutation)) or True,
    )

    assert preflight.main(["--allow-broker-network", "--allow-state-mutation"]) == 0
    assert calls == [("broker", True), ("clear", True), ("logger", True)]


def test_clear_stale_state_default_does_not_delete_files(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    state_file = tmp_path / "trading_data" / "pnl" / "state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text("{}", encoding="utf-8")

    assert preflight.clear_stale_state() is True

    assert state_file.exists()


def test_full_validation_default_skips_broker_category_and_report_write(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    safe_file = tmp_path / "safe_validation.py"
    broker_file = tmp_path / "broker_validation.py"
    safe_file.write_text("print('safe')\n", encoding="utf-8")
    broker_file.write_text("print('broker')\n", encoding="utf-8")
    monkeypatch.setattr(
        full_validation,
        "TEST_CATEGORIES",
        {
            "Phase 1: Smoke Tests (Fast)": [(str(safe_file), 1)],
            "Phase 4: Infrastructure & Broker Tests": [(str(broker_file), 1)],
        },
    )
    calls = []
    monkeypatch.setattr(
        full_validation,
        "run_test",
        lambda test_file, timeout, allow_broker_network=False: (
            calls.append((test_file, allow_broker_network))
            or {
                "file": test_file,
                "passed": True,
                "elapsed": 0.0,
                "passed_count": 1,
                "failed_count": 0,
            }
        ),
    )

    assert full_validation.main([]) == 0

    assert calls == [(str(safe_file), False)]
    assert not list(tmp_path.glob("OFFLINE_VALIDATION_SUMMARY_*.txt"))


def test_validation_report_default_avoids_live_approval_language():
    report = validation_report.build_report()

    assert "PRODUCTION READY" not in report
    assert "approve live trading" in report
