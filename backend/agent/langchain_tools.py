"""LangChain Tools for Workforce AI Agent.

Implements action tools for Slack, Gmail, and Notion operations.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from langchain_core.tools import Tool, StructuredTool
from pydantic.v1 import BaseModel, Field
import sys
import os
import base64
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from sqlalchemy import or_
import re

# Google OAuth imports for building credentials from stored tokens
from google.oauth2.credentials import Credentials
from google.auth.transport import requests as google_requests
from google.auth.exceptions import RefreshError

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
from settings.service import get_workspace_settings_view, get_effective_slack_bot_token
from utils.logger import get_logger

logger = get_logger(__name__)


def _normalize_notion_id(page_id: str) -> Optional[str]:
    page_id = (page_id or "").strip()
    if not page_id:
        return None

    # Handle full Notion URLs by extracting the last 32-character ID
    if "notion.so" in page_id:
        without_query = page_id.split("?", 1)[0].split("#", 1)[0].rstrip("/")
        last_segment = without_query.rsplit("/", 1)[-1]
        candidate = last_segment.rsplit("-", 1)[-1]
        cleaned = "".join(ch for ch in candidate if ch.isalnum())
        if len(cleaned) >= 32:
            return cleaned[-32:]

        return None

    # Basic validation for plain IDs (with or without hyphens)
    simple = page_id.split("?", 1)[0].split("#", 1)[0]
    hex_chars = "0123456789abcdefABCDEF-"
    if all(ch in hex_chars for ch in simple) and len(simple.replace("-", "")) >= 32:
        return simple

    return None


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


class GetFullEmailInput(BaseModel):
    """Input for getting full email content."""
    message_id: str = Field(description="Gmail message ID")


class GetUnreadCountInput(BaseModel):
    """Input for getting unread email count."""
    pass  # No parameters needed


class AdvancedSearchInput(BaseModel):
    """Input for advanced Gmail search."""
    query: str = Field(description="Gmail search query (from:, to:, subject:, has:attachment, is:unread, after:, before:)")
    limit: int = Field(default=20, description="Maximum results")


class UploadSlackFileInput(BaseModel):
    """Input for uploading files to Slack."""
    channel: str = Field(description="Channel ID")
    file_content: str = Field(description="File content or path")
    filename: str = Field(description="Filename")
    title: Optional[str] = Field(default=None, description="File title")


class PinMessageInput(BaseModel):
    """Input for pinning messages."""
    channel: str = Field(description="Channel ID")
    timestamp: str = Field(description="Message timestamp")


class UpdateNotionPageInput(BaseModel):
    """Input for updating Notion pages."""
    page_id: str = Field(description="Page ID")
    content: str = Field(description="New content to append or update")


class GetNotionPageContentInput(BaseModel):
    """Input for retrieving Notion page content, optionally including subpages."""
    page_id: str = Field(description="Notion page ID")
    include_subpages: bool = Field(
        default=False,
        description="Whether to also traverse and include subpages in the content",
    )
    max_blocks: int = Field(
        default=500,
        description="Maximum number of blocks to read for safety/performance",
    )


class UpdateNotionPageContentInput(BaseModel):
    """Input for find-and-replace inside Notion page content."""

    page_id: str = Field(description="Notion page ID whose content should be updated")
    find_text: str = Field(description="Exact text to search for in page blocks")
    replace_text: str = Field(description="Replacement text")
    include_subpages: bool = Field(
        default=False,
        description="Whether to also search and replace inside subpages",
    )
    max_matches: int = Field(
        default=50,
        description="Safety cap: maximum number of matches to replace across the page tree",
    )


class TrackProjectInput(BaseModel):
    """Input for tracking a project across platforms."""
    project_name: str = Field(description="Name of the project to track")
    days_back: int = Field(default=7, description="Number of days to look back")
    notion_page_id: Optional[str] = Field(default=None, description="Optional Notion page ID for updates")


class GenerateProjectReportInput(BaseModel):
    """Input for generating project reports."""
    project_name: str = Field(description="Name of the project")
    days_back: int = Field(default=7, description="Number of days to include in report")


class UpdateProjectNotionInput(BaseModel):
    """Input for updating Notion page with project status."""
    page_id: str = Field(description="Notion page ID to update")
    project_name: str = Field(description="Project name")
    days_back: int = Field(default=7, description="Days of history to include")


# ============================================================================
# Google Calendar Input Models
# ============================================================================

class ListCalendarEventsInput(BaseModel):
    """Input for listing calendar events."""
    days: int = Field(default=7, description="Number of days to look ahead (default: 7)")
    max_results: int = Field(default=20, description="Maximum number of events to return")


class CreateCalendarEventInput(BaseModel):
    """Input for creating a calendar event."""
    summary: str = Field(description="Event title/summary")
    start_time: str = Field(description="Start time in ISO format (e.g., 2025-01-15T10:00:00) or natural language (e.g., 'tomorrow at 2pm')")
    end_time: str = Field(description="End time in ISO format or natural language")
    description: Optional[str] = Field(default=None, description="Event description")
    location: Optional[str] = Field(default=None, description="Event location")
    attendees: Optional[str] = Field(default=None, description="Comma-separated list of attendee emails")


class UpdateCalendarEventInput(BaseModel):
    """Input for updating a calendar event."""
    event_id: str = Field(description="Google Calendar event ID")
    summary: Optional[str] = Field(default=None, description="New event title")
    start_time: Optional[str] = Field(default=None, description="New start time in ISO format")
    end_time: Optional[str] = Field(default=None, description="New end time in ISO format")
    description: Optional[str] = Field(default=None, description="New description")
    location: Optional[str] = Field(default=None, description="New location")


class DeleteCalendarEventInput(BaseModel):
    """Input for deleting a calendar event."""
    event_id: str = Field(description="Google Calendar event ID to delete")


class CheckCalendarAvailabilityInput(BaseModel):
    """Input for checking calendar availability."""
    start_time: str = Field(description="Start of time range to check (ISO format)")
    end_time: str = Field(description="End of time range to check (ISO format)")


# In-memory cache for Slack channels to avoid repeated API pagination
_slack_channel_cache: Dict[str, Any] = {
    "channels": [],
    "by_name": {},
    "by_id": {},
    "fetched_at": 0,
}
_SLACK_CACHE_TTL_SECONDS = 300  # 5 minutes


class WorkforceTools:
    """Collection of tools for the AI agent - Comprehensive API access."""
    
    def __init__(self, user_id: Optional[str] = None):
        """Initialize tools with API clients.
        
        Args:
            user_id: Optional user ID to load OAuth credentials for Gmail access.
                     If provided, Gmail client will be initialized with user's stored OAuth token.
        """
        self.db = DatabaseManager()
        self.slack_sender = MessageSender()
        self.user_id = user_id
        self._gmail_initialized = False
        
        # Initialize API clients
        try:
            from slack_sdk import WebClient
            token = get_effective_slack_bot_token(self.db)
            if not token:
                raise ValueError("Slack bot token not configured")
            # Add timeout to prevent hanging on network issues
            self.slack_client = WebClient(token=token, timeout=30)
        except Exception as e:
            self.slack_client = None
            logger.warning("Slack client not initialized: %s", e)
        
        # Gmail client will be lazily initialized with user credentials
        self.gmail_client = None
        if user_id:
            self._init_gmail_with_user_credentials(user_id)
        
        try:
            from notion_export.client import NotionClient
            self.notion_client = NotionClient()
        except:
            self.notion_client = None
            logger.warning("Notion client not initialized")
        
        # Initialize Project Tracker
        try:
            from agent.project_tracker import ProjectTracker
            self.project_tracker = ProjectTracker(self)
        except Exception as e:
            self.project_tracker = None
            logger.warning(f"Project Tracker not initialized: {e}")
        
        logger.info("Workforce tools initialized (user_id=%s, gmail=%s)", 
                    user_id[:8] + '...' if user_id else None, 
                    self._gmail_initialized)
    
    def _init_gmail_with_user_credentials(self, user_id: str) -> bool:
        """Initialize Gmail client with user's stored OAuth credentials.
        
        Args:
            user_id: User ID to fetch OAuth token for
            
        Returns:
            True if Gmail client was successfully initialized
        """
        from gmail.client import GmailClient
        from database.models import UserOAuthToken
        
        try:
            with self.db.get_session() as session:
                token = (
                    session.query(UserOAuthToken)
                    .filter_by(user_id=user_id, provider="google", revoked=False)
                    .first()
                )
                if not token or not token.access_token:
                    logger.warning("No valid Google OAuth token found for user %s", user_id)
                    return False
                
                scopes = token.scope.split() if token.scope else GmailClient.SCOPES
                
                creds = Credentials(
                    token=token.access_token,
                    refresh_token=token.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=Config.GOOGLE_CLIENT_ID or None,
                    client_secret=Config.GOOGLE_CLIENT_SECRET or None,
                    scopes=scopes,
                )
                
                # Refresh token if expired
                if token.expires_at and token.expires_at <= datetime.utcnow():
                    if token.refresh_token and Config.GOOGLE_CLIENT_ID and Config.GOOGLE_CLIENT_SECRET:
                        try:
                            creds.refresh(google_requests.Request())
                            token.access_token = creds.token
                            expiry = getattr(creds, "expiry", None)
                            token.expires_at = expiry or datetime.utcnow() + timedelta(seconds=3600)
                            session.commit()
                            logger.info("Refreshed Google OAuth token for user %s", user_id)
                        except RefreshError as e:
                            logger.error("Failed to refresh Google token for user %s: %s", user_id, e)
                            token.revoked = True
                            session.commit()
                            return False
                    else:
                        logger.warning("Token expired and cannot refresh for user %s", user_id)
                        return False
                
                # Initialize Gmail client with credentials
                self.gmail_client = GmailClient()
                if self.gmail_client.init_with_credentials(creds):
                    self._gmail_initialized = True
                    logger.info("Gmail client initialized for user %s", user_id)
                    return True
                else:
                    logger.error("Failed to initialize Gmail client with credentials")
                    self.gmail_client = None
                    return False
                    
        except Exception as e:
            logger.error("Error initializing Gmail for user %s: %s", user_id, e)
            return False
    
    def _ensure_gmail_authenticated(self) -> bool:
        """Check if Gmail client is properly authenticated.
        
        Returns:
            True if Gmail is ready to use, False otherwise
        """
        return self._gmail_initialized and self.gmail_client is not None and self.gmail_client.service is not None
    
    # ========================================
    # HELPER METHODS - Safety, Permissions & Caching
    # ========================================
    
    def _normalize_slack_channel(self, channel: Optional[str]) -> str:
        """Normalize Slack channel identifiers by stripping '#' and whitespace."""
        if not channel:
            return ""
        return channel.strip().lstrip("#")

    def _get_slack_policies(self) -> Dict[str, Any]:
        try:
            settings = get_workspace_settings_view(self.db)
            slack = settings.get("slack") or {}
            return slack
        except Exception as e:
            logger.error("Failed to load Slack policies from settings: %s", e)
            return {}

    def _check_slack_read_allowed(self, channel: Optional[str]) -> Optional[str]:
        """Return error message if reading from a Slack channel is blocked."""
        normalized = self._normalize_slack_channel(channel)
        if not normalized:
            return None
        policies = self._get_slack_policies()
        blocked_list = policies.get("blocked_channels") or []
        blocked = {c.strip().lstrip("#") for c in blocked_list if isinstance(c, str) and c.strip()}
        if normalized in blocked:
            return f"Slack channel '{channel}' is blocked by configuration; read actions are not allowed."
        return None

    def _check_slack_write_allowed(self, channel: Optional[str] = None) -> Optional[str]:
        """Return error message if writing to Slack is disallowed by configuration."""
        policies = self._get_slack_policies()
        mode = (policies.get("mode") or "standard").lower()
        if mode == "read_only":
            return "Slack is configured in read_only mode; write actions are disabled by configuration."
        normalized = self._normalize_slack_channel(channel)
        if normalized:
            blocked_list = policies.get("blocked_channels") or []
            blocked = {c.strip().lstrip("#") for c in blocked_list if isinstance(c, str) and c.strip()}
            if normalized in blocked:
                return f"Slack channel '{channel}' is blocked by configuration; this action is not allowed."
            readonly_list = policies.get("readonly_channels") or []
            readonly = {c.strip().lstrip("#") for c in readonly_list if isinstance(c, str) and c.strip()}
            if normalized in readonly:
                return f"Slack channel '{channel}' is read-only by configuration; write actions are not allowed."
        return None

    def _check_notion_write_allowed(self) -> Optional[str]:
        """Return error message if writing to Notion is disallowed by configuration."""
        mode = (Config.NOTION_MODE or "standard").lower()
        if mode == "read_only":
            return "Notion is configured in read_only mode; write actions are disabled by configuration."
        return None

    def _is_domain_allowed_for_send(self, email: str) -> bool:
        """Check if an email's domain is allowed for sending."""
        gmail = self._get_gmail_policies()
        allowed = gmail.get("allowed_send_domains") or []
        if not allowed or not email:
            return True
        lower_email = email.lower()
        return any(lower_email.endswith(dom.lower()) for dom in allowed)

    def _is_sender_allowed_for_read(self, sender: str) -> bool:
        """Check if a sender/address is allowed to be read based on domain filters."""
        gmail = self._get_gmail_policies()
        allowed = gmail.get("allowed_read_domains") or []
        if not allowed or not sender:
            return True
        lower_sender = sender.lower()
        return any(dom.lower() in lower_sender for dom in allowed)

    def _get_gmail_policies(self) -> Dict[str, Any]:
        try:
            settings = get_workspace_settings_view(self.db)
            gmail = settings.get("gmail") or {}
            return gmail
        except Exception as e:
            logger.error("Failed to load Gmail policies from settings: %s", e)
            return {}

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

    def _get_slack_channels_cached(self, force_refresh: bool = False) -> List[Dict[str, Any]]:
        """Get Slack channels with in-memory caching. Falls back to DB if API is slow/unavailable."""
        import time
        global _slack_channel_cache

        now = time.time()
        cache_age = now - _slack_channel_cache["fetched_at"]

        if not force_refresh and _slack_channel_cache["channels"] and cache_age < _SLACK_CACHE_TTL_SECONDS:
            logger.debug(f"Using cached channel list ({len(_slack_channel_cache['channels'])} channels)")
            return _slack_channel_cache["channels"]

        # Try to load from database first (fast and reliable)
        try:
            from database.models import Channel
            with self.db.get_session() as session:
                db_channels = session.query(Channel).filter(Channel.is_archived == False).all()
                if db_channels:
                    channels = [
                        {"id": ch.channel_id, "name": ch.name, "is_private": ch.is_private}
                        for ch in db_channels
                    ]
                    by_name = {ch["name"]: ch for ch in channels}
                    by_id = {ch["id"]: ch for ch in channels}
                    _slack_channel_cache = {
                        "channels": channels,
                        "by_name": by_name,
                        "by_id": by_id,
                        "fetched_at": now,
                    }
                    logger.debug(f"Loaded {len(channels)} channels from database")
                    return channels
        except Exception as db_err:
            logger.warning(f"Could not load channels from DB: {db_err}")

        # Fallback: Try Slack API (with timeout protection from WebClient)
        if not self.slack_client:
            logger.warning("No Slack client available for channel fetch")
            return _slack_channel_cache["channels"]

        channels: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        try:
            logger.info("Fetching Slack channels from API (fallback)...")
            page_count = 0
            max_pages = 5  # Limit pages to prevent long waits
            while page_count < max_pages:
                page_count += 1
                logger.debug(f"Fetching channel page {page_count}...")
                result = self.slack_client.conversations_list(
                    exclude_archived=False,
                    types="public_channel,private_channel",
                    cursor=cursor,
                    limit=200,
                )
                batch = result.get("channels", [])
                channels.extend(batch)
                logger.debug(f"Got {len(batch)} channels in page {page_count}")

                response_metadata = result.get("response_metadata") or {}
                cursor = response_metadata.get("next_cursor") or ""
                if not cursor:
                    break

            logger.info(f"Fetched {len(channels)} total channels from Slack API")

            by_name = {ch.get("name", ""): ch for ch in channels}
            by_id = {ch.get("id", ""): ch for ch in channels}

            _slack_channel_cache = {
                "channels": channels,
                "by_name": by_name,
                "by_id": by_id,
                "fetched_at": now,
            }
        except Exception as e:
            logger.error(f"Error fetching Slack channels from API: {e}", exc_info=True)

        return _slack_channel_cache["channels"]

    def _resolve_slack_channel_id(self, channel: str) -> Optional[str]:
        """Resolve a channel name or ID to a Slack channel ID using cached data."""
        logger.debug(f"Resolving channel: {channel}")
        normalized = self._normalize_slack_channel(channel)

        # If it already looks like a channel ID, return it
        if channel.startswith("C") or channel.startswith("G"):
            logger.debug(f"Channel {channel} looks like an ID, using directly")
            return channel

        # Try cache first
        logger.debug(f"Looking up normalized name: {normalized}")
        self._get_slack_channels_cached()
        global _slack_channel_cache

        ch = _slack_channel_cache["by_name"].get(normalized)
        if ch:
            logger.debug(f"Found channel in cache: {ch.get('id')}")
            return ch.get("id")

        # If not found in cache, force refresh once and try again
        logger.info(f"Channel '{normalized}' not in cache, force refreshing...")
        self._get_slack_channels_cached(force_refresh=True)
        ch = _slack_channel_cache["by_name"].get(normalized)
        if ch:
            logger.debug(f"Found channel after refresh: {ch.get('id')}")
            return ch.get("id")

        logger.warning(f"Channel '{channel}' (normalized: '{normalized}') not found in Slack")
        return None
    
    # ========================================
    # SLACK TOOLS - Read from Local Database
    # ========================================
    
    def get_all_slack_channels(self) -> str:
        """Get list of all Slack channels from the local database.
        
        Returns:
            List of channels with names and IDs
        """
        try:
            from database.models import Channel
            
            logger.info("get_all_slack_channels called (DB)")
            
            with self.db.get_session() as session:
                channels = session.query(Channel).filter(
                    Channel.is_archived == False
                ).order_by(Channel.name).all()
                
                if not channels:
                    return (
                        "No Slack channels found in synced data. "
                        "Run the Slack sync pipeline first to populate channels."
                    )
                
                results = [f"Found {len(channels)} Slack channels:\n"]
                for ch in channels:
                    name = ch.name or "unknown"
                    channel_id = ch.channel_id or ""
                    members = ch.num_members or 0
                    is_private = ch.is_private or False
                    privacy = "🔒 Private" if is_private else "🌐 Public"
                    results.append(f"  #{name} - {privacy} - {members} members (ID: {channel_id})")
                
                logger.info(f"get_all_slack_channels returned {len(channels)} channels from DB")
                return "\n".join(results)
        
        except Exception as e:
            logger.error(f"Error reading Slack channels from DB: {e}", exc_info=True)
            return f"❌ Error reading Slack channels: {str(e)}"
    
    def get_channel_messages(self, channel: str, limit: int = 100) -> str:
        """Get messages from a specific Slack channel from the local database.
        
        Args:
            channel: Channel name (without #) or channel ID
            limit: Maximum messages to retrieve
            
        Returns:
            Messages from the channel (from synced data)
        """
        try:
            from database.models import Channel, Message, User

            logger.info(f"get_channel_messages called (DB): channel={channel}, limit={limit}")

            # Enforce Slack read permissions (still respect safety rules)
            err = self._check_slack_read_allowed(channel)
            if err:
                logger.warning(f"Slack read not allowed: {err}")
                return f"❌ {err}"

            normalized = self._normalize_slack_channel(channel)

            with self.db.get_session() as session:
                # Find channel in local synced Slack data
                ch = (
                    session.query(Channel)
                    .filter(
                        or_(
                            Channel.name == normalized,
                            Channel.name_normalized == normalized,
                            Channel.channel_id == channel,
                        )
                    )
                    .first()
                )

                if not ch:
                    logger.warning("Channel '%s' not found in local Slack DB", channel)
                    return (
                        f"❌ Channel '{channel}' not found in synced Slack data. "
                        f"Try running the Slack sync pipeline for that workspace."
                    )

                channel_id = ch.channel_id
                logger.info(f"Found channel in DB: id={channel_id}, name={ch.name}")

                # Fetch most recent messages from DB
                q = (
                    session.query(Message, User)
                    .outerjoin(User, Message.user_id == User.user_id)
                    .filter(Message.channel_id == channel_id)
                    .order_by(Message.timestamp.desc())
                    .limit(limit)
                )
                rows = q.all()

                if not rows:
                    return f"No messages found in channel {ch.name or channel}"

                from datetime import datetime

                results = [
                    f"📝 Messages from {ch.name or channel} (most recent {len(rows)} messages):\n"
                ]

                # Reverse so we present oldest→newest within the limited window
                for message, user in reversed(rows):
                    ts = datetime.fromtimestamp(message.timestamp).strftime("%Y-%m-%d %H:%M")
                    if user is not None:
                        user_name = (
                            user.display_name
                            or user.real_name
                            or user.username
                            or user.user_id
                        )
                    else:
                        user_name = message.user_id or "Someone"

                    text = message.text or ""
                    results.append(f"[{ts}] {user_name}: {text}")

            logger.info("get_channel_messages completed successfully from DB")
            return "\n".join(results)

        except Exception as e:
            logger.error("Error reading Slack messages from DB: %s", e, exc_info=True)
            return f"❌ Error reading Slack messages: {str(e)}"
    
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
                    err = self._check_slack_read_allowed(channel)
                    if err:
                        return f"❌ {err}"
                    normalized = self._normalize_slack_channel(channel)
                    db_query = db_query.filter(
                        or_(
                            Channel.name == normalized,
                            Channel.channel_id == channel,
                        )
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
                    user_obj = getattr(msg, "user", None)
                    if user_obj is not None:
                        user_name = (
                            getattr(user_obj, "display_name", None)
                            or getattr(user_obj, "real_name", None)
                            or getattr(user_obj, "username", None)
                            or getattr(user_obj, "user_id", None)
                            or "Someone"
                        )
                    else:
                        user_name = getattr(msg, "user_id", None) or "Someone"

                    channel_obj = getattr(msg, "channel", None)
                    channel_name = getattr(channel_obj, "name", None) if channel_obj is not None else None
                    channel_display = channel_name or getattr(msg, "channel_id", None) or "unknown"

                    results.append(
                        f"[{timestamp}] {user_name} in #{channel_display}: {msg.text[:200]}"
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
            err = self._check_slack_write_allowed(channel)
            if err:
                return f"❌ {err}"
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
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated. Please ensure you're logged in with Google OAuth."

            # Enforce Gmail read domain restrictions (if configured)
            if not self._is_sender_allowed_for_read(sender):
                return (
                    "❌ Gmail read from this sender is blocked by configuration. "
                    "Update GMAIL_ALLOWED_READ_DOMAINS if you want to include this address."
                )
            
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
                                body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                                break
                    elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
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
            if not self._ensure_gmail_authenticated():
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

                    # Apply read-domain filter if configured
                    if not self._is_sender_allowed_for_read(from_addr):
                        continue
                    
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
    
    def search_gmail_messages(
        self,
        query: str,
        limit: int = 10,
        gmail_account_email: Optional[str] = None,
    ) -> str:
        """Search Gmail messages in the database.

        Args:
            query: Search query
            limit: Maximum results
            gmail_account_email: If provided, restrict results to this Gmail
                account (gmail_messages.account_email).

        Returns:
            Formatted search results
        """
        try:
            with self.db.get_session() as session:
                from database.models import GmailMessage

                # Build base query
                db_query = session.query(GmailMessage)

                # Scope to a specific Gmail account when requested (multi-tenant safety)
                if gmail_account_email:
                    db_query = db_query.filter(
                        GmailMessage.account_email == gmail_account_email
                    )

                # Text search in subject and body
                if query:
                    db_query = db_query.filter(
                        (GmailMessage.subject.ilike(f"%{query}%"))
                        | (GmailMessage.body_text.ilike(f"%{query}%"))
                    )

                # Apply global Gmail read-domain restriction if configured
                gmail = self._get_gmail_policies()
                allowed_domains = gmail.get("allowed_read_domains") or []
                if allowed_domains:
                    domain_filters = [
                        GmailMessage.from_address.ilike(f"%{dom}%")
                        for dom in allowed_domains
                    ]
                    db_query = db_query.filter(or_(*domain_filters))

                # Order by most recent
                messages = (
                    db_query.order_by(GmailMessage.date.desc()).limit(limit).all()
                )

                if not messages:
                    return f"No Gmail messages found matching '{query}'"

                # Format results
                results = []
                for msg in messages:
                    date_str = (
                        msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "N/A"
                    )
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
            if not self._ensure_gmail_authenticated():
                return "✗ Gmail authentication failed. Please ensure you're logged in with Google OAuth."

            # Enforce allowed send domains (if configured)
            if not self._is_domain_allowed_for_send(to):
                return (
                    "✗ Sending email blocked by configuration: recipient domain is not allowed. "
                    "Update GMAIL_ALLOWED_SEND_DOMAINS if you want to send to this address."
                )

            gmail = self._get_gmail_policies()
            mode = (gmail.get("send_mode") or "confirm").lower()

            # Create message
            message = MIMEText(body)
            message['to'] = to
            message['subject'] = subject
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

            if mode == "draft":
                # Never actually send - just return a draft preview
                return (
                    "✉️ Draft email (NOT SENT because GMAIL_SEND_MODE=draft):\n"
                    f"To: {to}\nSubject: {subject}\n\n{body}"
                )

            # confirm and auto_limited both send, but we still rely on AI guardrails
            result = self.gmail_client.send_message({'raw': raw_message})
            
            if result:
                return f"✓ Email sent to {to}"
            else:
                return f"✗ Failed to send email to {to}"
        
        except Exception as e:
            logger.error(f"Error sending email: {e}")
            return f"Error: {str(e)}"

    def create_gmail_draft(self, to: str, subject: str, body: str) -> str:
        """Create a Gmail draft preview (does not send).

        This intentionally does not call the Gmail send endpoint. It returns a
        preview payload that the UI/logs can display.
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "✗ Gmail authentication failed. Please ensure you're logged in with Google OAuth."

            if to and not self._is_domain_allowed_for_send(to):
                return (
                    "✗ Draft creation blocked by configuration: recipient domain is not allowed. "
                    "Update GMAIL_ALLOWED_SEND_DOMAINS if you want to allow this address."
                )

            return (
                "✉️ Draft email (NOT SENT):\n"
                f"To: {to}\nSubject: {subject}\n\n{body}"
            )
        except Exception as e:
            logger.error("Error creating Gmail draft: %s", e, exc_info=True)
            return f"Error: {str(e)}"

    def replace_notion_page_content(self, page_id: str, content: str) -> str:
        """Replace the content of a Notion page by archiving existing child blocks and appending new ones."""
        try:
            import requests

            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured. Please set it in your environment."

            normalized_id = _normalize_notion_id(page_id)
            if not normalized_id:
                return "❌ Invalid Notion page_id. Please pass a Notion page ID or full Notion URL."

            headers = {
                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }

            # 1) Archive existing children blocks
            cursor: Optional[str] = None
            archived = 0
            while True:
                params: Dict[str, Any] = {"page_size": 100}
                if cursor:
                    params["start_cursor"] = cursor

                resp = requests.get(
                    f"https://api.notion.com/v1/blocks/{normalized_id}/children",
                    headers=headers,
                    params=params,
                )
                if resp.status_code != 200:
                    return f"❌ Notion API error {resp.status_code}: {resp.text[:200]}"

                data = resp.json() or {}
                blocks = data.get("results", []) or []

                for block in blocks:
                    bid = block.get("id")
                    if not bid:
                        continue
                    patch = requests.patch(
                        f"https://api.notion.com/v1/blocks/{bid}",
                        headers=headers,
                        json={"archived": True},
                    )
                    if patch.status_code == 200:
                        archived += 1

                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")

            # 2) Append new blocks
            paragraphs = (content or "").split("\n\n")
            new_blocks: List[Dict[str, Any]] = []
            for para in paragraphs:
                if not para.strip():
                    continue
                new_blocks.append(
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [
                                {"type": "text", "text": {"content": para.strip()}}
                            ]
                        },
                    }
                )

            created = 0
            for i in range(0, len(new_blocks), 100):
                batch = new_blocks[i : i + 100]
                if not batch:
                    continue
                put = requests.patch(
                    f"https://api.notion.com/v1/blocks/{normalized_id}/children",
                    headers=headers,
                    json={"children": batch},
                )
                if put.status_code != 200:
                    return f"❌ Failed to append new content ({put.status_code}): {put.text[:200]}"
                created += len(batch)

            return f"✅ Replaced Notion page content. Archived {archived} block(s), added {created} block(s)."

        except Exception as e:
            logger.error("Error replacing Notion page content: %s", e, exc_info=True)
            return f"❌ Error replacing Notion page content: {str(e)}"
    
    def list_notion_pages(self, limit: int = 20) -> str:
        """List recent Notion pages.
        
        Args:
            limit: Maximum pages to list
            
        Returns:
            List of Notion pages
        """
        try:
            import requests

            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured. Please set it in your environment."

            # Use Notion search API to list pages, ordered by last edited time
            headers = {
                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }

            payload = {
                "page_size": min(max(limit, 1), 100),
                "filter": {"property": "object", "value": "page"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            }

            response = requests.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                logger.error(f"Notion list pages error {response.status_code}: {response.text}")
                return f"❌ Notion API error {response.status_code}: {response.text[:200]}"

            data = response.json()
            results = data.get("results", [])

            if not results:
                return "No Notion pages found. Make sure your integration has access to the workspace/pages."

            lines = []
            for page in results[:limit]:
                title = "Untitled"
                properties = page.get("properties", {})
                title_prop = properties.get("title", {}) or properties.get("Name", {})
                title_array = title_prop.get("title") or []
                if title_array:
                    title = title_array[0].get("plain_text") or title

                last_edited = page.get("last_edited_time", "")
                lines.append(f"📄 {title} (ID: {page['id']}) - Last edited: {last_edited}")

            return "🔍 Recent Notion pages:\n" + "\n".join(lines)

        except Exception as e:
            logger.error(f"Error listing Notion pages: {e}", exc_info=True)
            return f"Error listing Notion pages: {str(e)}"
    
    def list_notion_databases(self, limit: int = 20) -> str:
        """List recent Notion databases in the workspace.
        
        Args:
            limit: Maximum databases to list
            
        Returns:
            List of Notion databases with IDs
        """
        try:
            import requests

            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured. Please set it in your environment."

            headers = {
                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }

            payload = {
                "page_size": min(max(limit, 1), 100),
                "filter": {"property": "object", "value": "database"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            }

            response = requests.post(
                "https://api.notion.com/v1/search",
                headers=headers,
                json=payload,
            )

            if response.status_code != 200:
                logger.error(f"Notion list databases error {response.status_code}: {response.text}")
                return f"❌ Notion API error {response.status_code}: {response.text[:200]}"

            data = response.json()
            results = data.get("results", [])

            if not results:
                return "No Notion databases found. Make sure your integration has access to the workspace/databases."

            lines = []
            for db in results[:limit]:
                title = "Untitled Database"
                title_prop = db.get("title") or []
                if title_prop:
                    title = title_prop[0].get("plain_text") or title

                last_edited = db.get("last_edited_time", "")
                lines.append(f"📚 {title} (ID: {db['id']}) - Last edited: {last_edited}")

            return "🔍 Recent Notion databases:\n" + "\n".join(lines)

        except Exception as e:
            logger.error(f"Error listing Notion databases: {e}", exc_info=True)
            return f"Error listing Notion databases: {str(e)}"
    
    def search_notion_content(self, query: str) -> str:
        """Search Notion pages by content.
        
        Args:
            query: Search query
            
        Returns:
            Matching Notion pages
        """
        try:
            # Delegate to workspace search helper which already uses Notion Search API
            return self.search_notion_workspace(query)

        except Exception as e:
            logger.error(f"Error searching Notion: {e}", exc_info=True)
            return f"Error searching Notion: {str(e)}"
    
    def create_notion_page(self, title: str, content: str) -> str:
        """Create a Notion page.
        
        Args:
            title: Page title
            content: Page content
            
        Returns:
            Success/error message
        """
        try:
            err = self._check_notion_write_allowed()
            if err:
                return f"❌ {err}"

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
            err = self._check_slack_write_allowed(channel)
            if err:
                return f"❌ {err}"
            
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
            if not self._ensure_gmail_authenticated():
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
            if not self._ensure_gmail_authenticated():
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
            if not self._ensure_gmail_authenticated():
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
            if not self._ensure_gmail_authenticated():
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
            if not self._ensure_gmail_authenticated():
                return "Gmail not authenticated"
            
            # Basic validation: require a non-empty thread ID
            thread_id = (thread_id or "").strip()
            if not thread_id:
                return "❌ Gmail thread ID is required"
            
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
            # Normalize Gmail 400/404 errors into a friendly message
            try:
                from googleapiclient.errors import HttpError
            except Exception:  # pragma: no cover - import defensive
                HttpError = None

            if HttpError is not None and isinstance(e, HttpError) and getattr(e.resp, "status", None) in [400, 404]:
                logger.info("Gmail thread fetch failed (status %s): %s", getattr(e.resp, "status", "unknown"), e)
                return "❌ Gmail thread not found or invalid thread ID. It may have been deleted or the ID is incorrect."

            logger.error(f"Error getting thread: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"
    
    def list_gmail_attachments_for_message(self, message_id: str) -> str:
        """List attachments for a specific Gmail message - CALLS GMAIL API DIRECTLY.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Human-readable list of attachments with attachment IDs
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"
            
            msg = self.gmail_client.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            payload = msg.get('payload', {}) or {}
            attachments: List[Dict[str, Any]] = []
            
            def extract_parts(part: Dict[str, Any]):
                filename = part.get('filename')
                body = part.get('body', {}) or {}
                
                if filename and body.get('attachmentId'):
                    attachments.append({
                        'filename': filename,
                        'attachment_id': body.get('attachmentId'),
                        'mime_type': part.get('mimeType', ''),
                        'size': body.get('size', 0)
                    })
                
                for sub in part.get('parts', []) or []:
                    extract_parts(sub)
            
            extract_parts(payload)
            
            if not attachments:
                return f"No attachments found for message {message_id}"
            
            lines = [f"📎 Attachments for message {message_id}:"]
            for idx, att in enumerate(attachments, 1):
                lines.append(
                    f"{idx}. {att['filename']} "
                    f"(MIME: {att['mime_type']}, Size: {att['size']} bytes, "
                    f"attachment_id: {att['attachment_id']})"
                )
            
            return "\n".join(lines)
        
        except Exception as e:
            # Don't log stack trace for expected errors (invalid IDs, etc.)
            from googleapiclient.errors import HttpError
            if isinstance(e, HttpError) and e.resp.status in [400, 404]:
                logger.info(f"Gmail attachment listing failed (expected error): {e}")
            else:
                logger.error(f"Error listing attachments: {e}", exc_info=True)
            return f"❌ Error listing attachments: {str(e)}"
    
    def download_gmail_attachment(
        self,
        message_id: str,
        attachment_id: str,
        filename: str
    ) -> str:
        """Download a specific Gmail attachment and save it to local files directory.
        
        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID from Gmail
            filename: Desired filename for local storage
            
        Returns:
            Success/error message with local path
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"
            
            data = self.gmail_client.get_attachment(message_id, attachment_id)
            if not data:
                return "❌ Failed to download attachment (no data returned)"
            
            # Determine target directory
            base_dir = Config.FILES_DIR / "gmail_attachments"
            base_dir.mkdir(parents=True, exist_ok=True)
            
            # Use only the basename to avoid directory traversal
            safe_name = os.path.basename(filename) or f"attachment_{attachment_id}"
            file_path = base_dir / safe_name
            
            # Handle duplicate filenames
            if file_path.exists():
                stem = file_path.stem
                suffix = file_path.suffix
                file_path = base_dir / f"{stem}_{attachment_id[:8]}{suffix}"
            
            with open(file_path, "wb") as f:
                f.write(data)
            
            return f"✅ Attachment saved to {file_path}"
        
        except Exception as e:
            logger.error(f"Error downloading attachment: {e}", exc_info=True)
            return f"❌ Error downloading attachment: {str(e)}"
    
    def send_gmail_with_attachments(
        self,
        to: str,
        subject: str,
        body: str,
        file_paths: str
    ) -> str:
        """Send an email with one or more file attachments via Gmail.
        
        Args:
            to: Recipient email address
            subject: Email subject
            body: Plain-text email body
            file_paths: Comma-separated list of file paths to attach
            
        Returns:
            Success/error message
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "✗ Gmail authentication failed. Please ensure you're logged in with Google OAuth."

            # Enforce allowed send domains (if configured)
            if not self._is_domain_allowed_for_send(to):
                return (
                    "✗ Sending email blocked by configuration: recipient domain is not allowed. "
                    "Update GMAIL_ALLOWED_SEND_DOMAINS if you want to send to this address."
                )

            mode = (Config.GMAIL_SEND_MODE or "confirm").lower()

            msg = MIMEMultipart()
            msg["to"] = to
            msg["subject"] = subject
            
            # Body
            msg.attach(MIMEText(body, "plain"))
            
            # Attach files
            attached_files: List[str] = []
            paths = [p.strip() for p in (file_paths or "").split(",") if p.strip()]
            for path in paths:
                try:
                    file_path = Path(path)
                    if not file_path.is_absolute():
                        file_path = Config.PROJECT_ROOT / file_path
                    
                    if not file_path.exists():
                        logger.warning(f"Attachment file not found: {file_path}")
                        continue
                    
                    with open(file_path, "rb") as f:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{file_path.name}"',
                    )
                    msg.attach(part)
                    attached_files.append(str(file_path))
                except Exception as att_err:
                    logger.error(f"Error attaching file {path}: {att_err}")
                    continue
            
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode()

            if mode == "draft":
                # Never send - just describe the draft
                return (
                    "✉️ Draft email with attachments (NOT SENT because GMAIL_SEND_MODE=draft):\n"
                    f"To: {to}\nSubject: {subject}\n"
                    f"Attachments prepared: {', '.join(attached_files) if attached_files else 'none'}"
                )

            result = self.gmail_client.send_message({"raw": raw_message})
            
            if result:
                return (
                    f"✓ Email with {len(attached_files)} attachment(s) sent to {to}. "
                    f"Attached files: {', '.join(attached_files)}"
                )
            else:
                return f"✗ Failed to send email with attachments to {to}"
        
        except Exception as e:
            logger.error(f"Error sending email with attachments: {e}", exc_info=True)
            return f"Error: {str(e)}"
    
    # ========================================
    # ADVANCED NOTION TOOLS
    # ========================================

    def get_notion_database_content(
        self,
        database_id: str,
        max_entries: int = 500,
        filter_property: Optional[str] = None,
        filter_value: Optional[str] = None,
        as_markdown_table: bool = True,
    ) -> str:
        """Get ALL entries from a Notion database with their properties.

        This is specifically for Notion DATABASES (tables with rows and columns).
        Use this when a page contains structured data like a table/list with
        multiple entries and columns (e.g., Projects, Tasks, Contacts, etc.).

        Args:
            database_id: The Notion database ID or URL
            max_entries: Maximum number of entries to return (default 500 for complete data)
            filter_property: Optional property name to filter by
            filter_value: Optional value to filter for (used with filter_property)
            as_markdown_table: If True, format as markdown table for better display

        Returns:
            Formatted database content with all entries and their properties
        """
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"

            normalized_id = _normalize_notion_id(database_id)
            if not normalized_id:
                return "❌ Invalid database_id. Please pass a Notion database ID or full Notion URL."

            # First try to get database metadata to confirm it's a database
            db_meta = self.notion_client.get_database(normalized_id)
            db_title = "Untitled Database"
            
            if db_meta:
                # Get database title
                title_parts = db_meta.get("title", [])
                db_title = "".join(t.get("plain_text", "") for t in title_parts) or "Untitled Database"

            # Get database schema (properties/columns)
            schema = db_meta.get("properties", {}) if db_meta else {}
            
            # Build filter if specified
            filter_obj = None
            if filter_property and filter_value and filter_property in schema:
                prop_type = schema[filter_property].get("type")
                if prop_type in ("title", "rich_text"):
                    filter_obj = {
                        "property": filter_property,
                        prop_type: {"contains": filter_value}
                    }
                elif prop_type == "select":
                    filter_obj = {
                        "property": filter_property,
                        "select": {"equals": filter_value}
                    }
                elif prop_type == "status":
                    filter_obj = {
                        "property": filter_property,
                        "status": {"equals": filter_value}
                    }

            # Query database entries - get ALL of them
            entries = self.notion_client.query_database(
                normalized_id,
                filter_obj=filter_obj,
                max_results=max_entries,
            )

            # If no entries found, this might be a LINKED database view
            # Try to find the original database by title
            if not entries and db_title and db_title != "Untitled Database":
                logger.info(f"No entries for {normalized_id}, searching for original database '{db_title}'")
                original_db = self.notion_client.find_database_by_title(db_title)
                if original_db:
                    original_id = original_db.get("id")
                    if original_id and original_id != normalized_id:
                        logger.info(f"Found original database: {original_id}")
                        normalized_id = original_id
                        db_meta = original_db
                        schema = db_meta.get("properties", {})
                        entries = self.notion_client.query_database(
                            normalized_id,
                            filter_obj=filter_obj,
                            max_results=max_entries,
                        )
            
            # If still no metadata, we can't proceed
            if not db_meta:
                return f"❌ Could not find database {database_id}. Make sure the Notion integration has access to it."

            # Order columns: title first, then others
            title_col = None
            other_cols = []
            for col_name, col_schema in schema.items():
                if col_schema.get("type") == "title":
                    title_col = col_name
                else:
                    other_cols.append(col_name)
            columns = ([title_col] if title_col else []) + sorted(other_cols)

            if not entries:
                return f"📊 **Database: {db_title}**\n**Database ID**: `{normalized_id}`\n\nNo entries found. (This may be a linked database - ensure the original database is shared with the integration)"

            # Format as markdown table for better chat display
            if as_markdown_table:
                # Add database_id to the table output
                table_output = self._format_database_as_markdown_table(
                    db_title, columns, schema, entries
                )
                # Insert database_id after the title line
                lines = table_output.split("\n")
                if lines:
                    lines.insert(1, f"**Database ID**: `{normalized_id}` (use for updates)")
                return "\n".join(lines)

            # Fallback: plain text format
            lines = [
                f"📊 Database: {db_title}",
                f"**Database ID**: `{normalized_id}` (use for updates)",
                f"Columns: {', '.join(columns)}",
                f"Total entries: {len(entries)}",
                "",
            ]

            for i, entry in enumerate(entries, 1):
                formatted = self.notion_client.format_database_entry(entry)
                props = formatted["properties"]
                title_val = props.get(title_col) if title_col else "Untitled"
                lines.append(f"\n**Entry {i}: {title_val}** (ID: {formatted['id'][:8]}...)")

                for col in columns:
                    val = props.get(col)
                    if val is not None and val != "" and val != []:
                        if isinstance(val, list):
                            val_str = ", ".join(str(v) for v in val)
                        else:
                            val_str = str(val)
                        lines.append(f"  - {col}: {val_str}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error getting database content: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"

    def find_notion_entry(self, search_text: str, database_hint: Optional[str] = None) -> str:
        """POWERFUL SEARCH: Find a database entry by name across ALL databases.
        
        This is the BEST way to find an entry when you don't know which database it's in.
        Returns the entry with ALL details needed for updates (database_id, entry_id, properties).
        
        Args:
            search_text: The entry name to search for (e.g., "CloudFactory", "Alegion", "CCHP Health Plan")
            database_hint: Optional hint for which database to search first (e.g., "Yash Exploration")
        
        Returns:
            Entry details with database_id and entry_id ready for updates
        """
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"
            
            search_lower = search_text.lower()
            found_entries = []
            
            # Get all databases
            databases = self.notion_client.search(
                query="",
                filter_type="database",
                max_results=50
            )
            
            # If database_hint provided, prioritize matching databases
            if database_hint:
                hint_lower = database_hint.lower()
                prioritized = []
                others = []
                for db in databases:
                    title = "".join(t.get("plain_text", "") for t in db.get("title", []))
                    if hint_lower in title.lower():
                        prioritized.append(db)
                    else:
                        others.append(db)
                databases = prioritized + others
            
            for db in databases[:20]:  # Limit to first 20 databases
                db_id = db.get("id")
                db_title = "".join(t.get("plain_text", "") for t in db.get("title", []))
                
                if not db_id:
                    continue
                
                # Query this database
                try:
                    entries = self.notion_client.query_database(db_id, max_results=200)
                    
                    # Get schema for title column
                    schema = db.get("properties", {})
                    title_col = None
                    for col_name, col_schema in schema.items():
                        if col_schema.get("type") == "title":
                            title_col = col_name
                            break
                    
                    for entry in entries:
                        formatted = self.notion_client.format_database_entry(entry)
                        props = formatted["properties"]
                        
                        # Check if search_text matches any property
                        for col, val in props.items():
                            if val and search_lower in str(val).lower():
                                found_entries.append({
                                    "database_id": db_id,
                                    "database_title": db_title,
                                    "entry_id": entry.get("id"),
                                    "entry_title": props.get(title_col, "Entry") if title_col else "Entry",
                                    "properties": props,
                                    "title_col": title_col,
                                })
                                break
                except Exception as db_err:
                    logger.debug(f"Could not query database {db_id}: {db_err}")
                    continue
                
                # If we found matches, don't search more databases
                if found_entries:
                    break
            
            if not found_entries:
                return f"❌ Could not find any entry matching '{search_text}' in your Notion databases."
            
            # Format output with all needed IDs
            lines = [
                f"## ✅ Found {len(found_entries)} match(es) for '{search_text}'",
                "",
            ]
            
            for entry in found_entries[:5]:  # Show max 5 matches
                lines.append(f"### {entry['entry_title']}")
                lines.append(f"- **Database**: {entry['database_title']}")
                lines.append(f"- **Database ID**: `{entry['database_id']}`")
                lines.append(f"- **Entry ID**: `{entry['entry_id']}`")
                lines.append("")
                lines.append("**Properties:**")
                for prop_name, prop_val in entry["properties"].items():
                    if prop_val is not None and prop_val != "" and prop_val != []:
                        lines.append(f"- **{prop_name}**: {prop_val}")
                lines.append("")
                lines.append("---")
            
            # Add update instructions
            if found_entries:
                entry = found_entries[0]
                lines.append("")
                lines.append("💡 **To update this entry**, use `update_notion_entry_by_name` with:")
                lines.append(f"- `database_id`: `{entry['database_id']}`")
                lines.append(f"- `entry_name`: `{entry['entry_title']}`")
                lines.append("- `property_name`: (the property you want to change)")
                lines.append("- `new_value`: (the new value)")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Error finding Notion entry: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"

    def list_notion_databases(self, title_filter: Optional[str] = None) -> str:
        """List all databases in the Notion workspace.
        
        Use this to find the correct database ID before querying.
        This returns ORIGINAL databases (not linked views).
        
        Args:
            title_filter: Optional filter to search by title (case-insensitive)
            
        Returns:
            List of databases with their IDs and titles
        """
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"

            databases = self.notion_client.search_databases(title_filter)
            
            if not databases:
                if title_filter:
                    return f"No databases found matching '{title_filter}'"
                return "No databases found in the workspace"

            lines = [
                f"## 📊 Found {len(databases)} database(s)" + (f" matching '{title_filter}'" if title_filter else ""),
                "",
            ]

            for db in databases:
                db_id = db.get("id", "")
                title_parts = db.get("title", [])
                title = "".join(t.get("plain_text", "") for t in title_parts) or "Untitled"
                
                # Get entry count
                try:
                    entries = self.notion_client.query_database(db_id, max_results=1)
                    # Just check if there are entries
                    has_entries = "✓" if entries else "○"
                except:
                    has_entries = "?"
                
                lines.append(f"- **{title}** {has_entries}")
                lines.append(f"  ID: `{db_id}`")

            lines.append("")
            lines.append("*Use the database ID to query entries with `get_notion_database_content`*")
            
            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error listing databases: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"

    def _format_database_as_markdown_table(
        self,
        db_title: str,
        columns: List[str],
        schema: Dict[str, Any],
        entries: List[Dict[str, Any]],
        max_columns: int = 15,
    ) -> str:
        """Format database entries as a markdown table for chat display.
        
        Shows ALL columns up to max_columns. Remaining columns are shown in JSON format.
        """
        # Show more columns but still limit for table width
        display_columns = columns[:max_columns]
        remaining_columns = columns[max_columns:] if len(columns) > max_columns else []

        lines = [
            f"## 📊 {db_title}",
            f"*{len(entries)} entries found* | *{len(columns)} columns total*",
            "",
        ]

        # Build table header
        header = "| " + " | ".join(display_columns) + " |"
        separator = "| " + " | ".join(["---"] * len(display_columns)) + " |"
        lines.append(header)
        lines.append(separator)

        # Build table rows
        for entry in entries:
            formatted = self.notion_client.format_database_entry(entry)
            props = formatted["properties"]

            row_cells = []
            for col in display_columns:
                val = props.get(col)
                if val is None or val == "" or val == []:
                    cell = "-"
                elif isinstance(val, list):
                    cell = ", ".join(str(v)[:30] for v in val[:3])
                    if len(val) > 3:
                        cell += "..."
                elif isinstance(val, (int, float)):
                    # Format numbers nicely
                    if isinstance(val, float) and val >= 1000:
                        cell = f"${val:,.2f}" if "Estim" in col or "price" in col.lower() else f"{val:,.2f}"
                    else:
                        cell = str(val)
                else:
                    cell = str(val)[:100]
                    if len(str(val)) > 100:
                        cell += "..."
                # Escape pipe characters in cells
                cell = cell.replace("|", "\\|").replace("\n", " ")
                row_cells.append(cell)

            lines.append("| " + " | ".join(row_cells) + " |")

        # If there are remaining columns, show them as JSON for each entry
        if remaining_columns:
            lines.append("")
            lines.append(f"### Additional Columns ({', '.join(remaining_columns)})")
            lines.append("```json")
            import json
            for entry in entries[:20]:  # Limit to first 20 for JSON
                formatted = self.notion_client.format_database_entry(entry)
                props = formatted["properties"]
                # Get title/name for identification
                title_val = None
                for col in display_columns[:1]:  # First column is usually title
                    title_val = props.get(col, "Entry")
                    break
                extra_data = {col: props.get(col) for col in remaining_columns if props.get(col)}
                if extra_data:
                    lines.append(f'{{"name": "{title_val}", {json.dumps(extra_data)[1:]}')
            lines.append("```")
            if len(entries) > 20:
                lines.append(f"*(Showing additional columns for first 20 of {len(entries)} entries)*")

        return "\n".join(lines)

    def update_notion_database_entry(
        self,
        entry_id: str,
        property_name: str,
        new_value: Any,
        property_type: Optional[str] = None,
    ) -> str:
        """Update a specific property of a Notion database entry.

        Args:
            entry_id: The entry/page ID to update
            property_name: The name of the property/column to update
            new_value: The new value to set
            property_type: Optional property type hint (title, rich_text, number, 
                          select, status, date, checkbox, url, email). If not provided,
                          will try to auto-detect.

        Returns:
            Success or error message
        """
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"

            normalized_id = _normalize_notion_id(entry_id)
            if not normalized_id:
                return "❌ Invalid entry_id. Please pass a Notion page ID or full Notion URL."

            import requests
            headers = {
                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
            }

            # Get the page to find its parent database and determine property type
            resp = requests.get(
                f"https://api.notion.com/v1/pages/{normalized_id}",
                headers=headers,
            )
            if resp.status_code != 200:
                return f"❌ Could not find entry {entry_id}"

            page_data = resp.json()
            parent = page_data.get("parent", {})

            # If it's a database item, get the database schema
            if parent.get("type") == "database_id":
                db_id = parent.get("database_id")
                db_meta = self.notion_client.get_database(db_id)
                if db_meta:
                    schema = db_meta.get("properties", {})
                    if property_name not in schema:
                        available = ", ".join(schema.keys())
                        return f"❌ Property '{property_name}' not found. Available: {available}"

                    # Auto-detect property type if not provided
                    if not property_type:
                        property_type = schema[property_name].get("type")

            if not property_type:
                property_type = "rich_text"  # Default fallback

            # Build the property update
            prop_update = self.notion_client.build_property_update(property_type, new_value)
            if not prop_update:
                return f"❌ Property type '{property_type}' is not supported for updates"

            # Update the entry
            properties = {property_name: prop_update}
            result = self.notion_client.update_database_entry(normalized_id, properties)

            if result:
                return f"✅ Updated '{property_name}' to '{new_value}' for entry {normalized_id}"
            else:
                return f"❌ Failed to update entry. Check that you have edit access."

        except Exception as e:
            logger.error(f"Error updating database entry: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"

    def get_notion_page_content(
        self,
        page_id: str,
        include_subpages: bool = False,
        max_depth: int = 3,
        max_blocks: int = 500,
    ) -> str:
        """Get flattened text content of a Notion page OR database.

        This function automatically detects if the page_id refers to a database
        and returns the database entries with all properties. For regular pages,
        it returns the text content of blocks.

        Uses the Notion blocks API (GET /v1/blocks/:id/children) with
        pagination and optional recursion into child pages to build a
        readable text view of the page suitable for the chat agent.
        """

        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "Notion not connected"

            import requests

            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured. Please set it in your environment."

            normalized_id = _normalize_notion_id(page_id)
            if not normalized_id:
                return "❌ Invalid Notion page_id. Please pass a Notion page ID or full Notion URL."

            # First check if this is a database
            db_meta = self.notion_client.get_database(normalized_id)
            if db_meta:
                # It's a database! Use the database content function with full entries
                return self.get_notion_database_content(normalized_id, max_entries=500)

            normalized_id = _normalize_notion_id(page_id)
            if not normalized_id:
                return "❌ Invalid Notion page_id. Please pass a Notion page ID or full Notion URL."

            headers = {
                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
            }

            text_lines: List[str] = []
            visited_pages = set()

            TEXT_BLOCK_TYPES = {
                "paragraph",
                "heading_1",
                "heading_2",
                "heading_3",
                "bulleted_list_item",
                "numbered_list_item",
                "to_do",
                "toggle",
                "quote",
            }

            def render_rich_text(rt_list: List[Dict[str, Any]]) -> str:
                return "".join(rt.get("plain_text", "") for rt in (rt_list or [])).strip()

            def walk(parent_id: str, depth: int) -> None:
                """Depth-first traversal of block children with pagination."""

                if depth > max_depth or len(text_lines) >= max_blocks:
                    return

                cursor: Optional[str] = None
                while True:
                    params: Dict[str, Any] = {"page_size": 100}
                    if cursor:
                        params["start_cursor"] = cursor

                    resp = requests.get(
                        f"https://api.notion.com/v1/blocks/{parent_id}/children",
                        headers=headers,
                        params=params,
                    )
                    if resp.status_code != 200:
                        logger.error(
                            "Notion API error %s while reading children for %s: %s",
                            resp.status_code,
                            parent_id,
                            resp.text[:200],
                        )
                        return

                    data = resp.json()
                    blocks = data.get("results", []) or []

                    for block in blocks:
                        if len(text_lines) >= max_blocks:
                            return

                        btype = block.get("type")

                        # Handle child_database blocks - query them directly
                        # Note: Linked databases cannot be queried, must find original
                        if btype == "child_database":
                            db_id = block.get("id")
                            db_title = block.get("child_database", {}).get("title", "Database")
                            if db_id:
                                text_lines.append("")
                                text_lines.append(f"## 📊 Database: {db_title}")
                                text_lines.append(f"**Database ID**: `{db_id}` (use for updates)")
                                # Try to query the database
                                try:
                                    # First try querying the block ID directly
                                    entries = self.notion_client.query_database(db_id, max_results=500)
                                    
                                    # If no entries, this might be a LINKED database view
                                    # Search for the original database by title
                                    if not entries and db_title:
                                        logger.info(f"No entries found for {db_id}, searching for original database '{db_title}'")
                                        original_db = self.notion_client.find_database_by_title(db_title)
                                        if original_db:
                                            original_id = original_db.get("id")
                                            if original_id and original_id != db_id:
                                                logger.info(f"Found original database {original_id}")
                                                db_id = original_id
                                                text_lines.append(f"**Original Database ID**: `{db_id}` (use this for updates)")
                                                entries = self.notion_client.query_database(db_id, max_results=500)
                                    
                                    if entries:
                                        db_meta = self.notion_client.get_database(db_id)
                                        if db_meta:
                                            schema = db_meta.get("properties", {})
                                            # Order columns: title first, then others
                                            title_col = None
                                            other_cols = []
                                            for col_name, col_schema in schema.items():
                                                if col_schema.get("type") == "title":
                                                    title_col = col_name
                                                else:
                                                    other_cols.append(col_name)
                                            ordered_columns = ([title_col] if title_col else []) + sorted(other_cols)
                                            
                                            table_content = self._format_database_as_markdown_table(
                                                db_title, ordered_columns, schema, entries
                                            )
                                            # Skip the title line since we already added it
                                            table_lines = table_content.split("\n")
                                            for i, line in enumerate(table_lines):
                                                if line.startswith("|"):
                                                    text_lines.extend(table_lines[i:])
                                                    break
                                        else:
                                            text_lines.append(f"*{len(entries)} entries found*")
                                    else:
                                        text_lines.append("*No entries found or database not accessible*")
                                        text_lines.append("(This may be a linked database - ensure the original is shared with the integration)")
                                except Exception as db_err:
                                    logger.warning(f"Could not query child database {db_id}: {db_err}")
                                    text_lines.append(f"(Could not load database content: {db_err})")
                            continue

                        # Handle image blocks
                        if btype == "image":
                            image_data = block.get("image", {})
                            image_type = image_data.get("type")  # "file" or "external"
                            url = None
                            if image_type == "file":
                                url = image_data.get("file", {}).get("url")
                            elif image_type == "external":
                                url = image_data.get("external", {}).get("url")
                            caption = render_rich_text(image_data.get("caption", []))
                            if url:
                                text_lines.append(f"📷 Image: {caption or 'Image'}")
                                text_lines.append(f"   URL: {url}")
                            continue

                        # Handle file blocks
                        if btype == "file":
                            file_data = block.get("file", {})
                            file_type = file_data.get("type")
                            url = None
                            name = file_data.get("name", "File")
                            if file_type == "file":
                                url = file_data.get("file", {}).get("url")
                            elif file_type == "external":
                                url = file_data.get("external", {}).get("url")
                            caption = render_rich_text(file_data.get("caption", []))
                            text_lines.append(f"📎 File: {name}")
                            if url:
                                text_lines.append(f"   URL: {url}")
                            continue

                        # Handle video blocks
                        if btype == "video":
                            video_data = block.get("video", {})
                            video_type = video_data.get("type")
                            url = None
                            if video_type == "file":
                                url = video_data.get("file", {}).get("url")
                            elif video_type == "external":
                                url = video_data.get("external", {}).get("url")
                            caption = render_rich_text(video_data.get("caption", []))
                            text_lines.append(f"🎬 Video: {caption or 'Video'}")
                            if url:
                                text_lines.append(f"   URL: {url}")
                            continue

                        # Handle PDF blocks
                        if btype == "pdf":
                            pdf_data = block.get("pdf", {})
                            pdf_type = pdf_data.get("type")
                            url = None
                            if pdf_type == "file":
                                url = pdf_data.get("file", {}).get("url")
                            elif pdf_type == "external":
                                url = pdf_data.get("external", {}).get("url")
                            caption = render_rich_text(pdf_data.get("caption", []))
                            text_lines.append(f"📄 PDF: {caption or 'PDF Document'}")
                            if url:
                                text_lines.append(f"   URL: {url}")
                            continue

                        # Handle embed blocks (links, embeds)
                        if btype == "embed":
                            embed_data = block.get("embed", {})
                            url = embed_data.get("url", "")
                            caption = render_rich_text(embed_data.get("caption", []))
                            if url:
                                text_lines.append(f"🔗 Embed: {caption or url}")
                                text_lines.append(f"   URL: {url}")
                            continue

                        # Handle bookmark blocks
                        if btype == "bookmark":
                            bookmark_data = block.get("bookmark", {})
                            url = bookmark_data.get("url", "")
                            caption = render_rich_text(bookmark_data.get("caption", []))
                            if url:
                                text_lines.append(f"🔖 Bookmark: {caption or url}")
                                text_lines.append(f"   URL: {url}")
                            continue

                        # Handle code blocks
                        if btype == "code":
                            code_data = block.get("code", {})
                            language = code_data.get("language", "")
                            code_text = render_rich_text(code_data.get("rich_text", []))
                            text_lines.append(f"```{language}")
                            text_lines.append(code_text)
                            text_lines.append("```")
                            continue

                        # Handle callout blocks
                        if btype == "callout":
                            callout_data = block.get("callout", {})
                            icon = callout_data.get("icon", {})
                            emoji = icon.get("emoji", "💡") if icon.get("type") == "emoji" else "💡"
                            text = render_rich_text(callout_data.get("rich_text", []))
                            text_lines.append(f"{emoji} {text}")
                            continue

                        # Handle table blocks (inline tables, not databases)
                        if btype == "table":
                            table_data = block.get("table", {})
                            has_col_header = table_data.get("has_column_header", False)
                            text_lines.append("")
                            text_lines.append("📋 Table:")
                            # Fetch table rows directly since they are children of the table block
                            table_id = block.get("id")
                            if table_id:
                                try:
                                    table_resp = requests.get(
                                        f"https://api.notion.com/v1/blocks/{table_id}/children",
                                        headers=headers,
                                        timeout=30,
                                    )
                                    if table_resp.status_code == 200:
                                        table_data = table_resp.json()
                                        table_rows = table_data.get("results", [])
                                        is_first_row = True
                                        for row in table_rows:
                                            if row.get("type") == "table_row":
                                                cells = row.get("table_row", {}).get("cells", [])
                                                row_text = " | ".join(
                                                    render_rich_text(cell) for cell in cells
                                                )
                                                text_lines.append(f"| {row_text} |")
                                                # Add separator after header row
                                                if is_first_row and has_col_header:
                                                    sep = " | ".join(["---"] * len(cells))
                                                    text_lines.append(f"| {sep} |")
                                                is_first_row = False
                                except Exception as e:
                                    logger.warning(f"Could not fetch table rows: {e}")
                            continue

                        # Handle table_row blocks
                        if btype == "table_row":
                            row_data = block.get("table_row", {})
                            cells = row_data.get("cells", [])
                            row_text = " | ".join(
                                render_rich_text(cell) for cell in cells
                            )
                            text_lines.append(f"| {row_text} |")
                            continue

                        # Handle divider blocks
                        if btype == "divider":
                            text_lines.append("---")
                            continue

                        # Handle link_preview blocks
                        if btype == "link_preview":
                            preview_data = block.get("link_preview", {})
                            url = preview_data.get("url", "")
                            if url:
                                text_lines.append(f"🔗 Link: {url}")
                            continue

                        # Render text-like blocks
                        if btype in TEXT_BLOCK_TYPES:
                            block_data = block.get(btype, {}) or {}
                            text = render_rich_text(block_data.get("rich_text") or [])
                            if not text:
                                continue

                            indent = "  " * depth
                            if btype.startswith("heading_"):
                                try:
                                    level = int(btype.split("_")[1])
                                except Exception:
                                    level = 1
                                prefix = "#" * max(1, min(level, 6))
                                text_lines.append(f"{indent}{prefix} {text}")
                            elif btype in {"bulleted_list_item", "numbered_list_item", "to_do"}:
                                text_lines.append(f"{indent}- {text}")
                            else:
                                text_lines.append(f"{indent}{text}")

                        # Recurse into children (including optional subpages)
                        has_children = bool(block.get("has_children"))
                        if has_children:
                            if btype == "child_page":
                                if not include_subpages:
                                    continue
                                child_id = block.get("id")
                                if child_id and child_id not in visited_pages:
                                    visited_pages.add(child_id)
                                    title = (
                                        block.get("child_page", {}).get("title")
                                        or "Untitled page"
                                    )
                                    text_lines.append("")
                                    text_lines.append(
                                        "==== Subpage: " + title + " ===="
                                    )
                                    walk(child_id, depth + 1)
                            else:
                                child_id = block.get("id")
                                if child_id:
                                    walk(child_id, depth + 1)

                    if not data.get("has_more"):
                        break
                    cursor = data.get("next_cursor")

            # Start traversal from the page itself (page_id is also the root block_id)
            walk(normalized_id, depth=0)

            return "\n".join(text_lines) if text_lines else "No content"

        except Exception as e:
            logger.error(f"Error getting page content: {e}", exc_info=True)
            return f"Error: {str(e)}"

    def update_notion_page_content(
        self,
        page_id: str,
        find_text: str,
        replace_text: str,
        include_subpages: bool = False,
        max_matches: int = 50,
    ) -> str:
        """Find and replace text inside a Notion page (and optionally subpages).

        This uses the Notion blocks API (GET /v1/blocks/:id/children and
        PATCH /v1/blocks/:id) to update paragraph/heading/list/to_do/toggle
        blocks that contain the target text. Formatting inside those blocks
        may be simplified, since we replace the full rich_text with a single
        plain-text segment.
        """

        try:
            if not find_text:
                return "❌ find_text must not be empty."
            if find_text == replace_text:
                return "Nothing to update: find_text and replace_text are identical."

            if not self.notion_client or not self.notion_client.test_connection():
                return "Notion not connected"

            import requests

            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured. Please set it in your environment."

            normalized_id = _normalize_notion_id(page_id)
            if not normalized_id:
                return "❌ Invalid Notion page_id. Please pass a Notion page ID or full Notion URL."

            headers = {
                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            }

            TEXT_BLOCK_TYPES = {
                "paragraph",
                "heading_1",
                "heading_2",
                "heading_3",
                "bulleted_list_item",
                "numbered_list_item",
                "to_do",
                "toggle",
                "quote",
            }

            total_matches = 0
            updated_blocks = 0
            visited_pages = set()

            def render_rich_text(rt_list: List[Dict[str, Any]]) -> str:
                return "".join(rt.get("plain_text", "") for rt in (rt_list or [])).strip()

            def patch_block(block: Dict[str, Any], new_text: str) -> bool:
                btype = block.get("type")
                if btype not in TEXT_BLOCK_TYPES:
                    return False

                payload = {
                    btype: {
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": new_text},
                            }
                        ]
                    }
                }

                resp = requests.patch(
                    f"https://api.notion.com/v1/blocks/{block.get('id')}",
                    headers=headers,
                    json=payload,
                )
                if resp.status_code == 200:
                    return True

                logger.error(
                    "Failed to patch Notion block %s (%s): %s",
                    block.get("id"),
                    btype,
                    resp.text[:200],
                )
                return False

            def walk(parent_id: str, depth: int) -> None:
                nonlocal total_matches, updated_blocks
                if depth > 5 or total_matches >= max_matches:
                    return

                cursor: Optional[str] = None
                while True:
                    params: Dict[str, Any] = {"page_size": 100}
                    if cursor:
                        params["start_cursor"] = cursor

                    resp = requests.get(
                        f"https://api.notion.com/v1/blocks/{parent_id}/children",
                        headers=headers,
                        params=params,
                    )
                    if resp.status_code != 200:
                        logger.error(
                            "Notion API error %s while reading children for %s: %s",
                            resp.status_code,
                            parent_id,
                            resp.text[:200],
                        )
                        return

                    data = resp.json()
                    blocks = data.get("results", []) or []

                    for block in blocks:
                        if total_matches >= max_matches:
                            return

                        btype = block.get("type")
                        block_data = block.get(btype, {}) or {}

                        if btype in TEXT_BLOCK_TYPES:
                            text = render_rich_text(block_data.get("rich_text") or [])
                            if find_text in text:
                                new_text = text.replace(find_text, replace_text)
                                if new_text != text and patch_block(block, new_text):
                                    total_matches += text.count(find_text)
                                    updated_blocks += 1

                        # Recurse into child structures / subpages
                        has_children = bool(block.get("has_children"))
                        if has_children:
                            if btype == "child_page":
                                if not include_subpages:
                                    continue
                                child_id = block.get("id")
                                if child_id and child_id not in visited_pages:
                                    visited_pages.add(child_id)
                                    walk(child_id, depth + 1)
                            else:
                                child_id = block.get("id")
                                if child_id:
                                    walk(child_id, depth + 1)

                    if not data.get("has_more"):
                        break
                    cursor = data.get("next_cursor")

            walk(normalized_id, depth=0)

            if updated_blocks == 0:
                return "No matching text found on the specified page or subpages."

            return (
                f"✅ Updated {updated_blocks} block(s) in Notion. "
                f"Approximate matches replaced: {total_matches}."
            )

        except Exception as e:
            logger.error(f"Error updating Notion page content: {e}", exc_info=True)
            return f"❌ Error updating Notion page content: {str(e)}"
    
    def update_notion_page(self, page_id: str, title: str) -> str:
        """Update a Notion page title."""
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "Notion not connected"
            
            import requests
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
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
    
    def query_notion_database(
        self,
        database_id: str,
        filter_json: Optional[str] = None,
        page_size: int = 100,
        search_text: Optional[str] = None,
    ) -> str:
        """Query a Notion database and list matching rows with ALL properties.
        
        Args:
            database_id: ID of the Notion database to query
            filter_json: Optional Notion filter object as JSON string
            page_size: Maximum number of rows to return (default 100)
            search_text: Optional text to search for in entry names/titles
        """
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"

            normalized_id = _normalize_notion_id(database_id)
            if not normalized_id:
                return "❌ Invalid database_id. Please pass a Notion database ID or full Notion URL."

            # Get database metadata for title and schema
            db_meta = self.notion_client.get_database(normalized_id)
            if not db_meta:
                return f"❌ Could not find database {database_id}. Make sure the Notion integration has access to it."

            # Get database title
            title_parts = db_meta.get("title", [])
            db_title = "".join(t.get("plain_text", "") for t in title_parts) or "Untitled Database"

            # Get schema
            schema = db_meta.get("properties", {})
            columns = list(schema.keys())

            # Build filter if provided
            filter_obj = None
            if filter_json:
                try:
                    filter_obj = json.loads(filter_json)
                except json.JSONDecodeError:
                    return "❌ Invalid filter_json. It must be valid JSON representing a Notion filter object."

            # Order columns: title first, then others
            title_col = None
            other_cols = []
            for col_name, col_schema in schema.items():
                if col_schema.get("type") == "title":
                    title_col = col_name
                else:
                    other_cols.append(col_name)
            ordered_columns = ([title_col] if title_col else []) + sorted(other_cols)

            # Query database using the client's comprehensive method
            entries = self.notion_client.query_database(
                normalized_id,
                filter_obj=filter_obj,
                max_results=min(max(page_size, 1), 500),  # Get up to 500 entries
            )

            if not entries:
                return f"📊 **Database: {db_title}**\n\nNo entries found."

            # If search_text provided, filter entries and show full details for matches
            if search_text:
                search_lower = search_text.lower()
                matching_entries = []
                for entry in entries:
                    formatted = self.notion_client.format_database_entry(entry)
                    props = formatted["properties"]
                    # Check if search text matches any property value
                    for col, val in props.items():
                        if val and search_lower in str(val).lower():
                            matching_entries.append(entry)
                            break
                
                if not matching_entries:
                    return f"📊 **Database: {db_title}**\n\nNo entries matching '{search_text}' found."
                
                # Show full details for matching entries - include DATABASE_ID prominently for updates
                lines = [
                    f"## 📊 {db_title}",
                    f"**Database ID**: `{normalized_id}` (use this for updates)",
                    f"*Found {len(matching_entries)} entries matching '{search_text}'*",
                    "",
                ]
                for entry in matching_entries:
                    formatted = self.notion_client.format_database_entry(entry)
                    props = formatted["properties"]
                    # Get entry title
                    entry_title = props.get(title_col, "Entry") if title_col else "Entry"
                    lines.append(f"### {entry_title}")
                    lines.append(f"**Entry ID**: `{entry.get('id')}`")
                    lines.append("")
                    # Show properties in a readable format, not JSON
                    lines.append("**Properties:**")
                    for prop_name, prop_val in props.items():
                        if prop_val is not None and prop_val != "" and prop_val != []:
                            lines.append(f"- **{prop_name}**: {prop_val}")
                    lines.append("")
                    lines.append("---")
                
                lines.append("")
                lines.append("💡 **To update**: Use `update_notion_entry_by_name` with:")
                lines.append(f"- database_id: `{normalized_id}`")
                lines.append(f"- entry_name: (entry name from above)")
                lines.append("- property_name: (property to change)")
                lines.append("- new_value: (new value)")
                
                return "\n".join(lines)

            # Use markdown table format for better chat display
            return self._format_database_as_markdown_table(
                db_title, ordered_columns, schema, entries
            )
        except Exception as e:
            logger.error(f"Error querying Notion database: {e}", exc_info=True)
            return f"❌ Error querying Notion database: {str(e)}"
    
    def update_notion_database_item(self, page_id: str, properties_json: str) -> str:
        """Update properties of an existing Notion database item (page).
        
        Args:
            page_id: Notion page ID
            properties_json: JSON string representing Notion properties object
        """
        try:
            import requests
            
            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured. Please set it in your environment."
            
            try:
                properties = json.loads(properties_json)
            except json.JSONDecodeError:
                return "❌ Invalid properties_json. It must be valid JSON representing Notion properties."
            
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={"properties": properties},
            )
            
            if response.status_code == 200:
                return f"✅ Notion database item {page_id} updated successfully"
            else:
                logger.error(
                    f"Notion database item update error {response.status_code}: {response.text}"
                )
                return f"❌ Notion API error {response.status_code}: {response.text[:200]}"
        except Exception as e:
            logger.error(f"Error updating Notion database item: {e}", exc_info=True)
            return f"❌ Error updating Notion database item: {str(e)}"

    def update_notion_entry_by_name(
        self,
        database_id: str,
        entry_name: str,
        property_name: str,
        new_value: Any,
        property_type: Optional[str] = None,
    ) -> str:
        """Find a database entry by name/title and update a specific property.
        
        This is the easiest way to update Notion database entries - just specify the
        entry name, property to update, and the new value.
        
        Args:
            database_id: The database ID or URL containing the entry
            entry_name: The name/title of the entry to find (e.g., "Alegion", "CCHP Health Plan")
            property_name: The property/column name to update (e.g., "Estimated Value Annually")
            new_value: The new value to set (number, string, date, etc.)
            property_type: Optional hint for property type (number, text, select, date, checkbox, url)
        
        Returns:
            Success message with updated entry details or error message
        """
        try:
            import requests
            
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"
            
            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured."
            
            normalized_id = _normalize_notion_id(database_id)
            if not normalized_id:
                return "❌ Invalid database_id."
            
            # Get database schema to understand property types
            db_meta = self.notion_client.get_database(normalized_id)
            if not db_meta:
                return f"❌ Could not find database {database_id}"
            
            schema = db_meta.get("properties", {})
            
            # Find the title column
            title_col = None
            for col_name, col_schema in schema.items():
                if col_schema.get("type") == "title":
                    title_col = col_name
                    break
            
            # Query database to find the entry
            entries = self.notion_client.query_database(normalized_id, max_results=500)
            
            if not entries:
                return f"❌ No entries found in database"
            
            # Find matching entry by name
            matching_entry = None
            raw_name = (entry_name or "").strip()
            entry_name_lower = raw_name.lower()
            candidates: List[str] = []
            if entry_name_lower:
                candidates.append(entry_name_lower)
                try:
                    stripped = re.sub(r"^\[[^\]]+\]\s*", "", entry_name_lower).strip()
                    if stripped and stripped not in candidates:
                        candidates.append(stripped)
                except Exception:
                    pass
            for entry in entries:
                formatted = self.notion_client.format_database_entry(entry)
                props = formatted.get("properties", {}) if isinstance(formatted, dict) else {}
                
                # Check title column
                if title_col:
                    title_val = props.get(title_col, "")
                    title_lower = str(title_val).lower() if title_val else ""
                    if title_lower:
                        for c in candidates:
                            if c and (c in title_lower or title_lower in c):
                                matching_entry = entry
                                break
                        if matching_entry:
                            break
                
                # Also check any text property that contains the name
                for _, val in props.items():
                    if not val:
                        continue
                    v_lower = str(val).lower()
                    for c in candidates:
                        if c and (c in v_lower or v_lower in c):
                            matching_entry = entry
                            break
                    if matching_entry:
                        break
                if matching_entry:
                    break
            
            if not matching_entry:
                return f"❌ Could not find entry '{entry_name}' in database"
            
            entry_id = matching_entry.get("id")
            if not entry_id:
                return f"❌ Entry found but has no ID"
            
            # Get the property schema to determine type
            prop_schema = schema.get(property_name, {})
            detected_type = prop_schema.get("type") or property_type or "rich_text"
            
            # Build the proper Notion property update payload
            properties_payload = {}
            
            if detected_type == "number":
                try:
                    num_val = float(new_value) if "." in str(new_value) else int(new_value)
                except (ValueError, TypeError):
                    num_val = new_value
                properties_payload[property_name] = {"number": num_val}
                
            elif detected_type == "rich_text":
                properties_payload[property_name] = {
                    "rich_text": [{"text": {"content": str(new_value)}}]
                }
                
            elif detected_type == "title":
                properties_payload[property_name] = {
                    "title": [{"text": {"content": str(new_value)}}]
                }
                
            elif detected_type == "select":
                properties_payload[property_name] = {"select": {"name": str(new_value)}}
                
            elif detected_type == "status":
                properties_payload[property_name] = {"status": {"name": str(new_value)}}
                
            elif detected_type == "multi_select":
                if isinstance(new_value, list):
                    properties_payload[property_name] = {
                        "multi_select": [{"name": str(v)} for v in new_value]
                    }
                else:
                    properties_payload[property_name] = {
                        "multi_select": [{"name": str(new_value)}]
                    }
                    
            elif detected_type == "checkbox":
                bool_val = new_value if isinstance(new_value, bool) else str(new_value).lower() in ("true", "yes", "1")
                properties_payload[property_name] = {"checkbox": bool_val}
                
            elif detected_type == "url":
                properties_payload[property_name] = {"url": str(new_value)}
                
            elif detected_type == "email":
                properties_payload[property_name] = {"email": str(new_value)}
                
            elif detected_type == "phone_number":
                properties_payload[property_name] = {"phone_number": str(new_value)}
                
            elif detected_type == "date":
                # Handle date - expect ISO format or simple date string
                date_str = str(new_value)
                properties_payload[property_name] = {"date": {"start": date_str}}
                
            else:
                # Default to rich_text
                properties_payload[property_name] = {
                    "rich_text": [{"text": {"content": str(new_value)}}]
                }
            
            # Execute the update
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{entry_id}",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={"properties": properties_payload},
                timeout=30,
            )
            
            if response.status_code == 200:
                # Get the entry name for confirmation
                formatted = self.notion_client.format_database_entry(matching_entry)
                entry_title = formatted["properties"].get(title_col, entry_name) if title_col else entry_name
                return f"✅ Updated '{entry_title}':\n- **{property_name}**: {new_value}\n- Entry ID: `{entry_id}`"
            else:
                error_text = response.text[:300]
                logger.error(f"Notion update error {response.status_code}: {error_text}")
                return f"❌ Notion API error {response.status_code}: {error_text}"
                
        except Exception as e:
            logger.error(f"Error updating Notion entry: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"

    def update_notion_database_row_content(
        self,
        database_id: str,
        entry_name: str,
        content: str,
        mode: str = "replace",
    ) -> str:
        try:
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"

            normalized_id = _normalize_notion_id(database_id)
            if not normalized_id:
                return "❌ Invalid database_id."

            db_meta = self.notion_client.get_database(normalized_id)
            if not db_meta:
                return f"❌ Could not find database {database_id}"

            schema = db_meta.get("properties", {})

            title_col = None
            for col_name, col_schema in schema.items():
                if col_schema.get("type") == "title":
                    title_col = col_name
                    break

            entries = self.notion_client.query_database(normalized_id, max_results=500)
            if not entries:
                return "❌ No entries found in database"

            raw_name = (entry_name or "").strip()
            entry_name_lower = raw_name.lower()
            candidates: List[str] = []
            if entry_name_lower:
                candidates.append(entry_name_lower)
                # Common UX pattern: users prefix titles with workspace tags like "[Yash Exploration] Foo".
                # Make matching resilient even if the row title is just "Foo".
                try:
                    stripped = re.sub(r"^\[[^\]]+\]\s*", "", entry_name_lower).strip()
                    if stripped and stripped not in candidates:
                        candidates.append(stripped)
                except Exception:
                    pass
            matching_entry = None

            for entry in entries:
                formatted = self.notion_client.format_database_entry(entry)
                props = formatted.get("properties", {}) if isinstance(formatted, dict) else {}

                if title_col:
                    title_val = props.get(title_col, "")
                    if title_val and entry_name_lower in str(title_val).lower():
                        matching_entry = entry
                        break

                for _, val in props.items():
                    if not val:
                        continue
                    v_lower = str(val).lower()
                    for c in candidates:
                        if c and (c in v_lower or v_lower in c):
                            matching_entry = entry
                            break
                    if matching_entry:
                        break
                if matching_entry:
                    break

            if not matching_entry:
                return f"❌ Could not find entry '{entry_name}' in database"

            entry_id = matching_entry.get("id")
            if not entry_id:
                return "❌ Entry found but has no ID"

            mode_norm = (mode or "replace").strip().lower()
            if mode_norm == "append":
                result = self.append_to_notion_page(page_id=entry_id, content=content)
                return f"✅ Appended content to database row '{entry_name}' (page_id: {entry_id})\n{result}"

            result = self.replace_notion_page_content(page_id=entry_id, content=content)
            return f"✅ Replaced content in database row '{entry_name}' (page_id: {entry_id})\n{result}"

        except Exception as e:
            logger.error(f"Error updating Notion database row content: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"
    
    def add_notion_database_entry(
        self,
        database_id: str,
        properties: Dict[str, Any],
    ) -> str:
        """Add a new entry/row to a Notion database.
        
        Args:
            database_id: The database ID or URL to add entry to
            properties: Dict of property names to values (e.g., {"Name": "New Project", "Status": "Active"})
        
        Returns:
            Success message with new entry ID or error
        """
        try:
            import requests
            
            if not self.notion_client or not self.notion_client.test_connection():
                return "❌ Notion not connected"
            
            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured."
            
            normalized_id = _normalize_notion_id(database_id)
            if not normalized_id:
                return "❌ Invalid database_id."
            
            # Get database schema
            db_meta = self.notion_client.get_database(normalized_id)
            if not db_meta:
                return f"❌ Could not find database {database_id}"
            
            schema = db_meta.get("properties", {})
            
            # Build properties payload based on schema
            properties_payload = {}
            for prop_name, prop_value in properties.items():
                if prop_name not in schema:
                    continue
                    
                prop_type = schema[prop_name].get("type")
                
                if prop_type == "title":
                    properties_payload[prop_name] = {
                        "title": [{"text": {"content": str(prop_value)}}]
                    }
                elif prop_type == "rich_text":
                    properties_payload[prop_name] = {
                        "rich_text": [{"text": {"content": str(prop_value)}}]
                    }
                elif prop_type == "number":
                    try:
                        num_val = float(prop_value) if "." in str(prop_value) else int(prop_value)
                    except (ValueError, TypeError):
                        num_val = prop_value
                    properties_payload[prop_name] = {"number": num_val}
                elif prop_type == "select":
                    properties_payload[prop_name] = {"select": {"name": str(prop_value)}}
                elif prop_type == "status":
                    properties_payload[prop_name] = {"status": {"name": str(prop_value)}}
                elif prop_type == "multi_select":
                    if isinstance(prop_value, list):
                        properties_payload[prop_name] = {
                            "multi_select": [{"name": str(v)} for v in prop_value]
                        }
                    else:
                        properties_payload[prop_name] = {
                            "multi_select": [{"name": str(prop_value)}]
                        }
                elif prop_type == "checkbox":
                    bool_val = prop_value if isinstance(prop_value, bool) else str(prop_value).lower() in ("true", "yes", "1")
                    properties_payload[prop_name] = {"checkbox": bool_val}
                elif prop_type == "url":
                    properties_payload[prop_name] = {"url": str(prop_value)}
                elif prop_type == "email":
                    properties_payload[prop_name] = {"email": str(prop_value)}
                elif prop_type == "date":
                    properties_payload[prop_name] = {"date": {"start": str(prop_value)}}
                else:
                    # Default to rich_text
                    properties_payload[prop_name] = {
                        "rich_text": [{"text": {"content": str(prop_value)}}]
                    }
            
            # Create the page (entry)
            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={
                    "parent": {"database_id": normalized_id},
                    "properties": properties_payload,
                },
                timeout=30,
            )
            
            if response.status_code == 200:
                new_entry = response.json()
                entry_id = new_entry.get("id")
                return f"✅ Created new database entry!\n- Entry ID: `{entry_id}`\n- Properties: {list(properties.keys())}"
            else:
                error_text = response.text[:300]
                logger.error(f"Notion create error {response.status_code}: {error_text}")
                return f"❌ Notion API error {response.status_code}: {error_text}"
                
        except Exception as e:
            logger.error(f"Error creating Notion entry: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"
    
    def delete_notion_database_entry(self, entry_id: str) -> str:
        """Archive/delete a Notion database entry.
        
        Note: Notion doesn't permanently delete - it archives the page.
        
        Args:
            entry_id: The entry/page ID to archive
            
        Returns:
            Success or error message
        """
        try:
            import requests
            
            if not Config.NOTION_TOKEN:
                return "❌ NOTION_TOKEN is not configured."
            
            normalized_id = _normalize_notion_id(entry_id)
            if not normalized_id:
                return "❌ Invalid entry_id."
            
            response = requests.patch(
                f"https://api.notion.com/v1/pages/{normalized_id}",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={"archived": True},
                timeout=30,
            )
            
            if response.status_code == 200:
                return f"✅ Entry `{normalized_id}` has been archived (deleted)"
            else:
                error_text = response.text[:200]
                return f"❌ Notion API error {response.status_code}: {error_text}"
                
        except Exception as e:
            logger.error(f"Error archiving Notion entry: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"
    
    # ========================================
    # CRITICAL NEW TOOLS - Nov 2025 Features
    # ========================================
    
    def get_full_email_content(self, message_id: str) -> str:
        """Get FULL email content including complete body (not just snippet).
        
        This returns the entire email body, not just a preview.
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            Complete email with full body content
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"

            # Basic validation: require a non-empty message ID
            message_id = (message_id or "").strip()
            if not message_id:
                return "❌ Gmail message ID is required"

            # Get FULL message
            msg = self.gmail_client.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Extract headers safely
            payload = msg.get('payload') or {}
            headers = payload.get('headers') or []
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            from_addr = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
            to_addr = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
            
            # Extract COMPLETE body (not snippet)
            def extract_body(payload):
                body = ""
                if 'body' in payload and 'data' in payload['body']:
                    body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
                    return body
                
                if 'parts' in payload:
                    for part in payload['parts']:
                        mime_type = part.get('mimeType', '')
                        if mime_type == 'text/plain' and 'data' in part.get('body', {}):
                            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                            break
                        elif mime_type == 'text/html' and 'data' in part.get('body', {}) and not body:
                            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        if 'parts' in part:
                            nested = extract_body(part)
                            if nested and not body:
                                body = nested
                return body
            
            body = extract_body(payload)
            
            result = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 FULL EMAIL CONTENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
From: {from_addr}
To: {to_addr}
Date: {date}
Subject: {subject}

COMPLETE MESSAGE BODY:
{body if body else 'No body content'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
            return result
        except Exception as e:
            # Normalize Gmail 400/404 errors into a friendly message
            try:
                from googleapiclient.errors import HttpError
            except Exception:  # pragma: no cover - import defensive
                HttpError = None

            if HttpError is not None and isinstance(e, HttpError) and getattr(e.resp, "status", None) in [400, 404]:
                logger.info("Gmail message fetch failed (status %s): %s", getattr(e.resp, "status", "unknown"), e)
                return "❌ Gmail message not found or invalid message ID. It may have been deleted or the ID is incorrect."

            logger.error(f"Error getting full email: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"
    
    def get_unread_email_count(self) -> str:
        """Get EXACT count of unread emails.
        
        Returns:
            Exact number of unread emails in inbox
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"
            
            # Get unread count
            result = self.gmail_client.service.users().messages().list(
                userId='me',
                q='is:unread',
                maxResults=1
            ).execute()
            
            count = result.get('resultSizeEstimate', 0)
            
            return f"📬 You have {count} unread emails"
        except Exception as e:
            logger.error(f"Error getting unread count: {e}")
            return f"❌ Error: {str(e)}"
    
    def get_complete_email_thread(self, thread_id: str) -> str:
        """Get COMPLETE email thread with ALL messages (for long company threads).
        
        This retrieves the ENTIRE thread, no matter how many messages.
        Critical for business use cases with long email chains.
        
        Args:
            thread_id: Gmail thread ID
            
        Returns:
            Complete thread with all messages, full bodies, and metadata
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"

            # Basic validation: require a non-empty thread ID
            thread_id = (thread_id or "").strip()
            if not thread_id:
                return "❌ Gmail thread ID is required"

            # Get COMPLETE thread with ALL messages
            thread = self.gmail_client.service.users().threads().get(
                userId='me',
                id=thread_id,
                format='full'  # Get complete message content for ALL messages
            ).execute()
            
            messages = thread.get('messages') or []
            message_count = len(messages)
            
            if message_count == 0:
                return "No messages found in thread"
            
            # Extract body helper
            def extract_body(payload):
                body = ""
                if 'body' in payload and 'data' in payload['body']:
                    body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
                    return body
                
                if 'parts' in payload:
                    for part in payload['parts']:
                        mime_type = part.get('mimeType', '')
                        if mime_type == 'text/plain' and 'data' in part.get('body', {}):
                            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                            break
                        elif mime_type == 'text/html' and 'data' in part.get('body', {}) and not body:
                            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                        if 'parts' in part:
                            nested = extract_body(part)
                            if nested and not body:
                                body = nested
                return body
            
            # Format complete thread
            result = [f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📧 COMPLETE EMAIL THREAD
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Thread ID: {thread_id}
Total Messages: {message_count}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""]
            
            # Process ALL messages in thread
            for idx, msg in enumerate(messages, 1):
                payload = msg.get('payload') or {}
                headers = payload.get('headers') or []
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                from_addr = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                to_addr = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
                date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
                
                # Extract full body
                body = extract_body(payload)
                
                result.append(f"""
MESSAGE {idx} of {message_count}:
──────────────────────────────────────────────
From: {from_addr}
To: {to_addr}
Date: {date}
Subject: {subject}

{body if body else '[No body content]'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
            
            result.append(f"\n✅ Retrieved ALL {message_count} messages in thread")

            return "\n".join(result)

        except Exception as e:
            # Normalize Gmail 400/404 errors into a friendly message
            try:
                from googleapiclient.errors import HttpError
            except Exception:  # pragma: no cover - import defensive
                HttpError = None

            if HttpError is not None and isinstance(e, HttpError) and getattr(e.resp, "status", None) in [400, 404]:
                logger.info("Gmail thread fetch failed (status %s): %s", getattr(e.resp, "status", "unknown"), e)
                return "❌ Gmail thread not found or invalid thread ID. It may have been deleted or the ID is incorrect."

            logger.error(f"Error getting thread: {e}", exc_info=True)
            return f"❌ Error: {str(e)}"
    
    def search_email_threads(self, query: str, limit: int = 10) -> str:
        """Search for email threads (not individual messages) and get thread info.
        
        Use this when you need to find threads, then use get_complete_email_thread 
        to retrieve full thread content.
        
        Args:
            query: Gmail search query (supports all operators)
            limit: Maximum threads to return
            
        Returns:
            List of threads with summary info and thread IDs
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"
            
            # Search threads (not messages)
            result = self.gmail_client.service.users().threads().list(
                userId='me',
                q=query,
                maxResults=limit
            ).execute()
            
            threads = result.get('threads', [])
            
            if not threads:
                return f"No threads found matching: {query}"
            
            results = [f"📧 Found {len(threads)} email threads matching '{query}':\n"]
            
            # Get summary of each thread
            for idx, thread_ref in enumerate(threads, 1):
                try:
                    # Get thread with metadata
                    thread = self.gmail_client.service.users().threads().get(
                        userId='me',
                        id=thread_ref['id'],
                        format='metadata',
                        metadataHeaders=['Subject', 'From', 'Date']
                    ).execute()
                    
                    messages = thread.get('messages') or []
                    message_count = len(messages)
                    if not messages:
                        continue
                    
                    # Get first message headers safely
                    first_msg = messages[0]
                    payload = first_msg.get('payload') or {}
                    headers = payload.get('headers') or []
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    from_addr = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                    date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
                    
                    results.append(f"""
{idx}. Thread: {subject[:60]}
   Messages: {message_count}
   From: {from_addr}
   Latest: {date}
   Thread ID: {thread_ref['id']}
   Use get_complete_email_thread("{thread_ref['id']}") to read all {message_count} messages
""")
                    
                except Exception as e:
                    logger.error(f"Error getting thread summary: {e}")
                    continue
            
            return "\n".join(results)
            
        except Exception as e:
            logger.error(f"Error searching threads: {e}")
            return f"❌ Error: {str(e)}"
    
    def get_recent_email_thread_between_people(
        self,
        person_a: str,
        person_b: str,
        days_back: int = 60
    ) -> str:
        """Get the most recent email thread between two people and return full content.
        
        This is a high-level helper for natural queries like
        "get our recent email thread between Yash and Ivan".
        
        Args:
            person_a: Name or email of first person
            person_b: Name or email of second person
            days_back: How many days back to search (default: 60)
            
        Returns:
            Full formatted email thread, or explanation if nothing found
        """
        try:
            from datetime import datetime, timedelta

            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"

            # Build date filter
            date_filter = (datetime.now() - timedelta(days=days_back)).strftime("%Y/%m/%d")

            def norm_identifier(person: str) -> str:
                person = (person or "").strip()
                if "@" in person:
                    # Likely an email address
                    return person
                # For names, wrap in quotes so Gmail searches the phrase
                return f'"{person}"'

            a = norm_identifier(person_a)
            b = norm_identifier(person_b)

            # Query that captures both directions of conversation
            # and general mentions of both participants.
            query = (
                f"((from:{a} to:{b}) OR (from:{b} to:{a}) OR ({a} {b})) "
                f"after:{date_filter}"
            )

            # Search for threads matching this pattern (most recent first)
            service = self.gmail_client.service
            result = service.users().threads().list(
                userId="me",
                q=query,
                maxResults=5
            ).execute()

            threads = result.get("threads", [])
            if not threads:
                return (
                    "No recent email threads found between these people.\n"
                    f"Searched with query: {query}\n"
                    "Try providing exact email addresses if possible."
                )

            # Use the most recent thread
            thread_id = threads[0]["id"]

            # Delegate to full-thread helper to get complete content
            return self.get_complete_email_thread(thread_id)

        except Exception as e:
            logger.error(f"Error getting recent thread between people: {e}")
            return f"❌ Error getting recent thread: {str(e)}"
    
    def advanced_gmail_search(self, query: str, limit: int = 20) -> str:
        """Advanced Gmail search with ALL operators supported.
        
        Supports:
        - from:user@example.com - Emails from specific sender
        - to:user@example.com - Emails to specific recipient
        - subject:keyword - Search in subject
        - has:attachment - Emails with attachments
        - is:unread - Unread emails only
        - is:starred - Starred emails
        - is:important - Important emails
        - label:labelname - Emails with specific label
        - after:2024/11/01 - Emails after date
        - before:2024/11/30 - Emails before date
        - filename:pdf - Specific attachment type
        - larger:5M - Emails larger than size
        - smaller:1M - Emails smaller than size
        
        Args:
            query: Gmail search query with operators
            limit: Maximum results
            
        Returns:
            Formatted search results with full content
        """
        try:
            if not self._ensure_gmail_authenticated():
                return "❌ Gmail not authenticated"

            # Apply default label scoping if configured and no label: is present
            search_query = query
            if Config.GMAIL_DEFAULT_LABEL and "label:" not in (query or ""):
                search_query = f"label:{Config.GMAIL_DEFAULT_LABEL} {query}" if query else f"label:{Config.GMAIL_DEFAULT_LABEL}"

            # Execute advanced search
            results_response = self.gmail_client.service.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=limit
            ).execute()
            
            messages = results_response.get('messages', [])
            
            if not messages:
                return f"No emails found matching query: {query}"
            
            # Get full details for each message
            results = [f"📧 Found {len(messages)} emails matching '{query}':\n"]
            
            for msg_ref in messages[:limit]:
                try:
                    msg = self.gmail_client.service.users().messages().get(
                        userId='me',
                        id=msg_ref['id'],
                        format='full'
                    ).execute()
                    
                    headers = msg['payload']['headers']
                    subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
                    from_addr = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
                    date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')

                    # Enforce read-domain filter if configured
                    if not self._is_sender_allowed_for_read(from_addr):
                        continue

                    # Get snippet or body preview
                    snippet = msg.get('snippet', 'No preview')
                    
                    results.append(
                        f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"ID: {msg_ref['id']}\n"
                        f"From: {from_addr}\n"
                        f"Date: {date}\n"
                        f"Subject: {subject}\n"
                        f"Preview: {snippet[:200]}...\n"
                    )
                except Exception as e:
                    logger.error(f"Error getting message: {e}")
                    continue
            
            return "\n".join(results)
        except Exception as e:
            logger.error(f"Error in advanced search: {e}")
            return f"❌ Error: {str(e)}"
    
    def upload_file_to_slack(self, channel: str, file_content: str, filename: str, title: str = None) -> str:
        """Upload a file to Slack channel.
        
        Args:
            channel: Channel ID
            file_content: File content or path to file
            filename: Name for the file
            title: Optional title
            
        Returns:
            Success/error message
        """
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            err = self._check_slack_write_allowed(channel)
            if err:
                return f"❌ {err}"
            
            # Check if file_content is a path
            if os.path.exists(file_content):
                # Upload from file path
                result = self.slack_client.files_upload_v2(
                    channel=channel,
                    file=file_content,
                    filename=filename,
                    title=title or filename
                )
            else:
                # Upload from content
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=f"_{filename}") as tmp:
                    tmp.write(file_content)
                    tmp_path = tmp.name
                
                result = self.slack_client.files_upload_v2(
                    channel=channel,
                    file=tmp_path,
                    filename=filename,
                    title=title or filename
                )
                os.unlink(tmp_path)
            
            return f"✅ File '{filename}' uploaded to Slack"
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return f"❌ Error: {str(e)}"
    
    def pin_slack_message(self, channel: str, timestamp: str) -> str:
        """Pin a message in Slack channel.
        
        Args:
            channel: Channel ID
            timestamp: Message timestamp
            
        Returns:
            Success/error message
        """
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            
            self.slack_client.pins_add(channel=channel, timestamp=timestamp)
            return "✅ Message pinned successfully"
        except Exception as e:
            logger.error(f"Error pinning message: {e}")
            return f"❌ Error: {str(e)}"
    
    def unpin_slack_message(self, channel: str, timestamp: str) -> str:
        """Unpin a message from Slack channel."""
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            
            self.slack_client.pins_remove(channel=channel, timestamp=timestamp)
            return "✅ Message unpinned successfully"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def get_pinned_messages(self, channel: str) -> str:
        """Get all pinned messages in a channel."""
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            
            result = self.slack_client.pins_list(channel=channel)
            items = result.get('items', [])
            
            if not items:
                return "No pinned messages in this channel"
            
            messages = []
            for item in items:
                if 'message' in item:
                    msg = item['message']
                    messages.append(f"📌 {msg.get('text', 'No text')[:150]}")
            
            return "\n\n".join(messages) if messages else "No pinned messages"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def create_slack_channel(self, name: str, is_private: bool = False) -> str:
        """Create a new Slack channel.
        
        Args:
            name: Channel name (lowercase, no spaces)
            is_private: Create as private channel
            
        Returns:
            Success message with channel ID
        """
        try:
            if not self.slack_client:
                return "❌ Slack not configured"

            err = self._check_slack_write_allowed(name)
            if err:
                return f"❌ {err}"

            result = self.slack_client.conversations_create(
                name=name,
                is_private=is_private
            )
            
            channel = result['channel']
            privacy = "private" if is_private else "public"
            return f"✅ Created {privacy} channel #{channel['name']} (ID: {channel['id']})"
        except Exception as e:
            logger.error(f"Error creating channel: {e}")
            return f"❌ Error: {str(e)}"
    
    def archive_slack_channel(self, channel: str) -> str:
        """Archive a Slack channel."""
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            err = self._check_slack_write_allowed(channel)
            if err:
                return f"❌ {err}"
            
            self.slack_client.conversations_archive(channel=channel)
            return f"✅ Channel archived successfully"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def invite_to_slack_channel(self, channel: str, users: str) -> str:
        """Invite users to a Slack channel.
        
        Args:
            channel: Channel ID
            users: Comma-separated user IDs
            
        Returns:
            Success/error message
        """
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            
            self.slack_client.conversations_invite(
                channel=channel,
                users=users
            )
            return f"✅ Users invited to channel"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def update_slack_message(self, channel: str, timestamp: str, text: str) -> str:
        """Update/edit a Slack message.
        
        Args:
            channel: Channel ID
            timestamp: Message timestamp
            text: New message text
            
        Returns:
            Success/error message
        """
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            
            self.slack_client.chat_update(
                channel=channel,
                ts=timestamp,
                text=text
            )
            return "✅ Message updated successfully"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def delete_slack_message(self, channel: str, timestamp: str) -> str:
        """Delete a Slack message."""
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            
            self.slack_client.chat_delete(channel=channel, ts=timestamp)
            return "✅ Message deleted successfully"
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def list_all_slack_users(self) -> str:
        """List all users in the Slack workspace."""
        try:
            if not self.slack_client:
                return "❌ Slack not configured"
            
            result = self.slack_client.users_list()
            users = result.get('members', [])
            
            active_users = []
            for user in users:
                if not user.get('deleted') and not user.get('is_bot'):
                    name = user.get('real_name', user.get('name'))
                    email = user.get('profile', {}).get('email', 'No email')
                    active_users.append(f"- {name} (@{user['name']}) - {email} - ID: {user['id']}")
            
            return f"👥 Workspace users ({len(active_users)}):\n" + "\n".join(active_users)
        except Exception as e:
            return f"❌ Error: {str(e)}"
    
    def append_to_notion_page(self, page_id: str, content: str) -> str:
        """Append content to existing Notion page.
        
        Args:
            page_id: Page ID to append to
            content: Content to append
            
        Returns:
            Success/error message
        """
        try:
            import requests
            
            # Create paragraph blocks from content
            paragraphs = content.split('\n\n')
            blocks = []
            for para in paragraphs:
                if para.strip():
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "type": "text",
                                "text": {"content": para.strip()}
                            }]
                        }
                    })
            
            response = requests.patch(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json"
                },
                json={"children": blocks}
            )
            
            if response.status_code == 200:
                return f"✅ Content appended to Notion page"
            else:
                return f"❌ Error {response.status_code}: {response.text}"
        except Exception as e:
            logger.error(f"Error appending to page: {e}")
            return f"❌ Error: {str(e)}"
    
    def search_notion_workspace(self, query: str) -> str:
        """Search across entire Notion workspace.
        
        Args:
            query: Search query
        
        Returns:
            Matching pages and databases
        """
        try:
            import requests
            
            payload: Dict[str, Any] = {
                "page_size": 50,
                # No filter here so we see both pages and databases that are
                # shared with the integration across the workspace.
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            }

            if query:
                payload["query"] = query

            response = requests.post(
                "https://api.notion.com/v1/search",
                headers={
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json=payload,
            )

            if response.status_code != 200:
                return f"❌ Error {response.status_code}"
            
            raw_results = response.json().get("results", []) or []

            # Only keep actual pages and databases
            results = [r for r in raw_results if r.get("object") in ("page", "database")]

            if not results:
                return f"No Notion pages or databases found matching '{query}'"

            def _title_from_result(obj: Dict[str, Any]) -> str:
                # Try title property first (works for most pages/databases)
                properties = obj.get("properties", {}) or {}
                for prop in properties.values():
                    if prop.get("type") == "title":
                        title_parts = prop.get("title", []) or []
                        texts: List[str] = []
                        for part in title_parts:
                            text_obj = part.get("plain_text") or part.get("text", {}).get("content")
                            if text_obj:
                                texts.append(text_obj)
                        if texts:
                            return "".join(texts)

                # Fallback for database objects which expose their title at the top level
                top_title = obj.get("title")
                if isinstance(top_title, list):
                    texts: List[str] = []
                    for part in top_title:
                        if not isinstance(part, dict):
                            continue
                        text_obj = part.get("plain_text") or part.get("text", {}).get("content")
                        if text_obj:
                            texts.append(text_obj)
                    if texts:
                        return "".join(texts)

                return "Untitled"

            lines = []
            for item in results[:10]:
                title = _title_from_result(item)
                obj_type = item.get("object")
                emoji = "📄" if obj_type == "page" else "📚"  # simple hint for databases
                lines.append(f"{emoji} {title} (ID: {item.get('id')})")

            return f"🔍 Found {len(results)} items:\n" + "\n".join(lines)
        except Exception as e:
            logger.error(f"Error searching Notion: {e}")
            return f"❌ Error: {str(e)}"
    
    # ========================================
    # PROJECT TRACKING - Cross-Platform Aggregation
    # ========================================
    
    async def track_project(
        self,
        project_name: str,
        days_back: int = 7,
        notion_page_id: Optional[str] = None,
        gmail_account_email: Optional[str] = None,
    ) -> str:
        """Track a project across Slack, Gmail, and Notion.
        
        This is a powerful cross-platform aggregation tool that:
        - Gathers updates from Slack conversations
        - Collects relevant email threads from Gmail
        - Pulls information from Notion pages
        - Analyzes all sources to identify key points, action items, and blockers
        - Calculates project progress
        
        Args:
            project_name: Name of the project to track (e.g., "Q4 Dashboard", "Agent Project")
            days_back: Number of days of history to include (default: 7)
            notion_page_id: Optional Notion page ID to associate with project
            
        Returns:
            Comprehensive project status summary
        """
        if not self.project_tracker:
            return "❌ Project Tracker not available"
        
        try:
            logger.info(
                "Tracking project: %s [gmail_account=%s]",
                project_name,
                gmail_account_email or "<any>",
            )
            status = await self.project_tracker.track_project(
                project_name=project_name,
                days_back=days_back,
                notion_page_id=notion_page_id,
                gmail_account_email=gmail_account_email,
            )
            
            # Format response
            summary = f"""
📊 **Project: {status.project_name}**
🕐 Last Updated: {status.last_updated.strftime("%Y-%m-%d %H:%M")}
📈 Progress: {status.progress_percentage}%

**Updates Summary:**
- Slack: {len(status.slack_updates)} messages
- Gmail: {len(status.gmail_updates)} threads
- Notion: {len(status.notion_updates)} pages
- Total: {len(status.slack_updates) + len(status.gmail_updates) + len(status.notion_updates)} updates

**✅ Key Highlights:**
{chr(10).join(f"• {point}" for point in status.key_points[:5])}

**📋 Action Items:**
{chr(10).join(f"• {item}" for item in status.action_items[:5])}

**⚠️ Blockers:**
{chr(10).join(f"• {blocker}" for blocker in status.blockers[:3]) if status.blockers else "None identified"}

**👥 Team Members:**
{', '.join(status.team_members[:10])}
"""
            return summary
        
        except Exception as e:
            logger.error(f"Error tracking project: {e}")
            return f"❌ Error tracking project: {str(e)}"
    
    async def generate_project_report(
        self,
        project_name: str,
        days_back: int = 7,
        gmail_account_email: Optional[str] = None,
    ) -> str:
        """Generate a comprehensive formatted project report.
        
        Creates a detailed, formatted report suitable for sharing with stakeholders.
        Includes progress bars, statistics, and organized sections for all updates.
        
        Args:
            project_name: Name of the project
            days_back: Number of days to include (default: 7)
            
        Returns:
            Formatted project report
        """
        if not self.project_tracker:
            return "❌ Project Tracker not available"
        
        try:
            logger.info(
                "Generating report for: %s [gmail_account=%s]",
                project_name,
                gmail_account_email or "<any>",
            )
            report = await self.project_tracker.generate_report(
                project_name=project_name,
                days_back=days_back,
                gmail_account_email=gmail_account_email,
            )
            return report
        
        except Exception as e:
            logger.error(f"Error generating report: {e}")
            return f"❌ Error generating report: {str(e)}"
    
    async def update_project_notion_page(
        self,
        page_id: str,
        project_name: str,
        days_back: int = 7,
        gmail_account_email: Optional[str] = None,
    ) -> str:
        """Update existing Notion page with current project status.
        
        IMPORTANT: This UPDATES an existing Notion page, it does NOT create a new one.
        The page must already exist and be shared with your Notion integration.
        
        This method:
        1. Tracks the project across all platforms
        2. Formats the status update
        3. Appends it to the specified Notion page
        
        Args:
            page_id: ID of the existing Notion page to update
            project_name: Name of the project
            days_back: Days of history to include (default: 7)
            
        Returns:
            Success message or error
        """
        if not self.project_tracker:
            return "❌ Project Tracker not available"
        
        try:
            logger.info(
                "Updating Notion page %s for project %s [gmail_account=%s]",
                page_id,
                project_name,
                gmail_account_email or "<any>",
            )
            
            # Track the project
            status = await self.project_tracker.track_project(
                project_name=project_name,
                days_back=days_back,
                gmail_account_email=gmail_account_email,
            )
            
            # Update Notion page
            result = await self.project_tracker.update_notion_page(
                page_id=page_id,
                project_status=status
            )
            
            return f"✅ Notion page updated successfully!\n\n{result}"
        
        except Exception as e:
            logger.error(f"Error updating Notion page: {e}")
            return f"❌ Error: {str(e)}"
    
    # ========================================
    # UTILITY TOOLS - Cross-Platform & Analytics
    # ========================================
    
    async def search_all_platforms(
        self,
        query: str,
        limit_per_platform: int = 10,
        gmail_account_email: Optional[str] = None,
    ) -> str:
        """Search across all platforms simultaneously.
        
        Args:
            query: Search query
            limit_per_platform: Max results per platform
            
        Returns:
            Unified search results from all platforms
        """
        logger.info(f"Searching all platforms for: {query}")
        
        results = []
        
        # Search Slack
        try:
            slack_results = self.search_slack_messages(query, limit=limit_per_platform)
            results.append(f"## 💬 SLACK RESULTS\n{slack_results}\n")
        except Exception as e:
            results.append(f"## 💬 SLACK RESULTS\n❌ Error: {e}\n")
        
        # Search Gmail (scoped to a single Gmail account when provided)
        try:
            gmail_results = self.search_gmail_messages(
                query,
                limit=limit_per_platform,
                gmail_account_email=gmail_account_email,
            )
            results.append(f"## 📧 GMAIL RESULTS\n{gmail_results}\n")
        except Exception as e:
            results.append(f"## 📧 GMAIL RESULTS\n❌ Error: {e}\n")
        
        # Search Notion
        try:
            notion_results = self.search_notion_workspace(query)
            results.append(f"## 📄 NOTION RESULTS\n{notion_results}\n")
        except Exception as e:
            results.append(f"## 📄 NOTION RESULTS\n❌ Error: {e}\n")
        
        summary = f"""
🔍 **CROSS-PLATFORM SEARCH: "{query}"**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{chr(10).join(results)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Search complete across all platforms
"""
        return summary
    
    async def get_team_activity_summary(
        self,
        person_name: str,
        days_back: int = 7,
        gmail_account_email: Optional[str] = None,
    ) -> str:
        """Get activity summary for a team member.
        
        Args:
            person_name: Name or email of the person
            days_back: Days of history to include
            
        Returns:
            Activity summary across all platforms
        """
        logger.info(f"Getting activity summary for: {person_name}")
        
        activities = []
        
        # Search Slack for person's messages
        try:
            slack_query = f"from:@{person_name}"
            slack_results = self.search_slack_messages(slack_query, limit=20)
            if "Found" in slack_results:
                message_count = slack_results.count('\n')
                activities.append(f"💬 **Slack:** {message_count} messages found")
                activities.append(slack_results[:500] + "...\n")
            else:
                activities.append(f"💬 **Slack:** No messages found\n")
        except Exception as e:
            activities.append(f"💬 **Slack:** Error - {e}\n")
        
        # Search Gmail for person's emails
        try:
            gmail_query = f"from:{person_name}"
            gmail_results = self.search_gmail_messages(
                gmail_query,
                limit=20,
                gmail_account_email=gmail_account_email,
            )
            if "emails found" in gmail_results.lower():
                email_count = gmail_results.count('Subject:')
                activities.append(f"📧 **Gmail:** {email_count} emails found")
                activities.append(gmail_results[:500] + "...\n")
            else:
                activities.append(f"📧 **Gmail:** No emails found\n")
        except Exception as e:
            activities.append(f"📧 **Gmail:** Error - {e}\n")
        
        # Search Notion for person's updates
        try:
            notion_results = self.search_notion_workspace(person_name)
            if "Found" in notion_results:
                page_count = notion_results.count('📄')
                activities.append(f"📄 **Notion:** {page_count} pages found")
                activities.append(notion_results[:300] + "...\n")
            else:
                activities.append(f"📄 **Notion:** No pages found\n")
        except Exception as e:
            activities.append(f"📄 **Notion:** Error - {e}\n")
        
        summary = f"""
👤 **TEAM MEMBER ACTIVITY: {person_name}**
📅 Period: Last {days_back} days
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{chr(10).join(activities)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Activity summary complete
"""
        return summary
    
    async def analyze_slack_channel(
        self,
        channel: str,
        days_back: int = 7
    ) -> str:
        """Analyze Slack channel activity and engagement.
        
        Args:
            channel: Channel name or ID
            days_back: Days to analyze
            
        Returns:
            Channel analytics and insights
        """
        logger.info(f"Analyzing Slack channel: {channel}")
        
        try:
            # Get channel messages
            messages_result = self.get_channel_messages(channel, limit=100)
            
            if "Error" in messages_result or "not found" in messages_result.lower():
                return f"❌ Could not analyze channel '{channel}': {messages_result}"
            
            # Parse messages for analytics
            lines = messages_result.split('\n')
            message_count = len([l for l in lines if l.strip()])
            
            # Count unique users
            users = set()
            for line in lines:
                if ']' in line and ':' in line:
                    try:
                        user = line.split(']')[1].split(':')[0].strip()
                        users.add(user)
                    except:
                        pass
            
            # Basic sentiment analysis (simple keyword counting)
            positive_keywords = ['great', 'good', 'excellent', 'thanks', 'awesome', 'perfect', 'done', 'completed']
            negative_keywords = ['issue', 'problem', 'error', 'bug', 'blocked', 'stuck', 'failed']
            question_keywords = ['?', 'how', 'what', 'when', 'why', 'where']
            
            positive_count = sum(1 for line in lines for kw in positive_keywords if kw in line.lower())
            negative_count = sum(1 for line in lines for kw in negative_keywords if kw in line.lower())
            question_count = sum(1 for line in lines for kw in question_keywords if kw in line.lower())
            
            # Calculate engagement metrics
            avg_messages_per_user = message_count / len(users) if users else 0
            
            analysis = f"""
📊 **SLACK CHANNEL ANALYSIS: #{channel}**
📅 Period: Last {days_back} days
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📈 Activity Metrics:**
• Total Messages: {message_count}
• Active Users: {len(users)}
• Avg Messages/User: {avg_messages_per_user:.1f}

**👥 Most Active Users:**
{chr(10).join(f'• {user}' for user in list(users)[:10])}

**💬 Message Patterns:**
• Positive Mentions: {positive_count} (great, good, thanks, done, etc.)
• Issues/Blockers: {negative_count} (problem, error, blocked, etc.)
• Questions Asked: {question_count}

**📊 Engagement Level:**
{self._generate_engagement_bar(message_count, len(users))}

**🔍 Recent Activity Sample:**
{chr(10).join(lines[:5])}
...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Channel analysis complete
"""
            return analysis
        
        except Exception as e:
            logger.error(f"Error analyzing channel: {e}")
            return f"❌ Error analyzing channel: {str(e)}"
    
    def _generate_engagement_bar(self, message_count: int, user_count: int) -> str:
        """Generate visual engagement bar."""
        if message_count < 10:
            level = "Low"
            bar = "█░░░░░░░░░"
        elif message_count < 50:
            level = "Medium"
            bar = "████░░░░░░"
        elif message_count < 100:
            level = "High"
            bar = "███████░░░"
        else:
            level = "Very High"
            bar = "██████████"
        
        return f"{level}: {bar} ({message_count} messages, {user_count} users)"

    # ========================================================================
    # GOOGLE CALENDAR TOOLS
    # ========================================================================

    def _get_calendar_service(self):
        """Get Google Calendar service using user's OAuth credentials."""
        if not self.user_id:
            return None
        
        try:
            from googleapiclient.discovery import build
            from database.models import UserOAuthToken
            
            with self.db.get_session() as session:
                token = session.query(UserOAuthToken).filter_by(
                    user_id=self.user_id, provider="google"
                ).first()
                
                if not token or not token.access_token:
                    return None
                
                creds = Credentials(
                    token=token.access_token,
                    refresh_token=token.refresh_token,
                    token_uri="https://oauth2.googleapis.com/token",
                    client_id=Config.GOOGLE_CLIENT_ID,
                    client_secret=Config.GOOGLE_CLIENT_SECRET,
                    scopes=token.scope.split() if token.scope else ["https://www.googleapis.com/auth/calendar"]
                )
                
                # Refresh if expired
                if creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(google_requests.Request())
                        token.access_token = creds.token
                        if creds.refresh_token:
                            token.refresh_token = creds.refresh_token
                        session.commit()
                    except RefreshError:
                        logger.warning("Failed to refresh Calendar credentials")
                        return None
                
                return build("calendar", "v3", credentials=creds)
        except Exception as e:
            logger.error(f"Error getting Calendar service: {e}")
            return None

    def list_calendar_events(self, days: int = 7, max_results: int = 20) -> str:
        """List upcoming calendar events.
        
        Args:
            days: Number of days to look ahead
            max_results: Maximum number of events to return
            
        Returns:
            Formatted string of calendar events
        """
        try:
            service = self._get_calendar_service()
            if not service:
                return "❌ Google Calendar not authenticated. Please sign in with Google."
            
            now = datetime.utcnow()
            time_min = now.isoformat() + "Z"
            time_max = (now + timedelta(days=days)).isoformat() + "Z"
            
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            
            events = events_result.get("items", [])
            
            if not events:
                return f"📅 No upcoming events in the next {days} days."
            
            result = [f"📅 **Upcoming Events (next {days} days)**\n"]
            
            for event in events:
                start = event.get("start", {})
                start_time = start.get("dateTime", start.get("date", ""))
                summary = event.get("summary", "Untitled")
                location = event.get("location", "")
                event_id = event.get("id", "")
                
                # Format the time
                if "T" in start_time:
                    dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                    formatted_time = dt.strftime("%b %d, %Y at %I:%M %p")
                else:
                    formatted_time = start_time  # All-day event
                
                entry = f"• **{summary}** - {formatted_time}"
                if location:
                    entry += f" 📍 {location}"
                entry += f"\n  ID: `{event_id}`"
                result.append(entry)
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Error listing calendar events: {e}")
            return f"❌ Error listing calendar events: {str(e)}"

    def create_calendar_event(
        self,
        summary: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[str] = None
    ) -> str:
        """Create a new calendar event.
        
        Args:
            summary: Event title
            start_time: Start time in ISO format
            end_time: End time in ISO format
            description: Event description
            location: Event location
            attendees: Comma-separated attendee emails
            
        Returns:
            Success message with event details
        """
        try:
            service = self._get_calendar_service()
            if not service:
                return "❌ Google Calendar not authenticated. Please sign in with Google."
            
            # Parse times - handle both ISO and simple formats
            def parse_time(time_str: str) -> str:
                time_str = time_str.strip()
                # If already has timezone info, return as-is
                if "Z" in time_str or "+" in time_str or "-" in time_str[-6:]:
                    return time_str
                # Assume local time, add Z for UTC
                if "T" not in time_str:
                    time_str = time_str + "T00:00:00"
                return time_str
            
            event_body = {
                "summary": summary,
                "start": {"dateTime": parse_time(start_time), "timeZone": "UTC"},
                "end": {"dateTime": parse_time(end_time), "timeZone": "UTC"},
            }
            
            if description:
                event_body["description"] = description
            if location:
                event_body["location"] = location
            if attendees:
                attendee_list = [{"email": e.strip()} for e in attendees.split(",") if e.strip()]
                if attendee_list:
                    event_body["attendees"] = attendee_list
            
            event = service.events().insert(calendarId="primary", body=event_body).execute()
            
            return f"""✅ **Calendar Event Created**
• **Title:** {summary}
• **Start:** {start_time}
• **End:** {end_time}
• **Event ID:** `{event.get('id')}`
• **Link:** {event.get('htmlLink', 'N/A')}"""
            
        except Exception as e:
            logger.error(f"Error creating calendar event: {e}")
            return f"❌ Error creating calendar event: {str(e)}"

    def update_calendar_event(
        self,
        event_id: str,
        summary: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        description: Optional[str] = None,
        location: Optional[str] = None
    ) -> str:
        """Update an existing calendar event.
        
        Args:
            event_id: Google Calendar event ID
            summary: New title (optional)
            start_time: New start time (optional)
            end_time: New end time (optional)
            description: New description (optional)
            location: New location (optional)
            
        Returns:
            Success message with updated event details
        """
        try:
            service = self._get_calendar_service()
            if not service:
                return "❌ Google Calendar not authenticated. Please sign in with Google."
            
            event_id = (event_id or "").strip()
            if not event_id:
                return "❌ Event ID is required"
            
            # Get existing event
            try:
                event = service.events().get(calendarId="primary", eventId=event_id).execute()
            except Exception:
                return f"❌ Event not found with ID: {event_id}"
            
            # Update fields
            if summary:
                event["summary"] = summary
            if description is not None:
                event["description"] = description
            if location is not None:
                event["location"] = location
            if start_time:
                event["start"] = {"dateTime": start_time, "timeZone": "UTC"}
            if end_time:
                event["end"] = {"dateTime": end_time, "timeZone": "UTC"}
            
            updated_event = service.events().update(
                calendarId="primary", eventId=event_id, body=event
            ).execute()
            
            return f"""✅ **Calendar Event Updated**
• **Title:** {updated_event.get('summary', 'N/A')}
• **Event ID:** `{event_id}`
• **Link:** {updated_event.get('htmlLink', 'N/A')}"""
            
        except Exception as e:
            logger.error(f"Error updating calendar event: {e}")
            return f"❌ Error updating calendar event: {str(e)}"

    def delete_calendar_event(self, event_id: str) -> str:
        """Delete a calendar event.
        
        Args:
            event_id: Google Calendar event ID to delete
            
        Returns:
            Success or error message
        """
        try:
            service = self._get_calendar_service()
            if not service:
                return "❌ Google Calendar not authenticated. Please sign in with Google."
            
            event_id = (event_id or "").strip()
            if not event_id:
                return "❌ Event ID is required"
            
            # Get event details before deleting
            try:
                event = service.events().get(calendarId="primary", eventId=event_id).execute()
                summary = event.get("summary", "Untitled")
            except Exception:
                return f"❌ Event not found with ID: {event_id}"
            
            service.events().delete(calendarId="primary", eventId=event_id).execute()
            
            return f"✅ **Calendar event deleted:** {summary} (ID: `{event_id}`)"
            
        except Exception as e:
            logger.error(f"Error deleting calendar event: {e}")
            return f"❌ Error deleting calendar event: {str(e)}"

    def check_calendar_availability(self, start_time: str, end_time: str) -> str:
        """Check calendar availability for a time range.
        
        Args:
            start_time: Start of time range (ISO format)
            end_time: End of time range (ISO format)
            
        Returns:
            Availability status and any conflicting events
        """
        try:
            service = self._get_calendar_service()
            if not service:
                return "❌ Google Calendar not authenticated. Please sign in with Google."
            
            # Query events in the time range
            events_result = service.events().list(
                calendarId="primary",
                timeMin=start_time if "Z" in start_time else start_time + "Z",
                timeMax=end_time if "Z" in end_time else end_time + "Z",
                singleEvents=True,
                orderBy="startTime"
            ).execute()
            
            events = events_result.get("items", [])
            
            if not events:
                return f"""✅ **You're available!**
• Time range: {start_time} to {end_time}
• No conflicting events found."""
            
            result = [f"⚠️ **Conflicts found** ({len(events)} event(s)):\n"]
            for event in events:
                start = event.get("start", {})
                start_dt = start.get("dateTime", start.get("date", ""))
                summary = event.get("summary", "Untitled")
                result.append(f"• **{summary}** at {start_dt}")
            
            return "\n".join(result)
            
        except Exception as e:
            logger.error(f"Error checking calendar availability: {e}")
            return f"❌ Error checking availability: {str(e)}"
    
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
            # Calendar tools
            StructuredTool(
                name="list_calendar_events",
                description="List upcoming Google Calendar events. Use this when user asks about their schedule, upcoming meetings, or calendar.",
                func=self.list_calendar_events,
                args_schema=ListCalendarEventsInput
            ),
            StructuredTool(
                name="create_calendar_event",
                description="Create a new Google Calendar event. Use this when user asks to schedule a meeting, add an event, or create a calendar entry.",
                func=self.create_calendar_event,
                args_schema=CreateCalendarEventInput
            ),
            StructuredTool(
                name="update_calendar_event",
                description="Update an existing Google Calendar event. Use this when user asks to modify, reschedule, or change a calendar event.",
                func=self.update_calendar_event,
                args_schema=UpdateCalendarEventInput
            ),
            StructuredTool(
                name="delete_calendar_event",
                description="Delete a Google Calendar event. Use this when user asks to remove, cancel, or delete a calendar event.",
                func=self.delete_calendar_event,
                args_schema=DeleteCalendarEventInput
            ),
            StructuredTool(
                name="check_calendar_availability",
                description="Check if a time slot is available on Google Calendar. Use this when user asks about availability or free time.",
                func=self.check_calendar_availability,
                args_schema=CheckCalendarAvailabilityInput
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
