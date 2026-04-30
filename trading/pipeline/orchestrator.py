"""
orchestrator.py - 20-Stage Canonical Pipeline Orchestrator.

Implements the complete transformation pipeline:

Raw Data → State Construction → Path Generation → Constraint Filtering
→ Action Evaluation → Interference Selection → Proposal → Admissibility
→ Entropy Gate → Scheduler → Execution → Reconciliation → Evidence → Learning

Each stage is a checkpointed transformation with typed inputs/outputs.
"""

import time
import logging
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

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
    trajectories: List[Dict] = field(default_factory=list)
    admissible_paths: List[Dict] = field(default_factory=list)
    action_scores: Dict = field(default_factory=dict)
    selected_path: Optional[Dict] = None
    proposal: Dict = field(default_factory=dict)
    collapse_decision: Optional[str] = None
    execution_token: Optional[Any] = None
    execution_result: Dict = field(default_factory=dict)
    reconciliation_status: str = ""
    evidence_hash: str = ""
    weight_update_result: Dict = field(default_factory=dict)
    risk_check_passed: bool = False
    risk_check_message: str = ""
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
            timeout_seconds=30.0
        )
        self.collapse_breaker = get_circuit_breaker("scheduler_collapse", cb_config)
        self.collapse_breaker.register_on_open(
            lambda: self.risk_manager.trigger_kill_switch("circuit_breaker_open")
        )

        # Rolling PnL divergence histogram (last 100 executions)
        self.divergence_history: deque = deque(maxlen=100)

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
        
        # Execute stages in sequence
        stages = [
            PipelineStage.DATA_INGESTION,
            PipelineStage.STATE_CONSTRUCTION,
            PipelineStage.ICT_EXTRACTION,
            PipelineStage.GEOMETRY_COMPUTATION,
            PipelineStage.TRAJECTORY_GENERATION,
            PipelineStage.RAMANUJAN_COMPRESSION,
            PipelineStage.ADMISSIBILITY_FILTERING,
            PipelineStage.ACTION_EVALUATION,
            PipelineStage.PATH_INTEGRAL,
            PipelineStage.INTERFERENCE_SELECTION,
            PipelineStage.PATH_SELECTION,
            PipelineStage.PROPOSAL_GENERATION,
            PipelineStage.ADMISSIBILITY_CHECK,
            PipelineStage.ENTROPY_GATE,
            PipelineStage.SCHEDULER_COLLAPSE,
            PipelineStage.EXECUTION,
            PipelineStage.RECONCILIATION,
            PipelineStage.EVIDENCE_EMISSION,
            PipelineStage.WEIGHT_UPDATE,
        ]
        
        for stage in stages:
            result = self._execute_stage(stage, context)
            context.stage_history.append(result)
            
            if not result.success:
                logger.warning(f"Pipeline failed at stage {stage.value}: {result.error}")
                context.stage_history.append(
                    StageResult(stage=PipelineStage.FAILED, success=False, error=result.error)
                )
                self.failure_count += 1
                self._release_execution_token(context)
                return context
            
            # Check for early termination
            if stage == PipelineStage.SCHEDULER_COLLAPSE:
                if context.collapse_decision == 'REFUSED':
                    logger.info("Scheduler refused collapse - terminating pipeline")
                    context.stage_history.append(
                        StageResult(stage=PipelineStage.COMPLETED, success=True, 
                                   output={'reason': 'scheduler_refused'})
                    )
                    self.success_count += 1
                    self._release_execution_token(context)
                    return context
        
        # Completed successfully
        context.stage_history.append(
            StageResult(stage=PipelineStage.COMPLETED, success=True,
                       output={'duration_ms': context.duration_ms})
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
    
    def _execute_stage(self, stage: PipelineStage, context: PipelineContext) -> StageResult:
        """Execute a single pipeline stage"""
        start = time.time()
        
        handler = self.stage_handlers.get(stage)
        if handler is None:
            return StageResult(
                stage=stage,
                success=False,
                error=f"No handler for stage {stage}"
            )
        
        try:
            output = handler(context)
            duration = (time.time() - start) * 1000

            # Record stage timing for Prometheus metrics
            try:
                from trading.observability.metrics import MetricsCollector
                MetricsCollector.get().record_stage(stage.value, duration)
            except Exception:
                pass

            # Create checkpoint hash
            import hashlib
            checkpoint_data = f"{stage.value}:{context.symbol}:{context.timestamp}"
            checkpoint_hash = hashlib.sha256(checkpoint_data.encode()).hexdigest()[:16]

            return StageResult(
                stage=stage,
                success=True,
                output=output,
                duration_ms=duration,
                checkpoint_hash=checkpoint_hash
            )

        except Exception as e:
            duration = (time.time() - start) * 1000
            logger.error(f"Stage {stage.value} failed: {e}")
            return StageResult(
                stage=stage,
                success=False,
                error=str(e),
                duration_ms=duration
            )
    
    # === STAGE HANDLERS ===
    
    def _stage_data_ingestion(self, context: PipelineContext) -> Dict:
        """Stage 1: Normalize raw data into canonical format"""
        # Already done in context initialization
        return {'normalized': True, 'source': context.source}
    
    def _stage_state_construction(self, context: PipelineContext) -> Dict:
        """Stage 2: Build MarketState from raw data"""
        # If microstructure enabled, process ticks
        if self.use_microstructure and 'ticks' in context.raw_data:
            from ..microstructure import TickProcessor
            processor = TickProcessor()
            
            micro = None
            for tick in context.raw_data['ticks']:
                micro = processor.process_tick(tick)
            
            if micro:
                context.market_state['microstructure'] = micro

        order_book_result = self._stage_order_book_analysis(context)
        
        context.market_state['ohlcv'] = context.raw_data.get('ohlcv', [])
        context.market_state['symbol'] = context.symbol
        
        return {'state_built': True, **order_book_result}

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
        context.ict_geometry = {
            'liquidity_zones': context.raw_data.get('liquidity_zones', []),
            'fvgs': context.raw_data.get('fvgs', []),
            'session': context.raw_data.get('session', 'ny'),
            'htf_bias': context.raw_data.get('htf_bias', 'neutral'),
        }

        # Regime detection — requires at least a minimal price DataFrame
        try:
            import pandas as pd
            from ..core.market_regime_detector import MarketRegimeDetector

            ohlcv = context.raw_data.get('ohlcv') or context.market_state.get('ohlcv', [])
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
        """Stage 5: Compress paths into families"""
        # Group trajectories by behavior type
        families = {
            'sweep_continuation': context.trajectories[:2],
            'reversal': context.trajectories[2:4],
            'consolidation': context.trajectories[4:],
        }
        
        return {'families': list(families.keys())}
    
    def _stage_admissibility_filtering(self, context: PipelineContext) -> Dict:
        """Stage 6: Π_total - Filter illegal paths"""
        # All paths admissible for now
        context.admissible_paths = context.trajectories
        
        return {'admissible_count': len(context.admissible_paths)}
    
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
                # Convert path format
                micro = context.market_state.get('microstructure', {})
                path = [
                    {
                        'price': p[1],
                        'ofi': micro.get('ofi', 0.0),
                        'timestamp': p[0],
                        'spread': micro.get('spread', 0.0),
                        'acceleration': micro.get('acceleration', 0.0),
                    }
                    for p in traj['path']
                ]

                result = action_comp.compute_full_action(path, microstate, weights)
                context.action_scores[traj['id']] = result
                traj['action'] = result['total_action']

        return {'actions_computed': len(context.action_scores)}
    
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

        path = context.selected_path['path']
        first_price = path[0][1]
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
            return {'admissible': False, 'risk_ok': False, 'reason': 'no_proposal'}

        # Π_total: path-wise step validation before any risk computation
        if context.selected_path:
            path_ok, path_reason = self._validate_path_stepwise(
                context.selected_path['path'],
                proposal.get('direction', 'buy'),
            )
            if not path_ok:
                context.risk_check_passed = False
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

        return {'admissible': True, 'risk_ok': True, 'risk_level': risk_check.level.value}
    
    def _stage_entropy_gate(self, context: PipelineContext) -> Dict:
        """Stage 13: ΔS check - information gain threshold"""
        # Mock entropy calculation
        delta_s = 0.3  # Would compute from path variance
        
        threshold = 0.5
        passed = delta_s < threshold
        
        return {'delta_s': delta_s, 'passed': passed}
    
    def _stage_scheduler_collapse(self, context: PipelineContext) -> Dict:
        """Stage 15: Scheduler authorization (Λ) — requires prior risk gate passage."""
        from ..kernel.scheduler import CollapseDecision

        # Pre-collapse invariant: risk gate MUST have passed at Stage 12
        if not getattr(context, 'risk_check_passed', False):
            logger.error("Collapse attempted without passing risk gate — REFUSED")
            context.collapse_decision = 'REFUSED'
            return {
                'decision': 'REFUSED',
                'authorized': False,
                'token': None,
                'reason': f'risk_gate_not_passed: {context.risk_check_message}'
            }

        # Build trajectory dict for scheduler
        projected = [{
            'id': t['id'],
            'energy': t['energy'],
            'action': t.get('action', 1.0),
            'operator_scores': {},
        } for t in context.admissible_paths]

        delta_s = context.action_scores.get('delta_s', 0.3)

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
            return {'decision': 'REFUSED', 'authorized': False, 'reason': 'circuit_breaker_open'}

        decision, token = result
        context.collapse_decision = decision.name
        context.execution_token = token

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
            return {'executed': False}

        # Kill switch guard — never route orders when kill switch is active
        if getattr(self.risk_manager, 'kill_switch_active', False):
            logger.warning("Stage 16: kill switch active — execution blocked")
            return {'executed': False, 'reason': 'kill_switch_active'}

        if self._paper_mode:
            # Paper / demo mode: simulate fill at proposed price
            context.execution_result = {
                'order_id': f'ord_{int(time.time())}',
                'symbol': context.symbol,
                'entry_price': context.proposal['entry'],
                'status': 'filled',
                'realized_pnl': 0.0,
            }
            return {'executed': True, 'order': context.execution_result}

        # Live mode: place market order directly on MT5 (Deriv fallback not yet supported)
        from trading.brokers.mt5_broker import MT5Broker, MT5Order, mt5_broker as _mt5
        from trading.brokers.deriv_broker import DerivBroker, DerivOrder, deriv_broker as _deriv

        direction = context.proposal.get('direction', 'buy')
        entry     = context.proposal['entry']
        size      = context.proposal.get('size', 0.01)
        stop      = context.proposal.get('stop')
        target    = context.proposal.get('target')

        result = None

        # --- MT5 ---
        if _mt5.connected:
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
                logger.info(
                    "Stage 16: MT5 order placed ticket=%s %s %s size=%.2f",
                    result.get('ticket'), direction.upper(), context.symbol, size
                )

        # --- Deriv fallback ---
        if result is None and _deriv.connected:
            contract_type = 'CALL' if direction == 'buy' else 'PUT'
            d_order = DerivOrder(
                symbol='frx' + context.symbol if not context.symbol.startswith('frx') else context.symbol,
                contract_type=contract_type,
                duration=5,
                duration_unit='m',
                amount=max(round(size * 100, 2), 1.0),
            )
            result = _deriv.place_contract(d_order, token=context.execution_token)
            if result:
                logger.info(
                    "Stage 16: Deriv contract placed %s %s size=%.2f",
                    contract_type, context.symbol, size
                )

        if result is None:
            logger.error("Stage 16: no broker available for live execution — order not placed")
            return {'executed': False, 'reason': 'no_broker'}

        context.execution_result = {
            'order_id':    str(result.get('ticket') or result.get('contract_id') or f'ord_{int(time.time())}'),
            'symbol':      context.symbol,
            'entry_price': float(result.get('price', entry)),
            'status':      'filled',
            'realized_pnl': 0.0,
        }
        return {'executed': True, 'order': context.execution_result}
    
    def _stage_reconciliation(self, context: PipelineContext) -> Dict:
        """Stage 16: Compare intended vs actual execution"""
        if not context.execution_result:
            context.reconciliation_status = 'no_execution'
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

        # PnL divergence — flag if predicted vs realized PnL exceeds 15%
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
                delta_s=0.3,
                status='mismatch',
                contrib={'L': 25, 'T': 25, 'E': 25, 'R': 25},
                constraints_passed=False,
                evidence_complete=False
            )

        return {
            'status': status,
            'divergence': price_divergence,
            'pnl_divergence': pnl_divergence,
            'divergence_flagged': divergence_flagged
        }
    
    def _stage_evidence_emission(self, context: PipelineContext) -> Dict:
        """Stage 17: Emit cryptographic evidence"""
        import hashlib
        
        evidence_data = {
            'symbol': context.symbol,
            'proposal': context.proposal,
            'decision': context.collapse_decision,
            'execution': context.execution_result,
            'reconciliation': context.reconciliation_status,
        }
        
        evidence_str = str(evidence_data)
        context.evidence_hash = hashlib.sha256(evidence_str.encode()).hexdigest()[:32]
        
        return {'evidence_hash': context.evidence_hash}
    
    def _stage_weight_update(self, context: PipelineContext) -> Dict:
        """Stage 18: Backward learning - update action weights"""
        if not self.use_weight_learning:
            return {'updated': False, 'reason': 'learning_disabled'}
        
        if context.collapse_decision != 'AUTHORIZED':
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
            delta_s=0.3,
            status=context.reconciliation_status,
            contrib=contrib,
            constraints_passed=getattr(context, 'risk_check_passed', True),
            evidence_complete=bool(getattr(context, 'evidence_hash', ''))
        )
        
        context.weight_update_result = result
        
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
