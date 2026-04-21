"""
test_curvature.py - Unit tests for Gaussian curvature.

Tests the mathematical properties of curvature:
1. K = -e^(-2ϕ) Δϕ (defining equation)
2. Sign interpretation (basin/flat/saddle)
3. Constant ϕ implies K = 0
4. Laplacian relation
"""

import pytest
import numpy as np
from trading.geometry import gaussian_curvature, CurvatureAnalyzer, CurvatureRegime, classify_regime
from trading.geometry.liquidity_field import LiquidityField


class TestGaussianCurvatureEquation:
    """Test 2.3.2: K = -e^(-2ϕ) Δϕ."""
    
    def test_curvature_laplacian_relation(self):
        """Curvature must satisfy defining equation exactly."""
        test_cases = [
            (0.0, 1.0),    # phi=0, laplacian=1
            (0.5, 2.0),    # phi=0.5, laplacian=2
            (1.0, -1.0),   # phi=1, laplacian=-1
        ]
        
        for phi, laplacian in test_cases:
            K_computed = gaussian_curvature(phi, laplacian)
            K_expected = -np.exp(-2 * phi) * laplacian
            
            assert abs(K_computed - K_expected) < 1e-10, \
                f"K computed = {K_computed}, expected = {K_expected}"
    
    def test_curvature_scale_factor(self):
        """K scales with e^(-2ϕ)."""
        laplacian = 1.0
        
        for phi in [0.0, 0.5, 1.0, 2.0]:
            K = gaussian_curvature(phi, laplacian)
            scale = np.exp(-2 * phi)
            
            # K = -scale * laplacian
            expected = -scale * laplacian
            assert abs(K - expected) < 1e-10


class TestConstantPhiZeroCurvature:
    """Test 2.3.3: Constant ϕ implies K = 0."""
    
    def test_constant_phi_zero_laplacian(self):
        """If ϕ is constant, Δϕ = 0, therefore K = 0."""
        phi = 0.5
        laplacian = 0.0  # ∇²(constant) = 0
        
        K = gaussian_curvature(phi, laplacian)
        assert abs(K) < 1e-10, f"K must be zero for constant ϕ, got {K}"
    
    def test_zero_phi_zero_laplacian(self):
        """ϕ = 0, Δϕ = 0 → K = 0."""
        K = gaussian_curvature(phi=0.0, laplacian_phi=0.0)
        assert abs(K) < 1e-10


class TestCurvatureSignInterpretation:
    """Test 2.3.1: Sign of K matches geometric regime."""
    
    def test_positive_curvature_is_basin(self):
        """K > 0 → BASIN (attractor, mean-reversion)."""
        regime = classify_regime(0.1, threshold=0.01)
        assert regime == CurvatureRegime.BASIN
        
        regime = classify_regime(1.0, threshold=0.01)
        assert regime == CurvatureRegime.BASIN
    
    def test_negative_curvature_is_saddle(self):
        """K < 0 → SADDLE (instability, breakout)."""
        regime = classify_regime(-0.1, threshold=0.01)
        assert regime == CurvatureRegime.SADDLE
        
        regime = classify_regime(-1.0, threshold=0.01)
        assert regime == CurvatureRegime.SADDLE
    
    def test_near_zero_curvature_is_flat(self):
        """|K| < threshold → FLAT (continuation)."""
        regime = classify_regime(0.005, threshold=0.01)
        assert regime == CurvatureRegime.FLAT
        
        regime = classify_regime(-0.005, threshold=0.01)
        assert regime == CurvatureRegime.FLAT
        
        regime = classify_regime(0.0, threshold=0.01)
        assert regime == CurvatureRegime.FLAT
    
    def test_threshold_boundary(self):
        """Test at exact threshold boundary."""
        threshold = 0.01
        
        # Exactly at threshold should be flat (|K| = threshold)
        regime = classify_regime(threshold, threshold)
        assert regime == CurvatureRegime.FLAT
        
        # Just above threshold should be basin
        regime = classify_regime(threshold + 0.001, threshold)
        assert regime == CurvatureRegime.BASIN
        
        # Just below negative threshold should be saddle
        regime = classify_regime(-threshold - 0.001, threshold)
        assert regime == CurvatureRegime.SADDLE


class TestCurvatureAnalyzer:
    """Test CurvatureAnalyzer integration with liquidity field."""
    
    def test_analyzer_returns_curvature_data(self):
        """Analyzer returns complete curvature information."""
        field = LiquidityField()
        analyzer = CurvatureAnalyzer(field)
        
        ict_structures = {
            'order_blocks': [],
            'liquidity_pools': [],
            'fvgs': [],
        }
        
        data = analyzer.analyze_point(
            price=1.0850,
            timestamp=1000.0,
            ict_structures=ict_structures,
            microstructure=None
        )
        
        # Check all fields exist
        assert hasattr(data, 'gaussian_curvature')
        assert hasattr(data, 'regime')
        assert hasattr(data, 'magnitude')
        assert hasattr(data, 'stability')
        
        # Check types
        assert isinstance(data.gaussian_curvature, (int, float))
        assert isinstance(data.regime, CurvatureRegime)
        assert data.magnitude >= 0
        assert 0 <= data.stability <= 1
    
    def test_curvature_data_serialization(self):
        """Curvature data can be serialized to dict."""
        field = LiquidityField()
        analyzer = CurvatureAnalyzer(field)
        
        data = analyzer.analyze_point(
            price=1.0850,
            timestamp=1000.0,
            ict_structures={'order_blocks': [], 'liquidity_pools': [], 'fvgs': []},
            microstructure=None
        )
        
        d = data.to_dict()
        assert 'gaussian_curvature' in d
        assert 'regime' in d
        assert 'magnitude' in d
        assert 'stability' in d
    
    def test_path_analysis(self):
        """Analyze curvature along a path."""
        field = LiquidityField()
        analyzer = CurvatureAnalyzer(field)
        
        path = [(1.0850 + i*0.0001, 1000 + i*60) for i in range(5)]
        ict_structures = {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []}
        
        results = analyzer.analyze_path(path, ict_structures)
        
        assert len(results) == len(path)
        for data in results:
            assert isinstance(data.regime, CurvatureRegime)
            assert data.magnitude >= 0


class TestCurvatureCostComputation:
    """Test curvature penalty cost for paths."""
    
    def test_path_curvature_cost_non_negative(self):
        """Path curvature cost must be ≥ 0."""
        field = LiquidityField()
        analyzer = CurvatureAnalyzer(field)
        
        path = [(1.0850, 1000), (1.0851, 1060), (1.0852, 1120)]
        ict_structures = {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []}
        
        cost = analyzer.path_curvature_cost(path, ict_structures, None, lambda_curvature=0.5)
        
        assert cost >= 0, f"Curvature cost must be non-negative, got {cost}"
    
    def test_curvature_cost_scales_with_lambda(self):
        """Cost scales linearly with λ_K."""
        field = LiquidityField()
        analyzer = CurvatureAnalyzer(field)
        
        path = [(1.0850, 1000), (1.0851, 1060)]
        ict_structures = {'order_blocks': [], 'liquidity_pools': [], 'fvgs': []}
        
        cost_05 = analyzer.path_curvature_cost(path, ict_structures, None, 0.5)
        cost_10 = analyzer.path_curvature_cost(path, ict_structures, None, 1.0)
        
        # Should be exactly 2x
        assert abs(cost_10 - 2*cost_05) < 1e-10


class TestCurvatureAnomalyDetection:
    """Test detection of rapid curvature changes."""
    
    def test_anomaly_detection(self):
        """Detect rapid curvature changes along path."""
        field = LiquidityField()
        analyzer = CurvatureAnalyzer(field)
        
        # Create path data with varying curvature
        path_data = []
        for i in range(10):
            # Simulate varying curvature
            K = 0.01 if i < 5 else 0.1  # Sudden jump at i=5
            data = type('obj', (object,), {
                'gaussian_curvature': K,
                'magnitude': abs(K),
                'regime': CurvatureRegime.BASIN if K > 0 else CurvatureRegime.FLAT
            })()
            path_data.append(data)
        
        anomalies = analyzer.detect_curvature_anomalies(path_data, window=3)
        
        # Should detect the jump around index 5
        assert len(anomalies) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
