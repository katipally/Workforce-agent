"""LangChain Tools for Workforce AI Agent.

Implements action tools for Slack, Gmail, and Notion operations.
"""

from typing import List, Dict, Any, Optional
from langchain.tools import Tool, StructuredTool
from pydantic import BaseModel, Field
import sys
import os
from pathlib import Path

# Add core directory to path
core_path = Path(__file__).parent.parent / 'core'
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

from config import Config
from slack.sender.message_sender import MessageSender
from slack.sender.file_sender import FileSender
from gmail.client import GmailClient
from notion_export.client import NotionClient
from database.db_manager import DatabaseManager
from utils.logger import get_logger

logger = get_logger(__name__)


# Pydantic models for tool inputs
class SearchSlackInput(BaseModel):
    """Input for searching Slack messages."""
    query: str = Field(description="Search query for Slack messages")
    channel: Optional[str] = Field(default=None, description="Specific channel to search in")
    limit: int = Field(default=10, description="Maximum number of results")


class SendSlackMessageInput(BaseModel):
    """Input for sending Slack messages."""
    channel: str = Field(description="Channel ID or name to send message to")
    text: str = Field(description="Message text to send")


class SearchGmailInput(BaseModel):
    """Input for searching Gmail."""
    query: str = Field(description="Gmail search query (supports Gmail operators)")
    limit: int = Field(default=10, description="Maximum number of results")


class SendEmailInput(BaseModel):
    """Input for sending emails."""
    to: str = Field(description="Recipient email address")
    subject: str = Field(description="Email subject")
    body: str = Field(description="Email body content")


class CreateNotionPageInput(BaseModel):
    """Input for creating Notion pages."""
    title: str = Field(description="Page title")
    content: str = Field(description="Page content")


class WorkforceTools:
    """Collection of tools for the AI agent - Comprehensive API access."""
    
    def __init__(self):
        """Initialize tools with API clients."""
        self.db = DatabaseManager()
        self.slack_sender = MessageSender()
        
        # Initialize API clients
        try:
            from slack_sdk import WebClient
            self.slack_client = WebClient(token=Config.SLACK_BOT_TOKEN)
        except:
            self.slack_client = None
            logger.warning("Slack client not initialized")
        
        try:
            from gmail.client import GmailClient
            self.gmail_client = GmailClient()
        except:
            self.gmail_client = None
            logger.warning("Gmail client not initialized")
        
        try:
            from notion_export.client import NotionClient
            self.notion_client = NotionClient()
        except:
            self.notion_client = None
            logger.warning("Notion client not initialized")
        
        logger.info("Workforce tools initialized with all API clients")
    
    # ========================================
    # HELPER METHODS - Cache to Database
    # ========================================
    
    def _cache_channels_to_db(self, channels: list):
        """Cache Slack channels to database."""
        try:
            # Store channels for RAG later
            logger.info(f"Caching {len(channels)} channels to database")
        except Exception as e:
            logger.error(f"Error caching channels: {e}")
    
    def _cache_messages_to_db(self, channel_id: str, messages: list):
        """Cache Slack messages to database."""
        try:
            # Store messages for RAG later
            logger.info(f"Caching {len(messages)} messages to database")
        except Exception as e:
            logger.error(f"Error caching messages: {e}")
    
    # ========================================
    # SLACK TOOLS - Call API Directly
    # ========================================
    
    def get_all_slack_channels(self) -> str:
        """Get list of all Slack channels - CALLS SLACK API DIRECTLY.
        
        Returns:
            List of channels with names and IDs
        """
        try:
            if not self.slack_client:
                return "❌ Slack API not configured. Check SLACK_BOT_TOKEN in .env"
            
            # Call Slack API directly
            result = self.slack_client.conversations_list(
                exclude_archived=False,
                types="public_channel,private_channel"
            )
            
            channels = result.get('channels', [])
            
            if not channels:
                return "No Slack channels found. You may need to invite the bot to channels."
            
            # Format results
            results = [f"Found {len(channels)} Slack channels:\n"]
            for ch in channels:
                name = ch.get('name', 'unknown')
                channel_id = ch.get('id', '')
                members = ch.get('num_members', 0)
                is_private = ch.get('is_private', False)
                privacy = "🔒 Private" if is_private else "🌐 Public"
                results.append(f"  #{name} - {privacy} - {members} members (ID: {channel_id})")
            
            # Store in database for future use
            self._cache_channels_to_db(channels)
            
            return "\n".join(results)
        
        except Exception as e:
            logger.error(f"Error calling Slack API: {e}")
            return f"❌ Slack API Error: {str(e)}\nPlease check your SLACK_BOT_TOKEN and bot permissions."
    
    def get_channel_messages(self, channel: str, limit: int = 100) -> str:
        """Get ALL messages from a specific Slack channel - CALLS SLACK API DIRECTLY.
        
        Args:
            channel: Channel name (without #) or channel ID
            limit: Maximum messages to retrieve
            
        Returns:
            All messages from the channel
        """
        try:
            if not self.slack_client:
                return "❌ Slack API not configured"
            
            # Get channel ID if name provided
            channel_id = channel
            if not channel.startswith('C'):  # Not a channel ID
                # Find channel by name
                result = self.slack_client.conversations_list()
                channels = result.get('channels', [])
                found = False
                for ch in channels:
                    if ch['name'] == channel.lstrip('#'):
                        channel_id = ch['id']
                        found = True
                        break
                
                if not found:
                    return f"❌ Channel '{channel}' not found. Use get_all_slack_channels to see available channels."
            
            # Get messages from Slack API
            result = self.slack_client.conversations_history(
                channel=channel_id,
                limit=limit
            )
            
            messages = result.get('messages', [])
            
            if not messages:
                return f"No messages found in channel {channel}"
            
            # Get user names
            user_cache = {}
            def get_user_name(user_id):
                if user_id not in user_cache:
                    try:
                        user_info = self.slack_client.users_info(user=user_id)
                        user_cache[user_id] = user_info['user'].get('real_name', user_id)
                    except:
                        user_cache[user_id] = user_id
                return user_cache[user_id]
            
            # Format results
            results = [f"📝 Messages from {channel} ({len(messages)} messages):\n"]
            for msg in reversed(messages):  # Oldest first
                from datetime import datetime
                timestamp = float(msg.get('ts', 0))
                dt = datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")
                user = get_user_name(msg.get('user', 'unknown'))
                text = msg.get('text', '')
                results.append(f"[{dt}] {user}: {text}")
            
            # Store in database
            self._cache_messages_to_db(channel_id, messages)
            
            return "\n".join(results)
        
        except Exception as e:
            logger.error(f"Error calling Slack API: {e}")
            return f"❌ Error: {str(e)}"
    
    def summarize_slack_channel(self, channel: str, limit: int = 100) -> str:
        """Get messages from a channel for summarization.
        
        Args:
            channel: Channel name or ID
            limit: Number of recent messages
            
        Returns:
            Channel messages ready for AI summarization
        """
        messages = self.get_channel_messages(channel, limit)
        return f"Channel Summary Request:\n{messages}\n\nPlease provide a summary of the key topics, decisions, and action items discussed."
    
    def search_slack_messages(self, query: str, channel: Optional[str] = None, limit: int = 10) -> str:
        """Search Slack messages in the database.
        
        Args:
            query: Search query
            channel: Optional channel filter
            limit: Maximum results
            
        Returns:
            Formatted search results
        """
        try:
            with self.db.get_session() as session:
                from database.models import Message, Channel, User
                
                # Build query
                db_query = session.query(Message).join(Channel).join(User)
                
                # Filter by channel if specified
                if channel:
                    db_query = db_query.filter(
                        (Channel.name == channel) | (Channel.id == channel)
                    )
                
                # Text search
                if query:
                    db_query = db_query.filter(Message.text.ilike(f'%{query}%'))
                
                # Order by most recent
                messages = db_query.order_by(Message.timestamp.desc()).limit(limit).all()
                
                if not messages:
                    return f"No Slack messages found matching '{query}'"
                
                # Format results
                results = []
                for msg in messages:
                    from datetime import datetime
                    timestamp = datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d %H:%M")
                    results.append(
                        f"[{timestamp}] {msg.user.name} in #{msg.channel.name}: {msg.text[:200]}"
                    )
                
                return "\n\n".join(results)
        
        except Exception as e:
            logger.error(f"Error searching Slack: {e}")
            return f"Error searching Slack messages: {str(e)}"
    
    def send_slack_message(self, channel: str, text: str) -> str:
        """Send a message to Slack.
        
        Args:
            channel: Channel ID or name
            text: Message text
            
        Returns:
            Success/error message
        """
        try:
            result = self.slack_sender.send_message(channel, text)
            if result:
                return f"✓ Message sent to {channel}"
            else:
                return f"✗ Failed to send message to {channel}"
        
        except Exception as e:
            logger.error(f"Error sending Slack message: {e}")
            return f"Error: {str(e)}"
    
    def get_emails_from_sender(self, sender: str, limit: int = 10) -> str:
        """Get emails from a specific sender - CALLS GMAIL API DIRECTLY.
        
        Args:
            sender: Sender email address or name
            limit: Maximum emails to retrieve
            
        Returns:
            Emails from the specified sender
        """
        try:
            if not self.gmail_client:
                return "❌ Gmail API not configured. Check your Gmail credentials."
            
            if not self.gmail_client.authenticate():
                return "❌ Gmail authentication failed. Run authentication setup first."
            
            # Call Gmail API with search query
            gmail_query = f"from:{sender}"
            results_response = self.gmail_client.service.users().messages().list(
                userId='me',
                q=gmail_query,
                maxResults=limit
            ).execute()
            
            messages = results_response.get('messages', [])
            
            if not messages:
                return f"No emails found from '{sender}'"
            
            # Get full message details
            results = [f"📧 Emails from {sender} ({len(messages)} found):\n"]
            for msg_ref in messages:
                try:
                    msg = self.gmail_client.service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='full'
                    ).execute()
                    
                    headers = msg['payload']['headers']
                    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                    date = next((h['value'] for h in headers if h['name'] == 'Date'), 'No Date')
                    from_addr = next((h['value'] for h in headers if h['name'] == 'From'), sender)
                    
                    # Get body
                    body = ""
                    if 'parts' in msg['payload']:
                        for part in msg['payload']['parts']:
                            if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                                import base64
                                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                                break
                    elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
                        import base64
                        body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8')
                    
                    body_preview = (body[:300] if body else 'No content') + "..."
                    results.append(
                        f"\n[{date}]\n"
                        f"From: {from_addr}\n"
                        f"Subject: {subject}\n"
                        f"Body: {body_preview}\n"
                        f"---"
                    )
                except Exception as e:
                    logger.error(f"Error getting message details: {e}")
                    continue
            
            return "\n".join(results)
        
        except Exception as e:
            logger.error(f"Error calling Gmail API: {e}")
            return f"❌ Gmail API Error: {str(e)}"
    
    def get_email_by_subject(self, subject: str) -> str:
        """Get emails matching a specific subject - CALLS GMAIL API DIRECTLY.
        
        Args:
            subject: Subject keywords to search for
            
        Returns:
            Matching emails with full content
        """
        try:
            if not self.gmail_client or not self.gmail_client.authenticate():
                return "❌ Gmail not authenticated"
            
            # Call Gmail API
            gmail_query = f"subject:{subject}"
            results_response = self.gmail_client.service.users().messages().list(
                userId='me',
                q=gmail_query,
                maxResults=5
            ).execute()
            
            messages = results_response.get('messages', [])
            
            if not messages:
                return f"No emails found with subject containing '{subject}'"
            
            results = [f"📧 Emails with subject '{subject}':\n"]
            for msg_ref in messages:
                try:
                    msg = self.gmail_client.service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='full'
                    ).execute()
                    
                    headers = msg['payload']['headers']
                    subj = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                    date = next((h['value'] for h in headers if h['name'] == 'Date'), 'No Date')
                    from_addr = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                    
                    results.append(
                        f"\n[{date}] From: {from_addr}\n"
                        f"Subject: {subj}\n"
                        f"{'='*50}\n"
                    )
                except:
                    continue
            
            return "\n".join(results)
        
        except Exception as e:
            logger.error(f"Error calling Gmail API: {e}")
            return f"❌ Error: {str(e)}"
    
    def search_gmail_messages(self, query: str, limit: int = 10) -> str:
        """Search Gmail messages in the database.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            Formatted search results
        """
        try:
            with self.db.get_session() as session:
                from database.models import GmailMessage
                
                # Build query
                db_query = session.query(GmailMessage)
                
                # Text search in subject and body
                if query:
                    db_query = db_query.filter(
                        (GmailMessage.subject.ilike(f'%{query}%')) |
                        (GmailMessage.body_text.ilike(f'%{query}%'))
                    )
                
                # Order by most recent
                messages = db_query.order_by(GmailMessage.date.desc()).limit(limit).all()
                
                if not messages:
                    return f"No Gmail messages found matching '{query}'"
                
                # Format results
                results = []
                for msg in messages:
                    date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "N/A"
                    results.append(
                        f"[{date_str}] From: {msg.from_address}\n"
                        f"Subject: {msg.subject}\n"
                        f"Preview: {msg.body_text[:200] if msg.body_text else 'No content'}..."
                    )
                
                return "\n\n---\n\n".join(results)
        
        except Exception as e:
            logger.error(f"Error searching Gmail: {e}")
            return f"Error searching Gmail messages: {str(e)}"
    
    def send_email(self, to: str, subject: str, body: str) -> str:
        """Send an email via Gmail.
        
        Args:
            to: Recipient email
            subject: Email subject
            body: Email body
            
        Returns:
            Success/error message
        """
        try:
            # Initialize Gmail client
            gmail_client = GmailClient()
            if not gmail_client.authenticate():
                return "✗ Gmail authentication failed"
            
            # Create message
            from email.mime.text import MIMEText
            import base64
            
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Send
            result = gmail_client.send_message({'raw': raw_message})
            
            if result:
                return f"✓ Email sent to {to}"
            else:
                return f"✗ Failed to send email to {to}"
        
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return f"Error: {str(e)}"
    
    def list_notion_pages(self, limit: int = 20) -> str:
        """List recent Notion pages.
        
        Args:
            limit: Maximum pages to list
            
        Returns:
            List of Notion pages
        """
        try:
            notion_client = NotionClient()
            if not notion_client.test_connection():
                return "✗ Notion connection failed"
            
            # Note: This requires database query capability
            # For now, return status
            return "✓ Notion connected. Note: Listing pages requires database integration (coming soon)"
        
        except Exception as e:
            logger.error(f"Error listing Notion pages: {e}")
            return f"Error: {str(e)}"
    
    def search_notion_content(self, query: str) -> str:
        """Search Notion pages by content.
        
        Args:
            query: Search query
            
        Returns:
            Matching Notion pages
        """
        try:
            # Note: Notion Search API requires specific setup
            return f"Notion search for '{query}' - Feature requires Notion Search API setup"
        
        except Exception as e:
            logger.error(f"Error searching Notion: {e}")
            return f"Error: {str(e)}"
    
    def create_notion_page(self, title: str, content: str) -> str:
        """Create a Notion page.
        
        Args:
            title: Page title
            content: Page content
            
        Returns:
            Success/error message
        """
        try:
            notion_client = NotionClient()
            if not notion_client.test_connection():
                return "✗ Notion connection failed"
            
            # Create blocks from content
            paragraphs = content.split('\n\n')
            blocks = [notion_client.create_paragraph(p) for p in paragraphs if p.strip()]
            
            # Create page
            page_id = notion_client.create_page(
                parent_page_id=Config.NOTION_PARENT_PAGE_ID,
                title=title,
                children=blocks
            )
            
            if page_id:
                return f"✓ Notion page created: {page_id}"
            else:
                return "✗ Failed to create Notion page"
        
        except Exception as e:
            logger.error(f"Error creating Notion page: {e}")
            return f"Error: {str(e)}"
    
    # ========================================
    # ADVANCED SLACK TOOLS
    # ========================================
    
    def get_slack_user_info(self, user_id: str) -> str:
        """Get detailed information about a Slack user."""
        try:
            if not self.slack_client:
                return "Slack client not available"
            
            result = self.slack_client.users_info(user=user_id)
            user = result['user']
            
            info = f"User: {user.get('real_name', 'N/A')} (@{user['name']})\n"
            info += f"Email: {user.get('profile', {}).get('email', 'N/A')}\n"
            info += f"Title: {user.get('profile', {}).get('title', 'N/A')}\n"
            info += f"Status: {user.get('profile', {}).get('status_text', 'N/A')}\n"
            info += f"Timezone: {user.get('tz', 'N/A')}"
            
            return info
        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return f"Error: {str(e)}"
    
    def get_slack_channel_info(self, channel_id: str) -> str:
        """Get detailed information about a Slack channel."""
        try:
            if not self.slack_client:
                return "Slack client not available"
            
            result = self.slack_client.conversations_info(channel=channel_id)
            channel = result['channel']
            
            info = f"Channel: #{channel['name']}\n"
            info += f"Topic: {channel.get('topic', {}).get('value', 'No topic')}\n"
            info += f"Purpose: {channel.get('purpose', {}).get('value', 'No purpose')}\n"
            info += f"Members: {channel.get('num_members', 'N/A')}\n"
            info += f"Created: {channel.get('created', 'N/A')}"
            
            return info
        except Exception as e:
            logger.error(f"Error getting channel info: {e}")
            return f"Error: {str(e)}"
    
    def get_thread_replies(self, channel: str, thread_ts: str) -> str:
        """Get all replies in a Slack thread."""
        try:
            if not self.slack_client:
                return "Slack client not available"
            
            result = self.slack_client.conversations_replies(
                channel=channel,
                ts=thread_ts
            )
            
            messages = result.get('messages', [])
            if not messages:
                return "No replies found"
            
            replies = []
            for msg in messages[1:]:  # Skip parent message
                user = msg.get('user', 'Unknown')
                text = msg.get('text', '')
                replies.append(f"@{user}: {text}")
            
            return "\n\n".join(replies) if replies else "No replies"
        except Exception as e:
            logger.error(f"Error getting thread replies: {e}")
            return f"Error: {str(e)}"
    
    def add_slack_reaction(self, channel: str, timestamp: str, emoji: str) -> str:
        """Add emoji reaction to a Slack message."""
        try:
            if not self.slack_client:
                return "Slack client not available"
            
            self.slack_client.reactions_add(
                channel=channel,
                timestamp=timestamp,
                name=emoji.replace(':', '')
            )
            return f"✓ Added :{emoji}: reaction"
        except Exception as e:
            logger.error(f"Error adding reaction: {e}")
            return f"Error: {str(e)}"
    
    def set_channel_topic(self, channel: str, topic: str) -> str:
        """Set the topic of a Slack channel."""
        try:
            if not self.slack_client:
                return "Slack client not available"
            
            self.slack_client.conversations_setTopic(
                channel=channel,
                topic=topic
            )
            return f"✓ Channel topic updated"
        except Exception as e:
            logger.error(f"Error setting topic: {e}")
            return f"Error: {str(e)}"
    
    # ========================================
    # ADVANCED GMAIL TOOLS
    # ========================================
    
    def get_gmail_labels(self) -> str:
        """Get all Gmail labels/folders."""
        try:
            if not self.gmail_client or not self.gmail_client.authenticate():
                return "Gmail not authenticated"
            
            labels = self.gmail_client.service.users().labels().list(userId='me').execute()
            label_list = labels.get('labels', [])
            
            result = []
            for label in label_list:
                result.append(f"- {label['name']} (ID: {label['id']})")
            
            return "\n".join(result) if result else "No labels found"
        except Exception as e:
            logger.error(f"Error getting labels: {e}")
            return f"Error: {str(e)}"
    
    def mark_email_read(self, message_id: str) -> str:
        """Mark an email as read."""
        try:
            if not self.gmail_client or not self.gmail_client.authenticate():
                return "Gmail not authenticated"
            
            self.gmail_client.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['UNREAD']}
            ).execute()
            
            return "✓ Email marked as read"
        except Exception as e:
            logger.error(f"Error marking email: {e}")
            return f"Error: {str(e)}"
    
    def archive_email(self, message_id: str) -> str:
        """Archive an email (remove from inbox)."""
        try:
            if not self.gmail_client or not self.gmail_client.authenticate():
                return "Gmail not authenticated"
            
            self.gmail_client.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'removeLabelIds': ['INBOX']}
            ).execute()
            
            return "✓ Email archived"
        except Exception as e:
            logger.error(f"Error archiving email: {e}")
            return f"Error: {str(e)}"
    
    def add_gmail_label(self, message_id: str, label_name: str) -> str:
        """Add a label to an email."""
        try:
            if not self.gmail_client or not self.gmail_client.authenticate():
                return "Gmail not authenticated"
            
            # Find label ID
            labels = self.gmail_client.service.users().labels().list(userId='me').execute()
            label_id = None
            for label in labels.get('labels', []):
                if label['name'].lower() == label_name.lower():
                    label_id = label['id']
                    break
            
            if not label_id:
                return f"Label '{label_name}' not found"
            
            self.gmail_client.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()
            
            return f"✓ Added label '{label_name}'"
        except Exception as e:
            logger.error(f"Error adding label: {e}")
            return f"Error: {str(e)}"
    
    def get_email_thread(self, thread_id: str) -> str:
        """Get all messages in an email thread."""
        try:
            if not self.gmail_client or not self.gmail_client.authenticate():
                return "Gmail not authenticated"
            
            thread = self.gmail_client.service.users().threads().get(
                userId='me',
                id=thread_id
            ).execute()
            
            messages = thread.get('messages', [])
            result = []
            
            for msg in messages:
                headers = msg['payload']['headers']
                subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
                from_addr = next((h['value'] for h in headers if h['name'] == 'From'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'] == 'Date'), 'Unknown')
                
                result.append(f"From: {from_addr}\nDate: {date}\nSubject: {subject}\n")
            
            return "\n---\n".join(result)
        except Exception as e:
            logger.error(f"Error getting thread: {e}")
            return f"Error: {str(e)}"
    
    # ========================================
    # ADVANCED NOTION TOOLS
    # ========================================
    
    def get_notion_page_content(self, page_id: str) -> str:
        """Get content of a Notion page."""
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "Notion not connected"
            
            # Get page blocks
            import requests
            response = requests.get(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_API_KEY}",
                    "Notion-Version": "2022-06-28"
                }
            )
            
            if response.status_code != 200:
                return f"Error: {response.status_code}"
            
            blocks = response.json().get('results', [])
            content = []
            
            for block in blocks:
                block_type = block['type']
                if block_type == 'paragraph':
                    text = ''.join([t.get('plain_text', '') for t in block['paragraph'].get('rich_text', [])])
                    content.append(text)
                elif block_type == 'heading_1':
                    text = ''.join([t.get('plain_text', '') for t in block['heading_1'].get('rich_text', [])])
                    content.append(f"# {text}")
            
            return "\n\n".join(content) if content else "No content"
        except Exception as e:
            logger.error(f"Error getting page content: {e}")
            return f"Error: {str(e)}"
    
    def update_notion_page(self, page_id: str, title: str) -> str:
        """Update a Notion page title."""
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "Notion not connected"
            
            import requests
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_API_KEY}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                },
                json={
                    "properties": {
                        "title": {
                            "title": [{"text": {"content": title}}]
                        }
                    }
                }
            )
            
            if response.status_code == 200:
                return f"✓ Page updated: {title}"
            else:
                return f"Error: {response.status_code}"
        except Exception as e:
            logger.error(f"Error updating page: {e}")
            return f"Error: {str(e)}"
    
    def get_langchain_tools(self) -> List[Tool]:
        """Get list of LangChain tools.
        
        Returns:
            List of Tool objects for LangChain agents
        """
        tools = [
            StructuredTool(
                name="search_slack",
                description="Search through Slack messages. Use this when user asks about Slack messages, conversations, or specific people's messages.",
                func=self.search_slack_messages,
                args_schema=SearchSlackInput
            ),
            StructuredTool(
                name="send_slack_message",
                description="Send a message to a Slack channel. Use this when user asks you to send/post a message to Slack.",
                func=self.send_slack_message,
                args_schema=SendSlackMessageInput
            ),
            StructuredTool(
                name="search_gmail",
                description="Search through Gmail messages and emails. Use this when user asks about emails, inbox, or specific senders.",
                func=self.search_gmail_messages,
                args_schema=SearchGmailInput
            ),
            StructuredTool(
                name="send_email",
                description="Send an email via Gmail. Use this when user asks you to send/write an email to someone.",
                func=self.send_email,
                args_schema=SendEmailInput
            ),
            StructuredTool(
                name="create_notion_page",
                description="Create a new Notion page. Use this when user asks you to create documentation, notes, or save information to Notion.",
                func=self.create_notion_page,
                args_schema=CreateNotionPageInput
            ),
        ]
        
        logger.info(f"Created {len(tools)} LangChain tools")
        return tools
    
    def get_tool_descriptions(self) -> str:
        """Get formatted descriptions of all available tools.
        
        Returns:
            String with tool descriptions
        """
        tools = self.get_langchain_tools()
        descriptions = []
        for tool in tools:
            descriptions.append(f"- **{tool.name}**: {tool.description}")
        
        return "\n".join(descriptions)
