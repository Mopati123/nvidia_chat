"""
Vector Database for Market Pattern Memory

Stores market state embeddings with trajectory outcomes for similarity-based retrieval.
Uses ChromaDB for efficient approximate nearest neighbor search.

First Principles:
- Store: Market embedding → Trajectory outcomes + Metadata
- Query: Similar markets → Retrieve historical success patterns
- Bias: Weight current trajectories by historical success of similar states
"""

import chromadb
import json
import hashlib
import numpy as np
from typing import List, Dict, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class PatternMemory:
    """
    A stored market pattern with trajectory outcomes.
    
    This is the core data structure for pattern memory.
    """
    pattern_id: str
    timestamp: str
    symbol: str
    timeframe: str
    
    # Market state embedding (128-dim, not stored directly)
    embedding_hash: str
    
    # Trajectory outcomes
    trajectories: List[Dict]  # List of {trajectory_id, pnl, success, operators_used}
    
    # Aggregate metrics
    best_trajectory_id: Optional[str]
    best_pnl: float
    avg_pnl: float
    win_rate: float  # % of profitable trajectories
    
    # Market context (for debugging/analysis)
    market_summary: Dict  # {trend, volatility, session, etc.}
    
    # Evidence hash for audit
    evidence_hash: str
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for ChromaDB storage"""
        # ChromaDB only supports primitive types in metadata
        # So we serialize complex types to JSON strings
        data = dict(asdict(self))  # Create a copy
        
        # Serialize list/dict fields to JSON
        for key in ['trajectories', 'market_summary']:
            if key in data and data[key] is not None:
                data[key] = json.dumps(data[key])
        
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'PatternMemory':
        """Create from dictionary with JSON deserialization"""
        # Create a copy to avoid modifying the input
        data = dict(data)
        
        # Deserialize JSON fields
        for key in ['trajectories', 'market_summary']:
            if key in data and isinstance(data[key], str):
                try:
                    data[key] = json.loads(data[key])
                except json.JSONDecodeError:
                    data[key] = {} if key == 'market_summary' else []
        
        return cls(**data)


class PatternVectorStore:
    """
    Vector database for storing and querying market patterns.
    
    Uses ChromaDB with cosine similarity for pattern matching.
    """
    
    COLLECTION_NAME = "market_patterns"
    PERSIST_DIR = Path.home() / ".apexquantumict" / "vector_db"
    
    def __init__(self, collection_name: Optional[str] = None, 
                 persist_dir: Optional[Path] = None):
        self.collection_name = collection_name or self.COLLECTION_NAME
        self.persist_dir = persist_dir or self.PERSIST_DIR
        
        # Ensure directory exists
        self.persist_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize ChromaDB (new API)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}  # Cosine similarity
        )
        
        logger.info(f"Vector store initialized: {self.persist_dir}")
    
    def _compute_embedding_hash(self, embedding: np.ndarray) -> str:
        """Compute hash of embedding for deduplication"""
        # Quantize to reduce noise
        quantized = np.round(embedding, decimals=4)
        return hashlib.sha256(quantized.tobytes()).hexdigest()[:16]
    
    def store_pattern(self,
                     embedding: np.ndarray,
                     symbol: str,
                     timeframe: str,
                     trajectories: List[Dict],
                     market_summary: Optional[Dict] = None,
                     evidence_hash: str = "") -> str:
        """
        Store a market pattern with trajectory outcomes.
        
        Args:
            embedding: 128-dim market state embedding
            symbol: Trading pair (e.g., "EURUSD")
            timeframe: Candle timeframe (e.g., "1h", "15m")
            trajectories: List of trajectory outcomes
            market_summary: Additional context
            evidence_hash: For audit trail
        
        Returns:
            pattern_id: Unique identifier for this pattern
        """
        # Compute pattern ID from embedding
        embedding_hash = self._compute_embedding_hash(embedding)
        pattern_id = f"{symbol}_{timeframe}_{embedding_hash}_{datetime.now().isoformat()}"
        pattern_id = hashlib.sha256(pattern_id.encode()).hexdigest()[:16]
        
        # Aggregate metrics
        pnls = [t.get('pnl', 0) for t in trajectories]
        successes = [t.get('success', False) for t in trajectories]
        
        best_idx = np.argmax(pnls) if pnls else 0
        best_trajectory = trajectories[best_idx] if trajectories else None
        
        memory = PatternMemory(
            pattern_id=pattern_id,
            timestamp=datetime.now().isoformat(),
            symbol=symbol,
            timeframe=timeframe,
            embedding_hash=embedding_hash,
            trajectories=trajectories,
            best_trajectory_id=best_trajectory.get('trajectory_id') if best_trajectory else None,
            best_pnl=float(best_trajectory.get('pnl', 0)) if best_trajectory else 0.0,
            avg_pnl=float(np.mean(pnls)) if pnls else 0.0,
            win_rate=float(np.mean(successes)) if successes else 0.0,
            market_summary=market_summary or {},
            evidence_hash=evidence_hash
        )
        
        # Store in ChromaDB
        self.collection.add(
            ids=[pattern_id],
            embeddings=[embedding.tolist()],
            metadatas=[memory.to_dict()]
        )
        
        logger.debug(f"Stored pattern {pattern_id} for {symbol} ({timeframe})")
        return pattern_id
    
    def query_similar(self,
                     embedding: np.ndarray,
                     symbol: Optional[str] = None,
                     timeframe: Optional[str] = None,
                     top_k: int = 10,
                     min_similarity: float = 0.7) -> List[PatternMemory]:
        """
        Query for similar market patterns.
        
        Args:
            embedding: Query market state embedding
            symbol: Filter by symbol (optional)
            timeframe: Filter by timeframe (optional)
            top_k: Number of results to return
            min_similarity: Minimum cosine similarity (0-1)
        
        Returns:
            List of PatternMemory objects, sorted by similarity
        """
        # Build where clause (new ChromaDB API requires $eq operator and $and for multiple conditions)
        conditions = []
        if symbol:
            conditions.append({"symbol": {"$eq": symbol}})
        if timeframe:
            conditions.append({"timeframe": {"$eq": timeframe}})
        
        if len(conditions) == 1:
            where = conditions[0]
        elif len(conditions) > 1:
            where = {"$and": conditions}
        else:
            where = None
        
        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=[embedding.tolist()],
            n_results=top_k * 2,  # Get more, filter by similarity
            where=where
        )
        
        # Parse results
        memories = []
        if results['ids'] and results['ids'][0]:
            for i, pattern_id in enumerate(results['ids'][0]):
                distance = results['distances'][0][i]
                # Convert cosine distance to similarity (ChromaDB uses distance, not similarity)
                # Cosine distance = 1 - cosine similarity
                similarity = 1 - distance
                
                if similarity >= min_similarity:
                    metadata = results['metadatas'][0][i]
                    memory = PatternMemory.from_dict(metadata)
                    # Add similarity score
                    memory.market_summary['similarity'] = similarity
                    memories.append(memory)
        
        # Sort by similarity and take top_k
        memories.sort(key=lambda m: m.market_summary.get('similarity', 0), reverse=True)
        return memories[:top_k]
    
    def get_pattern(self, pattern_id: str) -> Optional[PatternMemory]:
        """Retrieve a specific pattern by ID"""
        try:
            result = self.collection.get(ids=[pattern_id])
            if result['metadatas']:
                return PatternMemory.from_dict(result['metadatas'][0])
        except Exception as e:
            logger.warning(f"Could not retrieve pattern {pattern_id}: {e}")
        return None
    
    def delete_pattern(self, pattern_id: str) -> bool:
        """Delete a pattern from the database"""
        try:
            self.collection.delete(ids=[pattern_id])
            return True
        except Exception as e:
            logger.error(f"Failed to delete pattern {pattern_id}: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        count = self.collection.count()
        return {
            "total_patterns": count,
            "collection_name": self.collection_name,
            "persist_dir": str(self.persist_dir)
        }
    
    def get_patterns_by_symbol(self, symbol: str, limit: int = 100) -> List[PatternMemory]:
        """Get all patterns for a specific symbol"""
        results = self.collection.get(
            where={"symbol": {"$eq": symbol}},
            limit=limit
        )
        
        memories = []
        if results['metadatas']:
            for metadata in results['metadatas']:
                memories.append(PatternMemory.from_dict(metadata))
        
        return memories
    
    def compute_memory_bias(self,
                           trajectories: List[Any],
                           similar_memories: List[PatternMemory],
                           bias_strength: float = 0.3) -> Dict[str, float]:
        """
        Compute bias weights for trajectories based on historical success.
        
        This is the core RAG (Retrieval-Augmented Generation) logic:
        - Retrieve similar historical patterns
        - Weight current trajectories by how similar patterns performed
        
        Args:
            trajectories: Current candidate trajectories
            similar_memories: Retrieved similar patterns
            bias_strength: How much to weight memory (0-1)
        
        Returns:
            Dict mapping trajectory_id to bias weight (1.0 = neutral)
        """
        if not similar_memories:
            # No memory, neutral weights
            return {t.id if hasattr(t, 'id') else str(i): 1.0 
                   for i, t in enumerate(trajectories)}
        
        # Compute historical success per operator type
        operator_success = {}
        total_weight = 0.0
        
        for memory in similar_memories:
            similarity = memory.market_summary.get('similarity', 0.5)
            weight = similarity * (1 + memory.win_rate)  # Weight by similarity and win rate
            
            for traj in memory.trajectories:
                op_key = tuple(sorted(traj.get('operators_used', [])))
                if op_key not in operator_success:
                    operator_success[op_key] = {'pnl': 0, 'weight': 0, 'count': 0}
                
                operator_success[op_key]['pnl'] += traj.get('pnl', 0) * weight
                operator_success[op_key]['weight'] += weight
                operator_success[op_key]['count'] += 1
            
            total_weight += weight
        
        # Compute bias for current trajectories
        biases = {}
        for i, traj in enumerate(trajectories):
            traj_id = traj.id if hasattr(traj, 'id') else f"traj_{i}"
            
            # Get operators used in this trajectory
            ops = getattr(traj, 'operators_used', []) or getattr(traj, 'operator_scores', {}).keys()
            op_key = tuple(sorted(ops)) if ops else ()
            
            # Look up historical performance
            if op_key in operator_success and operator_success[op_key]['weight'] > 0:
                avg_pnl = (operator_success[op_key]['pnl'] / 
                          operator_success[op_key]['weight'])
                # Convert to bias: positive PnL = higher weight
                bias = 1.0 + (bias_strength * np.tanh(avg_pnl * 10))  # [-1, 1] -> [0.7, 1.3]
            else:
                bias = 1.0  # No memory, neutral
            
            biases[traj_id] = bias
        
        return biases


# Global singleton instance
_vector_store: Optional[PatternVectorStore] = None


def get_vector_store(collection_name: Optional[str] = None) -> PatternVectorStore:
    """Get or create global vector store instance"""
    global _vector_store
    if _vector_store is None:
        _vector_store = PatternVectorStore(collection_name=collection_name)
    return _vector_store


def reset_vector_store():
    """Reset global instance (for testing)"""
    global _vector_store
    _vector_store = None
