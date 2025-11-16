"""FastAPI Backend for Workforce AI Agent.

Main application with WebSocket streaming support.
"""

import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
import json
import os
import sys
import aiofiles
import hashlib
import threading
import uuid
import base64
from datetime import datetime
from pathlib import Path
from email.utils import parsedate_to_datetime
import requests
from sqlalchemy import cast
from sqlalchemy.dialects.postgresql import JSONB

# Add core directory to path
core_path = Path(__file__).parent.parent / 'core'
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

# Add agent directory to path for relative imports
agent_path = Path(__file__).parent.parent / 'agent'
if str(agent_path) not in sys.path:
    sys.path.insert(0, str(agent_path))

from config import Config
from utils.logger import get_logger
from database.db_manager import DatabaseManager
from database.models import (
    Workspace,
    Channel,
    Message,
    User,
    GmailAccount,
    GmailMessage,
    GmailThread,
    NotionWorkspace,
    NotionPage,
)
from slack.extractor import ExtractionCoordinator
from gmail import GmailClient
from notion_export import NotionClient

logger = get_logger(__name__)

# Initialize database manager
db_manager = DatabaseManager()

# Import agent modules after setting up paths
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from agent.hybrid_rag import HybridRAGEngine
from agent.ai_brain import WorkforceAIBrain

# Global variables
rag_engine = None
ai_brain = None
rag_lock: asyncio.Lock | None = None
ai_brain_lock: asyncio.Lock | None = None

# Import appropriate embedding engine based on model name
def _get_embedding_classes():
    """Dynamically select embedding engine based on config."""
    model_name = Config.EMBEDDING_MODEL
    
    # Use lightweight sentence-transformers for non-Qwen models
    if not model_name.startswith('Qwen/'):
        logger.info("Using lightweight sentence-transformers engine")
        from agent.sentence_transformer_engine import (
            SentenceTransformerEmbedding as QwenEmbedding,
            SentenceTransformerReranker as QwenReranker
        )
    else:
        logger.info("Using Qwen engine (requires GPU for best performance)")
        from agent.qwen_engine import QwenEmbedding, QwenReranker
    
    return QwenEmbedding, QwenReranker

QwenEmbedding, QwenReranker = _get_embedding_classes()


async def get_rag_engine() -> HybridRAGEngine:
    """Lazy load and return the RAG engine with concurrency guard."""
    global rag_engine, rag_lock

    if rag_engine:
        return rag_engine

    if rag_lock is None:
        rag_lock = asyncio.Lock()

    async with rag_lock:
        if rag_engine:
            return rag_engine

        loop = asyncio.get_running_loop()
        logger.info("Initializing RAG engine...")

        embedding, reranker = await loop.run_in_executor(
            None,
            lambda: (
                QwenEmbedding(
                    model_name=Config.EMBEDDING_MODEL,
                    use_gpu=Config.USE_GPU
                ),
                QwenReranker(
                    model_name=Config.RERANKER_MODEL,
                    use_gpu=Config.USE_GPU
                ),
            ),
        )

        rag_engine = HybridRAGEngine(
            openai_api_key=Config.OPENAI_API_KEY,
            qwen_embedding=embedding,
            qwen_reranker=reranker
        )

        logger.info("✓ RAG engine initialized")
        return rag_engine


async def get_ai_brain() -> WorkforceAIBrain:
    """Lazy load and return the AI brain (self-aware agent with tools)."""
    global ai_brain, ai_brain_lock

    if ai_brain:
        return ai_brain

    if ai_brain_lock is None:
        ai_brain_lock = asyncio.Lock()

    async with ai_brain_lock:
        if ai_brain:
            return ai_brain

        logger.info("Initializing AI Brain (gpt-5-nano)...")
        rag = await get_rag_engine()

        loop = asyncio.get_running_loop()
        ai_brain_instance = await loop.run_in_executor(
            None,
            lambda: WorkforceAIBrain(
                openai_api_key=Config.OPENAI_API_KEY,
                rag_engine=rag,
                model=Config.LLM_MODEL,
                temperature=0.7,
            ),
        )

        ai_brain = ai_brain_instance
        logger.info("✓ AI Brain initialized with tool calling")
        return ai_brain


# Initialize FastAPI app
app = FastAPI(
    title="Workforce AI Agent API",
    description="AI agent with RAG for Slack, Gmail, and Notion",
    version="1.0.0"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite and CRA
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Request/Response models
class ChatRequest(BaseModel):
    """Chat request model."""
    query: str
    conversation_history: Optional[List[Dict[str, str]]] = None


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    sources: List[Dict[str, Any]]
    intent: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    models_loaded: bool
    ai_brain_loaded: bool
    capabilities: List[str]


# Routes
@app.get("/", response_model=HealthResponse)
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "models_loaded": rag_engine is not None,
        "ai_brain_loaded": ai_brain is not None,
        "capabilities": ["slack", "gmail", "notion", "rag_search"] if ai_brain else []
    }


@app.get("/health")
async def health():
    """Detailed health check."""
    return {
        "status": "ok",
        "models_loaded": rag_engine is not None,
        "ai_brain_loaded": ai_brain is not None,
        "capabilities": ["slack", "gmail", "notion", "rag_search"] if ai_brain else []
    }


@app.post("/api/chat/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest):
    """Non-streaming chat endpoint.
    
    Args:
        request: Chat request with query and optional history
        
    Returns:
        Chat response with answer and sources
    """
    try:
        engine = await get_rag_engine()
        result = await engine.query(
            request.query,
            conversation_history=request.conversation_history
        )
        
        return ChatResponse(
            response=result['response'],
            sources=result['sources'],
            intent=result['intent']
        )
    
    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _truncate_history(history: List[Dict[str, str]], max_messages: int = 40, max_chars: int = 8000) -> List[Dict[str, str]]:
    """Trim conversation history to keep context bounded."""
    if not history:
        return []

    trimmed = history[-max_messages:]
    total_chars = 0
    result = []
    for message in reversed(trimmed):
        content = message.get("content", "")
        total_chars += len(content)
        result.append(message)
        if total_chars >= max_chars:
            break
    return list(reversed(result))


async def _run_in_executor(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


@app.websocket("/api/chat/ws")
async def websocket_chat(websocket: WebSocket):
    """Production-ready WebSocket endpoint with conversation history support.
    
    Features:
    - Self-aware AI that knows its capabilities (Slack, Gmail, Notion)
    - Automatic tool calling based on user intent
    - gpt-5-nano as the main reasoning model
    - Conversation history persistence in database
    - Session management for multiple chats
    - Proper disconnect handling (1000, 1001, 1006)
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    
    # Initialize AI Brain (self-aware agent)
    brain = None
    try:
        brain = await get_ai_brain()
        logger.debug("AI Brain ready (GPT-4 + tools)")
    except Exception as e:
        logger.error(f"Failed to initialize AI Brain: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"Server initialization failed: {str(e)}"
            })
            await websocket.close(code=1011, reason="Server error")
        except:
            pass
        return
    
    try:
        while True:
            # Receive message from client
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect as disconnect:
                # Normal disconnect codes - not errors
                code = disconnect.code
                if code in [1000, 1001, 1006]:  # Normal, going away, abnormal (client refresh)
                    logger.debug(f"Client disconnected normally (code: {code})")
                else:
                    logger.warning(f"Client disconnected with code: {code}")
                break
            except Exception as e:
                logger.error(f"Unexpected receive error: {e}")
                break
            
            try:
                # Parse and validate
                message_data = json.loads(data)
                query = message_data.get('query', '').strip()
                session_id = message_data.get('session_id', 'default')
                
                if not query:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Empty query"
                    })
                    continue
                
                if len(query) > 5000:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Query too long (max 5000 chars)"
                    })
                    continue
                
                logger.info(f"Query: {query[:80]}... (session: {session_id})")
                
                # Ensure session exists
                try:
                    chat_session = await _run_in_executor(db_manager.get_chat_session, session_id)
                    if not chat_session:
                        await _run_in_executor(db_manager.create_chat_session, session_id)
                        logger.debug(f"Created new chat session: {session_id}")
                except Exception as db_error:
                    logger.error(f"Database error: {db_error}", exc_info=True)

                conversation_history: List[Dict[str, str]] = []
                try:
                    history = await _run_in_executor(db_manager.get_chat_history, session_id)
                    conversation_history = _truncate_history(history)
                    logger.debug(
                        "Loaded %s messages from history (trimmed to %s)",
                        len(history),
                        len(conversation_history),
                    )
                except Exception as db_error:
                    logger.error(f"Error loading history: {db_error}")

                try:
                    await _run_in_executor(db_manager.add_chat_message, session_id, 'user', query)
                except Exception as db_error:
                    logger.error(f"Error saving user message: {db_error}")
                
                # Send status
                await websocket.send_json({
                    "type": "status",
                    "content": "Processing..."
                })
                
                # Stream response from AI Brain with conversation history
                assistant_response = ""
                assistant_sources = []
                try:
                    async for event in brain.stream_query(query, conversation_history):
                        try:
                            await websocket.send_json(event)
                            # Collect assistant response for database storage
                            if event.get('type') == 'token':
                                assistant_response += event.get('content', '')
                            elif event.get('type') == 'sources':
                                assistant_sources = event.get('content', [])
                        except WebSocketDisconnect:
                            logger.debug("Client disconnected during streaming")
                            return
                        except Exception as send_error:
                            logger.error(f"Send error: {send_error}")
                            break
                    
                    # Save assistant response to database
                    if assistant_response:
                        try:
                            await _run_in_executor(
                                db_manager.add_chat_message,
                                session_id,
                                'assistant',
                                assistant_response,
                                assistant_sources,
                            )

                            if not conversation_history:
                                title = query[:50] + ('...' if len(query) > 50 else '')
                                await _run_in_executor(db_manager.update_session_title, session_id, title)
                        except Exception as db_error:
                            logger.error(f"Error saving assistant message: {db_error}")
                
                except Exception as stream_error:
                    logger.error(f"Streaming error: {stream_error}", exc_info=True)
                    try:
                        await websocket.send_json({
                            "type": "error",
                            "content": f"Error: {str(stream_error)}"
                        })
                    except:
                        break
            
            except json.JSONDecodeError:
                logger.warning("Invalid JSON received")
                try:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Invalid JSON"
                    })
                except:
                    break
            
            except Exception as e:
                logger.error(f"Processing error: {e}", exc_info=True)
                try:
                    await websocket.send_json({
                        "type": "error",
                        "content": f"Error: {str(e)}"
                    })
                except:
                    break
    
    finally:
        # Clean shutdown - no error logging for normal disconnects
        logger.debug("WebSocket connection closed")
        try:
            await websocket.close()
        except:
            pass


@app.post("/api/models/load")
async def load_models():
    """Pre-load AI models (useful for warmup).
    
    Returns:
        Status message
    """
    try:
        await get_rag_engine()
        return {"status": "ok", "message": "Models loaded successfully"}
    
    except Exception as e:
        logger.error(f"Error loading models: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Chat Session Management Endpoints
# ============================================================================

@app.get("/api/chat/sessions")
async def list_sessions():
    """List all chat sessions ordered by last update.
    
    Returns:
        List of chat sessions with metadata
    """
    try:
        sessions = db_manager.list_chat_sessions(limit=100)
        return {
            "sessions": [
                {
                    "session_id": session.session_id,
                    "title": session.title,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                }
                for session in sessions
            ]
        }
    except Exception as e:
        logger.error(f"Error listing sessions: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/chat/sessions/{session_id}")
async def get_session(session_id: str):
    """Get a specific chat session with all messages.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Session details with messages
    """
    try:
        session = db_manager.get_chat_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        
        # Get messages for this session
        messages = db_manager.get_chat_history(session_id)
        
        return {
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "messages": messages
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session and all its messages.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Success message
    """
    try:
        db_manager.delete_chat_session(session_id)
        return {"status": "ok", "message": "Session deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# File upload configuration
UPLOAD_DIR = Config.FILES_DIR
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp',  # Images
    '.pdf', '.txt', '.csv', '.json',  # Documents
    '.doc', '.docx', '.xls', '.xlsx'  # Office files
}


def get_file_hash(content: bytes) -> str:
    """Generate SHA256 hash of file content."""
    return hashlib.sha256(content).hexdigest()


@app.post("/api/files/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    session_id: Optional[str] = Form(None)
):
    """Upload files and store them for the AI agent.
    
    Files are stored in the data/files directory and can be referenced
    in chat messages. The AI agent can access uploaded files for analysis.
    
    Args:
        files: List of files to upload (max 5 files, 10MB each)
        session_id: Optional session ID to associate files with
        
    Returns:
        List of uploaded file metadata
    """
    try:
        if len(files) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 files allowed per upload")
        
        uploaded_files = []
        
        for file in files:
            # Validate file size (read in chunks to avoid loading large files into memory)
            content = await file.read()
            file_size = len(content)
            
            if file_size > MAX_FILE_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"File {file.filename} exceeds maximum size of 10MB"
                )
            
            # Validate file extension
            file_ext = Path(file.filename or "").suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                raise HTTPException(
                    status_code=400,
                    detail=f"File type {file_ext} not allowed. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
                )
            
            # Generate unique filename using hash and timestamp
            file_hash = get_file_hash(content)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_filename = f"{timestamp}_{file_hash[:12]}{file_ext}"
            
            # Save file
            file_path = UPLOAD_DIR / safe_filename
            UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(file_path, 'wb') as f:
                await f.write(content)
            
            # Store file metadata
            file_metadata = {
                "filename": file.filename,
                "stored_filename": safe_filename,
                "file_path": str(file_path),
                "file_size": file_size,
                "content_type": file.content_type,
                "file_hash": file_hash,
                "uploaded_at": datetime.now().isoformat(),
                "session_id": session_id
            }
            
            uploaded_files.append(file_metadata)
            logger.info(f"File uploaded: {file.filename} -> {safe_filename} ({file_size} bytes)")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "files": uploaded_files,
                "message": f"Successfully uploaded {len(uploaded_files)} file(s)"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading files: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")


@app.get("/api/files/list")
async def list_files(session_id: Optional[str] = None):
    """List uploaded files, optionally filtered by session.
    
    Args:
        session_id: Optional session ID to filter files
        
    Returns:
        List of file metadata
    """
    try:
        files = []
        if UPLOAD_DIR.exists():
            for file_path in UPLOAD_DIR.glob("*"):
                if file_path.is_file():
                    stat = file_path.stat()
                    files.append({
                        "filename": file_path.name,
                        "file_size": stat.st_size,
                        "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
        
        return {"files": files}
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Slack Pipeline Endpoints
# ============================================================================


class SlackPipelineRun(BaseModel):
    """Represents the status of a Slack pipeline run."""

    run_id: str
    status: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    stats: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


# In-memory registry of Slack pipeline runs. This is sufficient for v1 where
# runs are manually triggered and short-lived. If needed, we can persist this
# to the database later.
slack_pipeline_runs: Dict[str, Dict[str, Any]] = {}


def _run_slack_pipeline(run_id: str, include_archived: bool = False, download_files: bool = False) -> None:
    """Background worker that runs the Slack extraction pipeline.

    Uses the existing ExtractionCoordinator to perform a full workspace
    extraction (workspace, users, channels, messages, files) and updates the
    in-memory run registry with progress and statistics.
    """

    logger.info(
        "Starting Slack pipeline run %s (include_archived=%s, download_files=%s)",
        run_id,
        include_archived,
        download_files,
    )

    run_info = slack_pipeline_runs.get(run_id)
    if not run_info:
        # Should not happen, but guard against it.
        slack_pipeline_runs[run_id] = {"run_id": run_id}
        run_info = slack_pipeline_runs[run_id]

    run_info["status"] = "running"
    run_info["started_at"] = datetime.utcnow().isoformat()

    coordinator = ExtractionCoordinator(db_manager=db_manager)

    try:
        results = coordinator.extract_all(
            include_archived=include_archived,
            download_files=download_files,
        )

        stats = results.get("statistics", {}) or {}

        # If a cancel request came in while the extraction was running,
        # we still record stats but mark the run as cancelled instead of
        # completed so the UI reflects the user's intent.
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["stats"] = {
            "users": stats.get("users", 0),
            "channels": stats.get("channels", 0),
            "messages": stats.get("messages", 0),
            "files": stats.get("files", 0),
            "reactions": stats.get("reactions", 0),
        }

        if run_info.get("cancel_requested"):
            run_info["status"] = "cancelled"
            logger.info("Slack pipeline run %s marked as cancelled", run_id)
        else:
            run_info["status"] = "completed"
            logger.info("Slack pipeline run %s completed: %s", run_id, run_info["stats"])

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Slack pipeline run {run_id} failed: {e}", exc_info=True)
        run_info["status"] = "failed"
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["error"] = str(e)


@app.post("/api/pipelines/slack/run")
async def run_slack_pipeline(include_archived: bool = False, download_files: bool = False):
    """Trigger a Slack pipeline run in the background.

    Args:
        include_archived: Whether to include archived channels in extraction.
        download_files: Whether to download Slack file contents as part of the run.

    Returns:
        JSON with the new pipeline run ID and initial status.
    """

    run_id = uuid.uuid4().hex
    slack_pipeline_runs[run_id] = {
        "run_id": run_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "include_archived": include_archived,
        "download_files": download_files,
    }

    thread = threading.Thread(
        target=_run_slack_pipeline,
        args=(run_id, include_archived, download_files),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/pipelines/slack/status/{run_id}")
async def get_slack_pipeline_status(run_id: str):
    """Get the status of a Slack pipeline run."""

    run = slack_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/pipelines/slack/stop/{run_id}")
async def stop_slack_pipeline(run_id: str):
    """Request cancellation of a Slack pipeline run.

    Note: the underlying extraction cannot be force-stopped yet, but the
    run will be marked as cancelling/cancelled so the UI can reflect the
    user's intent.
    """

    run = slack_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run["cancel_requested"] = True
    if run.get("status") in ("pending", "running"):
        run["status"] = "cancelling"
    run["finished_at"] = datetime.utcnow().isoformat()
    return run


@app.get("/api/pipelines/slack/data")
async def get_slack_pipeline_data():
    """Return structured Slack data for the Pipelines UI.

    For v1 this returns:
    - Overall Slack stats (users, channels, messages, files, reactions)
    - Channel list with basic metadata and message counts
    """

    try:
        channels = db_manager.get_all_channels(include_archived=True)
        stats = db_manager.get_statistics()

        channel_data = []
        for ch in channels:
            message_count = db_manager.get_messages_count(channel_id=ch.channel_id)
            channel_data.append(
                {
                    "channel_id": ch.channel_id,
                    "name": ch.name,
                    "is_private": ch.is_private,
                    "is_archived": ch.is_archived,
                    "num_members": ch.num_members,
                    "message_count": message_count,
                }
            )

        return {
            "stats": stats,
            "channels": channel_data,
        }

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error fetching Slack pipeline data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pipelines/slack/messages")
async def get_slack_channel_messages(channel_id: str, limit: int = 200):
    """Return recent messages for a Slack channel for the Pipelines UI.

    This endpoint reads from the existing Slack message tables populated by the
    extraction pipeline and returns basic message metadata plus thread fields
    (thread_ts and reply_count) so the frontend can group messages by thread.
    """

    try:
        # Clamp limit to a reasonable range
        limit = max(1, min(limit, 500))

        with db_manager.get_session() as session:
            query = (
                session.query(Message, User)
                .outerjoin(User, Message.user_id == User.user_id)
                .filter(Message.channel_id == channel_id)
                .order_by(Message.timestamp.desc())
                .limit(limit)
            )

            records = query.all()

            messages: List[Dict[str, Any]] = []
            for msg, user in records:
                user_name = None
                if user:
                    user_name = (
                        user.real_name
                        or user.display_name
                        or user.username
                    )

                messages.append(
                    {
                        "message_id": msg.message_id,
                        "user_id": msg.user_id,
                        "user_name": user_name,
                        "text": msg.text,
                        "timestamp": msg.timestamp,
                        "thread_ts": msg.thread_ts,
                        "reply_count": msg.reply_count,
                        "subtype": msg.subtype,
                    }
                )

        return {"channel_id": channel_id, "messages": messages}

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error fetching Slack channel messages: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Gmail Pipeline Endpoints (label-based incremental sync, in-memory storage)
# ============================================================================


GMAIL_PIPELINE_STATE_FILE = Config.DATA_DIR / "gmail_pipeline_state.json"
gmail_pipeline_runs: Dict[str, Dict[str, Any]] = {}
gmail_run_messages: Dict[str, List[Dict[str, Any]]] = {}


def _load_gmail_state() -> Dict[str, Any]:
    """Load incremental Gmail pipeline state from JSON file."""

    try:
        if GMAIL_PIPELINE_STATE_FILE.exists():
            with open(GMAIL_PIPELINE_STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to load Gmail pipeline state: {e}")
    return {}


def _save_gmail_state(state: Dict[str, Any]) -> None:
    """Persist Gmail pipeline state to JSON file."""

    try:
        GMAIL_PIPELINE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(GMAIL_PIPELINE_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to save Gmail pipeline state: {e}")


def _extract_gmail_body(payload: Dict[str, Any]) -> tuple[str, str]:
    """Extract plain text and HTML body from a Gmail message payload."""

    plain_text = ""
    html_text = ""

    def decode_data(data: str) -> str:
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
        except Exception:
            return ""

    def extract_parts(part: Dict[str, Any]) -> None:
        nonlocal plain_text, html_text

        mime_type = part.get("mimeType", "")
        body = part.get("body", {})

        if body.get("data"):
            if mime_type == "text/plain":
                plain_text += decode_data(body.get("data", ""))
            elif mime_type == "text/html":
                html_text += decode_data(body.get("data", ""))

        for subpart in part.get("parts", []) or []:
            extract_parts(subpart)

    if payload:
        extract_parts(payload)

    return plain_text.strip(), html_text.strip()


def _ensure_gmail_account_profile(client: GmailClient) -> None:
    """Upsert the GmailAccount row for the authenticated user."""

    try:
        profile = client.get_profile()
        if not profile:
            return

        email_address = profile.get("emailAddress") or client.user_email
        if not email_address:
            return

        with db_manager.get_session() as session:
            account = session.query(GmailAccount).filter_by(email=email_address).first()
            if not account:
                account = GmailAccount(email=email_address)
                session.add(account)

            account.history_id = profile.get("historyId")
            account.messages_total = profile.get("messagesTotal", 0)
            account.threads_total = profile.get("threadsTotal", 0)
            account.updated_at = datetime.utcnow()
            session.commit()

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to upsert GmailAccount profile: {e}", exc_info=True)


def _persist_gmail_message_from_full(
    full_msg: Dict[str, Any],
    client: GmailClient,
    date_val: Optional[datetime],
    body_text: str,
    body_html: str,
) -> None:
    """Upsert a GmailMessage row from a full Gmail API message."""

    try:
        msg_id = full_msg.get("id")
        if not msg_id:
            return

        account_email = client.user_email
        if not account_email:
            return

        headers_list = full_msg.get("payload", {}).get("headers", []) or []
        headers = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}

        from_raw = headers.get("from", "")
        to_raw = headers.get("to")
        cc_raw = headers.get("cc")
        bcc_raw = headers.get("bcc")

        label_ids = full_msg.get("labelIds", []) or []
        is_unread = "UNREAD" in label_ids
        is_starred = "STARRED" in label_ids
        is_important = "IMPORTANT" in label_ids
        is_sent = "SENT" in label_ids
        is_draft = "DRAFT" in label_ids

        thread_id = full_msg.get("threadId")

        with db_manager.get_session() as session:
            # Ensure the GmailThread row exists so the foreign key on
            # GmailMessage.thread_id does not fail the insert.
            thread = None
            if thread_id:
                thread = session.query(GmailThread).filter_by(thread_id=thread_id).first()
                if not thread:
                    thread = GmailThread(
                        thread_id=thread_id,
                        account_email=account_email,
                        snippet=full_msg.get("snippet", ""),
                        history_id=full_msg.get("historyId"),
                    )
                    session.add(thread)

            msg = session.query(GmailMessage).filter_by(message_id=msg_id).first()
            if not msg:
                msg = GmailMessage(
                    message_id=msg_id,
                    account_email=account_email,
                    thread_id=thread_id,
                )
                session.add(msg)

            msg.thread_id = thread_id
            msg.history_id = full_msg.get("historyId")
            msg.from_address = from_raw
            msg.to_addresses = to_raw
            msg.cc_addresses = cc_raw
            msg.bcc_addresses = bcc_raw
            msg.subject = headers.get("subject", "")
            msg.date = date_val
            msg.body_text = body_text
            msg.body_html = body_html
            msg.snippet = full_msg.get("snippet", "")
            msg.label_ids = label_ids
            msg.is_unread = is_unread
            msg.is_starred = is_starred
            msg.is_important = is_important
            msg.is_draft = is_draft
            msg.is_sent = is_sent
            msg.raw_data = full_msg
            msg.updated_at = datetime.utcnow()

            # Keep basic thread metadata in sync
            if thread is not None:
                thread.snippet = thread.snippet or full_msg.get("snippet", "")
                thread.history_id = full_msg.get("historyId") or thread.history_id
                thread.message_count = session.query(GmailMessage).filter_by(thread_id=thread_id).count()
                thread.updated_at = datetime.utcnow()

            session.commit()

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to persist Gmail message {full_msg.get('id')}: {e}", exc_info=True)


def _run_gmail_pipeline(run_id: str, label_id: str) -> None:
    """Background worker to fetch new Gmail messages for a specific label.

    Uses GmailClient directly and stores messages in memory keyed by run_id.
    Incremental behavior is controlled by internalDate stored per label in a
    small JSON state file.
    """

    logger.info("Starting Gmail pipeline run %s for label %s", run_id, label_id)

    run_info = gmail_pipeline_runs.get(run_id) or {}
    gmail_pipeline_runs[run_id] = run_info
    run_info.setdefault("cancel_requested", False)
    run_info["status"] = "running"
    run_info["started_at"] = datetime.utcnow().isoformat()
    run_info["label_id"] = label_id

    client = GmailClient()
    if not client.authenticate():
        run_info["status"] = "failed"
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["error"] = "Gmail authentication failed"
        logger.error("Gmail authentication failed for pipeline run %s", run_id)
        return

    # Ensure the GmailAccount row exists/updated for this user so the
    # pipelines view can show Gmail stats similar to Slack.
    _ensure_gmail_account_profile(client)

    state = _load_gmail_state()
    last_ts_ms = int(state.get(label_id) or 0)

    messages: List[Dict[str, Any]] = []
    max_new_messages = 500
    processed_new = 0
    newest_ts_ms = last_ts_ms
    page_token: Optional[str] = None
    stop = False

    try:
        while not stop and processed_new < max_new_messages:
            # Cooperative cancellation support
            if run_info.get("cancel_requested"):
                run_info["status"] = "cancelled"
                run_info["finished_at"] = datetime.utcnow().isoformat()
                run_info["message_count"] = len(messages)
                gmail_run_messages[run_id] = messages
                logger.info("Gmail pipeline run %s cancelled", run_id)
                return

            batch_size = min(100, max_new_messages - processed_new)
            result = client.list_messages(
                max_results=batch_size,
                page_token=page_token,
                label_ids=[label_id],
            )

            msg_list = result.get("messages", []) or []
            if not msg_list:
                break

            for msg_info in msg_list:
                if processed_new >= max_new_messages:
                    stop = True
                    break

                msg_id = msg_info.get("id")
                if not msg_id:
                    continue

                full_msg = client.get_message(msg_id, format="full")
                if not full_msg:
                    continue

                internal_date_ms_str = full_msg.get("internalDate")
                try:
                    internal_date_ms = int(internal_date_ms_str) if internal_date_ms_str else 0
                except Exception:
                    internal_date_ms = 0

                if last_ts_ms and internal_date_ms <= last_ts_ms:
                    stop = True
                    break

                headers_list = full_msg.get("payload", {}).get("headers", []) or []
                headers = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}

                from_raw = headers.get("from", "")
                to_raw = headers.get("to")
                cc_raw = headers.get("cc")
                bcc_raw = headers.get("bcc")
                subject = headers.get("subject", "")
                date_str = headers.get("date")
                try:
                    date_val = parsedate_to_datetime(date_str) if date_str else None
                except Exception:
                    date_val = None

                body_text, body_html = _extract_gmail_body(full_msg.get("payload", {}) or {})

                # Persist into the GmailMessage table so Gmail data is durable
                # across runs and available to the chat/RAG tools.
                _persist_gmail_message_from_full(full_msg, client, date_val, body_text, body_html)

                message_obj = {
                    "id": msg_id,
                    "thread_id": full_msg.get("threadId"),
                    "from": from_raw,
                    "to": to_raw,
                    "cc": cc_raw,
                    "bcc": bcc_raw,
                    "subject": subject,
                    "date": date_val.isoformat() if date_val else None,
                    "snippet": full_msg.get("snippet", ""),
                    "body_text": body_text,
                    "body_html": body_html,
                }
                messages.append(message_obj)
                processed_new += 1

                if internal_date_ms > newest_ts_ms:
                    newest_ts_ms = internal_date_ms

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        # If no new messages were found for this label (common after the
        # first incremental run), still return the latest messages so the
        # UI always shows something useful.
        if not messages:
            try:
                fallback_result = client.list_messages(
                    max_results=50,
                    label_ids=[label_id],
                )
                fallback_list = fallback_result.get("messages", []) or []

                for msg_info in fallback_list:
                    msg_id = msg_info.get("id")
                    if not msg_id:
                        continue

                    full_msg = client.get_message(msg_id, format="full")
                    if not full_msg:
                        continue

                    internal_date_ms_str = full_msg.get("internalDate")
                    try:
                        internal_date_ms = int(internal_date_ms_str) if internal_date_ms_str else 0
                    except Exception:
                        internal_date_ms = 0

                    headers_list = full_msg.get("payload", {}).get("headers", []) or []
                    headers = {h.get("name", "").lower(): h.get("value", "") for h in headers_list}

                    from_raw = headers.get("from", "")
                    to_raw = headers.get("to")
                    cc_raw = headers.get("cc")
                    bcc_raw = headers.get("bcc")
                    subject = headers.get("subject", "")
                    date_str = headers.get("date")
                    try:
                        date_val = parsedate_to_datetime(date_str) if date_str else None
                    except Exception:
                        date_val = None

                    body_text, body_html = _extract_gmail_body(full_msg.get("payload", {}) or {})

                    # Persist fallback messages to the database as well so the
                    # label's history is complete.
                    _persist_gmail_message_from_full(full_msg, client, date_val, body_text, body_html)

                    message_obj = {
                        "id": msg_id,
                        "thread_id": full_msg.get("threadId"),
                        "from": from_raw,
                        "to": to_raw,
                        "cc": cc_raw,
                        "bcc": bcc_raw,
                        "subject": subject,
                        "date": date_val.isoformat() if date_val else None,
                        "snippet": full_msg.get("snippet", ""),
                        "body_text": body_text,
                        "body_html": body_html,
                    }
                    messages.append(message_obj)

                    if internal_date_ms > newest_ts_ms:
                        newest_ts_ms = internal_date_ms

            except Exception as e:  # pragma: no cover - defensive logging
                logger.error(f"Fallback Gmail fetch failed for run {run_id}: {e}", exc_info=True)

        gmail_run_messages[run_id] = messages
        run_info["status"] = "completed"
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["message_count"] = len(messages)

        if newest_ts_ms > last_ts_ms:
            state[label_id] = newest_ts_ms
            _save_gmail_state(state)

        logger.info(
            "Gmail pipeline run %s completed for label %s with %s messages",
            run_id,
            label_id,
            len(messages),
        )

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Gmail pipeline run {run_id} failed: {e}", exc_info=True)
        run_info["status"] = "failed"
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["error"] = str(e)


@app.get("/api/pipelines/gmail/labels")
async def list_gmail_labels():
    """List available Gmail labels using the Gmail API."""

    client = GmailClient()
    if not client.authenticate():
        raise HTTPException(status_code=500, detail="Gmail authentication failed")

    labels = client.list_labels() or []
    return {
        "labels": [
            {"id": lbl.get("id"), "name": lbl.get("name"), "type": lbl.get("type")}
            for lbl in labels
            if lbl.get("id") and lbl.get("name")
        ]
    }


@app.post("/api/pipelines/gmail/run")
async def run_gmail_pipeline(label_id: str):
    """Trigger a Gmail pipeline run for a specific label.

    Args:
        label_id: Gmail label ID to fetch messages for.
    """

    if not label_id:
        raise HTTPException(status_code=400, detail="label_id is required")

    run_id = uuid.uuid4().hex
    gmail_pipeline_runs[run_id] = {
        "run_id": run_id,
        "label_id": label_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
        "cancel_requested": False,
    }

    thread = threading.Thread(target=_run_gmail_pipeline, args=(run_id, label_id), daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/pipelines/gmail/status/{run_id}")
async def get_gmail_pipeline_status(run_id: str):
    """Get the status of a Gmail pipeline run."""

    run = gmail_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/pipelines/gmail/stop/{run_id}")
async def stop_gmail_pipeline(run_id: str):
    """Request cancellation of a Gmail pipeline run."""

    run = gmail_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run["cancel_requested"] = True
    if run.get("status") in ("pending", "running"):
        run["status"] = "cancelling"
    run["finished_at"] = datetime.utcnow().isoformat()
    return run


@app.get("/api/pipelines/gmail/messages")
async def get_gmail_pipeline_messages(run_id: str):
    """Return messages for a specific Gmail pipeline run."""

    run = gmail_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    label_id = run.get("label_id")

    # Always prefer DB-backed messages when available, but fall back to the
    # in-memory run results so the user sees emails immediately after a run
    # even if persistence is not working yet or the label filter returns zero
    # rows.
    db_messages: List[Dict[str, Any]] = []

    if label_id:
        try:
            with db_manager.get_session() as session:
                query = (
                    session.query(GmailMessage)
                    .filter(cast(GmailMessage.label_ids, JSONB).contains([label_id]))
                    .order_by(GmailMessage.date.asc())
                    .limit(500)
                )

                rows = query.all()

                for msg in rows:
                    db_messages.append(
                        {
                            "id": msg.message_id,
                            "thread_id": msg.thread_id,
                            "from": msg.from_address,
                            "to": msg.to_addresses,
                            "cc": msg.cc_addresses,
                            "bcc": msg.bcc_addresses,
                            "subject": msg.subject,
                            "date": msg.date.isoformat() if msg.date else None,
                            "snippet": msg.snippet,
                            "body_text": msg.body_text,
                            "body_html": msg.body_html,
                        }
                    )

        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(
                f"Error reading Gmail messages from DB for run {run_id}: {e}",
                exc_info=True,
            )

    in_memory = gmail_run_messages.get(run_id, [])
    messages = db_messages if db_messages else in_memory

    return {
        "run_id": run_id,
        "label_id": label_id,
        "messages": messages,
    }


@app.get("/api/pipelines/gmail/messages/by-label")
async def get_gmail_messages_by_label(label_id: str, limit: int = 200):
    """Return stored Gmail messages for a specific label from the database.

    This lets the Pipelines UI show previously-synced data for any label
    without requiring a new pipeline run each time the user switches labels.
    """

    if not label_id:
        raise HTTPException(status_code=400, detail="label_id is required")

    # Clamp limit to a reasonable range
    limit = max(1, min(limit, 1000))

    try:
        messages: List[Dict[str, Any]] = []
        with db_manager.get_session() as session:
            query = (
                session.query(GmailMessage)
                .filter(cast(GmailMessage.label_ids, JSONB).contains([label_id]))
                .order_by(GmailMessage.date.asc())
                .limit(limit)
            )

            rows = query.all()

            for msg in rows:
                messages.append(
                    {
                        "id": msg.message_id,
                        "thread_id": msg.thread_id,
                        "from": msg.from_address,
                        "to": msg.to_addresses,
                        "cc": msg.cc_addresses,
                        "bcc": msg.bcc_addresses,
                        "subject": msg.subject,
                        "date": msg.date.isoformat() if msg.date else None,
                        "snippet": msg.snippet,
                        "body_text": msg.body_text,
                        "body_html": msg.body_html,
                    }
                )

        return {"label_id": label_id, "messages": messages}
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error fetching Gmail messages for label {label_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load Gmail messages for label")

# ============================================================================


notion_pipeline_runs: Dict[str, Dict[str, Any]] = {}
notion_run_pages: Dict[str, List[Dict[str, Any]]] = {}


def _extract_notion_title(page: Dict[str, Any]) -> str:
    """Extract a human-readable title from a Notion page object."""

    properties = page.get("properties", {}) or {}
    for prop in properties.values():
        if prop.get("type") == "title":
            title_parts = prop.get("title", []) or []
            texts: List[str] = []
            for part in title_parts:
                text_obj = part.get("plain_text") or part.get("text", {}).get("content")
                if text_obj:
                    texts.append(text_obj)
            if texts:
                return "".join(texts)

    # Fallback for database objects which expose their title at the top level
    top_title = page.get("title")
    if isinstance(top_title, list):
        texts: List[str] = []
        for part in top_title:
            if not isinstance(part, dict):
                continue
            text_obj = part.get("plain_text") or part.get("text", {}).get("content")
            if text_obj:
                texts.append(text_obj)
        if texts:
            return "".join(texts)
    return "Untitled"


def _summarize_notion_properties(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return a lightweight summary of Notion page/database properties.

    This is used by the Pipelines UI to show a Gmail-like info panel when a
    page or database row is expanded in the accordion.
    """

    if not isinstance(raw, dict):
        return []

    properties = raw.get("properties", {}) or {}
    items: List[Dict[str, Any]] = []

    for name, prop in properties.items():
        if not isinstance(prop, dict):
            continue
        p_type = prop.get("type") or "unknown"
        value_str = ""

        try:
            if p_type in ("title", "rich_text"):
                parts = prop.get(p_type, []) or []
                texts: List[str] = []
                for part in parts:
                    if not isinstance(part, dict):
                        continue
                    text_obj = part.get("plain_text") or part.get("text", {}).get("content")
                    if text_obj:
                        texts.append(text_obj)
                value_str = "".join(texts)
            elif p_type in ("select", "status"):
                opt = prop.get(p_type) or {}
                if isinstance(opt, dict):
                    value_str = opt.get("name") or ""
            elif p_type == "multi_select":
                opts = prop.get("multi_select", []) or []
                names = [o.get("name") for o in opts if isinstance(o, dict) and o.get("name")]
                value_str = ", ".join(names)
            elif p_type == "checkbox":
                value_str = "true" if prop.get("checkbox") else "false"
            elif p_type == "number":
                num = prop.get("number")
                value_str = str(num) if num is not None else ""
            elif p_type == "date":
                date_obj = prop.get("date") or {}
                if isinstance(date_obj, dict):
                    start = date_obj.get("start") or ""
                    end = date_obj.get("end") or ""
                    value_str = f"{start} → {end}" if end else start
            else:
                # Fallback: best-effort stringification of the typed value
                inner = prop.get(p_type)
                if isinstance(inner, (str, int, float)):
                    value_str = str(inner)
        except Exception:  # pragma: no cover - defensive
            value_str = ""

        items.append({"name": name, "type": p_type, "value": value_str})

    return items


def _summarize_notion_blocks(blocks: List[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
    lines: List[str] = []
    attachments: List[Dict[str, Any]] = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if not block_type:
            continue

        value = block.get(block_type) or {}

        if block_type in (
            "paragraph",
            "heading_1",
            "heading_2",
            "heading_3",
            "quote",
            "callout",
            "to_do",
            "bulleted_list_item",
            "numbered_list_item",
        ):
            rich_text = value.get("rich_text") or []
            parts: List[str] = []
            for rt in rich_text:
                if not isinstance(rt, dict):
                    continue
                text_obj = rt.get("plain_text") or rt.get("text", {}).get("content")
                if text_obj:
                    parts.append(text_obj)
            text_line = "".join(parts).strip()
            if text_line:
                lines.append(text_line)

        if block_type in ("image", "file", "pdf", "video"):
            caption_texts: List[str] = []
            for rt in value.get("caption") or []:
                if not isinstance(rt, dict):
                    continue
                txt = rt.get("plain_text") or rt.get("text", {}).get("content")
                if txt:
                    caption_texts.append(txt)
            name = "".join(caption_texts) if caption_texts else None

            url: Optional[str] = None
            file_kind = value.get("type")
            if file_kind == "file":
                inner = value.get("file") or {}
                url = inner.get("url")
            elif file_kind == "external":
                inner = value.get("external") or {}
                url = inner.get("url")

            attachments.append(
                {
                    "id": block.get("id"),
                    "type": block_type,
                    "name": name or block.get("id"),
                    "url": url,
                }
            )

    return lines, attachments


def _persist_notion_pages(
    workspace_id: str,
    workspace_name: str,
    pages: List[Dict[str, Any]],
    full_refresh: bool = False,
) -> None:
    """Persist Notion pages into the local database.

    When ``full_refresh`` is True, pages that are no longer returned by the
    workspace-wide search are removed from the local table so deletions and
    unshared pages are reflected in the UI. For cancelled runs we keep
    ``full_refresh`` False so we don't accidentally delete data based on a
    partial result set.
    """

    if not pages:
        return

    try:
        with db_manager.get_session() as session:
            workspace = (
                session.query(NotionWorkspace)
                .filter_by(workspace_id=workspace_id)
                .first()
            )

            if not workspace:
                workspace = NotionWorkspace(
                    workspace_id=workspace_id,
                    name=workspace_name or "Notion Workspace",
                )
                session.add(workspace)
            else:
                if workspace_name:
                    workspace.name = workspace_name
                workspace.updated_at = datetime.utcnow()

            seen_ids: set[str] = set()

            for p in pages:
                page_id = p.get("id")
                if not page_id:
                    continue

                seen_ids.add(page_id)

                db_page = (
                    session.query(NotionPage)
                    .filter_by(page_id=page_id)
                    .first()
                )

                if not db_page:
                    db_page = NotionPage(
                        page_id=page_id,
                        workspace_id=workspace.workspace_id,
                    )
                    session.add(db_page)

                db_page.object_type = p.get("object_type")
                db_page.title = p.get("title")
                db_page.url = p.get("url")
                db_page.parent_id = p.get("parent_id")

                last_edited_str = p.get("last_edited_time")
                if last_edited_str:
                    try:
                        db_page.last_edited_time = datetime.fromisoformat(
                            last_edited_str.replace("Z", "+00:00")
                        )
                    except Exception:
                        pass

                raw = p.get("raw")
                if raw is not None:
                    db_page.raw_data = raw

            session.commit()

            if full_refresh and seen_ids:
                (
                    session.query(NotionPage)
                    .filter(NotionPage.workspace_id == workspace_id)
                    .filter(~NotionPage.page_id.in_(seen_ids))
                    .delete(synchronize_session=False)
                )
                session.commit()

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to persist Notion pages: {e}", exc_info=True)


def _run_notion_pipeline(run_id: str) -> None:
    """Background worker to fetch Notion pages under NOTION_PARENT_PAGE_ID."""

    run_info = notion_pipeline_runs.get(run_id) or {}
    notion_pipeline_runs[run_id] = run_info
    run_info.setdefault("cancel_requested", False)
    run_info["status"] = "running"
    run_info["started_at"] = datetime.utcnow().isoformat()

    token = Config.NOTION_TOKEN
    if not token:
        run_info["status"] = "failed"
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["error"] = "NOTION_TOKEN is not configured. Please set it in your environment."
        logger.error("Notion pipeline run %s failed: NOTION_TOKEN is not configured", run_id)
        return

    workspace_id = Config.WORKSPACE_ID or "default-notion-workspace"
    workspace_name = Config.WORKSPACE_NAME or "Notion Workspace"

    pages: List[Dict[str, Any]] = []
    max_pages = 500

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        base_payload: Dict[str, Any] = {
            "page_size": 50,
            # No filter here so we see both pages and databases that are
            # shared with the integration across the workspace.
            "sort": {"direction": "descending", "timestamp": "last_edited_time"},
        }
        start_cursor: Optional[str] = None

        while True:
            # Cooperative cancellation check so long-running searches can be
            # stopped from the UI.
            if notion_pipeline_runs.get(run_id, {}).get("cancel_requested"):
                run_info["status"] = "cancelled"
                run_info["finished_at"] = datetime.utcnow().isoformat()
                run_info["page_count"] = len(pages)
                notion_run_pages[run_id] = pages
                _persist_notion_pages(workspace_id, workspace_name, pages, full_refresh=False)
                logger.info("Notion pipeline run %s cancelled", run_id)
                return

            if len(pages) >= max_pages:
                break

            payload = dict(base_payload)
            if start_cursor:
                payload["start_cursor"] = start_cursor

            response = requests.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json=payload,
                timeout=30,
            )

            if response.status_code != 200:
                logger.error(
                    "Notion search API error %s: %s",
                    response.status_code,
                    response.text[:200],
                )
                run_info["status"] = "failed"
                run_info["finished_at"] = datetime.utcnow().isoformat()
                run_info["error"] = f"Notion API error {response.status_code}"
                return

            data = response.json()
            results = data.get("results", []) or []

            for page in results:
                obj_type = page.get("object")
                if obj_type not in ("page", "database"):
                    continue

                parent_obj = page.get("parent", {}) or {}
                parent_type = parent_obj.get("type")
                parent_id: Optional[str] = None
                if parent_type == "page_id":
                    parent_id = parent_obj.get("page_id")
                elif parent_type == "database_id":
                    parent_id = parent_obj.get("database_id")

                pages.append(
                    {
                        "id": page.get("id"),
                        "title": _extract_notion_title(page),
                        "url": page.get("url"),
                        "last_edited_time": page.get("last_edited_time"),
                        "object_type": obj_type,
                        "parent_id": parent_id,
                        "raw": page,
                    }
                )

                if len(pages) >= max_pages:
                    break

            if len(pages) >= max_pages:
                break

            if not data.get("has_more"):
                break
            start_cursor = data.get("next_cursor")

        notion_run_pages[run_id] = pages
        _persist_notion_pages(workspace_id, workspace_name, pages, full_refresh=True)
        run_info["status"] = "completed"
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["page_count"] = len(pages)

        logger.info("Notion pipeline run %s completed with %s pages", run_id, len(pages))

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Notion pipeline run {run_id} failed: {e}", exc_info=True)
        run_info["status"] = "failed"
        run_info["finished_at"] = datetime.utcnow().isoformat()
        run_info["error"] = str(e)


@app.post("/api/pipelines/notion/run")
async def run_notion_pipeline():
    """Trigger a Notion pipeline run to list pages under NOTION_PARENT_PAGE_ID."""

    run_id = uuid.uuid4().hex
    notion_pipeline_runs[run_id] = {
        "run_id": run_id,
        "status": "pending",
        "created_at": datetime.utcnow().isoformat(),
    }

    thread = threading.Thread(target=_run_notion_pipeline, args=(run_id,), daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/pipelines/notion/status/{run_id}")
async def get_notion_pipeline_status(run_id: str):
    """Get the status of a Notion pipeline run."""

    run = notion_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/pipelines/notion/stop/{run_id}")
async def stop_notion_pipeline(run_id: str):
    """Request cancellation of a Notion pipeline run."""

    run = notion_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    run["cancel_requested"] = True
    if run.get("status") in ("pending", "running"):
        run["status"] = "cancelling"
    run["finished_at"] = datetime.utcnow().isoformat()
    return run


@app.get("/api/pipelines/notion/pages")
async def get_notion_pipeline_pages(run_id: str):
    """Return pages for a specific Notion pipeline run."""

    run = notion_pipeline_runs.get(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    pages = notion_run_pages.get(run_id, [])
    return {"run_id": run_id, "pages": pages}


@app.get("/api/notion/hierarchy")
async def get_notion_hierarchy():
    """Return Notion workspace name and page hierarchy from the local DB.

    The hierarchy groups pages by their parent_id so the frontend can render an
    accordion view of master pages and subpages. It is intentionally
    independent from the in-memory pipeline state so that previously synced
    pages are available every time the user opens the Pipelines tab.
    """

    preferred_workspace_id = Config.WORKSPACE_ID or "default-notion-workspace"

    with db_manager.get_session() as session:
        # Try configured workspace first, but gracefully fall back to any
        # existing Notion workspace so older data (e.g. created before
        # WORKSPACE_ID was set) still appears.
        workspace = (
            session.query(NotionWorkspace)
            .filter_by(workspace_id=preferred_workspace_id)
            .first()
        )

        if not workspace:
            workspace = (
                session.query(NotionWorkspace)
                .order_by(NotionWorkspace.created_at.desc())
                .first()
            )

        if workspace:
            workspace_id = workspace.workspace_id
            workspace_name = workspace.name or Config.WORKSPACE_NAME or "Notion Workspace"
        else:
            workspace_id = preferred_workspace_id
            workspace_name = Config.WORKSPACE_NAME or "Notion Workspace"

        db_pages = (
            session.query(NotionPage)
            .filter_by(workspace_id=workspace_id)
            .order_by(NotionPage.last_edited_time.desc())
            .all()
        )

        nodes: Dict[str, Dict[str, Any]] = {}
        for p in db_pages:
            nodes[p.page_id] = {
                "id": p.page_id,
                "title": p.title or "Untitled",
                "url": p.url,
                "last_edited_time": p.last_edited_time.isoformat() if p.last_edited_time else None,
                "object_type": p.object_type,
                "parent_id": p.parent_id,
                # Simple properties summary for Gmail-like details panel
                "properties": _summarize_notion_properties(p.raw_data),
                "children": [],
            }

        roots: List[Dict[str, Any]] = []
        for node in nodes.values():
            parent_id = node.get("parent_id")
            if parent_id and parent_id in nodes:
                nodes[parent_id]["children"].append(node)
            else:
                roots.append(node)

    return {
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "pages": roots,
    }


@app.get("/api/notion/page-content")
async def get_notion_page_content(page_id: str):
    token = Config.NOTION_TOKEN
    if not token:
        raise HTTPException(
            status_code=500,
            detail="NOTION_TOKEN is not configured. Please set it in your environment.",
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }

    all_blocks: List[Dict[str, Any]] = []
    next_cursor: Optional[str] = None

    try:
        while True:
            params: Dict[str, Any] = {"page_size": 50}
            if next_cursor:
                params["start_cursor"] = next_cursor

            resp = requests.get(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=headers,
                params=params,
                timeout=30,
            )

            if resp.status_code != 200:
                logger.error(
                    "Notion blocks API error %s: %s",
                    resp.status_code,
                    resp.text[:200],
                )
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Notion API error {resp.status_code}",
                )

            data = resp.json()
            results = data.get("results", []) or []
            all_blocks.extend(results)

            if not data.get("has_more"):
                break
            next_cursor = data.get("next_cursor")
            if not next_cursor:
                break

        text_lines, attachments = _summarize_notion_blocks(all_blocks)
        content = "\n".join(text_lines)

        return {
            "page_id": page_id,
            "content": content,
            "attachments": attachments,
        }

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to fetch Notion page content: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to fetch Notion page content")


# Startup event
@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("Starting Workforce AI Agent API...")
    logger.info("Models will be lazy-loaded on first request")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("Shutting down Workforce AI Agent API...")


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
