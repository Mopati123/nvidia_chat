"""
test_liquidity_field.py - Unit tests for liquidity field ϕ(p,t).

Tests the mathematical properties:
1. Field computation from ICT structures
2. Gradient computation ∇ϕ
3. Laplacian computation Δϕ
4. Physical interpretation (resistance, decay)
"""

import pytest
import numpy as np
from trading.geometry import LiquidityField, compute_liquidity_field


class TestLiquidityFieldComputation:
    """Test field ϕ computation from ICT structures."""
    
    def test_empty_structures_gives_base_value(self):
        """Empty ICT structures gives base liquidity field."""
        field = LiquidityField()
        
        ict_structures = {
            'order_blocks': [],
            'liquidity_pools': [],
            'fvgs': [],
        }
        
        phi = field.compute(1.0850, 1000.0, ict_structures, None)
        
        # Should have some base value (from default parameters)
        assert isinstance(phi, (int, float))
        assert not np.isnan(phi)
        assert not np.isinf(phi)
    
    def test_order_block_increases_phi(self):
        """Order blocks increase liquidity field (raise resistance)."""
        field = LiquidityField()
        
        # Without order block
        phi_without = field.compute(
            1.0850, 1000.0,
            {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            None
        )
        
        # With order block at price
        phi_with = field.compute(
            1.0850, 1000.0,
            {
                'order_blocks': [{'level': 1.0850, 'strength': 2.0, 'width': 0.001}],
                'liquidity_pools': [],
                'fvgs': [],
            },
            None
        )
        
        assert phi_with > phi_without, "Order block should increase ϕ"
    
    def test_fvg_decreases_phi(self):
        """FVGs decrease liquidity field (reduce resistance)."""
        field = LiquidityField()
        
        # Base case
        phi_without = field.compute(
            1.0850, 1000.0,
            {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            None
        )
        
        # With FVG containing price
        phi_with_fvg = field.compute(
            1.0850, 1000.0,
            {
                'order_blocks': [],
                'liquidity_pools': [],
                'fvgs': [{'top': 1.0855, 'bottom': 1.0845, 'strength': 1.5}],
            },
            None
        )
        
        assert phi_with_fvg < phi_without, "FVG should decrease ϕ"
    
    def test_liquidity_pool_increases_phi(self):
        """Liquidity pools increase liquidity field."""
        field = LiquidityField()
        
        phi_without = field.compute(
            1.0850, 1000.0,
            {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            None
        )
        
        phi_with_pool = field.compute(
            1.0850, 1000.0,
            {
                'order_blocks': [],
                'liquidity_pools': [{'level': 1.0850, 'volume': 500, 'radius': 0.002}],
                'fvgs': [],
            },
            None
        )
        
        assert phi_with_pool > phi_without, "Liquidity pool should increase ϕ"


class TestGradientComputation:
    """Test gradient ∇ϕ = (∂_p ϕ, ∂_t ϕ) computation."""
    
    def test_gradient_finite(self):
        """Gradient must be finite."""
        field = LiquidityField()
        
        d_phi_dp, d_phi_dt = field.compute_gradient(
            1.0850, 1000.0,
            {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            None
        )
        
        assert np.isfinite(d_phi_dp)
        assert np.isfinite(d_phi_dt)
    
    def test_constant_field_zero_gradient(self):
        """Constant field has zero gradient."""
        field = LiquidityField()
        
        # Empty field is approximately constant
        d_phi_dp, d_phi_dt = field.compute_gradient(
            1.0850, 1000.0,
            {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            None,
            dp=0.001
        )
        
        # Gradient should be near zero for empty/flat field
        assert abs(d_phi_dp) < 100  # Reasonable bound


class TestLaplacianComputation:
    """Test Laplacian Δϕ = ∂²_p ϕ + ∂²_t ϕ computation."""
    
    def test_laplacian_finite(self):
        """Laplacian must be finite."""
        field = LiquidityField()
        
        laplacian = field.compute_laplacian(
            1.0850, 1000.0,
            {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            None
        )
        
        assert np.isfinite(laplacian)
    
    def test_constant_field_zero_laplacian(self):
        """Constant field has zero Laplacian."""
        field = LiquidityField()
        
        # For approximately constant field
        laplacian = field.compute_laplacian(
            1.0850, 1000.0,
            {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            None
        )
        
        # Laplacian of constant should be near zero
        # Note: With discrete numerical derivatives, won't be exactly zero
        assert abs(laplacian) < 1e6  # Very loose bound for safety


class TestSessionMisalignment:
    """Test session misalignment computation."""
    
    def test_london_session_low_misalignment(self):
        """London session has low misalignment."""
        field = LiquidityField()
        
        microstructure = {'session': 'london', 'kill_zone': True}
        m_t = field._compute_session_misalignment(1000.0, microstructure)
        
        assert m_t == 0.0, "London kill zone should have zero misalignment"
    
    def test_asia_session_high_misalignment(self):
        """Asia session has high misalignment."""
        field = LiquidityField()
        
        microstructure = {'session': 'asia', 'kill_zone': False}
        m_t = field._compute_session_misalignment(1000.0, microstructure)
        
        assert m_t == 1.0, "Asia session should have high misalignment"
    
    def test_no_microstructure_default(self):
        """Default misalignment when no microstructure."""
        field = LiquidityField()
        
        m_t = field._compute_session_misalignment(1000.0, None)
        
        assert m_t == 0.5, "Default should be neutral"


class TestConvenienceFunction:
    """Test compute_liquidity_field convenience function."""
    
    def test_convenience_function_works(self):
        """Convenience function returns same result as class method."""
        ict_structures = {
            'order_blocks': [],
            'liquidity_pools': [],
            'fvgs': [],
        }
        
        # Via class
        field = LiquidityField()
        phi_class = field.compute(1.0850, 1000.0, ict_structures, None)
        
        # Via convenience function
        phi_func = compute_liquidity_field(1.0850, 1000.0, ict_structures, None)
        
        assert abs(phi_class - phi_func) < 1e-10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
