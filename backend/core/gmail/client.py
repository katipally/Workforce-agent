"""Gmail API client."""

import os
import pickle
import base64
from pathlib import Path
from typing import List, Dict, Any, Optional
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.modify',
]


class GmailClient:
    """Gmail API client for authentication and API calls."""
    
    # Expose scopes on the class so other modules can reference them
    SCOPES = SCOPES

    def __init__(self):
        """Initialize Gmail client.
        
        The client must be initialized with OAuth Credentials via
        `init_with_credentials()` before use.
        """
        self.service = None
        self.user_email = None

    def init_with_credentials(self, creds: Credentials) -> bool:
        """Initialize client using already-obtained OAuth credentials."""
        if not creds:
            return False

        try:
            self.service = build('gmail', 'v1', credentials=creds)

            # Get user email
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')

            logger.info(f"Authenticated as: {self.user_email}")
            return True
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            return False

    def authenticate(self) -> bool:
        """Deprecated stub for backward compatibility.
        
        File-based Gmail authentication using credentials JSON and token pickle
        has been removed. GmailClient must be initialized with OAuth
        `Credentials` via `init_with_credentials()` instead.
        """
        logger.error(
            "GmailClient.authenticate() is deprecated. "
            "Use OAuth-based credentials with init_with_credentials() instead."
        )
        return False
    
    def get_profile(self) -> Optional[Dict[str, Any]]:
        """Get Gmail profile/account info.
        
        Returns:
            Profile dict or None
        """
        if not self.service:
            logger.error("Not authenticated")
            return None
        
        try:
            return self.service.users().getProfile(userId='me').execute()
        except HttpError as error:
            logger.error(f"Error getting profile: {error}")
            return None
    
    def list_labels(self) -> List[Dict[str, Any]]:
        """List all labels.
        
        Returns:
            List of label dicts
        """
        if not self.service:
            logger.error("Not authenticated")
            return []
        
        try:
            results = self.service.users().labels().list(userId='me').execute()
            return results.get('labels', [])
        except HttpError as error:
            logger.error(f"Error listing labels: {error}")
            return []
    
    def list_messages(
        self,
        query: str = '',
        max_results: int = 100,
        page_token: str = None,
        label_ids: List[str] = None
    ) -> Dict[str, Any]:
        """List messages matching query.
        
        Args:
            query: Gmail search query
            max_results: Max messages to return
            page_token: Pagination token
            label_ids: Filter by label IDs
            
        Returns:
            Response dict with 'messages' and 'nextPageToken'
        """
        if not self.service:
            logger.error("Not authenticated")
            return {}
        
        try:
            kwargs = {
                'userId': 'me',
                'maxResults': min(max_results, 500),  # API limit
            }
            
            if query:
                kwargs['q'] = query
            if page_token:
                kwargs['pageToken'] = page_token
            if label_ids:
                kwargs['labelIds'] = label_ids
            
            return self.service.users().messages().list(**kwargs).execute()
        
        except HttpError as error:
            logger.error(f"Error listing messages: {error}")
            return {}
    
    def get_message(
        self,
        message_id: str,
        format: str = 'full'
    ) -> Optional[Dict[str, Any]]:
        """Get full message details.
        
        Args:
            message_id: Gmail message ID
            format: 'minimal', 'full', 'raw', or 'metadata'
            
        Returns:
            Message dict or None
        """
        if not self.service:
            logger.error("Not authenticated")
            return None
        
        try:
            return self.service.users().messages().get(
                userId='me',
                id=message_id,
                format=format
            ).execute()
        
        except HttpError as error:
            logger.error(f"Error getting message {message_id}: {error}")
            return None
    
    def get_attachment(
        self,
        message_id: str,
        attachment_id: str
    ) -> Optional[bytes]:
        """Get raw attachment data for a given message.
        
        Uses the Gmail API users.messages.attachments.get endpoint and returns
        the decoded bytes for the attachment body.
        
        Args:
            message_id: Gmail message ID the attachment belongs to
            attachment_id: Attachment ID from the message payload
        
        Returns:
            Attachment bytes or None if not found/failed
        """
        if not self.service:
            logger.error("Not authenticated")
            return None

        try:
            attachment = self.service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()

            data = attachment.get('data')
            if not data:
                return None

            # Gmail API returns base64url-encoded data; decode to raw bytes
            return base64.urlsafe_b64decode(data.encode('utf-8'))

        except HttpError as error:
            logger.error(f"Error getting attachment {attachment_id} for message {message_id}: {error}")
            return None

    def send_message(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send an email message.
        
        Args:
            message: Message dict with 'raw' encoded content
            
        Returns:
            Sent message dict or None
        """
        if not self.service:
            logger.error("Not authenticated")
            return None
        
        try:
            return self.service.users().messages().send(
                userId='me',
                body=message
            ).execute()
        
        except HttpError as error:
            logger.error(f"Error sending message: {error}")
            return None
