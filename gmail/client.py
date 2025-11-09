"""Gmail API client wrapper."""

import os
import base64
import pickle
from typing import List, Dict, Any, Optional
from pathlib import Path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from utils.logger import get_logger

logger = get_logger(__name__)

# Gmail API scopes
SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',  # Read all resources
    'https://www.googleapis.com/auth/gmail.modify',     # Read, compose, send, and modify (no delete)
]


class GmailClient:
    """Gmail API client for reading emails, threads, and attachments."""
    
    def __init__(self, credentials_file: str = None, token_file: str = None):
        """Initialize Gmail client.
        
        Args:
            credentials_file: Path to OAuth 2.0 credentials JSON file
            token_file: Path to save/load user token
        """
        self.credentials_file = credentials_file or os.getenv('GMAIL_CREDENTIALS_FILE', 'credentials.json')
        self.token_file = token_file or os.getenv('GMAIL_TOKEN_FILE', 'data/gmail_token.pickle')
        self.service = None
        self.user_email = None
        
        # Ensure data directory exists
        Path(self.token_file).parent.mkdir(parents=True, exist_ok=True)
    
    def authenticate(self) -> bool:
        """Authenticate with Gmail API using OAuth 2.0.
        
        Returns:
            True if authentication successful, False otherwise
        """
        creds = None
        
        # Load existing token
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # If no valid credentials, authenticate
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired token...")
                creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    logger.error(f"Credentials file not found: {self.credentials_file}")
                    logger.error("Download from Google Cloud Console: https://console.cloud.google.com/")
                    return False
                
                logger.info("Starting OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, SCOPES
                )
                creds = flow.run_local_server(port=0)
                logger.info("✓ Authentication successful")
            
            # Save token for future use
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
                logger.info(f"Token saved to {self.token_file}")
        
        try:
            # Build Gmail service
            self.service = build('gmail', 'v1', credentials=creds)
            
            # Get user email
            profile = self.service.users().getProfile(userId='me').execute()
            self.user_email = profile.get('emailAddress')
            logger.info(f"Connected to Gmail: {self.user_email}")
            
            return True
        except HttpError as error:
            logger.error(f"Gmail API error: {error}")
            return False
    
    def test_connection(self) -> bool:
        """Test Gmail API connection.
        
        Returns:
            True if connected, False otherwise
        """
        if not self.service:
            return self.authenticate()
        
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return True
        except HttpError:
            return False
    
    def list_messages(
        self,
        query: str = '',
        max_results: int = 100,
        page_token: str = None,
        label_ids: List[str] = None
    ) -> Dict[str, Any]:
        """List messages matching query.
        
        Args:
            query: Gmail search query (e.g., 'from:example@gmail.com')
            max_results: Maximum number of messages to return (max 500)
            page_token: Token for pagination
            label_ids: List of label IDs to filter
            
        Returns:
            Dict with 'messages' list and optional 'nextPageToken'
            
        Quota: 5 units per request
        """
        try:
            params = {
                'userId': 'me',
                'maxResults': min(max_results, 500),  # API max is 500
                'q': query,
            }
            
            if page_token:
                params['pageToken'] = page_token
            if label_ids:
                params['labelIds'] = label_ids
            
            result = self.service.users().messages().list(**params).execute()
            return result
        except HttpError as error:
            logger.error(f"Error listing messages: {error}")
            return {'messages': []}
    
    def get_message(
        self,
        message_id: str,
        format: str = 'full',
        metadata_headers: List[str] = None
    ) -> Dict[str, Any]:
        """Get a message by ID.
        
        Args:
            message_id: Message ID
            format: Format of message ('full', 'metadata', 'minimal', 'raw')
            metadata_headers: List of headers to include if format='metadata'
            
        Returns:
            Message object
            
        Quota: 5 units per request
        """
        try:
            params = {
                'userId': 'me',
                'id': message_id,
                'format': format,
            }
            
            if metadata_headers and format == 'metadata':
                params['metadataHeaders'] = metadata_headers
            
            message = self.service.users().messages().get(**params).execute()
            return message
        except HttpError as error:
            logger.error(f"Error getting message {message_id}: {error}")
            return {}
    
    def get_attachment(self, message_id: str, attachment_id: str) -> Optional[bytes]:
        """Get an attachment from a message.
        
        Args:
            message_id: Message ID
            attachment_id: Attachment ID
            
        Returns:
            Attachment data as bytes, or None if error
            
        Quota: 5 units per request
        """
        try:
            attachment = self.service.users().messages().attachments().get(
                userId='me',
                messageId=message_id,
                id=attachment_id
            ).execute()
            
            # Decode base64url encoded data
            data = attachment.get('data', '')
            return base64.urlsafe_b64decode(data)
        except HttpError as error:
            logger.error(f"Error getting attachment: {error}")
            return None
    
    def list_threads(
        self,
        query: str = '',
        max_results: int = 100,
        page_token: str = None,
        label_ids: List[str] = None
    ) -> Dict[str, Any]:
        """List threads matching query.
        
        Args:
            query: Gmail search query
            max_results: Maximum number of threads to return (max 500)
            page_token: Token for pagination
            label_ids: List of label IDs to filter
            
        Returns:
            Dict with 'threads' list and optional 'nextPageToken'
            
        Quota: 5 units per request
        """
        try:
            params = {
                'userId': 'me',
                'maxResults': min(max_results, 500),
                'q': query,
            }
            
            if page_token:
                params['pageToken'] = page_token
            if label_ids:
                params['labelIds'] = label_ids
            
            result = self.service.users().threads().list(**params).execute()
            return result
        except HttpError as error:
            logger.error(f"Error listing threads: {error}")
            return {'threads': []}
    
    def get_thread(self, thread_id: str, format: str = 'full') -> Dict[str, Any]:
        """Get a thread by ID.
        
        Args:
            thread_id: Thread ID
            format: Format of messages in thread ('full', 'metadata', 'minimal')
            
        Returns:
            Thread object with messages
            
        Quota: 5 units per request
        """
        try:
            thread = self.service.users().threads().get(
                userId='me',
                id=thread_id,
                format=format
            ).execute()
            return thread
        except HttpError as error:
            logger.error(f"Error getting thread {thread_id}: {error}")
            return {}
    
    def list_labels(self) -> List[Dict[str, Any]]:
        """List all labels in the user's mailbox.
        
        Returns:
            List of label objects
            
        Quota: 1 unit per request
        """
        try:
            results = self.service.users().labels().list(userId='me').execute()
            return results.get('labels', [])
        except HttpError as error:
            logger.error(f"Error listing labels: {error}")
            return []
    
    def get_profile(self) -> Dict[str, Any]:
        """Get the user's Gmail profile.
        
        Returns:
            Profile object with email address and stats
            
        Quota: 1 unit per request
        """
        try:
            profile = self.service.users().getProfile(userId='me').execute()
            return profile
        except HttpError as error:
            logger.error(f"Error getting profile: {error}")
            return {}
