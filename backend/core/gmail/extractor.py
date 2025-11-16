"""Gmail data extraction."""

import os
import base64
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path
from email import message_from_string
from email.utils import parsedate_to_datetime
from tqdm import tqdm

from .client import GmailClient
from database.db_manager import DatabaseManager
from database.models import (
    GmailAccount, GmailLabel, GmailThread,
    GmailMessage, GmailAttachment
)
from utils.logger import get_logger

logger = get_logger(__name__)


class GmailExtractor:
    """Extract Gmail data and store in database."""
    
    def __init__(self, gmail_client: GmailClient = None, db_manager: DatabaseManager = None):
        """Initialize extractor.
        
        Args:
            gmail_client: Gmail API client
            db_manager: Database manager
        """
        self.client = gmail_client or GmailClient()
        self.db = db_manager or DatabaseManager()
        
        # Ensure authenticated
        if not self.client.service:
            self.client.authenticate()

    def authenticate(self) -> bool:
        """Authenticate the underlying Gmail client.
        
        Returns:
            True if authentication successful
        """
        return self.client.authenticate()
    
    def extract_profile(self) -> Dict[str, Any]:
        """Extract and save Gmail profile/account info.
        
        Returns:
            Profile info dict
        """
        logger.info("Extracting Gmail profile...")
        
        profile = self.client.get_profile()
        if not profile:
            logger.error("Failed to get profile")
            return {}
        
        email_address = profile.get('emailAddress') or self.client.user_email
        if not email_address:
            logger.error("Profile missing email address")
            return {}

        messages_total = profile.get('messagesTotal', 0)
        threads_total = profile.get('threadsTotal', 0)
        history_id = profile.get('historyId')
        
        # Save to database
        with self.db.get_session() as session:
            account = session.query(GmailAccount).filter_by(email=email_address).first()

            if not account:
                account = GmailAccount(email=email_address)
                session.add(account)

            account.messages_total = messages_total
            account.threads_total = threads_total
            account.history_id = history_id
            account.updated_at = datetime.utcnow()
            
            session.commit()
        
        logger.info(f"✓ Profile saved: {email_address} ({messages_total} messages, {threads_total} threads)")
        return profile
    
    def extract_labels(self) -> int:
        """Extract and save all labels.
        
        Returns:
            Number of labels extracted
        """
        logger.info("Extracting Gmail labels...")
        
        labels = self.client.list_labels()
        if not labels:
            logger.warning("No labels found")
            return 0
        
        email_address = self.client.user_email
        
        with self.db.get_session() as session:
            for label_data in tqdm(labels, desc="Saving labels"):
                label_id = label_data.get('id')
                
                label = session.query(GmailLabel).filter_by(label_id=label_id).first()
                
                if not label:
                    label = GmailLabel(
                        label_id=label_id,
                        account_email=email_address
                    )
                    session.add(label)
                
                # Update fields
                label.name = label_data.get('name')
                label.type = label_data.get('type')
                label.message_list_visibility = label_data.get('messageListVisibility')
                label.label_list_visibility = label_data.get('labelListVisibility')
            
            session.commit()
        
        logger.info(f"✓ Extracted {len(labels)} labels")
        return len(labels)
    
    def extract_messages(
        self,
        query: str = '',
        max_messages: int = 500,
        include_spam_trash: bool = False
    ) -> int:
        """Extract messages matching query.
        
        Args:
            query: Gmail search query (e.g., 'after:2024/01/01')
            max_messages: Maximum number of messages to extract
            include_spam_trash: Include spam and trash folders
            
        Returns:
            Number of messages extracted
        """
        logger.info(f"Extracting Gmail messages (query='{query}', max={max_messages})...")
        
        email_address = self.client.user_email
        messages_extracted = 0
        page_token = None
        
        # Exclude spam/trash by default (saves quota)
        if not include_spam_trash:
            exclude_query = '-in:spam -in:trash'
            query = f"{query} {exclude_query}".strip()
        
        while messages_extracted < max_messages:
            # List messages (5 quota units)
            batch_size = min(100, max_messages - messages_extracted)
            result = self.client.list_messages(
                query=query,
                max_results=batch_size,
                page_token=page_token
            )
            
            message_list = result.get('messages', [])
            if not message_list:
                break
            
            # Get full message details
            for msg_info in tqdm(message_list, desc=f"Fetching messages (batch {messages_extracted}-{messages_extracted + len(message_list)})"):
                msg_id = msg_info['id']
                
                # Get full message (5 quota units)
                message = self.client.get_message(msg_id, format='full')
                if message:
                    self._save_message(message, email_address)
                    messages_extracted += 1
            
            # Check for more pages
            page_token = result.get('nextPageToken')
            if not page_token:
                break
        
        logger.info(f"✓ Extracted {messages_extracted} messages")
        return messages_extracted
    
    def extract_threads(
        self,
        query: str = '',
        max_threads: int = 100,
        include_spam_trash: bool = False
    ) -> int:
        """Extract threads (conversations) matching query.
        
        Args:
            query: Gmail search query
            max_threads: Maximum number of threads to extract
            include_spam_trash: Include spam and trash
            
        Returns:
            Number of threads extracted
        """
        logger.info(f"Extracting Gmail threads (query='{query}', max={max_threads})...")
        
        email_address = self.client.user_email
        threads_extracted = 0
        page_token = None
        
        if not include_spam_trash:
            exclude_query = '-in:spam -in:trash'
            query = f"{query} {exclude_query}".strip()
        
        while threads_extracted < max_threads:
            # List threads (5 quota units)
            batch_size = min(50, max_threads - threads_extracted)
            result = self.client.list_threads(
                query=query,
                max_results=batch_size,
                page_token=page_token
            )
            
            thread_list = result.get('threads', [])
            if not thread_list:
                break
            
            # Get full thread details
            for thread_info in tqdm(thread_list, desc=f"Fetching threads"):
                thread_id = thread_info['id']
                
                # Get full thread with messages (5 quota units)
                thread = self.client.get_thread(thread_id, format='full')
                if thread:
                    self._save_thread(thread, email_address)
                    threads_extracted += 1
            
            # Check for more pages
            page_token = result.get('nextPageToken')
            if not page_token:
                break
        
        logger.info(f"✓ Extracted {threads_extracted} threads")
        return threads_extracted
    
    def download_attachments(
        self,
        message_id: str = None,
        output_dir: str = 'data/gmail_attachments'
    ) -> int:
        """Download attachments for a message or all messages.
        
        Args:
            message_id: Specific message ID, or None for all messages with attachments
            output_dir: Directory to save attachments
            
        Returns:
            Number of attachments downloaded
        """
        logger.info("Downloading Gmail attachments...")
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        downloaded = 0
        
        with self.db.get_session() as session:
            # Query for messages with attachments
            if message_id:
                attachments = session.query(GmailAttachment).filter_by(
                    message_id=message_id,
                    downloaded=False
                ).all()
            else:
                attachments = session.query(GmailAttachment).filter_by(
                    downloaded=False
                ).all()
            
            for attachment in tqdm(attachments, desc="Downloading attachments"):
                # Get attachment data (5 quota units)
                data = self.client.get_attachment(
                    attachment.message_id,
                    attachment.attachment_id
                )
                
                if data:
                    # Save file
                    filename = attachment.filename or f"attachment_{attachment.id}"
                    filepath = os.path.join(output_dir, filename)
                    
                    # Handle duplicate filenames
                    if os.path.exists(filepath):
                        name, ext = os.path.splitext(filename)
                        filepath = os.path.join(output_dir, f"{name}_{attachment.id}{ext}")
                    
                    with open(filepath, 'wb') as f:
                        f.write(data)
                    
                    # Update database
                    attachment.local_path = filepath
                    attachment.downloaded = True
                    
                    downloaded += 1
            
            session.commit()
        
        logger.info(f"✓ Downloaded {downloaded} attachments to {output_dir}")
        return downloaded
    
    def _save_message(self, message_data: Dict[str, Any], account_email: str):
        """Save a message to database.
        
        Args:
            message_data: Message object from Gmail API
            account_email: Email address of account
        """
        msg_id = message_data.get('id')
        thread_id = message_data.get('threadId')
        
        # Parse headers
        headers = {}
        for header in message_data.get('payload', {}).get('headers', []):
            headers[header['name'].lower()] = header['value']
        
        # Parse date
        date_str = headers.get('date')
        try:
            date = parsedate_to_datetime(date_str) if date_str else None
        except:
            date = None
        
        # Extract body
        body_plain, body_html = self._extract_body(message_data.get('payload', {}))
        
        # Parse labels
        label_ids = message_data.get('labelIds', [])
        
        # Get attachments info
        attachments = self._extract_attachments(message_data.get('payload', {}))
        
        with self.db.get_session() as session:
            # Ensure thread exists
            thread = session.query(GmailThread).filter_by(thread_id=thread_id).first()
            if not thread:
                thread = GmailThread(
                    thread_id=thread_id,
                    account_email=account_email,
                    snippet=message_data.get('snippet', ''),
                    history_id=message_data.get('historyId')
                )
                session.add(thread)
                session.flush()
            
            # Save or update message
            msg = session.query(GmailMessage).filter_by(message_id=msg_id).first()
            
            if not msg:
                msg = GmailMessage(
                    message_id=msg_id,
                    account_email=account_email,
                    thread_id=thread_id
                )
                session.add(msg)
            
            # Update fields
            msg.history_id = message_data.get('historyId')
            msg.subject = headers.get('subject', '')
            msg.from_address = headers.get('from', '')
            msg.to_addresses = headers.get('to')
            msg.cc_addresses = headers.get('cc')
            msg.bcc_addresses = headers.get('bcc')
            msg.date = date
            msg.snippet = message_data.get('snippet', '')
            msg.body_text = body_plain
            msg.body_html = body_html
            msg.label_ids = label_ids
            msg.is_unread = 'UNREAD' in label_ids
            msg.is_starred = 'STARRED' in label_ids
            msg.is_important = 'IMPORTANT' in label_ids
            msg.is_sent = 'SENT' in label_ids
            msg.is_draft = 'DRAFT' in label_ids
            msg.updated_at = datetime.utcnow()
            
            session.flush()
            
            # Save attachments
            for att_data in attachments:
                att = session.query(GmailAttachment).filter_by(
                    message_id=msg_id,
                    attachment_id=att_data['attachment_id']
                ).first()
                
                if not att:
                    att = GmailAttachment(
                        message_id=msg_id,
                        attachment_id=att_data['attachment_id'],
                        filename=att_data['filename'],
                        mimetype=att_data['mime_type'],
                        size=att_data['size']
                    )
                    session.add(att)
            
            # Update thread message count
            thread.message_count = session.query(GmailMessage).filter_by(thread_id=thread_id).count()
            thread.updated_at = datetime.utcnow()
            
            session.commit()
    
    def _save_thread(self, thread_data: Dict[str, Any], account_email: str):
        """Save a thread and its messages to database.
        
        Args:
            thread_data: Thread object from Gmail API
            account_email: Email address of account
        """
        thread_id = thread_data.get('id')
        
        with self.db.get_session() as session:
            # Save or update thread
            thread = session.query(GmailThread).filter_by(thread_id=thread_id).first()
            
            if not thread:
                thread = GmailThread(
                    thread_id=thread_id,
                    account_email=account_email
                )
                session.add(thread)
            
            thread.snippet = thread_data.get('snippet', '')
            thread.history_id = thread_data.get('historyId')
            thread.updated_at = datetime.utcnow()
            
            session.commit()
        
        # Save all messages in thread
        for message in thread_data.get('messages', []):
            self._save_message(message, account_email)
    
    def _extract_body(self, payload: Dict[str, Any]) -> tuple:
        """Extract plain text and HTML body from message payload.
        
        Handles both single-part and multi-part messages.
        
        Args:
            payload: Message payload
            
        Returns:
            Tuple of (plain_text, html_text)
        """
        plain_text = ''
        html_text = ''
        
        def decode_data(data: str) -> str:
            """Decode base64url encoded data."""
            if not data:
                return ''
            try:
                return base64.urlsafe_b64decode(data).decode('utf-8', errors='ignore')
            except Exception:
                return ''
        
        def extract_parts(part: Dict[str, Any]):
            """Recursively extract text from parts."""
            nonlocal plain_text, html_text
            
            mime_type = part.get('mimeType', '')
            body = part.get('body', {})
            
            # Check if this part has direct body data (single-part message)
            if body.get('data'):
                if mime_type == 'text/plain':
                    plain_text += decode_data(body.get('data', ''))
                elif mime_type == 'text/html':
                    html_text += decode_data(body.get('data', ''))
            
            # Check for nested parts (multi-part message)
            if 'parts' in part:
                for subpart in part.get('parts', []):
                    extract_parts(subpart)
        
        # Start extraction from payload
        if payload:
            extract_parts(payload)
        
        return plain_text.strip(), html_text.strip()
    
    def _extract_attachments(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract attachment info from message payload.
        
        Args:
            payload: Message payload
            
        Returns:
            List of attachment dicts
        """
        attachments = []
        
        def extract_parts(part: Dict[str, Any]):
            """Recursively extract attachments."""
            filename = part.get('filename')
            body = part.get('body', {})
            
            if filename and body.get('attachmentId'):
                attachments.append({
                    'filename': filename,
                    'mime_type': part.get('mimeType', ''),
                    'size': body.get('size', 0),
                    'attachment_id': body.get('attachmentId')
                })
            
            # Check nested parts
            if 'parts' in part:
                for subpart in part.get('parts', []):
                    extract_parts(subpart)
        
        extract_parts(payload)
        
        return attachments
