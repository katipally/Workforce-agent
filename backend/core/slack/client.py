"""Unified Slack API client wrapper."""

import os
from typing import Dict, Any, List, Optional
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from utils.logger import get_logger

logger = get_logger(__name__)


class SlackClient:
    """Unified Slack API client with all Slack functionality."""
    
    def __init__(self, token: str = None):
        """Initialize Slack client.
        
        Args:
            token: Slack bot token. If not provided, uses SLACK_BOT_TOKEN from env.
        """
        self.token = token or os.getenv('SLACK_BOT_TOKEN')
        
        if not self.token:
            raise ValueError("Slack token not provided. Set SLACK_BOT_TOKEN in .env or pass token parameter.")
        
        self.client = WebClient(token=self.token)
        self._bot_info = None
        self._team_info = None
        
        logger.info("Slack client initialized")
    
    def test_connection(self) -> bool:
        """Test Slack connection and authentication.
        
        Returns:
            True if connected successfully
        """
        try:
            response = self.client.auth_test()
            self._bot_info = response.data
            logger.info(f"Connected to Slack as {response['user']} in team {response['team']}")
            return True
        except SlackApiError as e:
            logger.error(f"Slack connection failed: {e}")
            return False
    
    @property
    def bot_id(self) -> Optional[str]:
        """Get bot user ID."""
        if not self._bot_info:
            self.test_connection()
        return self._bot_info.get('user_id') if self._bot_info else None
    
    @property
    def team_id(self) -> Optional[str]:
        """Get team/workspace ID."""
        if not self._bot_info:
            self.test_connection()
        return self._bot_info.get('team_id') if self._bot_info else None
    
    @property
    def team_name(self) -> Optional[str]:
        """Get team/workspace name."""
        if not self._bot_info:
            self.test_connection()
        return self._bot_info.get('team') if self._bot_info else None
    
    # Core API methods - direct pass-through to WebClient
    
    def conversations_list(self, **kwargs) -> Dict[str, Any]:
        """List conversations. See Slack SDK docs for parameters."""
        return self.client.conversations_list(**kwargs)
    
    def conversations_history(self, **kwargs) -> Dict[str, Any]:
        """Get conversation history. See Slack SDK docs for parameters."""
        return self.client.conversations_history(**kwargs)
    
    def conversations_replies(self, **kwargs) -> Dict[str, Any]:
        """Get thread messages (replies) for a conversation. See Slack SDK docs."""
        return self.client.conversations_replies(**kwargs)
    
    def conversations_members(self, **kwargs) -> Dict[str, Any]:
        """Get conversation members. See Slack SDK docs for parameters."""
        return self.client.conversations_members(**kwargs)
    
    def users_list(self, **kwargs) -> Dict[str, Any]:
        """List users. See Slack SDK docs for parameters."""
        return self.client.users_list(**kwargs)
    
    def users_info(self, **kwargs) -> Dict[str, Any]:
        """Get user info. See Slack SDK docs for parameters."""
        return self.client.users_info(**kwargs)
    
    def chat_postMessage(self, **kwargs) -> Dict[str, Any]:
        """Post a message. See Slack SDK docs for parameters."""
        return self.client.chat_postMessage(**kwargs)
    
    def chat_update(self, **kwargs) -> Dict[str, Any]:
        """Update a message. See Slack SDK docs for parameters."""
        return self.client.chat_update(**kwargs)
    
    def chat_delete(self, **kwargs) -> Dict[str, Any]:
        """Delete a message. See Slack SDK docs for parameters."""
        return self.client.chat_delete(**kwargs)
    
    def files_upload(self, **kwargs) -> Dict[str, Any]:
        """Upload a file. See Slack SDK docs for parameters."""
        return self.client.files_upload(**kwargs)
    
    def files_delete(self, **kwargs) -> Dict[str, Any]:
        """Delete a file. See Slack SDK docs for parameters."""
        return self.client.files_delete(**kwargs)
    
    def reactions_add(self, **kwargs) -> Dict[str, Any]:
        """Add a reaction. See Slack SDK docs for parameters."""
        return self.client.reactions_add(**kwargs)
    
    def reactions_remove(self, **kwargs) -> Dict[str, Any]:
        """Remove a reaction. See Slack SDK docs for parameters."""
        return self.client.reactions_remove(**kwargs)
    
    def reactions_get(self, **kwargs) -> Dict[str, Any]:
        """Get reactions. See Slack SDK docs for parameters."""
        return self.client.reactions_get(**kwargs)
