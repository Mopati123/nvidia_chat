"""
Neural Network Models for Trading

Provides machine learning models for price prediction and market analysis.

Key Components:
- PricePredictor: Transformer-based price distribution prediction
- PricePredictorInference: Inference wrapper with caching
- SimplePricePredictor: Simple interface for testing
"""

import numpy as np
from typing import Dict
from .price_predictor import (
    PricePredictor,
    PricePredictorInference,
    get_predictor,
    reset_predictor,
)


class SimplePricePredictor:
    """
    Simple predictor interface for testing and basic usage.
    
    Works with numpy embeddings directly instead of full OHLCV data.
    """
    
    def __init__(self, seed: int = 42):
        self.seed = seed
        np.random.seed(seed)
    
    def predict(self, embedding: np.ndarray) -> Dict[str, float]:
        """
        Generate simple prediction from embedding.
        
        Args:
            embedding: 128-dim numpy array
        
        Returns:
            Dict with 'mean', 'std', 'trend' as scalars
        """
        # Use embedding statistics for simple prediction
        mean_val = float(np.mean(embedding))
        std_val = float(np.std(embedding))
        
        # Simple trend from first vs last half
        mid = len(embedding) // 2
        first_half = np.mean(embedding[:mid])
        second_half = np.mean(embedding[mid:])
        trend_val = float(second_half - first_half)
        
        return {
            'mean': mean_val * 0.01,  # Scale down
            'std': max(std_val * 0.01, 0.001),  # Ensure positive
            'trend': np.tanh(trend_val)  # Bounded trend
        }


__all__ = [
    'PricePredictor',
    'PricePredictorInference',
    'SimplePricePredictor',
    'get_predictor',
    'reset_predictor',
]
