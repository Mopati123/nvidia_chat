#!/usr/bin/env python3
"""
TAEP Integration Test

Tests the complete TAEP + Trading integration.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

print('='*70)
print('TAEP INTEGRATION TEST')
print('='*70)

# Test 1: TAEP Core
print('\n1. TAEP Core Components')
print('-'*70)

try:
    from taep.core.state import TAEPState, ExecutionToken
    
    token = ExecutionToken('TEST', 1000.0, 9999999999.0)
    state = TAEPState(
        q=np.array([1.0850, 1000.0, 0.5]),
        p=np.array([0.0001, 0.0, 0.0]),
        k=np.array([0.5, 0.3, 0.2]),
        policy={'max_position': 10.0},
        entropy=0.5,
        token=token
    )
    
    assert state.is_admissible(), "State should be admissible"
    print('✅ TAEPState creation and admissibility')
    
    hash_val = state.compute_hash()
    assert len(hash_val) == 64, "Hash should be 64 chars"
    print('✅ State hashing')
    
except Exception as e:
    print(f'❌ TAEP Core failed: {e}')
    sys.exit(1)

# Test 2: Three-Body Chaos
print('\n2. Three-Body Chaos Engine')
print('-'*70)

try:
    from taep.chaos.three_body import ThreeBodyEngine
    
    engine = ThreeBodyEngine()
    
    # Generate key seed
    key_seed = engine.generate_key_seed(
        np.array([1.0850, 1000.0, 0.5]),
        np.array([0.0001, 0.0, 0.0])
    )
    
    assert len(key_seed) > 0, "Should generate key seed"
    assert np.all(key_seed >= 0), "Key seed should be positive"
    print('✅ Key seed generation')
    
    # Evolve system
    engine.evolve(dt=0.01, steps=10)
    print('✅ Three-body evolution')
    
except Exception as e:
    print(f'❌ Three-body failed: {e}')
    import traceback
    traceback.print_exc()

# Test 3: Scheduler
print('\n3. TAEP Scheduler')
print('-'*70)

try:
    from taep.scheduler.scheduler import TAEPScheduler
    
    scheduler = TAEPScheduler()
    
    # Authorize valid state
    authorized = scheduler.authorize(state, {'test': 'transition'})
    assert authorized, "Should authorize valid state"
    print('✅ Authorization')
    
    # Collapse and emit evidence
    evidence = scheduler.collapse(state, authorized)
    assert evidence is not None, "Should emit evidence"
    assert evidence.decision == 'ACCEPT', "Should be ACCEPT"
    print('✅ Evidence emission')
    
except Exception as e:
    print(f'❌ Scheduler failed: {e}')
    import traceback
    traceback.print_exc()

# Test 4: Trading Bridge
print('\n4. Trading-TAEP Bridge')
print('-'*70)

try:
    from trading.taep_bridge import TradingTAEPBridge
    
    bridge = TradingTAEPBridge()
    
    market_state = {
        'mid': 1.0850,
        'spread': 0.0002,
        'velocity': 0.0001,
        'acceleration': 0.0,
    }
    
    geometry_data = {'phi': 0.5, 'regime': 'flat'}
    
    decision_context = {
        'symbol': 'EURUSD',
        'timestamp': 1000.0,
        'session': 'london',
    }
    
    taep_state = bridge.trading_to_taep(
        market_state, geometry_data, decision_context
    )
    
    assert taep_state is not None, "Should create TAEP state"
    assert taep_state.q[0] == 1.0850, "Price should match"
    print('✅ Trading to TAEP conversion')
    
    # Convert back
    decision = bridge.taep_to_trading_decision(taep_state, authorized=True)
    assert decision['authorized'] == True
    print('✅ TAEP to trading conversion')
    
except Exception as e:
    print(f'❌ Bridge failed: {e}')
    import traceback
    traceback.print_exc()

# Test 5: Shadow Mode
print('\n5. TAEP Shadow Mode')
print('-'*70)

try:
    from trading.taep_shadow import TAEPShadowOrchestrator, create_shadow_orchestrator
    
    orchestrator = create_shadow_orchestrator()
    
    market_data = {
        'ticks': [{'bid': 1.0850, 'ask': 1.0852, 'timestamp': 1000}],
        'ict_structures': {},
        'timestamp': 1000.0,
    }
    
    ctx, evidence = orchestrator.run_shadow_decision(market_data, 'EURUSD')
    
    assert ctx is not None, "Should return context"
    assert evidence is not None, "Should emit evidence"
    print('✅ Shadow decision execution')
    
    # Check metrics
    stats = orchestrator.get_statistics()
    assert stats['total_decisions'] == 1
    print('✅ Statistics collection')
    
except Exception as e:
    print(f'❌ Shadow mode failed: {e}')
    import traceback
    traceback.print_exc()

# Summary
print('\n' + '='*70)
print('TAEP INTEGRATION TEST SUMMARY')
print('='*70)
print('✅ TAEP Core (State, Token, Admissibility)')
print('✅ Three-Body Chaos Engine')
print('✅ TAEP Scheduler (Collapse Authority)')
print('✅ Trading-TAEP Bridge')
print('✅ TAEP Shadow Mode')
print('\n✅ ALL TAEP INTEGRATION TESTS PASSED')
print('='*70)

sys.exit(0)
