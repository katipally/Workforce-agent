"""Message sender for posting to Slack."""
from typing import Optional, List, Dict, Any
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import Config
from utils.logger import get_logger
from utils.rate_limiter import get_rate_limiter
from utils.backoff import sync_retry_with_backoff

logger = get_logger(__name__)


class MessageSender:
    """Send messages to Slack."""
    
    def __init__(self, client: Optional[WebClient] = None):
        """Initialize message sender."""
        self.client = client or WebClient(token=Config.SLACK_BOT_TOKEN)
        self.rate_limiter = get_rate_limiter()
    
    def send_message(
        self,
        channel: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
        thread_ts: Optional[str] = None,
        attachments: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send a message to a channel."""
        logger.info(f"Sending message to {channel}")
        
        # Rate limiting
        self.rate_limiter.wait_if_needed("chat.postMessage")
        
        try:
            params = {
                "channel": channel,
                "text": text,
                **kwargs
            }
            
            if blocks:
                params["blocks"] = blocks
            if thread_ts:
                params["thread_ts"] = thread_ts
            if attachments:
                params["attachments"] = attachments
            
            response = sync_retry_with_backoff(
                lambda: self.client.chat_postMessage(**params)
            )
            
            if response.get("ok"):
                logger.info(f"✓ Message sent to {channel}")
                return response.data
            else:
                logger.error(f"Failed to send message: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error sending message: {e}")
            raise
    
    def send_ephemeral_message(
        self,
        channel: str,
        user: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Send an ephemeral message (only visible to one user)."""
        logger.info(f"Sending ephemeral message to {user} in {channel}")
        
        self.rate_limiter.wait_if_needed("chat.postEphemeral")
        
        try:
            params = {
                "channel": channel,
                "user": user,
                "text": text,
                **kwargs
            }
            
            if blocks:
                params["blocks"] = blocks
            
            response = sync_retry_with_backoff(
                lambda: self.client.chat_postEphemeral(**params)
            )
            
            if response.get("ok"):
                logger.info(f"✓ Ephemeral message sent")
                return response.data
            else:
                logger.error(f"Failed to send ephemeral message: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error sending ephemeral message: {e}")
            raise
    
    def update_message(
        self,
        channel: str,
        ts: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Update an existing message."""
        logger.info(f"Updating message {ts} in {channel}")
        
        self.rate_limiter.wait_if_needed("chat.update")
        
        try:
            params = {
                "channel": channel,
                "ts": ts,
                "text": text,
                **kwargs
            }
            
            if blocks:
                params["blocks"] = blocks
            
            response = sync_retry_with_backoff(
                lambda: self.client.chat_update(**params)
            )
            
            if response.get("ok"):
                logger.info(f"✓ Message updated")
                return response.data
            else:
                logger.error(f"Failed to update message: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error updating message: {e}")
            raise
    
    def delete_message(
        self,
        channel: str,
        ts: str
    ) -> Dict[str, Any]:
        """Delete a message."""
        logger.info(f"Deleting message {ts} in {channel}")
        
        self.rate_limiter.wait_if_needed("chat.delete")
        
        try:
            response = sync_retry_with_backoff(
                lambda: self.client.chat_delete(channel=channel, ts=ts)
            )
            
            if response.get("ok"):
                logger.info(f"✓ Message deleted")
                return response.data
            else:
                logger.error(f"Failed to delete message: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error deleting message: {e}")
            raise
    
    def schedule_message(
        self,
        channel: str,
        text: str,
        post_at: int,
        blocks: Optional[List[Dict]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Schedule a message for later."""
        logger.info(f"Scheduling message for {post_at}")
        
        self.rate_limiter.wait_if_needed("chat.scheduleMessage")
        
        try:
            params = {
                "channel": channel,
                "text": text,
                "post_at": post_at,
                **kwargs
            }
            
            if blocks:
                params["blocks"] = blocks
            
            response = sync_retry_with_backoff(
                lambda: self.client.chat_scheduleMessage(**params)
            )
            
            if response.get("ok"):
                logger.info(f"✓ Message scheduled")
                return response.data
            else:
                logger.error(f"Failed to schedule message: {response.get('error')}")
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error scheduling message: {e}")
            raise
    
    def send_rich_message(
        self,
        channel: str,
        title: str,
        text: str,
        color: str = "#36a64f",
        fields: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Send a rich formatted message with attachments."""
        attachment = {
            "color": color,
            "title": title,
            "text": text,
        }
        
        if fields:
            attachment["fields"] = fields
        
        return self.send_message(
            channel=channel,
            text=title,
            attachments=[attachment]
        )
