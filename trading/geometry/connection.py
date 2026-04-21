"""
connection.py - Christoffel symbols (connection coefficients).

Implements the Levi-Civita connection for the conformal metric.

For conformal metric g_ij = e^(2ϕ) δ_ij, the Christoffel symbols simplify to:

    Γ^i_jk = δ^i_k ∂_j ϕ + δ^i_j ∂_k ϕ - δ_jk ∂^i ϕ

In (p,t) coordinates, the key coefficients are:

    Γ^p_pp = ∂_p ϕ    (price curvature from price gradient)
    Γ^p_pt = ∂_t ϕ    (price curvature from time gradient)
    Γ^p_tt = -∂_p ϕ   (price acceleration from time flow)
    Γ^t_pp = -∂_t ϕ   (time shift from price movement)
    Γ^t_pt = ∂_p ϕ    (coupling term)
    Γ^t_tt = ∂_t ϕ    (time-phase bending)

These tell us how trajectories bend as they move through the liquidity field.
"""

import numpy as np
from typing import Tuple, Dict, Optional
from dataclasses import dataclass


@dataclass
class ChristoffelSymbols:
    """
    Christoffel symbols Γ^i_jk for 2D manifold (p,t).
    
    Indices:
        i = 0 for price (p)
        i = 1 for time (t)
    
    Stores 6 unique coefficients (symmetric in j,k):
        Γ^p_pp, Γ^p_pt, Γ^p_tt
        Γ^t_pp, Γ^t_pt, Γ^t_tt
    """
    # Price-indexed coefficients (i = p)
    G_p_pp: float  # Γ^p_pp
    G_p_pt: float  # Γ^p_pt
    G_p_tt: float  # Γ^p_tt
    
    # Time-indexed coefficients (i = t)
    G_t_pp: float  # Γ^t_pp
    G_t_pt: float  # Γ^t_pt
    G_t_tt: float  # Γ^t_tt
    
    @property
    def max_coefficient(self) -> float:
        """Maximum absolute Christoffel value (measures total curvature)"""
        return max(abs(self.G_p_pp), abs(self.G_p_pt), abs(self.G_p_tt),
                  abs(self.G_t_pp), abs(self.G_t_pt), abs(self.G_t_tt))
    
    @property
    def price_curvature(self) -> float:
        """
        Price-direction curvature magnitude.
        
        Computed from Γ^p_pp (spatial bending) and Γ^p_pt (temporal coupling).
        """
        return np.sqrt(self.G_p_pp ** 2 + self.G_p_pt ** 2)
    
    @property
    def time_curvature(self) -> float:
        """
        Time-direction curvature magnitude.
        
        Computed from Γ^t_tt (temporal bending) and Γ^t_pt (spatial coupling).
        """
        return np.sqrt(self.G_t_tt ** 2 + self.G_t_pt ** 2)
    
    def as_dict(self) -> Dict[str, float]:
        """Return as dictionary for serialization"""
        return {
            'G_p_pp': self.G_p_pp,
            'G_p_pt': self.G_p_pt,
            'G_p_tt': self.G_p_tt,
            'G_t_pp': self.G_t_pp,
            'G_t_pt': self.G_t_pt,
            'G_t_tt': self.G_t_tt,
        }


def compute_christoffel(d_phi_dp: float, d_phi_dt: float) -> ChristoffelSymbols:
    """
    Compute Christoffel symbols from liquidity field gradients.
    
    For conformal metric g_ij = e^(2ϕ) δ_ij:
    
        Γ^p_pp = ∂_p ϕ
        Γ^p_pt = ∂_t ϕ
        Γ^p_tt = -∂_p ϕ
        Γ^t_pp = -∂_t ϕ
        Γ^t_pt = ∂_p ϕ
        Γ^t_tt = ∂_t ϕ
    
    Args:
        d_phi_dp: ∂_p ϕ (price derivative of liquidity field)
        d_phi_dt: ∂_t ϕ (time derivative of liquidity field)
    
    Returns:
        ChristoffelSymbols with all 6 coefficients
    """
    return ChristoffelSymbols(
        G_p_pp=d_phi_dp,   # Price curvature from price gradient
        G_p_pt=d_phi_dt,   # Price curvature from time gradient
        G_p_tt=-d_phi_dp,  # Price acceleration from time flow
        G_t_pp=-d_phi_dt,  # Time shift from price movement
        G_t_pt=d_phi_dp,   # Coupling term
        G_t_tt=d_phi_dt    # Time-phase bending
    )


class ConnectionCalculator:
    """
    Calculator for Christoffel symbols at arbitrary points.
    
    Uses numerical differentiation to compute ∇ϕ, then derives Γ.
    """
    
    def __init__(self, liquidity_field):
        """
        Initialize with liquidity field calculator.
        
        Args:
            liquidity_field: LiquidityField instance
        """
        self.liquidity_field = liquidity_field
    
    def compute_at_point(self,
                        price: float,
                        timestamp: float,
                        ict_structures: dict,
                        microstructure: Optional[dict] = None) -> ChristoffelSymbols:
        """
        Compute Christoffel symbols at point (p,t).
        
        Args:
            price: Price coordinate
            timestamp: Time coordinate
            ict_structures: ICT geometry
            microstructure: Optional microstructure
        
        Returns:
            ChristoffelSymbols at the point
        """
        # Compute gradient ∇ϕ = (∂_p ϕ, ∂_t ϕ)
        d_phi_dp, d_phi_dt = self.liquidity_field.compute_gradient(
            price, timestamp, ict_structures, microstructure
        )
        
        return compute_christoffel(d_phi_dp, d_phi_dt)
    
    def compute_along_path(self,
                          path: list,
                          ict_structures: dict,
                          microstructure: Optional[dict] = None) -> list:
        """
        Compute Christoffel symbols along a price path.
        
        Args:
            path: List of (price, timestamp) tuples
            ict_structures: ICT geometry
            microstructure: Optional microstructure
        
        Returns:
            List of ChristoffelSymbols along the path
        """
        return [
            self.compute_at_point(p, t, ict_structures, microstructure)
            for p, t in path
        ]


def interpret_christoffel(G: ChristoffelSymbols) -> str:
    """
    Interpret Christoffel symbols in market terms.
    
    Args:
        G: ChristoffelSymbols
    
    Returns:
        String interpretation
    """
    interpretations = []
    
    # Price curvature analysis
    if abs(G.G_p_pp) > 0.1:
        direction = "inward" if G.G_p_pp > 0 else "outward"
        interpretations.append(f"Strong price-{direction} bending (Γ^p_pp={G.G_p_pp:.3f})")
    
    if abs(G.G_p_pt) > 0.1:
        interpretations.append(f"Time-induced price curvature (Γ^p_pt={G.G_p_pt:.3f})")
    
    if abs(G.G_p_tt) > 0.1:
        interpretations.append(f"Acceleration from time flow (Γ^p_tt={G.G_p_tt:.3f})")
    
    # Time curvature analysis
    if abs(G.G_t_tt) > 0.1:
        interpretations.append(f"Time-phase bending (Γ^t_tt={G.G_t_tt:.3f})")
    
    if abs(G.G_t_pt) > 0.1:
        interpretations.append(f"Price-time coupling (Γ^t_pt={G.G_t_pt:.3f})")
    
    if not interpretations:
        return "Locally flat (small Christoffel symbols)"
    
    return "; ".join(interpretations)
