"""
Market State Embedder

Converts OHLCV market data into dense vector embeddings using a neural autoencoder.
These embeddings are used for similarity search in the vector database.

First Principles:
- Compress high-dimensional OHLCV into latent representation
- Preserve topological structure (similar markets = similar embeddings)
- Use lightweight architecture for fast inference (< 10ms)
"""

import numpy as np
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

# Optional PyTorch support
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.info("PyTorch not available, using simple statistical encoding")


if TORCH_AVAILABLE:
    class MarketAutoencoder(nn.Module):
        """
        Autoencoder for market state compression.
        
        Input: 100 candles × 5 features (OHLCV) = 500 dimensions
        Latent: 128 dimensions
        Output: Reconstructed 500 dimensions
        """
        
        def __init__(self, input_dim: int = 500, latent_dim: int = 128):
            super().__init__()
            self.input_dim = input_dim
            self.latent_dim = latent_dim
            
            # Encoder: 500 -> 256 -> 128
            self.encoder = nn.Sequential(
                nn.Linear(input_dim, 256),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(256, latent_dim),
                nn.ReLU()
            )
            
            # Decoder: 128 -> 256 -> 500
            self.decoder = nn.Sequential(
                nn.Linear(latent_dim, 256),
                nn.ReLU(),
                nn.Dropout(0.1),
                nn.Linear(256, input_dim),
                nn.Sigmoid()  # Normalize to [0, 1]
            )
        
        def encode(self, x: torch.Tensor) -> torch.Tensor:
            """Compress market state to latent vector"""
            return self.encoder(x)
        
        def decode(self, z: torch.Tensor) -> torch.Tensor:
            """Reconstruct market state from latent vector"""
            return self.decoder(z)
        
        def forward(self, x: torch.Tensor) -> tuple:
            """Full autoencoder pass"""
            z = self.encode(x)
            x_recon = self.decode(z)
            return x_recon, z
else:
    class MarketAutoencoder:
        """Autoencoder stub for when PyTorch is not available"""
        def __init__(self, *args, **kwargs):
            self.input_dim = kwargs.get('input_dim', 500)
            self.latent_dim = kwargs.get('latent_dim', 128)
        
        def encode(self, x):
            raise RuntimeError("PyTorch not installed, cannot use neural encoding")
        
        def decode(self, z):
            raise NotImplementedError
        
        def forward(self, x):
            raise NotImplementedError
        
        def to(self, device):
            """Dummy to() method for API compatibility"""
            return self
        
        def eval(self):
            """Dummy eval() method for API compatibility"""
            pass
        
        def load_state_dict(self, state_dict):
            """Dummy load_state_dict() method for API compatibility"""
            pass


class MarketEmbedder:
    """
    Market state embedder with caching for fast retrieval.
    
    Usage:
        embedder = MarketEmbedder()
        embedding = embedder.encode(ohlcv_data)
        similar_patterns = vector_db.query(embedding, top_k=10)
    """
    
    LATENT_DIM = 128
    SEQUENCE_LENGTH = 100  # candles
    FEATURES = 5  # OHLCV
    
    def __init__(self, model_path: Optional[str] = None, device: str = "auto"):
        # Determine if we can use neural encoding
        logger.info(f"Initializing MarketEmbedder, TORCH_AVAILABLE={TORCH_AVAILABLE}")
        if TORCH_AVAILABLE:
            self.device = self._get_device(device)
            self.model = MarketAutoencoder(
                input_dim=self.SEQUENCE_LENGTH * self.FEATURES,
                latent_dim=self.LATENT_DIM
            ).to(self.device)
            
            # Try to load pretrained weights
            if model_path and torch.cuda.is_available() == False:
                # CPU-only, use simple encoding instead
                self.use_simple = True
                logger.info("Using simple statistical encoding (CPU mode)")
            else:
                self.use_simple = False
                if model_path:
                    try:
                        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
                        logger.info(f"Loaded embedder from {model_path}")
                    except Exception as e:
                        logger.warning(f"Could not load model: {e}, using untrained model")
                self.model.eval()
        else:
            # No torch available - use simple encoding
            self.use_simple = True
            self.device = None
            self.model = None
            logger.info(f"Using simple statistical encoding (PyTorch not available, use_simple={self.use_simple})")
    
    def _get_device(self, device: str):
        """Auto-detect best available device"""
        if not TORCH_AVAILABLE:
            return None
        if device == "auto":
            if torch.cuda.is_available():
                return torch.device("cuda")
            elif torch.backends.mps.is_available():
                return torch.device("mps")
            else:
                return torch.device("cpu")
        return torch.device(device)
    
    def _normalize_ohlcv(self, ohlcv: List[Dict]) -> np.ndarray:
        """
        Normalize OHLCV data to [0, 1] range.
        
        Uses min-max normalization per-feature to preserve relative structure.
        """
        if len(ohlcv) < self.SEQUENCE_LENGTH:
            # Pad with zeros if too short
            padding = [ohlcv[-1]] * (self.SEQUENCE_LENGTH - len(ohlcv))
            ohlcv = ohlcv + padding
        
        # Take last 100 candles
        ohlcv = ohlcv[-self.SEQUENCE_LENGTH:]
        
        # Extract features
        opens = np.array([c['open'] for c in ohlcv])
        highs = np.array([c['high'] for c in ohlcv])
        lows = np.array([c['low'] for c in ohlcv])
        closes = np.array([c['close'] for c in ohlcv])
        volumes = np.array([c.get('volume', 0) for c in ohlcv])
        
        # Stack: (100, 5)
        features = np.stack([opens, highs, lows, closes, volumes], axis=1)
        
        # Min-max normalize per feature
        for i in range(5):
            f_min, f_max = features[:, i].min(), features[:, i].max()
            if f_max > f_min:
                features[:, i] = (features[:, i] - f_min) / (f_max - f_min)
            else:
                features[:, i] = 0.5  # Constant feature
        
        return features.flatten()  # (500,)
    
    def _simple_encode(self, ohlcv: List[Dict]) -> np.ndarray:
        """
        Simple statistical encoding for CPU-only mode.
        Fast but less expressive than neural encoding.
        """
        if len(ohlcv) == 0:
            return np.zeros(self.LATENT_DIM)
        
        closes = [c['close'] for c in ohlcv]
        volumes = [c.get('volume', 0) for c in ohlcv]
        
        # Statistical features
        features = [
            np.mean(closes),
            np.std(closes),
            (closes[-1] - closes[0]) / closes[0] if closes[0] != 0 else 0,  # Return
            max(closes) - min(closes),  # Range
            np.mean(volumes),
            np.std(volumes),
            len(ohlcv),
        ]
        
        # Technical indicators (simplified)
        if len(closes) >= 20:
            sma20 = np.mean(closes[-20:])
            features.append((closes[-1] - sma20) / sma20)
        else:
            features.append(0)
        
        if len(closes) >= 50:
            sma50 = np.mean(closes[-50:])
            features.append((closes[-1] - sma50) / sma50)
        else:
            features.append(0)
        
        # Pad to LATENT_DIM
        embedding = np.array(features)
        if len(embedding) < self.LATENT_DIM:
            embedding = np.pad(embedding, (0, self.LATENT_DIM - len(embedding)))
        else:
            embedding = embedding[:self.LATENT_DIM]
        
        # Normalize
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding
    
    def encode(self, ohlcv: List[Dict]) -> np.ndarray:
        """
        Encode OHLCV data to 128-dim embedding vector.
        
        Args:
            ohlcv: List of candle dicts with keys: open, high, low, close, volume
        
        Returns:
            128-dimensional numpy array (normalized)
        """
        logger.debug(f"encode called, use_simple={self.use_simple}")
        if self.use_simple:
            return self._simple_encode(ohlcv)
        
        # Neural encoding
        normalized = self._normalize_ohlcv(ohlcv)
        
        with torch.no_grad():
            x = torch.FloatTensor(normalized).unsqueeze(0).to(self.device)
            embedding = self.model.encode(x)
            embedding = embedding.cpu().numpy().flatten()
        
        # L2 normalize for cosine similarity
        norm = np.linalg.norm(embedding)
        if norm > 0:
            embedding = embedding / norm
        
        return embedding
    
    def encode_market_state(self, market_state) -> np.ndarray:
        """
        Encode MarketState object to embedding.
        
        Handles both raw OHLCV and MarketTuple formats.
        """
        # Try to extract OHLCV from market state
        if hasattr(market_state, 'ohlc'):
            ohlcv = market_state.ohlc
        elif hasattr(market_state, 'M') and hasattr(market_state.M, 'ohlc'):
            ohlcv = market_state.M.ohlc
        elif isinstance(market_state, dict) and 'ohlcv' in market_state:
            ohlcv = market_state['ohlcv']
        elif isinstance(market_state, list):
            ohlcv = market_state
        else:
            # Try to extract from any attribute
            for attr in ['ohlcv', 'candles', 'data', 'prices']:
                if hasattr(market_state, attr):
                    ohlcv = getattr(market_state, attr)
                    break
            else:
                raise ValueError(f"Cannot extract OHLCV from market_state: {type(market_state)}")
        
        return self.encode(ohlcv)
    
    def compute_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings"""
        return np.dot(emb1, emb2)
    
    def train_step(self, batch: torch.Tensor) -> float:
        """Single training step (for online learning)"""
        self.model.train()
        
        # Reconstruction loss
        x_recon, z = self.model(batch)
        loss = nn.MSELoss()(x_recon, batch)
        
        return loss.item()


# Global singleton instance
_embedder: Optional[MarketEmbedder] = None


def get_embedder(model_path: Optional[str] = None) -> MarketEmbedder:
    """Get or create global embedder instance"""
    global _embedder
    if _embedder is None:
        _embedder = MarketEmbedder(model_path=model_path)
    return _embedder


def reset_embedder():
    """Reset global embedder instance (for testing)"""
    global _embedder
    _embedder = None
