"""
Embedding Synchronization Module.

Automatically generates and syncs embeddings after pipeline runs to ensure:
1. PostgreSQL data is always embedded and available in RAG
2. Embeddings are kept in sync with database state
3. Idempotent updates (no duplicates)

This module bridges Pipeline → PostgreSQL → Embeddings → RAG flow.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import numpy as np

# Setup paths for imports
project_root = Path(__file__).resolve().parents[2]
backend_root = project_root / "backend"
core_root = backend_root / "core"

for p in (backend_root, core_root):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from config import Config
from utils.logger import get_logger
from database.db_manager import DatabaseManager
from database.models import Message, GmailMessage, NotionPage
from agent.sentence_transformer_engine import SentenceTransformerEmbedding

logger = get_logger(__name__)


class EmbeddingSynchronizer:
    """Manages embedding generation and synchronization for all data sources."""
    
    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        """Initialize the embedding synchronizer.
        
        Args:
            db_manager: Database manager instance. If None, creates new one.
        """
        self.db = db_manager or DatabaseManager()
        self.embedding_model = None
        self._model_loaded = False
    
    def _ensure_model_loaded(self):
        """Lazy load the embedding model."""
        if not self._model_loaded:
            logger.info(f"Loading embedding model: {Config.EMBEDDING_MODEL}")
            self.embedding_model = SentenceTransformerEmbedding(
                model_name=Config.EMBEDDING_MODEL,
                use_gpu=Config.USE_GPU
            )
            self._model_loaded = True
            logger.info("✓ Embedding model loaded")
    
    def sync_slack_messages(
        self, 
        channel_ids: Optional[List[str]] = None,
        batch_size: int = 100
    ) -> Dict[str, int]:
        """Generate embeddings for Slack messages.
        
        Args:
            channel_ids: Optional list of channel IDs to sync. If None, syncs all.
            batch_size: Number of messages to process per batch.
            
        Returns:
            Statistics dict with counts of processed and updated messages.
        """
        self._ensure_model_loaded()
        
        stats = {"total": 0, "updated": 0, "skipped": 0, "errors": 0}
        
        with self.db.get_session() as session:
            # Build query
            query = session.query(Message)
            
            if channel_ids:
                query = query.filter(Message.channel_id.in_(channel_ids))
            
            # Only process messages without embeddings or with outdated embeddings
            messages = query.all()
            stats["total"] = len(messages)
            
            if stats["total"] == 0:
                logger.info("No Slack messages to embed")
                return stats
            
            logger.info(f"Embedding {stats['total']} Slack messages...")
            
            # Process in batches
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i + batch_size]
                
                for msg in batch:
                    try:
                        # Skip if already has embedding
                        if msg.embedding is not None:
                            stats["skipped"] += 1
                            continue
                        
                        # Generate text for embedding
                        text_parts = []
                        if msg.text:
                            text_parts.append(msg.text)
                        
                        # Add user context if available
                        if msg.user and msg.user.real_name:
                            text_parts.append(f"From: {msg.user.real_name}")
                        
                        # Add channel context if available
                        if msg.channel and msg.channel.name:
                            text_parts.append(f"Channel: #{msg.channel.name}")
                        
                        text = " ".join(text_parts)
                        
                        if not text.strip():
                            stats["skipped"] += 1
                            continue
                        
                        # Generate embedding
                        embedding = self.embedding_model.encode_single(text)
                        
                        # Store as list (works for both pgvector and JSON)
                        msg.embedding = embedding.tolist()
                        stats["updated"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding Slack message {msg.message_id}: {e}")
                        stats["errors"] += 1
                
                # Commit batch
                session.commit()
                logger.info(f"  Processed {min(i + batch_size, stats['total'])}/{stats['total']} messages")
        
        logger.info(f"✓ Slack embedding sync complete: {stats}")
        return stats
    
    def sync_gmail_messages(
        self,
        label_ids: Optional[List[str]] = None,
        batch_size: int = 100
    ) -> Dict[str, int]:
        """Generate embeddings for Gmail messages.
        
        Args:
            label_ids: Optional list of label IDs to sync. If None, syncs all.
            batch_size: Number of messages to process per batch.
            
        Returns:
            Statistics dict with counts of processed and updated messages.
        """
        self._ensure_model_loaded()
        
        stats = {"total": 0, "updated": 0, "skipped": 0, "errors": 0}
        
        with self.db.get_session() as session:
            query = session.query(GmailMessage)
            
            # Filter by labels if specified
            if label_ids:
                # Filter messages that have any of the specified labels
                from sqlalchemy import cast, or_
                from sqlalchemy.dialects.postgresql import JSONB
                conditions = [
                    cast(GmailMessage.label_ids, JSONB).contains([label_id])
                    for label_id in label_ids
                ]
                query = query.filter(or_(*conditions))
            
            messages = query.all()
            stats["total"] = len(messages)
            
            if stats["total"] == 0:
                logger.info("No Gmail messages to embed")
                return stats
            
            logger.info(f"Embedding {stats['total']} Gmail messages...")
            
            # Process in batches
            for i in range(0, len(messages), batch_size):
                batch = messages[i:i + batch_size]
                
                for msg in batch:
                    try:
                        # Skip if already has embedding
                        if msg.embedding is not None:
                            stats["skipped"] += 1
                            continue
                        
                        # Generate text for embedding
                        text_parts = []
                        
                        if msg.subject:
                            text_parts.append(f"Subject: {msg.subject}")
                        
                        if msg.from_address:
                            text_parts.append(f"From: {msg.from_address}")
                        
                        # Use body_text if available, otherwise snippet
                        body = msg.body_text or msg.snippet or ""
                        if body:
                            text_parts.append(body[:2000])  # Limit body length
                        
                        text = " ".join(text_parts)
                        
                        if not text.strip():
                            stats["skipped"] += 1
                            continue
                        
                        # Generate embedding
                        embedding = self.embedding_model.encode_single(text)
                        
                        # Store as list (works for both pgvector and JSON)
                        msg.embedding = embedding.tolist()
                        stats["updated"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding Gmail message {msg.message_id}: {e}")
                        stats["errors"] += 1
                
                # Commit batch
                session.commit()
                logger.info(f"  Processed {min(i + batch_size, stats['total'])}/{stats['total']} messages")
        
        logger.info(f"✓ Gmail embedding sync complete: {stats}")
        return stats
    
    def sync_notion_pages(
        self,
        workspace_id: Optional[str] = None,
        batch_size: int = 100
    ) -> Dict[str, int]:
        """Generate embeddings for Notion pages.
        
        Args:
            workspace_id: Optional workspace ID to sync. If None, syncs all.
            batch_size: Number of pages to process per batch.
            
        Returns:
            Statistics dict with counts of processed and updated pages.
        """
        self._ensure_model_loaded()
        
        stats = {"total": 0, "updated": 0, "skipped": 0, "errors": 0}
        
        with self.db.get_session() as session:
            query = session.query(NotionPage)
            
            if workspace_id:
                query = query.filter(NotionPage.workspace_id == workspace_id)
            
            pages = query.all()
            stats["total"] = len(pages)
            
            if stats["total"] == 0:
                logger.info("No Notion pages to embed")
                return stats
            
            logger.info(f"Embedding {stats['total']} Notion pages...")
            
            # Process in batches
            for i in range(0, len(pages), batch_size):
                batch = pages[i:i + batch_size]
                
                for page in batch:
                    try:
                        # Skip if already has embedding (check if column exists)
                        if hasattr(page, 'embedding') and page.embedding is not None:
                            stats["skipped"] += 1
                            continue
                        
                        # Generate text for embedding
                        text_parts = []
                        
                        if page.title:
                            text_parts.append(f"Title: {page.title}")
                        
                        # Notion pages don't have direct content field - use title only for now
                        # Full content extraction would require additional Notion API calls
                        
                        text = " ".join(text_parts)
                        
                        if not text.strip():
                            stats["skipped"] += 1
                            continue
                        
                        # Generate embedding
                        embedding = self.embedding_model.encode_single(text)
                        
                        # Store as list (only if column exists)
                        if hasattr(page, 'embedding'):
                            page.embedding = embedding.tolist()
                            stats["updated"] += 1
                        else:
                            stats["skipped"] += 1
                        
                    except Exception as e:
                        logger.error(f"Error embedding Notion page {page.page_id}: {e}")
                        stats["errors"] += 1
                
                # Commit batch
                session.commit()
                logger.info(f"  Processed {min(i + batch_size, stats['total'])}/{stats['total']} pages")
        
        logger.info(f"✓ Notion embedding sync complete: {stats}")
        return stats
    
    def sync_all(self) -> Dict[str, Dict[str, int]]:
        """Synchronize embeddings for all data sources.
        
        Returns:
            Dictionary with stats for each data source.
        """
        logger.info("=" * 80)
        logger.info("FULL EMBEDDING SYNCHRONIZATION")
        logger.info("=" * 80)
        
        results = {}
        
        # Sync Slack
        try:
            results["slack"] = self.sync_slack_messages()
        except Exception as e:
            logger.error(f"Slack sync failed: {e}")
            results["slack"] = {"error": str(e)}
        
        # Sync Gmail
        try:
            results["gmail"] = self.sync_gmail_messages()
        except Exception as e:
            logger.error(f"Gmail sync failed: {e}")
            results["gmail"] = {"error": str(e)}
        
        # Sync Notion
        try:
            results["notion"] = self.sync_notion_pages()
        except Exception as e:
            logger.error(f"Notion sync failed: {e}")
            results["notion"] = {"error": str(e)}
        
        logger.info("=" * 80)
        logger.info("✓ FULL SYNC COMPLETE")
        logger.info(f"Results: {results}")
        logger.info("=" * 80)
        
        return results


def sync_embeddings_after_pipeline(
    data_source: str,
    source_ids: Optional[List[str]] = None,
    db_manager: Optional[DatabaseManager] = None
) -> Dict[str, int]:
    """Convenience function to sync embeddings after a pipeline run.
    
    Args:
        data_source: One of 'slack', 'gmail', 'notion'
        source_ids: Optional list of specific IDs (channel_ids, label_ids, etc.)
        db_manager: Optional database manager instance
        
    Returns:
        Statistics dict from the sync operation
    """
    synchronizer = EmbeddingSynchronizer(db_manager)
    
    if data_source == "slack":
        return synchronizer.sync_slack_messages(channel_ids=source_ids)
    elif data_source == "gmail":
        return synchronizer.sync_gmail_messages(label_ids=source_ids)
    elif data_source == "notion":
        workspace_id = source_ids[0] if source_ids else None
        return synchronizer.sync_notion_pages(workspace_id=workspace_id)
    else:
        raise ValueError(f"Unknown data source: {data_source}")


if __name__ == "__main__":
    # CLI usage: python backend/core/embeddings_sync.py
    synchronizer = EmbeddingSynchronizer()
    synchronizer.sync_all()
