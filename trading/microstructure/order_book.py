"""
Depth-aware order book analytics for HFT-style microstructure signals.

This module is analytics-only. It normalizes order book snapshots and computes
signals that can improve scoring, but it never routes, authorizes, or executes
orders.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from math import log, sqrt, tanh
from typing import Any, Deque, Dict, Iterable, List, Optional

import numpy as np


@dataclass(frozen=True)
class OrderBookLevel:
    """One resting-liquidity price level."""

    price: float
    volume: float
    count: int = 1
    timestamp: float = 0.0

    @property
    def weighted_price(self) -> float:
        return self.price * self.volume


@dataclass
class OrderBookSnapshot:
    """Normalized bid/ask depth snapshot."""

    symbol: str
    timestamp: float
    bid_levels: List[OrderBookLevel] = field(default_factory=list)
    ask_levels: List[OrderBookLevel] = field(default_factory=list)

    @classmethod
    def from_dict(
        cls,
        snapshot: Dict[str, Any],
        *,
        default_symbol: str = "",
        depth_levels: int = 20,
    ) -> "OrderBookSnapshot":
        if not isinstance(snapshot, dict):
            raise ValueError("order book snapshot must be a dictionary")

        symbol = str(snapshot.get("symbol") or default_symbol or "").upper()
        if not symbol:
            raise ValueError("order book snapshot requires a symbol")

        timestamp = float(snapshot.get("timestamp") or time.time())
        bids = cls._parse_levels(snapshot.get("bids", []), timestamp, depth_levels)
        asks = cls._parse_levels(snapshot.get("asks", []), timestamp, depth_levels)

        if not bids or not asks:
            raise ValueError("order book snapshot requires non-empty bids and asks")

        # Canonical book ordering: highest bid first, lowest ask first.
        bids.sort(key=lambda level: level.price, reverse=True)
        asks.sort(key=lambda level: level.price)

        return cls(symbol=symbol, timestamp=timestamp, bid_levels=bids, ask_levels=asks)

    @staticmethod
    def _parse_levels(
        raw_levels: Iterable[Any],
        timestamp: float,
        depth_levels: int,
    ) -> List[OrderBookLevel]:
        levels: List[OrderBookLevel] = []
        for raw in list(raw_levels)[:depth_levels]:
            if isinstance(raw, dict):
                price = raw.get("price")
                volume = raw.get("volume", raw.get("size"))
                count = raw.get("count", 1)
            elif isinstance(raw, (list, tuple)) and len(raw) >= 2:
                price, volume = raw[0], raw[1]
                count = raw[2] if len(raw) >= 3 else 1
            else:
                raise ValueError(f"invalid order book level: {raw!r}")

            price_f = float(price)
            volume_f = float(volume)
            count_i = int(count)

            if price_f <= 0:
                raise ValueError("order book level price must be positive")
            if volume_f < 0:
                raise ValueError("order book level volume cannot be negative")
            if count_i < 0:
                raise ValueError("order book level count cannot be negative")

            levels.append(
                OrderBookLevel(
                    price=price_f,
                    volume=volume_f,
                    count=count_i,
                    timestamp=timestamp,
                )
            )
        return levels

    @property
    def best_bid(self) -> float:
        return self.bid_levels[0].price if self.bid_levels else 0.0

    @property
    def best_ask(self) -> float:
        return self.ask_levels[0].price if self.ask_levels else 0.0

    @property
    def spread(self) -> float:
        if not self.bid_levels or not self.ask_levels:
            return 0.0
        return self.best_ask - self.best_bid

    @property
    def mid_price(self) -> float:
        if not self.bid_levels or not self.ask_levels:
            return 0.0
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def total_bid_volume(self) -> float:
        return float(sum(level.volume for level in self.bid_levels))

    @property
    def total_ask_volume(self) -> float:
        return float(sum(level.volume for level in self.ask_levels))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "bids": [
                {
                    "price": level.price,
                    "volume": level.volume,
                    "count": level.count,
                }
                for level in self.bid_levels
            ],
            "asks": [
                {
                    "price": level.price,
                    "volume": level.volume,
                    "count": level.count,
                }
                for level in self.ask_levels
            ],
            "spread": self.spread,
            "mid_price": self.mid_price,
        }


@dataclass(frozen=True)
class OrderBookSignals:
    """Computed O19-O25 order-book signal payload."""

    depth_imbalance: float
    layering_score: float
    enhanced_microprice: float
    pressure_ratio: float
    iceberg_probability: float
    book_inversion: float
    cumulative_delta: float
    depth_imbalance_velocity: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "depth_imbalance": float(self.depth_imbalance),
            "layering_score": float(self.layering_score),
            "enhanced_microprice": float(self.enhanced_microprice),
            "pressure_ratio": float(self.pressure_ratio),
            "iceberg_probability": float(self.iceberg_probability),
            "book_inversion": float(self.book_inversion),
            "cumulative_delta": float(self.cumulative_delta),
            "depth_imbalance_velocity": float(self.depth_imbalance_velocity),
        }


class OrderBookEngine:
    """Stateful order-book analytics engine for one symbol."""

    def __init__(self, symbol: str, depth_levels: int = 20, history_size: int = 100):
        self.symbol = symbol.upper()
        self.depth_levels = depth_levels
        self.current_book: Optional[OrderBookSnapshot] = None
        self.previous_book: Optional[OrderBookSnapshot] = None
        self.book_history: Deque[OrderBookSnapshot] = deque(maxlen=history_size)
        self.depth_imbalance_history: Deque[float] = deque(maxlen=history_size)
        self.microprice_history: Deque[float] = deque(maxlen=history_size)
        self.pressure_history: Deque[float] = deque(maxlen=history_size)
        self.cumulative_delta: float = 0.0
        self.last_signals: Optional[OrderBookSignals] = None

    def process_snapshot(self, snapshot: Dict[str, Any] | OrderBookSnapshot) -> OrderBookSignals:
        """Normalize a snapshot, update history, and compute O19-O25 signals."""
        book = (
            snapshot
            if isinstance(snapshot, OrderBookSnapshot)
            else OrderBookSnapshot.from_dict(
                snapshot,
                default_symbol=self.symbol,
                depth_levels=self.depth_levels,
            )
        )
        if book.symbol.upper() != self.symbol:
            raise ValueError(f"snapshot symbol {book.symbol!r} does not match engine symbol {self.symbol!r}")

        self.previous_book = self.current_book
        self.current_book = book
        self.book_history.append(book)

        signals = self.compute_signals()
        self.last_signals = signals
        return signals

    def compute_signals(self) -> OrderBookSignals:
        """Compute the current order-book signal payload."""
        if self.current_book is None:
            return OrderBookSignals(0.0, 0.0, 0.0, 1.0, 0.0, 0.0, self.cumulative_delta)

        depth_imbalance = self._compute_depth_imbalance()
        depth_velocity = 0.0
        if len(self.depth_imbalance_history) >= 2:
            prev = self.depth_imbalance_history[-2]
            curr = self.depth_imbalance_history[-1]
            dt = max(self.current_book.timestamp - (self.previous_book.timestamp if self.previous_book else 0.0), 1e-9)
            depth_velocity = (curr - prev) / dt

        signals = OrderBookSignals(
            depth_imbalance=depth_imbalance,
            layering_score=self._compute_layering(),
            enhanced_microprice=self._compute_enhanced_microprice(),
            pressure_ratio=self._compute_pressure_ratio(),
            iceberg_probability=self._compute_iceberg_probability(),
            book_inversion=self._compute_book_inversion(),
            cumulative_delta=self._update_cumulative_delta(),
            depth_imbalance_velocity=depth_velocity,
        )
        return signals

    def _compute_depth_imbalance(self) -> float:
        book = self.current_book
        if book is None:
            return 0.0
        total = book.total_bid_volume + book.total_ask_volume
        imbalance = 0.0 if total <= 0 else (book.total_bid_volume - book.total_ask_volume) / total
        self.depth_imbalance_history.append(float(imbalance))
        return float(np.clip(imbalance, -1.0, 1.0))

    def _compute_layering(self) -> float:
        book = self.current_book
        if book is None:
            return 0.0

        def coefficient_of_variation(levels: List[OrderBookLevel]) -> float:
            sizes = [level.volume for level in levels[:5] if level.volume > 0]
            if len(sizes) < 3:
                return 1.0
            mean_size = float(np.mean(sizes))
            if mean_size <= 0:
                return 1.0
            return float(np.std(sizes) / mean_size)

        bid_cv = coefficient_of_variation(book.bid_levels)
        ask_cv = coefficient_of_variation(book.ask_levels)

        if bid_cv < 0.15 and bid_cv <= ask_cv:
            return -0.9
        if ask_cv < 0.15:
            return 0.9
        return 0.0

    def _compute_enhanced_microprice(self) -> float:
        book = self.current_book
        if book is None:
            return 0.0
        total_volume = book.total_bid_volume + book.total_ask_volume
        if total_volume <= 0:
            return book.mid_price
        numerator = sum(level.weighted_price for level in book.bid_levels)
        numerator += sum(level.weighted_price for level in book.ask_levels)
        microprice = numerator / total_volume
        self.microprice_history.append(float(microprice))
        return float(microprice)

    def _compute_pressure_ratio(self) -> float:
        book = self.current_book
        if book is None:
            return 1.0
        bid_pressure = sum(level.price * sqrt(level.volume) for level in book.bid_levels[:5] if level.volume > 0)
        ask_pressure = sum(level.price * sqrt(level.volume) for level in book.ask_levels[:5] if level.volume > 0)
        if ask_pressure <= 0:
            ratio = 2.0 if bid_pressure > 0 else 1.0
        else:
            ratio = bid_pressure / ask_pressure
        self.pressure_history.append(float(ratio))
        return float(ratio)

    def _compute_iceberg_probability(self) -> float:
        if len(self.book_history) < 3:
            return 0.0

        older = self.book_history[-3]
        drained = self.book_history[-2]
        current = self.book_history[-1]

        probabilities = []
        for side in ("bid", "ask"):
            older_levels = older.bid_levels if side == "bid" else older.ask_levels
            drained_levels = drained.bid_levels if side == "bid" else drained.ask_levels
            current_levels = current.bid_levels if side == "bid" else current.ask_levels
            for old_level in older_levels[:5]:
                drained_level = self._find_level_by_price(drained_levels, old_level.price)
                current_level = self._find_level_by_price(current_levels, old_level.price)
                if drained_level is None or current_level is None or old_level.volume <= 0:
                    continue
                drained_enough = drained_level.volume <= old_level.volume * 0.55
                refilled = current_level.volume >= old_level.volume * 0.85
                quick = current.timestamp - drained.timestamp <= 1.0
                if drained_enough and refilled and quick:
                    refill_ratio = min(current_level.volume / old_level.volume, 1.25)
                    probabilities.append(min(1.0, 0.6 + 0.25 * refill_ratio))

        return float(max(probabilities) if probabilities else 0.0)

    @staticmethod
    def _find_level_by_price(levels: List[OrderBookLevel], price: float) -> Optional[OrderBookLevel]:
        for level in levels:
            if abs(level.price - price) <= 1e-12:
                return level
        return None

    def _compute_book_inversion(self) -> float:
        book = self.current_book
        if book is None or not book.bid_levels or not book.ask_levels:
            return 0.0
        if book.best_bid > book.best_ask:
            return 1.0
        if book.best_bid == book.best_ask:
            return 0.5
        return 0.0

    def _update_cumulative_delta(self) -> float:
        book = self.current_book
        if book is None:
            return self.cumulative_delta
        if self.previous_book is None:
            return self.cumulative_delta

        bid_delta = book.total_bid_volume - self.previous_book.total_bid_volume
        ask_delta = book.total_ask_volume - self.previous_book.total_ask_volume
        self.cumulative_delta += bid_delta - ask_delta
        return float(self.cumulative_delta)


def pressure_ratio_to_signal(pressure_ratio: float) -> float:
    """Convert a positive pressure ratio into a bounded directional signal."""
    if pressure_ratio <= 0:
        return -1.0
    return float(np.clip(tanh(log(pressure_ratio)), -1.0, 1.0))

