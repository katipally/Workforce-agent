"""FastAPI Backend for Workforce AI Agent.

Main application with WebSocket streaming support.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import json
import os
import sys
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

logger = get_logger(__name__)

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
        
        # Initialize AI brain with GPT-4
        ai_brain = WorkforceAIBrain(
            openai_api_key=Config.OPENAI_API_KEY,
            rag_engine=rag,
            model="gpt-4-turbo-preview",
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
    """Production-ready WebSocket endpoint with self-aware AI agent.
    
    Features:
    - Self-aware AI that knows its capabilities (Slack, Gmail, Notion)
    - Automatic tool calling based on user intent
    - GPT-4 for better reasoning
    - Proper disconnect handling (1000, 1001, 1006)
    - No error logging for expected disconnects
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
                
                logger.info(f"Query: {query[:80]}...")
                
                # Send status
                await websocket.send_json({
                    "type": "status",
                    "content": "Processing..."
                })
                
                # Stream response from AI Brain
                try:
                    async for event in brain.stream_query(query):
                        try:
                            await websocket.send_json(event)
                        except WebSocketDisconnect:
                            logger.debug("Client disconnected during streaming")
                            return
                        except Exception as send_error:
                            logger.error(f"Send error: {send_error}")
                            break
                
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
