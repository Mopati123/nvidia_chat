from __future__ import annotations

import builtins
import math

import pytest


def _book(symbol: str = "EURUSD", timestamp: float = 1.0) -> dict:
    return {
        "symbol": symbol,
        "timestamp": timestamp,
        "bids": [
            {"price": 1.0998, "volume": 300.0, "count": 3},
            {"price": 1.0997, "volume": 200.0, "count": 2},
            {"price": 1.0996, "volume": 100.0, "count": 1},
        ],
        "asks": [
            {"price": 1.1002, "volume": 100.0, "count": 1},
            {"price": 1.1003, "volume": 100.0, "count": 1},
            {"price": 1.1004, "volume": 100.0, "count": 1},
        ],
    }


def test_order_book_snapshot_normalizes_and_scores_depth_signals():
    from trading.microstructure import OrderBookEngine, OrderBookSnapshot

    snapshot = OrderBookSnapshot.from_dict(_book(), default_symbol="EURUSD")
    assert snapshot.best_bid == pytest.approx(1.0998)
    assert snapshot.best_ask == pytest.approx(1.1002)
    assert snapshot.spread == pytest.approx(0.0004)

    engine = OrderBookEngine("EURUSD", depth_levels=5)
    signals = engine.process_snapshot(_book())
    payload = signals.to_dict()

    assert payload["depth_imbalance"] == pytest.approx((600.0 - 300.0) / 900.0)
    assert payload["layering_score"] == pytest.approx(0.9)
    assert payload["enhanced_microprice"] > snapshot.best_bid
    assert payload["enhanced_microprice"] < snapshot.best_ask
    assert payload["pressure_ratio"] > 1.0
    assert payload["book_inversion"] == 0.0


def test_order_book_snapshot_rejects_malformed_levels():
    from trading.microstructure import OrderBookSnapshot

    missing_side = {"symbol": "EURUSD", "bids": [[1.1, 100.0]], "asks": []}
    with pytest.raises(ValueError, match="non-empty bids and asks"):
        OrderBookSnapshot.from_dict(missing_side)

    negative_volume = _book()
    negative_volume["bids"][0]["volume"] = -1
    with pytest.raises(ValueError, match="volume cannot be negative"):
        OrderBookSnapshot.from_dict(negative_volume)


def test_order_book_detects_iceberg_cumulative_delta_and_inversion():
    from trading.microstructure import OrderBookEngine

    engine = OrderBookEngine("EURUSD", depth_levels=5)
    first = _book(timestamp=1.0)
    drained = _book(timestamp=1.2)
    refilled = _book(timestamp=1.4)
    drained["bids"][0]["volume"] = 40.0
    refilled["bids"][0]["volume"] = 280.0

    engine.process_snapshot(first)
    engine.process_snapshot(drained)
    signals = engine.process_snapshot(refilled)

    assert signals.iceberg_probability > 0.8
    assert signals.cumulative_delta != 0.0

    inverted = _book(timestamp=2.0)
    inverted["bids"][0]["price"] = 1.1005
    inverted["asks"][0]["price"] = 1.1002
    inversion_signals = engine.process_snapshot(inverted)
    assert inversion_signals.book_inversion == 1.0


def test_pipeline_populates_order_book_context_without_new_stage_contract():
    from trading.pipeline.orchestrator import PipelineContext, PipelineOrchestrator

    orchestrator = PipelineOrchestrator(use_microstructure=False)
    context = PipelineContext(
        symbol="EURUSD",
        timestamp=1.0,
        source="synthetic",
        raw_data={"order_book": _book(), "ohlcv": []},
    )

    result = orchestrator._stage_state_construction(context)

    assert result["state_built"] is True
    assert result["order_book_analyzed"] is True
    assert context.order_book is not None
    assert context.hft_signals["depth_imbalance"] > 0
    assert context.market_state["hft_signals"] == context.hft_signals


def test_action_functional_includes_s_hft_only_when_signals_exist():
    from trading.action.upgraded_components import UpgradedActionComponents

    component = UpgradedActionComponents()
    path = [
        {"price": 1.1000, "timestamp": 0.0, "ofi": 0.0},
        {"price": 1.1005, "timestamp": 1.0, "ofi": 0.0},
    ]
    weights = {"L": 0.5, "T": 0.3, "E": 0.1, "R": 0.1}

    without_hft = component.compute_full_action(path, {"ict_geometry": {}}, weights)
    assert "S_HFT" not in without_hft

    hft_signals = {
        "depth_imbalance": -0.5,
        "layering_score": 0.2,
        "enhanced_microprice": 1.0998,
        "pressure_ratio": 0.7,
        "iceberg_probability": 0.1,
        "book_inversion": 0.0,
        "cumulative_delta": -100.0,
    }
    with_hft = component.compute_full_action(
        path,
        {"ict_geometry": {}, "hft_signals": hft_signals},
        weights,
    )

    assert "S_HFT" in with_hft
    assert with_hft["S_HFT"] > 0
    assert with_hft["total_action"] > without_hft["total_action"]


def test_operator_registry_exposes_o19_to_o25_without_breaking_legacy_contract():
    from trading.operators.operator_registry import OperatorRegistry

    registry = OperatorRegistry()
    metadata = registry.get_registry_metadata()
    assert len(registry._legacy_operator_names) == 18

    for name in (
        "depth_imbalance",
        "volume_layering",
        "enhanced_microprice",
        "bid_ask_pressure",
        "iceberg_detection",
        "cumulative_delta_pressure",
        "book_inversion",
    ):
        assert name in metadata
        assert metadata[name]["id"] >= 19

    hft_signals = {
        "depth_imbalance": 0.25,
        "layering_score": -0.9,
        "enhanced_microprice": 1.1001,
        "pressure_ratio": 1.2,
        "iceberg_probability": 0.4,
        "book_inversion": 0.0,
        "cumulative_delta": 42.0,
    }
    scores = registry.get_all_scores({"hft_signals": hft_signals}, {"hft_signals": hft_signals})

    assert scores["depth_imbalance"] == pytest.approx(0.25)
    assert scores["volume_layering"] == pytest.approx(-0.9)
    assert scores["enhanced_microprice"] == pytest.approx(1.1001)
    assert scores["bid_ask_pressure"] == pytest.approx(1.2)
    assert scores["iceberg_detection"] == pytest.approx(0.4)
    assert scores["cumulative_delta_pressure"] == pytest.approx(42.0)


def test_order_book_analytics_do_not_import_execution_surfaces(monkeypatch):
    from trading.microstructure import OrderBookEngine

    real_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name.startswith("trading.brokers") or name.startswith("apps.telegram"):
            raise AssertionError(f"analytics imported execution surface {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    signals = OrderBookEngine("EURUSD").process_snapshot(_book())

    assert math.isfinite(signals.depth_imbalance)
