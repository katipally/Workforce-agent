"""Lightweight Sentence Transformer Engine.

CPU-friendly embedding and reranking using sentence-transformers library.
Perfect for development and production without GPU requirements.
"""

from sentence_transformers import SentenceTransformer, CrossEncoder
from typing import List, Tuple
import numpy as np
from tqdm import tqdm
import sys
from pathlib import Path

# Add core directory to path
core_path = Path(__file__).parent.parent / 'core'
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

from utils.logger import get_logger

logger = get_logger(__name__)


class SentenceTransformerEmbedding:
    """Lightweight embedding model using sentence-transformers.
    
    Models:
    - all-MiniLM-L6-v2: 384 dims, ~120MB, very fast (recommended for CPU)
    - all-mpnet-base-v2: 768 dims, ~420MB, better quality
    - all-MiniLM-L12-v2: 384 dims, ~120MB, balanced
    """
    
    def __init__(self, model_name: str = 'sentence-transformers/all-MiniLM-L6-v2', use_gpu: bool = False):
        """Initialize sentence transformer model.
        
        Args:
            model_name: Hugging Face model identifier or local path
            use_gpu: Whether to use GPU (automatically detected by sentence-transformers)
        """
        logger.info(f"Loading {model_name}...")
        
        # Remove 'sentence-transformers/' prefix if present
        if model_name.startswith('sentence-transformers/'):
            model_name = model_name.replace('sentence-transformers/', '')
        
        # sentence-transformers automatically uses GPU if available
        # use_gpu parameter kept for API compatibility with Qwen engine
        self.model = SentenceTransformer(model_name)
        self.embedding_dim = self.model.get_sentence_embedding_dimension()
        
        device = 'cuda' if self.model.device.type == 'cuda' else 'cpu'
        logger.info(f"✓ Model loaded: {model_name}")
        logger.info(f"  Device: {device}")
        logger.info(f"  Embedding dimension: {self.embedding_dim}")
        logger.info(f"  Max sequence length: {self.model.max_seq_length}")
    
    def encode(
        self,
        texts: List[str],
        batch_size: int = 32,
        show_progress: bool = False,
        **kwargs
    ) -> np.ndarray:
        """Generate embeddings for texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            show_progress: Show progress bar
            **kwargs: Additional arguments (for compatibility)
            
        Returns:
            numpy array of shape (len(texts), embedding_dim)
        """
        if not texts:
            return np.array([])
        
        embeddings = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=show_progress,
            convert_to_numpy=True,
            normalize_embeddings=True  # L2 normalization for cosine similarity
        )
        
        return embeddings
    
    def encode_single(self, text: str, is_query: bool = True) -> np.ndarray:
        """Encode a single text.
        
        Args:
            text: Text to embed
            is_query: Whether this is a query (for compatibility with Qwen)
            
        Returns:
            numpy array of shape (embedding_dim,)
        """
        if not text:
            return np.zeros(self.embedding_dim)
        
        embedding = self.model.encode(
            text,
            convert_to_numpy=True,
            normalize_embeddings=True
        )
        
        return embedding
    
    def get_embedding_dim(self) -> int:
        """Get embedding dimension."""
        return self.embedding_dim


class SentenceTransformerReranker:
    """Lightweight reranker using cross-encoders.
    
    Models:
    - ms-marco-MiniLM-L-6-v2: Fast, lightweight (recommended for CPU)
    - ms-marco-MiniLM-L-12-v2: Better quality, slower
    - ms-marco-TinyBERT-L-2-v2: Fastest, smallest
    """
    
    def __init__(self, model_name: str = 'cross-encoder/ms-marco-MiniLM-L-6-v2', use_gpu: bool = False):
        """Initialize cross-encoder reranker.
        
        Args:
            model_name: Hugging Face model identifier
            use_gpu: Whether to use GPU (automatically detected by CrossEncoder)
        """
        logger.info(f"Loading {model_name}...")
        
        # CrossEncoder automatically uses GPU if available
        # use_gpu parameter kept for API compatibility with Qwen engine
        self.model = CrossEncoder(model_name)
        
        device = 'cuda' if hasattr(self.model, 'device') and 'cuda' in str(self.model.device) else 'cpu'
        logger.info(f"✓ Reranker loaded: {model_name}")
        logger.info(f"  Device: {device}")
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = None,
        show_progress: bool = False
    ) -> List[Tuple[int, float]]:
        """Rerank documents by relevance to query.
        
        Args:
            query: Search query
            documents: List of candidate documents
            top_k: Return only top K results (None = all)
            show_progress: Show progress bar
            
        Returns:
            List of (index, score) tuples sorted by relevance
        """
        if not documents:
            return []
        
        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]
        
        # Get relevance scores
        scores = self.model.predict(
            pairs,
            show_progress_bar=show_progress,
            convert_to_numpy=True
        )
        
        # Sort by score descending
        ranked_results = sorted(
            enumerate(scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Return top_k if specified
        if top_k is not None:
            ranked_results = ranked_results[:top_k]
        
        return ranked_results
    
    def compute_score(self, query: str, document: str) -> float:
        """Compute relevance score for a single query-document pair.
        
        Args:
            query: Search query
            document: Document text
            
        Returns:
            Relevance score
        """
        score = self.model.predict([[query, document]])[0]
        return float(score)


# Compatibility aliases for drop-in replacement
class QwenEmbedding(SentenceTransformerEmbedding):
    """Compatibility alias - uses sentence-transformers instead of Qwen."""
    pass


class QwenReranker(SentenceTransformerReranker):
    """Compatibility alias - uses cross-encoder instead of Qwen."""
    pass
