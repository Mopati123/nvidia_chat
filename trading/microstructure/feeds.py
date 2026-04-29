"""Read-only order-book feed adapters.

These adapters normalize live or replayed depth data into OrderBookSnapshot
objects. They never place orders, import broker execution modules, or handle
private trading credentials.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional

from .order_book import OrderBookSnapshot


class OrderBookFeedError(RuntimeError):
    """Base exception raised by read-only order-book feeds."""


class FeedSnapshotError(OrderBookFeedError):
    """Raised when a feed receives malformed order-book data."""


@dataclass
class FeedHealth:
    """Runtime health snapshot for a read-only depth feed."""

    source: str
    connected: bool = False
    last_update_ts: Optional[float] = None
    queue_depth: int = 0
    dropped_updates: int = 0
    reconnect_count: int = 0
    stale_after_seconds: float = 5.0
    last_error: Optional[str] = None

    @property
    def update_age_seconds(self) -> Optional[float]:
        if self.last_update_ts is None:
            return None
        return max(0.0, time.time() - self.last_update_ts)

    @property
    def stale(self) -> bool:
        age = self.update_age_seconds
        return age is None or age > self.stale_after_seconds

    def mark_update(self, *, queue_depth: int = 0, timestamp: Optional[float] = None) -> None:
        self.connected = True
        self.last_update_ts = timestamp or time.time()
        self.queue_depth = queue_depth
        self.last_error = None

    def mark_error(self, error: BaseException | str) -> None:
        self.last_error = str(error)

    def mark_disconnected(self) -> None:
        self.connected = False

    def mark_reconnect(self) -> None:
        self.reconnect_count += 1

    def mark_drop(self) -> None:
        self.dropped_updates += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "connected": self.connected,
            "last_update_ts": self.last_update_ts,
            "update_age_seconds": self.update_age_seconds,
            "queue_depth": self.queue_depth,
            "dropped_updates": self.dropped_updates,
            "reconnect_count": self.reconnect_count,
            "stale": self.stale,
            "last_error": self.last_error,
        }


class OrderBookFeed:
    """Base class for read-only normalized order-book feeds."""

    def __init__(
        self,
        *,
        source: str,
        symbol: str,
        depth_levels: int = 20,
        stale_after_seconds: float = 5.0,
    ) -> None:
        self.source = source
        self.symbol = symbol.upper()
        self.depth_levels = depth_levels
        self.health = FeedHealth(source=source, stale_after_seconds=stale_after_seconds)

    async def snapshots(self) -> AsyncIterator[OrderBookSnapshot]:
        """Yield normalized order-book snapshots."""
        raise NotImplementedError

    def health_snapshot(self) -> Dict[str, Any]:
        return self.health.to_dict()

    def _normalize(self, snapshot: Dict[str, Any] | OrderBookSnapshot) -> OrderBookSnapshot:
        try:
            if isinstance(snapshot, OrderBookSnapshot):
                book = snapshot
            else:
                book = OrderBookSnapshot.from_dict(
                    snapshot,
                    default_symbol=self.symbol,
                    depth_levels=self.depth_levels,
                )
        except Exception as exc:  # noqa: BLE001 - rewrap with feed context
            self.health.mark_error(exc)
            raise FeedSnapshotError(f"{self.source} emitted malformed order book: {exc}") from exc

        if book.symbol.upper() != self.symbol:
            error = FeedSnapshotError(
                f"{self.source} emitted symbol {book.symbol!r}, expected {self.symbol!r}"
            )
            self.health.mark_error(error)
            raise error
        return book


class FakeOrderBookFeed(OrderBookFeed):
    """Deterministic in-memory feed for tests and local simulations."""

    def __init__(
        self,
        snapshots: Iterable[Dict[str, Any] | OrderBookSnapshot],
        *,
        symbol: str,
        source: str = "fake",
        interval_seconds: float = 0.0,
        depth_levels: int = 20,
    ) -> None:
        super().__init__(source=source, symbol=symbol, depth_levels=depth_levels)
        self._snapshots = list(snapshots)
        self.interval_seconds = interval_seconds

    async def snapshots(self) -> AsyncIterator[OrderBookSnapshot]:
        self.health.connected = True
        try:
            for raw in self._snapshots:
                book = self._normalize(raw)
                self.health.mark_update(queue_depth=0, timestamp=book.timestamp)
                yield book
                if self.interval_seconds > 0:
                    await asyncio.sleep(self.interval_seconds)
        finally:
            self.health.mark_disconnected()


class ReplayOrderBookFeed(FakeOrderBookFeed):
    """Replay a finite sequence of JSONL or in-memory order-book snapshots."""

    @classmethod
    def from_jsonl(
        cls,
        path: str | Path,
        *,
        symbol: str,
        source: str = "replay",
        interval_seconds: float = 0.0,
        depth_levels: int = 20,
    ) -> "ReplayOrderBookFeed":
        snapshots: List[Dict[str, Any]] = []
        with Path(path).open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise FeedSnapshotError(f"invalid JSONL replay line {line_number}: {exc}") from exc
                snapshots.append(payload)
        return cls(
            snapshots,
            symbol=symbol,
            source=source,
            interval_seconds=interval_seconds,
            depth_levels=depth_levels,
        )


class BinanceDepthFeed(OrderBookFeed):
    """Read-only Binance public depth WebSocket adapter."""

    STREAM_LEVELS = {5, 10, 20}

    def __init__(
        self,
        symbol: str,
        *,
        depth_levels: int = 20,
        stream_url: Optional[str] = None,
        reconnect_delay_seconds: float = 1.0,
        stale_after_seconds: float = 5.0,
    ) -> None:
        super().__init__(
            source="binance",
            symbol=symbol,
            depth_levels=depth_levels,
            stale_after_seconds=stale_after_seconds,
        )
        stream_depth = depth_levels if depth_levels in self.STREAM_LEVELS else 20
        self.stream_url = (
            stream_url
            or f"wss://stream.binance.com:9443/ws/{symbol.lower()}@depth{stream_depth}@100ms"
        )
        self.reconnect_delay_seconds = reconnect_delay_seconds

    def parse_message(self, message: str | Dict[str, Any]) -> OrderBookSnapshot:
        payload = json.loads(message) if isinstance(message, str) else message
        data = payload.get("data", payload)
        bids = data.get("bids", data.get("b", []))
        asks = data.get("asks", data.get("a", []))
        timestamp_ms = data.get("E") or data.get("T")
        timestamp = float(timestamp_ms) / 1000.0 if timestamp_ms else time.time()
        return self._normalize(
            {
                "symbol": self.symbol,
                "timestamp": timestamp,
                "bids": bids,
                "asks": asks,
            }
        )

    async def snapshots(self) -> AsyncIterator[OrderBookSnapshot]:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - dependency is declared in requirements
            self.health.mark_error(exc)
            raise OrderBookFeedError("websockets is required for BinanceDepthFeed") from exc

        while True:
            try:
                self.health.mark_reconnect()
                async with websockets.connect(self.stream_url, ping_interval=20) as websocket:
                    self.health.connected = True
                    async for raw_message in websocket:
                        book = self.parse_message(raw_message)
                        self.health.mark_update(queue_depth=0, timestamp=book.timestamp)
                        yield book
            except asyncio.CancelledError:
                self.health.mark_disconnected()
                raise
            except Exception as exc:  # pragma: no cover - exercised by integration/sandbox only
                self.health.mark_error(exc)
                self.health.mark_disconnected()
                await asyncio.sleep(self.reconnect_delay_seconds)


class InteractiveBrokersDepthFeed(OrderBookFeed):
    """Read-only IB/TWS market-depth callback bridge.

    IB's API delivers depth changes through callbacks. This adapter turns those
    callbacks into normalized snapshots and an async stream, but it never sends
    orders or imports IB execution clients.
    """

    def __init__(
        self,
        symbol: str,
        *,
        source: str = "ib",
        depth_levels: int = 20,
        stale_after_seconds: float = 5.0,
        queue_size: int = 100,
    ) -> None:
        super().__init__(
            source=source,
            symbol=symbol,
            depth_levels=depth_levels,
            stale_after_seconds=stale_after_seconds,
        )
        self._bids: Dict[int, Dict[str, Any]] = {}
        self._asks: Dict[int, Dict[str, Any]] = {}
        self._queue: asyncio.Queue[OrderBookSnapshot] = asyncio.Queue(maxsize=queue_size)

    @staticmethod
    def _side_name(side: str | int) -> str:
        if isinstance(side, str):
            normalized = side.lower()
            if normalized in {"bid", "bids"}:
                return "bid"
            if normalized in {"ask", "asks"}:
                return "ask"
        if side == 1:
            return "bid"
        if side == 0:
            return "ask"
        raise FeedSnapshotError(f"unknown IB depth side {side!r}")

    def apply_depth_update(
        self,
        *,
        position: int,
        operation: int,
        side: str | int,
        price: float,
        size: float,
        count: int = 1,
        timestamp: Optional[float] = None,
    ) -> Optional[OrderBookSnapshot]:
        """Apply one IB/TWS depth callback update.

        operation follows IB's convention: 0 insert, 1 update, 2 delete.
        side accepts strings or IB ints, where 1 is bid and 0 is ask.
        """
        book_side = self._side_name(side)
        levels = self._bids if book_side == "bid" else self._asks
        if operation == 2:
            levels.pop(position, None)
        elif operation in {0, 1}:
            levels[position] = {
                "price": float(price),
                "volume": float(size),
                "count": int(count),
            }
        else:
            raise FeedSnapshotError(f"unknown IB depth operation {operation!r}")

        if not self._bids or not self._asks:
            return None

        snapshot = self._normalize(
            {
                "symbol": self.symbol,
                "timestamp": timestamp or time.time(),
                "bids": [self._bids[index] for index in sorted(self._bids)],
                "asks": [self._asks[index] for index in sorted(self._asks)],
            }
        )
        self._enqueue(snapshot)
        return snapshot

    def _enqueue(self, snapshot: OrderBookSnapshot) -> None:
        if self._queue.full():
            self._queue.get_nowait()
            self.health.mark_drop()
        self._queue.put_nowait(snapshot)
        self.health.mark_update(queue_depth=self._queue.qsize(), timestamp=snapshot.timestamp)

    async def snapshots(self) -> AsyncIterator[OrderBookSnapshot]:
        self.health.connected = True
        try:
            while True:
                snapshot = await self._queue.get()
                self.health.mark_update(queue_depth=self._queue.qsize(), timestamp=snapshot.timestamp)
                yield snapshot
        finally:
            self.health.mark_disconnected()


IBDepthFeed = InteractiveBrokersDepthFeed

