"""Reaction manager for adding/removing reactions."""
from typing import Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import Config
from utils.logger import get_logger
from utils.rate_limiter import get_rate_limiter
from utils.backoff import sync_retry_with_backoff

logger = get_logger(__name__)


class ReactionManager:
    """Manage reactions on Slack messages."""
    
    def __init__(self, client: Optional[WebClient] = None):
        """Initialize reaction manager."""
        self.client = client or WebClient(token=Config.SLACK_BOT_TOKEN)
        self.rate_limiter = get_rate_limiter()
    
    def add_reaction(
        self,
        channel: str,
        timestamp: str,
        emoji: str
    ):
        """Add a reaction to a message."""
        # Remove colons if present
        emoji = emoji.strip(':')
        
        logger.info(f"Adding reaction :{emoji}: to {channel}/{timestamp}")
        
        self.rate_limiter.wait_if_needed("reactions.add")
        
        try:
            response = sync_retry_with_backoff(
                lambda: self.client.reactions_add(
                    channel=channel,
                    timestamp=timestamp,
                    name=emoji
                )
            )
            
            if response.get("ok"):
                logger.info(f"✓ Reaction added: :{emoji}:")
                return response.data
            else:
                logger.error(f"Failed to add reaction: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error adding reaction: {e}")
            raise
    
    def remove_reaction(
        self,
        channel: str,
        timestamp: str,
        emoji: str
    ):
        """Remove a reaction from a message."""
        # Remove colons if present
        emoji = emoji.strip(':')
        
        logger.info(f"Removing reaction :{emoji}: from {channel}/{timestamp}")
        
        self.rate_limiter.wait_if_needed("reactions.remove")
        
        try:
            response = sync_retry_with_backoff(
                lambda: self.client.reactions_remove(
                    channel=channel,
                    timestamp=timestamp,
                    name=emoji
                )
            )
            
            if response.get("ok"):
                logger.info(f"✓ Reaction removed: :{emoji}:")
                return response.data
            else:
                logger.error(f"Failed to remove reaction: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error removing reaction: {e}")
            raise
    
    def get_reactions(
        self,
        channel: str,
        timestamp: str
    ):
        """Get all reactions for a message."""
        logger.info(f"Getting reactions for {channel}/{timestamp}")
        
        self.rate_limiter.wait_if_needed("reactions.get")
        
        try:
            response = sync_retry_with_backoff(
                lambda: self.client.reactions_get(
                    channel=channel,
                    timestamp=timestamp
                )
            )
            
            if response.get("ok"):
                message = response.get("message", {})
                reactions = message.get("reactions", [])
                logger.info(f"Found {len(reactions)} reactions")
                return reactions
            else:
                logger.error(f"Failed to get reactions: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error getting reactions: {e}")
            raise
