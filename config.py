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

# Load environment variables from .env file
load_dotenv()

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
    
    # Database
    # PostgreSQL for production, SQLite for dev
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost/workforce_agent")
    
    # Data directories
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / os.getenv("DATA_DIR", "data")
    FILES_DIR = BASE_DIR / os.getenv("FILES_DIR", "data/files")
    EXPORT_DIR = BASE_DIR / os.getenv("EXPORT_DIR", "data/raw_exports")
    LOGS_DIR = BASE_DIR / "logs"
    
    # Rate limiting (requests per minute)
    TIER_1_RATE_LIMIT = 1
    TIER_2_RATE_LIMIT = 20
    TIER_3_RATE_LIMIT = 50
    TIER_4_RATE_LIMIT = int(os.getenv("TIER_4_RATE_LIMIT", "100"))
    DEFAULT_RATE_LIMIT = int(os.getenv("DEFAULT_RATE_LIMIT", "50"))
    SPECIAL_RATE_LIMIT = 1  # For conversations.history on non-Marketplace apps
    
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
    LOG_FILE = os.getenv("LOG_FILE", "logs/slack_agent.log")
    
    # Workspace
    WORKSPACE_NAME = os.getenv("WORKSPACE_NAME", "")
    WORKSPACE_ID = os.getenv("WORKSPACE_ID", "")
    
    # Performance
    BATCH_SIZE = 100
    WORKER_THREADS = 4
    
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
