"""Qwen3 Embedding and Reranking Engine.

Implements Qwen3-Embedding-8B (8192 dims) and Qwen3-Reranker-4B
based on official Hugging Face documentation (Nov 2025).
"""

import torch
import torch.nn.functional as F
from torch import Tensor
from transformers import AutoTokenizer, AutoModel
from typing import List, Tuple
import numpy as np
from tqdm import tqdm
import sys
import os
from pathlib import Path

# Add core directory to path
core_path = Path(__file__).parent.parent / 'core'
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

from utils.logger import get_logger

logger = get_logger(__name__)


def last_token_pool(last_hidden_states: Tensor, attention_mask: Tensor) -> Tensor:
    """Extract last token embeddings (Qwen3 official method)."""
    left_padding = (attention_mask[:, -1].sum() == attention_mask.shape[0])
    if left_padding:
        return last_hidden_states[:, -1]
    else:
        sequence_lengths = attention_mask.sum(dim=1) - 1
        batch_size = last_hidden_states.shape[0]
        return last_hidden_states[
            torch.arange(batch_size, device=last_hidden_states.device), 
            sequence_lengths
        ]


def get_detailed_instruct(task_description: str, query: str) -> str:
    """Format query with task instruction (Qwen3 requirement)."""
    return f'Instruct: {task_description}\nQuery: {query}'


class QwenEmbedding:
    """Qwen3-Embedding-8B model for generating 8192-dim embeddings.
    
    Based on official documentation:
    https://huggingface.co/Qwen/Qwen3-Embedding-8B
    """
    
    def __init__(self, model_name: str = 'Qwen/Qwen3-Embedding-8B', use_gpu: bool = True):
        """Initialize Qwen3 embedding model.
        
        Args:
            model_name: Hugging Face model identifier
            use_gpu: Use GPU if available (recommended for 8B model)
        """
        logger.info(f"Loading {model_name}...")
        
        self.device = torch.device('cuda' if use_gpu and torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {self.device}")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            padding_side='left',
            trust_remote_code=True
        )
        
        # Load model (use FP16 on GPU for speed)
        if self.device.type == 'cuda':
            self.model = AutoModel.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                trust_remote_code=True
            ).cuda()
        else:
            self.model = AutoModel.from_pretrained(
                model_name,
                trust_remote_code=True
            ).to(self.device)
        
        self.model.eval()
        self.max_length = 8192  # Qwen3 supports up to 8192 tokens
        
        logger.info("✓ Qwen3-Embedding-8B loaded successfully")
    
    def encode(
        self,
        texts: List[str],
        batch_size: int = 32,
        task: str = "Given a search query, retrieve relevant documents",
        is_query: bool = True,
        show_progress: bool = False
    ) -> np.ndarray:
        """Generate embeddings for texts.
        
        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing
            task: Task description for query formatting
            is_query: True if embedding queries, False for documents
            show_progress: Show progress bar
            
        Returns:
            numpy array of shape (len(texts), 8192)
        """
        all_embeddings = []
        
        # Format texts (queries need instruction, documents don't)
        formatted_texts = []
        for text in texts:
            if is_query:
                formatted_texts.append(get_detailed_instruct(task, text))
            else:
                formatted_texts.append(text)
        
        # Process in batches
        iterator = range(0, len(formatted_texts), batch_size)
        if show_progress:
            iterator = tqdm(iterator, desc="Generating embeddings")
        
        for i in iterator:
            batch_texts = formatted_texts[i:i+batch_size]
            
            # Tokenize
            batch_dict = self.tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors="pt",
            ).to(self.device)
            
            # Generate embeddings
            with torch.no_grad():
                outputs = self.model(**batch_dict)
                embeddings = last_token_pool(
                    outputs.last_hidden_state,
                    batch_dict['attention_mask']
                )
                
                # Normalize embeddings (L2 normalization)
                embeddings = F.normalize(embeddings, p=2, dim=1)
                
                all_embeddings.append(embeddings.cpu().numpy())
        
        return np.vstack(all_embeddings)
    
    def encode_single(self, text: str, is_query: bool = True) -> np.ndarray:
        """Encode a single text.
        
        Args:
            text: Text to embed
            is_query: True if embedding a query
            
        Returns:
            numpy array of shape (8192,)
        """
        embeddings = self.encode([text], batch_size=1, is_query=is_query, show_progress=False)
        return embeddings[0]
    
    def similarity(self, query_emb: np.ndarray, doc_embs: np.ndarray) -> np.ndarray:
        """Calculate cosine similarity between query and documents.
        
        Args:
            query_emb: Query embedding (8192,)
            doc_embs: Document embeddings (N, 8192)
            
        Returns:
            Similarity scores (N,)
        """
        # Embeddings are already normalized, so dot product = cosine similarity
        return np.dot(doc_embs, query_emb)


class QwenReranker:
    """Qwen3-Reranker-4B model for reranking retrieved documents.
    
    Based on official documentation:
    https://huggingface.co/Qwen/Qwen3-Reranker-4B
    """
    
    def __init__(self, model_name: str = 'Qwen/Qwen3-Reranker-4B', use_gpu: bool = True):
        """Initialize Qwen3 reranker model.
        
        Args:
            model_name: Hugging Face model identifier
            use_gpu: Use GPU if available
        """
        logger.info(f"Loading {model_name}...")
        
        self.device = torch.device('cuda' if use_gpu and torch.cuda.is_available() else 'cpu')
        logger.info(f"Using device: {self.device}")
        
        # Load tokenizer
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name,
            trust_remote_code=True
        )
        
        # Load model
        if self.device.type == 'cuda':
            self.model = AutoModel.from_pretrained(
                model_name,
                torch_dtype=torch.float16,
                trust_remote_code=True
            ).cuda()
        else:
            self.model = AutoModel.from_pretrained(
                model_name,
                trust_remote_code=True
            ).to(self.device)
        
        self.model.eval()
        self.max_length = 512  # Reranker uses shorter context
        
        logger.info("✓ Qwen3-Reranker-4B loaded successfully")
    
    def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: int = 5,
        batch_size: int = 32
    ) -> List[Tuple[str, float]]:
        """Rerank documents by relevance to query.
        
        Args:
            query: Query text
            documents: List of document texts
            top_k: Number of top documents to return
            batch_size: Batch size for processing
            
        Returns:
            List of (document, score) tuples, sorted by score descending
        """
        # Create query-document pairs
        pairs = [[query, doc] for doc in documents]
        scores = []
        
        # Process in batches
        for i in range(0, len(pairs), batch_size):
            batch_pairs = pairs[i:i+batch_size]
            
            # Tokenize
            inputs = self.tokenizer(
                batch_pairs,
                padding=True,
                truncation=True,
                max_length=self.max_length,
                return_tensors='pt'
            ).to(self.device)
            
            # Get relevance scores
            with torch.no_grad():
                outputs = self.model(**inputs)
                batch_scores = outputs.logits.squeeze().cpu().numpy()
                
                # Handle single item case
                if len(batch_pairs) == 1:
                    batch_scores = [batch_scores.item()]
                else:
                    batch_scores = batch_scores.tolist()
                
                scores.extend(batch_scores)
        
        # Sort by score descending
        ranked = sorted(
            zip(documents, scores),
            key=lambda x: x[1],
            reverse=True
        )
        
        return ranked[:top_k]
    
    def score(self, query: str, document: str) -> float:
        """Get relevance score for a single query-document pair.
        
        Args:
            query: Query text
            document: Document text
            
        Returns:
            Relevance score (higher = more relevant)
        """
        results = self.rerank(query, [document], top_k=1, batch_size=1)
        return results[0][1] if results else 0.0
