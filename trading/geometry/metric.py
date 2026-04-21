"""
metric.py - Conformal metric tensor for market manifold.

Implements the liquidity-weighted metric:

    g_ij = e^(2ϕ) · δ_ij

    ds² = e^(2ϕ) (dp² + dt²)

Where:
    ϕ = liquidity field (from liquidity_field.py)
    e^(2ϕ) = conformal scale factor
    δ_ij = Kronecker delta (flat background metric)

Components:
    g_pp = e^(2ϕ)  (price resistance)
    g_tt = e^(2ϕ)  (time-phase resistance)
    g_pt = 0       (no price-time coupling in conformal model)

The metric encodes how "expensive" it is to move through the market.
"""

import numpy as np
from typing import Tuple, Optional
from dataclasses import dataclass


@dataclass
class MetricTensor:
    """
    2D metric tensor for market manifold (p,t).
    
    Stores components:
        g_pp: price-price component
        g_tt: time-time component
        g_pt: price-time coupling
    """
    g_pp: float
    g_tt: float
    g_pt: float
    
    @property
    def determinant(self) -> float:
        """Determinant of metric: det(g) = g_pp·g_tt - g_pt²"""
        return self.g_pp * self.g_tt - self.g_pt ** 2
    
    @property
    def as_matrix(self) -> np.ndarray:
        """Return as 2x2 numpy array"""
        return np.array([[self.g_pp, self.g_pt],
                        [self.g_pt, self.g_tt]])
    
    def compute_inverse(self) -> 'MetricTensor':
        """
        Compute inverse metric g^ij.
        
        For 2x2 matrix:
            g^ij = (1/det(g)) · [ g_tt  -g_pt]
                                [ -g_pt  g_pp]
        """
        det = self.determinant
        if abs(det) < 1e-12:
            raise ValueError(f"Metric determinant too small: {det}")
        
        inv_pp = self.g_tt / det
        inv_tt = self.g_pp / det
        inv_pt = -self.g_pt / det
        
        return MetricTensor(g_pp=inv_pp, g_tt=inv_tt, g_pt=inv_pt)


class ConformalMetric:
    """
    Conformal metric for market manifold.
    
    The metric is conformally flat:
        g_ij = e^(2ϕ) · δ_ij
    
    This means the market manifold is a conformal transformation of flat
    price-time space, where the scale factor depends on liquidity.
    
    Properties:
        - Simple Christoffel symbols (derivatives of ϕ only)
        - Gaussian curvature reduces to Laplacian of ϕ
        - Computationally tractable
    """
    
    def __init__(self, phi: float):
        """
        Initialize conformal metric from liquidity field ϕ.
        
        Args:
            phi: Liquidity field value at point (p,t)
        """
        self.phi = phi
        self.scale_factor = np.exp(2 * phi)
        
    def get_metric_tensor(self) -> MetricTensor:
        """
        Compute metric tensor g_ij.
        
        Returns:
            MetricTensor with g_pp = g_tt = e^(2ϕ), g_pt = 0
        """
        return MetricTensor(
            g_pp=self.scale_factor,
            g_tt=self.scale_factor,
            g_pt=0.0
        )
    
    def line_element(self, dp: float, dt: float) -> float:
        """
        Compute line element ds² = g_ij dx^i dx^j.
        
        For conformal metric:
            ds² = e^(2ϕ) (dp² + dt²)
        
        Args:
            dp: Price displacement
            dt: Time displacement
        
        Returns:
            Line element ds² (infinitesimal distance squared)
        """
        return self.scale_factor * (dp ** 2 + dt ** 2)
    
    def distance(self, dp: float, dt: float) -> float:
        """
        Compute distance ds = sqrt(ds²).
        
        This is the "effective cost" of moving from point A to point B
        in the market manifold.
        
        Args:
            dp: Price displacement
            dt: Time displacement
        
        Returns:
            Distance ds
        """
        return np.sqrt(self.line_element(dp, dt))
    
    def compute_from_liquidity_field(self,
                                     price: float,
                                     timestamp: float,
                                     ict_structures: dict,
                                     microstructure: Optional[dict] = None) -> MetricTensor:
        """
        Convenience method: compute metric directly from liquidity field.
        
        Args:
            price: Price coordinate
            timestamp: Time coordinate
            ict_structures: ICT geometry
            microstructure: Optional microstructure
        
        Returns:
            MetricTensor at point (p,t)
        """
        from .liquidity_field import compute_liquidity_field
        
        phi = compute_liquidity_field(price, timestamp, ict_structures, microstructure)
        conformal = ConformalMetric(phi)
        return conformal.get_metric_tensor()


def compute_metric(phi: float) -> MetricTensor:
    """
    Convenience function: compute conformal metric from liquidity field.
    
    Args:
        phi: Liquidity field value
    
    Returns:
        MetricTensor g_ij
    """
    conformal = ConformalMetric(phi)
    return conformal.get_metric_tensor()
