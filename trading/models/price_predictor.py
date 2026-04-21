"""
Neural Network Price Predictor

Transformer-based model for learning price distributions from market data.
Replaces hand-crafted ICT potentials with data-driven learned potentials.

First Principles:
- Learn potential function V(q) from historical patterns
- Uncertainty quantification via predicted std
- Fast inference (< 50ms) for real-time trading
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from typing import List, Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for time series"""
    
    def __init__(self, d_model: int, max_len: int = 5000, dropout: float = 0.1):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-np.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0).transpose(0, 1)  # (max_len, 1, d_model)
        
        self.register_buffer('pe', pe)
    
    def forward(self, x):
        """Add positional encoding to input"""
        x = x + self.pe[:x.size(0), :]
        return self.dropout(x)


class PricePredictor(nn.Module):
    """
    Transformer encoder for price prediction.
    
    Architecture:
    - Input: (batch, seq_len=100, features=23)
        * 5 OHLCV features (open, high, low, close, volume)
        * 18 ICT operator scores
    - Output: (batch, pred_len=10, 3)
        * mean: predicted price change
        * std: uncertainty (higher = less confident)
        * trend: directional bias (-1 to +1)
    
    Example:
        model = PricePredictor()
        x = torch.randn(32, 100, 23)  # batch=32, seq=100, feats=23
        mean, std, trend = model(x)
        # mean: (32, 10), std: (32, 10), trend: (32, 10)
    """
    
    def __init__(self,
                 input_features: int = 23,
                 d_model: int = 128,
                 nhead: int = 8,
                 num_layers: int = 2,
                 dim_feedforward: int = 256,
                 dropout: float = 0.1,
                 seq_len: int = 100,
                 pred_len: int = 10):
        super().__init__()
        
        self.input_features = input_features
        self.d_model = d_model
        self.seq_len = seq_len
        self.pred_len = pred_len
        
        # Input projection
        self.input_proj = nn.Linear(input_features, d_model)
        
        # Positional encoding
        self.pos_encoder = PositionalEncoding(d_model, max_len=seq_len, dropout=dropout)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output heads
        self.mean_head = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, pred_len)
        )
        
        self.std_head = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, pred_len),
            nn.Softplus()  # Ensure positive std
        )
        
        self.trend_head = nn.Sequential(
            nn.Linear(d_model, dim_feedforward),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(dim_feedforward, pred_len),
            nn.Tanh()  # -1 to +1
        )
        
        # Initialize weights
        self._init_weights()
        
        logger.info(f"PricePredictor initialized: d_model={d_model}, nhead={nhead}, layers={num_layers}")
    
    def _init_weights(self):
        """Xavier initialization for better convergence"""
        for p in self.parameters():
            if p.dim() > 1:
                nn.init.xavier_uniform_(p)
    
    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Forward pass.
        
        Args:
            x: Input tensor (batch, seq_len, input_features)
        
        Returns:
            mean: Predicted price changes (batch, pred_len)
            std: Predicted uncertainty (batch, pred_len)
            trend: Directional bias (batch, pred_len)
        """
        batch_size = x.size(0)
        
        # Input projection: (batch, seq, features) -> (batch, seq, d_model)
        x = self.input_proj(x)
        
        # Add positional encoding
        x = self.pos_encoder(x.transpose(0, 1)).transpose(0, 1)
        
        # Transformer encoding
        # Output: (batch, seq, d_model)
        encoded = self.transformer(x)
        
        # Global average pooling over sequence dimension
        # (batch, seq, d_model) -> (batch, d_model)
        pooled = encoded.mean(dim=1)
        
        # Output predictions
        mean = self.mean_head(pooled)
        std = self.std_head(pooled)
        trend = self.trend_head(pooled)
        
        return mean, std, trend
    
    def predict(self, x: torch.Tensor) -> Dict[str, torch.Tensor]:
        """
        Convenience method returning dict of predictions.
        
        Args:
            x: Input tensor (batch, seq_len, input_features)
        
        Returns:
            Dict with keys: 'mean', 'std', 'trend', 'lower', 'upper'
        """
        self.eval()
        with torch.no_grad():
            mean, std, trend = self.forward(x)
            
            # Compute confidence intervals (95%)
            lower = mean - 1.96 * std
            upper = mean + 1.96 * std
            
            return {
                'mean': mean,
                'std': std,
                'trend': trend,
                'lower': lower,
                'upper': upper
            }


class PricePredictorInference:
    """
    Inference wrapper for PricePredictor with caching.
    
    Handles:
    - Model loading
    - Input preprocessing
    - Prediction caching
    - Device management
    """
    
    def __init__(self, model_path: Optional[str] = None, device: str = "auto"):
        self.device = self._get_device(device)
        
        # Initialize model
        self.model = PricePredictor().to(self.device)
        
        # Load weights if provided
        if model_path:
            try:
                self.model.load_state_dict(torch.load(model_path, map_location=self.device))
                logger.info(f"Loaded model from {model_path}")
            except Exception as e:
                logger.warning(f"Could not load model: {e}, using untrained model")
        
        self.model.eval()
        
        # Prediction cache: hash -> (prediction, timestamp)
        self._cache = {}
        self._cache_ttl = 60  # seconds
        
        logger.info(f"PricePredictorInference initialized on {self.device}")
    
    def _get_device(self, device: str) -> torch.device:
        """Auto-detect best available device"""
        if device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            elif torch.backends.mps.is_available():
                return torch.device("mps")
            else:
                return torch.device("cpu")
        return torch.device(device)
    
    def _compute_input_hash(self, ohlcv: List[Dict], operator_scores: Optional[Dict] = None) -> str:
        """Compute hash for caching"""
        import hashlib
        # Use last 10 closes as hash key
        closes = tuple(round(c['close'], 4) for c in ohlcv[-10:])
        op_hash = tuple(sorted(operator_scores.items())) if operator_scores else ()
        hash_input = str(closes) + str(op_hash)
        return hashlib.md5(hash_input.encode()).hexdigest()
    
    def _preprocess_input(self, 
                         ohlcv: List[Dict],
                         operator_scores: Optional[Dict] = None) -> torch.Tensor:
        """
        Convert OHLCV + operator scores to model input tensor.
        
        Args:
            ohlcv: List of candle dicts
            operator_scores: Dict of operator scores
        
        Returns:
            Tensor of shape (1, seq_len, input_features)
        """
        # Ensure we have 100 candles
        if len(ohlcv) < 100:
            # Pad with last candle
            padding = [ohlcv[-1]] * (100 - len(ohlcv))
            ohlcv = ohlcv + padding
        ohlcv = ohlcv[-100:]  # Take last 100
        
        # Extract OHLCV features
        features = []
        for candle in ohlcv:
            features.append([
                candle['open'],
                candle['high'],
                candle['low'],
                candle['close'],
                candle.get('volume', 0)
            ])
        
        # Add operator scores (18 operators)
        op_scores = operator_scores or {}
        default_ops = {
            'kinetic': 0.5, 'potential': 0.5, 'liquidity': 0.5, 'ob': 0.5,
            'fvg': 0.5, 'breaker': 0.5, 'orderblock': 0.5, 'mitigation': 0.5,
            'sweep': 0.5, 'choch': 0.5, 'bos': 0.5, 'fib': 0.5,
            'pdi': 0.5, 'ndi': 0.5, 'adx': 0.5, 'atr': 0.5,
            'rsi': 0.5, 'momentum': 0.5
        }
        default_ops.update(op_scores)
        
        # Append operator scores to each timestep (broadcast)
        op_values = list(default_ops.values())
        for i, feat in enumerate(features):
            features[i] = feat + op_values
        
        # Convert to tensor and normalize
        x = torch.FloatTensor(features).unsqueeze(0)  # (1, 100, 23)
        
        # Normalize by last close price
        last_close = x[0, -1, 3]  # close price at last timestep
        if last_close > 0:
            x[:, :, :5] = x[:, :, :5] / last_close - 1.0  # Normalize OHLCV
        
        return x
    
    def predict(self,
                ohlcv: List[Dict],
                operator_scores: Optional[Dict] = None,
                use_cache: bool = True) -> Dict[str, np.ndarray]:
        """
        Predict future price distribution.
        
        Args:
            ohlcv: List of candle dicts
            operator_scores: Dict of operator scores
            use_cache: Whether to use prediction cache
        
        Returns:
            Dict with keys: 'mean', 'std', 'trend', 'lower', 'upper'
            Each is numpy array of shape (pred_len,)
        """
        import time
        
        # Check cache
        if use_cache:
            cache_key = self._compute_input_hash(ohlcv, operator_scores)
            if cache_key in self._cache:
                prediction, timestamp = self._cache[cache_key]
                if time.time() - timestamp < self._cache_ttl:
                    return prediction
        
        # Preprocess input
        x = self._preprocess_input(ohlcv, operator_scores)
        x = x.to(self.device)
        
        # Predict
        self.model.eval()
        with torch.no_grad():
            result = self.model.predict(x)
        
        # Convert to numpy
        prediction = {k: v.cpu().numpy().flatten() for k, v in result.items()}
        
        # Update cache
        if use_cache:
            self._cache[cache_key] = (prediction, time.time())
        
        return prediction
    
    def to_potential(self, prediction: Dict[str, np.ndarray]) -> float:
        """
        Convert prediction to potential energy value.
        
        Higher uncertainty and unfavorable trend = higher potential (barrier)
        Lower uncertainty and favorable trend = lower potential (valley)
        
        Args:
            prediction: Output from predict()
        
        Returns:
            Scalar potential value
        """
        mean = prediction['mean'][0]  # First step prediction
        std = prediction['std'][0]
        trend = prediction['trend'][0]
        
        # Potential components:
        # 1. Uncertainty penalty (higher std = higher potential)
        uncertainty_penalty = std * 2.0
        
        # 2. Trend reward (positive trend = lower potential)
        trend_reward = -trend * 0.5
        
        # 3. Mean reversion penalty (large deviation = higher potential)
        mean_penalty = abs(mean) * 0.3
        
        potential = uncertainty_penalty + trend_reward + mean_penalty
        
        return float(potential)


# Global singleton instance
_predictor: Optional[PricePredictorInference] = None


def get_predictor(model_path: Optional[str] = None) -> PricePredictorInference:
    """Get or create global predictor instance"""
    global _predictor
    if _predictor is None:
        _predictor = PricePredictorInference(model_path=model_path)
    return _predictor


def reset_predictor():
    """Reset global predictor instance (for testing)"""
    global _predictor
    _predictor = None
