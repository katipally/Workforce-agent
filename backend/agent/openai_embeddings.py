"""OpenAI Embeddings Service for Project-Scoped RAG.

Uses OpenAI's text-embedding-3-small model (1536 dimensions) for generating
embeddings that are stored in Supabase with pgvector for semantic search.
"""

import hashlib
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

import openai
from tenacity import retry, stop_after_attempt, wait_exponential

from core.config import Config
from core.utils.logger import get_logger

logger = get_logger(__name__)

# OpenAI embedding model configuration
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
MAX_TOKENS_PER_CHUNK = 8000  # Safe limit for embedding model
MAX_BATCH_SIZE = 100  # OpenAI allows up to 2048, but we batch smaller for reliability


class OpenAIEmbeddingService:
    """Service for generating embeddings using OpenAI's API."""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the embedding service.
        
        Args:
            api_key: OpenAI API key. If None, uses Config.OPENAI_API_KEY
        """
        self.api_key = api_key or Config.OPENAI_API_KEY
        if not self.api_key:
            raise ValueError("OpenAI API key is required for embeddings")
        
        self.client = openai.OpenAI(api_key=self.api_key)
        self.model = EMBEDDING_MODEL
        self.dimensions = EMBEDDING_DIMENSIONS
        
        logger.info(f"OpenAI Embedding Service initialized with model: {self.model}")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            List of floats representing the embedding vector
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * self.dimensions
        
        # Truncate if too long (roughly 4 chars per token)
        max_chars = MAX_TOKENS_PER_CHUNK * 4
        if len(text) > max_chars:
            text = text[:max_chars]
        
        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions
        )
        
        return response.data[0].embedding
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for a batch of texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors (same order as input)
        """
        if not texts:
            return []
        
        # Filter and prepare texts
        processed_texts = []
        empty_indices = set()
        max_chars = MAX_TOKENS_PER_CHUNK * 4
        
        for i, text in enumerate(texts):
            if not text or not text.strip():
                empty_indices.add(i)
                processed_texts.append("")  # Placeholder
            else:
                # Truncate if too long
                processed_texts.append(text[:max_chars] if len(text) > max_chars else text)
        
        # Process in batches
        all_embeddings: List[List[float]] = [None] * len(texts)  # type: ignore
        
        for batch_start in range(0, len(processed_texts), MAX_BATCH_SIZE):
            batch_end = min(batch_start + MAX_BATCH_SIZE, len(processed_texts))
            batch_texts = processed_texts[batch_start:batch_end]
            
            # Filter out empty texts for the API call
            non_empty_texts = []
            non_empty_indices = []
            for i, text in enumerate(batch_texts):
                global_idx = batch_start + i
                if global_idx not in empty_indices:
                    non_empty_texts.append(text)
                    non_empty_indices.append(global_idx)
            
            if non_empty_texts:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=non_empty_texts,
                    dimensions=self.dimensions
                )
                
                for j, emb_data in enumerate(response.data):
                    all_embeddings[non_empty_indices[j]] = emb_data.embedding
        
        # Fill in zero vectors for empty texts
        zero_vector = [0.0] * self.dimensions
        for i in empty_indices:
            all_embeddings[i] = zero_vector
        
        return all_embeddings
    
    @staticmethod
    def compute_content_hash(text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Compute a hash of content for change detection.
        
        Args:
            text: The text content
            metadata: Optional metadata to include in hash
            
        Returns:
            SHA-256 hash string (64 chars)
        """
        hash_input = text or ""
        if metadata:
            # Include key metadata fields that indicate content changes
            for key in sorted(metadata.keys()):
                if key in ("timestamp", "date", "last_edited_time", "updated_at"):
                    hash_input += f"|{key}:{metadata[key]}"
        
        return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


def chunk_text(
    text: str,
    max_chunk_size: int = 1000,
    overlap: int = 100,
) -> List[Tuple[str, int]]:
    """Split text into overlapping chunks for embedding.
    
    Args:
        text: Text to chunk
        max_chunk_size: Maximum characters per chunk
        overlap: Number of overlapping characters between chunks
        
    Returns:
        List of (chunk_text, chunk_index) tuples
    """
    if not text:
        return []
    
    text = text.strip()
    if len(text) <= max_chunk_size:
        return [(text, 0)]
    
    chunks = []
    start = 0
    chunk_index = 0
    
    while start < len(text):
        end = start + max_chunk_size
        
        # Try to break at sentence or word boundary
        if end < len(text):
            # Look for sentence boundary
            for sep in [". ", ".\n", "! ", "!\n", "? ", "?\n", "\n\n"]:
                last_sep = text[start:end].rfind(sep)
                if last_sep > max_chunk_size // 2:
                    end = start + last_sep + len(sep)
                    break
            else:
                # Fall back to word boundary
                last_space = text[start:end].rfind(" ")
                if last_space > max_chunk_size // 2:
                    end = start + last_space + 1
        
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((chunk, chunk_index))
            chunk_index += 1
        
        # Move start with overlap
        start = end - overlap if end < len(text) else len(text)
    
    return chunks


def format_slack_message_for_embedding(
    message_text: str,
    channel_name: str,
    user_name: Optional[str],
    timestamp: Optional[float],
) -> Tuple[str, Dict[str, Any]]:
    """Format a Slack message for embedding with metadata.
    
    Returns:
        Tuple of (formatted_text, metadata_dict)
    """
    ts_str = ""
    if timestamp:
        try:
            ts_str = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
    
    author = user_name or "Unknown"
    formatted = f"[Slack #{channel_name}] {author}: {message_text}"
    
    metadata = {
        "source_type": "slack",
        "channel_name": channel_name,
        "author": author,
        "timestamp": timestamp,
        "timestamp_str": ts_str,
    }
    
    return formatted, metadata


def format_gmail_message_for_embedding(
    subject: str,
    snippet: str,
    body_text: Optional[str],
    from_address: str,
    date: Optional[datetime],
    label_ids: Optional[List[str]],
) -> Tuple[str, Dict[str, Any]]:
    """Format a Gmail message for embedding with metadata.
    
    Returns:
        Tuple of (formatted_text, metadata_dict)
    """
    date_str = date.strftime("%Y-%m-%d %H:%M") if date else ""
    
    # Use body if available, otherwise snippet
    content = body_text[:2000] if body_text else snippet
    
    formatted = f"[Email from {from_address}] Subject: {subject}\n{content}"
    
    metadata = {
        "source_type": "gmail",
        "from_address": from_address,
        "subject": subject,
        "date": date.isoformat() if date else None,
        "date_str": date_str,
        "label_ids": label_ids or [],
    }
    
    return formatted, metadata


def format_notion_page_for_embedding(
    title: str,
    content: str,
    page_id: str,
    last_edited_time: Optional[datetime],
) -> Tuple[str, Dict[str, Any]]:
    """Format a Notion page for embedding with metadata.
    
    Returns:
        Tuple of (formatted_text, metadata_dict)
    """
    edit_str = last_edited_time.strftime("%Y-%m-%d %H:%M") if last_edited_time else ""
    
    formatted = f"[Notion: {title}]\n{content}"
    
    metadata = {
        "source_type": "notion",
        "title": title,
        "page_id": page_id,
        "last_edited_time": last_edited_time.isoformat() if last_edited_time else None,
        "last_edited_str": edit_str,
    }
    
    return formatted, metadata
