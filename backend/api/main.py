"""FastAPI Backend for Workforce AI Agent.

Main application with WebSocket streaming support.
"""

import asyncio
import importlib.metadata as _importlib_metadata

# Compatibility shim for Python 3.9: some dependencies expect
# importlib.metadata.packages_distributions to exist.
try:
    _ = _importlib_metadata.packages_distributions
except AttributeError:  # pragma: no cover - best-effort shim
    try:
        import importlib_metadata as _importlib_metadata_backport  # type: ignore[import]

        _importlib_metadata.packages_distributions = (  # type: ignore[attr-defined]
            _importlib_metadata_backport.packages_distributions
        )
    except Exception:
        pass

from fastapi import (
    FastAPI,
    WebSocket,
    WebSocketDisconnect,
    HTTPException,
    UploadFile,
    File,
    Form,
    Depends,
    Request,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from typing import Optional, List, Dict, Any, Tuple
import json
import os

# Disable HuggingFace tokenizers parallelism by default to avoid noisy fork
# warnings. Users can override this via the TOKENIZERS_PARALLELISM env var.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

import sys
import aiofiles
import hashlib
import hmac
import threading
import uuid
import base64
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit
import time
import requests
from sqlalchemy import cast, or_, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Session
from google.oauth2 import id_token as google_id_token
from google.auth.transport import requests as google_requests
from google.oauth2.credentials import Credentials
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# LLM message types for summary generation
from langchain_core.messages import SystemMessage, HumanMessage

# Add core directory to path
core_path = Path(__file__).parent.parent / 'core'
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

# Add agent directory to path for relative imports
agent_path = Path(__file__).parent.parent / 'agent'
if str(agent_path) not in sys.path:
    sys.path.insert(0, str(agent_path))

from config import Config
from utils.logger import get_logger, setup_logging
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
    Project,
    ProjectSource,
    AppUser,
    UserOAuthToken,
    AppSession,
    PipelineRun,
)
from slack.extractor import ExtractionCoordinator
from slack.extractor.channels import ChannelExtractor
from slack.extractor.messages import MessageExtractor
from slack.sender.message_sender import MessageSender
from slack.sender.file_sender import FileSender
from gmail import GmailClient
from notion_export import NotionClient
from sentence_transformer_engine import SentenceTransformerEmbedding

"""Initialize logging and core services."""

# Ensure data/logs directories exist and configure logging
Config.create_directories()
setup_logging()

logger = get_logger(__name__)

_gmail_labels_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_notion_hierarchy_cache: Tuple[float, Dict[str, Any]] = (0.0, {})
_slack_channel_options_cache: Tuple[float, Dict[str, Any]] = (0.0, {})

_OPTIONS_CACHE_TTL_SECONDS = 300.0

_project_embedding_model: Optional[SentenceTransformerEmbedding] = None
_project_embedding_model_lock = threading.Lock()


def _get_project_embedding_model() -> SentenceTransformerEmbedding:
    global _project_embedding_model
    if _project_embedding_model is not None:
        return _project_embedding_model
    with _project_embedding_model_lock:
        if _project_embedding_model is None:
            _project_embedding_model = SentenceTransformerEmbedding(
                model_name=Config.EMBEDDING_MODEL,
                use_gpu=Config.USE_GPU,
            )
    return _project_embedding_model

class PipelineCancelled(Exception):
    """Raised when a pipeline stop is requested."""


def _project_chat_session_id(project_id: str, owner_user_id: str) -> str:
    # chat_sessions.session_id is limited to 50 chars; use a short stable hash
    digest = hashlib.sha1(f"{owner_user_id}:{project_id}".encode("utf-8")).hexdigest()[:32]
    return f"projchat_{digest}"

# Initialize database manager
db_manager = DatabaseManager()

SESSION_COOKIE_NAME = "wf_session"
SESSION_TTL_SECONDS = 60 * 60 * 24 * 7


def _cookie_settings() -> Dict[str, Any]:
    """Get cookie settings based on environment.
    
    For cross-subdomain auth (e.g., app.domain.com + api.domain.com):
    - Set COOKIE_DOMAIN=.domain.com in .env
    - This allows SameSite=Lax (more secure, better browser support)
    
    For cross-origin auth (different domains):
    - Leave COOKIE_DOMAIN empty
    - Uses SameSite=None (required for cross-origin, but blocked by some browsers)
    """
    frontend_url = Config.FRONTEND_BASE_URL or ""
    cookie_domain = Config.COOKIE_DOMAIN or ""
    
    is_local = (
        frontend_url.startswith("http://localhost")
        or frontend_url.startswith("http://127.0.0.1")
        or not frontend_url  # Empty = assume local dev
    )

    if is_local:
        return {
            "path": "/",
            "httponly": True,
            "secure": False,
            "samesite": "lax",
        }

    # Production settings
    settings: Dict[str, Any] = {
        "path": "/",
        "httponly": True,
        "secure": True,
    }
    
    # If COOKIE_DOMAIN is set, we're using same-root-domain setup
    # which allows SameSite=Lax (more compatible with browsers)
    if cookie_domain:
        settings["domain"] = cookie_domain
        settings["samesite"] = "lax"
    else:
        # Cross-origin setup requires SameSite=None
        # Note: This is blocked by Safari ITP and some other browsers
        settings["samesite"] = "none"
    
    return settings


def _delete_app_session(session_id: str) -> None:
    if not session_id:
        return
    with db_manager.get_session() as session:
        db_sess = session.query(AppSession).filter_by(id=session_id).first()
        if db_sess:
            session.delete(db_sess)
            session.commit()


def _get_user_from_session_id(session_id: Optional[str]) -> AppUser:
    if not session_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    with db_manager.get_session() as session:
        app_session = session.query(AppSession).filter_by(id=session_id).first()
        if not app_session or (app_session.expires_at and app_session.expires_at < datetime.utcnow()):
            if app_session:
                session.delete(app_session)
                session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired",
            )

        user = session.query(AppUser).filter_by(id=app_session.user_id).first()
        if not user:
            session.delete(app_session)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        app_session.last_seen_at = datetime.utcnow()
        session.commit()
        return user


def get_current_user(request: Request) -> AppUser:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if not session_id:
        user_agent = request.headers.get("user-agent", "unknown")
        logger.warning(
            "No session cookie found - UserAgent: %s, Cookies: %s",
            user_agent[:100] if user_agent else "none",
            list(request.cookies.keys())
        )
    return _get_user_from_session_id(session_id)


def get_current_user_from_websocket(websocket: WebSocket) -> AppUser:
    session_id = websocket.cookies.get(SESSION_COOKIE_NAME)
    return _get_user_from_session_id(session_id)


def get_current_user_with_gmail(request: Request) -> AppUser:
    user = get_current_user(request)

    with db_manager.get_session() as session:
        token = (
            session.query(UserOAuthToken)
            .filter_by(user_id=user.id, provider="google", revoked=False)
            .first()
        )
        if not token:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Gmail not authorized",
            )

    return user


def _build_google_credentials_for_user_id(user_id: str) -> Optional[Credentials]:
    if not user_id:
        return None

    with db_manager.get_session() as session:
        token = (
            session.query(UserOAuthToken)
            .filter_by(user_id=user_id, provider="google", revoked=False)
            .first()
        )
        if not token or not token.access_token:
            return None

        scopes = token.scope.split() if token.scope else GmailClient.SCOPES

        creds = Credentials(
            token=token.access_token,
            refresh_token=token.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=Config.GOOGLE_CLIENT_ID or None,
            client_secret=Config.GOOGLE_CLIENT_SECRET or None,
            scopes=scopes,
        )

        if token.expires_at and token.expires_at <= datetime.utcnow():
            if token.refresh_token and Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET:
                try:
                    creds.refresh(google_requests.Request())
                except RefreshError as e:
                    logger.error("Failed to refresh Google token for user %s: %s", user_id, e)
                    token.revoked = True
                    session.commit()
                    return None

                token.access_token = creds.token
                expiry = getattr(creds, "expiry", None)
                token.expires_at = expiry or datetime.utcnow() + timedelta(seconds=3600)
                session.commit()
            else:
                return None

        return creds


def _get_google_calendar_service_for_user(user_id: str):
    """Build a Google Calendar service for the given user, if authorized.

    Returns None if the user does not have a valid Google token or if the
    token cannot be used to construct a Calendar service.
    """

    creds = _build_google_credentials_for_user_id(user_id)
    if not creds:
        return None

    try:
        return build("calendar", "v3", credentials=creds)
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error("Failed to build Google Calendar service for user %s: %s", user_id, e)
        return None

def _build_oauth_state(redirect_path: Optional[str] = "/") -> str:
    payload = {
        "nonce": secrets.token_hex(16),
        "redirect_path": redirect_path or "/",
    }
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")

    if not Config.SESSION_SECRET:
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    sig = hmac.new(Config.SESSION_SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest().encode("ascii")
    token = base64.urlsafe_b64encode(raw + b"." + sig).decode("ascii").rstrip("=")
    return token


def _parse_oauth_state(state: str) -> Optional[Dict[str, Any]]:
    if not state:
        return None

    try:
        padded = state + "=" * (-len(state) % 4)
        data = base64.urlsafe_b64decode(padded.encode("ascii"))

        if Config.SESSION_SECRET:
            raw, sig = data.rsplit(b".", 1)
            expected_sig = hmac.new(
                Config.SESSION_SECRET.encode("utf-8"), raw, hashlib.sha256
            ).hexdigest().encode("ascii")
            if not hmac.compare_digest(sig, expected_sig):
                logger.warning("Invalid OAuth state signature")
                return None
        else:
            raw = data

        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else None
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to parse OAuth state: {e}", exc_info=True)
        return None


# Import agent modules after setting up paths
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from agent.hybrid_rag import HybridRAGEngine
from agent.ai_brain import WorkforceAIBrain
from agent.sentence_transformer_engine import (
    SentenceTransformerEmbedding,
    SentenceTransformerReranker,
)
from settings.service import (
    get_personal_settings_view,
    update_personal_settings,
    get_workspace_settings_view,
    update_workspace_settings,
    get_effective_openai_key,
    get_effective_llm_model,
    get_effective_notion_token,
    get_effective_slack_bot_token,
    bootstrap_app_settings_from_config_if_empty,
    sync_workspace_settings_from_config,
)

# Import embedding synchronizer for pipeline integration
sys.path.insert(0, str(Path(__file__).parent.parent / 'core'))
from embeddings_sync import sync_embeddings_after_pipeline

# Global variables
rag_engine = None
ai_brain = None  # Kept for backward-compatible health reporting; brains are built per-user.
rag_lock: Optional[asyncio.Lock] = None
ai_brain_lock: Optional[asyncio.Lock] = None

# Background workflow worker (Slack → Notion) state
workflow_worker_thread: Optional[threading.Thread] = None
workflow_worker_stop_event: Optional[threading.Event] = None


def _has_active_slack_to_notion_workflows() -> bool:
    """Return True if there is at least one active Slack → Notion workflow."""

    try:
        workflows = db_manager.list_workflows(limit=500)
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error("Failed to list workflows when checking active status: %s", e, exc_info=True)
        return False

    for wf in workflows:
        if getattr(wf, "type", None) == "slack_to_notion" and getattr(wf, "status", None) == "active":
            return True
    return False


def _start_workflow_worker_if_needed() -> None:
    """Start the Slack → Notion worker thread only when there are active workflows."""

    global workflow_worker_thread, workflow_worker_stop_event

    if workflow_worker_thread is not None and workflow_worker_thread.is_alive():
        return

    if not _has_active_slack_to_notion_workflows():
        logger.info("No active Slack → Notion workflows; scheduler thread not started")
        return

    # Import here to avoid circular imports at module load time
    from workflows.slack_to_notion_worker import run_scheduler

    workflow_worker_stop_event = threading.Event()

    def _runner() -> None:
        run_scheduler(stop_event=workflow_worker_stop_event)

    workflow_worker_thread = threading.Thread(
        target=_runner,
        name="slack_to_notion_worker",
        daemon=True,
    )
    workflow_worker_thread.start()
    logger.info("Started Slack → Notion workflow scheduler background thread")


def _stop_workflow_worker_internal() -> None:
    """Stop the background Slack → Notion workflow scheduler thread if running."""

    global workflow_worker_thread, workflow_worker_stop_event

    if workflow_worker_stop_event is not None:
        workflow_worker_stop_event.set()

    if workflow_worker_thread is not None and workflow_worker_thread.is_alive():
        workflow_worker_thread.join(timeout=10)

    workflow_worker_thread = None
    workflow_worker_stop_event = None


def _reconcile_workflow_worker_state() -> None:
    """Ensure the worker thread state matches DB workflow state.

    If there is at least one active Slack → Notion workflow, the scheduler
    thread is started (if not already running). If there are none, the thread
    is stopped.
    """

    if _has_active_slack_to_notion_workflows():
        _start_workflow_worker_if_needed()
    else:
        _stop_workflow_worker_internal()


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

        # Resolve AI infrastructure and OpenAI key from workspace settings where possible,
        # falling back to Config for defaults.
        settings_view = get_workspace_settings_view(db_manager, include_secrets=False)
        ai_infra = settings_view.get("ai_infra") or {}

        embedding_model_name = ai_infra.get("embedding_model") or Config.EMBEDDING_MODEL
        reranker_model_name = ai_infra.get("reranker_model") or Config.RERANKER_MODEL
        use_gpu = ai_infra.get("use_gpu") if "use_gpu" in ai_infra else Config.USE_GPU

        # Workspace-global OpenAI key (from system section or Config fallback)
        openai_key = get_effective_openai_key(db_manager, user_id="")

        embedding, reranker = await loop.run_in_executor(
            None,
            lambda: (
                SentenceTransformerEmbedding(
                    model_name=embedding_model_name,
                    use_gpu=use_gpu,
                ),
                SentenceTransformerReranker(
                    model_name=reranker_model_name,
                    use_gpu=use_gpu,
                ),
            ),
        )

        rag_engine = HybridRAGEngine(
            openai_api_key=openai_key or Config.OPENAI_API_KEY,
            embedding_model=embedding,
            reranker_model=reranker,
        )

        logger.info("✓ RAG engine initialized")
        return rag_engine


async def _build_ai_brain_for_user(current_user: AppUser) -> WorkforceAIBrain:
    """Construct an AI brain instance for the given user using personal settings.

    Each user can have their own OpenAI API key and preferred LLM model. We
    reuse the shared RAG engine but create a per-user WorkforceAIBrain so
    settings are respected across all tabs.
    """

    global ai_brain

    rag = await get_rag_engine()

    api_key = get_effective_openai_key(db_manager, current_user.id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OpenAI API key not configured. Please set the global key in Workspace settings.",
        )

    model = get_effective_llm_model(db_manager, current_user.id)

    loop = asyncio.get_running_loop()
    brain = await loop.run_in_executor(
        None,
        lambda: WorkforceAIBrain(
            openai_api_key=api_key,
            rag_engine=rag,
            model=model,
            temperature=0.7,
            user_id=current_user.id,
        ),
    )

    # Track the last-initialized brain globally so health endpoints can
    # advertise capabilities without needing a specific user context.
    ai_brain = brain

    return brain


# Initialize FastAPI app
app = FastAPI(
    title="Workforce AI Agent API",
    description="AI agent with RAG for Slack, Gmail, and Notion",
    version="1.0.0"
)


@app.get("/auth/google/login")
async def google_login(request: Request, redirect_path: Optional[str] = "/"):
    """Start Google OAuth login flow."""

    if not (Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET and Config.GOOGLE_OAUTH_REDIRECT_BASE):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google OAuth not configured")

    if not redirect_path or not redirect_path.startswith("/"):
        redirect_path = "/"

    state = _build_oauth_state(redirect_path)
    redirect_uri = f"{Config.GOOGLE_OAUTH_REDIRECT_BASE.rstrip('/')}/auth/google/callback"

    scopes = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/calendar",
    ] + GmailClient.SCOPES

    params = {
        "client_id": Config.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "state": state,
        "prompt": "consent",
    }

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    return RedirectResponse(auth_url, status_code=status.HTTP_302_FOUND)


@app.get("/auth/google/callback")
async def google_callback(request: Request, code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """Handle Google OAuth callback, create/update user, and set session cookie."""

    # Prefer explicit FRONTEND_BASE_URL, but fall back to the callback's base URL
    frontend_base = (Config.FRONTEND_BASE_URL or "").rstrip("/")
    if not frontend_base:
        frontend_base = str(request.base_url).rstrip("/")
    default_redirect = frontend_base

    if error or not code:
        redirect_url = f"{default_redirect}?auth_error={error or 'missing_code'}"
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    state_payload = _parse_oauth_state(state or "")
    if not state_payload:
        redirect_url = f"{default_redirect}?auth_error=invalid_state"
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    redirect_path = state_payload.get("redirect_path") or "/"
    if not redirect_path.startswith("/"):
        redirect_path = "/"

    redirect_uri = f"{Config.GOOGLE_OAUTH_REDIRECT_BASE.rstrip('/')}/auth/google/callback"

    token_data = {
        "code": code,
        "client_id": Config.GOOGLE_CLIENT_ID,
        "client_secret": Config.GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        token_resp = requests.post("https://oauth2.googleapis.com/token", data=token_data, timeout=10)
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error exchanging code for token: {e}", exc_info=True)
        redirect_url = f"{default_redirect}?auth_error=token_exchange_failed"
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    if token_resp.status_code != 200:
        logger.error("Token endpoint error %s: %s", token_resp.status_code, token_resp.text)
        redirect_url = f"{default_redirect}?auth_error=token_exchange_failed"
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    tokens = token_resp.json()
    id_token_str = tokens.get("id_token")
    access_token = tokens.get("access_token")
    refresh_token = tokens.get("refresh_token")
    expires_in = tokens.get("expires_in")
    scope_str = tokens.get("scope", "")
    token_type = tokens.get("token_type")

    if not id_token_str or not access_token:
        redirect_url = f"{default_redirect}?auth_error=invalid_token_response"
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    try:
        id_info = google_id_token.verify_oauth2_token(
            id_token_str,
            google_requests.Request(),
            audience=Config.GOOGLE_CLIENT_ID,
        )
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to verify ID token: {e}", exc_info=True)
        redirect_url = f"{default_redirect}?auth_error=id_token_invalid"
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    sub = id_info.get("sub")
    email = id_info.get("email")
    name = id_info.get("name") or ""
    picture = id_info.get("picture")

    if not sub or not email:
        redirect_url = f"{default_redirect}?auth_error=missing_profile"
        return RedirectResponse(redirect_url, status_code=status.HTTP_302_FOUND)

    session_id: Optional[str] = None

    with db_manager.get_session() as session:
        user = session.query(AppUser).filter_by(google_sub=sub).first()
        if not user:
            user = session.query(AppUser).filter_by(email=email).first()
        if not user:
            user = AppUser(
                google_sub=sub,
                email=email,
                name=name,
                picture_url=picture,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                last_login_at=datetime.utcnow(),
            )
            session.add(user)
        else:
            user.email = email
            user.name = name
            user.picture_url = picture
            user.last_login_at = datetime.utcnow()
            user.updated_at = datetime.utcnow()

        expires_at: Optional[datetime] = None
        try:
            if isinstance(expires_in, (int, float)):
                expires_at = datetime.utcnow() + timedelta(seconds=int(expires_in))
        except Exception:
            expires_at = None

        token = (
            session.query(UserOAuthToken)
            .filter_by(user_id=user.id, provider="google")
            .first()
        )
        if not token:
            token = UserOAuthToken(
                user_id=user.id,
                provider="google",
                access_token=access_token,
                refresh_token=refresh_token,
                expires_at=expires_at,
                scope=scope_str,
                token_type=token_type,
                revoked=False,
            )
            session.add(token)
        else:
            token.access_token = access_token
            if refresh_token:
                token.refresh_token = refresh_token
            token.expires_at = expires_at
            token.scope = scope_str
            token.token_type = token_type
            token.revoked = False

        scopes = (scope_str or "").split()
        has_gmail = any(s.startswith("https://www.googleapis.com/auth/gmail") for s in scopes)
        user.has_gmail_access = has_gmail

        now = datetime.utcnow()
        session_id = secrets.token_hex(32)
        app_session = AppSession(
            id=session_id,
            user_id=user.id,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=SESSION_TTL_SECONDS),
            last_seen_at=now,
        )
        session.add(app_session)
        session.commit()

    # Log successful session creation
    user_agent = request.headers.get("user-agent", "unknown")
    logger.info(
        "OAuth callback successful - User: %s, SessionID: %s, UserAgent: %s",
        email,
        session_id,
        user_agent[:100] if user_agent else "none"
    )

    # Add session token to URL as fallback for mobile Safari (ITP workaround)
    # The frontend will call /auth/session-exchange to set the cookie
    redirect_separator = "&" if "?" in redirect_path else "?"
    redirect_url = f"{default_redirect}{redirect_path}{redirect_separator}_session_token={session_id}"
    
    response = RedirectResponse(url=redirect_url, status_code=status.HTTP_302_FOUND)
    if session_id:
        cookie_settings = _cookie_settings()
        logger.info(
            "Setting session cookie - SessionID: %s, Settings: %s",
            session_id[:8] + "...",
            cookie_settings
        )
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=session_id,
            max_age=SESSION_TTL_SECONDS,
            **cookie_settings,
        )
    return response


@app.post("/auth/session-exchange")
async def session_exchange(request: Request):
    """Exchange a session token from URL for a proper session cookie.
    
    This is a workaround for mobile Safari's Intelligent Tracking Prevention (ITP)
    which blocks cross-site cookies even with SameSite=None. The frontend calls
    this endpoint with the token from the URL to set the cookie via a same-site request.
    """
    try:
        body = await request.json()
        token = body.get("token")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request body"
        )
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing token"
        )
    
    # Validate the token is a valid session
    with db_manager.get_session() as session:
        app_session = session.query(AppSession).filter_by(id=token).first()
        if not app_session:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token"
            )
        
        # Check if session is expired
        if app_session.expires_at and app_session.expires_at < datetime.utcnow():
            session.delete(app_session)
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired"
            )
        
        # Update last_seen
        app_session.last_seen_at = datetime.utcnow()
        session.commit()
    
    # Set the cookie via a same-site response
    response = JSONResponse({"detail": "session_set"})
    cookie_settings = _cookie_settings()
    logger.info(
        "Session exchange successful - SessionID: %s, Settings: %s",
        token[:8] + "...",
        cookie_settings
    )
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        **cookie_settings,
    )
    return response


@app.post("/auth/logout")
async def logout(request: Request):
    """Log the current user out and clear the session cookie."""

    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        _delete_app_session(session_id)

    response = JSONResponse({"detail": "logged_out"})
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response


@app.get("/auth/me")
async def auth_me(request: Request, current_user: AppUser = Depends(get_current_user)):
    """Return the current authenticated user's profile."""

    # Log successful authentication
    user_agent = request.headers.get("user-agent", "unknown")
    session_id = request.cookies.get(SESSION_COOKIE_NAME, "none")
    logger.info(
        "Auth check successful - User: %s, SessionID: %s, UserAgent: %s",
        current_user.email,
        session_id[:8] + "..." if session_id != "none" else "none",
        user_agent[:100] if user_agent else "none"
    )

    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "picture_url": current_user.picture_url,
        "has_gmail_access": bool(current_user.has_gmail_access),
    }

# CORS middleware for React frontend
_frontend_origins: list[str] = []


def _add_cors_origin(origin: str) -> None:
    origin = (origin or "").strip().rstrip("/")
    if not origin:
        return

    if origin not in _frontend_origins:
        _frontend_origins.append(origin)

    # Add both www/non-www variants to avoid subtle production mismatches.
    try:
        parsed = urlsplit(origin)
        if not parsed.scheme or not parsed.netloc:
            return

        host = parsed.netloc
        if host.startswith("www."):
            alt_host = host[4:]
        else:
            alt_host = f"www.{host}"

        alt_origin = f"{parsed.scheme}://{alt_host}"
        if alt_origin not in _frontend_origins:
            _frontend_origins.append(alt_origin)
    except Exception:
        return


if Config.FRONTEND_BASE_URL:
    _add_cors_origin(Config.FRONTEND_BASE_URL)

extra_origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
for origin in extra_origins.split(","):
    _add_cors_origin(origin)

if not _frontend_origins:
    # Fallback to permissive CORS when no origins are configured
    _frontend_origins.append("*")

logger.info("Configured CORS allowed origins: %s", _frontend_origins)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_frontend_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def bootstrap_workspace_settings() -> None:
    try:
        bootstrap_app_settings_from_config_if_empty(db_manager)
    except Exception as e:
        logger.error("Failed to bootstrap workspace settings from Config: %s", e, exc_info=True)


@app.on_event("startup")
async def start_workflow_worker() -> None:
    """Start the Slack → Notion workflow scheduler in a background thread.

    This avoids requiring a separate `python workflows/slack_to_notion_worker.py`
    process. The thread is stopped cleanly on application shutdown.
    """
    _start_workflow_worker_if_needed()


@app.on_event("shutdown")
async def stop_workflow_worker() -> None:
    """Stop the background Slack → Notion workflow scheduler thread."""
    _stop_workflow_worker_internal()


@app.on_event("startup")
async def start_workflow_scheduler_v2() -> None:
    """Start the modular workflow scheduler (v2) in a background thread."""
    try:
        from workflows.workflow_scheduler import reconcile_scheduler_state
        reconcile_scheduler_state(db_manager)
    except Exception as e:
        logger.warning(f"Failed to start workflow scheduler v2: {e}")


@app.on_event("shutdown")
async def stop_workflow_scheduler_v2() -> None:
    """Stop the modular workflow scheduler (v2) thread."""
    try:
        from workflows.workflow_scheduler import stop_workflow_scheduler
        stop_workflow_scheduler()
    except Exception as e:
        logger.warning(f"Failed to stop workflow scheduler v2: {e}")


# Request/Response models
class SourcePreferences(BaseModel):
    slack: bool = True
    gmail: bool = True
    notion: bool = True


class ChatRequest(BaseModel):
    """Chat request model."""
    query: str
    conversation_history: Optional[List[Dict[str, str]]] = None
    source_prefs: Optional[SourcePreferences] = None


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


class ConnectorHealth(BaseModel):
    """Status for a single external connector (Slack, Gmail, Notion)."""

    status: str  # connected, disconnected, degraded
    detail: Optional[str] = None


class ChatConnectorHealthResponse(BaseModel):
    """Aggregated connector health for the chat UI."""

    overall_status: str
    slack: ConnectorHealth
    gmail: ConnectorHealth
    notion: ConnectorHealth


class UserSettingsUpdate(BaseModel):
    """Payload for updating per-user settings."""

    openai_api_key: Optional[str] = None
    llm_model: Optional[str] = None
    timezone: Optional[str] = None


class WorkspaceSettingsUpdate(BaseModel):
    """Payload for updating workspace-wide settings.

    Each section is optional; when provided it replaces/updates that section in
    the underlying AppSettings JSON document.
    """

    system: Optional[Dict[str, Any]] = None
    slack: Optional[Dict[str, Any]] = None
    notion: Optional[Dict[str, Any]] = None
    gmail: Optional[Dict[str, Any]] = None
    workspace: Optional[Dict[str, Any]] = None
    runtime: Optional[Dict[str, Any]] = None
    database: Optional[Dict[str, Any]] = None
    ai_infra: Optional[Dict[str, Any]] = None
    

class ProjectSourcePayload(BaseModel):
    source_type: str
    source_id: str
    display_name: Optional[str] = None


class ProjectCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    main_goal: Optional[str] = None
    current_status_summary: Optional[str] = None
    important_notes: Optional[str] = None


class ProjectUpdateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    main_goal: Optional[str] = None
    current_status_summary: Optional[str] = None
    important_notes: Optional[str] = None


class ProjectChatRequest(BaseModel):
    query: str
    conversation_history: Optional[List[Dict[str, str]]] = None


class ProjectSummaryRequest(BaseModel):
    """Payload for AI-powered project summary generation."""

    max_tokens: int = 256


class WorkflowCreateRequest(BaseModel):
    """Create a new workflow (e.g., Slack → Notion)."""

    name: str
    type: str = "slack_to_notion"
    status: Optional[str] = None
    notion_master_page_id: Optional[str] = None
    poll_interval_seconds: Optional[int] = None


class WorkflowUpdateRequest(BaseModel):
    """Update an existing workflow."""

    name: Optional[str] = None
    status: Optional[str] = None
    notion_master_page_id: Optional[str] = None
    poll_interval_seconds: Optional[int] = None


class WorkflowChannelPayload(BaseModel):
    """Payload for adding Slack channels to a workflow."""

    slack_channel_id: str
    slack_channel_name: Optional[str] = None


WORKFLOW_ALLOWED_INTERVALS = {30,3600, 10800, 28800, 86400}


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


@app.get("/api/chat/connectors/status", response_model=ChatConnectorHealthResponse)
async def get_chat_connector_status(
    current_user: AppUser = Depends(get_current_user),
):
    """Return high-level connector health for Slack, Gmail, and Notion.

    This is used by the Chat UI header to show per-platform status. It is a
    lightweight check based primarily on configuration and user OAuth state,
    and does not perform heavy API calls.
    """

    # Slack workspace-level status
    slack_token = get_effective_slack_bot_token(db_manager)
    if slack_token:
        slack_status = "connected"
        slack_detail = "Slack bot token configured"
    else:
        slack_status = "disconnected"
        slack_detail = "Slack bot token not configured"

    # Gmail per-user status
    if getattr(current_user, "has_gmail_access", False):
        gmail_status = "connected"
        gmail_detail = "Gmail authorized for current user"
    else:
        gmail_status = "disconnected"
        gmail_detail = "Gmail not authorized for current user"

    # Notion workspace-level status
    notion_token = get_effective_notion_token(db_manager)
    if notion_token:
        notion_status = "connected"
        notion_detail = "Notion token configured"
    else:
        notion_status = "disconnected"
        notion_detail = "Notion token not configured"

    # Derive overall status
    connector_statuses = {slack_status, gmail_status, notion_status}
    if connector_statuses == {"connected"}:
        overall_status = "connected"
    elif connector_statuses == {"disconnected"}:
        overall_status = "disconnected"
    else:
        overall_status = "degraded"

    return ChatConnectorHealthResponse(
        overall_status=overall_status,
        slack=ConnectorHealth(status=slack_status, detail=slack_detail),
        gmail=ConnectorHealth(status=gmail_status, detail=gmail_detail),
        notion=ConnectorHealth(status=notion_status, detail=notion_detail),
    )


@app.get("/api/settings/me")
async def get_my_settings(
    include_secrets: bool = False,
    current_user: AppUser = Depends(get_current_user),
):
    """Return the current user's personal settings (per-user).

    When include_secrets is true, the full decrypted OpenAI API key is
    returned under openai_api_key_full in addition to the usual metadata.
    """

    return get_personal_settings_view(db_manager, current_user.id, include_secret=include_secrets)


@app.put("/api/settings/me")
async def update_my_settings(
    payload: UserSettingsUpdate,
    current_user: AppUser = Depends(get_current_user),
):
    """Update the current user's personal settings.

    Secrets (like the OpenAI API key) are encrypted at rest and only exposed via
    flags and last-4 digits in responses.
    """

    data = payload.dict(exclude_unset=True)
    return update_personal_settings(db_manager, current_user.id, data)


@app.get("/api/settings/workspace")
async def get_workspace_settings(
    include_secrets: bool = False,
    current_user: AppUser = Depends(get_current_user),
):
    """Return workspace-wide settings.

    For now all authenticated users are treated as admins and can view/edit
    workspace settings. When include_secrets is true, decrypted Slack and
    Notion tokens are included alongside their metadata.
    """

    return get_workspace_settings_view(db_manager, include_secrets=include_secrets)


@app.put("/api/settings/workspace")
async def update_workspace_settings_endpoint(
    payload: WorkspaceSettingsUpdate,
    current_user: AppUser = Depends(get_current_user),
):
    """Update workspace-wide settings."""

    global rag_engine, ai_brain

    data = payload.dict(exclude_unset=True)
    result = update_workspace_settings(db_manager, data)

    # Clear cached AI engines so they are rebuilt with new settings on next use.
    rag_engine = None
    ai_brain = None

    return result


@app.post("/api/settings/workspace/sync-from-env")
async def sync_workspace_settings_from_env_endpoint(
    current_user: AppUser = Depends(get_current_user),
):
    """Sync workspace-wide settings from current Config/env values.

    This is used by the Workspace settings UI "Sync from env" button to pull
    values from .env/Config into the AppSettings document.
    """

    global rag_engine, ai_brain

    result = sync_workspace_settings_from_config(db_manager)

    # Clear cached AI engines so they are rebuilt with new settings on next use.
    rag_engine = None
    ai_brain = None

    return result


@app.get("/api/settings/options/timezones")
async def get_timezone_options(current_user: AppUser = Depends(get_current_user)):
    """Return a curated list of common timezones for autocomplete."""

    timezones = [
        "UTC",
        "America/Los_Angeles",
        "America/New_York",
        "Europe/London",
        "Europe/Berlin",
        "Asia/Kolkata",
        "Asia/Tokyo",
    ]
    return {"timezones": timezones}


@app.get("/api/settings/options/slack-channels")
async def get_slack_channel_options(current_user: AppUser = Depends(get_current_user)):
    """Return Slack channels from the database for autocomplete inputs."""

    with db_manager.get_session() as session:
        channels = (
            session.query(Channel)
            .order_by(Channel.name.asc())
            .limit(500)
            .all()
        )

    items = [
        {"id": ch.channel_id, "name": ch.name}
        for ch in channels
        if getattr(ch, "name", None)
    ]
    return {"channels": items}


@app.get("/api/settings/options/gmail-labels")
async def get_gmail_label_options(current_user: AppUser = Depends(get_current_user)):
    """Return Gmail label names from the database for autocomplete inputs."""

    from database.models import GmailLabel

    with db_manager.get_session() as session:
        labels = session.query(GmailLabel).limit(500).all()

    names = []
    for lbl in labels:
        name = getattr(lbl, "name", None)
        if name:
            names.append(name)

    return {"labels": names}


@app.get("/api/calendar/events")
async def list_calendar_events(
    view: str = "day",
    date: Optional[str] = None,
    current_user: AppUser = Depends(get_current_user),
):
    """List Google Calendar events for the current user.

    View can be one of: day, week, month. Date is interpreted as YYYY-MM-DD
    in server time; for now we treat times as UTC when building Calendar
    timeMin/timeMax bounds.
    """

    view = view.lower()
    if view not in {"day", "week", "month"}:
        raise HTTPException(status_code=400, detail="Invalid view; expected day, week, or month")

    # Parse date or default to today (UTC)
    try:
        if date:
            base_date = datetime.fromisoformat(date)
        else:
            base_date = datetime.utcnow()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid date format; expected YYYY-MM-DD")

    # Compute time window
    if view == "month":
        # Always cover the full calendar month that contains base_date,
        # so the Calendar UI sees all events for that month regardless of
        # which specific day is selected.
        start = datetime(base_date.year, base_date.month, 1)
        if base_date.month == 12:
            end = datetime(base_date.year + 1, 1, 1)
        else:
            end = datetime(base_date.year, base_date.month + 1, 1)
    else:
        start = datetime(base_date.year, base_date.month, base_date.day)
        if view == "day":
            end = start + timedelta(days=1)
        else:  # week
            # Assume week starts on Monday
            weekday = start.weekday()
            start = start - timedelta(days=weekday)
            end = start + timedelta(days=7)

    service = _get_google_calendar_service_for_user(current_user.id)
    if not service:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google Calendar not authorized")

    try:
        events_result = (
            service.events()
            .list(
                calendarId="primary",
                timeMin=start.isoformat() + "Z",
                timeMax=end.isoformat() + "Z",
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
    except HttpError as e:
        logger.error("Google Calendar API error for user %s: %s", current_user.id, e)
        raise HTTPException(status_code=502, detail="Error fetching calendar events from Google")

    items = events_result.get("items", [])

    def _normalize_event(ev: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "id": ev.get("id"),
            "status": ev.get("status"),
            "htmlLink": ev.get("htmlLink"),
            "summary": ev.get("summary"),
            "description": ev.get("description"),
            "location": ev.get("location"),
            "start": ev.get("start"),
            "end": ev.get("end"),
            "organizer": ev.get("organizer"),
            "attendees": ev.get("attendees", []),
            "hangoutLink": ev.get("hangoutLink"),
            "conferenceData": ev.get("conferenceData"),
        }

    return {"events": [_normalize_event(ev) for ev in items]}


@app.get("/api/calendar/events/{event_id}")
async def get_calendar_event(event_id: str, current_user: AppUser = Depends(get_current_user)):
    """Return details for a single Google Calendar event for the current user."""

    if not event_id:
        raise HTTPException(status_code=400, detail="event_id is required")

    service = _get_google_calendar_service_for_user(current_user.id)
    if not service:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Google Calendar not authorized")

    try:
        ev = service.events().get(calendarId="primary", eventId=event_id).execute()
    except HttpError as e:
        if getattr(e, "status_code", None) == 404:
            raise HTTPException(status_code=404, detail="Event not found")
        logger.error("Google Calendar get event error for user %s: %s", current_user.id, e)
        raise HTTPException(status_code=502, detail="Error fetching calendar event from Google")

    return {
        "id": ev.get("id"),
        "status": ev.get("status"),
        "htmlLink": ev.get("htmlLink"),
        "summary": ev.get("summary"),
        "description": ev.get("description"),
        "location": ev.get("location"),
        "start": ev.get("start"),
        "end": ev.get("end"),
        "organizer": ev.get("organizer"),
        "attendees": ev.get("attendees", []),
        "hangoutLink": ev.get("hangoutLink"),
        "conferenceData": ev.get("conferenceData"),
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
async def chat_message(
    request: ChatRequest,
    current_user: AppUser = Depends(get_current_user),
):
    """Non-streaming chat endpoint with AI Brain and tool calling.
    
    Routes through AI Brain for consistent behavior with WebSocket endpoint.
    The AI Brain has access to all tools (Slack, Gmail, Notion) and RAG.
    
    Args:
        request: Chat request with query and optional history
        
    Returns:
        Chat response with answer and sources
    """
    brain = None
    try:
        brain = await _build_ai_brain_for_user(current_user)

        # Collect streaming response into single output
        full_response = ""
        sources = []

        prefs_dict = request.source_prefs.dict() if request.source_prefs else None

        async for event in brain.stream_query(
            request.query,
            request.conversation_history or [],
            user_email=current_user.email,
            source_prefs=prefs_dict,
        ):
            if event.get("type") == "token":
                full_response += event.get("content", "")
            elif event.get("type") == "sources":
                sources = event.get("content", [])

        return ChatResponse(
            response=full_response,
            sources=sources,
            intent="general"  # AI Brain doesn't expose intent separately
        )

    except Exception as e:
        logger.error(f"Error in chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        try:
            if brain and hasattr(brain, "close"):
                await brain.close()
        except Exception:
            pass


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
    # Authenticate user via session cookie before accepting the connection
    try:
        current_user = get_current_user_from_websocket(websocket)
    except HTTPException as e:
        logger.warning("WebSocket authentication failed: %s", e.detail)
        try:
            await websocket.close(code=1008, reason=e.detail)
        except Exception:
            pass
        return

    await websocket.accept()
    logger.info("WebSocket connection accepted for user %s", current_user.email)
    
    # Initialize AI Brain (self-aware agent) for this user
    brain = None
    try:
        brain = await _build_ai_brain_for_user(current_user)
        logger.debug("AI Brain ready for user %s", current_user.email)
    except Exception as e:
        logger.error(f"Failed to initialize AI Brain: {e}", exc_info=True)
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"Server initialization failed: {str(e)}"
            })
            await websocket.close(code=1011, reason="Server error")
        except Exception:
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
                source_prefs = message_data.get('source_prefs') or None
                
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
                
                logger.info(f"Query: {query[:80]}... (session: {session_id}, user: {current_user.email})")
                
                # Ensure session exists and is owned by the current user
                try:
                    chat_session = await _run_in_executor(
                        db_manager.get_chat_session,
                        session_id,
                        current_user.id,
                    )
                    if not chat_session:
                        await _run_in_executor(
                            db_manager.create_chat_session,
                            session_id,
                            "New Chat",
                            current_user.id,
                        )
                        logger.debug(
                            "Created new chat session %s for user %s",
                            session_id,
                            current_user.id,
                        )
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
                    async for event in brain.stream_query(
                        query,
                        conversation_history,
                        user_email=current_user.email,
                        source_prefs=source_prefs,
                    ):
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
            
            except WebSocketDisconnect as e:
                logger.debug(f"WebSocket disconnected during processing: {e}")
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
            if brain and hasattr(brain, "close"):
                await brain.close()
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
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
async def list_sessions(current_user: AppUser = Depends(get_current_user)):
    """List chat sessions for the current user ordered by last update."""
    try:
        sessions = db_manager.list_chat_sessions(owner_user_id=current_user.id, limit=100)
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
async def get_session(session_id: str, current_user: AppUser = Depends(get_current_user)):
    """Get a specific chat session with all messages.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Session details with messages
    """
    try:
        session = db_manager.get_chat_session(session_id, owner_user_id=current_user.id)

        # For brand new sessions, auto-create an empty session for this user
        # instead of returning 404 so the frontend can immediately attach
        # messages.
        if not session:
            db_manager.create_chat_session(session_id, owner_user_id=current_user.id)
            session = db_manager.get_chat_session(session_id, owner_user_id=current_user.id)
            if not session:
                raise HTTPException(status_code=500, detail="Failed to create chat session")
        
        # Get messages for this session (empty list for new sessions)
        messages = db_manager.get_chat_history(session_id)
        
        return {
            "session_id": session.session_id,
            "title": session.title,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "messages": messages,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/chat/sessions/{session_id}")
async def delete_session(session_id: str, current_user: AppUser = Depends(get_current_user)):
    """Delete a chat session and all its messages.
    
    Args:
        session_id: Session identifier
        
    Returns:
        Success message
    """
    try:
        db_manager.delete_chat_session(session_id, owner_user_id=current_user.id)
        return {"status": "ok", "message": "Session deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Project Endpoints
# ============================================================================


@app.get("/api/projects")
async def list_projects(current_user: AppUser = Depends(get_current_user)):
    """List projects for the Projects tab for the current user."""
    try:
        projects = db_manager.list_projects(owner_user_id=current_user.id, limit=100)
        return {
            "projects": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "status": p.status,
                    "summary": p.summary,
                    "main_goal": p.main_goal,
                    "current_status_summary": p.current_status_summary,
                    "important_notes": p.important_notes,
                    "last_project_sync_at": p.last_project_sync_at.isoformat() if p.last_project_sync_at else None,
                    "last_summary_generated_at": p.last_summary_generated_at.isoformat() if p.last_summary_generated_at else None,
                    "created_at": p.created_at.isoformat() if p.created_at else None,
                    "updated_at": p.updated_at.isoformat() if p.updated_at else None,
                }
                for p in projects
            ]
        }
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error listing projects: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list projects")


@app.post("/api/projects")
async def create_project(payload: ProjectCreateRequest, current_user: AppUser = Depends(get_current_user)):
    """Create a new project."""
    try:
        status = payload.status or "not_started"
        project = db_manager.create_project(
            name=payload.name,
            description=payload.description,
            status=status,
            summary=payload.summary,
            main_goal=payload.main_goal,
            current_status_summary=payload.current_status_summary,
            important_notes=payload.important_notes,
            owner_user_id=current_user.id,
        )
        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "summary": project.summary,
            "main_goal": project.main_goal,
            "current_status_summary": project.current_status_summary,
            "important_notes": project.important_notes,
            "last_project_sync_at": project.last_project_sync_at.isoformat() if project.last_project_sync_at else None,
            "last_summary_generated_at": project.last_summary_generated_at.isoformat() if project.last_summary_generated_at else None,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error creating project: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create project")


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str, current_user: AppUser = Depends(get_current_user)):
    """Get a project with its linked sources."""
    try:
        project = db_manager.get_project(project_id, owner_user_id=current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        sources = db_manager.get_project_sources(project_id)
        slack_channels: List[Dict[str, Any]] = []
        gmail_labels: List[Dict[str, Any]] = []
        notion_pages: List[Dict[str, Any]] = []

        for s in sources:
            item = {
                "source_type": s.source_type,
                "source_id": s.source_id,
                "display_name": s.display_name,
            }
            if s.source_type == "slack_channel":
                slack_channels.append(item)
            elif s.source_type == "gmail_label":
                gmail_labels.append(item)
            elif s.source_type == "notion_page":
                notion_pages.append(item)

        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "summary": project.summary,
            "main_goal": project.main_goal,
            "current_status_summary": project.current_status_summary,
            "important_notes": project.important_notes,
            "last_project_sync_at": project.last_project_sync_at.isoformat() if project.last_project_sync_at else None,
            "last_summary_generated_at": project.last_summary_generated_at.isoformat() if project.last_summary_generated_at else None,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
            "sources": {
                "slack_channels": slack_channels,
                "gmail_labels": gmail_labels,
                "notion_pages": notion_pages,
            },
        }
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error getting project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get project")


@app.put("/api/projects/{project_id}")
async def update_project(project_id: str, payload: ProjectUpdateRequest, current_user: AppUser = Depends(get_current_user)):
    """Update an existing project."""
    try:
        fields: Dict[str, Any] = payload.dict(exclude_unset=True)
        project = db_manager.update_project(project_id, owner_user_id=current_user.id, **fields)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        return {
            "id": project.id,
            "name": project.name,
            "description": project.description,
            "status": project.status,
            "summary": project.summary,
            "main_goal": project.main_goal,
            "current_status_summary": project.current_status_summary,
            "important_notes": project.important_notes,
            "last_project_sync_at": project.last_project_sync_at.isoformat() if project.last_project_sync_at else None,
            "last_summary_generated_at": project.last_summary_generated_at.isoformat() if project.last_summary_generated_at else None,
            "created_at": project.created_at.isoformat() if project.created_at else None,
            "updated_at": project.updated_at.isoformat() if project.updated_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error updating project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update project")


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str, current_user: AppUser = Depends(get_current_user)):
    """Delete a project and all associated mappings."""
    try:
        db_manager.delete_project(project_id, owner_user_id=current_user.id)
        return {"status": "ok"}
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error deleting project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete project")


@app.post("/api/projects/{project_id}/sources")
async def add_project_sources(project_id: str, sources: List[ProjectSourcePayload], current_user: AppUser = Depends(get_current_user)):
    """Add one or more sources to a project."""
    try:
        project = db_manager.get_project(project_id, owner_user_id=current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        created: List[Dict[str, Any]] = []
        for s in sources:
            mapping = db_manager.add_project_source(
                project_id=project_id,
                source_type=s.source_type,
                source_id=s.source_id,
                display_name=s.display_name,
            )
            created.append(
                {
                    "id": mapping.id,
                    "source_type": mapping.source_type,
                    "source_id": mapping.source_id,
                    "display_name": mapping.display_name,
                }
            )

        return {"sources": created}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error adding sources to project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add project sources")


@app.delete("/api/projects/{project_id}/sources/{source_type}/{source_id}")
async def delete_project_source(project_id: str, source_type: str, source_id: str, current_user: AppUser = Depends(get_current_user)):
    """Remove a specific source mapping from a project."""
    try:
        project = db_manager.get_project(project_id, owner_user_id=current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        db_manager.remove_project_source(project_id, source_type, source_id)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(
            f"Error removing source {source_type}:{source_id} from project {project_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to remove project source")


@app.post("/api/projects/{project_id}/auto-summary")
async def generate_project_summary(
    project_id: str,
    payload: ProjectSummaryRequest,
    current_user: AppUser = Depends(get_current_user),
):
    """Use the AI brain to generate a short description and summary for a project.

    This uses the same RAG engine and ChatGPT backend as the main chat, but the
    retrieval is scoped to Slack/Gmail/Notion data mapped to the project.
    """

    try:
        project = db_manager.get_project(project_id, owner_user_id=current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        sources = db_manager.get_project_sources(project_id)
        slack_channel_ids = [s.source_id for s in sources if s.source_type == "slack_channel"]
        gmail_label_ids = [s.source_id for s in sources if s.source_type == "gmail_label"]
        notion_page_ids = [s.source_id for s in sources if s.source_type == "notion_page"]

        if not (slack_channel_ids or gmail_label_ids or notion_page_ids):
            raise HTTPException(
                status_code=400,
                detail="Project has no linked sources; add Slack/Gmail/Notion sources first.",
            )

        # ------------------------------------------------------------------
        # Build a concrete text context directly from the project's sources.
        # This makes the summary robust even if vector embeddings are missing
        # or the search query does not match message contents.
        # ------------------------------------------------------------------

        engine = await get_rag_engine()

        context_lines: List[str] = []
        slack_limit = 80
        gmail_limit = 40
        notion_limit = 5

        with db_manager.get_session() as session:
            # Slack: recent messages from mapped channels
            if slack_channel_ids:
                slack_query = (
                    session.query(Message, Channel, User)
                    .join(Channel, Message.channel_id == Channel.channel_id)
                    .outerjoin(User, Message.user_id == User.user_id)
                    .filter(Message.channel_id.in_(slack_channel_ids))
                    .order_by(Message.timestamp.desc())
                    .limit(slack_limit)
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
                    ts = (
                        datetime.fromtimestamp(msg.timestamp).isoformat()
                        if msg.timestamp
                        else ""
                    )
                    text = (msg.text or "").replace("\n", " ").strip()
                    context_lines.append(
                        f"[SLACK] {ts} #{ch.name or ch.channel_id} "
                        f"{user_name or 'Someone'}: {text}"
                    )

            # Gmail: recent messages for mapped labels (scoped to current user)
            if gmail_label_ids:
                gmail_query = session.query(GmailMessage).filter(
                    GmailMessage.account_email == current_user.email
                )
                label_filters = [
                    cast(GmailMessage.label_ids, JSONB).contains([lbl])
                    for lbl in gmail_label_ids
                ]
                if label_filters:
                    gmail_query = gmail_query.filter(or_(*label_filters))

                gmail_query = gmail_query.order_by(GmailMessage.date.desc()).limit(
                    gmail_limit
                )

                for email in gmail_query.all():
                    ts = (
                        email.date.isoformat()
                        if email.date
                        else (email.created_at.isoformat() if email.created_at else "")
                    )
                    from_addr = email.from_address or "Unknown sender"
                    subject = (email.subject or "No subject").replace("\n", " ").strip()
                    snippet = (
                        email.snippet
                        or (email.body_text[:200] if email.body_text else "")
                    )
                    snippet = (snippet or "").replace("\n", " ").strip()
                    context_lines.append(
                        f"[GMAIL] {ts} from {from_addr} – {subject}: {snippet}"
                    )

            # Notion: a small slice of content from mapped pages (via RAG helper)
            notion_pages: List[NotionPage] = []
            if notion_page_ids:
                notion_pages = (
                    session.query(NotionPage)
                    .filter(NotionPage.page_id.in_(notion_page_ids))
                    .order_by(NotionPage.last_edited_time.desc())
                    .limit(notion_limit)
                    .all()
                )

        # Fetch Notion page text outside the DB session using the RAG helpers
        for page in notion_pages:
            try:
                page_text = engine._get_notion_page_text(page.page_id, max_blocks=40)
            except Exception:
                page_text = ""

            if not page_text:
                continue

            snippet = page_text.replace("\n", " ").strip()[:400]
            context_lines.append(
                f"[NOTION] {page.title or 'Untitled page'}: {snippet}"
            )

        if not context_lines:
            raw_text = (
                "I don't see any Slack messages, Gmail threads, or Notion pages "
                "for this project yet, so I cannot summarize actual activity."
            )
        else:
            # Keep context to a reasonable size for the LLM
            max_chars = 8000
            context_text = "\n".join(context_lines)
            if len(context_text) > max_chars:
                context_text = context_text[-max_chars:]

            system_prompt = (
                "You are helping maintain a single source of truth for a cross-tool "
                "project. Based ONLY on the context from Slack, Gmail, and Notion "
                "shown below, produce:\n\n"
                "1) A one-line short description of the project (max 140 characters).\n"
                "2) A 3-5 sentence high-level summary capturing goals, current state, "
                "and important updates.\n"
                "3) A concise main goal for the project (one or two sentences).\n"
                "4) A brief current status line (one or two sentences).\n"
                "5) A short list of important notes / risks / decisions (1-4 bullet points).\n\n"
                "Prefer summarizing what *is* known over saying there is not enough "
                "information, unless the context is truly empty. Return your answer "
                "as compact JSON with keys 'short_description', 'summary', 'main_goal', "
                "'current_status', and 'important_notes'."
            )

            user_prompt = (
                f"Project name: {project.name}\n\n"
                "Context from linked Slack, Gmail, and Notion sources "
                "(most recent items first):\n"
                f"{context_text}"
            )

            response = engine.llm.invoke(
                [
                    SystemMessage(content=system_prompt),
                    HumanMessage(content=user_prompt),
                ]
            )

            raw_text = response.content.strip()

        short_desc = None
        summary = None
        main_goal_text: Optional[str] = None
        current_status_text: Optional[str] = None
        important_notes_text: Optional[str] = None

        # Try to parse JSON; if it fails, fall back to simple heuristics.
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                short_desc = parsed.get("short_description")
                summary = parsed.get("summary")
                main_goal_text = parsed.get("main_goal")
                current_status_text = parsed.get("current_status") or parsed.get("status")
                important_notes_text = parsed.get("important_notes") or parsed.get("notes")
        except Exception:
            pass

        if not short_desc or not summary:
            # Heuristic: treat first line as short description, rest as summary.
            lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
            if lines:
                short_desc = short_desc or lines[0][:140]
                summary = summary or ("\n".join(lines[1:]) if len(lines) > 1 else lines[0])

        # Coerce all fields to plain strings or None so they can be safely
        # saved into ProjectUpdateRequest (Optional[str] fields).
        def _to_str(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, (list, tuple)):
                return "\n".join(str(v) for v in value)
            return str(value)

        short_desc = _to_str(short_desc)
        summary = _to_str(summary)
        main_goal_text = _to_str(main_goal_text)
        current_status_text = _to_str(current_status_text)
        important_notes_text = _to_str(important_notes_text)

        return {
            "project_id": project_id,
            "short_description": short_desc,
            "summary": summary,
            "main_goal": main_goal_text,
            "current_status": current_status_text,
            "important_notes": important_notes_text,
            "raw": raw_text,
        }

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error generating summary for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate project summary")


@app.post("/api/projects/{project_id}/sync")
async def sync_project_data(project_id: str, current_user: AppUser = Depends(get_current_user)):
    """Embed Slack and Gmail data for the project's mapped sources.

    This endpoint generates vector embeddings for Slack messages and Gmail
    messages that belong to the project's linked channels/labels and do not
    yet have embeddings in the generic embedding column. It also returns
    simple last-synced timestamps per source type so the UI can show freshness.
    """

    try:
        project = db_manager.get_project(project_id, owner_user_id=current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        sources = db_manager.get_project_sources(project_id)
        slack_channel_ids = [s.source_id for s in sources if s.source_type == "slack_channel"]
        gmail_label_ids = [s.source_id for s in sources if s.source_type == "gmail_label"]
        notion_page_ids = [s.source_id for s in sources if s.source_type == "notion_page"]

        if not (slack_channel_ids or gmail_label_ids or notion_page_ids):
            raise HTTPException(
                status_code=400,
                detail="Project has no linked sources; add Slack/Gmail/Notion sources first.",
            )

        engine = await get_rag_engine()

        def _sync() -> Dict[str, Any]:
            engine._ensure_models_loaded()
            embedding_model = engine.embedding_model

            indexed_slack = 0
            indexed_gmail = 0

            last_slack_ts: Optional[datetime] = None
            last_gmail_ts: Optional[datetime] = None
            last_notion_ts: Optional[datetime] = None

            with db_manager.get_session() as session:
                # Always compute last-synced timestamps for UI
                if slack_channel_ids:
                    last_msg = (
                        session.query(Message)
                        .filter(Message.channel_id.in_(slack_channel_ids))
                        .order_by(Message.timestamp.desc())
                        .first()
                    )
                    if last_msg and last_msg.timestamp:
                        last_slack_ts = datetime.fromtimestamp(last_msg.timestamp)

                if gmail_label_ids:
                    gmail_base = session.query(GmailMessage).filter(
                        GmailMessage.account_email == current_user.email
                    )
                    label_filters = [
                        cast(GmailMessage.label_ids, JSONB).contains([lbl])
                        for lbl in gmail_label_ids
                    ]
                    if label_filters:
                        gmail_base = gmail_base.filter(or_(*label_filters))

                    last_email = gmail_base.order_by(GmailMessage.date.desc()).first()
                    if last_email and last_email.date:
                        last_gmail_ts = last_email.date

                if notion_page_ids:
                    page = (
                        session.query(NotionPage)
                        .filter(NotionPage.page_id.in_(notion_page_ids))
                        .order_by(NotionPage.last_edited_time.desc())
                        .first()
                    )
                    if page and page.last_edited_time:
                        last_notion_ts = page.last_edited_time

                # Generate embeddings for unmapped rows using the configured
                # sentence-transformers model and the generic embedding column.
                if slack_channel_ids:
                    batch_size = 64
                    while True:
                        slack_batch = (
                            session.query(Message)
                            .filter(Message.channel_id.in_(slack_channel_ids))
                            .filter(Message.text.isnot(None))
                            .filter(Message.text != "")
                            .filter(Message.embedding.is_(None))
                            .order_by(Message.timestamp.desc())
                            .limit(batch_size)
                            .all()
                        )
                        if not slack_batch:
                            break

                        texts = [m.text for m in slack_batch]
                        embeddings = embedding_model.encode(
                            texts,
                            batch_size=len(texts),
                            is_query=False,
                            show_progress=False,
                        )
                        for msg, emb in zip(slack_batch, embeddings):
                            msg.embedding = emb.tolist()
                        indexed_slack += len(slack_batch)
                        session.commit()

                if gmail_label_ids:
                    gmail_query = session.query(GmailMessage).filter(
                        GmailMessage.account_email == current_user.email
                    )
                    label_filters = [
                        cast(GmailMessage.label_ids, JSONB).contains([lbl])
                        for lbl in gmail_label_ids
                    ]
                    if label_filters:
                        gmail_query = gmail_query.filter(or_(*label_filters))

                    batch_size = 32
                    while True:
                        gmail_batch = (
                            gmail_query.filter(GmailMessage.embedding.is_(None))
                            .order_by(GmailMessage.date.desc())
                            .limit(batch_size)
                            .all()
                        )
                        if not gmail_batch:
                            break

                        texts: List[str] = []
                        for email in gmail_batch:
                            text_parts: List[str] = []
                            if email.subject:
                                text_parts.append(email.subject)
                            if email.body_text:
                                text_parts.append(email.body_text[:1000])
                            text = "\n\n".join(text_parts).strip() or "Empty email"
                            texts.append(text)

                        embeddings = embedding_model.encode(
                            texts,
                            batch_size=len(texts),
                            is_query=False,
                            show_progress=False,
                        )
                        for email, emb in zip(gmail_batch, embeddings):
                            email.embedding = emb.tolist()
                        indexed_gmail += len(gmail_batch)
                        session.commit()

            return {
                "indexed_slack": indexed_slack,
                "indexed_gmail": indexed_gmail,
                "indexed_notion": 0,
                "last_synced": {
                    "slack": last_slack_ts.isoformat() if last_slack_ts else None,
                    "gmail": last_gmail_ts.isoformat() if last_gmail_ts else None,
                    "notion": last_notion_ts.isoformat() if last_notion_ts else None,
                },
            }

        sync_result = await _run_in_executor(_sync)
        try:
            db_manager.update_project(project_id, last_project_sync_at=datetime.utcnow())
        except Exception:
            logger.warning("Failed to update last_project_sync_at for project %s", project_id)

        return {"project_id": project_id, **sync_result}

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error syncing data for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to sync project data")


def _run_project_sync(
    run_id: str,
    project_id: str,
    owner_user_id: str,
    account_email: str,
) -> None:
    _update_pipeline_run(run_id, status="running", started_at=datetime.utcnow())

    stats: Dict[str, Any] = {
        "project_id": project_id,
        "stage": "starting",
        "progress": 0.0,
        "processed": 0,
        "total": 0,
        "indexed_slack": 0,
        "indexed_gmail": 0,
        "indexed_notion": 0,
        "last_synced": {"slack": None, "gmail": None, "notion": None},
    }

    def _check_cancel():
        if _is_cancel_requested(run_id):
            raise PipelineCancelled()

    try:
        project = db_manager.get_project(project_id, owner_user_id=owner_user_id)
        if not project:
            _update_pipeline_run(
                run_id,
                status="failed",
                finished_at=datetime.utcnow(),
                error="Project not found",
                stats=stats,
            )
            return

        sources = db_manager.get_project_sources(project_id)
        slack_channel_ids = [s.source_id for s in sources if s.source_type == "slack_channel"]
        gmail_label_ids = [s.source_id for s in sources if s.source_type == "gmail_label"]
        notion_page_ids = [s.source_id for s in sources if s.source_type == "notion_page"]

        embedding_model = _get_project_embedding_model()

        with db_manager.get_session() as session:
            total = 0

            for channel_id in slack_channel_ids:
                cursor = db_manager.get_project_sync_cursor(project_id, "slack_channel", channel_id) or 0.0
                cursor_dt = datetime.fromtimestamp(cursor) if cursor else datetime.utcfromtimestamp(0)
                _check_cancel()
                cnt = (
                    session.query(func.count(Message.message_id))
                    .filter(Message.channel_id == channel_id)
                    .filter(Message.text.isnot(None))
                    .filter(Message.text != "")
                    .filter(Message.embedding.is_(None))
                    .filter(Message.created_at > cursor_dt)
                    .scalar()
                )
                total += int(cnt or 0)

            for label_id in gmail_label_ids:
                cursor = db_manager.get_project_sync_cursor(project_id, "gmail_label", label_id) or 0.0
                cursor_dt = datetime.fromtimestamp(cursor) if cursor else datetime.utcfromtimestamp(0)
                _check_cancel()
                cnt = (
                    session.query(func.count(GmailMessage.message_id))
                    .filter(GmailMessage.account_email == account_email)
                    .filter(cast(GmailMessage.label_ids, JSONB).contains([label_id]))
                    .filter(GmailMessage.embedding.is_(None))
                    .filter(GmailMessage.created_at > cursor_dt)
                    .scalar()
                )
                total += int(cnt or 0)

            for page_id in notion_page_ids:
                cursor = db_manager.get_project_sync_cursor(project_id, "notion_page", page_id) or 0.0
                cursor_dt = datetime.fromtimestamp(cursor) if cursor else datetime.utcfromtimestamp(0)
                _check_cancel()
                cnt = (
                    session.query(func.count(NotionPage.page_id))
                    .filter(NotionPage.page_id == page_id)
                    .filter(
                        or_(
                            NotionPage.embedding.is_(None),
                            NotionPage.updated_at > cursor_dt,
                        )
                    )
                    .scalar()
                )
                total += int(cnt or 0)

            stats["total"] = total
            _update_pipeline_run(run_id, stats=stats)

            processed = 0

            for channel_id in slack_channel_ids:
                stats["stage"] = f"embedding_slack:{channel_id}"
                _update_pipeline_run(run_id, stats=stats)
                cursor = db_manager.get_project_sync_cursor(project_id, "slack_channel", channel_id) or 0.0
                cursor_dt = datetime.fromtimestamp(cursor) if cursor else datetime.utcfromtimestamp(0)
                last_ts = cursor
                while True:
                    _check_cancel()
                    batch = (
                        session.query(Message)
                        .filter(Message.channel_id == channel_id)
                        .filter(Message.text.isnot(None))
                        .filter(Message.text != "")
                        .filter(Message.embedding.is_(None))
                        .filter(Message.created_at > cursor_dt)
                        .order_by(Message.created_at.asc())
                        .limit(64)
                        .all()
                    )
                    if not batch:
                        break
                    texts = [m.text or "" for m in batch]
                    embeddings = embedding_model.encode(texts, batch_size=min(32, len(texts)), show_progress=False)
                    for msg, emb in zip(batch, embeddings):
                        msg.embedding = emb.tolist()
                        if msg.created_at:
                            last_ts = max(last_ts, msg.created_at.timestamp())
                    session.commit()
                    processed += len(batch)
                    stats["indexed_slack"] += len(batch)
                    stats["processed"] = processed
                    stats["progress"] = 1.0 if total == 0 else min(1.0, processed / total)
                    _update_pipeline_run(run_id, stats=stats)

                db_manager.upsert_project_sync_cursor(project_id, "slack_channel", channel_id, last_ts)

            for label_id in gmail_label_ids:
                stats["stage"] = f"embedding_gmail:{label_id}"
                _update_pipeline_run(run_id, stats=stats)
                cursor = db_manager.get_project_sync_cursor(project_id, "gmail_label", label_id) or 0.0
                cursor_dt = datetime.fromtimestamp(cursor) if cursor else datetime.utcfromtimestamp(0)
                last_ts = cursor
                while True:
                    _check_cancel()
                    batch = (
                        session.query(GmailMessage)
                        .filter(GmailMessage.account_email == account_email)
                        .filter(cast(GmailMessage.label_ids, JSONB).contains([label_id]))
                        .filter(GmailMessage.embedding.is_(None))
                        .filter(GmailMessage.created_at > cursor_dt)
                        .order_by(GmailMessage.created_at.asc())
                        .limit(32)
                        .all()
                    )
                    if not batch:
                        break

                    texts: List[str] = []
                    for email in batch:
                        parts: List[str] = []
                        if email.subject:
                            parts.append(email.subject)
                        if email.body_text:
                            parts.append(email.body_text[:1000])
                        text = "\n\n".join(parts).strip() or "Empty email"
                        texts.append(text)

                    embeddings = embedding_model.encode(texts, batch_size=min(16, len(texts)), show_progress=False)
                    for email, emb in zip(batch, embeddings):
                        email.embedding = emb.tolist()
                        if email.created_at:
                            last_ts = max(last_ts, email.created_at.timestamp())
                    session.commit()
                    processed += len(batch)
                    stats["indexed_gmail"] += len(batch)
                    stats["processed"] = processed
                    stats["progress"] = 1.0 if total == 0 else min(1.0, processed / total)
                    _update_pipeline_run(run_id, stats=stats)

                db_manager.upsert_project_sync_cursor(project_id, "gmail_label", label_id, last_ts)

            for page_id in notion_page_ids:
                stats["stage"] = f"embedding_notion:{page_id}"
                _update_pipeline_run(run_id, stats=stats)
                cursor = db_manager.get_project_sync_cursor(project_id, "notion_page", page_id) or 0.0
                cursor_dt = datetime.fromtimestamp(cursor) if cursor else datetime.utcfromtimestamp(0)
                last_ts = cursor
                while True:
                    _check_cancel()
                    batch = (
                        session.query(NotionPage)
                        .filter(NotionPage.page_id == page_id)
                        .filter(
                            or_(
                                NotionPage.embedding.is_(None),
                                NotionPage.updated_at > cursor_dt,
                            )
                        )
                        .order_by(NotionPage.updated_at.asc())
                        .limit(10)
                        .all()
                    )
                    if not batch:
                        break

                    texts = [f"Title: {p.title or 'Untitled'}" for p in batch]
                    embeddings = embedding_model.encode(texts, batch_size=min(8, len(texts)), show_progress=False)
                    for page, emb in zip(batch, embeddings):
                        page.embedding = emb.tolist()
                        if page.updated_at:
                            last_ts = max(last_ts, page.updated_at.timestamp())
                    session.commit()
                    processed += len(batch)
                    stats["indexed_notion"] += len(batch)
                    stats["processed"] = processed
                    stats["progress"] = 1.0 if total == 0 else min(1.0, processed / total)
                    _update_pipeline_run(run_id, stats=stats)

                db_manager.upsert_project_sync_cursor(project_id, "notion_page", page_id, last_ts)

        with db_manager.get_session() as session:
            last_slack_ts = None
            if slack_channel_ids:
                last_msg = (
                    session.query(Message)
                    .filter(Message.channel_id.in_(slack_channel_ids))
                    .order_by(Message.timestamp.desc())
                    .first()
                )
                if last_msg and last_msg.timestamp:
                    last_slack_ts = datetime.fromtimestamp(last_msg.timestamp)

            last_gmail_ts = None
            if gmail_label_ids:
                gmail_base = session.query(GmailMessage).filter(GmailMessage.account_email == account_email)
                label_filters = [cast(GmailMessage.label_ids, JSONB).contains([lbl]) for lbl in gmail_label_ids]
                if label_filters:
                    gmail_base = gmail_base.filter(or_(*label_filters))
                last_email = gmail_base.order_by(GmailMessage.date.desc()).first()
                if last_email and last_email.date:
                    last_gmail_ts = last_email.date

            last_notion_ts = None
            if notion_page_ids:
                last_page = (
                    session.query(NotionPage)
                    .filter(NotionPage.page_id.in_(notion_page_ids))
                    .order_by(NotionPage.last_edited_time.desc())
                    .first()
                )
                if last_page and last_page.last_edited_time:
                    last_notion_ts = last_page.last_edited_time

        stats["stage"] = "completed"
        stats["progress"] = 1.0
        stats["last_synced"] = {
            "slack": last_slack_ts.isoformat() if last_slack_ts else None,
            "gmail": last_gmail_ts.isoformat() if last_gmail_ts else None,
            "notion": last_notion_ts.isoformat() if last_notion_ts else None,
        }
        _update_pipeline_run(run_id, status="completed", finished_at=datetime.utcnow(), stats=stats)
        try:
            db_manager.update_project(project_id, owner_user_id=owner_user_id, last_project_sync_at=datetime.utcnow())
        except Exception:
            pass

    except PipelineCancelled:
        stats["stage"] = "cancelled"
        _update_pipeline_run(run_id, status="cancelled", finished_at=datetime.utcnow(), stats=stats)
    except KeyboardInterrupt:
        stats["stage"] = "cancelled"
        _update_pipeline_run(run_id, status="cancelled", finished_at=datetime.utcnow(), stats=stats)
    except Exception as e:  # pragma: no cover
        _update_pipeline_run(run_id, status="failed", finished_at=datetime.utcnow(), error=str(e), stats=stats)


def _run_project_auto_summary(
    run_id: str,
    project_id: str,
    owner_user_id: str,
    account_email: str,
    max_tokens: int = 256,
) -> None:
    _update_pipeline_run(run_id, status="running", started_at=datetime.utcnow())
    stats: Dict[str, Any] = {"project_id": project_id, "stage": "starting", "progress": 0.0}
    try:
        project = db_manager.get_project(project_id, owner_user_id=owner_user_id)
        if not project:
            _update_pipeline_run(run_id, status="failed", finished_at=datetime.utcnow(), error="Project not found")
            return

        sources = db_manager.get_project_sources(project_id)
        slack_channel_ids = [s.source_id for s in sources if s.source_type == "slack_channel"]
        gmail_label_ids = [s.source_id for s in sources if s.source_type == "gmail_label"]
        notion_page_ids = [s.source_id for s in sources if s.source_type == "notion_page"]

        if _is_cancel_requested(run_id):
            raise PipelineCancelled()

        engine = asyncio.run(get_rag_engine())
        stats["stage"] = "loading_context"
        stats["progress"] = 0.1
        _update_pipeline_run(run_id, stats=stats)

        context_lines: List[str] = []
        slack_limit = 80
        gmail_limit = 40
        notion_limit = 5

        with db_manager.get_session() as session:
            if slack_channel_ids:
                slack_query = (
                    session.query(Message, Channel, User)
                    .join(Channel, Message.channel_id == Channel.channel_id)
                    .outerjoin(User, Message.user_id == User.user_id)
                    .filter(Message.channel_id.in_(slack_channel_ids))
                    .order_by(Message.timestamp.desc())
                    .limit(slack_limit)
                )
                for msg, ch, user in slack_query.all():
                    if not msg.text:
                        continue
                    user_name = None
                    if user is not None:
                        user_name = user.real_name or user.display_name or user.username
                    ts = datetime.fromtimestamp(msg.timestamp).isoformat() if msg.timestamp else ""
                    text = (msg.text or "").replace("\n", " ").strip()
                    context_lines.append(
                        f"[SLACK] {ts} #{ch.name or ch.channel_id} {user_name or 'Someone'}: {text}"
                    )

            if gmail_label_ids:
                gmail_query = session.query(GmailMessage).filter(GmailMessage.account_email == account_email)
                label_filters = [cast(GmailMessage.label_ids, JSONB).contains([lbl]) for lbl in gmail_label_ids]
                if label_filters:
                    gmail_query = gmail_query.filter(or_(*label_filters))
                gmail_query = gmail_query.order_by(GmailMessage.date.desc()).limit(gmail_limit)
                for email in gmail_query.all():
                    ts = (
                        email.date.isoformat()
                        if email.date
                        else (email.created_at.isoformat() if email.created_at else "")
                    )
                    from_addr = email.from_address or "Unknown sender"
                    subject = (email.subject or "No subject").replace("\n", " ").strip()
                    snippet = email.snippet or (email.body_text[:200] if email.body_text else "")
                    snippet = (snippet or "").replace("\n", " ").strip()
                    context_lines.append(f"[GMAIL] {ts} from {from_addr} – {subject}: {snippet}")

            notion_pages: List[NotionPage] = []
            if notion_page_ids:
                notion_pages = (
                    session.query(NotionPage)
                    .filter(NotionPage.page_id.in_(notion_page_ids))
                    .order_by(NotionPage.last_edited_time.desc())
                    .limit(notion_limit)
                    .all()
                )

        if _is_cancel_requested(run_id):
            raise PipelineCancelled()

        stats["stage"] = "llm"
        stats["progress"] = 0.6
        _update_pipeline_run(run_id, stats=stats)

        for page in notion_pages:
            if _is_cancel_requested(run_id):
                raise PipelineCancelled()
            try:
                page_text = engine._get_notion_page_text(page.page_id, max_blocks=40)
            except Exception:
                page_text = ""
            if not page_text:
                continue
            snippet = page_text.replace("\n", " ").strip()[:400]
            context_lines.append(f"[NOTION] {page.title or 'Untitled page'}: {snippet}")

        max_chars = 8000
        context_text = "\n".join(context_lines)
        if len(context_text) > max_chars:
            context_text = context_text[-max_chars:]

        system_prompt = (
            "You are helping maintain a single source of truth for a cross-tool project. "
            "Based ONLY on the context from Slack, Gmail, and Notion shown below, produce compact JSON with keys "
            "'short_description', 'summary', 'main_goal', 'current_status', and 'important_notes'."
        )
        user_prompt = (
            f"Project name: {project.name}\n\n"
            "Context from linked Slack, Gmail, and Notion sources (most recent items first):\n"
            f"{context_text}"
        )

        response = engine.llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        raw_text = response.content.strip()

        short_desc = None
        summary = None
        main_goal_text: Optional[str] = None
        current_status_text: Optional[str] = None
        important_notes_text: Optional[str] = None
        try:
            parsed = json.loads(raw_text)
            if isinstance(parsed, dict):
                short_desc = parsed.get("short_description")
                summary = parsed.get("summary")
                main_goal_text = parsed.get("main_goal")
                current_status_text = parsed.get("current_status") or parsed.get("status")
                important_notes_text = parsed.get("important_notes") or parsed.get("notes")
        except Exception:
            pass

        def _to_str(value: Any) -> Optional[str]:
            if value is None:
                return None
            if isinstance(value, str):
                return value
            if isinstance(value, (list, tuple)):
                return "\n".join(str(v) for v in value)
            return str(value)

        short_desc = _to_str(short_desc)
        summary = _to_str(summary)
        main_goal_text = _to_str(main_goal_text)
        current_status_text = _to_str(current_status_text)
        important_notes_text = _to_str(important_notes_text)

        if _is_cancel_requested(run_id):
            raise PipelineCancelled()

        stats.update(
            {
                "stage": "saving",
                "progress": 0.9,
                "short_description": short_desc,
                "summary": summary,
                "main_goal": main_goal_text,
                "current_status": current_status_text,
                "important_notes": important_notes_text,
            }
        )
        _update_pipeline_run(run_id, stats=stats)

        db_manager.update_project(
            project_id,
            owner_user_id=owner_user_id,
            description=short_desc,
            summary=summary,
            main_goal=main_goal_text,
            current_status_summary=current_status_text,
            important_notes=important_notes_text,
            last_summary_generated_at=datetime.utcnow(),
        )

        stats["stage"] = "completed"
        stats["progress"] = 1.0
        _update_pipeline_run(run_id, status="completed", finished_at=datetime.utcnow(), stats=stats)
    except PipelineCancelled:
        stats["stage"] = "cancelled"
        _update_pipeline_run(run_id, status="cancelled", finished_at=datetime.utcnow(), stats=stats)
    except Exception as e:  # pragma: no cover
        _update_pipeline_run(run_id, status="failed", finished_at=datetime.utcnow(), error=str(e), stats=stats)


@app.post("/api/projects/{project_id}/sync/run")
async def run_project_sync(project_id: str, current_user: AppUser = Depends(get_current_user)):
    project = db_manager.get_project(project_id, owner_user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    run_id = uuid.uuid4().hex
    with db_manager.get_session() as session:
        pipeline_run = PipelineRun(
            run_id=run_id,
            pipeline_type="project_sync",
            status="pending",
            config={
                "project_id": project_id,
                "owner_user_id": current_user.id,
                "account_email": current_user.email,
            },
        )
        session.add(pipeline_run)
        session.commit()

    thread = threading.Thread(
        target=_run_project_sync,
        args=(run_id, project_id, current_user.id, current_user.email),
        daemon=True,
    )
    thread.start()
    return {"run_id": run_id, "status": "started"}


@app.get("/api/projects/sync/status/{run_id}")
async def get_project_sync_status(run_id: str, current_user: AppUser = Depends(get_current_user)):
    run = _get_pipeline_run(run_id)
    if not run or run.get("pipeline_type") != "project_sync":
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.get("config") or {}).get("owner_user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/projects/sync/stop/{run_id}")
async def stop_project_sync(run_id: str, current_user: AppUser = Depends(get_current_user)):
    run = _get_pipeline_run(run_id)
    if not run or run.get("pipeline_type") != "project_sync":
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.get("config") or {}).get("owner_user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    _update_pipeline_run(run_id, cancel_requested=True)
    return {"run_id": run_id, "status": "cancelling"}


@app.post("/api/projects/{project_id}/auto-summary/run")
async def run_project_auto_summary(
    project_id: str,
    payload: ProjectSummaryRequest,
    current_user: AppUser = Depends(get_current_user),
):
    project = db_manager.get_project(project_id, owner_user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    run_id = uuid.uuid4().hex
    with db_manager.get_session() as session:
        pipeline_run = PipelineRun(
            run_id=run_id,
            pipeline_type="project_summary",
            status="pending",
            config={
                "project_id": project_id,
                "owner_user_id": current_user.id,
                "account_email": current_user.email,
                "max_tokens": payload.max_tokens or 256,
            },
        )
        session.add(pipeline_run)
        session.commit()

    thread = threading.Thread(
        target=_run_project_auto_summary,
        args=(run_id, project_id, current_user.id, current_user.email, int(payload.max_tokens or 256)),
        daemon=True,
    )
    thread.start()
    return {"run_id": run_id, "status": "started"}


@app.get("/api/projects/auto-summary/status/{run_id}")
async def get_project_auto_summary_status(run_id: str, current_user: AppUser = Depends(get_current_user)):
    run = _get_pipeline_run(run_id)
    if not run or run.get("pipeline_type") != "project_summary":
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.get("config") or {}).get("owner_user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/projects/auto-summary/stop/{run_id}")
async def stop_project_auto_summary(run_id: str, current_user: AppUser = Depends(get_current_user)):
    run = _get_pipeline_run(run_id)
    if not run or run.get("pipeline_type") != "project_summary":
        raise HTTPException(status_code=404, detail="Run not found")
    if (run.get("config") or {}).get("owner_user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")
    _update_pipeline_run(run_id, cancel_requested=True)
    return {"run_id": run_id, "status": "cancelling"}


@app.get("/api/projects/{project_id}/activity")
async def get_project_activity(
    project_id: str,
    limit: int = 50,
    current_user: AppUser = Depends(get_current_user),
):
    """Return recent Slack/Gmail/Notion activity for a project.

    This aggregates events from mapped Slack channels, Gmail labels, and
    Notion pages and returns them as a unified, time-sorted list.
    """

    try:
        project = db_manager.get_project(project_id, owner_user_id=current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        sources = db_manager.get_project_sources(project_id)
        slack_channel_ids = [s.source_id for s in sources if s.source_type == "slack_channel"]
        gmail_label_ids = [s.source_id for s in sources if s.source_type == "gmail_label"]
        notion_page_ids = [s.source_id for s in sources if s.source_type == "notion_page"]

        activities: List[Dict[str, Any]] = []

        with db_manager.get_session() as session:
            # Slack activity
            if slack_channel_ids:
                slack_query = (
                    session.query(Message, Channel, User)
                    .join(Channel, Message.channel_id == Channel.channel_id)
                    .outerjoin(User, Message.user_id == User.user_id)
                    .filter(Message.channel_id.in_(slack_channel_ids))
                    .order_by(Message.timestamp.desc())
                    .limit(limit)
                )

                for msg, ch, user in slack_query.all():
                    user_name = None
                    if user is not None:
                        user_name = (
                            user.real_name
                            or user.display_name
                            or user.username
                        )

                    ts = datetime.fromtimestamp(msg.timestamp) if msg.timestamp else datetime.utcnow()
                    activities.append(
                        {
                            "source": "slack",
                            "timestamp": ts.isoformat(),
                            "title": f"{user_name or 'Someone'} in #{ch.name or ch.channel_id}",
                            "snippet": msg.text or "",
                            "metadata": {
                                "channel_id": ch.channel_id,
                                "channel_name": ch.name,
                                "user_id": msg.user_id,
                                "user_name": user_name,
                            },
                        }
                    )

            # Gmail activity
            if gmail_label_ids:
                gmail_query = session.query(GmailMessage).filter(
                    GmailMessage.account_email == current_user.email
                )
                label_filters = [
                    cast(GmailMessage.label_ids, JSONB).contains([lbl]) for lbl in gmail_label_ids
                ]
                if label_filters:
                    gmail_query = gmail_query.filter(or_(*label_filters))

                gmail_query = gmail_query.order_by(GmailMessage.date.desc()).limit(limit)

                for email in gmail_query.all():
                    ts = email.date or email.created_at or datetime.utcnow()
                    from_addr = email.from_address or "Unknown sender"
                    subject = email.subject or "No subject"
                    activities.append(
                        {
                            "source": "gmail",
                            "timestamp": ts.isoformat(),
                            "title": f"{from_addr} – {subject}",
                            "snippet": email.snippet or (email.body_text[:200] if email.body_text else ""),
                            "metadata": {
                                "message_id": email.message_id,
                                "from": from_addr,
                                "subject": subject,
                            },
                        }
                    )

            # Notion activity
            if notion_page_ids:
                notion_query = (
                    session.query(NotionPage)
                    .filter(NotionPage.page_id.in_(notion_page_ids))
                    .order_by(NotionPage.last_edited_time.desc())
                    .limit(limit)
                )

                for page in notion_query.all():
                    ts = page.last_edited_time or page.updated_at or datetime.utcnow()
                    activities.append(
                        {
                            "source": "notion",
                            "timestamp": ts.isoformat(),
                            "title": page.title or "Untitled page",
                            "snippet": None,
                            "metadata": {
                                "page_id": page.page_id,
                                "url": page.url,
                            },
                        }
                    )

        # Sort combined list and enforce global limit
        activities.sort(key=lambda a: a.get("timestamp") or "", reverse=True)
        if limit > 0:
            activities = activities[:limit]

        return {"project_id": project_id, "activities": activities}

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error fetching activity for project {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load project activity")


@app.post("/api/chat/project/{project_id}", response_model=ChatResponse)
async def chat_project(
    project_id: str,
    payload: ProjectChatRequest,
    current_user: AppUser = Depends(get_current_user),
):
    """Project-scoped chat using AI Brain with project context.

    The AI Brain will have access to project-specific data and can use
    all tools with awareness of the project scope.
    """

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty")

    try:
        project = db_manager.get_project(project_id, owner_user_id=current_user.id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")

        session_id = _project_chat_session_id(project_id, current_user.id)
        try:
            existing_session = db_manager.get_chat_session(session_id, owner_user_id=current_user.id)
            if not existing_session:
                db_manager.create_chat_session(
                    session_id,
                    title=f"Project: {project.name}",
                    owner_user_id=current_user.id,
                )
        except Exception:
            logger.warning("Failed ensuring project chat session exists", exc_info=True)

        sources = db_manager.get_project_sources(project_id)
        slack_channel_ids = [s.source_id for s in sources if s.source_type == "slack_channel"]
        gmail_label_ids = [s.source_id for s in sources if s.source_type == "gmail_label"]
        notion_page_ids = [s.source_id for s in sources if s.source_type == "notion_page"]

        conversation_history: List[Dict[str, str]] = []
        try:
            history = await _run_in_executor(db_manager.get_chat_history, session_id, 100)
            conversation_history = _truncate_history(history)
        except Exception:
            conversation_history = payload.conversation_history or []

        try:
            await _run_in_executor(db_manager.add_chat_message, session_id, "user", query)
        except Exception:
            logger.warning("Failed to save project chat user message", exc_info=True)

        # Use the hybrid RAG engine's project-scoped query instead of the generic
        # AI Brain tool-calling loop. This keeps project chat fast and strictly
        # limited to the project's linked Slack channels, Gmail labels, and
        # Notion pages, and it reuses the same retrieval logic as the project
        # summary/description pipeline.
        engine = await get_rag_engine()

        result = await _run_in_executor(
            engine.query_project,
            user_query=query,
            channel_ids=slack_channel_ids,
            label_ids=gmail_label_ids,
            notion_page_ids=notion_page_ids,
            project_name=project.name,
            conversation_history=conversation_history,
            force_search=True,
            gmail_account_email=current_user.email,
        )

        try:
            await _run_in_executor(
                db_manager.add_chat_message,
                session_id,
                "assistant",
                result.get("response", ""),
                result.get("sources", []),
            )
        except Exception:
            logger.warning("Failed to save project chat assistant message", exc_info=True)

        return ChatResponse(
            response=result.get("response", ""),
            sources=result.get("sources", []),
            intent=result.get("intent", "project_query"),
        )

    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error in project chat for {project_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Project chat failed")


@app.get("/api/projects/{project_id}/chat/history")
async def get_project_chat_history(
    project_id: str,
    limit: int = 200,
    current_user: AppUser = Depends(get_current_user),
):
    project = db_manager.get_project(project_id, owner_user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    session_id = _project_chat_session_id(project_id, current_user.id)
    session = db_manager.get_chat_session(session_id, owner_user_id=current_user.id)
    if not session:
        return {"project_id": project_id, "session_id": session_id, "messages": []}

    messages = db_manager.get_chat_history(session_id, limit=limit)
    return {"project_id": project_id, "session_id": session_id, "messages": messages}


@app.delete("/api/projects/{project_id}/chat/history")
async def clear_project_chat_history(
    project_id: str,
    current_user: AppUser = Depends(get_current_user),
):
    project = db_manager.get_project(project_id, owner_user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    session_id = _project_chat_session_id(project_id, current_user.id)
    db_manager.delete_chat_session(session_id, owner_user_id=current_user.id)
    return {"status": "ok", "project_id": project_id}


@app.get("/api/workflows")
async def list_workflows():
    """List workflows for the Workflows tab."""
    try:
        workflows = db_manager.list_workflows(limit=100)
        result: List[Dict[str, Any]] = []
        now = datetime.utcnow()
        for wf in workflows:
            channels = db_manager.get_workflow_channels(wf.id)
            is_active = wf.status == "active"
            next_run_at: Optional[str] = None
            due_now = False

            if wf.type == "slack_to_notion" and is_active:
                interval = wf.poll_interval_seconds or 30
                last_run = wf.last_run_at or (now - timedelta(seconds=interval * 2))
                next_due = last_run + timedelta(seconds=interval)
                next_run_at = next_due.isoformat()
                due_now = now >= next_due

            result.append(
                {
                    "id": wf.id,
                    "name": wf.name,
                    "type": wf.type,
                    "status": wf.status,
                    "is_active": is_active,
                    "notion_master_page_id": wf.notion_master_page_id,
                    "poll_interval_seconds": wf.poll_interval_seconds,
                    "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
                    "next_run_at": next_run_at,
                    "due_now": due_now,
                    "created_at": wf.created_at.isoformat() if wf.created_at else None,
                    "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
                    "channels": [
                        {
                            "slack_channel_id": c.slack_channel_id,
                            "slack_channel_name": c.slack_channel_name,
                            "notion_subpage_id": c.notion_subpage_id,
                            "last_slack_ts_synced": c.last_slack_ts_synced,
                            "created_at": c.created_at.isoformat() if c.created_at else None,
                            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                        }
                        for c in channels
                    ],
                }
            )
        return {"workflows": result}
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error listing workflows: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list workflows")


@app.post("/api/workflows")
async def create_workflow(payload: WorkflowCreateRequest):
    """Create a new workflow definition."""
    try:
        if payload.type != "slack_to_notion":
            raise HTTPException(
                status_code=400,
                detail="Unsupported workflow type; only 'slack_to_notion' is supported",
            )

        interval = payload.poll_interval_seconds or 3600
        if interval not in WORKFLOW_ALLOWED_INTERVALS:
            raise HTTPException(
                status_code=400,
                detail="Invalid poll_interval_seconds; allowed values are 3600, 10800, 28800, 86400",
            )

        status = payload.status or "active"

        workflow = db_manager.create_workflow(
            name=payload.name,
            type=payload.type,
            status=status,
            notion_master_page_id=payload.notion_master_page_id,
            poll_interval_seconds=interval,
        )

        response = {
            "id": workflow.id,
            "name": workflow.name,
            "type": workflow.type,
            "status": workflow.status,
            "notion_master_page_id": workflow.notion_master_page_id,
            "poll_interval_seconds": workflow.poll_interval_seconds,
            "last_run_at": workflow.last_run_at.isoformat() if workflow.last_run_at else None,
            "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
            "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
            "channels": [],
        }

        _reconcile_workflow_worker_state()
        return response
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error creating workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create workflow")


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get a workflow with its channel mappings."""
    try:
        workflow = db_manager.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        channels = db_manager.get_workflow_channels(workflow_id)
        return {
            "id": workflow.id,
            "name": workflow.name,
            "type": workflow.type,
            "status": workflow.status,
            "notion_master_page_id": workflow.notion_master_page_id,
            "poll_interval_seconds": workflow.poll_interval_seconds,
            "last_run_at": workflow.last_run_at.isoformat() if workflow.last_run_at else None,
            "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
            "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
            "channels": [
                {
                    "slack_channel_id": c.slack_channel_id,
                    "slack_channel_name": c.slack_channel_name,
                    "notion_subpage_id": c.notion_subpage_id,
                    "last_slack_ts_synced": c.last_slack_ts_synced,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
                for c in channels
            ],
        }
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error getting workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get workflow")


@app.put("/api/workflows/{workflow_id}")
async def update_workflow_endpoint(workflow_id: str, payload: WorkflowUpdateRequest):
    """Update an existing workflow."""
    try:
        fields: Dict[str, Any] = payload.dict(exclude_unset=True)
        if "poll_interval_seconds" in fields and fields["poll_interval_seconds"] is not None:
            interval = int(fields["poll_interval_seconds"])
            if interval not in WORKFLOW_ALLOWED_INTERVALS:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid poll_interval_seconds; allowed values are 3600, 10800, 28800, 86400",
                )

        workflow = db_manager.update_workflow(workflow_id, **fields)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        channels = db_manager.get_workflow_channels(workflow_id)
        response = {
            "id": workflow.id,
            "name": workflow.name,
            "type": workflow.type,
            "status": workflow.status,
            "notion_master_page_id": workflow.notion_master_page_id,
            "poll_interval_seconds": workflow.poll_interval_seconds,
            "last_run_at": workflow.last_run_at.isoformat() if workflow.last_run_at else None,
            "created_at": workflow.created_at.isoformat() if workflow.created_at else None,
            "updated_at": workflow.updated_at.isoformat() if workflow.updated_at else None,
            "channels": [
                {
                    "slack_channel_id": c.slack_channel_id,
                    "slack_channel_name": c.slack_channel_name,
                    "notion_subpage_id": c.notion_subpage_id,
                    "last_slack_ts_synced": c.last_slack_ts_synced,
                    "created_at": c.created_at.isoformat() if c.created_at else None,
                    "updated_at": c.updated_at.isoformat() if c.updated_at else None,
                }
                for c in channels
            ],
        }

        _reconcile_workflow_worker_state()
        return response
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error updating workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update workflow")


@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow_endpoint(workflow_id: str):
    """Delete a workflow and its mappings."""
    try:
        db_manager.delete_workflow(workflow_id)
        _reconcile_workflow_worker_state()
        return {"status": "ok"}
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error deleting workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete workflow")


@app.post("/api/workflows/{workflow_id}/channels")
async def add_workflow_channels(workflow_id: str, channels: List[WorkflowChannelPayload]):
    """Add one or more Slack channels to a workflow."""
    try:
        workflow = db_manager.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        created: List[Dict[str, Any]] = []
        for ch in channels:
            mapping = db_manager.add_workflow_channel(
                workflow_id=workflow_id,
                slack_channel_id=ch.slack_channel_id,
                slack_channel_name=ch.slack_channel_name,
            )
            created.append(
                {
                    "slack_channel_id": mapping.slack_channel_id,
                    "slack_channel_name": mapping.slack_channel_name,
                    "notion_subpage_id": mapping.notion_subpage_id,
                    "last_slack_ts_synced": mapping.last_slack_ts_synced,
                    "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
                    "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
                }
            )

        return {"channels": created}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error adding channels to workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to add workflow channels")


@app.delete("/api/workflows/{workflow_id}/channels/{slack_channel_id}")
async def delete_workflow_channel(workflow_id: str, slack_channel_id: str):
    """Remove a Slack channel mapping from a workflow."""
    try:
        workflow = db_manager.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        db_manager.remove_workflow_channel(workflow_id, slack_channel_id)
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(
            f"Error removing channel {slack_channel_id} from workflow {workflow_id}: {e}",
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Failed to remove workflow channel")


@app.post("/api/workflows/{workflow_id}/run-once")
async def run_workflow_once(workflow_id: str):
    """Run a workflow once synchronously.

    In v1 this endpoint only updates last_run_at and returns placeholder
    statistics. The Slack → Notion worker implementation will plug into
    this later.
    """
    try:
        workflow = db_manager.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Import here so the API can run even if the workflows package is not used
        # elsewhere, and to avoid circular import issues at module load time.
        try:
            from workflows.slack_to_notion_core import process_workflow_once
        except Exception as e:  # pragma: no cover - defensive
            logger.error(f"Failed to import workflow core: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail="Workflow core not available")

        stats = await _run_in_executor(process_workflow_once, workflow_id)

        return stats
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error running workflow {workflow_id} once: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to run workflow once")


# ============================================================================
# User Workflows v2 - Modular Source → AI Prompt → Output
# ============================================================================


class UserWorkflowCreateRequest(BaseModel):
    """Request to create a new user workflow."""
    name: str
    description: Optional[str] = None
    source_config: Optional[Dict[str, Any]] = None
    prompt_config: Optional[Dict[str, Any]] = None
    output_config: Optional[Dict[str, Any]] = None
    schedule_type: str = "manual"
    schedule_config: Optional[Dict[str, Any]] = None


class UserWorkflowUpdateRequest(BaseModel):
    """Request to update a user workflow."""
    name: Optional[str] = None
    description: Optional[str] = None
    source_config: Optional[Dict[str, Any]] = None
    prompt_config: Optional[Dict[str, Any]] = None
    output_config: Optional[Dict[str, Any]] = None
    schedule_type: Optional[str] = None
    schedule_config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None


def _serialize_user_workflow(wf) -> Dict[str, Any]:
    """Serialize a UserWorkflow model to a dict."""
    return {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "source_config": wf.source_config or {},
        "prompt_config": wf.prompt_config or {},
        "output_config": wf.output_config or {},
        "schedule_type": wf.schedule_type,
        "schedule_config": wf.schedule_config or {},
        "status": wf.status,
        "last_run_at": wf.last_run_at.isoformat() if wf.last_run_at else None,
        "next_run_at": wf.next_run_at.isoformat() if wf.next_run_at else None,
        "created_at": wf.created_at.isoformat() if wf.created_at else None,
        "updated_at": wf.updated_at.isoformat() if wf.updated_at else None,
    }


def _serialize_workflow_run(run) -> Dict[str, Any]:
    """Serialize a WorkflowRun model to a dict."""
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "source_items_count": run.source_items_count,
        "source_data_preview": run.source_data_preview,
        "ai_response": run.ai_response,
        "output_result": run.output_result,
        "error_message": run.error_message,
        "current_step": run.current_step,
        "progress_percent": run.progress_percent,
        "logs": run.logs or [],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@app.get("/api/v2/workflows")
async def list_user_workflows(user: AppUser = Depends(get_current_user)):
    """List all workflows for the workspace (shared)."""
    try:
        workflows = db_manager.list_user_workflows()
        return {"workflows": [_serialize_user_workflow(wf) for wf in workflows]}
    except Exception as e:
        logger.error(f"Error listing user workflows: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list workflows")


@app.post("/api/v2/workflows")
async def create_user_workflow(
    req: UserWorkflowCreateRequest,
    user: AppUser = Depends(get_current_user)
):
    """Create a new user workflow."""
    try:
        workflow = db_manager.create_user_workflow(
            owner_user_id=user.id,
            name=req.name,
            description=req.description,
            source_config=req.source_config,
            prompt_config=req.prompt_config,
            output_config=req.output_config,
            schedule_type=req.schedule_type,
            schedule_config=req.schedule_config,
        )
        return _serialize_user_workflow(workflow)
    except Exception as e:
        logger.error(f"Error creating user workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create workflow")


@app.get("/api/v2/workflows/{workflow_id}")
async def get_user_workflow(
    workflow_id: str,
    user: AppUser = Depends(get_current_user)
):
    """Get a specific workflow by ID."""
    try:
        workflow = db_manager.get_user_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return _serialize_user_workflow(workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting user workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get workflow")


@app.put("/api/v2/workflows/{workflow_id}")
async def update_user_workflow(
    workflow_id: str,
    req: UserWorkflowUpdateRequest,
    user: AppUser = Depends(get_current_user)
):
    """Update a workflow's configuration."""
    try:
        updates = {k: v for k, v in req.model_dump().items() if v is not None}
        workflow = db_manager.update_user_workflow(workflow_id, None, **updates)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return _serialize_user_workflow(workflow)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating user workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update workflow")


@app.delete("/api/v2/workflows/{workflow_id}")
async def delete_user_workflow(
    workflow_id: str,
    user: AppUser = Depends(get_current_user)
):
    """Delete a workflow and all its runs."""
    try:
        deleted = db_manager.delete_user_workflow(workflow_id, None)
        if not deleted:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting user workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete workflow")


@app.post("/api/v2/workflows/{workflow_id}/run")
async def run_user_workflow(
    workflow_id: str,
    user: AppUser = Depends(get_current_user)
):
    """Trigger a manual run of a workflow."""
    try:
        workflow = db_manager.get_user_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        # Import and run the workflow engine
        from workflows.workflow_engine import WorkflowExecutionEngine
        engine = WorkflowExecutionEngine(db_manager, workflow.owner_user_id)

        # Create a run record immediately so the UI can poll for status/logs.
        run = db_manager.create_workflow_run(workflow_id)
        run_id = run.id

        # Run in background thread to avoid blocking the API.
        loop = asyncio.get_running_loop()

        def _runner():
            return asyncio.run(engine.execute_workflow(workflow_id, run_id=run_id))

        fut = loop.run_in_executor(None, _runner)

        def _done_callback(f):
            try:
                _ = f.result()
            except Exception as e:  # pragma: no cover
                logger.error(f"Background workflow run failed (workflow_id={workflow_id}, run_id={run_id}): {e}", exc_info=True)

        fut.add_done_callback(_done_callback)

        return {"run_id": run_id, "status": "running"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error running user workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to run workflow")


class WorkflowRunResolveRequest(BaseModel):
    selection: str


@app.post("/api/v2/workflows/{workflow_id}/runs/{run_id}/resolve")
async def resolve_workflow_run_conflict(
    workflow_id: str,
    run_id: str,
    req: WorkflowRunResolveRequest,
    user: AppUser = Depends(get_current_user),
):
    """Resolve a paused workflow run conflict and resume execution."""
    try:
        workflow = db_manager.get_user_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        run = db_manager.get_workflow_run(run_id)
        if not run or run.workflow_id != workflow_id:
            raise HTTPException(status_code=404, detail="Run not found")

        if run.status != "awaiting_user_input":
            raise HTTPException(status_code=400, detail="Run is not awaiting user input")

        selection = (req.selection or "").strip()
        if not selection:
            raise HTTPException(status_code=400, detail="selection is required")

        from workflows.workflow_engine import WorkflowExecutionEngine
        engine = WorkflowExecutionEngine(db_manager, workflow.owner_user_id)

        loop = asyncio.get_running_loop()

        def _runner():
            return asyncio.run(engine.resume_workflow_run(workflow_id, run_id, selection))

        fut = loop.run_in_executor(None, _runner)

        def _done_callback(f):
            try:
                _ = f.result()
            except Exception as e:  # pragma: no cover
                logger.error(f"Background workflow resume failed (workflow_id={workflow_id}, run_id={run_id}): {e}", exc_info=True)

        fut.add_done_callback(_done_callback)

        return {"run_id": run_id, "status": "running"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving workflow run conflict {run_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to resolve workflow run conflict")


@app.get("/api/v2/workflows/{workflow_id}/runs")
async def list_workflow_runs(
    workflow_id: str,
    limit: int = 20,
    user: AppUser = Depends(get_current_user)
):
    """List runs for a workflow."""
    try:
        workflow = db_manager.get_user_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        runs = db_manager.list_workflow_runs(workflow_id, limit)
        return {"runs": [_serialize_workflow_run(r) for r in runs]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing runs for workflow {workflow_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list workflow runs")


@app.get("/api/v2/workflows/{workflow_id}/runs/{run_id}")
async def get_workflow_run(
    workflow_id: str,
    run_id: str,
    user: AppUser = Depends(get_current_user)
):
    """Get details of a specific workflow run."""
    try:
        workflow = db_manager.get_user_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        run = db_manager.get_workflow_run(run_id)
        if not run or run.workflow_id != workflow_id:
            raise HTTPException(status_code=404, detail="Run not found")

        return _serialize_workflow_run(run)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run {run_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get workflow run")


@app.post("/api/v2/workflows/{workflow_id}/runs/{run_id}/cancel")
async def cancel_workflow_run(
    workflow_id: str,
    run_id: str,
    user: AppUser = Depends(get_current_user)
):
    """Cancel a running workflow."""
    try:
        workflow = db_manager.get_user_workflow(workflow_id)
        if not workflow:
            raise HTTPException(status_code=404, detail="Workflow not found")

        run = db_manager.get_workflow_run(run_id)
        if not run or run.workflow_id != workflow_id:
            raise HTTPException(status_code=404, detail="Run not found")

        if run.status != "running":
            raise HTTPException(status_code=400, detail="Run is not currently running")

        # Mark the run as cancelled
        db_manager.update_workflow_run(
            run_id,
            status="cancelled",
            completed_at=datetime.utcnow(),
            current_step="cancelled",
            error_message="Cancelled by user"
        )
        db_manager.add_workflow_run_log(run_id, "info", "Workflow cancelled by user")

        return {"success": True, "message": "Workflow cancelled"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling run {run_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to cancel workflow run")


# ============================================================================
# Workflow Source Helpers (for UI dropdowns)
# ============================================================================


@app.get("/api/v2/workflows/sources/slack/channels")
async def get_workflow_slack_channels(user: AppUser = Depends(get_current_user)):
    """Get available Slack channels for workflow source configuration."""
    try:
        channels = db_manager.get_all_channels(include_archived=False)
        return {
            "channels": [
                {
                    "id": ch.channel_id,
                    "name": ch.name,
                    "is_private": ch.is_private,
                    "num_members": ch.num_members,
                }
                for ch in channels
            ]
        }
    except Exception as e:
        logger.error(f"Error getting Slack channels for workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get Slack channels")


@app.get("/api/v2/workflows/sources/gmail/labels")
async def get_workflow_gmail_labels(user: AppUser = Depends(get_current_user)):
    """Get available Gmail labels for workflow source configuration."""
    try:
        with db_manager.get_session() as session:
            from database.models import GmailLabel
            labels = session.query(GmailLabel).all()
            return {
                "labels": [
                    {
                        "id": label.label_id,
                        "name": label.name,
                        "type": label.type,
                    }
                    for label in labels
                ]
            }
    except Exception as e:
        logger.error(f"Error getting Gmail labels for workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get Gmail labels")


@app.get("/api/v2/workflows/sources/notion/pages")
async def get_workflow_notion_pages(user: AppUser = Depends(get_current_user)):
    """Get available Notion pages for workflow source configuration."""
    try:
        with db_manager.get_session() as session:
            pages = (
                session.query(NotionPage)
                .order_by(NotionPage.last_edited_time.desc())
                .limit(100)
                .all()
            )
            return {
                "pages": [
                    {
                        "id": page.page_id,
                        "title": page.title or "Untitled",
                        "object_type": page.object_type,
                        "url": page.url,
                    }
                    for page in pages
                ]
            }
    except Exception as e:
        logger.error(f"Error getting Notion pages for workflow: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get Notion pages")


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


# Helper functions for database-backed pipeline runs (works with multiple workers)
def _update_pipeline_run(run_id: str, **updates):
    """Update a pipeline run in the database."""
    with db_manager.get_session() as session:
        run = session.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        if run:
            for key, value in updates.items():
                setattr(run, key, value)
            session.commit()


def _get_pipeline_run(run_id: str) -> Optional[Dict[str, Any]]:
    """Get a pipeline run from the database."""
    with db_manager.get_session() as session:
        run = session.query(PipelineRun).filter(PipelineRun.run_id == run_id).first()
        if not run:
            return None
        return {
            "run_id": run.run_id,
            "pipeline_type": run.pipeline_type,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "stats": run.stats or {},
            "error": run.error,
            "config": run.config or {},
            "cancel_requested": run.cancel_requested,
        }


def _is_cancel_requested(run_id: str) -> bool:
    run = _get_pipeline_run(run_id)
    return bool(run and run.get("cancel_requested"))


def _run_slack_pipeline(run_id: str, include_archived: bool = False, download_files: bool = False) -> None:
    """Background worker that runs the Slack extraction pipeline.

    Uses the existing ExtractionCoordinator to perform a full workspace
    extraction (workspace, users, channels, messages, files) and updates the
    database with progress and statistics.
    """

    logger.info(
        "Starting Slack pipeline run %s (include_archived=%s, download_files=%s)",
        run_id,
        include_archived,
        download_files,
    )

    _update_pipeline_run(run_id, status="running", started_at=datetime.utcnow())

    coordinator = ExtractionCoordinator(db_manager=db_manager)

    try:
        results = coordinator.extract_all(
            include_archived=include_archived,
            download_files=download_files,
        )

        stats = results.get("statistics", {}) or {}
        run_stats = {
            "users": stats.get("users", 0),
            "channels": stats.get("channels", 0),
            "messages": stats.get("messages", 0),
            "files": stats.get("files", 0),
            "reactions": stats.get("reactions", 0),
        }

        # Check if cancel was requested
        run_info = _get_pipeline_run(run_id)
        if run_info and run_info.get("cancel_requested"):
            _update_pipeline_run(run_id, status="cancelled", finished_at=datetime.utcnow(), stats=run_stats)
            logger.info("Slack pipeline run %s marked as cancelled", run_id)
        else:
            _update_pipeline_run(run_id, status="completed", finished_at=datetime.utcnow(), stats=run_stats)
            logger.info("Slack pipeline run %s completed: %s", run_id, run_stats)

            if Config.AUTO_SYNC_EMBEDDINGS_AFTER_PIPELINE:
                # Automatically sync embeddings after successful extraction
                try:
                    logger.info("Auto-syncing Slack embeddings...")
                    embed_stats = sync_embeddings_after_pipeline(
                        data_source="slack",
                        db_manager=db_manager
                    )
                    # Update stats with embedding info
                    run_stats["embedding_stats"] = embed_stats
                    _update_pipeline_run(run_id, stats=run_stats)
                    logger.info("✓ Slack embeddings synced: %s", embed_stats)
                except Exception as embed_error:
                    logger.error(f"Embedding sync failed (non-fatal): {embed_error}")
                    run_stats["embedding_error"] = str(embed_error)
                    _update_pipeline_run(run_id, stats=run_stats)

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Slack pipeline run {run_id} failed: {e}", exc_info=True)
        _update_pipeline_run(run_id, status="failed", finished_at=datetime.utcnow(), error=str(e))


@app.post("/api/pipelines/slack/run")
async def run_slack_pipeline(
    include_archived: bool = False,
    download_files: bool = False,
    current_user: AppUser = Depends(get_current_user),
):
    """Trigger a Slack pipeline run in the background.

    Args:
        include_archived: Whether to include archived channels in extraction.
        download_files: Whether to download Slack file contents as part of the run.

    Returns:
        JSON with the new pipeline run ID and initial status.
    """

    run_id = uuid.uuid4().hex
    
    # Create pipeline run in database (works with multiple workers)
    with db_manager.get_session() as session:
        pipeline_run = PipelineRun(
            run_id=run_id,
            pipeline_type="slack",
            status="pending",
            config={"include_archived": include_archived, "download_files": download_files},
        )
        session.add(pipeline_run)
        session.commit()

    thread = threading.Thread(
        target=_run_slack_pipeline,
        args=(run_id, include_archived, download_files),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "started"}


def _run_slack_channel_pipeline(
    run_id: str,
    channel_id: str,
    include_threads: bool = False,
    lookback_hours: Optional[int] = 24,
) -> None:
    """Background worker to refresh a single Slack channel incrementally."""
    logger.info(
        "Starting Slack channel pipeline run %s (channel=%s, include_threads=%s, lookback_hours=%s)",
        run_id,
        channel_id,
        include_threads,
        lookback_hours,
    )

    _update_pipeline_run(run_id, status="running", started_at=datetime.utcnow())

    # Determine incremental window from SyncStatus
    sync_status = db_manager.get_sync_status(channel_id)
    oldest = None
    if sync_status and sync_status.last_synced_ts:
        oldest = sync_status.last_synced_ts
        if lookback_hours and lookback_hours > 0:
            # Revisit a small window to capture edits/reactions
            revisit = datetime.utcnow().timestamp() - (lookback_hours * 3600)
            oldest = min(oldest, revisit) if oldest else revisit
    elif lookback_hours and lookback_hours > 0:
        oldest = datetime.utcnow().timestamp() - (lookback_hours * 3600)

    extractor = MessageExtractor(db_manager=db_manager)

    # Stats container
    stats: Dict[str, Any] = {"channel_id": channel_id, "progress": 0.0}

    def progress_cb(payload: Dict[str, float]):
        # payload keys: stage, progress, total_messages, processed_messages
        stats.update(payload)
        if _is_cancel_requested(run_id):
            raise PipelineCancelled()
        _update_pipeline_run(run_id, stats=stats)

    try:
        count = extractor.extract_channel_history(
            channel_id=channel_id,
            oldest=oldest,
            include_threads=include_threads,
            progress_callback=progress_cb,
        )

        stats.update(
            {
                "messages": count,
                "progress": 1.0,
                "completed_at": datetime.utcnow().isoformat(),
            }
        )
        _update_pipeline_run(
            run_id,
            status="completed",
            finished_at=datetime.utcnow(),
            stats=stats,
        )
        logger.info(
            "Slack channel pipeline run %s completed: channel=%s, messages=%s",
            run_id,
            channel_id,
            count,
        )
    except PipelineCancelled:
        logger.info("Slack channel pipeline run %s cancelled", run_id)
        _update_pipeline_run(
            run_id,
            status="cancelled",
            finished_at=datetime.utcnow(),
            stats=stats,
        )
    except KeyboardInterrupt:
        logger.info("Slack channel pipeline run %s cancelled (interrupt)", run_id)
        _update_pipeline_run(
            run_id,
            status="cancelled",
            finished_at=datetime.utcnow(),
            stats=stats,
        )
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Slack channel pipeline run {run_id} failed: {e}", exc_info=True)
        _update_pipeline_run(
            run_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error=str(e),
            stats=stats,
        )


def _run_slack_channels_refresh(
    run_id: str,
    include_archived: bool = False,
) -> None:
    """Background worker to refresh Slack channel list only."""
    logger.info("Starting Slack channel list refresh run %s", run_id)
    _update_pipeline_run(run_id, status="running", started_at=datetime.utcnow())

    extractor = ChannelExtractor(db_manager=db_manager)
    stats: Dict[str, Any] = {"progress": 0.0}

    def progress_cb(payload: Dict[str, Any]):
        stats.update(payload)
        if _is_cancel_requested(run_id):
            raise PipelineCancelled()
        _update_pipeline_run(run_id, stats=stats)

    try:
        count = extractor.extract_all_channels(
            exclude_archived=not include_archived,
            progress_callback=progress_cb,
            cancel_check=lambda: _is_cancel_requested(run_id),
        )
        stats.update({"channels": count, "progress": 1.0, "completed_at": datetime.utcnow().isoformat()})
        _update_pipeline_run(run_id, status="completed", finished_at=datetime.utcnow(), stats=stats)
        logger.info("Slack channel list refresh run %s completed, channels=%s", run_id, count)
    except PipelineCancelled:
        logger.info("Slack channel list refresh run %s cancelled", run_id)
        _update_pipeline_run(
            run_id,
            status="cancelled",
            finished_at=datetime.utcnow(),
            stats=stats,
        )
    except KeyboardInterrupt:
        logger.info("Slack channel list refresh run %s cancelled (interrupt)", run_id)
        _update_pipeline_run(
            run_id,
            status="cancelled",
            finished_at=datetime.utcnow(),
            stats=stats,
        )
    except Exception as e:  # pragma: no cover
        logger.error(f"Slack channel list refresh run {run_id} failed: {e}", exc_info=True)
        _update_pipeline_run(
            run_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error=str(e),
            stats=stats,
        )


@app.post("/api/pipelines/slack/channel/run")
async def run_slack_channel_pipeline(
    channel_id: str,
    include_threads: bool = False,
    lookback_hours: Optional[int] = 24,
    current_user: AppUser = Depends(get_current_user),
):
    """Trigger an incremental Slack pipeline run for a single channel."""
    if not channel_id:
        raise HTTPException(status_code=400, detail="channel_id is required")

    run_id = uuid.uuid4().hex

    with db_manager.get_session() as session:
        pipeline_run = PipelineRun(
            run_id=run_id,
            pipeline_type="slack_channel",
            status="pending",
            config={
                "channel_id": channel_id,
                "include_threads": include_threads,
                "lookback_hours": lookback_hours,
            },
        )
        session.add(pipeline_run)
        session.commit()

    thread = threading.Thread(
        target=_run_slack_channel_pipeline,
        args=(run_id, channel_id, include_threads, lookback_hours),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/pipelines/slack/channel/status/{run_id}")
async def get_slack_channel_pipeline_status(
    run_id: str,
    current_user: AppUser = Depends(get_current_user),
):
    """Get the status of a single-channel Slack pipeline run."""
    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/pipelines/slack/channel/stop/{run_id}")
async def stop_slack_channel_pipeline(
    run_id: str,
    current_user: AppUser = Depends(get_current_user),
):
    """Request cancellation of a single-channel Slack pipeline run."""
    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["pipeline_type"] != "slack_channel":
        raise HTTPException(status_code=400, detail="Run is not a slack_channel pipeline")

    _update_pipeline_run(run_id, cancel_requested=True)
    return {"run_id": run_id, "status": "cancelling"}


@app.post("/api/pipelines/slack/channels/refresh")
async def refresh_slack_channel_list(
    include_archived: bool = False,
    current_user: AppUser = Depends(get_current_user),
):
    """Refresh Slack channel list only (no messages/files) with background progress."""
    run_id = uuid.uuid4().hex

    with db_manager.get_session() as session:
        pipeline_run = PipelineRun(
            run_id=run_id,
            pipeline_type="slack_channels",
            status="pending",
            config={"include_archived": include_archived},
        )
        session.add(pipeline_run)
        session.commit()

    thread = threading.Thread(
        target=_run_slack_channels_refresh,
        args=(run_id, include_archived),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.post("/api/pipelines/slack/channels/stop/{run_id}")
async def stop_slack_channel_list(
    run_id: str,
    current_user: AppUser = Depends(get_current_user),
):
    """Request cancellation of Slack channel list refresh."""
    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run["pipeline_type"] != "slack_channels":
        raise HTTPException(status_code=400, detail="Run is not a slack_channels pipeline")

    _update_pipeline_run(run_id, cancel_requested=True)
    return {"run_id": run_id, "status": "cancelling"}


@app.get("/api/pipelines/slack/status/{run_id}")
async def get_slack_pipeline_status(
    run_id: str,
    current_user: AppUser = Depends(get_current_user),
):
    """Get the status of a Slack pipeline run."""

    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/pipelines/slack/stop/{run_id}")
async def stop_slack_pipeline(
    run_id: str,
    current_user: AppUser = Depends(get_current_user),
):
    """Request cancellation of a Slack pipeline run.

    Note: the underlying extraction cannot be force-stopped yet, but the
    run will be marked as cancelling/cancelled so the UI can reflect the
    user's intent.
    """

    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    _update_pipeline_run(
        run_id,
        cancel_requested=True,
        status="cancelling" if run.get("status") in ("pending", "running") else run.get("status"),
        finished_at=datetime.utcnow(),
    )
    return _get_pipeline_run(run_id)


@app.get("/api/pipelines/slack/data")
async def get_slack_pipeline_data(
    current_user: AppUser = Depends(get_current_user),
):
    """Return structured Slack data for the Pipelines UI.

    For v1 this returns:
    - Overall Slack stats (users, channels, messages, files, reactions)
    - Channel list with basic metadata and message counts
    """

    try:
        # Use batch query to avoid N+1 problem (was 1 query per channel!)
        channels = db_manager.get_all_channels(include_archived=True)
        stats = db_manager.get_statistics()
        message_counts = db_manager.get_messages_count_by_channel()

        channel_data = [
            {
                "channel_id": ch.channel_id,
                "name": ch.name,
                "is_private": ch.is_private,
                "is_archived": ch.is_archived,
                "num_members": ch.num_members,
                "message_count": message_counts.get(ch.channel_id, 0),
            }
            for ch in channels
        ]

        return {
            "stats": stats,
            "channels": channel_data,
        }

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error fetching Slack pipeline data: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pipelines/slack/channels/options")
async def get_slack_channel_options(current_user: AppUser = Depends(get_current_user)):
    """Return Slack channel options for selection UIs (Projects tab).

    This endpoint is intentionally lightweight vs /api/pipelines/slack/data:
    it does NOT compute global stats or per-channel message counts.
    """

    global _slack_channel_options_cache

    try:
        now = time.time()
        cached_at, cached = _slack_channel_options_cache
        if cached and (now - cached_at) < _OPTIONS_CACHE_TTL_SECONDS:
            return cached

        channels = db_manager.get_all_channels(include_archived=True)
        payload = {
            "channels": [
                {
                    "channel_id": ch.channel_id,
                    "name": ch.name,
                    "is_private": ch.is_private,
                    "is_archived": ch.is_archived,
                }
                for ch in channels
            ]
        }
        _slack_channel_options_cache = (now, payload)
        return payload
    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Error fetching Slack channel options: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/pipelines/slack/messages")
async def get_slack_channel_messages(
    channel_id: str,
    limit: int = 200,
    current_user: AppUser = Depends(get_current_user),
):
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
    session: Optional[Session] = None,
    commit: bool = True,
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

        owns_session = session is None
        if owns_session:
            session = db_manager.get_session()

        assert session is not None

        # Ensure the GmailThread row exists so the foreign key on
        # GmailMessage.thread_id does not fail the insert.
        thread = None
        if thread_id:
            thread = session.get(GmailThread, thread_id)
            if not thread:
                thread = GmailThread(
                    thread_id=thread_id,
                    account_email=account_email,
                    snippet=full_msg.get("snippet", ""),
                    history_id=full_msg.get("historyId"),
                )
                session.add(thread)

        msg = session.get(GmailMessage, msg_id)
        is_new_message = msg is None
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

        # Keep basic thread metadata in sync (avoid per-message COUNT(*) queries)
        if thread is not None:
            thread.snippet = thread.snippet or full_msg.get("snippet", "")
            thread.history_id = full_msg.get("historyId") or thread.history_id
            if is_new_message:
                thread.message_count = int(thread.message_count or 0) + 1
            thread.updated_at = datetime.utcnow()

        if commit:
            session.commit()

        if owns_session:
            session.close()

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Failed to persist Gmail message {full_msg.get('id')}: {e}", exc_info=True)


def _run_gmail_pipeline(run_id: str, label_id: str, user_id: str) -> None:
    """Background worker to fetch new Gmail messages for a specific label.

    Uses GmailClient with per-user OAuth credentials, stores messages in
    PostgreSQL, and syncs embeddings. Incremental behavior is controlled by
    internalDate stored per label in a small JSON state file.
    """

    logger.info("Starting Gmail pipeline run %s for label %s (user_id=%s)", run_id, label_id, user_id)

    run_stats: Dict[str, Any] = {"label_id": label_id}
    _update_pipeline_run(run_id, status="running", started_at=datetime.utcnow(), stats=run_stats)

    creds = _build_google_credentials_for_user_id(user_id)
    if not creds:
        _update_pipeline_run(
            run_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error="Gmail not authorized for user",
            stats=run_stats,
        )
        logger.error("No valid Gmail credentials for user %s in pipeline run %s", user_id, run_id)
        return

    client = GmailClient()
    if not client.init_with_credentials(creds):
        _update_pipeline_run(
            run_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error="Gmail authentication failed",
            stats=run_stats,
        )
        logger.error("Gmail authentication failed for pipeline run %s", run_id)
        return

    # Ensure the GmailAccount row exists/updated for this user so the
    # pipelines view can show Gmail stats similar to Slack.
    _ensure_gmail_account_profile(client)

    # Load incremental state, scoped per Gmail account email so multiple
    # users with the same label IDs (e.g., "INBOX") do not share a single
    # global cursor. For backward compatibility with the previous
    # label-only JSON structure, we gracefully fall back.
    state_all = _load_gmail_state() or {}
    account_email = client.user_email

    last_ts_ms = 0
    if account_email:
        user_state = state_all.get(account_email)
        if isinstance(user_state, dict):
            try:
                last_ts_ms = int(user_state.get(label_id) or 0)
            except Exception:
                last_ts_ms = 0
        else:
            # Old format: top-level dict keyed by label_id
            try:
                last_ts_ms = int(state_all.get(label_id) or 0)
            except Exception:
                last_ts_ms = 0
    else:
        try:
            last_ts_ms = int(state_all.get(label_id) or 0)
        except Exception:
            last_ts_ms = 0

    messages: List[Dict[str, Any]] = []
    max_new_messages = 500
    processed_new = 0
    newest_ts_ms = last_ts_ms
    page_token: Optional[str] = None
    stop = False

    try:
        commit_batch_size = max(1, int(getattr(Config, "BATCH_SIZE", 100)))
        pending_commits = 0

        with db_manager.get_session() as session:
            while not stop and processed_new < max_new_messages:
                # Cooperative cancellation support
                if _is_cancel_requested(run_id):
                    session.commit()
                    run_stats["message_count"] = len(messages)
                    _update_pipeline_run(
                        run_id,
                        status="cancelled",
                        finished_at=datetime.utcnow(),
                        stats=run_stats,
                    )
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
                    _persist_gmail_message_from_full(
                        full_msg,
                        client,
                        date_val,
                        body_text,
                        body_html,
                        session=session,
                        commit=False,
                    )
                    pending_commits += 1
                    if pending_commits % commit_batch_size == 0:
                        session.commit()

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
                        _persist_gmail_message_from_full(
                            full_msg,
                            client,
                            date_val,
                            body_text,
                            body_html,
                            session=session,
                            commit=False,
                        )
                        pending_commits += 1
                        if pending_commits % commit_batch_size == 0:
                            session.commit()

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

            session.commit()

        gmail_run_messages[run_id] = messages
        run_stats["message_count"] = len(messages)
        _update_pipeline_run(
            run_id,
            status="completed",
            finished_at=datetime.utcnow(),
            stats=run_stats,
        )

        if newest_ts_ms > last_ts_ms:
            if account_email:
                user_state = state_all.get(account_email)
                if not isinstance(user_state, dict):
                    user_state = {}
                user_state[label_id] = newest_ts_ms
                state_all[account_email] = user_state
            else:
                state_all[label_id] = newest_ts_ms
            _save_gmail_state(state_all)

        logger.info(
            "Gmail pipeline run %s completed for label %s with %s messages",
            run_id,
            label_id,
            len(messages),
        )

        if Config.AUTO_SYNC_EMBEDDINGS_AFTER_PIPELINE:
            # Automatically sync embeddings after successful ingestion
            try:
                logger.info("Auto-syncing Gmail embeddings for label %s...", label_id)
                embed_stats = sync_embeddings_after_pipeline(
                    data_source="gmail",
                    source_ids=[label_id],
                    db_manager=db_manager
                )
                run_stats["embedding_stats"] = embed_stats
                _update_pipeline_run(run_id, stats=run_stats)
                logger.info("✓ Gmail embeddings synced: %s", embed_stats)
            except Exception as embed_error:
                logger.error(f"Embedding sync failed (non-fatal): {embed_error}")
                run_stats["embedding_error"] = str(embed_error)
                _update_pipeline_run(run_id, stats=run_stats)

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Gmail pipeline run {run_id} failed: {e}", exc_info=True)
        run_stats["error"] = str(e)
        _update_pipeline_run(
            run_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error=str(e),
            stats=run_stats,
        )


@app.get("/api/pipelines/gmail/labels")
async def list_gmail_labels(current_user: AppUser = Depends(get_current_user)):
    """List available Gmail labels using the Gmail API."""
    now = time.time()
    cached = _gmail_labels_cache.get(current_user.id)
    if cached and (now - cached[0]) < _OPTIONS_CACHE_TTL_SECONDS:
        return cached[1]

    creds = _build_google_credentials_for_user_id(current_user.id)
    if not creds:
        # Return empty label list if Gmail is not connected for this user.
        logger.warning("Gmail not connected for user %s; returning empty label list", current_user.id)
        payload = {"labels": []}
        _gmail_labels_cache[current_user.id] = (now, payload)
        return payload

    client = GmailClient()
    if not client.init_with_credentials(creds):
        logger.error("Gmail init_with_credentials failed when listing labels for user %s", current_user.id)
        payload = {"labels": []}
        _gmail_labels_cache[current_user.id] = (now, payload)
        return payload

    labels = client.list_labels() or []
    payload = {
        "labels": [
            {"id": lbl.get("id"), "name": lbl.get("name"), "type": lbl.get("type")}
            for lbl in labels
            if lbl.get("id") and lbl.get("name")
        ]
    }
    _gmail_labels_cache[current_user.id] = (now, payload)
    return payload


@app.post("/api/pipelines/gmail/run")
async def run_gmail_pipeline(label_id: str, current_user: AppUser = Depends(get_current_user)):
    """Trigger a Gmail pipeline run for a specific label.

    Args:
        label_id: Gmail label ID to fetch messages for.
    """

    if not label_id:
        raise HTTPException(status_code=400, detail="label_id is required")

    # Ensure the user has Gmail connected before starting the pipeline
    creds = _build_google_credentials_for_user_id(current_user.id)
    if not creds:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Gmail not authorized")

    run_id = uuid.uuid4().hex

    with db_manager.get_session() as session:
        pipeline_run = PipelineRun(
            run_id=run_id,
            pipeline_type="gmail",
            status="pending",
            config={"label_id": label_id, "user_id": current_user.id},
        )
        session.add(pipeline_run)
        session.commit()

    thread = threading.Thread(target=_run_gmail_pipeline, args=(run_id, label_id, current_user.id), daemon=True)
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/pipelines/gmail/status/{run_id}")
async def get_gmail_pipeline_status(run_id: str, current_user: AppUser = Depends(get_current_user)):
    """Get the status of a Gmail pipeline run."""

    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    cfg = run.get("config") or {}
    if cfg.get("user_id") != current_user.id:
        # Hide existence of other users' runs
        raise HTTPException(status_code=404, detail="Run not found")

    return run


@app.post("/api/pipelines/gmail/stop/{run_id}")
async def stop_gmail_pipeline(run_id: str, current_user: AppUser = Depends(get_current_user)):
    """Request cancellation of a Gmail pipeline run."""

    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    cfg = run.get("config") or {}
    if cfg.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    updates: Dict[str, Any] = {"cancel_requested": True}
    if run.get("status") in ("pending", "running"):
        updates["status"] = "cancelling"
    _update_pipeline_run(run_id, **updates)

    refreshed = _get_pipeline_run(run_id)
    return refreshed or {"run_id": run_id, "status": "cancelling"}


@app.get("/api/pipelines/gmail/messages")
async def get_gmail_pipeline_messages(run_id: str, current_user: AppUser = Depends(get_current_user)):
    """Return messages for a specific Gmail pipeline run."""

    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    cfg = run.get("config") or {}
    if cfg.get("user_id") != current_user.id:
        raise HTTPException(status_code=404, detail="Run not found")

    label_id = cfg.get("label_id")

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
                    .filter(GmailMessage.account_email == current_user.email)
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
async def get_gmail_messages_by_label(label_id: str, limit: int = 200, current_user: AppUser = Depends(get_current_user)):
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
                .filter(GmailMessage.account_email == current_user.email)
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


# notion_run_pages still in-memory for large page data (not critical for status)
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


def _summarize_notion_blocks(
    blocks: List[Dict[str, Any]],
    include_databases: bool = True,
) -> Tuple[List[str], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Summarize Notion blocks into text lines, attachments, and database references.
    
    Returns:
        Tuple of (text_lines, attachments, child_databases)
    """
    lines: List[str] = []
    attachments: List[Dict[str, Any]] = []
    child_databases: List[Dict[str, Any]] = []

    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if not block_type:
            continue

        value = block.get(block_type) or {}

        # Handle child_database blocks
        if block_type == "child_database" and include_databases:
            db_id = block.get("id")
            db_title = value.get("title", "Database")
            if db_id:
                child_databases.append({
                    "id": db_id,
                    "title": db_title,
                    "type": "child_database",
                })
            continue

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

        # Handle embed and bookmark blocks
        if block_type in ("embed", "bookmark", "link_preview"):
            url = value.get("url", "")
            caption_texts = []
            for rt in value.get("caption") or []:
                if isinstance(rt, dict):
                    txt = rt.get("plain_text") or rt.get("text", {}).get("content")
                    if txt:
                        caption_texts.append(txt)
            name = "".join(caption_texts) if caption_texts else url
            if url:
                attachments.append({
                    "id": block.get("id"),
                    "type": block_type,
                    "name": name,
                    "url": url,
                })

        # Handle code blocks
        if block_type == "code":
            language = value.get("language", "")
            rich_text = value.get("rich_text") or []
            code_parts = []
            for rt in rich_text:
                if isinstance(rt, dict):
                    txt = rt.get("plain_text", "")
                    if txt:
                        code_parts.append(txt)
            code_text = "".join(code_parts)
            if code_text:
                lines.append(f"```{language}")
                lines.append(code_text)
                lines.append("```")

        # Handle table_row blocks
        if block_type == "table_row":
            cells = value.get("cells", [])
            cell_texts = []
            for cell in cells:
                cell_parts = []
                for rt in cell:
                    if isinstance(rt, dict):
                        txt = rt.get("plain_text", "")
                        if txt:
                            cell_parts.append(txt)
                cell_texts.append("".join(cell_parts))
            if cell_texts:
                lines.append("| " + " | ".join(cell_texts) + " |")

        # Handle divider blocks
        if block_type == "divider":
            lines.append("---")

    return lines, attachments, child_databases


def _flatten_notion_block_tree(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    flat: List[Dict[str, Any]] = []
    stack: List[Dict[str, Any]] = []
    for b in blocks or []:
        if isinstance(b, dict):
            stack.append(b)
    while stack:
        block = stack.pop()
        if not isinstance(block, dict):
            continue
        flat.append(block)
        children = block.get("_children")
        if isinstance(children, list) and children:
            for child in children:
                if isinstance(child, dict):
                    stack.append(child)
    return flat


def _query_notion_database_for_api(database_id: str, db_title: Optional[str] = None) -> Dict[str, Any]:
    """Query a Notion database and return its entries formatted for the API.
    
    If the database returns 0 entries (possibly a linked view), will search
    for the original database by title.
    """
    from core.notion_export.client import NotionClient
    
    token = Config.NOTION_TOKEN
    if not token:
        return {"entries": [], "error": "NOTION_TOKEN not configured"}
    
    try:
        client = NotionClient(token)
        
        # Get database metadata
        db_meta = client.get_database(database_id)
        actual_db_id = database_id
        
        if db_meta:
            # Get database title
            title_parts = db_meta.get("title", [])
            db_title = "".join(t.get("plain_text", "") for t in title_parts) or db_title
        
        # Get schema
        schema = db_meta.get("properties", {}) if db_meta else {}
        
        # Get title column
        title_col = None
        for col_name, col_schema in schema.items():
            if col_schema.get("type") == "title":
                title_col = col_name
                break
        
        # Query entries (up to 500)
        entries = client.query_database(database_id, max_results=500)
        
        # If no entries, this might be a LINKED database view
        # Try to find the original database by title
        if not entries and db_title:
            logger.info(f"No entries for {database_id}, searching for original database '{db_title}'")
            original_db = client.find_database_by_title(db_title)
            if original_db:
                original_id = original_db.get("id")
                if original_id and original_id != database_id:
                    logger.info(f"Found original database: {original_id}")
                    actual_db_id = original_id
                    db_meta = original_db
                    schema = db_meta.get("properties", {})
                    # Update title_col
                    title_col = None
                    for col_name, col_schema in schema.items():
                        if col_schema.get("type") == "title":
                            title_col = col_name
                            break
                    entries = client.query_database(actual_db_id, max_results=500)
        
        if not db_meta:
            return {"entries": [], "error": "Could not access database"}
        
        # Order columns: title first, then other important columns, then rest
        ordered_columns = []
        other_columns = []
        for col_name, col_schema in schema.items():
            if col_schema.get("type") == "title":
                ordered_columns.insert(0, col_name)  # Title first
            elif col_name.lower() in ["name", "status", "priority", "date", "due date", "assignee"]:
                ordered_columns.append(col_name)  # Important columns early
            else:
                other_columns.append(col_name)
        ordered_columns.extend(sorted(other_columns))
        
        formatted_entries = []
        for entry in entries:
            formatted = client.format_database_entry(entry)
            props = formatted["properties"]
            
            entry_data = {
                "id": formatted["id"],
                "title": props.get(title_col, "Untitled") if title_col else "Untitled",
                "properties": props,
            }
            formatted_entries.append(entry_data)
        
        return {
            "requested_database_id": database_id,
            "database_id": actual_db_id,
            "title": "".join(t.get("plain_text", "") for t in db_meta.get("title", [])) if db_meta else db_title,
            "columns": ordered_columns,
            "entries": formatted_entries,
            "total": len(formatted_entries),
            "properties": schema,
        }
    except Exception as e:
        logger.error(f"Error querying database {database_id}: {e}")
        return {"requested_database_id": database_id, "entries": [], "error": str(e)}


def _build_database_schema_cache(
    *,
    properties: Dict[str, Any],
    db_data: Dict[str, Any],
) -> Dict[str, Any]:
    schema_data: Dict[str, Any] = {"properties": properties or {}}
    if isinstance(db_data, dict):
        if db_data.get("database_id"):
            schema_data["cached_database_id"] = db_data.get("database_id")
        if db_data.get("requested_database_id"):
            schema_data["cached_requested_database_id"] = db_data.get("requested_database_id")
        if db_data.get("title") is not None:
            schema_data["cached_title"] = db_data.get("title")
        if db_data.get("columns") is not None:
            schema_data["cached_columns"] = db_data.get("columns")
        if db_data.get("entries") is not None:
            schema_data["cached_entries"] = db_data.get("entries")
        if db_data.get("total") is not None:
            schema_data["cached_total"] = db_data.get("total")
        if db_data.get("error") is not None:
            schema_data["cached_error"] = db_data.get("error")
    schema_data["cached_at"] = datetime.utcnow().isoformat()
    return schema_data


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

                # Persist icon and cover metadata
                if p.get("icon") is not None:
                    db_page.icon = p.get("icon")
                if p.get("cover") is not None:
                    db_page.cover = p.get("cover")

                # Persist deep-fetched blocks and schema
                if p.get("blocks_data") is not None:
                    db_page.blocks_data = p.get("blocks_data")
                if p.get("schema_data") is not None:
                    db_page.schema_data = p.get("schema_data")

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


def _fetch_notion_blocks(page_id: str, headers: Dict[str, str], max_depth: int = 3) -> List[Dict[str, Any]]:
    """Recursively fetch all blocks for a Notion page with rate limiting."""
    import time
    all_blocks: List[Dict[str, Any]] = []
    
    def fetch_children(block_id: str, depth: int) -> List[Dict[str, Any]]:
        if depth > max_depth:
            return []
        blocks: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        
        while True:
            time.sleep(Config.NOTION_API_RATE_LIMIT_DELAY)
            params: Dict[str, Any] = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor
            
            try:
                resp = requests.get(
                    f"https://api.notion.com/v1/blocks/{block_id}/children",
                    headers=headers,
                    params=params,
                    timeout=30,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                results = data.get("results", []) or []
                
                for block in results:
                    block_copy = dict(block)
                    blocks.append(block_copy)
                    # Recursively fetch children for blocks that have them
                    if block.get("has_children"):
                        child_blocks = fetch_children(block.get("id"), depth + 1)
                        block_copy["_children"] = child_blocks
                
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
            except Exception as e:
                logger.warning(f"Error fetching blocks for {block_id}: {e}")
                break
        
        return blocks
    
    return fetch_children(page_id, 0)


def _fetch_notion_database_schema(database_id: str, headers: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Fetch database schema/properties."""
    import time
    time.sleep(Config.NOTION_API_RATE_LIMIT_DELAY)
    try:
        resp = requests.get(
            f"https://api.notion.com/v1/databases/{database_id}",
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 200:
            db_data = resp.json() or {}
            data_sources = db_data.get("data_sources") or []
            ds_id = None
            if isinstance(data_sources, list) and data_sources:
                first = data_sources[0]
                if isinstance(first, dict):
                    ds_id = first.get("id")

            if ds_id:
                ds_resp = requests.get(
                    f"https://api.notion.com/v1/data_sources/{ds_id}",
                    headers=headers,
                    timeout=30,
                )
                if ds_resp.status_code == 200:
                    ds_data = ds_resp.json() or {}
                    return {
                        "properties": ds_data.get("properties", {}),
                        "title": db_data.get("title", []),
                        "description": db_data.get("description", []),
                        "is_inline": db_data.get("is_inline", False),
                        "data_source_id": ds_id,
                    }

            return {
                "properties": db_data.get("properties", {}),
                "title": db_data.get("title", []),
                "description": db_data.get("description", []),
                "is_inline": db_data.get("is_inline", False),
            }

        # Also support passing a data_source_id directly (common in 2025+).
        ds_resp = requests.get(
            f"https://api.notion.com/v1/data_sources/{database_id}",
            headers=headers,
            timeout=30,
        )
        if ds_resp.status_code == 200:
            ds_data = ds_resp.json() or {}
            parent = ds_data.get("parent") or {}
            return {
                "properties": ds_data.get("properties", {}),
                "title": ds_data.get("title", []),
                "description": ds_data.get("description", []),
                "data_source_id": ds_data.get("id") or database_id,
                "database_id": parent.get("database_id"),
            }
    except Exception as e:
        logger.warning(f"Error fetching database schema for {database_id}: {e}")
    return None


def _run_notion_pipeline(
    run_id: str,
    deep_fetch_override: Optional[bool] = None,
    fetch_blocks_override: Optional[bool] = None,
) -> None:
    """Background worker to fetch Notion pages under NOTION_PARENT_PAGE_ID."""
    import time

    _update_pipeline_run(run_id, status="running", started_at=datetime.utcnow())

    token = Config.NOTION_TOKEN
    if not token:
        _update_pipeline_run(
            run_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error="NOTION_TOKEN is not configured. Please set it in your environment.",
        )
        logger.error("Notion pipeline run %s failed: NOTION_TOKEN is not configured", run_id)
        return

    workspace_id = Config.WORKSPACE_ID or "default-notion-workspace"
    workspace_name = Config.WORKSPACE_NAME or "Notion Workspace"

    pages: List[Dict[str, Any]] = []
    max_pages = Config.NOTION_PIPELINE_MAX_PAGES
    deep_fetch = (
        deep_fetch_override
        if deep_fetch_override is not None
        else Config.NOTION_PIPELINE_DEEP_FETCH
    )
    fetch_blocks = (
        fetch_blocks_override
        if fetch_blocks_override is not None
        else Config.NOTION_PIPELINE_FETCH_BLOCKS
    )

    try:
        headers = {
            "Authorization": f"Bearer {token}",
            "Notion-Version": Config.NOTION_VERSION,
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
            run_info = _get_pipeline_run(run_id)
            if run_info and run_info.get("cancel_requested"):
                _update_pipeline_run(
                    run_id,
                    status="cancelled",
                    finished_at=datetime.utcnow(),
                    stats={"page_count": len(pages)},
                )
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
                _update_pipeline_run(
                    run_id,
                    status="failed",
                    finished_at=datetime.utcnow(),
                    error=f"Notion API error {response.status_code}",
                )
                return

            data = response.json()
            results = data.get("results", []) or []

            for page in results:
                obj_type = page.get("object")
                if obj_type not in ("page", "database", "data_source"):
                    continue

                parent_obj = page.get("parent", {}) or {}
                parent_type = parent_obj.get("type")
                parent_id: Optional[str] = None
                if parent_type == "page_id":
                    parent_id = parent_obj.get("page_id")
                elif parent_type == "database_id":
                    parent_id = parent_obj.get("database_id")
                elif parent_type == "data_source_id":
                    parent_id = parent_obj.get("database_id") or parent_obj.get("data_source_id")

                normalized_obj_type = "database" if obj_type == "data_source" else obj_type
                page_data: Dict[str, Any] = {
                    "id": page.get("id"),
                    "title": _extract_notion_title(page),
                    "url": page.get("url"),
                    "last_edited_time": page.get("last_edited_time"),
                    "object_type": normalized_obj_type,
                    "parent_id": parent_id,
                    "icon": page.get("icon"),
                    "cover": page.get("cover"),
                    "raw": page,
                }

                # Deep fetch blocks and schema if enabled
                if deep_fetch:
                    page_id = page.get("id")
                    if obj_type in ("database", "data_source"):
                        # Fetch database schema (properties live on data source in 2025 API)
                        schema = _fetch_notion_database_schema(page_id, headers)
                        if schema:
                            page_data["schema_data"] = schema
                    
                    if fetch_blocks and obj_type == "page":
                        # Fetch page blocks (skip for databases as they have rows, not blocks)
                        blocks = _fetch_notion_blocks(page_id, headers, max_depth=3)
                        if blocks:
                            page_data["blocks_data"] = blocks

                pages.append(page_data)

                if len(pages) >= max_pages:
                    break

            if len(pages) >= max_pages:
                break

            if not data.get("has_more"):
                break
            start_cursor = data.get("next_cursor")
            time.sleep(Config.NOTION_API_RATE_LIMIT_DELAY)  # Rate limit between search pages

        notion_run_pages[run_id] = pages
        _persist_notion_pages(workspace_id, workspace_name, pages, full_refresh=True)

        global _notion_hierarchy_cache
        _notion_hierarchy_cache = (0.0, {})
        
        run_stats = {"page_count": len(pages)}
        _update_pipeline_run(
            run_id,
            status="completed",
            finished_at=datetime.utcnow(),
            stats=run_stats,
        )

        logger.info("Notion pipeline run %s completed with %s pages", run_id, len(pages))

        if Config.AUTO_SYNC_EMBEDDINGS_AFTER_PIPELINE:
            # Automatically sync embeddings after successful ingestion
            try:
                logger.info("Auto-syncing Notion embeddings for workspace %s...", workspace_id)
                embed_stats = sync_embeddings_after_pipeline(
                    data_source="notion",
                    source_ids=[workspace_id],
                    db_manager=db_manager
                )
                run_stats["embedding_stats"] = embed_stats
                _update_pipeline_run(run_id, stats=run_stats)
                logger.info("✓ Notion embeddings synced: %s", embed_stats)
            except Exception as embed_error:
                logger.error(f"Embedding sync failed (non-fatal): {embed_error}")
                run_stats["embedding_error"] = str(embed_error)
                _update_pipeline_run(run_id, stats=run_stats)

    except Exception as e:  # pragma: no cover - defensive logging
        logger.error(f"Notion pipeline run {run_id} failed: {e}", exc_info=True)
        _update_pipeline_run(
            run_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error=str(e),
        )


@app.post("/api/pipelines/notion/run")
async def run_notion_pipeline(mode: str = "titles"):
    """Trigger a Notion pipeline run.

    mode=titles: fast refresh that only persists titles/metadata.
    mode=deep: optional deep fetch (blocks/schema) based on env.
    """

    run_id = uuid.uuid4().hex
    
    # Create pipeline run in database (works with multiple workers)
    with db_manager.get_session() as session:
        pipeline_run = PipelineRun(
            run_id=run_id,
            pipeline_type="notion",
            status="pending",
        )
        session.add(pipeline_run)
        session.commit()

    mode_norm = (mode or "titles").strip().lower()
    if mode_norm == "deep":
        deep_fetch_override = True
        fetch_blocks_override = True
    else:
        deep_fetch_override = False
        fetch_blocks_override = False

    thread = threading.Thread(
        target=_run_notion_pipeline,
        args=(run_id, deep_fetch_override, fetch_blocks_override),
        daemon=True,
    )
    thread.start()

    return {"run_id": run_id, "status": "started"}


@app.get("/api/pipelines/notion/status/{run_id}")
async def get_notion_pipeline_status(run_id: str):
    """Get the status of a Notion pipeline run."""

    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@app.post("/api/pipelines/notion/stop/{run_id}")
async def stop_notion_pipeline(run_id: str):
    """Request cancellation of a Notion pipeline run."""

    run = _get_pipeline_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    _update_pipeline_run(
        run_id,
        cancel_requested=True,
        status="cancelling" if run.get("status") in ("pending", "running") else run.get("status"),
        finished_at=datetime.utcnow(),
    )
    return _get_pipeline_run(run_id)


@app.get("/api/pipelines/notion/pages")
async def get_notion_pipeline_pages(run_id: str):
    """Return pages for a specific Notion pipeline run."""

    run = _get_pipeline_run(run_id)
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

    global _notion_hierarchy_cache

    now = time.time()
    cached_at, cached = _notion_hierarchy_cache
    if cached and (now - cached_at) < _OPTIONS_CACHE_TTL_SECONDS:
        return cached

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

    payload = {
        "workspace_id": workspace_id,
        "workspace_name": workspace_name,
        "pages": roots,
    }

    _notion_hierarchy_cache = (now, payload)
    return payload


@app.get("/api/notion/page-content")
async def get_notion_page_content(
    page_id: str,
    include_databases: bool = True,
    refresh: bool = False,
    cache_only: bool = False,
):
    """Get content of a Notion page including any embedded databases.
    
    Args:
        page_id: The Notion page ID
        include_databases: If True, query and include content from child databases
    """
    token = Config.NOTION_TOKEN
    if not token:
        raise HTTPException(
            status_code=500,
            detail="NOTION_TOKEN is not configured. Please set it in your environment.",
        )

    global _notion_hierarchy_cache

    if cache_only and not refresh:
        with db_manager.get_session() as session:
            db_page = session.query(NotionPage).filter_by(page_id=page_id).first()

            if not db_page:
                return {
                    "page_id": page_id,
                    "content": "",
                    "attachments": [],
                    "is_database": False,
                    "child_databases": [],
                    "cached": False,
                    "message": "Not found in local DB. Refresh titles list first.",
                }

            obj_type = (db_page.object_type or "page").lower()
            if obj_type == "database":
                schema = db_page.schema_data or {}
                props = schema.get("properties") if isinstance(schema, dict) else {}
                columns = list(props.keys()) if isinstance(props, dict) else []

                cached_columns = schema.get("cached_columns") if isinstance(schema, dict) else None
                cached_entries = schema.get("cached_entries") if isinstance(schema, dict) else None
                cached_total = schema.get("cached_total") if isinstance(schema, dict) else None
                cached_error = schema.get("cached_error") if isinstance(schema, dict) else None

                if isinstance(cached_columns, list) and cached_columns:
                    columns = cached_columns
                entries = cached_entries if isinstance(cached_entries, list) else []
                total = cached_total if isinstance(cached_total, int) else len(entries)

                return {
                    "page_id": page_id,
                    "content": "",
                    "attachments": [],
                    "is_database": True,
                    "database": {
                        "database_id": page_id,
                        "title": schema.get("cached_title") if isinstance(schema, dict) and schema.get("cached_title") else (db_page.title or "Untitled"),
                        "columns": columns,
                        "entries": entries,
                        "total": total,
                        "error": cached_error
                        if cached_error
                        else ("Not refreshed. Click Refresh to fetch entries." if not entries else None),
                    },
                    "child_databases": [],
                    "cached": bool(entries) or bool(db_page.schema_data),
                }

            blocks = db_page.blocks_data or []
            if not blocks:
                return {
                    "page_id": page_id,
                    "content": "",
                    "attachments": [],
                    "is_database": False,
                    "child_databases": [],
                    "cached": False,
                    "message": "No cached content. Click Refresh to fetch page data.",
                }

            flat_blocks = _flatten_notion_block_tree(blocks) if isinstance(blocks, list) else []
            text_lines, attachments, child_databases = _summarize_notion_blocks(
                flat_blocks, include_databases=include_databases
            )

            databases_content: List[Dict[str, Any]] = []
            if include_databases and child_databases:
                for db_ref in child_databases:
                    db_id = db_ref.get("id") if isinstance(db_ref, dict) else None
                    db_title = db_ref.get("title", "Database") if isinstance(db_ref, dict) else "Database"
                    if db_id:
                        cached_db = session.query(NotionPage).filter_by(page_id=db_id).first()
                        if cached_db and cached_db.schema_data:
                            schema = cached_db.schema_data or {}
                            props = schema.get("properties") if isinstance(schema, dict) else {}
                            columns = list(props.keys()) if isinstance(props, dict) else []
                            cached_columns = schema.get("cached_columns") if isinstance(schema, dict) else None
                            cached_entries = schema.get("cached_entries") if isinstance(schema, dict) else None
                            cached_total = schema.get("cached_total") if isinstance(schema, dict) else None
                            cached_error = schema.get("cached_error") if isinstance(schema, dict) else None
                            if isinstance(cached_columns, list) and cached_columns:
                                columns = cached_columns
                            entries = cached_entries if isinstance(cached_entries, list) else []
                            total = cached_total if isinstance(cached_total, int) else len(entries)
                            databases_content.append(
                                {
                                    "database_id": db_id,
                                    "title": schema.get("cached_title")
                                    if isinstance(schema, dict) and schema.get("cached_title")
                                    else (cached_db.title or db_title),
                                    "columns": columns,
                                    "entries": entries,
                                    "total": total,
                                    "error": cached_error
                                    if cached_error
                                    else ("Not refreshed. Click Refresh to fetch entries." if not entries else None),
                                }
                            )
                        else:
                            databases_content.append(
                                {
                                    "database_id": db_id,
                                    "title": db_title,
                                    "columns": [],
                                    "entries": [],
                                    "total": 0,
                                    "error": "Not refreshed. Click Refresh to fetch entries.",
                                }
                            )

            return {
                "page_id": page_id,
                "content": "\n".join(text_lines),
                "attachments": attachments,
                "is_database": False,
                "child_databases": databases_content,
                "cached": True,
            }

    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": Config.NOTION_VERSION,
        "Content-Type": "application/json",
    }

    all_blocks: List[Dict[str, Any]] = []
    next_cursor: Optional[str] = None

    try:
        if not refresh:
            return {
                "page_id": page_id,
                "content": "",
                "attachments": [],
                "is_database": False,
                "child_databases": [],
                "cached": False,
                "message": "Cache-only mode required unless refresh=true.",
            }

        page_meta_resp = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers,
            timeout=30,
        )
        if page_meta_resp.status_code == 200:
            page_meta = page_meta_resp.json()

            with db_manager.get_session() as session:
                existing = session.query(NotionPage).filter_by(page_id=page_id).first()
                workspace_id = (
                    existing.workspace_id
                    if existing and existing.workspace_id
                    else (Config.WORKSPACE_ID or "default-notion-workspace")
                )
                ws = session.query(NotionWorkspace).filter_by(workspace_id=workspace_id).first()
                workspace_name = ws.name if ws and ws.name else (Config.WORKSPACE_NAME or "Notion Workspace")

            blocks_tree = _fetch_notion_blocks(page_id, headers, max_depth=3)
            flat_blocks = _flatten_notion_block_tree(blocks_tree)
            text_lines, attachments, child_databases = _summarize_notion_blocks(
                flat_blocks, include_databases=include_databases
            )
            content = "\n".join(text_lines)

            databases_content: List[Dict[str, Any]] = []
            if include_databases and child_databases:
                for db_ref in child_databases:
                    db_id = db_ref.get("id")
                    db_title = db_ref.get("title", "Database")
                    if db_id:
                        db_data = _query_notion_database_for_api(db_id, db_title=db_title)
                        if not db_data.get("title"):
                            db_data["title"] = db_title
                        databases_content.append(db_data)

                        # Persist cached database rows/schema so future cache_only requests
                        # (including subpage expansions) do not require another refresh.
                        db_properties = db_data.get("properties") if isinstance(db_data, dict) else {}
                        schema_cache = _build_database_schema_cache(
                            properties=db_properties if isinstance(db_properties, dict) else {},
                            db_data=db_data,
                        )

                        db_page_payload: Dict[str, Any] = {
                            "id": db_id,
                            "title": db_data.get("title") or db_title,
                            "url": None,
                            "last_edited_time": None,
                            "object_type": "database",
                            "parent_id": page_id,
                            "schema_data": schema_cache,
                        }
                        _persist_notion_pages(workspace_id, workspace_name, [db_page_payload], full_refresh=False)

                        resolved_id = db_data.get("database_id") if isinstance(db_data, dict) else None
                        if resolved_id and resolved_id != db_id:
                            resolved_payload = dict(db_page_payload)
                            resolved_payload["id"] = resolved_id
                            _persist_notion_pages(
                                workspace_id,
                                workspace_name,
                                [resolved_payload],
                                full_refresh=False,
                            )

            parent_obj = page_meta.get("parent", {}) or {}
            parent_type = parent_obj.get("type")
            parent_id: Optional[str] = None
            if parent_type == "page_id":
                parent_id = parent_obj.get("page_id")
            elif parent_type == "database_id":
                parent_id = parent_obj.get("database_id")

            page_data: Dict[str, Any] = {
                "id": page_id,
                "title": _extract_notion_title(page_meta),
                "url": page_meta.get("url"),
                "last_edited_time": page_meta.get("last_edited_time"),
                "object_type": "page",
                "parent_id": parent_id,
                "icon": page_meta.get("icon"),
                "cover": page_meta.get("cover"),
                "raw": page_meta,
                "blocks_data": blocks_tree,
            }
            _persist_notion_pages(workspace_id, workspace_name, [page_data], full_refresh=False)
            _notion_hierarchy_cache = (0.0, {})

            return {
                "page_id": page_id,
                "content": content,
                "attachments": attachments,
                "is_database": False,
                "child_databases": databases_content,
                "refreshed": True,
            }

        db_meta_resp = requests.get(
            f"https://api.notion.com/v1/databases/{page_id}",
            headers=headers,
            timeout=30,
        )
        if db_meta_resp.status_code == 200:
            db_meta = db_meta_resp.json() or {}
            db_data = _query_notion_database_for_api(page_id)

            with db_manager.get_session() as session:
                existing = session.query(NotionPage).filter_by(page_id=page_id).first()
                workspace_id = (
                    existing.workspace_id
                    if existing and existing.workspace_id
                    else (Config.WORKSPACE_ID or "default-notion-workspace")
                )
                ws = session.query(NotionWorkspace).filter_by(workspace_id=workspace_id).first()
                workspace_name = ws.name if ws and ws.name else (Config.WORKSPACE_NAME or "Notion Workspace")

            parent_obj = db_meta.get("parent", {}) or {}
            parent_type = parent_obj.get("type")
            parent_id: Optional[str] = None
            if parent_type == "page_id":
                parent_id = parent_obj.get("page_id")

            db_properties = db_data.get("properties") if isinstance(db_data, dict) else {}
            schema_data = _build_database_schema_cache(
                properties=db_properties if isinstance(db_properties, dict) else {},
                db_data=db_data,
            )
            schema_data["title"] = db_meta.get("title", [])
            schema_data["description"] = db_meta.get("description", [])
            schema_data["is_inline"] = db_meta.get("is_inline", False)

            page_data = {
                "id": page_id,
                "title": "".join(t.get("plain_text", "") for t in db_meta.get("title", [])) or "Untitled",
                "url": db_meta.get("url"),
                "last_edited_time": db_meta.get("last_edited_time"),
                "object_type": "database",
                "parent_id": parent_id,
                "icon": db_meta.get("icon"),
                "cover": db_meta.get("cover"),
                "raw": db_meta,
                "schema_data": schema_data,
            }
            _persist_notion_pages(workspace_id, workspace_name, [page_data], full_refresh=False)
            _notion_hierarchy_cache = (0.0, {})

            return {
                "page_id": page_id,
                "content": "",
                "attachments": [],
                "is_database": True,
                "database": db_data,
                "child_databases": [],
                "refreshed": True,
            }

        ds_meta_resp = requests.get(
            f"https://api.notion.com/v1/data_sources/{page_id}",
            headers=headers,
            timeout=30,
        )
        if ds_meta_resp.status_code == 200:
            ds_meta = ds_meta_resp.json() or {}
            db_data = _query_notion_database_for_api(page_id)

            with db_manager.get_session() as session:
                existing = session.query(NotionPage).filter_by(page_id=page_id).first()
                workspace_id = (
                    existing.workspace_id
                    if existing and existing.workspace_id
                    else (Config.WORKSPACE_ID or "default-notion-workspace")
                )
                ws = session.query(NotionWorkspace).filter_by(workspace_id=workspace_id).first()
                workspace_name = ws.name if ws and ws.name else (Config.WORKSPACE_NAME or "Notion Workspace")

            db_properties = ds_meta.get("properties", {}) if isinstance(ds_meta, dict) else {}
            schema_data = _build_database_schema_cache(
                properties=db_properties if isinstance(db_properties, dict) else {},
                db_data=db_data,
            )
            schema_data["title"] = ds_meta.get("title", [])
            schema_data["description"] = ds_meta.get("description", [])

            parent_obj = ds_meta.get("parent", {}) or {}
            parent_id = parent_obj.get("database_id")

            page_data = {
                "id": page_id,
                "title": "".join(t.get("plain_text", "") for t in ds_meta.get("title", [])) or "Untitled",
                "url": ds_meta.get("url"),
                "last_edited_time": ds_meta.get("last_edited_time"),
                "object_type": "database",
                "parent_id": parent_id,
                "icon": ds_meta.get("icon"),
                "cover": ds_meta.get("cover"),
                "raw": ds_meta,
                "schema_data": schema_data,
            }
            _persist_notion_pages(workspace_id, workspace_name, [page_data], full_refresh=False)
            _notion_hierarchy_cache = (0.0, {})

            return {
                "page_id": page_id,
                "content": "",
                "attachments": [],
                "is_database": True,
                "database": db_data,
                "child_databases": [],
                "refreshed": True,
            }

        raise HTTPException(status_code=404, detail="Notion page/database not found")

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

    try:
        if ai_brain and hasattr(ai_brain, "close"):
            await ai_brain.close()
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
