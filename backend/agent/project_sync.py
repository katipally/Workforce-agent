"""Project Sync Service for Project-Scoped RAG.

Handles syncing data from selected sources (Slack, Gmail, Notion) into
project_chunks with OpenAI embeddings for semantic search.

Supports incremental updates:
- Add new content
- Update changed content (via content_hash)
- Delete removed content (via sync_version)
"""

import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from sqlalchemy import or_, cast
from sqlalchemy.dialects.postgresql import JSONB

from core.database.db_manager import DatabaseManager
from core.database.models import Message, Channel, User, GmailMessage, NotionPage
from core.config import Config
from core.utils.logger import get_logger
from .openai_embeddings import (
    OpenAIEmbeddingService,
    chunk_text,
    format_slack_message_for_embedding,
    format_gmail_message_for_embedding,
    format_notion_page_for_embedding,
)

logger = get_logger(__name__)

# Batch sizes for embedding API calls
EMBEDDING_BATCH_SIZE = 50
MAX_CHUNKS_PER_SOURCE = 500


class ProjectSyncService:
    """Service for syncing project sources into embeddings."""
    
    def __init__(
        self,
        db_manager: DatabaseManager,
        embedding_service: Optional[OpenAIEmbeddingService] = None,
    ):
        """Initialize the sync service.
        
        Args:
            db_manager: Database manager instance
            embedding_service: Optional pre-initialized embedding service
        """
        self.db = db_manager
        self._embedding_service = embedding_service
    
    @property
    def embedding_service(self) -> OpenAIEmbeddingService:
        """Lazy-load embedding service."""
        if self._embedding_service is None:
            self._embedding_service = OpenAIEmbeddingService()
        return self._embedding_service
    
    def sync_project(
        self,
        project_id: str,
        slack_channel_ids: List[str],
        gmail_label_ids: List[str],
        notion_page_ids: List[str],
        gmail_account_email: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Sync all selected sources for a project.
        
        This is the main entry point for project data sync. It:
        1. Fetches data from each source type
        2. Chunks and embeds the content
        3. Stores in project_chunks with incremental update support
        4. Cleans up stale chunks (deleted content)
        
        Args:
            project_id: Project ID to sync
            slack_channel_ids: List of Slack channel IDs to sync
            gmail_label_ids: List of Gmail label IDs to sync
            notion_page_ids: List of Notion page IDs to sync
            gmail_account_email: Gmail account email for scoping
            progress_callback: Optional callback for progress updates
            cancel_check: Optional function to check for cancellation
            
        Returns:
            Dict with sync statistics
        """
        sync_version = datetime.utcnow().isoformat()
        stats = {
            "sync_version": sync_version,
            "slack_chunks": 0,
            "gmail_chunks": 0,
            "notion_chunks": 0,
            "total_chunks": 0,
            "deleted_stale": 0,
            "errors": [],
        }
        
        def _progress(stage: str, progress: float, detail: str = ""):
            if progress_callback:
                progress_callback({
                    "stage": stage,
                    "progress": progress,
                    "detail": detail,
                    "stats": stats,
                })
        
        def _check_cancel():
            if cancel_check and cancel_check():
                raise InterruptedError("Sync cancelled")
        
        try:
            # Stage 1: Sync Slack channels
            if slack_channel_ids:
                _progress("slack", 0.0, "Syncing Slack messages...")
                _check_cancel()
                
                slack_stats = self._sync_slack_channels(
                    project_id=project_id,
                    channel_ids=slack_channel_ids,
                    sync_version=sync_version,
                    progress_callback=lambda p: _progress("slack", p * 0.33, f"Slack: {p*100:.0f}%"),
                    cancel_check=cancel_check,
                )
                stats["slack_chunks"] = slack_stats.get("chunks", 0)
                stats["errors"].extend(slack_stats.get("errors", []))
            
            # Stage 2: Sync Gmail labels
            if gmail_label_ids:
                _progress("gmail", 0.33, "Syncing Gmail messages...")
                _check_cancel()
                
                gmail_stats = self._sync_gmail_labels(
                    project_id=project_id,
                    label_ids=gmail_label_ids,
                    gmail_account_email=gmail_account_email,
                    sync_version=sync_version,
                    progress_callback=lambda p: _progress("gmail", 0.33 + p * 0.33, f"Gmail: {p*100:.0f}%"),
                    cancel_check=cancel_check,
                )
                stats["gmail_chunks"] = gmail_stats.get("chunks", 0)
                stats["errors"].extend(gmail_stats.get("errors", []))
            
            # Stage 3: Sync Notion pages
            if notion_page_ids:
                _progress("notion", 0.66, "Syncing Notion pages...")
                _check_cancel()
                
                notion_stats = self._sync_notion_pages(
                    project_id=project_id,
                    page_ids=notion_page_ids,
                    sync_version=sync_version,
                    progress_callback=lambda p: _progress("notion", 0.66 + p * 0.34, f"Notion: {p*100:.0f}%"),
                    cancel_check=cancel_check,
                )
                stats["notion_chunks"] = notion_stats.get("chunks", 0)
                stats["errors"].extend(notion_stats.get("errors", []))
            
            # Stage 4: Clean up stale chunks
            _progress("cleanup", 0.95, "Cleaning up stale data...")
            deleted = self.db.delete_stale_project_chunks(project_id, sync_version)
            stats["deleted_stale"] = deleted
            
            stats["total_chunks"] = (
                stats["slack_chunks"] + 
                stats["gmail_chunks"] + 
                stats["notion_chunks"]
            )
            
            _progress("completed", 1.0, "Sync completed")
            
            logger.info(
                "Project %s sync completed: %d chunks (%d slack, %d gmail, %d notion), %d stale deleted",
                project_id,
                stats["total_chunks"],
                stats["slack_chunks"],
                stats["gmail_chunks"],
                stats["notion_chunks"],
                stats["deleted_stale"],
            )
            
            return stats
            
        except InterruptedError:
            logger.info("Project %s sync cancelled", project_id)
            raise
        except Exception as e:
            logger.error("Project %s sync failed: %s", project_id, e, exc_info=True)
            stats["errors"].append(str(e))
            raise
    
    def _sync_slack_channels(
        self,
        project_id: str,
        channel_ids: List[str],
        sync_version: str,
        progress_callback: Optional[Callable[[float], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Sync Slack messages from specified channels."""
        stats = {"chunks": 0, "errors": []}
        
        with self.db.get_session() as session:
            # Fetch messages with channel and user info
            query = (
                session.query(Message, Channel, User)
                .join(Channel, Message.channel_id == Channel.channel_id)
                .outerjoin(User, Message.user_id == User.user_id)
                .filter(Message.channel_id.in_(channel_ids))
                .filter(Message.text.isnot(None))
                .filter(Message.text != "")
                .order_by(Message.timestamp.desc())
                .limit(MAX_CHUNKS_PER_SOURCE)
            )
            
            messages = query.all()
        
        if not messages:
            return stats
        
        # Prepare chunks for embedding
        chunks_to_embed = []
        for i, (msg, channel, user) in enumerate(messages):
            if cancel_check and cancel_check():
                raise InterruptedError("Sync cancelled")
            
            user_name = None
            if user:
                user_name = user.real_name or user.display_name or user.username
            
            channel_name = channel.name or channel.channel_id
            
            formatted_text, metadata = format_slack_message_for_embedding(
                message_text=msg.text or "",
                channel_name=channel_name,
                user_name=user_name,
                timestamp=msg.timestamp,
            )
            
            content_hash = self.embedding_service.compute_content_hash(
                formatted_text, metadata
            )
            
            chunks_to_embed.append({
                "source_type": "slack",
                "source_id": msg.channel_id,
                "content_id": msg.message_id,
                "chunk_text": formatted_text,
                "content_hash": content_hash,
                "metadata": metadata,
                "chunk_index": 0,
            })
            
            if progress_callback and i % 50 == 0:
                progress_callback(i / len(messages))
        
        # Generate embeddings in batches
        stats["chunks"] = self._embed_and_store_chunks(
            project_id=project_id,
            chunks=chunks_to_embed,
            sync_version=sync_version,
            cancel_check=cancel_check,
        )
        
        if progress_callback:
            progress_callback(1.0)
        
        return stats
    
    def _sync_gmail_labels(
        self,
        project_id: str,
        label_ids: List[str],
        gmail_account_email: Optional[str],
        sync_version: str,
        progress_callback: Optional[Callable[[float], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Sync Gmail messages from specified labels."""
        stats = {"chunks": 0, "errors": []}
        
        with self.db.get_session() as session:
            query = session.query(GmailMessage)
            
            # Scope by account email
            if gmail_account_email:
                query = query.filter(GmailMessage.account_email == gmail_account_email)
            
            # Filter by labels (stored as JSON array)
            label_filters = [
                cast(GmailMessage.label_ids, JSONB).contains([lbl])
                for lbl in label_ids
            ]
            if label_filters:
                query = query.filter(or_(*label_filters))
            
            emails = (
                query
                .order_by(GmailMessage.date.desc())
                .limit(MAX_CHUNKS_PER_SOURCE)
                .all()
            )
        
        if not emails:
            return stats
        
        # Prepare chunks for embedding
        chunks_to_embed = []
        for i, email in enumerate(emails):
            if cancel_check and cancel_check():
                raise InterruptedError("Sync cancelled")
            
            formatted_text, metadata = format_gmail_message_for_embedding(
                subject=email.subject or "",
                snippet=email.snippet or "",
                body_text=email.body_text,
                from_address=email.from_address or "",
                date=email.date,
                label_ids=email.label_ids,
            )
            
            content_hash = self.embedding_service.compute_content_hash(
                formatted_text, metadata
            )
            
            # For longer emails, chunk the content
            text_chunks = chunk_text(formatted_text, max_chunk_size=1000, overlap=100)
            
            for chunk_text_str, chunk_idx in text_chunks:
                chunks_to_embed.append({
                    "source_type": "gmail",
                    "source_id": ",".join(label_ids),  # Use labels as source_id
                    "content_id": email.message_id,
                    "chunk_text": chunk_text_str,
                    "content_hash": content_hash if chunk_idx == 0 else f"{content_hash}_{chunk_idx}",
                    "metadata": metadata,
                    "chunk_index": chunk_idx,
                })
            
            if progress_callback and i % 20 == 0:
                progress_callback(i / len(emails))
        
        # Generate embeddings in batches
        stats["chunks"] = self._embed_and_store_chunks(
            project_id=project_id,
            chunks=chunks_to_embed,
            sync_version=sync_version,
            cancel_check=cancel_check,
        )
        
        if progress_callback:
            progress_callback(1.0)
        
        return stats
    
    def _sync_notion_pages(
        self,
        project_id: str,
        page_ids: List[str],
        sync_version: str,
        progress_callback: Optional[Callable[[float], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Dict[str, Any]:
        """Sync Notion pages."""
        stats = {"chunks": 0, "errors": []}
        
        with self.db.get_session() as session:
            pages = (
                session.query(NotionPage)
                .filter(NotionPage.page_id.in_(page_ids))
                .all()
            )
        
        if not pages:
            return stats
        
        chunks_to_embed = []
        for i, page in enumerate(pages):
            if cancel_check and cancel_check():
                raise InterruptedError("Sync cancelled")
            
            # Get page content from blocks_data or raw_data
            page_content = ""
            if page.blocks_data:
                # Extract text from blocks
                page_content = self._extract_notion_block_text(page.blocks_data)
            elif page.raw_data:
                # Fallback to raw properties
                props = page.raw_data.get("properties", {})
                for prop_name, prop_value in props.items():
                    if isinstance(prop_value, dict):
                        prop_type = prop_value.get("type", "")
                        if prop_type == "title":
                            titles = prop_value.get("title", [])
                            for t in titles:
                                if isinstance(t, dict) and "plain_text" in t:
                                    page_content += t["plain_text"] + "\n"
                        elif prop_type == "rich_text":
                            texts = prop_value.get("rich_text", [])
                            for t in texts:
                                if isinstance(t, dict) and "plain_text" in t:
                                    page_content += t["plain_text"] + "\n"
            
            if not page_content.strip():
                continue
            
            formatted_text, metadata = format_notion_page_for_embedding(
                title=page.title or "Untitled",
                content=page_content,
                page_id=page.page_id,
                last_edited_time=page.last_edited_time,
            )
            
            content_hash = self.embedding_service.compute_content_hash(
                formatted_text, metadata
            )
            
            # Chunk longer pages
            text_chunks = chunk_text(formatted_text, max_chunk_size=1000, overlap=100)
            
            for chunk_text_str, chunk_idx in text_chunks:
                chunks_to_embed.append({
                    "source_type": "notion",
                    "source_id": page.page_id,
                    "content_id": page.page_id,
                    "chunk_text": chunk_text_str,
                    "content_hash": content_hash if chunk_idx == 0 else f"{content_hash}_{chunk_idx}",
                    "metadata": metadata,
                    "chunk_index": chunk_idx,
                })
            
            if progress_callback and i % 5 == 0:
                progress_callback(i / len(pages))
        
        # Generate embeddings in batches
        stats["chunks"] = self._embed_and_store_chunks(
            project_id=project_id,
            chunks=chunks_to_embed,
            sync_version=sync_version,
            cancel_check=cancel_check,
        )
        
        if progress_callback:
            progress_callback(1.0)
        
        return stats
    
    def _extract_notion_block_text(self, blocks_data: List[Dict[str, Any]]) -> str:
        """Extract plain text from Notion blocks."""
        text_parts = []
        
        def extract_rich_text(rich_texts: List[Dict[str, Any]]) -> str:
            return "".join(
                rt.get("plain_text", "") 
                for rt in rich_texts 
                if isinstance(rt, dict)
            )
        
        for block in blocks_data:
            if not isinstance(block, dict):
                continue
            
            block_type = block.get("type", "")
            block_content = block.get(block_type, {})
            
            if isinstance(block_content, dict):
                rich_text = block_content.get("rich_text", [])
                if rich_text:
                    text_parts.append(extract_rich_text(rich_text))
                
                # Handle special block types
                if block_type == "code":
                    text_parts.append(extract_rich_text(block_content.get("rich_text", [])))
                elif block_type in ("bulleted_list_item", "numbered_list_item", "to_do"):
                    text_parts.append("• " + extract_rich_text(block_content.get("rich_text", [])))
                elif block_type == "heading_1":
                    text_parts.append("# " + extract_rich_text(block_content.get("rich_text", [])))
                elif block_type == "heading_2":
                    text_parts.append("## " + extract_rich_text(block_content.get("rich_text", [])))
                elif block_type == "heading_3":
                    text_parts.append("### " + extract_rich_text(block_content.get("rich_text", [])))
            
            # Recursively handle children
            children = block.get("children", [])
            if children:
                text_parts.append(self._extract_notion_block_text(children))
        
        return "\n".join(filter(None, text_parts))
    
    def _embed_and_store_chunks(
        self,
        project_id: str,
        chunks: List[Dict[str, Any]],
        sync_version: str,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> int:
        """Generate embeddings and store chunks in database."""
        if not chunks:
            return 0
        
        # Generate embeddings in batches
        texts = [c["chunk_text"] for c in chunks]
        
        all_embeddings = []
        for batch_start in range(0, len(texts), EMBEDDING_BATCH_SIZE):
            if cancel_check and cancel_check():
                raise InterruptedError("Sync cancelled")
            
            batch_end = min(batch_start + EMBEDDING_BATCH_SIZE, len(texts))
            batch_texts = texts[batch_start:batch_end]
            
            try:
                batch_embeddings = self.embedding_service.embed_batch(batch_texts)
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error("Failed to generate embeddings for batch: %s", e)
                # Use zero vectors as fallback
                all_embeddings.extend([[0.0] * 1536] * len(batch_texts))
        
        # Add embeddings to chunks
        for i, chunk in enumerate(chunks):
            chunk["embedding"] = all_embeddings[i]
        
        # Store in database
        count = self.db.bulk_upsert_project_chunks(
            project_id=project_id,
            chunks=chunks,
            sync_version=sync_version,
        )
        
        return count
