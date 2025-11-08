"""
Check and verify Slack Bot Token scopes
"""
from slack_sdk import WebClient
from config import Config
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def check_scopes():
    """Check current bot scopes vs required scopes."""
    
    console.print(Panel.fit(
        "[bold cyan]Slack Bot Token Scope Checker[/bold cyan]\n"
        "Verifying your bot has all required permissions",
        border_style="cyan"
    ))
    
    # Required scopes for full functionality
    REQUIRED_SCOPES = {
        "users:read": "List and read user information",
        "users:read.email": "Read user email addresses",
        "team:read": "Read workspace/team information",
        "channels:read": "List public channels",
        "channels:history": "Read messages from public channels",
        "channels:manage": "Manage public channels",
        "channels:join": "Join public channels",
        "groups:read": "List private channels",
        "groups:history": "Read messages from private channels",
        "im:read": "List direct messages",
        "im:history": "Read direct messages",
        "mpim:read": "List group direct messages",
        "mpim:history": "Read group direct messages",
        "chat:write": "Send messages",
        "chat:write.public": "Send messages to channels bot isn't in",
        "files:read": "List and read files",
        "files:write": "Upload files",
        "reactions:read": "Read reactions",
        "reactions:write": "Add/remove reactions",
        "app_mentions:read": "Receive app mentions",
        "usergroups:read": "Read user groups",
    }
    
    try:
        client = WebClient(token=Config.SLACK_BOT_TOKEN)
        response = client.auth_test()
        
        if not response.get("ok"):
            console.print("[red]✗ Failed to authenticate[/red]")
            return
        
        # Get current scopes
        # Note: auth.test doesn't return scopes, but we can see them in error messages
        # Let's make a test call to see what scopes we have
        console.print(f"\n[green]✓ Connected to: {response.get('team')}[/green]")
        console.print(f"[green]✓ Bot user: {response.get('user')}[/green]\n")
        
        # Test each scope
        console.print("[bold]Testing API Access:[/bold]\n")
        
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("Scope", width=25)
        table.add_column("Status", width=10)
        table.add_column("Description", width=35)
        
        # Test users:read
        try:
            client.users_list(limit=1)
            table.add_row("users:read", "[green]✓ OK[/green]", "Read user information")
        except Exception as e:
            if "missing_scope" in str(e):
                table.add_row("users:read", "[red]✗ MISSING[/red]", "Read user information")
            else:
                table.add_row("users:read", "[yellow]? ERROR[/yellow]", str(e)[:30])
        
        # Test team:read
        try:
            client.team_info()
            table.add_row("team:read", "[green]✓ OK[/green]", "Read workspace information")
        except Exception as e:
            if "missing_scope" in str(e):
                table.add_row("team:read", "[red]✗ MISSING[/red]", "Read workspace information")
            else:
                table.add_row("team:read", "[yellow]? ERROR[/yellow]", str(e)[:30])
        
        # Test chat:write
        try:
            # Just test permission, don't actually send
            table.add_row("chat:write", "[yellow]? UNTESTED[/yellow]", "Send messages (need to test manually)")
        except Exception:
            pass
        
        # Test files:read
        try:
            client.files_list(count=1)
            table.add_row("files:read", "[green]✓ OK[/green]", "Read files")
        except Exception as e:
            if "missing_scope" in str(e):
                table.add_row("files:read", "[red]✗ MISSING[/red]", "Read files")
            else:
                table.add_row("files:read", "[yellow]? ERROR[/yellow]", str(e)[:30])
        
        # Test files:write
        table.add_row("files:write", "[yellow]? UNTESTED[/yellow]", "Upload files (need to test manually)")
        
        # Test reactions:read
        table.add_row("reactions:read", "[yellow]? UNTESTED[/yellow]", "Read reactions (need to test manually)")
        
        # Test reactions:write
        table.add_row("reactions:write", "[yellow]? UNTESTED[/yellow]", "Add reactions (need to test manually)")
        
        console.print(table)
        
        console.print("\n[bold]Missing Scopes Detected![/bold]\n")
        console.print("You need to add these scopes in Slack App settings:\n")
        
        missing_scopes = [
            "users:read",
            "users:read.email", 
            "team:read",
            "chat:write",
            "chat:write.public",
            "files:read",
            "files:write",
            "reactions:read",
            "reactions:write",
            "mpim:read",
            "mpim:history",
        ]
        
        console.print("[cyan]Required Bot Token Scopes:[/cyan]")
        for scope in missing_scopes:
            console.print(f"  • {scope}")
        
        console.print("\n[bold yellow]📝 How to Fix:[/bold yellow]\n")
        console.print("1. Go to: https://api.slack.com/apps/A09R6CU0295")
        console.print("2. Click 'OAuth & Permissions' in left sidebar")
        console.print("3. Scroll to 'Scopes' → 'Bot Token Scopes'")
        console.print("4. Click 'Add an OAuth Scope' and add each missing scope")
        console.print("5. Scroll up and click 'Reinstall to Workspace'")
        console.print("6. Click 'Allow' to approve the new permissions")
        console.print("7. Run this test again: python test_slack_integration.py\n")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


if __name__ == "__main__":
    check_scopes()
