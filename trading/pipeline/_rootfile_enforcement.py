"""Rootfile token-flow adapters for the live pipeline boundary."""

from __future__ import annotations

from typing import Any


def install_pipeline_token_bridge() -> None:
    """Carry scheduler-issued tokens into direct broker calls."""
    try:
        from . import orchestrator
    except Exception:
        return

    pipeline_cls = orchestrator.PipelineOrchestrator
    if getattr(pipeline_cls, "_ROOTFILE_TOKEN_BRIDGE_INSTALLED", False):
        return

    original_scheduler_stage = pipeline_cls._stage_scheduler_collapse
    original_execution_stage = pipeline_cls._stage_execution

    def scheduler_stage_with_token(self: Any, context: Any) -> dict:
        captured: dict[str, Any] = {}
        original_authorize = self.scheduler.authorize_collapse

        def capture_authorize(*args: Any, **kwargs: Any) -> Any:
            decision, token = original_authorize(*args, **kwargs)
            captured["token"] = token
            return decision, token

        self.scheduler.authorize_collapse = capture_authorize
        try:
            result = original_scheduler_stage(self, context)
        finally:
            self.scheduler.authorize_collapse = original_authorize

        context.execution_token = captured.get("token")
        return result

    def execution_stage_with_token(self: Any, context: Any) -> dict:
        from trading.brokers.deriv_broker import deriv_broker
        from trading.brokers.mt5_broker import mt5_broker

        token = getattr(context, "execution_token", None)
        original_mt5_place = mt5_broker.place_order
        original_deriv_place = deriv_broker.place_contract

        def mt5_place_with_token(order: Any, *args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("token", token)
            return original_mt5_place(order, *args, **kwargs)

        def deriv_place_with_token(order: Any, *args: Any, **kwargs: Any) -> Any:
            kwargs.setdefault("token", token)
            return original_deriv_place(order, *args, **kwargs)

        mt5_broker.place_order = mt5_place_with_token
        deriv_broker.place_contract = deriv_place_with_token
        try:
            return original_execution_stage(self, context)
        finally:
            mt5_broker.place_order = original_mt5_place
            deriv_broker.place_contract = original_deriv_place

    pipeline_cls._stage_scheduler_collapse = scheduler_stage_with_token
    pipeline_cls._stage_execution = execution_stage_with_token
    pipeline_cls._ROOTFILE_TOKEN_BRIDGE_INSTALLED = True
