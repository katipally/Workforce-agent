"""Export entire database to Notion - all tables and data."""

from datetime import datetime
from typing import List, Dict, Any
from rich.console import Console
from rich.progress import Progress

from database.db_manager import DatabaseManager
from database.models import (
    Workspace, User, Channel, Message, File, Reaction, SyncStatus,
    GmailAccount, GmailLabel, GmailThread, GmailMessage, GmailAttachment
)
from notion_export.client import NotionClient
from utils.logger import get_logger

console = Console()
logger = get_logger(__name__)


class FullDatabaseExporter:
    """Export all database tables to Notion."""
    
    def __init__(self, notion_token: str = None):
        """Initialize exporter."""
        self.db = DatabaseManager()
        self.notion = NotionClient(notion_token)
        logger.info("FullDatabaseExporter initialized")
    
    def export_all(self, parent_page_id: str) -> Dict[str, Any]:
        """Export all database tables to Notion."""
        
        console.print("\n[bold cyan]📊 Full Database → Notion Export[/bold cyan]")
        console.print("Exporting ALL tables with complete data...\n")
        
        # Test Notion connection
        if not self.notion.test_connection():
            raise ValueError("Failed to connect to Notion API")
        console.print("✓ Notion connected\n")
        
        # Load all data
        console.print("[cyan]Loading data from database...[/cyan]")
        data = self._load_all_data()
        console.print("✓ Data loaded\n")
        
        # Show summary
        self._print_summary(data)
        
        # Format for Notion
        console.print("\n[cyan]Formatting data for Notion...[/cyan]")
        blocks = self._format_all_data(data)
        console.print(f"Created {len(blocks)} blocks\n")
        
        # Create page
        console.print("[cyan]Creating Notion page...[/cyan]")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        page_title = f"Complete Database Export - {timestamp}"
        
        page = self.notion.create_page(
            parent_id=parent_page_id,
            title=page_title,
            blocks=blocks
        )
        
        page_url = page.get("url", "")
        console.print(f"\n[bold green]✓ Export Complete![/bold green]")
        console.print(f"[cyan]Page URL:[/cyan] {page_url}\n")
        
        return {
            "success": True,
            "page_id": page.get("id"),
            "url": page_url,
            "timestamp": timestamp,
            "total_blocks": len(blocks)
        }
    
    def _load_all_data(self) -> Dict[str, Any]:
        """Load all data from database."""
        with self.db.get_session() as session:
            return {
                # Slack tables
                "workspaces": session.query(Workspace).all(),
                "users": session.query(User).all(),
                "channels": session.query(Channel).all(),
                "messages": session.query(Message).all(),
                "files": session.query(File).all(),
                "reactions": session.query(Reaction).all(),
                "sync_status": session.query(SyncStatus).all(),
                
                # Gmail tables
                "gmail_accounts": session.query(GmailAccount).all(),
                "gmail_labels": session.query(GmailLabel).all(),
                "gmail_threads": session.query(GmailThread).all(),
                "gmail_messages": session.query(GmailMessage).all(),
                "gmail_attachments": session.query(GmailAttachment).all(),
            }
    
    def _print_summary(self, data: Dict[str, Any]):
        """Print summary of data."""
        console.print("[bold]Database Summary:[/bold]")
        
        # Slack data
        console.print("\n[cyan]Slack Data:[/cyan]")
        console.print(f"  • Workspaces: {len(data['workspaces'])}")
        console.print(f"  • Users: {len(data['users'])}")
        console.print(f"  • Channels: {len(data['channels'])}")
        console.print(f"  • Messages: {len(data['messages'])}")
        console.print(f"  • Files: {len(data['files'])}")
        console.print(f"  • Reactions: {len(data['reactions'])}")
        
        # Gmail data
        console.print("\n[cyan]Gmail Data:[/cyan]")
        console.print(f"  • Accounts: {len(data['gmail_accounts'])}")
        console.print(f"  • Labels: {len(data['gmail_labels'])}")
        console.print(f"  • Threads: {len(data['gmail_threads'])}")
        console.print(f"  • Messages: {len(data['gmail_messages'])}")
        console.print(f"  • Attachments: {len(data['gmail_attachments'])}")
    
    def _format_all_data(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Format all data as Notion blocks."""
        blocks = []
        
        # Title and overview
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"text": {"content": "📊 Complete Database Export"}}]
            }
        })
        
        # Summary statistics
        total_slack = sum([
            len(data['workspaces']),
            len(data['users']),
            len(data['channels']),
            len(data['messages']),
            len(data['files']),
            len(data['reactions'])
        ])
        
        total_gmail = sum([
            len(data['gmail_accounts']),
            len(data['gmail_labels']),
            len(data['gmail_threads']),
            len(data['gmail_messages']),
            len(data['gmail_attachments'])
        ])
        
        summary = f"Total Records: {total_slack + total_gmail}\n"
        summary += f"Slack Records: {total_slack}\n"
        summary += f"Gmail Records: {total_gmail}\n"
        summary += f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": summary}}]
            }
        })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Table of Contents
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": "📑 Table of Contents"}}]
            }
        })
        
        toc = "Slack Tables:\n"
        toc += "  1. Workspaces\n  2. Users\n  3. Channels\n  4. Messages\n  5. Files\n  6. Reactions\n\n"
        toc += "Gmail Tables:\n"
        toc += "  7. Accounts\n  8. Labels\n  9. Threads\n  10. Messages\n  11. Attachments"
        
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": toc}}]
            }
        })
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Slack Tables
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"text": {"content": "💬 Slack Data"}}]
            }
        })
        
        # Workspaces
        blocks.extend(self._format_workspaces(data['workspaces']))
        
        # Users
        blocks.extend(self._format_users(data['users']))
        
        # Channels
        blocks.extend(self._format_channels(data['channels']))
        
        # Messages
        blocks.extend(self._format_messages(data['messages']))
        
        # Files
        blocks.extend(self._format_files(data['files']))
        
        # Reactions
        blocks.extend(self._format_reactions(data['reactions']))
        
        blocks.append({"object": "block", "type": "divider", "divider": {}})
        
        # Gmail Tables
        blocks.append({
            "object": "block",
            "type": "heading_1",
            "heading_1": {
                "rich_text": [{"text": {"content": "📧 Gmail Data"}}]
            }
        })
        
        # Gmail Accounts
        blocks.extend(self._format_gmail_accounts(data['gmail_accounts']))
        
        # Gmail Labels
        blocks.extend(self._format_gmail_labels(data['gmail_labels']))
        
        # Gmail Threads
        blocks.extend(self._format_gmail_threads(data['gmail_threads']))
        
        # Gmail Messages
        blocks.extend(self._format_gmail_messages(data['gmail_messages']))
        
        # Gmail Attachments
        blocks.extend(self._format_gmail_attachments(data['gmail_attachments']))
        
        return blocks
    
    def _format_workspaces(self, workspaces: List[Workspace]) -> List[Dict[str, Any]]:
        """Format workspaces table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"🏢 Workspaces ({len(workspaces)})"}}]
            }
        })
        
        if not workspaces:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No workspaces found."}}]
                }
            })
            return blocks
        
        for ws in workspaces[:50]:  # Limit to avoid block limit
            text = f"• {ws.name or 'N/A'}\n"
            text += f"  ID: {ws.workspace_id}\n"
            text += f"  Domain: {ws.domain or 'N/A'}\n"
            text += f"  Email Domain: {ws.email_domain or 'N/A'}"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(workspaces) > 50:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(workspaces) - 50} more"}}]
                }
            })
        
        return blocks
    
    def _format_users(self, users: List[User]) -> List[Dict[str, Any]]:
        """Format users table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"👤 Users ({len(users)})"}}]
            }
        })
        
        if not users:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No users found."}}]
                }
            })
            return blocks
        
        for user in users[:50]:
            text = f"• @{user.username or user.user_id}\n"
            text += f"  Real Name: {user.real_name or 'N/A'}\n"
            text += f"  Email: {user.email or 'N/A'}\n"
            text += f"  Bot: {'Yes' if user.is_bot else 'No'}"
            if user.is_admin:
                text += " | Admin"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(users) > 50:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(users) - 50} more"}}]
                }
            })
        
        return blocks
    
    def _format_channels(self, channels: List[Channel]) -> List[Dict[str, Any]]:
        """Format channels table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"#️⃣ Channels ({len(channels)})"}}]
            }
        })
        
        if not channels:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No channels found."}}]
                }
            })
            return blocks
        
        for channel in channels[:50]:
            text = f"• #{channel.name or channel.channel_id}\n"
            text += f"  Topic: {channel.topic or 'N/A'}\n"
            text += f"  Members: {channel.num_members or 0}\n"
            text += f"  Private: {'Yes' if channel.is_private else 'No'}"
            if channel.is_archived:
                text += " | Archived"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(channels) > 50:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(channels) - 50} more"}}]
                }
            })
        
        return blocks
    
    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Format messages table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"💬 Messages ({len(messages)})"}}]
            }
        })
        
        if not messages:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No messages found."}}]
                }
            })
            return blocks
        
        # Show recent messages
        recent = sorted(messages, key=lambda m: m.timestamp or 0, reverse=True)[:30]
        
        for msg in recent:
            text = msg.text or "[No text]"
            if len(text) > 200:
                text = text[:200] + "..."
            
            msg_info = f"• {text}\n"
            msg_info += f"  User: {msg.user_id}\n"
            msg_info += f"  Time: {datetime.fromtimestamp(msg.timestamp).strftime('%Y-%m-%d %H:%M') if msg.timestamp else 'N/A'}"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": msg_info}}]
                }
            })
        
        if len(messages) > 30:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(messages) - 30} more messages"}}]
                }
            })
        
        return blocks
    
    def _format_files(self, files: List[File]) -> List[Dict[str, Any]]:
        """Format files table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"📎 Files ({len(files)})"}}]
            }
        })
        
        if not files:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No files found."}}]
                }
            })
            return blocks
        
        for file in files[:30]:
            text = f"• {file.name or file.title or 'Untitled'}\n"
            text += f"  Type: {file.mimetype or 'Unknown'}\n"
            text += f"  Size: {file.size or 0} bytes"
            if file.permalink:
                text += f"\n  URL: {file.permalink}"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(files) > 30:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(files) - 30} more files"}}]
                }
            })
        
        return blocks
    
    def _format_reactions(self, reactions: List[Reaction]) -> List[Dict[str, Any]]:
        """Format reactions table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"👍 Reactions ({len(reactions)})"}}]
            }
        })
        
        if not reactions:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No reactions found."}}]
                }
            })
            return blocks
        
        # Group by emoji
        emoji_counts = {}
        for r in reactions:
            emoji_counts[r.name] = emoji_counts.get(r.name, 0) + 1
        
        # Top reactions
        top_reactions = sorted(emoji_counts.items(), key=lambda x: x[1], reverse=True)[:20]
        
        text = "Top Reactions:\n"
        for emoji, count in top_reactions:
            text += f"  :{emoji}: × {count}\n"
        
        blocks.append({
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"text": {"content": text.strip()}}]
            }
        })
        
        return blocks
    
    def _format_gmail_accounts(self, accounts: List[GmailAccount]) -> List[Dict[str, Any]]:
        """Format Gmail accounts table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"📧 Gmail Accounts ({len(accounts)})"}}]
            }
        })
        
        if not accounts:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No Gmail accounts found."}}]
                }
            })
            return blocks
        
        for acc in accounts:
            text = f"• {acc.email_address}\n"
            text += f"  Total Messages: {acc.messages_total or 0}\n"
            text += f"  Total Threads: {acc.threads_total or 0}"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        return blocks
    
    def _format_gmail_labels(self, labels: List[GmailLabel]) -> List[Dict[str, Any]]:
        """Format Gmail labels table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"🏷️ Gmail Labels ({len(labels)})"}}]
            }
        })
        
        if not labels:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No Gmail labels found."}}]
                }
            })
            return blocks
        
        for label in labels[:30]:
            text = f"• {label.name}\n"
            text += f"  Messages: {label.messages_total or 0}"
            if label.messages_unread:
                text += f" ({label.messages_unread} unread)"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(labels) > 30:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(labels) - 30} more labels"}}]
                }
            })
        
        return blocks
    
    def _format_gmail_threads(self, threads: List[GmailThread]) -> List[Dict[str, Any]]:
        """Format Gmail threads table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"🧵 Gmail Threads ({len(threads)})"}}]
            }
        })
        
        if not threads:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No Gmail threads found."}}]
                }
            })
            return blocks
        
        for thread in threads[:30]:
            snippet = thread.snippet or "No snippet"
            if len(snippet) > 100:
                snippet = snippet[:100] + "..."
            
            text = f"• {snippet}\n"
            text += f"  Messages: {thread.message_count or 0}"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(threads) > 30:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(threads) - 30} more threads"}}]
                }
            })
        
        return blocks
    
    def _format_gmail_messages(self, messages: List[GmailMessage]) -> List[Dict[str, Any]]:
        """Format Gmail messages table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"✉️ Gmail Messages ({len(messages)})"}}]
            }
        })
        
        if not messages:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No Gmail messages found."}}]
                }
            })
            return blocks
        
        # Show recent messages
        recent = sorted(messages, key=lambda m: m.date or datetime.min, reverse=True)[:30]
        
        for msg in recent:
            subject = msg.subject or "No subject"
            if len(subject) > 100:
                subject = subject[:100] + "..."
            
            text = f"• {subject}\n"
            text += f"  From: {msg.from_email or 'Unknown'}\n"
            text += f"  Date: {msg.date.strftime('%Y-%m-%d %H:%M') if msg.date else 'N/A'}"
            if not msg.is_read:
                text += " | UNREAD"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(messages) > 30:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(messages) - 30} more messages"}}]
                }
            })
        
        return blocks
    
    def _format_gmail_attachments(self, attachments: List[GmailAttachment]) -> List[Dict[str, Any]]:
        """Format Gmail attachments table."""
        blocks = []
        
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"text": {"content": f"📎 Gmail Attachments ({len(attachments)})"}}]
            }
        })
        
        if not attachments:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": "No Gmail attachments found."}}]
                }
            })
            return blocks
        
        for att in attachments[:30]:
            text = f"• {att.filename or 'Unnamed'}\n"
            text += f"  Type: {att.mime_type or 'Unknown'}\n"
            text += f"  Size: {att.size or 0} bytes"
            
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": text}}]
                }
            })
        
        if len(attachments) > 30:
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"text": {"content": f"... and {len(attachments) - 30} more attachments"}}]
                }
            })
        
        return blocks
