"""Test script to verify the complete setup.

This script tests:
1. Configuration loading
2. Database connection
3. API integrations (Slack, Gmail, Notion)
4. Model availability
"""

import sys
import os
from pathlib import Path

# Add backend/core directory to path (for config, database, utils)
ROOT = Path(__file__).resolve().parents[2]
BACKEND_CORE = ROOT / "backend" / "core"
if str(BACKEND_CORE) not in sys.path:
    sys.path.insert(0, str(BACKEND_CORE))

from config import Config
from database.db_manager import DatabaseManager
from utils.logger import get_logger
import torch

# Import API clients
try:
    from slack.client import SlackClient
except ImportError:
    SlackClient = None

try:
    from gmail.client import GmailClient
except ImportError:
    GmailClient = None

try:
    from notion_export.client import NotionClient
except ImportError:
    NotionClient = None

logger = get_logger(__name__)


def test_config():
    """Test configuration loading."""
    logger.info("=" * 60)
    logger.info("Testing Configuration")
    logger.info("=" * 60)
    
    tests = {
        "OPENAI_API_KEY": bool(Config.OPENAI_API_KEY),
        "SLACK_BOT_TOKEN": bool(Config.SLACK_BOT_TOKEN),
        "SLACK_APP_TOKEN": bool(Config.SLACK_APP_TOKEN),
        "NOTION_TOKEN": bool(Config.NOTION_TOKEN),
        "DATABASE_URL": bool(Config.DATABASE_URL),
        "EMBEDDING_MODEL": Config.EMBEDDING_MODEL,
        "RERANKER_MODEL": Config.RERANKER_MODEL,
        "USE_GPU": Config.USE_GPU,
        "EMBEDDING_BATCH_SIZE": Config.EMBEDDING_BATCH_SIZE,
    }
    
    for key, value in tests.items():
        status = "✓" if value else "✗"
        logger.info(f"{status} {key}: {value}")
    
    logger.info("")
    return all([Config.OPENAI_API_KEY, Config.DATABASE_URL])


def test_database():
    """Test database connection."""
    logger.info("=" * 60)
    logger.info("Testing Database Connection")
    logger.info("=" * 60)
    
    try:
        db = DatabaseManager()
        stats = db.get_statistics()
        
        logger.info("✓ Database connected successfully!")
        logger.info(f"  Users: {stats.get('users', 0)}")
        logger.info(f"  Channels: {stats.get('channels', 0)}")
        logger.info(f"  Messages: {stats.get('messages', 0)}")
        logger.info(f"  Files: {stats.get('files', 0)}")
        logger.info(f"  Reactions: {stats.get('reactions', 0)}")
        
        # Check Gmail stats if available
        try:
            gmail_stats = db.get_gmail_statistics()
            logger.info(f"  Gmail Messages: {gmail_stats.get('messages', 0)}")
        except:
            logger.info(f"  Gmail Messages: Not yet set up")
        
        logger.info("")
        return True
    
    except Exception as e:
        logger.error(f"✗ Database connection failed: {e}")
        logger.info("")
        return False


def test_slack():
    """Test Slack API connection."""
    logger.info("=" * 60)
    logger.info("Testing Slack API")
    logger.info("=" * 60)
    
    try:
        if SlackClient is None:
            logger.warning("⚠ SlackClient not available - check imports")
            logger.info("")
            return False
        
        if not Config.SLACK_BOT_TOKEN:
            logger.warning("⚠ Slack bot token not configured")
            logger.info("")
            return False
        
        client = SlackClient()
        auth = client.test_auth()
        
        if auth:
            logger.info(f"✓ Slack API connected!")
            logger.info(f"  Team: {auth.get('team', 'Unknown')}")
            logger.info(f"  User: {auth.get('user', 'Unknown')}")
            logger.info(f"  User ID: {auth.get('user_id', 'Unknown')}")
            logger.info("")
            return True
        else:
            logger.error("✗ Slack auth test failed")
            logger.info("")
            return False
    
    except Exception as e:
        logger.error(f"✗ Slack connection failed: {e}")
        logger.info("")
        return False


def test_gmail():
    """Test Gmail API connection (deprecated file-based flow).

    Gmail now uses OAuth-based per-user tokens via the web app.
    This legacy setup check is kept for backwards compatibility but
    no longer verifies a credentials.json file.
    """
    logger.info("=" * 60)
    logger.info("Testing Gmail API (OAuth-based)")
    logger.info("=" * 60)
    logger.info("Gmail file-based credentials are no longer used.")
    logger.info("To verify Gmail, sign in via the web UI and run a Gmail pipeline.")
    logger.info("")
    return True


def test_notion():
    """Test Notion API connection."""
    logger.info("=" * 60)
    logger.info("Testing Notion API")
    logger.info("=" * 60)
    
    try:
        if NotionClient is None:
            logger.warning("⚠ NotionClient not available - check imports")
            logger.info("")
            return False
        
        if not Config.NOTION_TOKEN:
            logger.warning("⚠ Notion token not configured")
            logger.info("")
            return False
        
        client = NotionClient()
        connected = client.test_connection()
        
        if connected:
            logger.info(f"✓ Notion API connected!")
            logger.info("")
            return True
        else:
            logger.error("✗ Notion connection test failed")
            logger.info("")
            return False
    
    except Exception as e:
        logger.error(f"✗ Notion connection failed: {e}")
        logger.info("")
        return False


def test_gpu():
    """Test GPU availability."""
    logger.info("=" * 60)
    logger.info("Testing GPU Availability")
    logger.info("=" * 60)
    
    cuda_available = torch.cuda.is_available()
    
    if cuda_available:
        logger.info("✓ CUDA is available!")
        logger.info(f"  GPU Device: {torch.cuda.get_device_name(0)}")
        logger.info(f"  GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.2f} GB")
        logger.info(f"  Config USE_GPU: {Config.USE_GPU}")
    else:
        logger.warning("⚠ CUDA not available - will use CPU mode")
        logger.info(f"  Config USE_GPU: {Config.USE_GPU}")
    
    logger.info("")
    return True


def main():
    """Run all tests."""
    logger.info("\n")
    logger.info("=" * 60)
    logger.info("WORKFORCE AI AGENT - SETUP VERIFICATION")
    logger.info("=" * 60)
    logger.info("\n")
    
    results = {
        "Config": test_config(),
        "Database": test_database(),
        "Slack": test_slack(),
        "Gmail": test_gmail(),
        "Notion": test_notion(),
        "GPU": test_gpu(),
    }
    
    # Summary
    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    
    for test, passed in results.items():
        status = "✓ PASS" if passed else "✗ FAIL"
        logger.info(f"{status}: {test}")
    
    logger.info("")
    
    passed = sum(results.values())
    total = len(results)
    
    logger.info(f"Tests Passed: {passed}/{total}")
    
    if passed == total:
        logger.info("\n✓ All tests passed! Your setup is complete.")
        logger.info("\nNext steps:")
        logger.info("1. Generate embeddings: python backend/scripts/generate_embeddings.py")
        logger.info("2. Start backend: uvicorn backend.api.main:app --reload")
        logger.info("3. Start frontend: cd frontend && npm run dev")
    else:
        logger.warning("\n⚠ Some tests failed. Please check the errors above.")
        
        if not results["Config"]:
            logger.info("\nMissing configuration. Please update your .env file.")
        
        if not results["Database"]:
            logger.info("\nDatabase connection failed. Please check:")
            logger.info("  - PostgreSQL is running")
            logger.info("  - DATABASE_URL is correct")
            logger.info("  - pgvector extension is installed")
    
    logger.info("")


if __name__ == "__main__":
    main()
