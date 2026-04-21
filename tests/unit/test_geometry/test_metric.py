"""
test_metric.py - Unit tests for conformal metric tensor.

Tests the mathematical properties of the metric:
1. Positivity: g_pp > 0, g_tt > 0, det(g) > 0
2. Inverse consistency: g · g^-1 = I
3. Scale factor: g = e^(2ϕ) δ_ij
4. Conformal structure: g_pp = g_tt, g_pt = 0
"""

import pytest
import numpy as np
from trading.geometry import ConformalMetric, MetricTensor


class TestMetricPositivity:
    """Test 2.1.1: Metric must be positive definite."""
    
    def test_metric_components_positive(self):
        """g_pp > 0 and g_tt > 0 for all finite ϕ."""
        for phi in [-1.0, 0.0, 0.5, 1.0, 2.0]:
            metric = ConformalMetric(phi)
            g = metric.get_metric_tensor()
            
            assert g.g_pp > 0, f"g_pp must be positive for ϕ={phi}"
            assert g.g_tt > 0, f"g_tt must be positive for ϕ={phi}"
    
    def test_metric_determinant_positive(self):
        """det(g) > 0 for positive definite metric."""
        for phi in [-1.0, 0.0, 0.5, 1.0, 2.0]:
            metric = ConformalMetric(phi)
            g = metric.get_metric_tensor()
            
            assert g.determinant > 0, f"det(g) must be positive for ϕ={phi}"
    
    def test_conformal_structure(self):
        """Conformal metric has g_pp = g_tt and g_pt = 0."""
        metric = ConformalMetric(phi=0.5)
        g = metric.get_metric_tensor()
        
        assert g.g_pp == g.g_tt, "g_pp must equal g_tt in conformal metric"
        assert g.g_pt == 0.0, "g_pt must be zero in conformal metric"


class TestMetricInverseConsistency:
    """Test 2.1.2: g · g^-1 = I (identity matrix)."""
    
    def test_inverse_exists(self):
        """Inverse must exist for non-singular metric."""
        metric = ConformalMetric(phi=0.5)
        g = metric.get_metric_tensor()
        
        g_inv = g.compute_inverse()
        
        assert isinstance(g_inv, MetricTensor)
        assert g_inv.g_pp > 0
        assert g_inv.g_tt > 0
    
    def test_metric_inverse_product(self):
        """g · g^-1 should equal identity matrix."""
        for phi in [0.0, 0.5, 1.0, 2.0]:
            metric = ConformalMetric(phi)
            g = metric.get_metric_tensor()
            g_inv = g.compute_inverse()
            
            # Compute matrix product
            product_pp = g.g_pp * g_inv.g_pp + g.g_pt * g_inv.g_pt
            product_pt = g.g_pp * g_inv.g_pt + g.g_pt * g_inv.g_tt
            product_tp = g.g_pt * g_inv.g_pp + g.g_tt * g_inv.g_pt
            product_tt = g.g_pt * g_inv.g_pt + g.g_tt * g_inv.g_tt
            
            # Should equal identity [1, 0; 0, 1]
            assert abs(product_pp - 1.0) < 1e-10, f"(g·g^-1)_pp ≠ 1 for ϕ={phi}"
            assert abs(product_tt - 1.0) < 1e-10, f"(g·g^-1)_tt ≠ 1 for ϕ={phi}"
            assert abs(product_pt) < 1e-10, f"(g·g^-1)_pt ≠ 0 for ϕ={phi}"
            assert abs(product_tp) < 1e-10, f"(g·g^-1)_tp ≠ 0 for ϕ={phi}"


class TestScaleFactorExponential:
    """Test 2.1.3: Scale factor e^(2ϕ) properties."""
    
    def test_scale_factor_monotonic(self):
        """Higher ϕ → higher metric components."""
        phis = [0.0, 0.1, 0.5, 1.0, 2.0]
        metrics = [ConformalMetric(phi) for phi in phis]
        g_values = [m.get_metric_tensor().g_pp for m in metrics]
        
        # Should be strictly increasing
        for i in range(len(g_values) - 1):
            assert g_values[i] < g_values[i+1], \
                f"g_pp not monotonic: {g_values[i]} >= {g_values[i+1]}"
    
    def test_scale_factor_exponential_form(self):
        """g_pp = e^(2ϕ) exactly."""
        for phi in [0.0, 0.1, 0.5, 1.0, 2.0]:
            metric = ConformalMetric(phi)
            g = metric.get_metric_tensor()
            
            expected = np.exp(2 * phi)
            assert abs(g.g_pp - expected) < 1e-10, \
                f"g_pp = {g.g_pp} ≠ e^(2·{phi}) = {expected}"
    
    def test_zero_phi_gives_identity(self):
        """ϕ = 0 → g = I (identity matrix)."""
        metric = ConformalMetric(phi=0.0)
        g = metric.get_metric_tensor()
        
        assert abs(g.g_pp - 1.0) < 1e-10
        assert abs(g.g_tt - 1.0) < 1e-10
        assert abs(g.g_pt) < 1e-10
        assert abs(g.determinant - 1.0) < 1e-10


class TestLineElement:
    """Test line element ds² = g_ij dx^i dx^j."""
    
    def test_line_element_positive(self):
        """ds² ≥ 0 for all displacements."""
        metric = ConformalMetric(phi=0.5)
        
        # Test various displacements
        for dp in [0.0, 0.001, -0.001, 0.01]:
            for dt in [0, 60, -60, 300]:
                ds_sq = metric.line_element(dp, dt)
                assert ds_sq >= 0, f"ds² must be non-negative, got {ds_sq}"
    
    def test_line_element_conformal(self):
        """For conformal metric: ds² = e^(2ϕ)(dp² + dt²)."""
        phi = 0.5
        metric = ConformalMetric(phi)
        
        dp, dt = 0.001, 60.0
        ds_sq = metric.line_element(dp, dt)
        
        expected = np.exp(2 * phi) * (dp**2 + dt**2)
        assert abs(ds_sq - expected) < 1e-10
    
    def test_zero_displacement_zero_length(self):
        """ds = 0 when dp = dt = 0."""
        metric = ConformalMetric(phi=0.5)
        
        ds_sq = metric.line_element(0.0, 0.0)
        assert ds_sq == 0.0
        
        ds = metric.distance(0.0, 0.0)
        assert ds == 0.0


class TestMetricTensorDataclass:
    """Test MetricTensor dataclass functionality."""
    
    def test_as_matrix(self):
        """as_matrix returns correct 2x2 array."""
        g = MetricTensor(g_pp=2.0, g_tt=3.0, g_pt=0.5)
        matrix = g.as_matrix
        
        assert matrix.shape == (2, 2)
        assert matrix[0, 0] == 2.0
        assert matrix[1, 1] == 3.0
        assert matrix[0, 1] == 0.5
        assert matrix[1, 0] == 0.5
    
    def test_determinant_calculation(self):
        """Determinant computed correctly: det = g_pp·g_tt - g_pt²."""
        g = MetricTensor(g_pp=4.0, g_tt=9.0, g_pt=2.0)
        
        expected_det = 4.0 * 9.0 - 2.0**2  # 36 - 4 = 32
        assert g.determinant == expected_det


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
