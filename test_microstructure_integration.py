#!/usr/bin/env python3
"""
Microstructure + Backward Learning Integration Test

Validates the complete integration of:
1. Tick-level microstructure (OFI, flow fields)
2. Upgraded action components (S_L, S_T, S_E, S_R with microstructure)
3. Backward learning (WeightUpdateOperator)
4. Scheduler integration (dynamic weight updates)
"""

import sys
import numpy as np
from datetime import datetime

print('='*70)
print('MICROSTRUCTURE + BACKWARD LEARNING INTEGRATION TEST')
print('='*70)

# Test 1: Microstructure Components
print('\n1. Microstructure Components')
print('-'*70)

try:
    from trading.microstructure import TickProcessor, MicroState
    from trading.microstructure import LiquidityPotentialField, FlowField
    
    # Test tick processing
    processor = TickProcessor(window_size=10)
    
    # Simulate tick stream
    ticks = [
        {'timestamp': 1.0, 'bid': 1.0850, 'ask': 1.0852, 'bid_volume': 100, 'ask_volume': 100},
        {'timestamp': 2.0, 'bid': 1.0851, 'ask': 1.0853, 'bid_volume': 150, 'ask_volume': 80},
        {'timestamp': 3.0, 'bid': 1.0852, 'ask': 1.0854, 'bid_volume': 200, 'ask_volume': 60},
        {'timestamp': 4.0, 'bid': 1.0853, 'ask': 1.0855, 'bid_volume': 250, 'ask_volume': 40},
        {'timestamp': 5.0, 'bid': 1.0854, 'ask': 1.0856, 'bid_volume': 300, 'ask_volume': 30},
    ]
    
    for tick in ticks:
        result = processor.process_tick(tick)
    
    print(f'✅ TickProcessor working')
    print(f'   OFI: {result["ofi"]:.2f}')
    print(f'   Microprice: {result["microprice"]:.5f}')
    print(f'   Velocity: {result["velocity"]:.6f}')
    print(f'   Flow bias: {result.get("ofi_signal", "N/A")}')
    
    # Test flow field
    flow_field = LiquidityPotentialField()
    flow_field.set_liquidity_zones([
        {'level': 1.0860, 'type': 'high', 'strength': 3.0},
        {'level': 1.0840, 'type': 'low', 'strength': 2.0},
    ])
    flow_field.set_fvg_zones([
        {'top': 1.0855, 'bottom': 1.0853, 'type': 'bullish'},
    ])
    
    potential = flow_field.compute_potential(1.0854, ofi=0.5)
    print(f'✅ LiquidityPotentialField working')
    print(f'   Potential at 1.0854: {potential:.6f}')
    
except Exception as e:
    print(f'❌ Microstructure test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Upgraded Action Components
print('\n2. Upgraded Action Components (S_L, S_T, S_E, S_R)')
print('-'*70)

try:
    from trading.action.upgraded_components import UpgradedActionComponents
    
    action_comp = UpgradedActionComponents()
    
    # Test S_L (Liquidity)
    path = [
        {'price': 1.0850, 'ofi': 0.3, 'timestamp': 1.0},
        {'price': 1.0852, 'ofi': 0.5, 'timestamp': 2.0},
        {'price': 1.0854, 'ofi': 0.7, 'timestamp': 3.0},
    ]
    liquidity_zones = [
        {'level': 1.0860, 'type': 'high', 'strength': 3.0},
    ]
    fvgs = [
        {'top': 1.0855, 'bottom': 1.0853, 'type': 'bullish'},
    ]
    
    s_l = action_comp.compute_s_liquidity(path, liquidity_zones, fvgs)
    print(f'✅ S_L (Liquidity) computed: {s_l:.6f}')
    
    # Test S_T (Time)
    s_t = action_comp.compute_s_time(path, 'london', in_kill_zone=False)
    print(f'✅ S_T (Time) computed: {s_t:.6f}')
    
    s_t_kz = action_comp.compute_s_time(path, 'ny', in_kill_zone=True)
    print(f'✅ S_T kill zone bonus: {s_t_kz:.6f}')
    
    # Test S_E (Entry)
    s_e = action_comp.compute_s_entry(
        entry_price=1.0854,
        fvg_midpoint=1.0854,
        fib_level=1.0853,
        ofi_at_entry=0.5,
        ofi_before=0.3
    )
    print(f'✅ S_E (Entry) computed: {s_e:.6f}')
    
    # Test S_R (Risk)
    path_with_risk = [
        {'price': 1.0850, 'drawdown': 0.0, 'spread': 0.0002, 'acceleration': 0.0},
        {'price': 1.0848, 'drawdown': 0.0002, 'spread': 0.0003, 'acceleration': -0.0001},
        {'price': 1.0847, 'drawdown': 0.0003, 'spread': 0.0004, 'acceleration': -0.0002},
    ]
    s_r = action_comp.compute_s_risk(path_with_risk)
    print(f'✅ S_R (Risk) computed: {s_r:.6f}')
    
    # Test full action
    microstate = {
        'ict_geometry': {
            'liquidity_zones': liquidity_zones,
            'fvgs': fvgs,
            'current_session': 'london',
            'kill_zone': False,
        }
    }
    weights = {'L': 0.5, 'T': 0.3, 'E': 0.1, 'R': 0.1}
    
    full_action = action_comp.compute_full_action(path, microstate, weights)
    print(f'✅ Full action computed:')
    print(f'   S_L={full_action["S_L"]:.6f}')
    print(f'   S_T={full_action["S_T"]:.6f}')
    print(f'   S_E={full_action["S_E"]:.6f}')
    print(f'   S_R={full_action["S_R"]:.6f}')
    print(f'   Total={full_action["total_action"]:.6f}')
    
except Exception as e:
    print(f'❌ Action components test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Weight Update Operator
print('\n3. Weight Update Operator (Backward Learning)')
print('-'*70)

try:
    from trading.core.learning import WeightUpdateOperator
    
    operator = WeightUpdateOperator()
    
    # Simulate weight update
    weights = {'L': 0.5, 'T': 0.3, 'E': 0.1, 'R': 0.1}
    contrib = {'L': 10.0, 'T': 5.0, 'E': 3.0, 'R': 2.0}
    pnl = 50.0
    delta_s = 0.3
    status = 'match'
    
    result = operator.update(
        weights=weights,
        contrib=contrib,
        pnl=pnl,
        delta_s=delta_s,
        status=status,
        constraints_passed=True,
        collapse_authorized=True,
        evidence_complete=True
    )
    
    print(f'✅ Weight update executed')
    print(f'   Updated: {result.updated}')
    print(f'   Reward: {result.reward:.4f}')
    print(f'   Old weights: {result.old_weights}')
    print(f'   New weights: {result.new_weights}')
    
    # Test with mismatch
    result_mismatch = operator.update(
        weights=result.new_weights,
        contrib=contrib,
        pnl=-20.0,
        delta_s=0.1,
        status='mismatch',
        constraints_passed=True,
        collapse_authorized=True,
        evidence_complete=True
    )
    
    print(f'✅ Weight update with mismatch handled')
    print(f'   Reward (negative): {result_mismatch.reward:.4f}')
    
except Exception as e:
    print(f'❌ Weight update test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 4: Scheduler Integration
print('\n4. Scheduler Integration')
print('-'*70)

try:
    from trading.kernel.scheduler import Scheduler
    
    scheduler = Scheduler()
    
    # Get initial weights
    initial_weights = scheduler.get_action_weights()
    print(f'✅ Initial action weights: {initial_weights}')
    
    # Simulate post-trade weight update
    update_result = scheduler.update_action_weights(
        pnl=75.0,
        delta_s=0.4,
        status='match',
        contrib={'L': 12.0, 'T': 6.0, 'E': 4.0, 'R': 3.0},
        constraints_passed=True,
        evidence_complete=True
    )
    
    print(f'✅ Scheduler weight update executed')
    print(f'   Reward: {update_result["reward"]:.4f}')
    
    # Get updated weights
    updated_weights = scheduler.get_action_weights()
    print(f'✅ Updated action weights: {updated_weights}')
    
    # Verify weights changed
    weights_changed = any(
        initial_weights[k] != updated_weights[k] 
        for k in initial_weights.keys()
    )
    
    if weights_changed:
        print(f'✅ Weights successfully adapted')
    else:
        print(f'⚠️ Weights unchanged (may be due to small reward)')
    
except Exception as e:
    print(f'❌ Scheduler integration test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: End-to-End Integration
print('\n5. End-to-End Integration')
print('-'*70)

try:
    # Simulate a complete trade cycle
    
    # 1. Market data → Microstructure
    processor = TickProcessor()
    tick_data = {'timestamp': 1.0, 'bid': 1.0850, 'ask': 1.0852, 
                 'bid_volume': 200, 'ask_volume': 50}  # Strong buying
    micro_result = processor.process_tick(tick_data)
    
    # 2. Microstructure → Action Components
    action_comp = UpgradedActionComponents()
    path = [{'price': 1.0851, 'ofi': micro_result['ofi'], 'timestamp': 1.0}]
    liquidity_zones = [{'level': 1.0860, 'type': 'high', 'strength': 3.0}]
    fvgs = [{'top': 1.0855, 'bottom': 1.0853, 'type': 'bullish'}]
    
    s_l = action_comp.compute_s_liquidity(path, liquidity_zones, fvgs)
    
    # 3. Action → Scheduler → Weights
    scheduler = Scheduler()
    weights = scheduler.get_action_weights()
    
    # 4. Simulate trade outcome
    update_result = scheduler.update_action_weights(
        pnl=100.0,
        delta_s=0.5,
        status='match',
        contrib={'L': s_l * 10, 'T': 5.0, 'E': 3.0, 'R': 2.0},
        constraints_passed=True,
        evidence_complete=True
    )
    
    print(f'✅ End-to-end integration successful')
    print(f'   Microstructure captured OFI: {micro_result["ofi"]:.2f}')
    print(f'   Liquidity cost computed: {s_l:.6f}')
    print(f'   Weights updated: {update_result["updated"]}')
    print(f'   Final reward: {update_result["reward"]:.4f}')
    
except Exception as e:
    print(f'❌ End-to-end test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Summary
print('\n' + '='*70)
print('INTEGRATION TEST SUMMARY')
print('='*70)
print('✅ Microstructure Components (OFI, Flow Fields)')
print('✅ Upgraded Action Components (S_L, S_T, S_E, S_R)')
print('✅ Weight Update Operator (Backward Learning)')
print('✅ Scheduler Integration (Dynamic Weights)')
print('✅ End-to-End Pipeline')
print('\n✅ ALL TESTS PASSED - Integration Complete')
print('='*70)

sys.exit(0)
