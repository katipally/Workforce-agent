"""Export complete database to Notion."""

from datetime import datetime
from typing import Optional
from rich.console import Console

from .client import NotionClient
from database.db_manager import DatabaseManager
from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class FullDatabaseExporter:
    """Export entire database (Slack + Gmail) to Notion."""
    
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
    
    def export_all(self) -> Optional[str]:
        """Export all database tables to a single Notion page.
        
        Returns:
            Created page ID or None
        """
        logger.info("Exporting entire database to Notion...")
        
        if not self.parent_page_id:
            logger.error("NOTION_PARENT_PAGE_ID not configured")
            return None
        
        # Get all statistics
        slack_stats = self.db.get_statistics()
        gmail_stats = self.db.get_gmail_statistics()
        
        # Create page title
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        title = f"Complete Database Export - {timestamp}"
        
        # Build blocks
        blocks = []
        
        # Overview
        blocks.append(self.notion.create_heading("🗄️ Database Overview", 1))
        blocks.append(self.notion.create_paragraph(
            f"Complete export of all data from Workforce Agent. Exported on {timestamp}."
        ))
        blocks.append(self.notion.create_divider())
        
        # Slack section
        blocks.append(self.notion.create_heading("💬 Slack Data", 2))
        blocks.append(self.notion.create_bulleted_list_item(f"Users: {slack_stats.get('users', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Channels: {slack_stats.get('channels', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Messages: {slack_stats.get('messages', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Files: {slack_stats.get('files', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Reactions: {slack_stats.get('reactions', 0)}"))
        blocks.append(self.notion.create_divider())
        
        # Gmail section
        blocks.append(self.notion.create_heading("📧 Gmail Data", 2))
        blocks.append(self.notion.create_bulleted_list_item(f"Accounts: {gmail_stats.get('accounts', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Labels: {gmail_stats.get('labels', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Messages: {gmail_stats.get('messages', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Threads: {gmail_stats.get('threads', 0)}"))
        blocks.append(self.notion.create_bulleted_list_item(f"Attachments: {gmail_stats.get('attachments', 0)}"))
        blocks.append(self.notion.create_divider())
        
        # Recent activity
        blocks.append(self.notion.create_heading("📊 Recent Activity", 2))
        
        # Recent Slack messages
        blocks.append(self.notion.create_heading("Recent Slack Messages", 3))
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
                text = (msg.text or "")[:100]
                blocks.append(
                    self.notion.create_paragraph(
                        f"[{timestamp_str}] {msg.user.name} in #{msg.channel.name}: {text}"
                    )
                )
        
        blocks.append(self.notion.create_divider())
        
        # Recent Gmail messages
        blocks.append(self.notion.create_heading("Recent Gmail Messages", 3))
        with self.db.get_session() as session:
            from database.models import GmailMessage
            emails = session.query(GmailMessage)\
                .order_by(GmailMessage.date.desc())\
                .limit(10)\
                .all()
            
            for email in emails:
                date_str = email.date.strftime("%Y-%m-%d %H:%M") if email.date else "N/A"
                from_addr = email.from_address or "Unknown"
                subject = (email.subject or "No Subject")[:80]
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
            logger.info(f"Successfully exported all data to Notion page: {page_id}")
            console.print(f"[green]✓ Exported all data to Notion page: {page_id}[/green]")
        
        return page_id
