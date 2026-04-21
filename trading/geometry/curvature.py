"""
curvature.py - Gaussian curvature for market manifold.

Implements Gaussian curvature K for conformal metric:

    K = -e^(-2ϕ) · Δϕ

Where:
    ϕ = liquidity field
    Δϕ = ∂²_p ϕ + ∂²_t ϕ (Laplacian)
    e^(-2ϕ) = inverse conformal factor

Interpretation of K:
    K > 0: Basin/attractor (mean-reversion, liquidity pools)
    K ≈ 0: Flat (continuation, trend channels)
    K < 0: Saddle/breakout (instability, regime shift)

This is the key regime classifier in the geometric framework.
"""

import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class CurvatureRegime(Enum):
    """Market regime based on Gaussian curvature"""
    BASIN = "basin"           # K > 0: attractor, mean-reversion
    FLAT = "flat"             # K ≈ 0: continuation, trend
    SADDLE = "saddle"         # K < 0: breakout, instability
    TRANSITION = "transition" # Rapid curvature change


@dataclass
class CurvatureData:
    """Complete curvature information at a point"""
    gaussian_curvature: float  # K
    mean_curvature: float     # H (optional)
    regime: CurvatureRegime
    magnitude: float          # |K|
    stability: float          # 1 / (1 + |K|) - inverse of curvature strength
    
    def to_dict(self) -> dict:
        return {
            'gaussian_curvature': self.gaussian_curvature,
            'mean_curvature': self.mean_curvature,
            'regime': self.regime.value,
            'magnitude': self.magnitude,
            'stability': self.stability,
        }


def gaussian_curvature(phi: float, laplacian_phi: float) -> float:
    """
    Compute Gaussian curvature K for conformal metric.
    
    For conformal metric g_ij = e^(2ϕ) δ_ij:
        K = -e^(-2ϕ) · Δϕ
    
    Args:
        phi: Liquidity field value
        laplacian_phi: Laplacian of ϕ (Δϕ = ∂²_p ϕ + ∂²_t ϕ)
    
    Returns:
        Gaussian curvature K
    """
    scale_factor_inv = np.exp(-2 * phi)
    K = -scale_factor_inv * laplacian_phi
    return K


def classify_regime(K: float, threshold: float = 0.01) -> CurvatureRegime:
    """
    Classify market regime from Gaussian curvature.
    
    Classification:
        K > threshold: BASIN (attractor, mean-reversion)
        |K| < threshold: FLAT (continuation, trend)
        K < -threshold: SADDLE (breakout, instability)
    
    Args:
        K: Gaussian curvature
        threshold: Classification threshold
    
    Returns:
        CurvatureRegime enum
    """
    if K > threshold:
        return CurvatureRegime.BASIN
    elif K < -threshold:
        return CurvatureRegime.SADDLE
    else:
        return CurvatureRegime.FLAT


class CurvatureAnalyzer:
    """
    Analyzer for market curvature along paths and regions.
    
    Computes curvature from liquidity field and classifies regimes.
    """
    
    def __init__(self, liquidity_field, threshold: float = 0.01):
        """
        Initialize curvature analyzer.
        
        Args:
            liquidity_field: LiquidityField instance
            threshold: Regime classification threshold
        """
        self.liquidity_field = liquidity_field
        self.threshold = threshold
    
    def analyze_point(self,
                     price: float,
                     timestamp: float,
                     ict_structures: dict,
                     microstructure: Optional[dict] = None) -> CurvatureData:
        """
        Compute complete curvature analysis at point (p,t).
        
        Args:
            price: Price coordinate
            timestamp: Time coordinate
            ict_structures: ICT geometry
            microstructure: Optional microstructure
        
        Returns:
            CurvatureData with K, regime, and interpretation
        """
        # Compute liquidity field
        phi = self.liquidity_field.compute(price, timestamp, ict_structures, microstructure)
        
        # Compute Laplacian Δϕ
        laplacian = self.liquidity_field.compute_laplacian(
            price, timestamp, ict_structures, microstructure
        )
        
        # Compute Gaussian curvature
        K = gaussian_curvature(phi, laplacian)
        
        # Classify regime
        regime = classify_regime(K, self.threshold)
        
        # Compute derived quantities
        magnitude = abs(K)
        stability = 1.0 / (1.0 + magnitude)
        
        return CurvatureData(
            gaussian_curvature=K,
            mean_curvature=0.0,  # Could add if needed
            regime=regime,
            magnitude=magnitude,
            stability=stability
        )
    
    def analyze_path(self,
                    path: list,
                    ict_structures: dict,
                    microstructure: Optional[dict] = None) -> list:
        """
        Analyze curvature along a price path.
        
        Args:
            path: List of (price, timestamp) tuples
            ict_structures: ICT geometry
            microstructure: Optional microstructure
        
        Returns:
            List of CurvatureData along path
        """
        return [
            self.analyze_point(p, t, ict_structures, microstructure)
            for p, t in path
        ]
    
    def detect_curvature_anomalies(self,
                                   path_data: list,
                                   window: int = 5) -> list:
        """
        Detect rapid curvature changes (anomalies/regime shifts).
        
        Args:
            path_data: List of CurvatureData
            window: Window size for change detection
        
        Returns:
            List of (index, curvature_change) tuples
        """
        anomalies = []
        
        for i in range(window, len(path_data)):
            # Compute curvature change over window
            K_current = path_data[i].gaussian_curvature
            K_past = path_data[i - window].gaussian_curvature
            
            change = abs(K_current - K_past)
            
            # Flag as anomaly if change is large
            if change > 0.05:  # Threshold for significant change
                anomalies.append((i, change))
        
        return anomalies
    
    def path_curvature_cost(self,
                           path: list,
                           ict_structures: dict,
                           microstructure: Optional[dict] = None,
                           lambda_curvature: float = 0.5) -> float:
        """
        Compute curvature penalty cost for a path.
        
        Used in action functional:
            S_L_curvature = ∫ |K(γ(s))| ds
        
        Args:
            path: List of (price, timestamp) points
            ict_structures: ICT geometry
            microstructure: Optional microstructure
            lambda_curvature: Weight for curvature penalty
        
        Returns:
            Integrated curvature penalty
        """
        curvature_data = self.analyze_path(path, ict_structures, microstructure)
        
        # Sum absolute curvature along path
        total_curvature = sum(data.magnitude for data in curvature_data)
        
        # Average per point
        avg_curvature = total_curvature / len(curvature_data) if curvature_data else 0.0
        
        # Apply weight
        cost = lambda_curvature * avg_curvature
        
        return cost


def interpret_curvature(K: float) -> str:
    """
    Provide market interpretation of Gaussian curvature value.
    
    Args:
        K: Gaussian curvature
    
    Returns:
        String interpretation
    """
    if K > 0.05:
        return f"BASIN (K={K:.4f}): Attractor zone, mean-reversion likely, liquidity pool"
    elif K > 0.01:
        return f"WEAK BASIN (K={K:.4f}): Mild attraction, some containment"
    elif K < -0.05:
        return f"SADDLE (K={K:.4f}): Instability, breakout geometry, regime shift"
    elif K < -0.01:
        return f"WEAK SADDLE (K={K:.4f}): Mild instability, approaching transition"
    else:
        return f"FLAT (K={K:.4f}): Continuation geometry, trend-friendly"


def compute_curvature_regime_transition_probability(
    K_history: list,
    window: int = 10
) -> float:
    """
    Estimate probability of imminent regime transition.
    
    Based on curvature volatility and trend.
    
    Args:
        K_history: List of recent Gaussian curvature values
        window: Analysis window
    
    Returns:
        Transition probability [0, 1]
    """
    if len(K_history) < window:
        return 0.0
    
    recent = K_history[-window:]
    
    # Compute curvature volatility
    volatility = np.std(recent)
    
    # Compute curvature trend (increasing = approaching transition)
    trend = np.polyfit(range(len(recent)), recent, 1)[0]
    
    # Transition probability increases with:
    # - High volatility (unstable)
    # - Strong trend (moving toward boundary)
    # - Near-zero crossing (transition zone)
    
    prob_volatility = min(volatility * 10, 0.5)  # Cap at 0.5
    prob_trend = min(abs(trend) * 100, 0.3)  # Cap at 0.3
    
    # Check if near zero (transition zone)
    current_K = recent[-1]
    near_zero = abs(current_K) < 0.02
    prob_zone = 0.2 if near_zero else 0.0
    
    # Combined probability
    total_prob = min(prob_volatility + prob_trend + prob_zone, 1.0)
    
    return total_prob
