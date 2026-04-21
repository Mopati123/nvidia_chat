"""
upgraded_action_curvature.py - Curvature-aware liquidity cost.

Extends S_L (liquidity cost) with curvature penalty:

    S_L_curvature = S_L + λ_K · ∫ |K(γ(s))| ds

Where:
    S_L = Base liquidity cost (flow-weighted)
    λ_K = Curvature penalty weight
    K = Gaussian curvature along path

This means:
    - High curvature paths (|K| large) are more expensive
    - Low curvature paths (flat regions) are cheaper
    - Paths through attractors (K>0) or saddles (K<0) are penalized

The system prefers geodesics through flat regions (continuation).
"""

import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass


@dataclass
class CurvatureActionConfig:
    """Configuration for curvature-aware action"""
    lambda_curvature: float = 0.5  # Weight for curvature penalty
    base_liquidity_weight: float = 1.0  # Weight for base S_L
    regime_threshold: float = 0.01  # Curvature regime threshold


class CurvatureAwareLiquidityCost:
    """
    Liquidity cost component with curvature penalty.
    
    Combines:
    1. Base liquidity cost (from upgraded_components.py)
    2. Curvature penalty (high |K| = high cost)
    
    The curvature penalty makes the system prefer:
    - Flat regions (continuation)
    - Avoid basins (mean-reversion traps)
    - Avoid saddles (instability)
    """
    
    def __init__(self,
                 liquidity_field,
                 curvature_analyzer,
                 config: Optional[CurvatureActionConfig] = None):
        """
        Initialize curvature-aware liquidity cost.
        
        Args:
            liquidity_field: LiquidityField instance
            curvature_analyzer: CurvatureAnalyzer instance
            config: Optional configuration
        """
        self.liquidity_field = liquidity_field
        self.curvature_analyzer = curvature_analyzer
        self.config = config or CurvatureActionConfig()
    
    def compute(self,
               path: List[Dict],
               ict_structures: Dict,
               microstructure: Optional[Dict] = None) -> Dict[str, float]:
        """
        Compute curvature-aware liquidity cost for a path.
        
        Args:
            path: Path steps with 'price', 'timestamp', 'ofi', etc.
            ict_structures: ICT geometry
            microstructure: Optional microstructure
        
        Returns:
            Dict with base_cost, curvature_penalty, total_cost
        """
        # Compute base liquidity cost (from existing components)
        base_cost = self._compute_base_liquidity_cost(path, ict_structures, microstructure)
        
        # Compute curvature penalty
        curvature_penalty = self._compute_curvature_penalty(path, ict_structures, microstructure)
        
        # Total cost
        cfg = self.config
        total_cost = (
            cfg.base_liquidity_weight * base_cost +
            cfg.lambda_curvature * curvature_penalty
        )
        
        return {
            'base_liquidity_cost': base_cost,
            'curvature_penalty': curvature_penalty,
            'lambda_curvature': cfg.lambda_curvature,
            'total_cost': total_cost,
            'regime': self._dominant_regime(path, ict_structures, microstructure),
        }
    
    def _compute_base_liquidity_cost(self,
                                    path: List[Dict],
                                    ict_structures: Dict,
                                    microstructure: Optional[Dict]) -> float:
        """
        Compute base liquidity cost (flow-weighted, from existing system).
        
        This is the original S_L from upgraded_components.py.
        """
        from .upgraded_components import UpgradedActionComponents
        
        # Use existing action components
        action_comp = UpgradedActionComponents()
        
        # Compute S_L with microstructure
        s_l = action_comp.compute_s_liquidity(
            path,
            ict_structures.get('liquidity_zones', []),
            ict_structures.get('fvgs', [])
        )
        
        return s_l
    
    def _compute_curvature_penalty(self,
                                  path: List[Dict],
                                  ict_structures: Dict,
                                  microstructure: Optional[Dict]) -> float:
        """
        Compute curvature penalty: ∫ |K(γ(s))| ds
        
        High |K| regions are penalized because they represent:
        - Attractors (K>0): Trap price, prevent continuation
        - Saddles (K<0): Unstable, unpredictable
        """
        # Convert path to (price, timestamp) tuples
        path_points = [
            (step.get('price', 0.0), step.get('timestamp', 0.0))
            for step in path
        ]
        
        # Use curvature analyzer to compute path cost
        penalty = self.curvature_analyzer.path_curvature_cost(
            path_points,
            ict_structures,
            microstructure,
            lambda_curvature=1.0  # Will be weighted later
        )
        
        return penalty
    
    def _dominant_regime(self,
                        path: List[Dict],
                        ict_structures: Dict,
                        microstructure: Optional[Dict]) -> str:
        """
        Determine dominant curvature regime along path.
        
        Returns: 'basin', 'flat', 'saddle', or 'mixed'
        """
        # Get curvature data along path
        path_points = [
            (step.get('price', 0.0), step.get('timestamp', 0.0))
            for step in path
        ]
        
        curvature_data = self.curvature_analyzer.analyze_path(
            path_points, ict_structures, microstructure
        )
        
        # Count regimes
        regimes = [data.regime.value for data in curvature_data]
        
        # Find dominant regime
        from collections import Counter
        regime_counts = Counter(regimes)
        dominant = regime_counts.most_common(1)[0][0]
        
        # Check if mixed
        if len(set(regimes)) > 1 and max(regime_counts.values()) < len(regimes) * 0.6:
            return 'mixed'
        
        return dominant


def compute_curvature_aware_action(path: List[Dict],
                                 ict_structures: Dict,
                                 microstructure: Optional[Dict] = None,
                                 lambda_curvature: float = 0.5) -> Dict[str, float]:
    """
    Convenience function for curvature-aware liquidity cost.
    
    Args:
        path: Path steps
        ict_structures: ICT geometry
        microstructure: Optional microstructure
        lambda_curvature: Curvature penalty weight
    
    Returns:
        Dict with cost breakdown
    """
    from ..geometry import LiquidityField, CurvatureAnalyzer
    
    # Create components
    liquidity_field = LiquidityField()
    curvature_analyzer = CurvatureAnalyzer(liquidity_field)
    
    config = CurvatureActionConfig(lambda_curvature=lambda_curvature)
    
    # Create calculator and compute
    calculator = CurvatureAwareLiquidityCost(
        liquidity_field, curvature_analyzer, config
    )
    
    return calculator.compute(path, ict_structures, microstructure)


class CurvatureRegimeFilter:
    """
    Filter paths based on curvature regime.
    
    Can be used to:
    - Block paths through high-curvature regions
    - Prefer flat regions for trend continuation
    - Detect regime transitions
    """
    
    def __init__(self, max_curvature_magnitude: float = 0.1):
        self.max_curvature = max_curvature_magnitude
    
    def filter_paths(self,
                    paths: List[List[Dict]],
                    ict_structures: Dict,
                    curvature_analyzer) -> List[Tuple[List[Dict], str]]:
        """
        Filter and classify paths by curvature regime.
        
        Returns:
            List of (path, regime) tuples for acceptable paths
        """
        filtered = []
        
        for path in paths:
            # Analyze curvature along path
            path_points = [(p.get('price', 0), p.get('timestamp', 0)) for p in path]
            curvature_data = curvature_analyzer.analyze_path(path_points, ict_structures)
            
            # Check if path is acceptable
            max_K = max(data.magnitude for data in curvature_data)
            
            if max_K < self.max_curvature:
                # Determine dominant regime
                regimes = [d.regime.value for d in curvature_data]
                from collections import Counter
                dominant = Counter(regimes).most_common(1)[0][0]
                
                filtered.append((path, dominant))
        
        return filtered
