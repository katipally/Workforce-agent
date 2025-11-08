"""Export Slack data from database to Notion."""

from datetime import datetime
from typing import List, Dict, Any
from database.db_manager import DatabaseManager
from .client import NotionClient
from utils.logger import get_logger
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

logger = get_logger(__name__)
console = Console()


class NotionExporter:
    """Export Slack data to Notion page."""
    
    def __init__(self, notion_token: str = None):
        """Initialize exporter.
        
        Args:
            notion_token: Notion integration token
        """
        self.db = DatabaseManager()
        self.notion = NotionClient(token=notion_token)
        logger.info("NotionExporter initialized")
    
    def export_all(self, parent_page_id: str) -> Dict[str, Any]:
        """Export all Slack data to a single Notion page.
        
        Args:
            parent_page_id: Notion page ID where export page will be created
            
        Returns:
            Created Notion page info
        """
        console.print("\n[bold blue]Starting Slack → Notion Export[/bold blue]")
        
        # Test connection first
        if not self.notion.test_connection():
            console.print("[bold red]✗ Notion connection failed![/bold red]")
            return None
        
        console.print("[green]✓ Notion connected[/green]")
        
        # Gather data from database
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            
            task = progress.add_task("Reading data from database...", total=None)
            
            stats = self.db.get_statistics()
            users = self.db.get_all_users()
            channels = self.db.get_all_channels()
            
            # Get sample messages (limit to avoid overwhelming)
            all_messages = []
            for channel in channels[:10]:  # Limit to first 10 channels
                messages = self.db.get_messages_by_channel(channel.channel_id, limit=50)
                all_messages.extend(messages)
            
            files = self.db.get_all_files()
            
            progress.update(task, description="[green]✓ Data loaded[/green]")
        
        console.print(f"\n[cyan]Found:[/cyan]")
        console.print(f"  • Users: {stats.get('users', 0)}")
        console.print(f"  • Channels: {stats.get('channels', 0)}")
        console.print(f"  • Messages: {stats.get('messages', 0)}")
        console.print(f"  • Files: {stats.get('files', 0)}")
        
        # Format blocks
        console.print("\n[yellow]Formatting data for Notion...[/yellow]")
        blocks = self._format_all_data(stats, users, channels, all_messages, files)
        
        console.print(f"[cyan]Created {len(blocks)} blocks[/cyan]")
        
        # Create page
        console.print("\n[yellow]Creating Notion page...[/yellow]")
        
        title = f"Slack Data Export - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        
        try:
            page = self.notion.create_page(
                parent_id=parent_page_id,
                title=title,
                blocks=blocks
            )
            
            page_url = page.get("url", "N/A")
            console.print(f"\n[bold green]✓ Export Complete![/bold green]")
            console.print(f"[cyan]Page URL:[/cyan] {page_url}")
            
            return page
        
        except Exception as e:
            console.print(f"\n[bold red]✗ Export failed: {e}[/bold red]")
            logger.error(f"Export failed: {e}")
            return None
    
    def _format_all_data(
        self, 
        stats: Dict[str, int],
        users: List[Any],
        channels: List[Any],
        messages: List[Any],
        files: List[Any]
    ) -> List[Dict[str, Any]]:
        """Format all data as Notion blocks.
        
        Args:
            stats: Statistics dictionary
            users: List of user objects
            channels: List of channel objects
            messages: List of message objects
            files: List of file objects
            
        Returns:
            List of Notion block objects
        """
        blocks = []
        
        # Header
        blocks.append(self._create_heading1("Slack Workspace Data Export"))
        blocks.append(self._create_callout(
            "📊",
            f"Exported on {datetime.now().strftime('%B %d, %Y at %I:%M %p')}"
        ))
        
        # Statistics
        blocks.append(self._create_heading2("📈 Statistics"))
        stats_text = (
            f"• Total Users: {stats.get('users', 0)}\n"
            f"• Total Channels: {stats.get('channels', 0)}\n"
            f"• Total Messages: {stats.get('messages', 0)}\n"
            f"• Total Files: {stats.get('files', 0)}\n"
            f"• Total Reactions: {stats.get('reactions', 0)}"
        )
        blocks.append(self._create_paragraph(stats_text))
        
        blocks.append(self._create_divider())
        
        # Users
        blocks.append(self._create_heading2("👥 Users"))
        for user in users[:50]:  # Limit to 50 users
            user_text = f"• {user.real_name or user.username} (@{user.username})"
            if user.email:
                user_text += f" - {user.email}"
            blocks.append(self._create_paragraph(user_text))
        
        if len(users) > 50:
            blocks.append(self._create_paragraph(f"... and {len(users) - 50} more users"))
        
        blocks.append(self._create_divider())
        
        # Channels
        blocks.append(self._create_heading2("📢 Channels"))
        for channel in channels[:50]:  # Limit to 50 channels
            channel_type = "🔒 Private" if channel.is_private else "🌐 Public"
            archived = " [Archived]" if channel.is_archived else ""
            blocks.append(self._create_paragraph(
                f"• #{channel.name} - {channel_type}{archived}"
            ))
        
        if len(channels) > 50:
            blocks.append(self._create_paragraph(f"... and {len(channels) - 50} more channels"))
        
        blocks.append(self._create_divider())
        
        # Messages (sample)
        blocks.append(self._create_heading2("💬 Messages (Sample)"))
        blocks.append(self._create_paragraph(
            f"Showing {len(messages)} recent messages from first 10 channels"
        ))
        
        for msg in messages[:100]:  # Limit to 100 messages
            # Format message text
            msg_text = msg.text or "[No text]"
            
            # Truncate if too long (Notion has 2000 char limit per rich text)
            if len(msg_text) > 1500:
                msg_text = msg_text[:1500] + "..."
            
            # Get username from user_id
            username = msg.user_id or "Unknown"
            
            # Format timestamp
            timestamp_str = datetime.fromtimestamp(msg.timestamp).strftime('%Y-%m-%d %H:%M')
            
            # Create quote block for message
            blocks.append(self._create_quote(
                f"💬 {username} at {timestamp_str}:\n{msg_text}"
            ))
        
        if len(messages) > 100:
            blocks.append(self._create_paragraph(
                f"... and {len(messages) - 100} more messages (showing sample only)"
            ))
        
        blocks.append(self._create_divider())
        
        # Files
        if files:
            blocks.append(self._create_heading2("📎 Files"))
            for file in files[:50]:  # Limit to 50 files
                file_text = f"• {file.name} ({file.filetype}) - {file.size} bytes"
                if file.url_private:
                    file_text += f"\n  URL: {file.url_private}"
                blocks.append(self._create_paragraph(file_text))
            
            if len(files) > 50:
                blocks.append(self._create_paragraph(f"... and {len(files) - 50} more files"))
        
        # Footer
        blocks.append(self._create_divider())
        blocks.append(self._create_paragraph(
            "🤖 Exported by Slack Workspace Agent"
        ))
        
        return blocks
    
    # Block creation helpers
    
    def _create_heading1(self, text: str) -> Dict[str, Any]:
        """Create heading 1 block."""
        return {
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"text": {"content": text[:2000]}}]
            }
        }
    
    def _create_heading2(self, text: str) -> Dict[str, Any]:
        """Create heading 2 block."""
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": text[:2000]}}]
            }
        }
    
    def _create_paragraph(self, text: str) -> Dict[str, Any]:
        """Create paragraph block."""
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": text[:2000]}}]
            }
        }
    
    def _create_callout(self, emoji: str, text: str) -> Dict[str, Any]:
        """Create callout block."""
        return {
            "object": "block",
            "type": "callout",
            "callout": {
                "icon": {"emoji": emoji},
                "rich_text": [{"text": {"content": text[:2000]}}]
            }
        }
    
    def _create_quote(self, text: str) -> Dict[str, Any]:
        """Create quote block."""
        return {
            "object": "block",
            "type": "quote",
            "quote": {
                "rich_text": [{"text": {"content": text[:2000]}}]
            }
        }
    
    def _create_divider(self) -> Dict[str, Any]:
        """Create divider block."""
        return {
            "object": "block",
            "type": "divider",
            "divider": {}
        }
