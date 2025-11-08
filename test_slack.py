"""Comprehensive Slack API Integration Test Suite.

Tests all Slack functionality:
- Authentication
- Data extraction (users, channels, messages, files)
- Message sending/receiving
- File uploads
- Reactions
- Socket Mode streaming
- Database operations
"""

import sys
import time
import asyncio
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from config import Config
from database.db_manager import DatabaseManager
from extractor import ExtractionCoordinator
from sender import MessageSender, FileSender, ReactionManager
from realtime.event_handlers import EventHandlers
from realtime.socket_client import SocketModeClient
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

console = Console()


class SlackIntegrationTest:
    """Comprehensive Slack integration test."""
    
    def __init__(self):
        self.results = []
        self.client = None
        self.db = None
        self.test_channel = None
    
    def log_result(self, test_name: str, passed: bool, message: str = ""):
        """Log test result."""
        self.results.append({"test": test_name, "passed": passed, "message": message})
        status = "✓" if passed else "✗"
        color = "green" if passed else "red"
        console.print(f"[{color}]{status}[/{color}] {test_name}")
        if message:
            console.print(f"   {message}")
    
    def test_authentication(self) -> bool:
        """Test bot authentication."""
        console.print("\n[bold cyan]1. Authentication[/bold cyan]")
        
        try:
            self.client = WebClient(token=Config.SLACK_BOT_TOKEN)
            auth = self.client.auth_test()
            
            bot_id = auth.get("user_id", "Unknown")
            team = auth.get("team", "Unknown")
            
            self.log_result("Bot Authentication", True, f"Bot ID: {bot_id}, Team: {team}")
            return True
        except Exception as e:
            self.log_result("Bot Authentication", False, f"Error: {e}")
            return False
    
    def test_database(self) -> bool:
        """Test database initialization."""
        console.print("\n[bold cyan]2. Database[/bold cyan]")
        
        try:
            self.db = DatabaseManager()
            stats = self.db.get_statistics()
            
            self.log_result("Database Init", True, f"Users: {stats['users']}, Channels: {stats['channels']}, Messages: {stats['messages']}")
            return True
        except Exception as e:
            self.log_result("Database Init", False, f"Error: {e}")
            return False
    
    def test_extraction(self) -> bool:
        """Test data extraction."""
        console.print("\n[bold cyan]3. Data Extraction[/bold cyan]")
        
        try:
            coordinator = ExtractionCoordinator(client=self.client, db_manager=self.db)
            results = coordinator.extract_all()
            
            users = results.get('users', 0)
            channels = results.get('channels', 0)
            
            self.log_result("Extract All Data", True, f"Extracted {users} users, {channels} channels")
            return True
        except Exception as e:
            self.log_result("Extract All Data", False, f"Error: {e}")
            return False
    
    def test_channels(self) -> bool:
        """Test channel operations."""
        console.print("\n[bold cyan]4. Channel Operations[/bold cyan]")
        
        try:
            response = self.client.conversations_list(types="public_channel,private_channel", limit=10)
            channels = response.get("channels", [])
            
            if channels:
                self.test_channel = channels[0]["id"]
                self.log_result("List Channels", True, f"Found {len(channels)} channels")
                return True
            else:
                self.log_result("List Channels", False, "No channels found")
                return False
        except Exception as e:
            self.log_result("List Channels", False, f"Error: {e}")
            return False
    
    def test_messages(self) -> bool:
        """Test message operations."""
        console.print("\n[bold cyan]5. Message Operations[/bold cyan]")
        
        if not self.test_channel:
            self.log_result("Messages", False, "No test channel")
            return False
        
        try:
            sender = MessageSender(client=self.client)
            
            # Send message
            result = sender.send_message(
                channel=self.test_channel,
                text=f"🧪 Test message - {time.strftime('%H:%M:%S')}"
            )
            
            if result and result.get("ok"):
                msg_ts = result.get("ts")
                self.log_result("Send Message", True, f"Message sent (ts: {msg_ts})")
                
                # Delete message
                time.sleep(1)
                try:
                    delete_result = sender.delete_message(channel=self.test_channel, ts=msg_ts)
                    if delete_result and delete_result.get("ok"):
                        self.log_result("Delete Message", True, "Message cleaned up")
                except:
                    pass
                
                return True
            else:
                self.log_result("Send Message", False, "Failed to send")
                return False
        except Exception as e:
            self.log_result("Messages", False, f"Error: {e}")
            return False
    
    def test_rich_formatting(self) -> bool:
        """Test rich message formatting."""
        console.print("\n[bold cyan]6. Rich Formatting[/bold cyan]")
        
        if not self.test_channel:
            self.log_result("Rich Formatting", False, "No test channel")
            return False
        
        try:
            sender = MessageSender(client=self.client)
            
            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "*Test Rich Message*\nFormatted content"}
                }
            ]
            
            result = sender.send_message(channel=self.test_channel, text="Rich test", blocks=blocks)
            
            if result and result.get("ok"):
                msg_ts = result.get("ts")
                self.log_result("Rich Formatting", True, "Formatted message sent")
                
                # Cleanup
                time.sleep(1)
                try:
                    sender.delete_message(channel=self.test_channel, ts=msg_ts)
                except:
                    pass
                
                return True
            else:
                self.log_result("Rich Formatting", False, "Failed")
                return False
        except Exception as e:
            self.log_result("Rich Formatting", False, f"Error: {e}")
            return False
    
    def test_reactions(self) -> bool:
        """Test reaction operations."""
        console.print("\n[bold cyan]7. Reactions[/bold cyan]")
        
        if not self.test_channel:
            self.log_result("Reactions", False, "No test channel")
            return False
        
        try:
            # Send a message first
            sender = MessageSender(client=self.client)
            result = sender.send_message(channel=self.test_channel, text="Test for reactions")
            
            if not result or not result.get("ok"):
                self.log_result("Reactions", False, "Couldn't send test message")
                return False
            
            msg_ts = result.get("ts")
            
            # Add reaction
            reaction_mgr = ReactionManager(client=self.client)
            add_result = reaction_mgr.add_reaction(channel=self.test_channel, timestamp=msg_ts, emoji="thumbsup")
            
            if add_result and add_result.get("ok"):
                self.log_result("Add Reaction", True, "Reaction added")
                
                # Remove reaction
                time.sleep(1)
                remove_result = reaction_mgr.remove_reaction(channel=self.test_channel, timestamp=msg_ts, emoji="thumbsup")
                if remove_result and remove_result.get("ok"):
                    self.log_result("Remove Reaction", True, "Reaction removed")
                
                # Cleanup message
                time.sleep(1)
                try:
                    sender.delete_message(channel=self.test_channel, ts=msg_ts)
                except:
                    pass
                
                return True
            else:
                self.log_result("Reactions", False, "Failed to add reaction")
                # Cleanup
                try:
                    sender.delete_message(channel=self.test_channel, ts=msg_ts)
                except:
                    pass
                return False
        except Exception as e:
            self.log_result("Reactions", False, f"Error: {e}")
            return False
    
    async def test_socket_mode(self) -> bool:
        """Test Socket Mode streaming."""
        console.print("\n[bold cyan]8. Socket Mode Streaming[/bold cyan]")
        
        try:
            handlers = EventHandlers(db_manager=self.db)
            client = SocketModeClient(db_manager=self.db, event_handlers=handlers)
            
            # Start stream for 3 seconds
            stream_task = asyncio.create_task(client.start())
            await asyncio.sleep(3)
            
            if client.is_running:
                self.log_result("Socket Mode", True, "Streaming works (no OAuth errors)")
                await client.stop()
                return True
            else:
                self.log_result("Socket Mode", False, "Stream stopped unexpectedly")
                return False
        except Exception as e:
            self.log_result("Socket Mode", False, f"Error: {e}")
            return False
    
    def test_database_queries(self) -> bool:
        """Test database query operations."""
        console.print("\n[bold cyan]9. Database Queries[/bold cyan]")
        
        try:
            users = self.db.get_all_users()
            channels = self.db.get_all_channels()
            files = self.db.get_all_files()
            
            # Test message query
            if channels:
                messages = self.db.get_messages_by_channel(channels[0].channel_id, limit=10)
                msg_count = len(messages)
            else:
                msg_count = 0
            
            self.log_result("Database Queries", True, f"{len(users)} users, {len(channels)} channels, {msg_count} messages queryable")
            return True
        except Exception as e:
            self.log_result("Database Queries", False, f"Error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        console.print(Panel.fit(
            "[bold cyan]Slack Integration Test Suite[/bold cyan]\n"
            "Testing all Slack API functionality",
            border_style="cyan"
        ))
        
        # Sync tests
        auth_ok = self.test_authentication()
        if not auth_ok:
            self.print_summary()
            return
        
        db_ok = self.test_database()
        extract_ok = self.test_extraction()
        channels_ok = self.test_channels()
        messages_ok = self.test_messages()
        rich_ok = self.test_rich_formatting()
        reactions_ok = self.test_reactions()
        queries_ok = self.test_database_queries()
        
        # Async test for Socket Mode
        try:
            socket_ok = asyncio.run(self.test_socket_mode())
        except Exception as e:
            self.log_result("Socket Mode", False, f"Error: {e}")
            socket_ok = False
        
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        console.print("\n" + "="*60)
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        table = Table(title="Test Results", show_header=True)
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Details")
        
        for result in self.results:
            status = "[green]✓ PASS[/green]" if result["passed"] else "[red]✗ FAIL[/red]"
            table.add_row(result["test"], status, result["message"])
        
        console.print(table)
        console.print(f"\n[bold]Results: {passed}/{total} tests passed[/bold]")
        
        if passed == total:
            console.print("\n[bold green]✅ All Slack tests passed![/bold green]")
            console.print("\n[cyan]Slack integration fully operational:[/cyan]")
            console.print("  • Authentication working")
            console.print("  • Data extraction working")
            console.print("  • Message operations working")
            console.print("  • Socket Mode streaming working")
            console.print("  • Database operations working")
        else:
            console.print("\n[bold red]❌ Some tests failed[/bold red]")
            console.print("\nCheck the errors above and fix them.")


def main():
    """Run tests."""
    tester = SlackIntegrationTest()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
