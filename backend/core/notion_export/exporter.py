"""Export Slack data to Notion."""

from datetime import datetime
from typing import List, Dict, Any, Optional
from rich.console import Console

from .client import NotionClient
from database.db_manager import DatabaseManager
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class NotionExporter:
    """Export Slack data to Notion pages."""
    
    def __init__(
        self,
        notion_client: NotionClient = None,
        db_manager: DatabaseManager = None,
        parent_page_id: str = None
    ):
        """Initialize exporter.
        
        Args:
            notion_client: Notion API client
            db_manager: Database manager
            parent_page_id: Parent Notion page ID
        """
        self.notion = notion_client or NotionClient()
        self.db = db_manager or DatabaseManager()
        self.parent_page_id = parent_page_id or Config.NOTION_PARENT_PAGE_ID
    
    def export_slack_data(self) -> Optional[str]:
        """Export all Slack data to a Notion page.
        
        Returns:
            Created page ID or None
        """
        logger.info("Exporting Slack data to Notion...")
        
        if not self.parent_page_id:
            logger.error("NOTION_PARENT_PAGE_ID not configured")
            return None
        
        # Get statistics
        stats = self.db.get_statistics()
        
        # Create page title
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = f"Slack Export - {timestamp}"
        
        # Build blocks
        blocks = []
        
        # Statistics section
        blocks.append(self.notion.create_heading("📊 Statistics", 2))
        blocks.append(self.notion.create_bulleted_list_item(f"Users: {stats.get('users', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Channels: {stats.get('channels', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Messages: {stats.get('messages', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Files: {stats.get('files', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Reactions: {stats.get('reactions', 0)}"))
        blocks.append(self.notion.create_divider())
        
        # Channels section
        blocks.append(self.notion.create_heading("💬 Channels", 2))
        channels = self.db.get_all_channels()[:20]  # Limit to 20
        for channel in channels:
            channel_type = "🔒" if channel.is_private else "📢"
            blocks.append(
                self.notion.create_bulleted_list_item(
                    f"{channel_type} {channel.name} ({channel.num_members or 0} members)"
                )
            )
        blocks.append(self.notion.create_divider())
        
        # Recent messages section
        blocks.append(self.notion.create_heading("📝 Recent Messages", 2))
        with self.db.get_session() as session:
            from database.models import Message, Channel, User
            messages = session.query(Message)\
                .join(Channel)\
                .join(User)\
                .order_by(Message.timestamp.desc())\
                .limit(10)\
                .all()
            
            for msg in messages:
                timestamp_str = datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d %H:%M")
                text = (msg.text or "")[:100]  # Truncate
                blocks.append(
                    self.notion.create_paragraph(
                        f"[{timestamp_str}] {msg.user.name} in #{msg.channel.name}: {text}"
                    )
                )
        
        # Create page
        page_id = self.notion.create_page(
            parent_page_id=self.parent_page_id,
            title=title,
            children=blocks
        )
        
        if page_id:
            logger.info(f"Successfully exported Slack data to Notion page: {page_id}")
        
        return page_id
    
    def export_gmail_data(self) -> Optional[str]:
        """Export Gmail data to a Notion page.
        
        Returns:
            Created page ID or None
        """
        logger.info("Exporting Gmail data to Notion...")
        
        if not self.parent_page_id:
            logger.error("NOTION_PARENT_PAGE_ID not configured")
            return None
        
        # Get statistics
        gmail_stats = self.db.get_gmail_statistics()
        
        # Create page title
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = f"Gmail Export - {timestamp}"
        
        # Build blocks
        blocks = []
        
        # Statistics section
        blocks.append(self.notion.create_heading("📊 Gmail Statistics", 2))
        blocks.append(self.notion.create_bulleted_list_item(f"Accounts: {gmail_stats.get('accounts', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Labels: {gmail_stats.get('labels', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Messages: {gmail_stats.get('messages', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Threads: {gmail_stats.get('threads', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Attachments: {gmail_stats.get('attachments', 0)}"))
        blocks.append(self.notion.create_divider())
        
        # Recent emails section
        blocks.append(self.notion.create_heading("📧 Recent Emails", 2))
        with self.db.get_session() as session:
            from database.models import GmailMessage
            messages = session.query(GmailMessage)\
                .order_by(GmailMessage.date.desc())\
                .limit(10)\
                .all()
            
            for msg in messages:
                date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "N/A"
                from_addr = msg.from_address or "Unknown"
                subject = (msg.subject or "No Subject")[:80]
                blocks.append(
                    self.notion.create_paragraph(
                        f"[{date_str}] From: {from_addr} - {subject}"
                    )
                )
        
        # Create page
        page_id = self.notion.create_page(
            parent_page_id=self.parent_page_id,
            title=title,
            children=blocks
        )
        
        if page_id:
            logger.info(f"Successfully exported Gmail data to Notion page: {page_id}")
        
        return page_id
