"""Hybrid RAG Engine with LightRAG + LangChain + LangGraph.

Combines:
- LightRAG for fast retrieval
- LangChain for tool orchestration
- LangGraph for stateful workflows
- sentence-transformers for embeddings and reranking
"""

from typing import TypedDict, List, Dict, Any, Optional, AsyncIterator
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage
import numpy as np
import os
import sys
from pathlib import Path
import requests
from sqlalchemy import or_, cast
from sqlalchemy.dialects.postgresql import JSONB

# Add core directory to path
core_path = Path(__file__).parent.parent / 'core'
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

from .sentence_transformer_engine import (
    SentenceTransformerEmbedding,
    SentenceTransformerReranker,
)
from .langchain_tools import WorkforceTools
from database.db_manager import DatabaseManager
from database.models import Message, GmailMessage, Channel, User, NotionPage
from config import Config
from settings.service import get_effective_notion_token
from utils.logger import get_logger

logger = get_logger(__name__)


class AgentState(TypedDict):
    """State passed through LangGraph workflow."""
    query: str
    intent: str
    entities: Dict[str, Any]
    retrieved_context: List[Dict[str, Any]]
    tool_calls: List[Dict[str, Any]]
    response: str
    sources: List[Dict[str, Any]]
    conversation_history: List[Dict[str, str]]


class HybridRAGEngine:
    """Hybrid RAG engine combining multiple techniques."""
    
    def __init__(
        self,
        openai_api_key: str,
        embedding_model: Optional[SentenceTransformerEmbedding] = None,
        reranker_model: Optional[SentenceTransformerReranker] = None
    ):
        """Initialize hybrid RAG engine.
        
        Args:
            openai_api_key: OpenAI API key
            qwen_embedding: Optional pre-loaded Qwen embedding model
            qwen_reranker: Optional pre-loaded Qwen reranker model
        """
        logger.info("Initializing Hybrid RAG Engine...")
        
        # Initialize embedding / reranker models (lazy loading if not provided)
        self.embedding_model = embedding_model
        self.reranker_model = reranker_model
        
        # Initialize OpenAI (for LLM calls)
        # Using Config.LLM_MODEL (default: gpt-5-nano) for hybrid RAG and intent classification
        # GPT-5 series models only support the default temperature (1.0), so we avoid custom values there.
        base_temperature = 0.1
        if Config.LLM_MODEL.startswith("gpt-5"):
            base_temperature = 1.0
        self.llm = ChatOpenAI(
            model=Config.LLM_MODEL,
            api_key=openai_api_key,
            temperature=base_temperature,
            streaming=True
        )
        
        # Initialize tools
        self.tools = WorkforceTools()
        self.langchain_tools = self.tools.get_langchain_tools()
        
        # Initialize database
        self.db = DatabaseManager()
        
        # Build LangGraph workflow
        self.workflow = self._build_workflow()
        
        logger.info("✓ Hybrid RAG Engine initialized")
    
    def _ensure_models_loaded(self):
        """Lazy load Qwen models if not already loaded."""
        if self.embedding_model is None:
            logger.info("Loading embedding model...")
            self.embedding_model = SentenceTransformerEmbedding(
                model_name=Config.EMBEDDING_MODEL,
                use_gpu=Config.USE_GPU,
            )
        
        if self.reranker_model is None:
            logger.info("Loading reranker model...")
            self.reranker_model = SentenceTransformerReranker(
                model_name=Config.RERANKER_MODEL,
                use_gpu=Config.USE_GPU,
            )
    
    def _search_notion_pages(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Search Notion workspace for pages matching the query.
        
        Uses the Notion Search API at query time (no DB storage) so that
        Notion content can participate in hybrid RAG without schema changes.
        """
        token = get_effective_notion_token(self.db)
        if not token:
            logger.debug("Notion token not configured; skipping Notion search")
            return []

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        payload = {
            "query": query,
            "filter": {"property": "object", "value": "page"},
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            "page_size": min(max(limit, 1), 25),  # keep small for latency
        }

        try:
            response = requests.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json=payload,
                timeout=10,
            )
        except Exception as e:
            logger.error(f"Error calling Notion search API: {e}", exc_info=True)
            return []

        if response.status_code != 200:
            logger.error(
                f"Notion search API error {response.status_code}: {response.text[:200]}"
            )
            return []

        data = response.json()
        results: List[Dict[str, Any]] = []
        for page in data.get("results", [])[:limit]:
            if page.get("object") != "page":
                continue

            properties = page.get("properties", {})
            title_prop = properties.get("title", {}) or properties.get("Name", {})
            title_array = title_prop.get("title") or []
            title = "Untitled"
            if title_array:
                # Use first title segment
                title = title_array[0].get("plain_text") or title

            results.append(
                {
                    "id": page.get("id"),
                    "title": title,
                    "last_edited_time": page.get("last_edited_time"),
                }
            )

        return results

    def _get_notion_page_text(self, page_id: str, max_blocks: int = 50) -> str:
        """Retrieve and flatten a Notion page's top blocks into plain text.

        This is intentionally shallow (first N blocks) to keep latency and
        token usage under control, while still giving the RAG engine a solid
        textual representation of the page.
        """
        token = get_effective_notion_token(self.db)
        if not token or not page_id:
            return ""

        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
        }

        url = f"https://api.notion.com/v1/blocks/{page_id}/children"
        blocks: List[Dict[str, Any]] = []
        next_cursor: Optional[str] = None

        # Paginate until we have max_blocks or run out of content
        while len(blocks) < max_blocks:
            params: Dict[str, Any] = {
                "page_size": min(max_blocks - len(blocks), 100),
            }
            if next_cursor:
                params["start_cursor"] = next_cursor

            try:
                resp = requests.get(
                    url,
                    headers=headers,
                    params=params,
                    timeout=10,
                )
            except Exception as e:
                logger.error(f"Error calling Notion blocks API: {e}", exc_info=True)
                break

            if resp.status_code != 200:
                logger.error(
                    f"Notion blocks API error {resp.status_code}: {resp.text[:200]}"
                )
                break

            data = resp.json()
            batch = data.get("results", [])
            if not batch:
                break

            blocks.extend(batch)
            has_more = data.get("has_more")
            next_cursor = data.get("next_cursor")
            if not has_more or not next_cursor:
                break

        lines: List[str] = []

        for block in blocks[:max_blocks]:
            block_type = block.get("type")
            rich_text_list = None

            if block_type in ("paragraph", "heading_1", "heading_2", "heading_3"):
                rich_text_list = block.get(block_type, {}).get("rich_text", [])
            elif block_type in ("bulleted_list_item", "numbered_list_item", "to_do"):
                rich_text_list = block.get(block_type, {}).get("rich_text", [])

            if not rich_text_list:
                continue

            text = "".join(rt.get("plain_text", "") for rt in rich_text_list).strip()
            if not text:
                continue

            if block_type == "heading_1":
                lines.append(f"# {text}")
            elif block_type == "heading_2":
                lines.append(f"## {text}")
            elif block_type == "heading_3":
                lines.append(f"### {text}")
            else:
                lines.append(text)

        content = "\n".join(lines).strip()
        # Avoid extremely long contexts
        if len(content) > 2000:
            content = content[:2000] + "..."
        return content
    
    def _classify_intent(self, query: str) -> str:
        """Classify user intent (search, action, or hybrid).
        
        Args:
            query: User query
            
        Returns:
            Intent type: "search", "action", or "hybrid"
        """
        # Use main LLM (Config.LLM_MODEL) for intent classification
        system_prompt = """Classify the user's intent into ONE of these categories:
        - "search": User wants to find/retrieve information (e.g., "what did John say?", "find emails about...")
        - "action": User wants to perform an action (e.g., "send a message", "create a page")
        - "hybrid": User wants both (e.g., "find the email and forward it")
        
        Respond with ONLY the category name, nothing else."""
        
        response = self.llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=query)
        ])
        
        intent = response.content.strip().lower()
        if intent not in ["search", "action", "hybrid"]:
            intent = "search"  # Default to search
        
        logger.info(f"Classified intent: {intent}")
        return intent
    
    def _vector_search(
        self,
        query: str,
        limit: int = 20,
        gmail_account_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Semantic search using Qwen3 embeddings.
        
        Args:
            query: Search query
            limit: Number of results
            
        Returns:
            List of matching documents with scores
        """
        self._ensure_models_loaded()
        
        # Generate query embedding
        query_emb = self.embedding_model.encode_single(query, is_query=True)
        
        results = []
        
        with self.db.get_session() as session:
            # Search Slack messages
            slack_messages = session.query(Message).join(Channel).join(User).limit(1000).all()
            
            for msg in slack_messages:
                # Use generic embedding column for semantic search
                if msg.embedding is not None:
                    doc_emb = np.array(msg.embedding)
                    if doc_emb.shape[0] != query_emb.shape[0]:
                        continue
                    score = float(np.dot(query_emb, doc_emb))

                    user_name = None
                    try:
                        if msg.user is not None:
                            user_name = (
                                msg.user.real_name
                                or msg.user.display_name
                                or msg.user.username
                            )
                    except Exception:
                        user_name = None
                    
                    results.append({
                        'type': 'slack',
                        'text': msg.text,
                        'score': float(score),
                        'metadata': {
                            'channel': msg.channel.name,
                            'channel_id': msg.channel_id,
                            'user': user_name,
                            'user_id': msg.user_id,
                            'timestamp': msg.timestamp,
                        }
                    })
            
            # Search Gmail messages
            gmail_query = session.query(GmailMessage)
            if gmail_account_email:
                gmail_query = gmail_query.filter(GmailMessage.account_email == gmail_account_email)

            gmail_messages = gmail_query.limit(1000).all()
            
            for email in gmail_messages:
                # Use generic embedding column for semantic search
                if email.embedding is not None:
                    doc_emb = np.array(email.embedding)
                    if doc_emb.shape[0] != query_emb.shape[0]:
                        continue
                    score = float(np.dot(query_emb, doc_emb))
                    
                    results.append({
                        'type': 'gmail',
                        'text': email.subject + "\n" + (email.body_text[:500] if email.body_text else ""),
                        'score': float(score),
                        'metadata': {
                            'from': email.from_address,
                            'subject': email.subject,
                            'date': email.date,
                            'label_ids': email.label_ids or [],
                        }
                    })
        
        # Search Notion pages semantically at query time (no DB storage)
        try:
            notion_pages = self._search_notion_pages(query, limit=min(limit, 10))
        except Exception as e:
            logger.error(f"Error searching Notion for vector search: {e}", exc_info=True)
            notion_pages = []

        if notion_pages:
            texts: List[str] = []
            meta: List[Dict[str, Any]] = []
            for page in notion_pages:
                page_text = self._get_notion_page_text(page.get('id'), max_blocks=50)
                if not page_text:
                    continue
                full_text = f"{page.get('title', 'Untitled')}\n{page_text}"
                texts.append(full_text)
                meta.append(page)

            if texts:
                try:
                    doc_embs = self.embedding_model.encode(
                        texts,
                        batch_size=min(len(texts), 8),
                        is_query=False,
                        show_progress=False,
                    )
                    for text_doc, emb, page_meta in zip(texts, doc_embs, meta):
                        score = float(np.dot(query_emb, emb))
                        results.append({
                            'type': 'notion',
                            'text': text_doc,
                            'score': score,
                            'metadata': {
                                'page_id': page_meta.get('id'),
                                'title': page_meta.get('title'),
                                'last_edited_time': page_meta.get('last_edited_time')
                            }
                        })
                except Exception as e:
                    logger.error(f"Error embedding Notion documents: {e}", exc_info=True)
        
        # Sort by score descending
        results.sort(key=lambda x: x['score'], reverse=True)
        
        logger.info(f"Vector search found {len(results[:limit])} results")
        return results[:limit]
    
    def _keyword_search(
        self,
        query: str,
        limit: int = 20,
        gmail_account_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Keyword search using PostgreSQL full-text search.
        
        Args:
            query: Search query
            limit: Number of results
            
        Returns:
            List of matching documents
        """
        results = []
        
        with self.db.get_session() as session:
            # Search Slack messages
            slack_messages = (
                session.query(Message)
                .join(Channel)
                .join(User)
                .filter(Message.text.ilike(f'%{query}%'))
                .limit(limit)
                .all()
            )
            
            for msg in slack_messages:
                user_name = None
                try:
                    if msg.user is not None:
                        user_name = (
                            msg.user.real_name
                            or msg.user.display_name
                            or msg.user.username
                        )
                except Exception:
                    user_name = None

                results.append({
                    'type': 'slack',
                    'text': msg.text,
                    'score': 1.0,  # No score for keyword search
                    'metadata': {
                        'channel': msg.channel.name,
                        'channel_id': msg.channel_id,
                        'user': user_name,
                        'user_id': msg.user_id,
                        'timestamp': msg.timestamp,
                    }
                })
            
            # Search Gmail messages
            gmail_query = session.query(GmailMessage).filter(
                (GmailMessage.subject.ilike(f'%{query}%'))
                | (GmailMessage.body_text.ilike(f'%{query}%'))
            )

            if gmail_account_email:
                gmail_query = gmail_query.filter(GmailMessage.account_email == gmail_account_email)

            gmail_messages = gmail_query.limit(limit).all()
            
            for email in gmail_messages:
                results.append({
                    'type': 'gmail',
                    'text': email.subject + "\n" + (email.body_text[:500] if email.body_text else ""),
                    'score': 1.0,
                    'metadata': {
                        'from': email.from_address,
                        'subject': email.subject,
                        'date': email.date,
                        'label_ids': email.label_ids or [],
                    }
                })
        
            # Keyword-style Notion search (via Notion Search API)
            try:
                notion_pages = self._search_notion_pages(query, limit=limit)
            except Exception as e:
                logger.error(f"Error searching Notion for keyword search: {e}", exc_info=True)
                notion_pages = []

            for page in notion_pages:
                page_text = self._get_notion_page_text(page.get('id'), max_blocks=20)
                preview = page_text[:500] if page_text else ""
                results.append({
                    'type': 'notion',
                    'text': f"{page.get('title', 'Untitled')}\n{preview}",
                    'score': 1.0,
                    'metadata': {
                        'page_id': page.get('id'),
                        'title': page.get('title'),
                        'last_edited_time': page.get('last_edited_time')
                    }
                })
        
        logger.info(f"Keyword search found {len(results)} results")
        return results
    
    def _rrf_fusion(
        self,
        vector_results: List[Dict],
        keyword_results: List[Dict],
        k: int = 60
    ) -> List[Dict]:
        """Reciprocal Rank Fusion (RRF) to merge results.
        
        Args:
            vector_results: Results from vector search
            keyword_results: Results from keyword search
            k: RRF constant (default 60)
            
        Returns:
            Fused and ranked results
        """
        # Build document registry
        doc_registry = {}
        
        # Add vector results
        for rank, doc in enumerate(vector_results, 1):
            doc_key = doc['text'][:100]  # Use first 100 chars as key
            if doc_key not in doc_registry:
                doc_registry[doc_key] = {'doc': doc, 'score': 0}
            doc_registry[doc_key]['score'] += 1 / (k + rank)
        
        # Add keyword results
        for rank, doc in enumerate(keyword_results, 1):
            doc_key = doc['text'][:100]
            if doc_key not in doc_registry:
                doc_registry[doc_key] = {'doc': doc, 'score': 0}
            doc_registry[doc_key]['score'] += 1 / (k + rank)
        
        # Sort by fused score
        fused_results = [
            item['doc']
            for item in sorted(
                doc_registry.values(),
                key=lambda x: x['score'],
                reverse=True
            )
        ]
        
        logger.info(f"RRF fusion produced {len(fused_results)} unique results")
        return fused_results
    
    def _vector_search_scoped(
        self,
        query: str,
        channel_ids: Optional[List[str]] = None,
        label_ids: Optional[List[str]] = None,
        notion_page_ids: Optional[List[str]] = None,
        limit: int = 20,
        gmail_account_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Vector search restricted to specific Slack channels, Gmail labels, and Notion pages.

        TRUE SCOPING: Queries database with filters applied FIRST to ensure we only
        retrieve data from the project's linked sources.
        """
        
        # If no filters provided, fall back to global search
        if not channel_ids and not label_ids and not notion_page_ids:
            return self._vector_search(query, limit=limit)
        
        self._ensure_models_loaded()
        
        # Generate query embedding
        query_emb = self.embedding_model.encode_single(query, is_query=True)
        
        results = []
        
        with self.db.get_session() as session:
            # Search ONLY Slack messages from specified channels
            if channel_ids:
                slack_messages = (
                    session.query(Message)
                    .join(Channel)
                    .join(User)
                    .filter(Message.channel_id.in_(channel_ids))
                    .limit(500)
                    .all()
                )
                
                for msg in slack_messages:
                    if msg.embedding is not None:
                        doc_emb = np.array(msg.embedding)
                        if doc_emb.shape[0] != query_emb.shape[0]:
                            continue
                        score = float(np.dot(query_emb, doc_emb))

                        user_name = None
                        try:
                            if msg.user is not None:
                                user_name = (
                                    msg.user.real_name
                                    or msg.user.display_name
                                    or msg.user.username
                                )
                        except Exception:
                            user_name = None
                        
                        results.append({
                            'type': 'slack',
                            'text': msg.text,
                            'score': float(score),
                            'metadata': {
                                'channel': msg.channel.name,
                                'channel_id': msg.channel_id,
                                'user': user_name,
                                'user_id': msg.user_id,
                                'timestamp': msg.timestamp,
                            }
                        })
            
            # Search ONLY Gmail messages with specified labels
            if label_ids:
                # Use JSONB containment to filter by label_ids
                label_filters = [
                    cast(GmailMessage.label_ids, JSONB).contains([lbl])
                    for lbl in label_ids
                ]
                gmail_query = session.query(GmailMessage).filter(or_(*label_filters))

                if gmail_account_email:
                    gmail_query = gmail_query.filter(GmailMessage.account_email == gmail_account_email)

                gmail_messages = gmail_query.limit(500).all()
                
                for email in gmail_messages:
                    if email.embedding is not None:
                        doc_emb = np.array(email.embedding)
                        if doc_emb.shape[0] != query_emb.shape[0]:
                            continue
                        score = float(np.dot(query_emb, doc_emb))
                        
                        results.append({
                            'type': 'gmail',
                            'text': email.subject + "\n" + (email.body_text[:500] if email.body_text else ""),
                            'score': float(score),
                            'metadata': {
                                'from': email.from_address,
                                'subject': email.subject,
                                'date': email.date,
                                'label_ids': email.label_ids or [],
                            }
                        })
            
            # Search ONLY specified Notion pages
            if notion_page_ids:
                notion_pages = (
                    session.query(NotionPage)
                    .filter(NotionPage.page_id.in_(notion_page_ids))
                    .order_by(NotionPage.last_edited_time.desc())
                    .limit(20)
                    .all()
                )
                
                # Generate embeddings for Notion pages on-the-fly if needed
                for page in notion_pages:
                    try:
                        page_text = self._get_notion_page_text(page.page_id, max_blocks=50)
                        if not page_text:
                            continue
                        
                        full_text = f"{page.title or 'Untitled'}\n{page_text}"
                        doc_emb = self.embedding_model.encode_single(full_text, is_query=False)
                        score = float(np.dot(query_emb, doc_emb))
                        
                        results.append({
                            'type': 'notion',
                            'text': full_text,
                            'score': score,
                            'metadata': {
                                'page_id': page.page_id,
                                'title': page.title,
                                'last_edited_time': page.last_edited_time
                            }
                        })
                    except Exception as e:
                        logger.error(f"Error processing Notion page {page.page_id}: {e}")
                        continue
        
        # Sort by score descending
        results.sort(key=lambda x: x['score'], reverse=True)
        
        logger.info(f"Project-scoped vector search found {len(results[:limit])} results from {len(channel_ids or [])} channels, {len(label_ids or [])} labels, {len(notion_page_ids or [])} pages")
        return results[:limit]

    def _keyword_search_scoped(
        self,
        query: str,
        channel_ids: Optional[List[str]] = None,
        label_ids: Optional[List[str]] = None,
        notion_page_ids: Optional[List[str]] = None,
        limit: int = 20,
        gmail_account_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Keyword search restricted to specific Slack channels, Gmail labels, and Notion pages.
        
        TRUE SCOPING: Queries database with filters applied FIRST to ensure we only
        retrieve data from the project's linked sources.
        """
        
        # If no filters provided, fall back to global search
        if not channel_ids and not label_ids and not notion_page_ids:
            return self._keyword_search(query, limit=limit)
        
        results = []
        
        with self.db.get_session() as session:
            # Search ONLY Slack messages from specified channels
            if channel_ids:
                slack_messages = (
                    session.query(Message)
                    .join(Channel)
                    .join(User)
                    .filter(Message.channel_id.in_(channel_ids))
                    .filter(Message.text.ilike(f'%{query}%'))
                    .limit(limit)
                    .all()
                )
                
                for msg in slack_messages:
                    user_name = None
                    try:
                        if msg.user is not None:
                            user_name = (
                                msg.user.real_name
                                or msg.user.display_name
                                or msg.user.username
                            )
                    except Exception:
                        user_name = None
                    
                    results.append({
                        'type': 'slack',
                        'text': msg.text,
                        'score': 1.0,
                        'metadata': {
                            'channel': msg.channel.name,
                            'channel_id': msg.channel_id,
                            'user': user_name,
                            'user_id': msg.user_id,
                            'timestamp': msg.timestamp,
                        }
                    })
            
            # Search ONLY Gmail messages with specified labels
            if label_ids:
                label_filters = [
                    cast(GmailMessage.label_ids, JSONB).contains([lbl])
                    for lbl in label_ids
                ]
                gmail_query = (
                    session.query(GmailMessage)
                    .filter(or_(*label_filters))
                    .filter(
                        or_(
                            GmailMessage.subject.ilike(f'%{query}%'),
                            GmailMessage.body_text.ilike(f'%{query}%')
                        )
                    )
                )

                if gmail_account_email:
                    gmail_query = gmail_query.filter(GmailMessage.account_email == gmail_account_email)

                gmail_messages = gmail_query.limit(limit).all()
                
                for email in gmail_messages:
                    results.append({
                        'type': 'gmail',
                        'text': email.subject + "\n" + (email.body_text[:500] if email.body_text else ""),
                        'score': 1.0,
                        'metadata': {
                            'from': email.from_address,
                            'subject': email.subject,
                            'date': email.date,
                            'label_ids': email.label_ids or [],
                        }
                    })
            
            # Search ONLY specified Notion pages (via Notion API if query is relevant)
            if notion_page_ids:
                # For keyword search, we fetch the specified pages and check if query appears
                notion_pages = (
                    session.query(NotionPage)
                    .filter(NotionPage.page_id.in_(notion_page_ids))
                    .filter(NotionPage.title.ilike(f'%{query}%'))
                    .order_by(NotionPage.last_edited_time.desc())
                    .limit(min(limit, 10))
                    .all()
                )
                
                for page in notion_pages:
                    try:
                        page_text = self._get_notion_page_text(page.page_id, max_blocks=20)
                        preview = page_text[:500] if page_text else ""
                        
                        results.append({
                            'type': 'notion',
                            'text': f"{page.title or 'Untitled'}\n{preview}",
                            'score': 1.0,
                            'metadata': {
                                'page_id': page.page_id,
                                'title': page.title,
                                'last_edited_time': page.last_edited_time
                            }
                        })
                    except Exception as e:
                        logger.error(f"Error processing Notion page {page.page_id}: {e}")
                        continue
        
        logger.info(f"Project-scoped keyword search found {len(results)} results from {len(channel_ids or [])} channels, {len(label_ids or [])} labels, {len(notion_page_ids or [])} pages")
        return results

    def _retrieve_context_scoped(
        self,
        query: str,
        channel_ids: Optional[List[str]] = None,
        label_ids: Optional[List[str]] = None,
        notion_page_ids: Optional[List[str]] = None,
        top_k: int = 5,
        gmail_account_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval with reranking, restricted to specific sources.

        This mirrors _retrieve_context but filters both vector and keyword
        results using the scoped metadata filters before fusion and rerank.
        """

        logger.info("Retrieving project-scoped context for: %s", query)

        # Step 1: Vector search (scoped)
        vector_results = self._vector_search_scoped(
            query,
            channel_ids=channel_ids,
            label_ids=label_ids,
            notion_page_ids=notion_page_ids,
            limit=20,
            gmail_account_email=gmail_account_email,
        )

        # Step 2: Keyword search (scoped)
        keyword_results = self._keyword_search_scoped(
            query,
            channel_ids=channel_ids,
            label_ids=label_ids,
            notion_page_ids=notion_page_ids,
            limit=20,
            gmail_account_email=gmail_account_email,
        )

        # Step 3: RRF fusion
        fused_results = self._rrf_fusion(vector_results, keyword_results)

        # Step 4: Rerank top 30 with cross-encoder reranker
        if len(fused_results) > 0:
            self._ensure_models_loaded()

            candidates = fused_results[:30]
            texts = [doc['text'] for doc in candidates]

            reranked = self.reranker_model.rerank(query, texts, top_k=top_k)

            # Match back to original documents using indices
            final_results: List[Dict[str, Any]] = []
            for idx, score in reranked:
                if 0 <= idx < len(candidates):
                    doc = candidates[idx]
                    doc['rerank_score'] = float(score)
                    final_results.append(doc)

            logger.info(
                "Project-scoped reranking selected top %s documents",
                len(final_results),
            )
            return final_results

        return []

    def _retrieve_context(
        self,
        query: str,
        top_k: int = 5,
        gmail_account_email: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid retrieval with reranking.
        
        Args:
            query: Search query
            top_k: Number of final results
            
        Returns:
            Top-k most relevant documents
        """
        logger.info(f"Retrieving context for: {query}")
        
        # Step 1: Vector search
        vector_results = self._vector_search(
            query,
            limit=20,
            gmail_account_email=gmail_account_email,
        )
        
        # Step 2: Keyword search
        keyword_results = self._keyword_search(
            query,
            limit=20,
            gmail_account_email=gmail_account_email,
        )
        
        # Step 3: RRF fusion
        fused_results = self._rrf_fusion(vector_results, keyword_results)
        
        # Step 4: Rerank top 30 with cross-encoder reranker
        if len(fused_results) > 0:
            self._ensure_models_loaded()
            
            candidates = fused_results[:30]
            texts = [doc['text'] for doc in candidates]
            
            reranked = self.reranker_model.rerank(query, texts, top_k=top_k)
            
            # Match back to original documents using indices
            final_results: List[Dict[str, Any]] = []
            for idx, score in reranked:
                if 0 <= idx < len(candidates):
                    doc = candidates[idx]
                    doc['rerank_score'] = float(score)
                    final_results.append(doc)
            
            logger.info(f"Reranking selected top {len(final_results)} documents")
            return final_results
        
        return []
    
    def _build_workflow(self) -> StateGraph:
        """Build LangGraph workflow."""
        
        def classify_intent_node(state: AgentState) -> AgentState:
            """Classify user intent."""
            intent = self._classify_intent(state['query'])
            return {"intent": intent}
        
        def retrieve_context_node(state: AgentState) -> AgentState:
            """Retrieve relevant context."""
            if state['intent'] in ['search', 'hybrid']:
                context = self._retrieve_context(state['query'], top_k=5)
                return {"retrieved_context": context}
            return {}
        
        def execute_tools_node(state: AgentState) -> AgentState:
            """Execute tools if action intent."""
            if state['intent'] in ['action', 'hybrid']:
                # Use LLM (Config.LLM_MODEL, gpt-5-nano by default) to determine which tool to call
                tool_prompt = f"""Based on this user query: "{state['query']}"
                
Available tools:
{self.tools.get_tool_descriptions()}

Determine if any tool should be called. If yes, respond with ONLY the tool name and parameters as JSON.
If no tool is needed, respond with "NO_TOOL".
"""
                response = self.llm.invoke([
                    SystemMessage(content=tool_prompt),
                    HumanMessage(content=state['query'])
                ])
                
                # Parse and execute tool
                tool_response = response.content.strip()
                if tool_response != "NO_TOOL":
                    # Simple execution (in production, use proper tool calling)
                    return {"tool_calls": [{"result": tool_response}]}
            
            return {}
        
        def generate_response_node(state: AgentState) -> AgentState:
            """Generate final response."""
            # Build context string
            context_str = ""
            sources = []
            
            if state.get('retrieved_context'):
                context_str = "\n\n".join([
                    f"[{doc['type'].upper()}] {doc['text'][:300]}..."
                    for doc in state['retrieved_context']
                ])
                sources = state['retrieved_context']
            
            # Build prompt
            system_prompt = """You are a helpful AI assistant for workplace data. 
Answer questions accurately based on the provided context.
If you don't have enough information, say so.
Always cite your sources."""
            
            user_prompt = f"""Question: {state['query']}

Context:
{context_str}

Answer the question based on the context above. Be concise and accurate."""
            
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ])
            
            return {
                "response": response.content,
                "sources": sources
            }
        
        # Build graph
        workflow = StateGraph(AgentState)
        workflow.add_node("classify", classify_intent_node)
        workflow.add_node("retrieve", retrieve_context_node)
        workflow.add_node("execute", execute_tools_node)
        workflow.add_node("generate", generate_response_node)
        
        # Define edges
        workflow.add_edge(START, "classify")
        workflow.add_edge("classify", "retrieve")
        workflow.add_edge("retrieve", "execute")
        workflow.add_edge("execute", "generate")
        workflow.add_edge("generate", END)
        
        return workflow.compile()
    
    async def query(self, user_query: str, conversation_history: List[Dict] = None) -> Dict[str, Any]:
        """Process a query through the workflow.
        
        Args:
            user_query: User's question
            conversation_history: Optional conversation history
            
        Returns:
            Response dict with answer and sources
        """
        initial_state = {
            "query": user_query,
            "intent": "",
            "entities": {},
            "retrieved_context": [],
            "tool_calls": [],
            "response": "",
            "sources": [],
            "conversation_history": conversation_history or []
        }
        
        result = await self.workflow.ainvoke(initial_state)
        
        return {
            "response": result.get('response', ''),
            "sources": result.get('sources', []),
            "intent": result.get('intent', ''),
            "tool_calls": result.get('tool_calls', [])
        }
    
    def query_project(
        self,
        user_query: str,
        channel_ids: Optional[List[str]] = None,
        label_ids: Optional[List[str]] = None,
        notion_page_ids: Optional[List[str]] = None,
        project_name: Optional[str] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        force_search: bool = False,
        gmail_account_email: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Project-scoped query that only uses data from mapped sources.

        This reuses the same ChatGPT (ChatOpenAI) model as the global RAG
        but restricts retrieval to Slack channels, Gmail labels, and Notion
        pages associated with a given project.
        """

        intent = self._classify_intent(user_query)
        if force_search:
            # Bypass intent classification when the caller knows this is a
            # retrieval-style query (e.g. internal summarization tasks).
            intent = 'search'

        context: List[Dict[str, Any]] = []
        if intent in ['search', 'hybrid']:
            context = self._retrieve_context_scoped(
                user_query,
                channel_ids=channel_ids or [],
                label_ids=label_ids or [],
                notion_page_ids=notion_page_ids or [],
                top_k=5,
                gmail_account_email=gmail_account_email,
            )

            # ------------------------------------------------------------------
            # Fallback: if hybrid RAG returns no context (e.g., embeddings missing
            # or project not yet fully synced), build a lightweight context
            # directly from the database, mirroring the auto-summary endpoint.
            # ------------------------------------------------------------------
            if not context and (channel_ids or label_ids or notion_page_ids):
                db_context: List[Dict[str, Any]] = []
                notion_pages: List[NotionPage] = []

                with self.db.get_session() as session:
                    # Slack: recent messages from mapped channels
                    if channel_ids:
                        slack_query = (
                            session.query(Message, Channel, User)
                            .join(Channel, Message.channel_id == Channel.channel_id)
                            .outerjoin(User, Message.user_id == User.user_id)
                            .filter(Message.channel_id.in_(channel_ids))
                            .order_by(Message.timestamp.desc())
                            .limit(80)
                        )

                        for msg, ch, user in slack_query.all():
                            if not msg.text:
                                continue
                            user_name = None
                            if user is not None:
                                user_name = (
                                    user.real_name
                                    or user.display_name
                                    or user.username
                                )
                            ts = msg.timestamp
                            text = (msg.text or "").replace("\n", " ").strip()
                            db_context.append(
                                {
                                    "type": "slack",
                                    "text": text,
                                    "metadata": {
                                        "channel": ch.name or ch.channel_id,
                                        "channel_id": msg.channel_id,
                                        "user": user_name,
                                        "user_id": msg.user_id,
                                        "timestamp": ts,
                                    },
                                }
                            )

                    # Gmail: recent messages for mapped labels
                    if label_ids:
                        gmail_query = session.query(GmailMessage)

                        # Scope by Gmail account for multi-tenant safety
                        if gmail_account_email:
                            gmail_query = gmail_query.filter(
                                GmailMessage.account_email == gmail_account_email
                            )

                        label_filters = [
                            cast(GmailMessage.label_ids, JSONB).contains([lbl])
                            for lbl in label_ids
                        ]
                        if label_filters:
                            gmail_query = gmail_query.filter(or_(*label_filters))

                        gmail_query = gmail_query.order_by(GmailMessage.date.desc()).limit(40)

                        for email in gmail_query.all():
                            from_addr = email.from_address or "Unknown sender"
                            subject = (email.subject or "No subject").replace("\n", " ").strip()
                            snippet = (
                                email.snippet
                                or (email.body_text[:200] if email.body_text else "")
                            )
                            snippet = (snippet or "").replace("\n", " ").strip()
                            db_context.append(
                                {
                                    "type": "gmail",
                                    "text": f"{subject}: {snippet}",
                                    "metadata": {
                                        "from": from_addr,
                                        "subject": email.subject,
                                        "date": email.date,
                                        "label_ids": email.label_ids or [],
                                    },
                                }
                            )

                    # Notion: a small slice of content from mapped pages
                    if notion_page_ids:
                        notion_pages = (
                            session.query(NotionPage)
                            .filter(NotionPage.page_id.in_(notion_page_ids))
                            .order_by(NotionPage.last_edited_time.desc())
                            .limit(5)
                            .all()
                        )

                # Fetch Notion page text outside the DB session
                for page in notion_pages:
                    try:
                        page_text = self._get_notion_page_text(page.page_id, max_blocks=40)
                    except Exception:
                        page_text = ""

                    if not page_text:
                        continue

                    snippet = page_text.replace("\n", " ").strip()[:400]
                    db_context.append(
                        {
                            "type": "notion",
                            "text": f"{page.title or 'Untitled page'}: {snippet}",
                            "metadata": {
                                "page_id": page.page_id,
                                "title": page.title,
                                "last_edited_time": page.last_edited_time,
                            },
                        }
                    )

                if db_context:
                    logger.info(
                        "Using DB-based project context fallback with %s items",
                        len(db_context),
                    )
                    context = db_context

        # Build context string for the prompt, including human-friendly names
        context_str = ''
        if context:
            lines: List[str] = []
            for doc in context:
                doc_type = (doc.get('type') or '').lower()
                text = (doc.get('text') or '')[:300]
                meta = doc.get('metadata') or {}

                if doc_type == 'slack':
                    channel = meta.get('channel') or meta.get('channel_id') or 'unknown-channel'
                    user = meta.get('user') or meta.get('user_id') or 'someone'
                    prefix = f"[SLACK #{channel} | {user}]"
                elif doc_type == 'gmail':
                    sender = meta.get('from') or 'Unknown sender'
                    subject = meta.get('subject') or 'No subject'
                    prefix = f"[GMAIL {sender} – {subject}]"
                elif doc_type == 'notion':
                    title = meta.get('title') or 'Untitled page'
                    prefix = f"[NOTION {title}]"
                else:
                    prefix = f"[{(doc.get('type') or '').upper()}]"

                lines.append(f"{prefix} {text}...")

            context_str = '\n\n'.join(lines)

        # Optionally incorporate brief conversation history
        history_str = ''
        if conversation_history:
            trimmed = conversation_history[-10:]
            history_lines = []
            for msg in trimmed:
                role = msg.get('role', 'user')
                content = msg.get('content', '')
                prefix = 'User' if role == 'user' else 'Assistant'
                history_lines.append(f"{prefix}: {content}")
            history_str = '\n'.join(history_lines)

        project_label = project_name or 'this project'

        system_prompt = (
            "You are a helpful project assistant for a cross-application project. "
            "You ONLY use the provided context from Slack, Gmail, and Notion that "
            "belongs to this project. If the context is insufficient, say you "
            "don't have enough information instead of guessing. Always keep "
            "answers concise and focused on this project."
        )

        user_prompt_parts = [
            f"Project: {project_label}",
            f"Question: {user_query}",
        ]
        if history_str:
            user_prompt_parts.append("Recent conversation history:\n" + history_str)
        if context_str:
            user_prompt_parts.append("Context:\n" + context_str)

        user_prompt = '\n\n'.join(user_prompt_parts) + '\n\nAnswer based on the project context above.'

        response = self.llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])

        return {
            'response': response.content,
            'sources': context,
            'intent': intent,
        }
    
    async def stream_query(self, user_query: str) -> AsyncIterator[Dict[str, Any]]:
        """Stream query response token by token.
        
        Args:
            user_query: User's question
            
        Yields:
            Dicts with type="token", "sources", or "done"
        """
        # First, get context (not streamed)
        intent = self._classify_intent(user_query)
        
        context = []
        if intent in ['search', 'hybrid']:
            context = self._retrieve_context(user_query, top_k=5)
            
            # Send sources first
            yield {
                "type": "sources",
                "content": context
            }
        
        # Stream LLM response
        context_str = "\n\n".join([
            f"[{doc['type'].upper()}] {doc['text'][:300]}..."
            for doc in context
        ]) if context else ""
        
        system_prompt = """You are a helpful AI assistant. Answer questions based on context provided."""
        user_prompt = f"""Question: {user_query}

Context:
{context_str}

Answer:"""
        
        async for chunk in self.llm.astream([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt)
        ]):
            if chunk.content:
                yield {
                    "type": "token",
                    "content": chunk.content
                }
        
        yield {"type": "done", "content": ""}
