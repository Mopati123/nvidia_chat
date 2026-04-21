"""
Pattern Memory Module

Provides vector database storage for market patterns and trajectory outcomes.
Enables similarity-based retrieval to bias trajectory generation.

Key Components:
- MarketEmbedder: Converts OHLCV to 128-dim embeddings
- PatternVectorStore: ChromaDB wrapper for pattern storage/retrieval
- PatternMemory: Data structure for storing pattern + outcomes

Usage:
    from trading.memory import get_embedder, get_vector_store
    
    # Encode market state
    embedder = get_embedder()
    embedding = embedder.encode(ohlcv_data)
    
    # Query similar patterns
    store = get_vector_store()
    similar = store.query_similar(embedding, symbol="EURUSD", top_k=10)
    
    # Bias trajectories
    biases = store.compute_memory_bias(trajectories, similar)
"""

from .embedder import MarketEmbedder, get_embedder, reset_embedder
from .vector_store import PatternVectorStore, PatternMemory, get_vector_store, reset_vector_store

__all__ = [
    'MarketEmbedder',
    'get_embedder',
    'reset_embedder',
    'PatternVectorStore',
    'PatternMemory',
    'get_vector_store',
    'reset_vector_store',
]
