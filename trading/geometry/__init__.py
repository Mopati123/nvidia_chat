"""
geometry package - Riemannian market manifold.

Implements differential-geometric market model:
- Liquidity field ϕ(p,t) - resistance potential
- Conformal metric g_ij = e^(2ϕ) δ_ij
- Christoffel symbols Γ^i_jk - connection coefficients
- Gaussian curvature K - regime classifier
- Geodesic integration - trajectory prediction

Transforms ICT patterns into rigorous differential geometry.
"""

from .liquidity_field import LiquidityField, compute_liquidity_field
from .metric import ConformalMetric, MetricTensor
from .connection import ChristoffelSymbols, compute_christoffel, ChristoffelProvider
from .curvature import gaussian_curvature, CurvatureAnalyzer, CurvatureRegime, classify_regime, CurvatureData
from .geodesic import GeodesicIntegrator, integrate_geodesic, GeodesicState

__all__ = [
    'LiquidityField',
    'compute_liquidity_field',
    'ConformalMetric',
    'MetricTensor',
    'ChristoffelSymbols',
    'compute_christoffel',
    'ChristoffelProvider',
    'gaussian_curvature',
    'CurvatureAnalyzer',
    'CurvatureRegime',
    'classify_regime',
    'CurvatureData',
    'GeodesicIntegrator',
    'integrate_geodesic',
    'GeodesicState',
]
