"""
Async Tick Processing Loop  (T2-F)

Wraps the existing synchronous Deriv and MT5 brokers in an asyncio event loop,
connecting tick producers to the pipeline via an asyncio.Queue.

Target latency: < 50 ms from tick receipt to pipeline entry.

Usage:
    async def my_pipeline(tick):
        ...  # process one tick

    loop = AsyncTickLoop(pipeline_fn=my_pipeline)
    asyncio.run(loop.run(deriv_broker, mt5_broker, symbol="EURUSD"))

Both brokers remain synchronous; they are called in executor threads so the
event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Optional, Tuple

logger = logging.getLogger(__name__)


class AsyncTickLoop:
    """
    Event-driven tick ingestion using asyncio.

    Architecture:
        deriv_producer  ─┐
                          ├─► asyncio.Queue ─► consumer ─► pipeline_fn
        mt5_producer    ─┘

    The queue decouples production from consumption and provides
    natural backpressure (blocks producer when full).
    """

    def __init__(
        self,
        pipeline_fn: Callable[[Tuple[str, Any]], Any],
        queue_maxsize: int = 1000,
        deriv_poll_interval: float = 0.005,   # 5 ms
        mt5_poll_interval: float = 0.010,     # 10 ms
    ) -> None:
        """
        Args:
            pipeline_fn: Called with (source, tick) for every incoming tick.
                         May be a plain function or a coroutine function.
            queue_maxsize: Maximum queue depth before producers are back-pressured.
            deriv_poll_interval: Seconds between Deriv polls.
            mt5_poll_interval: Seconds between MT5 polls.
        """
        self.pipeline_fn = pipeline_fn
        self.queue_maxsize = queue_maxsize
        self.deriv_poll_interval = deriv_poll_interval
        self.mt5_poll_interval = mt5_poll_interval

        self._queue: Optional[asyncio.Queue] = None
        self._latencies: list = []

    # ------------------------------------------------------------------
    # Producers
    # ------------------------------------------------------------------

    async def deriv_producer(self, deriv_broker: Any) -> None:
        """
        Poll Deriv broker for new ticks in an executor thread and push to queue.
        Runs until cancelled.
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                tick = await loop.run_in_executor(None, deriv_broker.get_latest_tick)
                if tick is not None:
                    await self._queue.put(("deriv", tick, time.monotonic()))
            except Exception as exc:
                logger.debug("Deriv producer error: %s", exc)
            await asyncio.sleep(self.deriv_poll_interval)

    async def mt5_producer(self, mt5_broker: Any, symbol: str) -> None:
        """
        Poll MT5 for current price in an executor thread and push to queue.
        Runs until cancelled.
        """
        loop = asyncio.get_event_loop()
        while True:
            try:
                tick = await loop.run_in_executor(
                    None, mt5_broker.get_current_price, symbol
                )
                if tick is not None:
                    await self._queue.put(("mt5", tick, time.monotonic()))
            except Exception as exc:
                logger.debug("MT5 producer error: %s", exc)
            await asyncio.sleep(self.mt5_poll_interval)

    # ------------------------------------------------------------------
    # Consumer
    # ------------------------------------------------------------------

    async def consumer(self) -> None:
        """
        Drain the queue and call pipeline_fn for each tick.
        Records end-to-end latency (queue put → pipeline call).
        """
        loop = asyncio.get_event_loop()
        is_coro = asyncio.iscoroutinefunction(self.pipeline_fn)

        while True:
            source, tick, enqueue_time = await self._queue.get()
            try:
                if is_coro:
                    await self.pipeline_fn((source, tick))
                else:
                    await loop.run_in_executor(None, self.pipeline_fn, (source, tick))
                latency_ms = (time.monotonic() - enqueue_time) * 1000
                self._latencies.append(latency_ms)
                if len(self._latencies) % 100 == 0:
                    avg = sum(self._latencies[-100:]) / 100
                    logger.info("Tick latency avg (last 100): %.1f ms", avg)
            except Exception as exc:
                logger.warning("Pipeline error on %s tick: %s", source, exc)
            finally:
                self._queue.task_done()

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        deriv_broker: Optional[Any] = None,
        mt5_broker: Optional[Any] = None,
        symbol: str = "EURUSD",
    ) -> None:
        """
        Start all producers and the consumer, run until cancelled.

        At least one broker must be provided; omit the other with None.
        """
        self._queue = asyncio.Queue(maxsize=self.queue_maxsize)

        tasks = [asyncio.create_task(self.consumer(), name="tick_consumer")]
        if deriv_broker is not None:
            tasks.append(asyncio.create_task(
                self.deriv_producer(deriv_broker), name="deriv_producer"
            ))
        if mt5_broker is not None:
            tasks.append(asyncio.create_task(
                self.mt5_producer(mt5_broker, symbol), name="mt5_producer"
            ))

        if len(tasks) == 1:
            raise ValueError("At least one broker (deriv_broker or mt5_broker) must be provided.")

        logger.info("AsyncTickLoop started: %d tasks", len(tasks))
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for t in tasks:
                t.cancel()
            logger.info("AsyncTickLoop stopped")

    def get_latency_stats(self) -> dict:
        """Return latency statistics (ms)."""
        if not self._latencies:
            return {"count": 0}
        last = self._latencies[-100:]
        return {
            "count": len(self._latencies),
            "avg_ms": sum(last) / len(last),
            "max_ms": max(last),
            "min_ms": min(last),
        }
