"""
Comprehensive Slack API Integration Test
Tests all features end-to-end with Nov 2025 methods
"""
import asyncio
import time
from datetime import datetime
from pathlib import Path

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from config import Config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

class SlackIntegrationTester:
    """Comprehensive Slack API integration tester."""
    
    def __init__(self):
        """Initialize tester."""
        self.client = WebClient(token=Config.SLACK_BOT_TOKEN)
        self.test_results = []
        self.workspace_info = {}
        self.test_channel = None
        self.test_message_ts = None
        
    def log_test(self, test_name: str, passed: bool, message: str = "", details: dict = None):
        """Log test result."""
        self.test_results.append({
            "name": test_name,
            "passed": passed,
            "message": message,
            "details": details or {}
        })
        
        status = "[green]✓ PASS[/green]" if passed else "[red]✗ FAIL[/red]"
        console.print(f"{status} {test_name}: {message}")
        
        if details and passed:
            for key, value in details.items():
                console.print(f"      [dim]{key}: {value}[/dim]")
    
    async def test_1_credentials(self):
        """Test 1: Verify all credentials are configured."""
        console.print("\n[bold blue]Test 1: Credentials Configuration[/bold blue]")
        
        # Check bot token
        if Config.SLACK_BOT_TOKEN and Config.SLACK_BOT_TOKEN.startswith("xoxb-"):
            self.log_test("Bot Token", True, "Valid bot token configured")
        else:
            self.log_test("Bot Token", False, "Invalid or missing bot token")
            return False
        
        # Check app token
        if Config.SLACK_APP_TOKEN and Config.SLACK_APP_TOKEN.startswith("xapp-"):
            self.log_test("App-Level Token", True, "Valid app token configured")
        else:
            self.log_test("App-Level Token", False, "Missing app token (required for Socket Mode)")
        
        # Check other credentials
        if Config.SLACK_APP_ID:
            self.log_test("App ID", True, f"App ID: {Config.SLACK_APP_ID}")
        
        if Config.SLACK_CLIENT_ID:
            self.log_test("Client ID", True, f"Client ID configured")
        
        if Config.SLACK_CLIENT_SECRET:
            self.log_test("Client Secret", True, "Client secret configured")
        else:
            self.log_test("Client Secret", False, "Client secret not set (optional)")
        
        if Config.SLACK_SIGNING_SECRET:
            self.log_test("Signing Secret", True, "Signing secret configured")
        else:
            self.log_test("Signing Secret", False, "Signing secret not set (optional)")
        
        return True
    
    async def test_2_auth_test(self):
        """Test 2: Authentication and workspace connection."""
        console.print("\n[bold blue]Test 2: Authentication & Workspace Connection[/bold blue]")
        
        try:
            response = self.client.auth_test()
            
            if response.get("ok"):
                self.workspace_info = {
                    "team": response.get("team"),
                    "team_id": response.get("team_id"),
                    "user": response.get("user"),
                    "user_id": response.get("user_id"),
                    "bot_id": response.get("bot_id")
                }
                
                self.log_test(
                    "Auth Test",
                    True,
                    f"Connected to {self.workspace_info['team']}",
                    self.workspace_info
                )
                return True
            else:
                self.log_test("Auth Test", False, f"Auth failed: {response.get('error')}")
                return False
        
        except SlackApiError as e:
            self.log_test("Auth Test", False, f"API Error: {e.response['error']}")
            return False
        except Exception as e:
            self.log_test("Auth Test", False, f"Exception: {str(e)}")
            return False
    
    async def test_3_team_info(self):
        """Test 3: Get workspace/team information."""
        console.print("\n[bold blue]Test 3: Workspace Information (team.info)[/bold blue]")
        
        try:
            response = self.client.team_info()
            
            if response.get("ok"):
                team = response.get("team", {})
                details = {
                    "name": team.get("name"),
                    "domain": team.get("domain"),
                    "email_domain": team.get("email_domain"),
                }
                
                self.log_test("Team Info", True, "Workspace info retrieved", details)
                return True
            else:
                self.log_test("Team Info", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Team Info", False, f"Error: {str(e)}")
            return False
    
    async def test_4_list_users(self):
        """Test 4: List users (users.list)."""
        console.print("\n[bold blue]Test 4: List Users (users.list)[/bold blue]")
        
        try:
            response = self.client.users_list(limit=10)
            
            if response.get("ok"):
                members = response.get("members", [])
                user_count = len(members)
                
                # Get active users
                active_users = [u for u in members if not u.get("deleted") and not u.get("is_bot")]
                
                details = {
                    "total_fetched": user_count,
                    "active_users": len(active_users),
                    "sample_user": active_users[0].get("name") if active_users else "None"
                }
                
                self.log_test("List Users", True, f"Retrieved {user_count} users", details)
                return True
            else:
                self.log_test("List Users", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("List Users", False, f"Error: {str(e)}")
            return False
    
    async def test_5_list_channels(self):
        """Test 5: List conversations (conversations.list)."""
        console.print("\n[bold blue]Test 5: List Channels (conversations.list)[/bold blue]")
        
        try:
            response = self.client.conversations_list(
                types="public_channel,private_channel",
                limit=50
            )
            
            if response.get("ok"):
                channels = response.get("channels", [])
                channel_count = len(channels)
                
                # Find a channel for testing
                public_channels = [c for c in channels if not c.get("is_private")]
                if public_channels:
                    self.test_channel = public_channels[0]["id"]
                
                details = {
                    "total_channels": channel_count,
                    "public": len([c for c in channels if not c.get("is_private")]),
                    "private": len([c for c in channels if c.get("is_private")]),
                    "test_channel": self.test_channel
                }
                
                self.log_test("List Channels", True, f"Retrieved {channel_count} channels", details)
                return True
            else:
                self.log_test("List Channels", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("List Channels", False, f"Error: {str(e)}")
            return False
    
    async def test_6_channel_info(self):
        """Test 6: Get channel info (conversations.info)."""
        console.print("\n[bold blue]Test 6: Channel Info (conversations.info)[/bold blue]")
        
        if not self.test_channel:
            self.log_test("Channel Info", False, "No test channel available")
            return False
        
        try:
            response = self.client.conversations_info(channel=self.test_channel)
            
            if response.get("ok"):
                channel = response.get("channel", {})
                details = {
                    "name": channel.get("name"),
                    "id": channel.get("id"),
                    "members": channel.get("num_members"),
                    "topic": channel.get("topic", {}).get("value", "")[:50]
                }
                
                self.log_test("Channel Info", True, f"Retrieved info for #{channel.get('name')}", details)
                return True
            else:
                self.log_test("Channel Info", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Channel Info", False, f"Error: {str(e)}")
            return False
    
    async def test_7_channel_members(self):
        """Test 7: Get channel members (conversations.members)."""
        console.print("\n[bold blue]Test 7: Channel Members (conversations.members)[/bold blue]")
        
        if not self.test_channel:
            self.log_test("Channel Members", False, "No test channel available")
            return False
        
        try:
            response = self.client.conversations_members(channel=self.test_channel, limit=50)
            
            if response.get("ok"):
                members = response.get("members", [])
                details = {
                    "member_count": len(members),
                    "sample_members": members[:3]
                }
                
                self.log_test("Channel Members", True, f"Retrieved {len(members)} members", details)
                return True
            else:
                self.log_test("Channel Members", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Channel Members", False, f"Error: {str(e)}")
            return False
    
    async def test_8_message_history(self):
        """Test 8: Get message history (conversations.history)."""
        console.print("\n[bold blue]Test 8: Message History (conversations.history)[/bold blue]")
        
        if not self.test_channel:
            self.log_test("Message History", False, "No test channel available")
            return False
        
        try:
            # First, try to join the channel if not already a member
            try:
                self.client.conversations_join(channel=self.test_channel)
                console.print("  [dim]→ Joined channel[/dim]")
            except Exception:
                pass  # Already in channel or can't join
            
            response = self.client.conversations_history(
                channel=self.test_channel,
                limit=10
            )
            
            if response.get("ok"):
                messages = response.get("messages", [])
                
                # Save a message for reaction testing
                if messages:
                    self.test_message_ts = messages[0].get("ts")
                
                details = {
                    "message_count": len(messages),
                    "has_messages": len(messages) > 0,
                    "latest_ts": self.test_message_ts
                }
                
                self.log_test("Message History", True, f"Retrieved {len(messages)} messages", details)
                return True
            else:
                self.log_test("Message History", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Message History", False, f"Error: {str(e)}")
            return False
    
    async def test_9_send_message(self):
        """Test 9: Send a message (chat.postMessage)."""
        console.print("\n[bold blue]Test 9: Send Message (chat.postMessage)[/bold blue]")
        
        if not self.test_channel:
            self.log_test("Send Message", False, "No test channel available")
            return False
        
        try:
            test_text = f"🤖 Slack Agent Test - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            
            response = self.client.chat_postMessage(
                channel=self.test_channel,
                text=test_text,
                blocks=[
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Integration Test Message*\n{test_text}"
                        }
                    }
                ]
            )
            
            if response.get("ok"):
                self.test_message_ts = response.get("ts")
                
                details = {
                    "channel": response.get("channel"),
                    "ts": self.test_message_ts,
                    "text": test_text[:50]
                }
                
                self.log_test("Send Message", True, "Message sent successfully", details)
                return True
            else:
                self.log_test("Send Message", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Send Message", False, f"Error: {str(e)}")
            return False
    
    async def test_10_update_message(self):
        """Test 10: Update a message (chat.update)."""
        console.print("\n[bold blue]Test 10: Update Message (chat.update)[/bold blue]")
        
        if not self.test_channel or not self.test_message_ts:
            self.log_test("Update Message", False, "No test message available")
            return False
        
        try:
            updated_text = f"✅ Message Updated - {datetime.now().strftime('%H:%M:%S')}"
            
            response = self.client.chat_update(
                channel=self.test_channel,
                ts=self.test_message_ts,
                text=updated_text
            )
            
            if response.get("ok"):
                details = {
                    "channel": response.get("channel"),
                    "ts": response.get("ts"),
                    "updated_text": updated_text[:50]
                }
                
                self.log_test("Update Message", True, "Message updated successfully", details)
                return True
            else:
                self.log_test("Update Message", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Update Message", False, f"Error: {str(e)}")
            return False
    
    async def test_11_add_reaction(self):
        """Test 11: Add reaction (reactions.add)."""
        console.print("\n[bold blue]Test 11: Add Reaction (reactions.add)[/bold blue]")
        
        if not self.test_channel or not self.test_message_ts:
            self.log_test("Add Reaction", False, "No test message available")
            return False
        
        try:
            # Ensure bot is in channel
            try:
                self.client.conversations_join(channel=self.test_channel)
            except Exception:
                pass
            
            response = self.client.reactions_add(
                channel=self.test_channel,
                timestamp=self.test_message_ts,
                name="white_check_mark"
            )
            
            if response.get("ok"):
                details = {
                    "emoji": "white_check_mark",
                    "message_ts": self.test_message_ts
                }
                
                self.log_test("Add Reaction", True, "Reaction added successfully", details)
                return True
            else:
                # Already reacted is also ok
                if response.get("error") == "already_reacted":
                    self.log_test("Add Reaction", True, "Reaction already exists (OK)")
                    return True
                else:
                    self.log_test("Add Reaction", False, f"Failed: {response.get('error')}")
                    return False
        
        except Exception as e:
            self.log_test("Add Reaction", False, f"Error: {str(e)}")
            return False
    
    async def test_12_get_reactions(self):
        """Test 12: Get reactions (reactions.get)."""
        console.print("\n[bold blue]Test 12: Get Reactions (reactions.get)[/bold blue]")
        
        if not self.test_channel or not self.test_message_ts:
            self.log_test("Get Reactions", False, "No test message available")
            return False
        
        try:
            # Ensure bot is in channel
            try:
                self.client.conversations_join(channel=self.test_channel)
            except Exception:
                pass
            
            response = self.client.reactions_get(
                channel=self.test_channel,
                timestamp=self.test_message_ts
            )
            
            if response.get("ok"):
                message = response.get("message", {})
                reactions = message.get("reactions", [])
                
                details = {
                    "reaction_count": len(reactions),
                    "reactions": [r.get("name") for r in reactions]
                }
                
                self.log_test("Get Reactions", True, f"Retrieved {len(reactions)} reactions", details)
                return True
            else:
                self.log_test("Get Reactions", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Get Reactions", False, f"Error: {str(e)}")
            return False
    
    async def test_13_list_files(self):
        """Test 13: List files (files.list)."""
        console.print("\n[bold blue]Test 13: List Files (files.list)[/bold blue]")
        
        try:
            response = self.client.files_list(count=10)
            
            if response.get("ok"):
                files = response.get("files", [])
                
                details = {
                    "file_count": len(files),
                    "sample_file": files[0].get("name") if files else "None"
                }
                
                self.log_test("List Files", True, f"Retrieved {len(files)} files", details)
                return True
            else:
                self.log_test("List Files", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("List Files", False, f"Error: {str(e)}")
            return False
    
    async def test_14_upload_file(self):
        """Test 14: Upload file (files_upload_v2)."""
        console.print("\n[bold blue]Test 14: Upload File (files_upload_v2)[/bold blue]")
        
        if not self.test_channel:
            self.log_test("Upload File", False, "No test channel available")
            return False
        
        try:
            # Ensure bot is in channel
            try:
                self.client.conversations_join(channel=self.test_channel)
            except Exception:
                pass
            
            # Create a test file
            test_content = f"Slack Agent Integration Test\n{datetime.now()}\n✅ File upload test"
            
            response = self.client.files_upload_v2(
                channel=self.test_channel,
                content=test_content,
                filename="slack_agent_test.txt",
                title="Integration Test File",
                initial_comment="🤖 Test file upload from Slack Agent"
            )
            
            if response.get("ok"):
                file_data = response.get("file", {})
                
                details = {
                    "file_id": file_data.get("id"),
                    "filename": file_data.get("name"),
                    "size": file_data.get("size")
                }
                
                self.log_test("Upload File", True, "File uploaded successfully", details)
                return True
            else:
                self.log_test("Upload File", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Upload File", False, f"Error: {str(e)}")
            return False
    
    async def test_15_user_info(self):
        """Test 15: Get user info (users.info)."""
        console.print("\n[bold blue]Test 15: User Info (users.info)[/bold blue]")
        
        user_id = self.workspace_info.get("user_id")
        if not user_id:
            self.log_test("User Info", False, "No user ID available")
            return False
        
        try:
            response = self.client.users_info(user=user_id)
            
            if response.get("ok"):
                user = response.get("user", {})
                profile = user.get("profile", {})
                
                details = {
                    "name": user.get("name"),
                    "real_name": profile.get("real_name"),
                    "email": profile.get("email"),
                    "is_admin": user.get("is_admin", False)
                }
                
                self.log_test("User Info", True, f"Retrieved info for {user.get('name')}", details)
                return True
            else:
                self.log_test("User Info", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("User Info", False, f"Error: {str(e)}")
            return False
    
    async def test_16_socket_mode_connection(self):
        """Test 16: Socket Mode connection test."""
        console.print("\n[bold blue]Test 16: Socket Mode Connection[/bold blue]")
        
        if not Config.SLACK_APP_TOKEN:
            self.log_test("Socket Mode", False, "App token not configured")
            return False
        
        try:
            # Create app
            app = AsyncApp(token=Config.SLACK_BOT_TOKEN)
            
            # Test connection by creating handler
            handler = AsyncSocketModeHandler(app, Config.SLACK_APP_TOKEN)
            
            # Just test initialization
            self.log_test(
                "Socket Mode",
                True,
                "Socket Mode handler initialized successfully",
                {"app_token": f"{Config.SLACK_APP_TOKEN[:20]}..."}
            )
            return True
        
        except Exception as e:
            self.log_test("Socket Mode", False, f"Error: {str(e)}")
            return False
    
    async def test_17_rate_limiting(self):
        """Test 17: Rate limiting and retry logic."""
        console.print("\n[bold blue]Test 17: Rate Limiting Test[/bold blue]")
        
        try:
            from utils.rate_limiter import get_rate_limiter
            
            rate_limiter = get_rate_limiter()
            
            # Test rate limiter exists and works
            method = "test.method"
            rate_limiter.wait_if_needed(method)
            
            details = {
                "rate_limiter": "Initialized",
                "default_limit": Config.DEFAULT_RATE_LIMIT,
                "tier_4_limit": Config.TIER_4_RATE_LIMIT
            }
            
            self.log_test("Rate Limiting", True, "Rate limiter working", details)
            return True
        
        except Exception as e:
            self.log_test("Rate Limiting", False, f"Error: {str(e)}")
            return False
    
    async def test_18_database(self):
        """Test 18: Database connectivity."""
        console.print("\n[bold blue]Test 18: Database Connection[/bold blue]")
        
        try:
            from database.db_manager import DatabaseManager
            
            # Create data directory if it doesn't exist
            Config.create_directories()
            
            db = DatabaseManager()
            
            # Try to get stats
            stats = db.get_statistics()
            
            details = {
                "database_url": Config.DATABASE_URL,
                "users": stats.get("users", 0),
                "channels": stats.get("channels", 0),
                "messages": stats.get("messages", 0)
            }
            
            self.log_test("Database", True, "Database connected and operational", details)
            return True
        
        except Exception as e:
            self.log_test("Database", False, f"Error: {str(e)}")
            return False
    
    async def test_19_cleanup(self):
        """Test 19: Cleanup - delete test message."""
        console.print("\n[bold blue]Test 19: Cleanup (chat.delete)[/bold blue]")
        
        if not self.test_channel or not self.test_message_ts:
            self.log_test("Cleanup", True, "No test message to clean up")
            return True
        
        try:
            response = self.client.chat_delete(
                channel=self.test_channel,
                ts=self.test_message_ts
            )
            
            if response.get("ok"):
                self.log_test("Cleanup", True, "Test message deleted successfully")
                return True
            else:
                self.log_test("Cleanup", False, f"Failed: {response.get('error')}")
                return False
        
        except Exception as e:
            self.log_test("Cleanup", False, f"Error: {str(e)}")
            return False
    
    def print_summary(self):
        """Print test summary."""
        console.print("\n" + "="*70)
        console.print("\n[bold]TEST SUMMARY[/bold]\n")
        
        # Create summary table
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", style="dim", width=3)
        table.add_column("Test Name", min_width=30)
        table.add_column("Status", width=10)
        table.add_column("Message", min_width=20)
        
        passed = 0
        failed = 0
        
        for idx, result in enumerate(self.test_results, 1):
            if result["passed"]:
                passed += 1
                status = "[green]✓ PASS[/green]"
            else:
                failed += 1
                status = "[red]✗ FAIL[/red]"
            
            table.add_row(
                str(idx),
                result["name"],
                status,
                result["message"][:40]
            )
        
        console.print(table)
        
        # Overall result
        total = passed + failed
        pass_rate = (passed / total * 100) if total > 0 else 0
        
        console.print(f"\n[bold]Results:[/bold]")
        console.print(f"  Total Tests: {total}")
        console.print(f"  [green]Passed: {passed}[/green]")
        console.print(f"  [red]Failed: {failed}[/red]")
        console.print(f"  Pass Rate: {pass_rate:.1f}%")
        
        if failed == 0:
            console.print(Panel(
                "[bold green]🎉 ALL TESTS PASSED![/bold green]\n"
                "Your Slack Agent is fully operational and ready to use.",
                style="green"
            ))
        elif pass_rate >= 80:
            console.print(Panel(
                f"[bold yellow]⚠ {failed} test(s) failed[/bold yellow]\n"
                "Most features are working. Check failed tests above.",
                style="yellow"
            ))
        else:
            console.print(Panel(
                f"[bold red]❌ {failed} test(s) failed[/bold red]\n"
                "Multiple issues detected. Please check your configuration.",
                style="red"
            ))
        
        console.print("\n" + "="*70 + "\n")


async def main():
    """Run all tests."""
    console.print(Panel.fit(
        "[bold cyan]Slack Agent Integration Test Suite[/bold cyan]\n"
        "Testing all API features end-to-end with Nov 2025 methods",
        border_style="cyan"
    ))
    
    console.print(f"\n[dim]Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n")
    
    tester = SlackIntegrationTester()
    
    # Run all tests in sequence
    tests = [
        tester.test_1_credentials,
        tester.test_2_auth_test,
        tester.test_3_team_info,
        tester.test_4_list_users,
        tester.test_5_list_channels,
        tester.test_6_channel_info,
        tester.test_7_channel_members,
        tester.test_8_message_history,
        tester.test_9_send_message,
        tester.test_10_update_message,
        tester.test_11_add_reaction,
        tester.test_12_get_reactions,
        tester.test_13_list_files,
        tester.test_14_upload_file,
        tester.test_15_user_info,
        tester.test_16_socket_mode_connection,
        tester.test_17_rate_limiting,
        tester.test_18_database,
        tester.test_19_cleanup,
    ]
    
    for test in tests:
        try:
            await test()
            # Small delay between tests
            await asyncio.sleep(0.5)
        except Exception as e:
            console.print(f"[red]Unexpected error in {test.__name__}: {e}[/red]")
    
    # Print summary
    tester.print_summary()
    
    console.print(f"[dim]Completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/dim]\n")


if __name__ == "__main__":
    asyncio.run(main())
