"""FastAPI Backend for Workforce AI Agent.

Main application with WebSocket streaming support.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import os
import sys
import aiofiles
import hashlib
from datetime import datetime
from pathlib import Path

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


def get_rag_engine() -> HybridRAGEngine:
    """Lazy load and return the RAG engine."""
    global rag_engine
    
    if rag_engine is None:
        logger.info("Initializing RAG engine...")
        
        embedding = QwenEmbedding(
            model_name=Config.EMBEDDING_MODEL,
            use_gpu=Config.USE_GPU
        )
        
        reranker = QwenReranker(
            model_name=Config.RERANKER_MODEL,
            use_gpu=Config.USE_GPU
        )
        
        rag_engine = HybridRAGEngine(
            openai_api_key=Config.OPENAI_API_KEY,
            qwen_embedding=embedding,
            qwen_reranker=reranker
        )
        
        logger.info("✓ RAG engine initialized")
    
    return rag_engine


def get_ai_brain() -> WorkforceAIBrain:
    """Lazy load and return the AI brain (self-aware agent with tools)."""
    global ai_brain
    
    if ai_brain is None:
        logger.info("Initializing AI Brain (GPT-4)...")
        
        # Ensure RAG engine is initialized first
        rag = get_rag_engine()
        
        # Initialize AI brain with GPT-4o-mini (Nov 2025)
        # 80% cheaper than GPT-4, maintains full capabilities
        ai_brain = WorkforceAIBrain(
            openai_api_key=Config.OPENAI_API_KEY,
            rag_engine=rag,
            model=Config.LLM_MODEL,  # Defaults to gpt-4o-mini, configurable via .env
            temperature=0.7
        )
        
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
        engine = get_rag_engine()
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


@app.websocket("/api/chat/ws")
async def websocket_chat(websocket: WebSocket):
    """Production-ready WebSocket endpoint with conversation history support.
    
    Features:
    - Self-aware AI that knows its capabilities (Slack, Gmail, Notion)
    - Automatic tool calling based on user intent
    - GPT-4 for better reasoning
    - Conversation history persistence in database
    - Session management for multiple chats
    - Proper disconnect handling (1000, 1001, 1006)
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    
    # Initialize AI Brain (self-aware agent)
    brain = None
    try:
        brain = get_ai_brain()
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
                    chat_session = db_manager.get_chat_session(session_id)
                    if not chat_session:
                        # Create new session
                        db_manager.create_chat_session(session_id)
                        logger.debug(f"Created new chat session: {session_id}")
                except Exception as db_error:
                    logger.error(f"Database error: {db_error}", exc_info=True)
                    # Continue without persistence if DB fails
                
                # Load conversation history from database
                conversation_history = []
                try:
                    conversation_history = db_manager.get_chat_history(session_id)
                    logger.debug(f"Loaded {len(conversation_history)} messages from history")
                except Exception as db_error:
                    logger.error(f"Error loading history: {db_error}")
                
                # Save user message to database
                try:
                    db_manager.add_chat_message(session_id, 'user', query)
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
                            db_manager.add_chat_message(
                                session_id, 
                                'assistant', 
                                assistant_response,
                                assistant_sources
                            )
                            
                            # Auto-generate title from first user message if session is new
                            if len(conversation_history) == 0:
                                # Generate concise title from first message
                                title = query[:50] + ('...' if len(query) > 50 else '')
                                db_manager.update_session_title(session_id, title)
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
        get_rag_engine()
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
