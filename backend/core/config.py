"""Configuration management for Workforce Agent.

Manages all application settings including:
- API credentials (Slack, Gmail, Notion)
- Database connection (PostgreSQL with pgvector)
- Rate limiting and performance settings
- File paths and logging configuration
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file in project root
project_root = Path(__file__).parent.parent.parent
env_path = project_root / '.env'
load_dotenv(dotenv_path=env_path)

class Config:
    """Application configuration loaded from environment variables and defaults."""
    
    # Slack API Tokens
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
    SLACK_APP_TOKEN = os.getenv("SLACK_APP_TOKEN", "")
    SLACK_USER_TOKEN = os.getenv("SLACK_USER_TOKEN", "")
    
    # Slack App Credentials
    SLACK_APP_ID = os.getenv("SLACK_APP_ID", "")
    SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID", "")
    SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET", "")
    SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
    SLACK_VERIFICATION_TOKEN = os.getenv("SLACK_VERIFICATION_TOKEN", "")

    SLACK_CONVERSATIONS_HISTORY_LIMIT = int(os.getenv("SLACK_CONVERSATIONS_HISTORY_LIMIT", "15"))
    
    # Database
    # Connection string must be provided via environment (see .env.example)
    DATABASE_URL = os.getenv("DATABASE_URL", "")
    
    # Data directories (relative to project root)
    BASE_DIR = Path(__file__).parent  # backend/core
    PROJECT_ROOT = BASE_DIR.parent.parent  # project root
    DATA_DIR = PROJECT_ROOT / os.getenv("DATA_DIR", "data")
    FILES_DIR = PROJECT_ROOT / os.getenv("FILES_DIR", "data/files")
    EXPORT_DIR = PROJECT_ROOT / os.getenv("EXPORT_DIR", "data/raw_exports")
    # LOGS_DIR uses backend directory for consistency (logs written here on both local and EC2)
    LOGS_DIR = BASE_DIR.parent / "logs"
    PROJECT_REGISTRY_FILE = PROJECT_ROOT / os.getenv("PROJECT_REGISTRY_FILE", "data/project_registry.json")
    
    # Notion credentials
    NOTION_TOKEN = os.getenv("NOTION_TOKEN", "")
    NOTION_PARENT_PAGE_ID = os.getenv("NOTION_PARENT_PAGE_ID", "")

    # Google OAuth (app-level)
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_OAUTH_REDIRECT_BASE = os.getenv("GOOGLE_OAUTH_REDIRECT_BASE", "")
    # Base URL of the frontend application (must be set explicitly in .env)
    FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", "")
    SESSION_SECRET = os.getenv("SESSION_SECRET", "")
    
    # Cookie domain for cross-subdomain sharing in production
    # Set to ".yourdomain.com" (with leading dot) to share cookies across subdomains
    # e.g., ".dinoagent.com" allows cookies between app.dinoagent.com and api.dinoagent.com
    COOKIE_DOMAIN = os.getenv("COOKIE_DOMAIN", "")

    # Safety & permissions configuration
    SLACK_MODE = os.getenv("SLACK_MODE", "standard").lower()
    SLACK_READONLY_CHANNELS = os.getenv("SLACK_READONLY_CHANNELS", "")
    SLACK_BLOCKED_CHANNELS = os.getenv("SLACK_BLOCKED_CHANNELS", "")
    NOTION_MODE = os.getenv("NOTION_MODE", "standard").lower()

    # Gmail safety & scope
    GMAIL_SEND_MODE = os.getenv("GMAIL_SEND_MODE", "confirm").lower()
    GMAIL_ALLOWED_SEND_DOMAINS = os.getenv("GMAIL_ALLOWED_SEND_DOMAINS", "")
    GMAIL_ALLOWED_READ_DOMAINS = os.getenv("GMAIL_ALLOWED_READ_DOMAINS", "")
    GMAIL_DEFAULT_LABEL = os.getenv("GMAIL_DEFAULT_LABEL", "")
    
    # OpenAI API (for AI agent)
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    
    # AI Agent Configuration
    EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    RERANKER_MODEL = os.getenv("RERANKER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
    # LLM Model - default to gpt-5-nano (Nov 2025)
    # gpt-5-nano: Latest lightweight reasoning model, optimized for speed & cost with tool calling + streaming
    # Other options (if enabled for your account): gpt-5-mini, gpt-5
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-5-nano")
    EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))
    USE_GPU = os.getenv("USE_GPU", "false").lower() == "true"
    
    # API Server
    API_PORT = int(os.getenv("API_PORT", "8000"))
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    
    # Rate limiting (requests per minute)
    TIER_1_RATE_LIMIT = int(os.getenv("TIER_1_RATE_LIMIT", "1"))
    TIER_2_RATE_LIMIT = int(os.getenv("TIER_2_RATE_LIMIT", "20"))
    TIER_3_RATE_LIMIT = int(os.getenv("TIER_3_RATE_LIMIT", "50"))
    TIER_4_RATE_LIMIT = int(os.getenv("TIER_4_RATE_LIMIT", "100"))
    DEFAULT_RATE_LIMIT = int(os.getenv("DEFAULT_RATE_LIMIT", "50"))
    SPECIAL_RATE_LIMIT = int(os.getenv("SPECIAL_RATE_LIMIT", "1"))  # For conversations.history on non-Marketplace apps
    
    # Burst limiting
    MAX_BURST_REQUESTS = 5
    BURST_COOLDOWN_SECONDS = 1
    
    # Pagination
    DEFAULT_PAGE_SIZE = 200  # Maximum for most methods
    MAX_RETRIES = 5
    
    # Socket Mode
    SOCKET_MODE_ENABLED = os.getenv("SOCKET_MODE_ENABLED", "true").lower() == "true"
    MAX_RECONNECT_ATTEMPTS = int(os.getenv("MAX_RECONNECT_ATTEMPTS", "10"))
    SOCKET_PING_INTERVAL = 30
    
    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", str(LOGS_DIR / "slack_agent.log"))
    
    # Workspace
    WORKSPACE_NAME = os.getenv("WORKSPACE_NAME", "")
    WORKSPACE_ID = os.getenv("WORKSPACE_ID", "")
    
    # Performance
    BATCH_SIZE = 100
    WORKER_THREADS = 4

    AUTO_SYNC_EMBEDDINGS_AFTER_PIPELINE = (
        os.getenv("AUTO_SYNC_EMBEDDINGS_AFTER_PIPELINE", "false").lower() == "true"
    )
    
    @classmethod
    def create_directories(cls):
        """Create necessary directories if they don't exist."""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        cls.FILES_DIR.mkdir(parents=True, exist_ok=True)
        cls.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def validate(cls):
        """Validate required configuration."""
        errors = []
        
        if not cls.SLACK_BOT_TOKEN:
            errors.append("SLACK_BOT_TOKEN is required")
        
        if cls.SOCKET_MODE_ENABLED and not cls.SLACK_APP_TOKEN:
            errors.append("SLACK_APP_TOKEN is required when Socket Mode is enabled")
        
        if errors:
            raise ValueError(f"Configuration errors: {', '.join(errors)}")
        
        return True


# Rate limit tiers for different API methods
RATE_LIMIT_TIERS = {
    # Tier 4 - Highest rate limits (100+ req/min)
    "api.test": Config.TIER_4_RATE_LIMIT,
    "apps.connections.open": Config.TIER_4_RATE_LIMIT,
    "auth.test": Config.TIER_4_RATE_LIMIT,
    "bots.info": Config.TIER_4_RATE_LIMIT,
    "emoji.list": Config.TIER_4_RATE_LIMIT,
    "reactions.get": Config.TIER_4_RATE_LIMIT,
    "team.info": Config.TIER_4_RATE_LIMIT,
    "users.info": Config.TIER_4_RATE_LIMIT,
    "users.lookupByEmail": Config.TIER_4_RATE_LIMIT,
    
    # Tier 3 - Good rate limits (50+ req/min)
    "channels.info": Config.TIER_3_RATE_LIMIT,
    "chat.delete": Config.TIER_3_RATE_LIMIT,
    "chat.postMessage": Config.TIER_3_RATE_LIMIT,
    "chat.update": Config.TIER_3_RATE_LIMIT,
    "conversations.info": Config.TIER_3_RATE_LIMIT,
    "conversations.members": Config.TIER_3_RATE_LIMIT,
    "files.info": Config.TIER_3_RATE_LIMIT,
    "reactions.add": Config.TIER_3_RATE_LIMIT,
    "reactions.remove": Config.TIER_3_RATE_LIMIT,
    "users.conversations": Config.TIER_3_RATE_LIMIT,
    
    # Tier 2 - Moderate rate limits (20+ req/min)
    "conversations.list": Config.TIER_2_RATE_LIMIT,
    "files.list": Config.TIER_2_RATE_LIMIT,
    "reactions.list": Config.TIER_2_RATE_LIMIT,
    "users.list": Config.TIER_2_RATE_LIMIT,
    
    # Special - conversations.history has special limits
    # 1 req/min for non-Marketplace apps, Tier 3 for Marketplace
    "conversations.history": Config.SPECIAL_RATE_LIMIT,
    "conversations.replies": Config.SPECIAL_RATE_LIMIT,
    
    # Default for unknown methods
    "default": Config.DEFAULT_RATE_LIMIT,
}


def get_rate_limit_for_method(method_name: str) -> int:
    """Get rate limit for a specific API method."""
    return RATE_LIMIT_TIERS.get(method_name, RATE_LIMIT_TIERS["default"])
