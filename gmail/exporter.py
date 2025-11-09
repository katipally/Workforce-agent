"""Export Gmail data to Notion."""

from datetime import datetime
from typing import List, Dict, Any
from rich.console import Console

from notion_export.client import NotionClient
from database.db_manager import DatabaseManager
from database.models import GmailAccount, GmailMessage, GmailThread, GmailLabel, GmailAttachment
from utils.logger import get_logger

logger = get_logger(__name__)
console = Console()


class GmailNotionExporter:
    """Export Gmail data to Notion pages."""
    
    def __init__(self, notion_token: str = None):
        """Initialize exporter.
        
        Args:
            notion_token: Notion integration token
        """
        self.db = DatabaseManager()
        self.notion = NotionClient(token=notion_token)
        logger.info("GmailNotionExporter initialized")
    
    def export_all(self, parent_page_id: str, max_emails: int = 50) -> Dict[str, Any]:
        """Export all Gmail data to a single Notion page.
        
        Args:
            parent_page_id: Notion page ID where export page will be created
            max_emails: Maximum number of emails to include in export
            
        Returns:
            Created Notion page info
        """
        console.print("\n[bold blue]Starting Gmail → Notion Export[/bold blue]")
        
        try:
            # Test connection
            if not self.notion.test_connection():
                console.print("[bold red]✗ Failed to connect to Notion[/bold red]")
                return {}
            console.print("[green]✓ Notion connected[/green]")
            
            # Load Gmail data from database
            console.print("\n[cyan]Loading Gmail data from database...[/cyan]")
            with self.db.get_session() as session:
                accounts = session.query(GmailAccount).all()
                labels = session.query(GmailLabel).all()
                threads = session.query(GmailThread).order_by(GmailThread.updated_at.desc()).limit(20).all()
                messages = session.query(GmailMessage).order_by(GmailMessage.date.desc()).limit(max_emails).all()
                attachments = session.query(GmailAttachment).all()
            
            console.print(f"\n[green]✓ Data loaded[/green]")
            console.print(f"\nFound:")
            console.print(f"  • Accounts: {len(accounts)}")
            console.print(f"  • Labels: {len(labels)}")
            console.print(f"  • Threads: {len(threads)}")
            console.print(f"  • Messages: {len(messages)}")
            console.print(f"  • Attachments: {len(attachments)}")
            
            # Format data for Notion
            console.print("\n[cyan]Formatting data for Notion...[/cyan]")
            blocks = self._format_all_data(accounts, labels, threads, messages, attachments)
            console.print(f"[green]Created {len(blocks)} blocks[/green]")
            
            # Create Notion page
            console.print("\n[cyan]Creating Notion page...[/cyan]")
            page_title = f"Gmail Data Export - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            
            page = self.notion.create_page(
                parent_id=parent_page_id,
                title=page_title,
                blocks=blocks[:100]  # Notion limit: 100 blocks per request
            )
            
            page_url = page.get('url', '')
            
            console.print(f"\n[bold green]✓ Export Complete![/bold green]")
            console.print(f"[cyan]Page URL:[/cyan] {page_url}")
            
            return page
        
        except Exception as e:
            console.print(f"\n[bold red]✗ Export failed: {e}[/bold red]")
            logger.error(f"Export failed: {e}", exc_info=True)
            return {}
    
    def _format_all_data(
        self,
        accounts: List[GmailAccount],
        labels: List[GmailLabel],
        threads: List[GmailThread],
        messages: List[GmailMessage],
        attachments: List[GmailAttachment]
    ) -> List[Dict[str, Any]]:
        """Format Gmail data as Notion blocks.
        
        Args:
            accounts: List of Gmail accounts
            labels: List of labels
            threads: List of threads
            messages: List of messages
            attachments: List of attachments
            
        Returns:
            List of Notion block objects
        """
        blocks = []
        
        # Header
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"text": {"content": "📧 Gmail Data Export"}}]
            }
        })
        
        # Export info
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{
                    "text": {"content": f"Exported on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
                }]
            }
        })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Statistics
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": "📊 Statistics"}}]
            }
        })
        
        stats_text = f"• Accounts: {len(accounts)}\n"
        stats_text += f"• Labels/Folders: {len(labels)}\n"
        stats_text += f"• Threads: {len(threads)}\n"
        stats_text += f"• Messages: {len(messages)}\n"
        stats_text += f"• Attachments: {len(attachments)}"
        
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": stats_text}}]
            }
        })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Accounts
        if accounts:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "👤 Account"}}]
                }
            })
            
            for account in accounts:
                account_text = f"• {account.email_address}\n"
                account_text += f"  Total Messages: {account.messages_total or 0}\n"
                account_text += f"  Total Threads: {account.threads_total or 0}"
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": account_text}}]
                    }
                })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Labels
        if labels:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": "🏷️ Labels"}}]
                }
            })
            
            # Group by type
            system_labels = [l for l in labels if l.type == 'system']
            user_labels = [l for l in labels if l.type == 'user']
            
            if system_labels:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": "System Labels:"}, "annotations": {"bold": True}}]
                    }
                })
                
                for label in system_labels[:10]:
                    label_text = f"• {label.name} ({label.messages_total or 0} messages"
                    if label.messages_unread:
                        label_text += f", {label.messages_unread} unread"
                    label_text += ")"
                    
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"text": {"content": label_text}}]
                        }
                    })
            
            if user_labels:
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": "User Labels:"}, "annotations": {"bold": True}}]
                    }
                })
                
                for label in user_labels[:10]:
                    label_text = f"• {label.name} ({label.messages_total or 0} messages)"
                    
                    blocks.append({
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"text": {"content": label_text}}]
                        }
                    })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Recent Messages
        if messages:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": f"📨 Recent Messages (Top {len(messages)})"}}]
                }
            })
            
            for msg in messages[:20]:  # Limit to prevent too many blocks
                # Message header
                subject = msg.subject or "(No Subject)"
                from_email = msg.from_email or "Unknown"
                date_str = msg.date.strftime('%Y-%m-%d %H:%M') if msg.date else "Unknown date"
                
                msg_header = f"**From:** {from_email}\n"
                msg_header += f"**Subject:** {subject}\n"
                msg_header += f"**Date:** {date_str}\n"
                
                if msg.has_attachments:
                    msg_header += f"**Attachments:** {msg.attachment_count}\n"
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": msg_header}}]
                    }
                })
                
                # Message snippet
                snippet = msg.snippet or ""
                if len(snippet) > 200:
                    snippet = snippet[:200] + "..."
                
                if snippet:
                    blocks.append({
                        "object": "block",
                        "type": "quote",
                        "quote": {
                            "rich_text": [{"text": {"content": snippet}}]
                        }
                    })
                
                # Separator
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": ""}}]
                    }
                })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Threads
        if threads:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": f"💬 Recent Threads (Top {len(threads)})"}}]
                }
            })
            
            for thread in threads[:10]:
                thread_text = f"• Thread ID: {thread.thread_id}\n"
                thread_text += f"  Messages in thread: {thread.message_count}\n"
                
                snippet = thread.snippet or ""
                if len(snippet) > 100:
                    snippet = snippet[:100] + "..."
                thread_text += f"  Preview: {snippet}"
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": thread_text}}]
                    }
                })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Attachments
        if attachments:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"text": {"content": f"📎 Attachments ({len(attachments)} total)"}}]
                }
            })
            
            downloaded = [a for a in attachments if a.is_downloaded]
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{
                        "text": {"content": f"Downloaded: {len(downloaded)} / {len(attachments)}"}
                    }]
                }
            })
            
            # Show sample attachments
            for att in attachments[:15]:
                att_text = f"• {att.filename or 'Unknown'} "
                att_text += f"({att.mime_type}, {att.size} bytes)"
                if att.is_downloaded:
                    att_text += " ✓ Downloaded"
                
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"text": {"content": att_text}}]
                    }
                })
        
        return blocks
