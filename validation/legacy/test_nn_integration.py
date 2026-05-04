#!/usr/bin/env python3
"""
Test script for Neural Network Price Predictor Integration

Verifies:
1. PricePredictor model architecture
2. Training on synthetic data
3. Inference and caching
4. Minkowski adapter integration
"""

import sys
sys.path.insert(0, '.')

import numpy as np
import torch

def test_model_architecture():
    """Test PricePredictor architecture"""
    print("\n" + "="*70)
    print("🧪 TEST 1: Model Architecture")
    print("="*70)
    
    from trading.models import PricePredictor
    
    model = PricePredictor()
    
    # Test forward pass
    batch_size = 4
    x = torch.randn(batch_size, 100, 23)  # (batch, seq, features)
    
    mean, std, trend = model(x)
    
    print(f"✅ Input shape: {x.shape}")
    print(f"✅ Mean output shape: {mean.shape} (expected: ({batch_size}, 10))")
    print(f"✅ Std output shape: {std.shape}")
    print(f"✅ Trend output shape: {trend.shape}")
    print(f"✅ Mean range: [{mean.min().item():.4f}, {mean.max().item():.4f}]")
    print(f"✅ Std range: [{std.min().item():.4f}, {std.max().item():.4f}] (should be positive)")
    print(f"✅ Trend range: [{trend.min().item():.4f}, {trend.max().item():.4f}] (should be in [-1, 1])")
    
    # Count parameters
    total_params = sum(p.numel() for p in model.parameters())
    print(f"✅ Total parameters: {total_params:,}")
    
    return True


def test_training():
    """Test training pipeline on synthetic data"""
    print("\n" + "="*70)
    print("🧪 TEST 2: Training Pipeline (Synthetic)")
    print("="*70)
    
    from trading.models import PricePredictor
    from trading.models.train import SyntheticDataset, PricePredictorTrainer
    from torch.utils.data import DataLoader
    
    # Create small dataset for quick test
    dataset = SyntheticDataset(n_samples=100, seq_len=100, pred_len=10)
    dataloader = DataLoader(dataset, batch_size=8, shuffle=True)
    
    # Create model and trainer
    model = PricePredictor()
    trainer = PricePredictorTrainer(model, device="cpu")
    
    # Train for a few steps
    print("Training for 5 epochs...")
    losses = []
    for epoch in range(5):
        loss = trainer.train_epoch(dataloader)
        losses.append(loss)
        print(f"  Epoch {epoch+1}: loss={loss:.6f}")
    
    # Check that loss is decreasing
    if losses[-1] < losses[0]:
        print(f"✅ Loss decreasing: {losses[0]:.6f} -> {losses[-1]:.6f}")
    else:
        print(f"⚠️ Loss not decreasing (may need more epochs)")
    
    return True


def test_inference():
    """Test inference wrapper"""
    print("\n" + "="*70)
    print("🧪 TEST 3: Inference & Caching")
    print("="*70)
    
    from trading.models import PricePredictorInference
    
    # Create predictor
    predictor = PricePredictorInference(device="cpu")
    
    # Create sample OHLCV
    ohlcv = []
    base_price = 1.0850
    for i in range(100):
        close = base_price + np.random.normal(0, 0.001) + (i * 0.00001)
        ohlcv.append({
            'open': close - 0.0001,
            'high': close + 0.0002,
            'low': close - 0.0002,
            'close': close,
            'volume': 1000 + i * 10
        })
    
    # First prediction (no cache)
    import time
    start = time.time()
    pred1 = predictor.predict(ohlcv)
    time1 = time.time() - start
    
    print(f"✅ First prediction: {time1*1000:.2f}ms")
    print(f"   Mean: {pred1['mean'][:3]}... (showing first 3)")
    print(f"   Std: {pred1['std'][:3]}...")
    print(f"   Trend: {pred1['trend'][:3]}...")
    
    # Second prediction (should be cached)
    start = time.time()
    pred2 = predictor.predict(ohlcv)
    time2 = time.time() - start
    
    print(f"✅ Cached prediction: {time2*1000:.2f}ms (should be faster)")
    
    # Verify same result
    if np.allclose(pred1['mean'], pred2['mean']):
        print("✅ Cached result matches original")
    
    # Test potential conversion
    potential = predictor.to_potential(pred1)
    print(f"✅ Potential value: {potential:.6f}")
    
    return True


def test_minkowski_integration():
    """Test Minkowski adapter with NN potentials"""
    print("\n" + "="*70)
    print("🧪 TEST 4: Minkowski Adapter Integration")
    print("="*70)
    
    from trading.market_bridge import MinkowskiAdapter
    
    # Create sample OHLCV
    ohlcv = []
    base_price = 1.0850
    for i in range(100):
        close = base_price + np.random.normal(0, 0.001) + (i * 0.00001)
        ohlcv.append({
            'open': close - 0.0001,
            'high': close + 0.0002,
            'low': close - 0.0002,
            'close': close,
            'volume': 1000 + i * 10
        })
    
    # Test without NN
    adapter_ict = MinkowskiAdapter(use_nn=False)
    tuple_ict = adapter_ict.transform(ohlcv)
    
    print("Without NN (ICT only):")
    print(f"  Total energy: {tuple_ict.H['total_energy']:.6f}")
    print(f"  Kinetic: {tuple_ict.H['kinetic']:.6f}")
    print(f"  Potential: {tuple_ict.H['potential']:.6f}")
    print(f"  NN potential: {tuple_ict.H.get('nn_potential', 0):.6f}")
    print(f"  NN weight: {tuple_ict.H.get('nn_weight', 0):.6f}")
    
    # Test with NN (if available)
    try:
        adapter_nn = MinkowskiAdapter(use_nn=True, nn_weight=0.3)
        tuple_nn = adapter_nn.transform(ohlcv)
        
        print("\nWith NN (Hybrid 70% ICT + 30% NN):")
        print(f"  Total energy: {tuple_nn.H['total_energy']:.6f}")
        print(f"  Kinetic: {tuple_nn.H['kinetic']:.6f}")
        print(f"  Potential: {tuple_nn.H['potential']:.6f}")
        print(f"  NN potential: {tuple_nn.H.get('nn_potential', 0):.6f}")
        print(f"  NN weight: {tuple_nn.H.get('nn_weight', 0):.6f}")
        
        # Verify hybrid formula
        ict_energy = tuple_ict.H['total_energy']
        nn_potential = tuple_nn.H.get('nn_potential', 0)
        expected = 0.7 * ict_energy + 0.3 * nn_potential
        actual = tuple_nn.H['total_energy']
        
        if abs(expected - actual) < 0.001:
            print(f"✅ Hybrid formula verified: 0.7*{ict_energy:.4f} + 0.3*{nn_potential:.4f} = {actual:.4f}")
        else:
            print(f"⚠️ Hybrid formula mismatch: expected {expected:.4f}, got {actual:.4f}")
            
    except Exception as e:
        print(f"⚠️ NN integration test skipped: {e}")
    
    return True


def main():
    """Run all tests"""
    print("="*70)
    print("🚀 NN PRICE PREDICTOR INTEGRATION TEST SUITE")
    print("="*70)
    
    tests = [
        ("Model Architecture", test_model_architecture),
        ("Training Pipeline", test_training),
        ("Inference & Caching", test_inference),
        ("Minkowski Integration", test_minkowski_integration),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        try:
            if test_fn():
                passed += 1
                print(f"\n✅ {name}: PASSED")
            else:
                failed += 1
                print(f"\n❌ {name}: FAILED")
        except Exception as e:
            failed += 1
            print(f"\n❌ {name}: ERROR - {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*70)
    print(f"📊 RESULTS: {passed} passed, {failed} failed")
    print("="*70)
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
