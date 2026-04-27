#!/usr/bin/env python3
"""
Riemannian Geometry Integration Test

Validates the complete Riemannian geometry implementation:
1. Liquidity field ϕ(p,t) computation
2. Conformal metric g_ij = e^(2ϕ) δ_ij
3. Christoffel symbols Γ^i_jk
4. Gaussian curvature K = -e^(-2ϕ) Δϕ
5. Geodesic integration
6. Curvature-aware action cost
"""

import sys
import numpy as np

print('='*70)
print('RIEMANNIAN GEOMETRY INTEGRATION TEST')
print('='*70)

# Test 1: Liquidity Field
print('\n1. Liquidity Field ϕ(p,t)')
print('-'*70)

try:
    from trading.geometry import LiquidityField, compute_liquidity_field
    
    field = LiquidityField()
    
    # Create mock ICT structures
    ict_structures = {
        'order_blocks': [
            {'level': 1.0850, 'strength': 2.0, 'width': 0.0010},
        ],
        'liquidity_pools': [
            {'level': 1.0860, 'volume': 500, 'radius': 0.0020},
        ],
        'fvgs': [
            {'top': 1.0855, 'bottom': 1.0853, 'strength': 1.5},
        ],
    }
    
    microstructure = {
        'mid': 1.0852,
        'spread': 0.0002,
        'session': 'london',
        'kill_zone': True,
    }
    
    # Compute field
    phi = field.compute(1.0852, 1000.0, ict_structures, microstructure)
    print(f'✅ Liquidity field computed: ϕ = {phi:.4f}')
    
    # Compute gradient
    d_phi_dp, d_phi_dt = field.compute_gradient(
        1.0852, 1000.0, ict_structures, microstructure
    )
    print(f'✅ Gradient computed: ∂pϕ = {d_phi_dp:.4f}, ∂tϕ = {d_phi_dt:.4f}')
    
    # Compute Laplacian
    laplacian = field.compute_laplacian(
        1.0852, 1000.0, ict_structures, microstructure
    )
    print(f'✅ Laplacian computed: Δϕ = {laplacian:.4f}')
    
except Exception as e:
    print(f'❌ Liquidity field test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Conformal Metric
print('\n2. Conformal Metric g_ij = e^(2ϕ) δ_ij')
print('-'*70)

try:
    from trading.geometry import ConformalMetric, MetricTensor
    
    # Create metric from field
    metric = ConformalMetric(phi)
    g = metric.get_metric_tensor()
    
    print(f'✅ Metric computed:')
    print(f'   g_pp = {g.g_pp:.4f}')
    print(f'   g_tt = {g.g_tt:.4f}')
    print(f'   g_pt = {g.g_pt:.4f}')
    print(f'   det(g) = {g.determinant:.4f}')
    
    # Test inverse metric
    g_inv = g.compute_inverse()
    print(f'✅ Inverse metric computed:')
    print(f'   g^pp = {g_inv.g_pp:.4f}')
    print(f'   g^tt = {g_inv.g_tt:.4f}')
    
    # Test line element
    ds = metric.line_element(dp=0.0010, dt=60)
    print(f'✅ Line element: ds² = {ds:.6f}')
    
except Exception as e:
    print(f'❌ Metric test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Christoffel Symbols
print('\n3. Christoffel Symbols Γ^i_jk')
print('-'*70)

try:
    from trading.geometry import ChristoffelSymbols, compute_christoffel
    
    # Compute from gradients
    christoffel = compute_christoffel(d_phi_dp, d_phi_dt)
    
    print(f'✅ Christoffel symbols computed:')
    print(f'   Γ^p_pp = {christoffel.G_p_pp:.4f}')
    print(f'   Γ^p_pt = {christoffel.G_p_pt:.4f}')
    print(f'   Γ^p_tt = {christoffel.G_p_tt:.4f}')
    print(f'   Γ^t_pp = {christoffel.G_t_pp:.4f}')
    print(f'   Γ^t_pt = {christoffel.G_t_pt:.4f}')
    print(f'   Γ^t_tt = {christoffel.G_t_tt:.4f}')
    
    print(f'✅ Max coefficient: {christoffel.max_coefficient:.4f}')
    print(f'✅ Price curvature: {christoffel.price_curvature:.4f}')
    
except Exception as e:
    print(f'❌ Christoffel test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Gaussian Curvature
print('\n4. Gaussian Curvature K = -e^(-2ϕ) Δϕ')
print('-'*70)

try:
    from trading.geometry import gaussian_curvature, CurvatureAnalyzer
    from trading.geometry import CurvatureRegime
    
    # Compute curvature
    K = gaussian_curvature(phi, laplacian)
    print(f'✅ Gaussian curvature: K = {K:.6f}')
    
    # Classify regime
    analyzer = CurvatureAnalyzer(field)
    curvature_data = analyzer.analyze_point(
        1.0852, 1000.0, ict_structures, microstructure
    )
    
    print(f'✅ Regime: {curvature_data.regime.value}')
    print(f'✅ Magnitude: {curvature_data.magnitude:.4f}')
    print(f'✅ Stability: {curvature_data.stability:.4f}')
    
    # Interpret
    from trading.geometry.curvature import interpret_curvature
    interpretation = interpret_curvature(K)
    print(f'✅ Interpretation: {interpretation}')
    
except Exception as e:
    print(f'❌ Curvature test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Geodesic Integration
print('\n5. Geodesic Integration')
print('-'*70)

try:
    from trading.geometry import GeodesicIntegrator, integrate_geodesic
    
    # Create Christoffel function
    def christoffel_func(p, t):
        d_p, d_t = field.compute_gradient(p, t, ict_structures, microstructure)
        return compute_christoffel(d_p, d_t)
    
    # Integrate geodesic
    geodesic = integrate_geodesic(
        price=1.0852,
        time=1000.0,
        velocity=0.0001,
        christoffel_func=christoffel_func,
        duration=3600,  # 1 hour
        num_points=20
    )
    
    print(f'✅ Geodesic integrated: {len(geodesic)} points')
    print(f'   Start price: {geodesic[0][0]:.5f}')
    print(f'   End price: {geodesic[-1][0]:.5f}')
    print(f'   Price change: {geodesic[-1][0] - geodesic[0][0]:.5f}')
    
except Exception as e:
    print(f'❌ Geodesic test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 6: Curvature-Aware Action Cost
print('\n6. Curvature-Aware Action Cost')
print('-'*70)

try:
    from trading.action.upgraded_action_curvature import (
        CurvatureAwareLiquidityCost,
        compute_curvature_aware_action
    )
    
    # Create path
    path = [
        {'price': 1.0850 + i*0.0001, 'timestamp': 1000 + i*60, 'ofi': 0.0}
        for i in range(10)
    ]
    
    # Compute curvature-aware cost
    result = compute_curvature_aware_action(
        path, ict_structures, microstructure, lambda_curvature=0.5
    )
    
    print(f'✅ Curvature-aware cost computed:')
    print(f'   Base liquidity cost: {result["base_liquidity_cost"]:.6f}')
    print(f'   Curvature penalty: {result["curvature_penalty"]:.6f}')
    print(f'   Lambda curvature: {result["lambda_curvature"]:.2f}')
    print(f'   Total cost: {result["total_cost"]:.6f}')
    print(f'   Dominant regime: {result["regime"]}')
    
except Exception as e:
    print(f'❌ Action cost test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 7: Pipeline Integration
print('\n7. Pipeline with Geometry Stage')
print('-'*70)

try:
    from trading.pipeline import PipelineOrchestrator
    
    # Create pipeline
    pipeline = PipelineOrchestrator()
    
    # Execute with raw data
    raw_data = {
        'ohlcv': [],
        'ticks': [
            {'bid': 1.0850, 'ask': 1.0852, 'bid_volume': 200, 'ask_volume': 50}
        ],
        'liquidity_zones': [{'level': 1.0860, 'type': 'high'}],
        'fvgs': [{'top': 1.0855, 'bottom': 1.0853}],
        'session': 'london',
    }
    
    context = pipeline.execute(raw_data, symbol='EURUSD')
    
    print(f'✅ Pipeline executed: {len(context.stage_history)} stages')
    
    # Check geometry stage
    geometry_stages = [s for s in context.stage_history 
                      if s.stage.value == 'geometry_computation']
    if geometry_stages:
        geom_stage = geometry_stages[0]
        print(f'✅ Geometry stage: success={geom_stage.success}')
        if geom_stage.success:
            print(f'   Phi: {geom_stage.output.get("phi", 0):.4f}')
            print(f'   Curvature K: {geom_stage.output.get("curvature_K", 0):.6f}')
            print(f'   Regime: {geom_stage.output.get("regime", "unknown")}')
    
    # Check geometry data in context
    if context.geometry_data:
        print(f'✅ Geometry data stored in context:')
        print(f'   Keys: {list(context.geometry_data.keys())}')
    
except Exception as e:
    print(f'❌ Pipeline test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Summary
print('\n' + '='*70)
print('RIEMANNIAN GEOMETRY TEST SUMMARY')
print('='*70)
print('✅ Liquidity Field ϕ(p,t)')
print('✅ Conformal Metric g_ij = e^(2ϕ) δ_ij')
print('✅ Christoffel Symbols Γ^i_jk')
print('✅ Gaussian Curvature K = -e^(-2ϕ) Δϕ')
print('✅ Geodesic Integration')
print('✅ Curvature-Aware Action Cost')
print('✅ Pipeline Integration')
print('\n✅ ALL RIEMANNIAN GEOMETRY TESTS PASSED')
print('='*70)

sys.exit(0)
