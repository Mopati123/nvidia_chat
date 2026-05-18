"""
orchestrator.py - 20-Stage Canonical Pipeline Orchestrator.

Implements the complete transformation pipeline:

Raw Data → State Construction → Path Generation → Constraint Filtering
→ Action Evaluation → Interference Selection → Proposal → Admissibility
→ Entropy Gate → Scheduler → Execution → Reconciliation → Evidence → Learning

Each stage is a checkpointed transformation with typed inputs/outputs.
"""

import os
import time
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from .stage_contracts import CANONICAL_STAGE_SEQUENCE, get_stage_operator_spec
from .stage_proof import build_stage_proof, stage_context_snapshot

logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Canonical 20-stage pipeline stages"""
    # Data Ingestion
    DATA_INGESTION = "data_ingestion"
    STATE_CONSTRUCTION = "state_construction"
    
    # ICT Geometry
    ICT_EXTRACTION = "ict_extraction"
    
    # Riemannian Geometry
    GEOMETRY_COMPUTATION = "geometry_computation"
    FIELD_EVALUATION = "field_evaluation"
    
    # Path Generation
    TRAJECTORY_GENERATION = "trajectory_generation"
    RAMANUJAN_COMPRESSION = "ramanujan_compression"
    
    # Filtering & Validation
    ADMISSIBILITY_FILTERING = "admissibility_filtering"
    
    # Action & Selection
    ACTION_EVALUATION = "action_evaluation"
    PATH_INTEGRAL = "path_integral"
    INTERFERENCE_SELECTION = "interference_selection"
    PATH_SELECTION = "path_selection"
    
    # Proposal & Gates
    PROPOSAL_GENERATION = "proposal_generation"
    ADMISSIBILITY_CHECK = "admissibility_check"
    ENTROPY_GATE = "entropy_gate"
    SCHEDULER_COLLAPSE = "scheduler_collapse"
    
    # Execution
    EXECUTION = "execution"
    RECONCILIATION = "reconciliation"
    EVIDENCE_EMISSION = "evidence_emission"
    
    # Learning
    WEIGHT_UPDATE = "weight_update"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class StageResult:
    """Result from a pipeline stage execution"""
    stage: PipelineStage
    success: bool
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: float = 0.0
    checkpoint_hash: str = ""
    operator_id: str = ""
    canonical_law: str = ""
    input_hash: str = ""
    output_hash: str = ""
    previous_hash: str = ""
    proof_hash: str = ""
    preconditions: List[str] = field(default_factory=list)
    postconditions: List[str] = field(default_factory=list)
    refusal_code: Optional[str] = None


@dataclass
class PipelineContext:
    """Context maintained through pipeline execution"""
    symbol: str
    timestamp: float
    source: str  # 'MT5', 'Deriv', 'TradingView'
    
    # Stage outputs (checkpointed)
    raw_data: Dict = field(default_factory=dict)
    market_state: Dict = field(default_factory=dict)
    order_book: Optional[Any] = None
    hft_signals: Dict = field(default_factory=dict)
    ict_geometry: Dict = field(default_factory=dict)
    geometry_data: Dict = field(default_factory=dict)  # Riemannian geometry
    field_data: Dict = field(default_factory=dict)
    field_admissible: bool = True
    field_reason: str = ""
    trajectories: List[Dict] = field(default_factory=list)
    path_families: Dict[str, List[str]] = field(default_factory=dict)
    path_signatures: Dict[str, Dict[str, str]] = field(default_factory=dict)
    admissible_paths: List[Dict] = field(default_factory=list)
    action_scores: Dict = field(default_factory=dict)
    selected_path: Optional[Dict] = None
    proposal: Dict = field(default_factory=dict)
    collapse_decision: Optional[str] = None
    execution_token: Optional[Any] = None
    execution_result: Dict = field(default_factory=dict)
    reconciliation_status: str = ""
    evidence_hash: str = ""
    qpt_token_id: Optional[str] = None
    weight_update_result: Dict = field(default_factory=dict)
    risk_check_passed: bool = False
    risk_check_message: str = ""
    entropy_gate_passed: bool = False
    entropy_gate_message: str = ""
    regime: Optional[Any] = None          # MarketRegime enum from detector
    regime_params: Optional[Any] = None   # RegimeParameters from detector
    action_weights: Dict = field(default_factory=dict)  # scheduler weights at execution time

    # Metadata
    stage_history: List[StageResult] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)
    adapted_params: Optional[Any] = None
    
    @property
    def duration_ms(self) -> float:
        return (time.time() - self.start_time) * 1000


class PipelineOrchestrator:
    """
    Master orchestrator for the 20-stage canonical pipeline.
    
    Implements the complete transformation from raw market data
    to self-adapting action weights.
    
    Each stage:
    1. Validates input from previous stage
    2. Executes transformation
    3. Produces checkpointed output
    4. Continues or fails based on governance rules
    """
    
    def __init__(self,
                 scheduler=None,
                 risk_manager=None,
                 use_microstructure: bool = True,
                 use_weight_learning: bool = True):
        """
        Initialize pipeline orchestrator.

        Args:
            scheduler: Scheduler instance (created if None)
            risk_manager: ProductionRiskManager instance (created if None)
            use_microstructure: Enable tick-level microstructure processing
            use_weight_learning: Enable backward-law weight updates
        """
        self.use_microstructure = use_microstructure
        self.use_weight_learning = use_weight_learning
        self._paper_mode: bool = True  # set False for live broker execution
        self.live_broker_mode: Optional[str] = None
        self.deriv_live_config: Dict[str, Any] = {
            "stake": 1.0,
            "duration": 5,
            "duration_unit": "m",
            "max_contracts": 1,
        }

        # Initialize scheduler
        if scheduler is None:
            from ..kernel import Scheduler
            scheduler = Scheduler()
        self.scheduler = scheduler

        # Initialize risk manager — hard stops are mandatory, not advisory
        if risk_manager is None:
            from ..risk.risk_manager import ProductionRiskManager
            risk_manager = ProductionRiskManager()
        self.risk_manager = risk_manager

        # Circuit breaker — auto-kill after 10 consecutive collapse failures
        from ..resilience.circuit_breaker import get_circuit_breaker, CircuitBreakerConfig
        from collections import deque
        cb_config = CircuitBreakerConfig(
            failure_threshold=10,
            success_threshold=3,
            timeout_seconds=30.0,
            backoff_multiplier=2.0,
            max_timeout_seconds=300.0,
        )
        self.collapse_breaker = get_circuit_breaker("scheduler_collapse", cb_config)
        self.collapse_breaker.config = cb_config
        self.collapse_breaker.register_on_open(
            lambda: self._trigger_risk_kill_switch("circuit_breaker_open")
        )
        self.checkpoint_dir = Path(
            os.getenv("TRADING_CHECKPOINT_DIR", "trading_data/state/checkpoints")
        )

        # Rolling PnL divergence histogram (last 1000 closed executions)
        self.divergence_history: deque = deque(maxlen=1000)

        # Operator registry — used by trajectory generator for per-path ICT scoring
        try:
            from ..operators.operator_registry import OperatorRegistry
            self.operator_registry = OperatorRegistry()
        except Exception:
            self.operator_registry = None

        # Stage handlers
        self.stage_handlers: Dict[PipelineStage, Callable] = {
            PipelineStage.DATA_INGESTION: self._stage_data_ingestion,
            PipelineStage.STATE_CONSTRUCTION: self._stage_state_construction,
            PipelineStage.ICT_EXTRACTION: self._stage_ict_extraction,
            PipelineStage.GEOMETRY_COMPUTATION: self._stage_geometry_computation,
            PipelineStage.FIELD_EVALUATION: self._stage_field_evaluation,
            PipelineStage.TRAJECTORY_GENERATION: self._stage_trajectory_generation,
            PipelineStage.RAMANUJAN_COMPRESSION: self._stage_ramanujan_compression,
            PipelineStage.ADMISSIBILITY_FILTERING: self._stage_admissibility_filtering,
            PipelineStage.ACTION_EVALUATION: self._stage_action_evaluation,
            PipelineStage.PATH_INTEGRAL: self._stage_path_integral,
            PipelineStage.INTERFERENCE_SELECTION: self._stage_interference_selection,
            PipelineStage.PATH_SELECTION: self._stage_path_selection,
            PipelineStage.PROPOSAL_GENERATION: self._stage_proposal_generation,
            PipelineStage.ADMISSIBILITY_CHECK: self._stage_admissibility_check,
            PipelineStage.ENTROPY_GATE: self._stage_entropy_gate,
            PipelineStage.SCHEDULER_COLLAPSE: self._stage_scheduler_collapse,
            PipelineStage.EXECUTION: self._stage_execution,
            PipelineStage.RECONCILIATION: self._stage_reconciliation,
            PipelineStage.EVIDENCE_EMISSION: self._stage_evidence_emission,
            PipelineStage.WEIGHT_UPDATE: self._stage_weight_update,
        }
        
        # Statistics
        self.execution_count = 0
        self.success_count = 0
        self.failure_count = 0
        
    def execute(self, raw_data: Dict, symbol: str, source: str = 'MT5', adapted_params: Optional[Any] = None) -> PipelineContext:
        """
        Execute complete 20-stage pipeline.
        
        Args:
            raw_data: Raw market data (ticks, OHLCV)
            symbol: Trading symbol
            source: Data source ('MT5', 'Deriv', 'TradingView')
        
        Returns:
            PipelineContext with full execution history
        """
        # Initialize context
        context = PipelineContext(
            symbol=symbol,
            timestamp=time.time(),
            source=source,
            raw_data=raw_data,
            adapted_params=adapted_params
        )
        
        logger.info(f"Starting pipeline execution for {symbol}")
        
        # Execute stages in the rootfile-governed canonical sequence.
        stages = [PipelineStage(stage) for stage in CANONICAL_STAGE_SEQUENCE]
        
        for stage in stages:
            result = self._execute_stage(stage, context)
            context.stage_history.append(result)
            
            if not result.success:
                logger.warning(f"Pipeline failed at stage {stage.value}: {result.error}")
                context.stage_history.append(
                    self._terminal_stage_result(
                        context,
                        PipelineStage.FAILED,
                        success=False,
                        output={'failed_stage': stage.value},
                        error=result.error,
                    )
                )
                self.execution_count += 1
                self.failure_count += 1
                self._release_execution_token(context)
                return context
            
            # Check for early termination
            if stage == PipelineStage.SCHEDULER_COLLAPSE:
                if context.collapse_decision == 'REFUSED':
                    logger.info("Scheduler refused collapse - terminating pipeline")
                    context.stage_history.append(
                        self._terminal_stage_result(
                            context,
                            PipelineStage.COMPLETED,
                            success=True,
                            output={'reason': 'scheduler_refused'},
                        )
                    )
                    self.execution_count += 1
                    self.success_count += 1
                    self._release_execution_token(context)
                    return context
        
        # Completed successfully
        context.stage_history.append(
            self._terminal_stage_result(
                context,
                PipelineStage.COMPLETED,
                success=True,
                output={'duration_ms': context.duration_ms},
            )
        )
        
        self.execution_count += 1
        self.success_count += 1
        
        logger.info(f"Pipeline completed in {context.duration_ms:.2f}ms")
        self._release_execution_token(context)
        return context

    def _release_execution_token(self, context: PipelineContext) -> None:
        """Release scheduler-owned authority backing the context token, if present."""
        token = getattr(context, 'execution_token', None)
        if token is None:
            return
        release = getattr(self.scheduler, 'release_execution_token', None)
        if callable(release):
            release(token)

    def _audit_gate(self, gate: str, status: str, **fields: Any) -> None:
        """Emit compact, machine-readable audit markers for live canaries."""
        parts = []
        for key in sorted(fields):
            value = fields[key]
            if value is None:
                continue
            text = str(value).replace("\r", " ").replace("\n", " ").strip()
            parts.append(f"{key}={text.replace(' ', '_')}")
        suffix = " " + " ".join(parts) if parts else ""
        logger.info("CANARY_AUDIT gate=%s status=%s%s", gate, status, suffix)

    def _trigger_risk_kill_switch(self, reason: str) -> None:
        trigger = getattr(self.risk_manager, "trigger_kill_switch", None)
        if callable(trigger):
            trigger(reason)

    def _scheduler_checkpoint_payload(
        self,
        context: PipelineContext,
        *,
        kind: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        risk_snapshot = None
        snapshot = getattr(self.risk_manager, "snapshot_state", None)
        if callable(snapshot):
            try:
                risk_snapshot = snapshot()
            except Exception as exc:
                risk_snapshot = {"snapshot_error": str(exc)}

        payload = {
            "kind": kind,
            "symbol": context.symbol,
            "timestamp": context.timestamp,
            "proposal": context.proposal,
            "risk_check_passed": context.risk_check_passed,
            "risk_check_message": context.risk_check_message,
            "entropy_gate_passed": context.entropy_gate_passed,
            "entropy_gate_message": context.entropy_gate_message,
            "delta_s": context.action_scores.get("delta_s", 0.3),
            "projected_paths": [
                {
                    "id": path.get("id"),
                    "energy": float(path.get("energy", 0.0)),
                    "action": path.get("action", 1.0),
                }
                for path in context.admissible_paths
            ],
            "collapse_decision": context.collapse_decision,
            "token_id": getattr(context.execution_token, "token_id", None),
            "risk_state": risk_snapshot,
        }
        if extra:
            payload.update(extra)
        return payload

    def _persist_scheduler_checkpoint(
        self,
        kind: str,
        context: PipelineContext,
        *,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Optional[Path]:
        try:
            from trading.resilience.checkpoints import Checkpoint, persist_checkpoint

            checkpoint = Checkpoint.create(
                component="pipeline",
                stage=PipelineStage.SCHEDULER_COLLAPSE.value,
                kind=kind,
                payload=self._scheduler_checkpoint_payload(context, kind=kind, extra=extra),
                evidence_hash=getattr(context, "evidence_hash", "") or "",
            )
            if not checkpoint.validate():
                self._trigger_risk_kill_switch("scheduler_checkpoint_invalid")
                return None
            return persist_checkpoint(self.checkpoint_dir, checkpoint)
        except Exception as exc:
            logger.error("Stage 15: failed to persist %s checkpoint: %s", kind, exc)
            self._trigger_risk_kill_switch("scheduler_checkpoint_failure")
            return None

    @staticmethod
    def _previous_stage_proof_hash(context: PipelineContext) -> str:
        if not context.stage_history:
            return ""
        previous = context.stage_history[-1]
        return previous.proof_hash or previous.checkpoint_hash or ""

    def _stage_result_with_proof(
        self,
        *,
        stage: PipelineStage,
        success: bool,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: float = 0.0,
        input_snapshot: Optional[Dict[str, Any]] = None,
        output_snapshot: Optional[Dict[str, Any]] = None,
        previous_hash: str = "",
    ) -> StageResult:
        stage_output = output or {}
        if input_snapshot is None:
            input_snapshot = {}
        if output_snapshot is None:
            output_snapshot = {"output": stage_output}
        spec = get_stage_operator_spec(stage)
        proof = build_stage_proof(
            stage=stage.value,
            spec=spec,
            input_snapshot=input_snapshot,
            output_snapshot=output_snapshot,
            success=success,
            output=stage_output,
            error=error,
            previous_hash=previous_hash,
        )
        return StageResult(
            stage=stage,
            success=success,
            output=stage_output,
            error=error,
            duration_ms=duration_ms,
            checkpoint_hash=proof["proof_hash"][:16],
            operator_id=proof["operator_id"],
            canonical_law=proof["canonical_law"],
            input_hash=proof["input_hash"],
            output_hash=proof["output_hash"],
            previous_hash=proof["previous_hash"],
            proof_hash=proof["proof_hash"],
            preconditions=proof["preconditions"],
            postconditions=proof["postconditions"],
            refusal_code=proof["refusal_code"],
        )

    def _terminal_stage_result(
        self,
        context: PipelineContext,
        stage: PipelineStage,
        *,
        success: bool,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> StageResult:
        snapshot = stage_context_snapshot(context)
        stage_output = output or {}
        return self._stage_result_with_proof(
            stage=stage,
            success=success,
            output=stage_output,
            error=error,
            input_snapshot=snapshot,
            output_snapshot={"output": stage_output, "context": snapshot},
            previous_hash=self._previous_stage_proof_hash(context),
        )
    
    def _execute_stage(self, stage: PipelineStage, context: PipelineContext) -> StageResult:
        """Execute a single pipeline stage"""
        start = time.time()
        input_snapshot = stage_context_snapshot(context)
        previous_hash = self._previous_stage_proof_hash(context)
        
        handler = self.stage_handlers.get(stage)
        if handler is None:
            return self._stage_result_with_proof(
                stage=stage,
                success=False,
                error=f"No handler for stage {stage}",
                input_snapshot=input_snapshot,
                output_snapshot={"output": {}, "context": input_snapshot},
                previous_hash=previous_hash,
            )
        
        try:
            output = handler(context) or {}
            duration = (time.time() - start) * 1000

            # Record stage timing for Prometheus metrics
            try:
                from trading.observability.metrics import MetricsCollector
                MetricsCollector.get().record_stage(stage.value, duration)
            except Exception:
                pass

            output_snapshot = {
                "output": output,
                "context": stage_context_snapshot(context),
            }
            return self._stage_result_with_proof(
                stage=stage,
                success=True,
                output=output,
                duration_ms=duration,
                input_snapshot=input_snapshot,
                output_snapshot=output_snapshot,
                previous_hash=previous_hash,
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"Stage {stage.value} failed: {e}")
            output_snapshot = {
                "output": {},
                "context": stage_context_snapshot(context),
                "error": str(e),
            }
            return self._stage_result_with_proof(
                stage=stage,
                success=False,
                error=str(e),
                duration_ms=duration,
                input_snapshot=input_snapshot,
                output_snapshot=output_snapshot,
                previous_hash=previous_hash,
            )
    
    # === STAGE HANDLERS ===
    
    def _stage_data_ingestion(self, context: PipelineContext) -> Dict:
        """Stage 1: Normalize raw data into canonical format"""
        # Already done in context initialization
        return {'normalized': True, 'source': context.source}

    @staticmethod
    def _coerce_float(value: Any, default: Optional[float] = None) -> Optional[float]:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        return number if np.isfinite(number) else default

    @classmethod
    def _canonical_ohlcv_bars(cls, raw_data: Dict) -> List[Dict[str, float]]:
        """Normalize dict/list OHLCV inputs into canonical bar dictionaries."""
        source = raw_data.get('ohlcv')
        if isinstance(source, dict):
            raw_data = {**raw_data, **source}
            source = None

        bars: List[Dict[str, float]] = []
        if isinstance(source, list):
            for index, item in enumerate(source):
                if not isinstance(item, dict):
                    continue
                normalized = {str(key).lower(): value for key, value in item.items()}
                close = cls._coerce_float(normalized.get('close', normalized.get('price')))
                high = cls._coerce_float(normalized.get('high'), close)
                low = cls._coerce_float(normalized.get('low'), close)
                open_price = cls._coerce_float(normalized.get('open'), close)
                if close is None or high is None or low is None or open_price is None:
                    continue
                timestamp = cls._coerce_float(
                    normalized.get('timestamp', normalized.get('time')),
                    float(index),
                )
                volume = cls._coerce_float(normalized.get('volume'), 0.0) or 0.0
                bars.append({
                    'timestamp': timestamp if timestamp is not None else float(index),
                    'time': timestamp if timestamp is not None else float(index),
                    'open': open_price,
                    'high': high,
                    'low': low,
                    'close': close,
                    'volume': volume,
                })
            if bars:
                return bars

        required = ('open', 'high', 'low', 'close')
        arrays = {name: raw_data.get(name) for name in required}
        if not all(isinstance(arrays[name], (list, tuple)) for name in required):
            return []

        length = min(len(arrays[name]) for name in required)
        volumes = raw_data.get('volume', [])
        timestamps = raw_data.get('timestamp', raw_data.get('time', []))
        for index in range(length):
            open_price = cls._coerce_float(arrays['open'][index])
            high = cls._coerce_float(arrays['high'][index])
            low = cls._coerce_float(arrays['low'][index])
            close = cls._coerce_float(arrays['close'][index])
            if None in (open_price, high, low, close):
                continue
            volume = (
                cls._coerce_float(volumes[index], 0.0)
                if isinstance(volumes, (list, tuple)) and index < len(volumes)
                else 0.0
            )
            timestamp = (
                cls._coerce_float(timestamps[index], float(index))
                if isinstance(timestamps, (list, tuple)) and index < len(timestamps)
                else float(index)
            )
            bars.append({
                'timestamp': timestamp if timestamp is not None else float(index),
                'time': timestamp if timestamp is not None else float(index),
                'open': open_price,
                'high': high,
                'low': low,
                'close': close,
                'volume': volume or 0.0,
            })
        return bars

    @staticmethod
    def _derive_ohlcv_microstructure(bars: List[Dict[str, float]], raw_data: Dict) -> Dict[str, float]:
        """Build minimal live microstructure when only OHLCV bars are available."""
        if not bars:
            return {}

        latest = bars[-1]
        close = float(latest['close'])
        spread = max(0.0, float(latest['high']) - float(latest['low']))

        def _bar_velocity(current: Dict[str, float], previous: Dict[str, float]) -> float:
            dt = abs(float(current.get('timestamp', 0.0)) - float(previous.get('timestamp', 0.0)))
            if dt <= 0.0:
                dt = 1.0
            return (float(current['close']) - float(previous['close'])) / dt

        velocity = _bar_velocity(bars[-1], bars[-2]) if len(bars) >= 2 else 0.0
        previous_velocity = _bar_velocity(bars[-2], bars[-3]) if len(bars) >= 3 else 0.0
        acceleration = velocity - previous_velocity
        half_spread = spread / 2.0
        session = str(raw_data.get('current_session') or raw_data.get('session') or 'ny')

        return {
            'mid': close,
            'microprice': close,
            'bid': close - half_spread,
            'ask': close + half_spread,
            'spread': spread,
            'spread_proxy': spread,
            'velocity': velocity,
            'acceleration': acceleration,
            'ofi': 0.0,
            'session': session,
            'current_session': session,
            'kill_zone': bool(raw_data.get('kill_zone', False)),
        }

    @staticmethod
    def _derive_ohlcv_fvgs(bars: List[Dict[str, float]]) -> List[Dict[str, float]]:
        fvgs: List[Dict[str, float]] = []
        if len(bars) < 3:
            return fvgs

        ranges = [max(0.0, float(bar['high']) - float(bar['low'])) for bar in bars[-20:]]
        avg_range = float(np.mean(ranges)) if ranges else 0.0
        clear_gap = max(avg_range * 0.05, abs(float(bars[-1]['close'])) * 1e-6, 1e-9)

        for index in range(2, len(bars)):
            first = bars[index - 2]
            current = bars[index]
            if float(current['low']) > float(first['high']):
                bottom = float(first['high'])
                top = float(current['low'])
                direction = 'bullish'
            elif float(current['high']) < float(first['low']):
                bottom = float(current['high'])
                top = float(first['low'])
                direction = 'bearish'
            else:
                continue

            if top - bottom < clear_gap:
                continue
            fvgs.append({
                'top': top,
                'bottom': bottom,
                'midpoint': (top + bottom) / 2.0,
                'strength': min(3.0, max(1.0, (top - bottom) / clear_gap)),
                'direction': direction,
                'source': 'ohlcv_gap',
            })
        return fvgs

    @classmethod
    def _derive_ohlcv_ict_context(cls, raw_data: Dict, bars: List[Dict[str, float]]) -> Dict[str, Any]:
        """Derive conservative liquidity context from live OHLCV fallback bars."""
        session = str(raw_data.get('current_session') or raw_data.get('session') or 'ny')
        explicit_zones = raw_data.get('liquidity_zones') or raw_data.get('liquidity_pools') or []
        explicit_fvgs = raw_data.get('fvgs') or raw_data.get('fvg_zones') or []

        liquidity_zones = list(explicit_zones) if isinstance(explicit_zones, list) else []
        if not liquidity_zones and bars:
            recent = bars[-min(len(bars), 20):]
            high_level = max(float(bar['high']) for bar in recent)
            low_level = min(float(bar['low']) for bar in recent)
            volume = sum(float(bar.get('volume', 0.0) or 0.0) for bar in recent)
            width = max(high_level - low_level, abs(float(recent[-1]['close'])) * 1e-5, 1e-9)
            liquidity_zones = [
                {
                    'level': high_level,
                    'type': 'buy_side_liquidity',
                    'strength': 1.0,
                    'volume': volume,
                    'radius': width * 0.25,
                    'source': 'ohlcv_recent_high',
                },
                {
                    'level': low_level,
                    'type': 'sell_side_liquidity',
                    'strength': 1.0,
                    'volume': volume,
                    'radius': width * 0.25,
                    'source': 'ohlcv_recent_low',
                },
            ]

        fvgs = list(explicit_fvgs) if isinstance(explicit_fvgs, list) else []
        if not fvgs:
            fvgs = cls._derive_ohlcv_fvgs(bars)

        return {
            'liquidity_zones': liquidity_zones,
            'liquidity_pools': liquidity_zones,
            'fvgs': fvgs,
            'fvg_zones': fvgs,
            'fair_value_gaps': fvgs,
            'sweeps': raw_data.get('sweeps', []),
            'session': session,
            'current_session': session,
            'kill_zone': bool(raw_data.get('kill_zone', False)),
            'htf_bias': raw_data.get('htf_bias', 'neutral'),
        }
    
    def _stage_state_construction(self, context: PipelineContext) -> Dict:
        """Stage 2: Build MarketState from raw data"""
        ohlcv_bars = self._canonical_ohlcv_bars(context.raw_data)

        # If microstructure enabled, process ticks
        if self.use_microstructure and 'ticks' in context.raw_data:
            from ..microstructure import TickProcessor
            processor = TickProcessor()
            
            micro = None
            for tick in context.raw_data['ticks']:
                micro = processor.process_tick(tick)
            
            if micro:
                context.market_state['microstructure'] = micro

        if ohlcv_bars and not context.market_state.get('microstructure'):
            context.market_state['microstructure'] = self._derive_ohlcv_microstructure(
                ohlcv_bars,
                context.raw_data,
            )

        order_book_result = self._stage_order_book_analysis(context)
        
        context.market_state['ohlcv'] = ohlcv_bars
        context.market_state['symbol'] = context.symbol
        context.market_state['session'] = (
            context.raw_data.get('current_session')
            or context.raw_data.get('session')
            or context.market_state.get('microstructure', {}).get('session')
            or 'ny'
        )
        
        return {
            'state_built': True,
            'ohlcv_bars': len(ohlcv_bars),
            'microstructure_source': 'ohlcv' if ohlcv_bars and 'ticks' not in context.raw_data else 'ticks',
            **order_book_result,
        }

    def _stage_order_book_analysis(self, context: PipelineContext) -> Dict:
        """Stage 2.5: Optional analytics-only order-book depth analysis."""
        raw_book = context.raw_data.get('order_book')
        if not raw_book:
            return {'order_book_analyzed': False}

        from ..microstructure import OrderBookEngine

        engine = OrderBookEngine(context.symbol)
        signals = engine.process_snapshot(raw_book)
        context.order_book = engine.current_book
        context.hft_signals = signals.to_dict()
        context.market_state['order_book'] = (
            context.order_book.to_dict() if context.order_book is not None else {}
        )
        context.market_state['hft_signals'] = dict(context.hft_signals)

        return {
            'order_book_analyzed': True,
            'hft_signals': dict(context.hft_signals),
        }
    
    def _stage_ict_extraction(self, context: PipelineContext) -> Dict:
        """Stage 3: Extract ICT geometry + detect market regime.

        Regime detection runs here so RegimeParameters are available for:
        - Stage 5 (TRAJECTORY_GENERATION): epsilon and trajectory_count
        - Stage 12 (ADMISSIBILITY_CHECK): position size gate
        - Risk manager: live limit update
        """
        bars = context.market_state.get('ohlcv') or self._canonical_ohlcv_bars(context.raw_data)
        context.ict_geometry = self._derive_ohlcv_ict_context(context.raw_data, bars)

        # Regime detection — requires at least a minimal price DataFrame
        try:
            import pandas as pd
            from ..core.market_regime_detector import MarketRegimeDetector

            ohlcv = bars
            if len(ohlcv) >= 20:
                df = pd.DataFrame(ohlcv)
                # Normalize column names to what detector expects
                col_map = {c: c.lower() for c in df.columns}
                df.rename(columns=col_map, inplace=True)
                for col in ('high', 'low', 'close'):
                    if col not in df.columns and 'price' in df.columns:
                        df[col] = df['price']

                detector = MarketRegimeDetector()
                regime, regime_params = detector.detect_regime_with_params(df)

                context.regime = regime
                context.regime_params = regime_params
                # Keep backwards compat with adapted_params
                context.adapted_params = regime_params

                # Wire regime limits into the live risk manager immediately
                self.risk_manager.set_regime_limits(regime_params)

                context.ict_geometry['regime'] = regime.value
                logger.info(f"Regime detected: {regime.value}, epsilon_scale={regime_params.epsilon_scale}")
            else:
                logger.debug("Insufficient OHLCV data for regime detection; using defaults")
        except Exception as e:
            logger.warning(f"Regime detection skipped: {e}")

        return {'ict_extracted': True, 'regime': getattr(context.regime, 'value', 'unknown')}
    
    def _stage_geometry_computation(self, context: PipelineContext) -> Dict:
        """
        Stage 4: Riemannian geometry computation.
        
        Computes:
        - Liquidity field ϕ(p,t)
        - Metric tensor g_ij
        - Christoffel symbols Γ^i_jk
        - Gaussian curvature K
        """
        from ..geometry import (
            LiquidityField, ConformalMetric,
            ChristoffelSymbols, compute_christoffel,
            CurvatureAnalyzer
        )
        
        # Get current price/time
        micro = context.market_state.get('microstructure', {})
        price = micro.get('mid', 1.0)
        timestamp = context.timestamp
        
        # Initialize geometry components
        liquidity_field = LiquidityField()
        curvature_analyzer = CurvatureAnalyzer(liquidity_field)
        
        # Compute geometry at current point
        try:
            # Liquidity field
            phi = liquidity_field.compute(price, timestamp, context.ict_geometry, micro)
            
            # Metric
            metric = ConformalMetric(phi)
            g = metric.get_metric_tensor()
            
            # Christoffel symbols
            d_phi_dp, d_phi_dt = liquidity_field.compute_gradient(
                price, timestamp, context.ict_geometry, micro
            )
            christoffel = compute_christoffel(d_phi_dp, d_phi_dt)
            
            # Curvature
            curvature_data = curvature_analyzer.analyze_point(
                price, timestamp, context.ict_geometry, micro
            )
            
            # Store geometry data
            context.geometry_data = {
                'phi': phi,
                'metric': {
                    'g_pp': g.g_pp,
                    'g_tt': g.g_tt,
                    'determinant': g.determinant,
                },
                'christoffel': christoffel.as_dict(),
                'curvature': curvature_data.to_dict(),
                'regime': curvature_data.regime.value,
            }
            
            return {
                'geometry_computed': True,
                'phi': phi,
                'curvature_K': curvature_data.gaussian_curvature,
                'regime': curvature_data.regime.value,
            }
            
        except Exception as e:
            logger.warning(f"Geometry computation failed: {e}")
            # Continue without geometry (graceful degradation)
            context.geometry_data = {}
            return {'geometry_computed': False, 'error': str(e)}

    def _stage_field_evaluation(self, context: PipelineContext) -> Dict:
        """Stage 4b: Field Hamiltonian diagnostics after geometry computation."""
        from ..kernel.H_field import FieldHamiltonian

        result = FieldHamiltonian().evaluate(
            context.market_state,
            context.geometry_data,
            context.proposal,
        )
        context.field_data = result.to_dict()
        context.field_admissible = bool(result.field_admissible)
        context.field_reason = ",".join(result.reasons) if result.reasons else "field_admissible"
        enabled = os.getenv("ENABLE_FIELD_HAMILTONIAN", "0") == "1"
        status = "passed" if context.field_admissible or not enabled else "failed"
        self._audit_gate(
            "stage4b_field",
            status,
            enabled=enabled,
            field_admissible=context.field_admissible,
            field_reason=context.field_reason,
            polarity=result.polarity.get("polarity"),
            coupling_strength=f"{result.coupling.get('coupling_strength', 0.0):.6g}",
            symbol=context.symbol,
        )
        return {
            "field_evaluated": True,
            "field_enabled": enabled,
            "field_admissible": context.field_admissible,
            "field_reason": context.field_reason,
        }
    
    def _stage_trajectory_generation(self, context: PipelineContext) -> Dict:
        """Stage 5: Generate candidate trajectory families with regime-aware parameters.

        T2-A: Builds a Γ(p,t) → ChristoffelSymbols callable from the liquidity
              field so initial velocity seeds are bent by local geodesic curvature.
        T2-B: The same callable drives time-varying RK4 acceleration at each
              sub-step (replaces the constant "force" placeholder).

        Falls back to uniform perturbations + constant force if the liquidity
        field or ICT geometry is unavailable.
        """
        from ..path_integral import LeastActionGenerator
        from ..geometry.connection import ChristoffelProvider
        from ..geometry.liquidity_field import LiquidityField

        BASE_EPSILON = 0.015
        n_trajectories = 5
        epsilon = BASE_EPSILON
        risk_aversion = 1.0

        rp = context.regime_params or context.adapted_params
        if rp is not None:
            if hasattr(rp, 'trajectory_count'):
                n_trajectories = int(rp.trajectory_count)
            if hasattr(rp, 'epsilon_scale'):
                epsilon = BASE_EPSILON * float(rp.epsilon_scale)
            if hasattr(rp, 'risk_aversion'):
                risk_aversion = float(rp.risk_aversion)

        logger.debug(
            f"Trajectory generation: n={n_trajectories}, "
            f"epsilon={epsilon:.5f}, risk_aversion={risk_aversion:.2f}"
        )

        micro = context.market_state.get('microstructure', {})
        initial_state = {
            'price': micro.get('mid', 1.0),
            'velocity': micro.get('velocity', 0.0),
        }

        # T2-A: build Christoffel closure bound to current ICT geometry
        christoffel_func = None
        try:
            lf = LiquidityField()
            provider = ChristoffelProvider(lf)
            christoffel_func = provider.get_christoffel_func(
                context.ict_geometry or {},
                micro,
            )
        except Exception as e:
            logger.warning(f"ChristoffelProvider unavailable, using flat trajectories: {e}")

        generator = LeastActionGenerator(
            n_trajectories=n_trajectories,
            epsilon=epsilon,
        )

        try:
            trajectories = generator.generate_trajectories(
                initial_state,
                {},                    # Hamiltonian values computed per-path internally
                self.operator_registry if hasattr(self, 'operator_registry') else None,
                christoffel_func=christoffel_func,
                regime=getattr(context.regime, 'value', None),  # T2-D: regime → sailing alpha
            )
            context.trajectories = [t.to_dict() for t in trajectories]
        except Exception as e:
            logger.warning(f"Trajectory generation failed ({e}), using linear fallback")
            price = initial_state['price']
            context.trajectories = [
                {
                    'id': f'traj_{i}',
                    'path': [(j, price + i * 0.0001 * j) for j in range(20)],
                    'energy': 0.5 + i * 0.1 * risk_aversion,
                }
                for i in range(n_trajectories)
            ]

        # Store ℏ and trajectory count on context for evidence block in Stage 11
        context._epsilon = epsilon
        context._num_trajectories = len(context.trajectories)

        return {
            'trajectories_generated': len(context.trajectories),
            'epsilon': epsilon,
            'n_trajectories': n_trajectories,
            'geodesic_guided': christoffel_func is not None,
            'regime': getattr(context.regime, 'value', 'unknown'),
        }
    
    def _stage_ramanujan_compression(self, context: PipelineContext) -> Dict:
        """Stage 5: Compress paths into deterministic behavior families."""
        families: Dict[str, List[str]] = {}
        signatures: Dict[str, Dict[str, str]] = {}

        for index, trajectory in enumerate(context.trajectories):
            trajectory_id = str(trajectory.get('id') or f'traj_{index}')
            trajectory['id'] = trajectory_id

            signature = self._path_signature(trajectory, context)
            family_key = "|".join(
                f"{name}={signature[name]}"
                for name in ("liquidity", "time", "entry", "risk", "topology")
            )
            trajectory['signature'] = signature
            trajectory['family'] = family_key
            signatures[trajectory_id] = signature
            families.setdefault(family_key, []).append(trajectory_id)

        context.path_families = families
        context.path_signatures = signatures

        return {
            'families': sorted(families),
            'family_count': len(families),
            'signatures': signatures,
        }

    @staticmethod
    def _trajectory_points(path: Any) -> List[Tuple[float, float]]:
        """Normalize trajectory path points into (time, price) pairs."""
        points: List[Tuple[float, float]] = []
        if not isinstance(path, list):
            return points

        for index, point in enumerate(path):
            try:
                if isinstance(point, dict):
                    timestamp = float(point.get('timestamp', point.get('t', index)))
                    price = float(point.get('price', point.get('p')))
                else:
                    timestamp = float(point[0])
                    price = float(point[1])
            except (TypeError, ValueError, IndexError, KeyError):
                continue
            points.append((timestamp, price))
        return points

    @staticmethod
    def _count_items(value: Any) -> int:
        if isinstance(value, (list, tuple, set)):
            return len(value)
        if isinstance(value, dict):
            return len(value)
        return 1 if value else 0

    def _path_signature(self, trajectory: Dict, context: PipelineContext) -> Dict[str, str]:
        """Build the v1 Ramanujan path-family signature."""
        points = self._trajectory_points(trajectory.get('path', []))
        prices = [price for _, price in points]
        start = prices[0] if prices else 0.0
        end = prices[-1] if prices else start
        delta = end - start
        tolerance = max(abs(start) * 1e-5, 1e-9)

        if abs(delta) <= tolerance:
            direction = "flat"
        elif delta > 0:
            direction = "bullish"
        else:
            direction = "bearish"

        price_deltas = [
            prices[i + 1] - prices[i]
            for i in range(len(prices) - 1)
            if abs(prices[i + 1] - prices[i]) > tolerance
        ]
        signs = [1 if item > 0 else -1 for item in price_deltas]
        turns = sum(1 for i in range(len(signs) - 1) if signs[i] != signs[i + 1])
        if not price_deltas or direction == "flat":
            topology = "flat"
        elif turns == 0:
            topology = f"monotonic_{direction}"
        else:
            topology = "oscillating"

        max_excursion = max((abs(price - start) for price in prices), default=0.0)
        if max_excursion <= tolerance * 2:
            risk = "low"
        elif max_excursion <= tolerance * 8:
            risk = "medium"
        else:
            risk = "high"

        ict = context.ict_geometry or {}
        fvg_count = self._count_items(
            ict.get('fvg_zones')
            or ict.get('fair_value_gaps')
            or ict.get('fvg')
        )
        pool_count = self._count_items(
            ict.get('liquidity_pools')
            or ict.get('liquidity_zones')
            or ict.get('pools')
        )
        sweep_count = self._count_items(ict.get('sweeps') or ict.get('sweep'))
        liquidity = (
            f"fvg{min(fvg_count, 3)}"
            f"_pool{min(pool_count, 3)}"
            f"_sweep{min(sweep_count, 3)}"
        )

        session = (
            ict.get('session')
            or context.market_state.get('session')
            or context.raw_data.get('session')
            or "unknown"
        )

        return {
            "liquidity": liquidity,
            "time": str(session).lower().replace(" ", "_"),
            "entry": f"{direction}_entry",
            "risk": risk,
            "topology": topology,
        }
    
    def _stage_admissibility_filtering(self, context: PipelineContext) -> Dict:
        """Stage 6: Π_total - Filter illegal paths"""
        # All paths admissible for now
        context.admissible_paths = context.trajectories
        
        return {'admissible_count': len(context.admissible_paths)}

    @staticmethod
    def _nearest_fvg_midpoint(price: float, fvgs: List[Dict], fallback: float) -> float:
        midpoint = fallback
        nearest_distance = float('inf')
        for fvg in fvgs:
            try:
                candidate = float(fvg.get('midpoint', (float(fvg['top']) + float(fvg['bottom'])) / 2.0))
            except (TypeError, ValueError, KeyError):
                continue
            distance = abs(price - candidate)
            if distance < nearest_distance:
                midpoint = candidate
                nearest_distance = distance
        return midpoint

    def _trajectory_action_steps(self, trajectory: Dict, context: PipelineContext) -> List[Dict[str, float]]:
        """Add deterministic path-local action features for OHLCV-only live input."""
        points = self._trajectory_points(trajectory.get('path', []))
        if not points:
            return []

        micro = context.market_state.get('microstructure', {}) or {}
        ict = context.ict_geometry or {}
        fvgs = ict.get('fvgs') or ict.get('fvg_zones') or []
        prices = [price for _, price in points]
        start = prices[0]
        end = prices[-1]
        path_high = max(prices)
        path_low = min(prices)
        path_range = max(path_high - path_low, abs(start) * 1e-9, 1e-12)
        direction = 1.0 if end >= start else -1.0
        fib_level = (
            path_low + 0.618 * path_range
            if direction >= 0.0
            else path_high - 0.618 * path_range
        )
        fallback_midpoint = (path_high + path_low) / 2.0
        spread = float(micro.get('spread_proxy', micro.get('spread', 0.0)) or 0.0)
        base_ofi = float(micro.get('ofi', 0.0) or 0.0)
        micro_acceleration = float(micro.get('acceleration', 0.0) or 0.0)

        velocities: List[float] = []
        for index, (timestamp, price) in enumerate(points):
            if index == 0:
                velocities.append(float(micro.get('velocity', 0.0) or 0.0))
                continue
            previous_time, previous_price = points[index - 1]
            dt = abs(timestamp - previous_time) or 1.0
            velocities.append((price - previous_price) / dt)

        steps: List[Dict[str, float]] = []
        for index, (timestamp, price) in enumerate(points):
            previous_velocity = velocities[index - 1] if index > 0 else velocities[index]
            acceleration = (velocities[index] - previous_velocity) + micro_acceleration
            adverse = max(0.0, (start - price) * direction)
            if direction < 0.0:
                adverse = max(0.0, price - start)
            steps.append({
                'price': price,
                'ofi': base_ofi,
                'timestamp': timestamp,
                'spread': spread,
                'acceleration': acceleration,
                'drawdown': adverse,
                'fvg_midpoint': self._nearest_fvg_midpoint(price, fvgs, fallback_midpoint),
                'fib_level': fib_level,
            })

        return steps
    
    def _stage_action_evaluation(self, context: PipelineContext) -> Dict:
        """Stage 7: Compute S[γ] for each path"""
        if self.use_microstructure:
            from ..action.upgraded_components import UpgradedActionComponents
            
            action_comp = UpgradedActionComponents()
            weights = self.scheduler.get_action_weights()
            context.action_weights = dict(weights)  # snapshot for PPO state vector

            microstate = {
                'ict_geometry': context.ict_geometry,
                'market_state': context.market_state,
                'hft_signals': context.hft_signals,
            }

            for traj in context.admissible_paths:
                path = self._trajectory_action_steps(traj, context)

                result = action_comp.compute_full_action(path, microstate, weights)
                result['path_feature_source'] = (
                    'ohlcv_fallback'
                    if context.market_state.get('ohlcv') and not context.raw_data.get('ticks')
                    else 'microstructure'
                )
                context.action_scores[traj['id']] = result
                traj['action'] = result['total_action']

        action_values = [
            float(score.get('total_action', 0.0))
            for score in context.action_scores.values()
            if isinstance(score, dict)
        ]
        _, _, action_spread = self._score_spread(action_values)
        return {
            'actions_computed': len(context.action_scores),
            'action_spread': action_spread,
        }
    
    def _stage_path_integral(self, context: PipelineContext) -> Dict:
        """Stage 8: Compute Ψ = Σ e^(iS/ℏ)"""
        # Weight by exp(-action)
        epsilon = 0.015  # ℏ
        
        for traj in context.admissible_paths:
            action = traj.get('action', 1.0)
            traj['weight'] = np.exp(-action / epsilon)
        
        return {'integral_computed': True}
    
    def _stage_interference_selection(self, context: PipelineContext) -> Dict:
        """Stage 9: Interference suppresses bad paths"""
        # High weight = low action = survives
        # Already weighted in previous stage
        return {'interference_applied': True}
    
    def _stage_path_selection(self, context: PipelineContext) -> Dict:
        """Stage 10: Select least-action trajectory"""
        if not context.admissible_paths:
            return {'selected': None}
        
        # Select max weight = min action
        best = max(context.admissible_paths, key=lambda t: t.get('weight', 0))
        context.selected_path = best
        
        return {'selected_id': best['id'], 'action': best.get('action', 0)}
    
    def _stage_proposal_generation(self, context: PipelineContext) -> Dict:
        """Stage 11: Extract trade proposal from selected path (curvature-adaptive)."""
        if context.selected_path is None:
            return {'proposal': None}

        path = self._trajectory_points(context.selected_path['path'])
        first_price = path[0][1] if len(path) > 0 else 0.0
        last_price = path[-1][1] if len(path) > 1 else first_price

        # Anchor entry to actual market price — trajectory coords are Riemannian,
        # not directly comparable to broker prices.
        closes = context.raw_data.get('close', [])
        entry  = float(closes[-1]) if closes else first_price

        # --- Curvature extraction ---
        curvature_data = context.geometry_data.get('curvature', {})
        if isinstance(curvature_data, dict):
            K = float(
                curvature_data.get('gaussian_curvature')
                or curvature_data.get('K')
                or curvature_data.get('scalar_curvature')
                or curvature_data.get('curvature_value')
                or 0.0
            )
        else:
            K = 0.0
        regime = context.geometry_data.get('regime', 'FLAT')

        # --- Direction: regime-gated ---
        path_moved   = abs(last_price - first_price) > 1e-8
        path_went_up = (last_price - first_price) > 1e-8

        if not path_moved:
            direction = 'sell' if regime != 'SADDLE' else 'buy'
        elif K < -0.05:
            # Negative curvature (hyperbolic/saddle): breakout regime — follow the path
            direction = 'buy' if path_went_up else 'sell'
        else:
            # Flat / positive curvature: mean-reversion — contrarian to path
            direction = 'sell' if path_went_up else 'buy'

        # --- Curvature-adaptive stop/target (2:1 R:R always) ---
        K_abs = abs(K)
        stop_mult     = min(1.0 + K_abs, 2.0)   # K=0→1.0×, K=0.5→1.5×, cap 2.0×
        base_stop_pips = 0.0010                   # 10 pip base
        stop_pips   = base_stop_pips * stop_mult
        target_pips = stop_pips * 2.0             # 2:1 R:R

        if direction == 'buy':
            stop   = entry - stop_pips
            target = entry + target_pips
        else:
            stop   = entry + stop_pips
            target = entry - target_pips

        # --- Sailing ladder: FVG-indexed lot sizing ---
        fvgs = (context.ict_geometry or {}).get('fvgs', [])
        fvg_index = min(len(fvgs), 3)
        _SAILING_LADDER = {0: 0.01, 1: 0.01, 2: 0.1, 3: 1.0}
        proposed_size = _SAILING_LADDER[fvg_index]

        context.proposal = {
            'direction': direction,
            'entry':     entry,
            'stop':      stop,
            'target':    target,
            'size':      proposed_size,
            'path_id':   context.selected_path['id'],
            'fvg_index': fvg_index,
        }

        # --- Mandatory evidence block ---
        path_prices = [step[1] for step in path]
        path_std    = float(np.std(path_prices)) if len(path_prices) > 1 else 0.0
        evidence = {
            'curvature_mean':     K,
            'curvature_max':      K_abs,
            'curvature_regime':   regime,
            'selected_path_action': context.selected_path.get('action', 0.0),
            'path_entropy':       path_std,
            'num_paths':          getattr(context, '_num_trajectories', 0),
            'hbar':               getattr(context, '_epsilon', 0.015),
            'fvg_index':          fvg_index,
            'stop_multiplier':    stop_mult,
        }
        context.path_integral_evidence = evidence

        return {
            'proposal': context.proposal,
            'evidence': evidence,
        }
    
    def _validate_path_stepwise(self, path: list, direction: str) -> Tuple[bool, str]:
        """
        Π_total: validate every step of a trajectory in Riemannian coordinate space.
        Refusal-first semantics — any single violation refuses the entire path.

        Gates:
          1. Non-degenerate: path must have measurable net movement.
          3. Oscillation: no midpoint retraces more than 80% of path_delta back past start.
          4. Velocity: no single step exceeds 40% of total movement (no teleporting).
        Note: direction consistency (Gate 2) is intentionally omitted — regime-gated
        direction (breakout vs mean-reversion) is handled upstream in proposal generation.
        """
        if not path or len(path) < 2:
            return False, "path_too_short"

        prices = [step[1] for step in path]
        first, last = prices[0], prices[-1]
        path_delta = last - first

        # Gate 1: Non-degenerate — net movement must be measurable
        if abs(path_delta) < 1e-8:
            return False, "degenerate_path"

        path_went_up = path_delta > 0

        # Gate 3: Oscillation — midpoints must not retrace back past start by > 80% of path_delta.
        # For upward paths: reject if any midpoint drops more than 80% of path_delta below start.
        # For downward paths: reject if any midpoint rises more than 80% of |path_delta| above start.
        if len(prices) > 2:
            midprices = prices[1:-1]
            retrace_limit = 0.80
            if path_went_up:
                min_mid = min(midprices)
                threshold = first - retrace_limit * path_delta
                if min_mid < threshold:
                    retrace_frac = (first - min_mid) / path_delta
                    return False, f"excessive_oscillation_{retrace_frac:.0%}_below_start"
            else:
                max_mid = max(midprices)
                threshold = first + retrace_limit * abs(path_delta)
                if max_mid > threshold:
                    retrace_frac = (max_mid - first) / abs(path_delta)
                    return False, f"excessive_oscillation_{retrace_frac:.0%}_above_start"

        # Gate 4: Velocity bound — no single step > 40% of total movement (no teleporting).
        # Only enforced for paths with enough steps that uniform motion stays well under limit.
        if len(prices) >= 5:
            max_step = abs(path_delta) * 0.40
            for i in range(1, len(prices)):
                step_size = abs(prices[i] - prices[i - 1])
                if step_size > max_step:
                    return False, f"velocity_spike_at_step_{i}: {step_size:.6f}"

        return True, "ok"

    def _stage_admissibility_check(self, context: PipelineContext) -> Dict:
        """Stage 12: Final admissibility check — hard risk gates enforced here."""
        proposal = context.proposal
        if not proposal:
            self._audit_gate("stage12_admissibility", "failed", reason="no_proposal")
            return {'admissible': False, 'risk_ok': False, 'reason': 'no_proposal'}

        if os.getenv("ENABLE_FIELD_HAMILTONIAN", "0") == "1" and not context.field_admissible:
            context.risk_check_passed = False
            reason = f"field_hamiltonian_refusal:{context.field_reason}"
            self._audit_gate(
                "stage12_admissibility",
                "failed",
                reason=reason,
                symbol=context.symbol,
            )
            return {'admissible': False, 'risk_ok': False, 'reason': reason}

        # Π_total: path-wise step validation before any risk computation
        if context.selected_path:
            path_ok, path_reason = self._validate_path_stepwise(
                context.selected_path['path'],
                proposal.get('direction', 'buy'),
            )
            if not path_ok:
                context.risk_check_passed = False
                self._audit_gate(
                    "stage12_admissibility",
                    "failed",
                    reason=f"pi_total_path_violation:{path_reason}",
                    symbol=context.symbol,
                )
                return {
                    'admissible': False,
                    'risk_ok': False,
                    'reason': f'pi_total_path_violation: {path_reason}',
                }

        symbol = context.symbol
        direction = proposal.get('direction', 'buy')
        # Clamp proposed size to regime max_position_size before risk check
        rp = context.regime_params or context.adapted_params
        regime_max = float(rp.max_position_size) if rp and hasattr(rp, 'max_position_size') else 1.0
        size = min(
            float(proposal.get('size', self.risk_manager.max_position_size)),
            self.risk_manager.max_position_size * regime_max
        )
        proposal['size'] = size  # Update proposal with clamped size
        entry = proposal.get('entry', 0.0)

        # Hard stop enforcement via ProductionRiskManager (not advisory)
        risk_check = self.risk_manager.check_all_limits(
            symbol=symbol,
            direction=direction,
            size=size,
            price=entry
        )

        # Persist risk check result on context for scheduler pre-collapse assertion
        context.risk_check_passed = risk_check.passed
        context.risk_check_message = risk_check.message

        if not risk_check.passed:
            logger.warning(f"Risk gate FAILED at Stage 12: {risk_check.message}")
            self._audit_gate(
                "stage12_admissibility",
                "failed",
                reason=risk_check.message,
                risk_level=risk_check.level.value,
                symbol=symbol,
            )
            return {
                'admissible': False,
                'risk_ok': False,
                'risk_level': risk_check.level.value,
                'reason': risk_check.message
            }

        # Secondary geometric check: stop distance sanity
        stop_dist = abs(entry - proposal.get('stop', entry - 0.0010))
        if stop_dist > 0.0050:  # 50 pip hard max
            context.risk_check_passed = False
            self._audit_gate(
                "stage12_admissibility",
                "failed",
                reason=f"stop_distance_too_large:{stop_dist:.5f}",
                symbol=symbol,
            )
            return {
                'admissible': False,
                'risk_ok': False,
                'reason': f'stop_distance_too_large: {stop_dist:.5f}'
            }

        # Compute predicted PnL now that size is finalised
        entry = proposal['entry']
        target = proposal.get('target', entry)
        pip_move = abs(target - entry)
        predicted_pnl = round(pip_move * proposal['size'] * 10_000, 4)
        proposal['predicted_pnl'] = predicted_pnl

        self._audit_gate(
            "stage12_admissibility",
            "passed",
            direction=direction,
            risk_level=risk_check.level.value,
            size=size,
            symbol=symbol,
        )
        return {'admissible': True, 'risk_ok': True, 'risk_level': risk_check.level.value}
    
    def _stage_entropy_gate(self, context: PipelineContext) -> Dict:
        """Stage 13: measured uncertainty gate for scheduler collapse."""
        metrics = self._measure_path_uncertainty(context)
        delta_s = metrics['posterior_entropy']
        information_gain = metrics['information_gain']

        context.action_scores['delta_s'] = delta_s
        context.action_scores['information_gain'] = information_gain
        context.action_scores['prior_entropy'] = metrics['prior_entropy']
        context.action_scores['posterior_entropy'] = metrics['posterior_entropy']
        context.action_scores['entropy_diagnostics'] = {
            'path_count': metrics['path_count'],
            'posterior_score_source': metrics['posterior_score_source'],
            'posterior_score_min': metrics['posterior_score_min'],
            'posterior_score_max': metrics['posterior_score_max'],
            'posterior_score_spread': metrics['posterior_score_spread'],
            'selected_path_id': metrics['selected_path_id'],
            'selected_family': metrics['selected_family'],
            'entropy_reason': metrics['entropy_reason'],
        }

        config = getattr(self.scheduler, 'config', None)
        if config is None:
            threshold = 0.5
        elif hasattr(config, 'get'):
            threshold = float(config.get('max_entropy', 0.5))
        else:
            threshold = float(getattr(config, 'max_entropy', 0.5))
        passed = delta_s <= threshold
        status = "passed" if passed else "failed"
        context.entropy_gate_passed = passed
        context.entropy_gate_message = (
            "passed" if passed else metrics['entropy_reason']
        )

        self._audit_gate(
            "stage13_entropy",
            status,
            delta_s=f"{delta_s:.4f}",
            entropy_reason=metrics['entropy_reason'] if not passed else None,
            information_gain=f"{information_gain:.4f}",
            path_count=metrics['path_count'],
            posterior_entropy=f"{metrics['posterior_entropy']:.4f}",
            posterior_score_max=f"{metrics['posterior_score_max']:.6g}",
            posterior_score_min=f"{metrics['posterior_score_min']:.6g}",
            posterior_score_source=metrics['posterior_score_source'],
            posterior_score_spread=f"{metrics['posterior_score_spread']:.6g}",
            prior_entropy=f"{metrics['prior_entropy']:.4f}",
            selected_family=metrics['selected_family'],
            selected_path_id=metrics['selected_path_id'],
            threshold=f"{threshold:.4f}",
        )
        return {**metrics, 'delta_s': delta_s, 'threshold': threshold, 'passed': passed}

    @staticmethod
    def _normalized_entropy(scores: List[float]) -> float:
        clean_scores: List[float] = []
        for score in scores:
            try:
                value = float(score)
            except (TypeError, ValueError):
                continue
            if np.isfinite(value) and value > 0.0:
                clean_scores.append(value)

        clean = np.array(clean_scores, dtype=float)
        if clean.size <= 1:
            return 0.0

        total = float(clean.sum())
        if total <= 0.0:
            return 1.0

        probs = clean / total
        entropy = -float(np.sum(probs * np.log(probs + 1e-12)))
        return max(0.0, min(1.0, entropy / float(np.log(clean.size))))

    @staticmethod
    def _score_spread(values: List[float]) -> Tuple[float, float, float]:
        if not values:
            return 0.0, 0.0, 0.0
        arr = np.array(values, dtype=float)
        return float(arr.min()), float(arr.max()), float(arr.max() - arr.min())

    @staticmethod
    def _has_meaningful_spread(values: List[float]) -> bool:
        if len(values) <= 1:
            return True
        score_min, score_max, spread = PipelineOrchestrator._score_spread(values)
        scale = max(abs(score_min), abs(score_max), 1.0)
        return bool(spread > max(1e-9, scale * 1e-6))

    @staticmethod
    def _costs_to_posterior_scores(costs: List[float]) -> List[float]:
        if len(costs) == 1:
            return [1.0]
        if not PipelineOrchestrator._has_meaningful_spread(costs):
            return []
        arr = np.array(costs, dtype=float)
        spread = float(arr.max() - arr.min())
        if spread <= 0.0:
            return []
        normalized_cost = (arr - float(arr.min())) / spread
        temperature = 0.08
        scores = np.exp(-normalized_cost / temperature)
        return [float(score) for score in scores if np.isfinite(score) and score > 0.0]

    def _path_action_costs(self, context: PipelineContext) -> List[float]:
        actions: List[float] = []
        for path in context.admissible_paths:
            path_id = path.get('id')
            result = context.action_scores.get(path_id, {})
            try:
                if isinstance(result, dict) and 'total_action' in result:
                    action = float(result.get('total_action'))
                else:
                    action = float(path.get('action'))
            except (TypeError, ValueError):
                continue
            if np.isfinite(action):
                actions.append(action)
        return actions

    def _path_weight_scores(self, context: PipelineContext) -> List[float]:
        weights: List[float] = []
        for path in context.admissible_paths:
            try:
                weight = float(path.get('weight', 0.0))
            except (TypeError, ValueError):
                continue
            if np.isfinite(weight) and weight > 0.0:
                weights.append(weight)
        return weights

    def _posterior_scores_with_diagnostics(self, context: PipelineContext) -> Tuple[List[float], Dict[str, Any]]:
        path_count = len(context.admissible_paths)
        selected = context.selected_path or {}
        selected_path_id = str(selected.get('id') or '')
        selected_family = str(selected.get('family') or '')

        actions = self._path_action_costs(context)
        action_min, action_max, action_spread = self._score_spread(actions)
        if len(actions) == path_count:
            action_scores = self._costs_to_posterior_scores(actions)
            if action_scores:
                score_min, score_max, score_spread = self._score_spread(action_scores)
                return action_scores, {
                    "path_count": path_count,
                    "posterior_score_source": "action",
                    "posterior_score_min": score_min,
                    "posterior_score_max": score_max,
                    "posterior_score_spread": score_spread,
                    "selected_path_id": selected_path_id,
                    "selected_family": selected_family,
                    "entropy_reason": "action_distribution_measured",
                }

        weights = self._path_weight_scores(context)
        if len(weights) == path_count and self._has_meaningful_spread(weights):
            score_min, score_max, score_spread = self._score_spread(weights)
            return weights, {
                "path_count": path_count,
                "posterior_score_source": "weight",
                "posterior_score_min": score_min,
                "posterior_score_max": score_max,
                "posterior_score_spread": score_spread,
                "selected_path_id": selected_path_id,
                "selected_family": selected_family,
                "entropy_reason": "weight_distribution_measured",
            }

        score_source = "action" if actions else ("weight" if weights else "uniform")
        score_min = action_min
        score_max = action_max
        score_spread = action_spread
        if not actions and weights:
            score_min, score_max, score_spread = self._score_spread(weights)

        return [1.0] * path_count, {
            "path_count": path_count,
            "posterior_score_source": score_source,
            "posterior_score_min": score_min,
            "posterior_score_max": score_max,
            "posterior_score_spread": score_spread,
            "selected_path_id": selected_path_id,
            "selected_family": selected_family,
            "entropy_reason": "flat_posterior_distribution",
        }

    def _measure_path_uncertainty(self, context: PipelineContext) -> Dict[str, Any]:
        path_count = len(context.admissible_paths)
        prior_entropy = self._normalized_entropy([1.0] * path_count)
        posterior_scores, diagnostics = self._posterior_scores_with_diagnostics(context)
        posterior_entropy = self._normalized_entropy(posterior_scores)
        information_gain = max(0.0, prior_entropy - posterior_entropy)
        return {
            "prior_entropy": prior_entropy,
            "posterior_entropy": posterior_entropy,
            "information_gain": information_gain,
            **diagnostics,
        }
    
    def _stage_scheduler_collapse(self, context: PipelineContext) -> Dict:
        """Stage 15: Scheduler authorization (Λ) — requires prior risk gate passage."""
        from ..kernel.scheduler import CollapseDecision

        # Pre-collapse invariant: risk gate MUST have passed at Stage 12
        if not getattr(context, 'risk_check_passed', False):
            logger.error("Collapse attempted without passing risk gate — REFUSED")
            context.collapse_decision = 'REFUSED'
            self._audit_gate(
                "stage15_scheduler",
                "refused",
                reason=f"risk_gate_not_passed:{context.risk_check_message}",
                symbol=context.symbol,
            )
            return {
                'decision': 'REFUSED',
                'authorized': False,
                'token': None,
                'reason': f'risk_gate_not_passed: {context.risk_check_message}'
            }

        if not getattr(context, 'entropy_gate_passed', False):
            reason = getattr(context, 'entropy_gate_message', '') or 'entropy_gate_not_passed'
            logger.error("Collapse attempted without passing entropy gate — REFUSED")
            context.collapse_decision = 'REFUSED'
            self._audit_gate(
                "stage15_scheduler",
                "refused",
                delta_s=f"{context.action_scores.get('delta_s', 1.0):.4f}",
                reason=f"entropy_gate_not_passed:{reason}",
                symbol=context.symbol,
            )
            return {
                'decision': 'REFUSED',
                'authorized': False,
                'token': None,
                'reason': f'entropy_gate_not_passed: {reason}'
            }

        # Build trajectory dict for scheduler
        projected = [{
            'id': t['id'],
            'energy': float(t.get('energy', 0.0)),
            'action': t.get('action', 1.0),
            'operator_scores': {},
        } for t in context.admissible_paths]

        delta_s = context.action_scores.get('delta_s', 0.3)
        pre_checkpoint = self._persist_scheduler_checkpoint("pre", context)
        if pre_checkpoint is None:
            context.collapse_decision = 'REFUSED'
            self._audit_gate(
                "stage15_scheduler",
                "refused",
                reason="checkpoint_failure",
                symbol=context.symbol,
            )
            return {'decision': 'REFUSED', 'authorized': False, 'reason': 'checkpoint_failure'}

        ok, result = self.collapse_breaker.call(
            self.scheduler.authorize_collapse,
            proposal=context.proposal,
            projected_trajectories=projected,
            delta_s=delta_s,
            constraints_passed=context.risk_check_passed,
            reconciliation_clear=True
        )

        if not ok:
            context.collapse_decision = 'REFUSED'
            logger.error(f"Stage 15: collapse rejected by circuit breaker — {result}")
            breaker_status = {}
            get_status = getattr(self.collapse_breaker, "get_status", None)
            if callable(get_status):
                breaker_status = get_status()
            self._persist_scheduler_checkpoint(
                "failure",
                context,
                extra={"error": str(result), "breaker_status": breaker_status},
            )
            self._trigger_risk_kill_switch("scheduler_collapse_recovery_unsafe")
            self._audit_gate(
                "stage15_scheduler",
                "refused",
                reason="circuit_breaker_open",
                symbol=context.symbol,
            )
            return {'decision': 'REFUSED', 'authorized': False, 'reason': 'circuit_breaker_open'}

        decision, token = result
        context.collapse_decision = decision.name
        context.execution_token = token
        post_checkpoint = self._persist_scheduler_checkpoint(
            "post",
            context,
            extra={
                "decision": decision.name,
                "authorized": decision == CollapseDecision.AUTHORIZED,
            },
        )
        if post_checkpoint is None:
            context.collapse_decision = 'REFUSED'
            self._audit_gate(
                "stage15_scheduler",
                "refused",
                reason="checkpoint_failure",
                symbol=context.symbol,
            )
            return {'decision': 'REFUSED', 'authorized': False, 'reason': 'checkpoint_failure'}
        self._audit_gate(
            "stage15_scheduler",
            "passed" if decision == CollapseDecision.AUTHORIZED else "refused",
            decision=decision.name,
            delta_s=f"{delta_s:.4f}",
            information_gain=f"{context.action_scores.get('information_gain', 0.0):.4f}",
            symbol=context.symbol,
            token=token.token_id if token else None,
        )

        try:
            from trading.observability.metrics import MetricsCollector
            MetricsCollector.get().record_decision(decision.name)
        except Exception:
            pass

        return {
            'decision': decision.name,
            'authorized': decision == CollapseDecision.AUTHORIZED,
            'token': token.token_id if token else None
        }
    
    def _stage_execution(self, context: PipelineContext) -> Dict:
        """Stage 16: Execute trade — paper simulation or live broker routing."""
        if context.collapse_decision != 'AUTHORIZED':
            self._audit_gate("stage16_execution", "skipped", reason="not_authorized", symbol=context.symbol)
            return {'executed': False}

        # Kill switch guard — never route orders when kill switch is active
        if getattr(self.risk_manager, 'kill_switch_active', False):
            logger.warning("Stage 16: kill switch active — execution blocked")
            self._audit_gate("stage16_execution", "blocked", reason="kill_switch_active", symbol=context.symbol)
            return {'executed': False, 'reason': 'kill_switch_active'}

        if self._paper_mode:
            # Paper / demo mode: simulate fill at proposed price
            context.execution_result = {
                'order_id': f'ord_{int(time.time())}',
                'symbol': context.symbol,
                'entry_price': context.proposal['entry'],
                'status': 'filled',
                'realized_pnl': 0.0,
                'pnl_status': 'entry_simulated',
            }
            self._audit_gate(
                "stage16_execution",
                "simulated",
                order_id=context.execution_result['order_id'],
                symbol=context.symbol,
            )
            return {'executed': True, 'order': context.execution_result}

        # Live mode: route through the explicitly selected demo broker.
        live_broker_mode = getattr(self, 'live_broker_mode', None)
        MT5Order = None
        _mt5 = None
        if live_broker_mode in (None, 'mt5'):
            try:
                from trading.brokers.mt5_broker import MT5Order, mt5_broker as _mt5
            except Exception as exc:
                logger.warning("Stage 16: MT5 broker unavailable: %s", exc)

        _deriv = None
        try:
            from trading.brokers.deriv_broker import DerivBroker, DerivOrder, deriv_broker as _deriv
        except Exception as exc:
            logger.warning("Stage 16: Deriv broker unavailable: %s", exc)
            _deriv = None

        direction = context.proposal.get('direction', 'buy')
        entry     = context.proposal['entry']
        size      = context.proposal.get('size', 0.01)
        stop      = context.proposal.get('stop')
        target    = context.proposal.get('target')

        result = None
        broker_name = None
        attempted_broker = False

        # --- MT5 ---
        if live_broker_mode in (None, 'mt5') and _mt5 is not None and _mt5.connected:
            attempted_broker = True
            mt5_order = MT5Order(
                symbol=context.symbol,
                order_type=direction,
                volume=size,
                sl=stop,
                tp=target,
                comment='ApexQuantumICT',
            )
            result = _mt5.place_order(mt5_order, token=context.execution_token)
            if result:
                broker_name = "mt5"
                logger.info(
                    "Stage 16: MT5 order placed ticket=%s %s %s size=%.2f",
                    result.get('ticket'), direction.upper(), context.symbol, size
                )
                self._audit_gate(
                    "stage16_execution",
                    "passed",
                    broker="mt5",
                    size=size,
                    symbol=context.symbol,
                    ticket=result.get('ticket'),
                )

        # --- Deriv ---
        if result is None and live_broker_mode in (None, 'deriv') and _deriv is not None and _deriv.connected:
            attempted_broker = True
            deriv_config = getattr(self, 'deriv_live_config', {}) or {}
            contract_type = 'CALL' if direction == 'buy' else 'PUT'
            # Case-insensitive check for 'frx' prefix
            symbol_lower = context.symbol[:3].lower() if len(context.symbol) >= 3 else ""
            deriv_symbol = 'frx' + context.symbol if symbol_lower != 'frx' else context.symbol
            d_order = DerivOrder(
                symbol=deriv_symbol,
                contract_type=contract_type,
                duration=int(deriv_config.get('duration', 5)),
                duration_unit=str(deriv_config.get('duration_unit', 'm')),
                amount=float(deriv_config.get('stake', 1.0)),
            )
            result = _deriv.place_contract(d_order, token=context.execution_token)
            if result:
                broker_name = "deriv"
                logger.info(
                    "Stage 16: Deriv contract placed %s %s stake=$%.2f duration=%d%s",
                    contract_type, d_order.symbol, d_order.amount, d_order.duration, d_order.duration_unit
                )
                self._audit_gate(
                    "stage16_execution",
                    "passed",
                    broker="deriv",
                    contract_id=result.get('contract_id'),
                    stake=d_order.amount,
                    symbol=context.symbol,
                )

        if result is None:
            reason = 'broker_refusal' if attempted_broker else 'no_broker'
            logger.error("Stage 16: live execution failed - %s", reason)
            self._audit_gate("stage16_execution", "failed", reason=reason, symbol=context.symbol)
            return {'executed': False, 'reason': reason}

        context.execution_result = {
            'order_id':    str(result.get('ticket') or result.get('contract_id') or f'ord_{int(time.time())}'),
            'symbol':      context.symbol,
            'entry_price': float(result.get('price', entry) if broker_name == "mt5" else entry),
            'broker':      broker_name,
            'status':      'filled',
            'realized_pnl': 0.0,
            'pnl_status':   'pending_close',
        }
        return {'executed': True, 'order': context.execution_result}
    
    def _stage_reconciliation(self, context: PipelineContext) -> Dict:
        """Stage 17: Compare intended vs actual execution"""
        if not context.execution_result:
            context.reconciliation_status = 'no_execution'
            self._audit_gate("stage17_reconciliation", "skipped", reason="no_execution", symbol=context.symbol)
            return {'status': 'no_execution'}
        
        # Price divergence — compare entry prices
        predicted = context.proposal['entry']
        actual = context.execution_result['entry_price']
        price_divergence = abs(predicted - actual)

        if price_divergence < 0.0001:  # 1 pip
            status = 'match'
        elif price_divergence < 0.0005:  # 5 pips
            status = 'mismatch'
        else:
            status = 'rollback'

        context.reconciliation_status = status

        broker = str(context.execution_result.get('broker') or "").lower()
        pnl_status = context.execution_result.get('pnl_status')
        live_pending_close = pnl_status == 'pending_close' or broker in {'mt5', 'deriv'}
        pnl_divergence = None
        divergence_flagged = False

        if live_pending_close:
            pnl_status = 'pending_close'
            context.execution_result['pnl_status'] = pnl_status
        else:
            # PnL divergence is only valid once realized PnL exists.
            predicted_pnl = context.proposal.get('predicted_pnl', 0.0)
            realized_pnl = context.execution_result.get('realized_pnl', predicted_pnl)
            pnl_divergence = abs(predicted_pnl - realized_pnl) / max(abs(predicted_pnl), 1.0)
            self.divergence_history.append(pnl_divergence)
            divergence_flagged = pnl_divergence > 0.15

        if divergence_flagged:
            logger.warning(
                f"Stage 17: PnL divergence {pnl_divergence:.1%} > 15% "
                f"(predicted={predicted_pnl:.2f}, realized={realized_pnl:.2f})"
            )
            self.scheduler.update_action_weights(
                pnl=-pnl_divergence * 10,
                delta_s=float(context.action_scores.get('delta_s', 0.3)),
                status='mismatch',
                contrib={'L': 25, 'T': 25, 'E': 25, 'R': 25},
                constraints_passed=False,
                evidence_complete=False
            )

        self._audit_gate(
            "stage17_reconciliation",
            "flagged" if divergence_flagged else "passed",
            price_divergence=f"{price_divergence:.8f}",
            pnl_divergence=f"{pnl_divergence:.4f}" if pnl_divergence is not None else None,
            pnl_status=pnl_status,
            reconciliation_status=status,
            symbol=context.symbol,
        )
        return {
            'status': status,
            'divergence': price_divergence,
            'pnl_divergence': pnl_divergence,
            'pnl_status': pnl_status,
            'divergence_flagged': divergence_flagged
        }
    
    def _stage_evidence_emission(self, context: PipelineContext) -> Dict:
        """Stage 18: Emit cryptographic evidence"""
        import hashlib
        
        evidence_data = {
            'symbol': context.symbol,
            'proposal': context.proposal,
            'decision': context.collapse_decision,
            'execution': context.execution_result,
            'reconciliation': context.reconciliation_status,
            'field': context.field_data,
            'qpt_token_id': None,
        }
        
        evidence_str = str(evidence_data)
        provisional_hash = hashlib.sha256(evidence_str.encode()).hexdigest()[:32]

        try:
            from core.economics.qpt_token import mint_qpt_if_applicable
            from core.orchestration.reconciliation import ReconciliationReport

            report = ReconciliationReport(
                execution_id=str(
                    context.execution_result.get("order_id")
                    or context.execution_result.get("ticket")
                    or context.execution_result.get("contract_id")
                    or provisional_hash
                ),
                symbol=context.symbol,
                accepted=context.reconciliation_status == "match",
                status=context.reconciliation_status or "unknown",
                realized_pnl=context.execution_result.get("pnl"),
                admissible=bool(context.risk_check_passed),
                information_gain=float(context.action_scores.get("delta_s", 0.0) or 0.0),
                scheduler_authorized=context.collapse_decision == "AUTHORIZED",
                evidence_valid=bool(provisional_hash),
                broker=context.source,
                payload={"provisional_evidence_hash": provisional_hash},
            )
            context.qpt_token_id = mint_qpt_if_applicable(report)
        except Exception as exc:
            logger.warning("Stage 18: QPT minting skipped: %s", exc)
            context.qpt_token_id = None

        evidence_data['qpt_token_id'] = context.qpt_token_id
        context.evidence_hash = hashlib.sha256(str(evidence_data).encode()).hexdigest()[:32]

        self._audit_gate(
            "stage18_evidence",
            "passed",
            evidence_hash=context.evidence_hash,
            qpt_token_id=context.qpt_token_id,
            symbol=context.symbol,
        )
        return {'evidence_hash': context.evidence_hash, 'qpt_token_id': context.qpt_token_id}
    
    def _stage_weight_update(self, context: PipelineContext) -> Dict:
        """Stage 19: Backward learning - update action weights"""
        if not self.use_weight_learning:
            self._audit_gate("stage19_weight_update", "skipped", reason="learning_disabled", symbol=context.symbol)
            return {'updated': False, 'reason': 'learning_disabled'}
        
        if context.collapse_decision != 'AUTHORIZED':
            self._audit_gate("stage19_weight_update", "skipped", reason="not_authorized", symbol=context.symbol)
            return {'updated': False, 'reason': 'not_authorized'}
        
        # Stage 18 learns entry quality (L/T/E/R operator weights), not realized PnL.
        # Realized PnL flows asynchronously via MT5PositionCloseTracker -> PPO only.
        _RECONCILIATION_REWARD = {
            'match':         10.0,
            'mismatch':      -5.0,
            'rollback':     -20.0,
            'no_execution':   0.0,
        }
        pnl = _RECONCILIATION_REWARD.get(context.reconciliation_status, 0.0)
        
        # Get contributions from selected path
        if context.selected_path:
            path_id = context.selected_path['id']
            action_result = context.action_scores.get(path_id, {})
            contrib = {
                'L': action_result.get('S_L', 0) * 100,
                'T': action_result.get('S_T', 0) * 100,
                'E': action_result.get('S_E', 0) * 100,
                'R': action_result.get('S_R', 0) * 100,
            }
        else:
            contrib = {'L': 25, 'T': 25, 'E': 25, 'R': 25}
        
        # Update weights — use actual gate results, not hardcoded True
        result = self.scheduler.update_action_weights(
            pnl=pnl,
            delta_s=float(context.action_scores.get('delta_s', 0.3)),
            status=context.reconciliation_status,
            contrib=contrib,
            constraints_passed=getattr(context, 'risk_check_passed', True),
            evidence_complete=bool(getattr(context, 'evidence_hash', ''))
        )
        
        context.weight_update_result = result
        self._audit_gate(
            "stage19_weight_update",
            "passed" if result['updated'] else "flagged",
            reason=result.get('reason'),
            reward=f"{result.get('reward', 0.0):.4f}",
            reconciliation_status=context.reconciliation_status,
            symbol=context.symbol,
        )
        
        return {
            'updated': result['updated'],
            'reward': result['reward'],
            'new_weights': result['new_weights']
        }
    
    def get_statistics(self) -> Dict:
        """Get pipeline execution statistics"""
        return {
            'total_executions': self.execution_count,
            'successful': self.success_count,
            'failed': self.failure_count,
            'success_rate': self.success_count / max(self.execution_count, 1),
        }
