"""Command-line interface for Workforce Agent.

Provides all CLI commands for interacting with Slack, Gmail, and Notion APIs.
Uses Click for command structure and Rich for beautiful terminal output.
"""
import asyncio
import click
from rich.console import Console
from rich.table import Table
from rich.progress import track

from config import Config
from database.db_manager import DatabaseManager
from slack.extractor import ExtractionCoordinator
from slack.sender import MessageSender, FileSender, ReactionManager
from slack.realtime.event_handlers import EventHandlers
from slack.realtime.socket_client import SocketModeClient
from utils.logger import setup_logging, get_logger

console = Console()
logger = get_logger(__name__)


@click.group()
@click.option('--log-level', default='INFO', help='Logging level (DEBUG, INFO, WARNING, ERROR)')
def cli(log_level):
    """Workforce Agent - Extract data from Slack, Gmail, and export to Notion."""
    setup_logging(log_level=log_level)
    Config.create_directories()
    
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        console.print(f"[red]Configuration Error: {e}[/red]")
        console.print("[yellow]Please check your .env file[/yellow]")
        raise click.Abort()


@cli.command()
def init():
    """Initialize database and verify connection."""
    console.print("[bold blue]Initializing Slack Agent...[/bold blue]")
    
    try:
        # Test connection
        from slack_sdk import WebClient
        client = WebClient(token=Config.SLACK_BOT_TOKEN)
        response = client.auth_test()
        
        console.print(f"[green]✓ Connected to Slack[/green]")
        console.print(f"  Workspace: {response['team']}")
        console.print(f"  User: {response['user']}")
        console.print(f"  Team ID: {response['team_id']}")
        console.print(f"  Bot User ID: {response['user_id']}")
        
        # Initialize database
        db = DatabaseManager()
        console.print("[green]✓ Database initialized[/green]")
        
        console.print("[bold green]Initialization complete![/bold green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def verify_credentials():
    """Verify all Slack API credentials are properly configured."""
    console.print("[bold blue]Verifying Slack API Credentials...[/bold blue]\n")
    
    from rich.panel import Panel
    
    # Check Bot Token
    if Config.SLACK_BOT_TOKEN and Config.SLACK_BOT_TOKEN.startswith("xoxb-"):
        console.print("[green]✓ Bot Token[/green] (xoxb-...) - Configured")
        
        # Test bot token
        try:
            from slack_sdk import WebClient
            client = WebClient(token=Config.SLACK_BOT_TOKEN)
            response = client.auth_test()
            console.print(f"  → Workspace: [cyan]{response['team']}[/cyan]")
            console.print(f"  → Team ID: [cyan]{response['team_id']}[/cyan]")
            console.print(f"  → Bot User: [cyan]{response['user']}[/cyan]")
        except Exception as e:
            console.print(f"  [red]✗ Bot token test failed: {e}[/red]")
    else:
        console.print("[red]✗ Bot Token[/red] - Missing or invalid")
    
    # Check App Token
    if Config.SLACK_APP_TOKEN and Config.SLACK_APP_TOKEN.startswith("xapp-"):
        console.print("[green]✓ App-Level Token[/green] (xapp-...) - Configured")
        console.print(f"  → Required for Socket Mode")
    else:
        console.print("[yellow]⚠ App-Level Token[/yellow] - Not configured (required for Socket Mode)")
    
    # Check App ID
    if Config.SLACK_APP_ID:
        console.print(f"[green]✓ App ID[/green] - {Config.SLACK_APP_ID}")
    else:
        console.print("[yellow]⚠ App ID[/yellow] - Not configured")
    
    # Check Client ID
    if Config.SLACK_CLIENT_ID:
        console.print(f"[green]✓ Client ID[/green] - {Config.SLACK_CLIENT_ID}")
    else:
        console.print("[yellow]⚠ Client ID[/yellow] - Not configured (required for OAuth)")
    
    # Check Client Secret
    if Config.SLACK_CLIENT_SECRET:
        masked = Config.SLACK_CLIENT_SECRET[:8] + "..." if len(Config.SLACK_CLIENT_SECRET) > 8 else "***"
        console.print(f"[green]✓ Client Secret[/green] - {masked}")
    else:
        console.print("[yellow]⚠ Client Secret[/yellow] - Not configured (required for OAuth)")
    
    # Check Signing Secret
    if Config.SLACK_SIGNING_SECRET:
        masked = Config.SLACK_SIGNING_SECRET[:8] + "..." if len(Config.SLACK_SIGNING_SECRET) > 8 else "***"
        console.print(f"[green]✓ Signing Secret[/green] - {masked}")
        console.print(f"  → Used for request verification")
    else:
        console.print("[yellow]⚠ Signing Secret[/yellow] - Not configured (required for HTTP webhooks)")
    
    # Check Verification Token
    if Config.SLACK_VERIFICATION_TOKEN:
        console.print(f"[green]✓ Verification Token[/green] - {Config.SLACK_VERIFICATION_TOKEN}")
        console.print(f"  → [dim](Deprecated - use Signing Secret instead)[/dim]")
    else:
        console.print("[dim]○ Verification Token[/dim] - Not configured (deprecated)")
    
    # Summary
    console.print("\n" + "="*60)
    
    required_tokens = all([
        Config.SLACK_BOT_TOKEN,
        Config.SLACK_APP_TOKEN if Config.SOCKET_MODE_ENABLED else True
    ])
    
    if required_tokens:
        console.print(Panel(
            "[bold green]✓ Core credentials are configured![/bold green]\n"
            "You can start using the agent.",
            style="green"
        ))
    else:
        console.print(Panel(
            "[bold red]✗ Missing required credentials[/bold red]\n"
            "Please add SLACK_BOT_TOKEN and SLACK_APP_TOKEN to your .env file.",
            style="red"
        ))
    
    # Additional info
    console.print("\n[dim]Tip: Click 'Show' on Client Secret and Signing Secret in Slack App settings[/dim]")
    console.print("[dim]     Then paste them into your .env file for complete integration[/dim]")


@cli.command()
@click.option('--exclude-archived', is_flag=True, help='Exclude archived channels')
@click.option('--download-files', is_flag=True, help='Download files')
def extract_all(exclude_archived, download_files):
    """Extract all data from workspace (users, channels, messages, files)."""
    console.print("[bold blue]Starting full workspace extraction...[/bold blue]")
    
    if not exclude_archived:
        console.print("[yellow]Note: This will include archived channels[/yellow]")
    
    if not download_files:
        console.print("[yellow]Note: Files will be cataloged but not downloaded[/yellow]")
    
    try:
        coordinator = ExtractionCoordinator()
        results = coordinator.extract_all(
            include_archived=not exclude_archived,
            download_files=download_files
        )
        
        # Display results
        table = Table(title="Extraction Results")
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="green")
        
        stats = results.get("statistics", {})
        table.add_row("Users", str(stats.get("users", 0)))
        table.add_row("Channels", str(stats.get("channels", 0)))
        table.add_row("Messages", str(stats.get("messages", 0)))
        table.add_row("Files", str(stats.get("files", 0)))
        table.add_row("Reactions", str(stats.get("reactions", 0)))
        
        console.print(table)
        console.print("[bold green]Extraction complete![/bold green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def extract_users():
    """Extract all users from workspace."""
    console.print("[bold blue]Extracting users...[/bold blue]")
    
    try:
        coordinator = ExtractionCoordinator()
        coordinator.extract_workspace_info()
        count = coordinator.extract_all_users()
        console.print(f"[green]✓ Extracted {count} users[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
@click.option('--exclude-archived', is_flag=True, help='Exclude archived channels')
def extract_channels(exclude_archived):
    """Extract all channels from workspace."""
    console.print("[bold blue]Extracting channels...[/bold blue]")
    
    try:
        coordinator = ExtractionCoordinator()
        coordinator.extract_workspace_info()
        count = coordinator.extract_all_channels(exclude_archived=exclude_archived)
        console.print(f"[green]✓ Extracted {count} channels[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
@click.option('--exclude-archived', is_flag=True, help='Exclude archived channels')
def extract_messages(exclude_archived):
    """Extract all messages from all channels."""
    console.print("[bold blue]Extracting messages...[/bold blue]")
    console.print("[yellow]Note: This may take a long time due to rate limits[/yellow]")
    
    try:
        coordinator = ExtractionCoordinator()
        coordinator.extract_workspace_info()
        
        # Ensure channels are extracted first
        coordinator.extract_all_channels(exclude_archived=exclude_archived)
        
        results = coordinator.extract_all_messages(include_archived=not exclude_archived)
        
        total = sum(r.get("count", 0) for r in results.values())
        console.print(f"[green]✓ Extracted {total} messages[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
@click.option('--download', is_flag=True, help='Download file contents')
def extract_files(download):
    """Extract file metadata (and optionally download)."""
    console.print("[bold blue]Extracting files...[/bold blue]")
    
    try:
        coordinator = ExtractionCoordinator()
        coordinator.extract_workspace_info()
        count = coordinator.extract_all_files(download=download)
        console.print(f"[green]✓ Extracted {count} files[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def stream():
    """Start real-time event streaming via Socket Mode."""
    console.print("[bold blue]Starting real-time event streaming...[/bold blue]")
    
    if not Config.SOCKET_MODE_ENABLED:
        console.print("[red]Socket Mode is not enabled in config[/red]")
        return
    
    if not Config.SLACK_APP_TOKEN:
        console.print("[red]SLACK_APP_TOKEN is required for Socket Mode[/red]")
        return
    
    try:
        db_manager = DatabaseManager()
        event_handlers = EventHandlers(db_manager=db_manager)
        client = SocketModeClient(
            db_manager=db_manager,
            event_handlers=event_handlers
        )
        
        console.print("[green]✓ Socket Mode client initialized[/green]")
        console.print("[yellow]Press Ctrl+C to stop[/yellow]")
        
        asyncio.run(client.run_forever())
    
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping...[/yellow]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
@click.argument('channel')
@click.argument('message')
@click.option('--thread-ts', help='Reply to thread')
def send(channel, message, thread_ts):
    """Send a message to a channel."""
    console.print(f"[bold blue]Sending message to {channel}...[/bold blue]")
    
    try:
        sender = MessageSender()
        result = sender.send_message(
            channel=channel,
            text=message,
            thread_ts=thread_ts
        )
        
        console.print(f"[green]✓ Message sent[/green]")
        console.print(f"  Channel: {result.get('channel')}")
        console.print(f"  Timestamp: {result.get('ts')}")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
@click.argument('channel')
@click.argument('file_path')
@click.option('--title', help='File title')
@click.option('--comment', help='Initial comment')
def upload(channel, file_path, title, comment):
    """Upload a file to a channel."""
    console.print(f"[bold blue]Uploading file to {channel}...[/bold blue]")
    
    try:
        sender = FileSender()
        result = sender.upload_file_v2(
            channel=channel,
            file_path=file_path,
            title=title,
            initial_comment=comment
        )
        
        console.print(f"[green]✓ File uploaded[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
@click.argument('channel')
@click.argument('timestamp')
@click.argument('emoji')
def react(channel, timestamp, emoji):
    """Add a reaction to a message."""
    console.print(f"[bold blue]Adding reaction...[/bold blue]")
    
    try:
        manager = ReactionManager()
        manager.add_reaction(
            channel=channel,
            timestamp=timestamp,
            emoji=emoji
        )
        
        console.print(f"[green]✓ Reaction added[/green]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def stats():
    """Show database statistics."""
    console.print("[bold blue]Database Statistics[/bold blue]")
    
    try:
        db = DatabaseManager()
        stats = db.get_statistics()
        
        table = Table(title="Slack Agent Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green")
        
        table.add_row("Users", str(stats.get("users", 0)))
        table.add_row("Channels", str(stats.get("channels", 0)))
        table.add_row("Messages", str(stats.get("messages", 0)))
        table.add_row("Files", str(stats.get("files", 0)))
        table.add_row("Reactions", str(stats.get("reactions", 0)))
        
        console.print(table)
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def list_channels():
    """List all channels in workspace."""
    console.print("[bold blue]Channels in Workspace[/bold blue]")
    
    try:
        db = DatabaseManager()
        channels = db.get_all_channels()
        
        table = Table()
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Members", style="magenta")
        
        for channel in channels[:50]:  # Limit to 50
            channel_type = "Private" if channel.is_private else "Public"
            if channel.is_im:
                channel_type = "DM"
            elif channel.is_mpim:
                channel_type = "Group DM"
            
            table.add_row(
                channel.channel_id,
                channel.name or "(unnamed)",
                channel_type,
                str(channel.num_members or 0)
            )
        
        console.print(table)
        
        if len(channels) > 50:
            console.print(f"[yellow]Showing 50 of {len(channels)} channels[/yellow]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
@click.option('--query', default='', help='Gmail search query')
@click.option('--max-messages', default=50, help='Maximum messages to extract')
def gmail_extract(query, max_messages):
    """Extract emails from Gmail and store in database (deprecated).

    Gmail now uses OAuth-based per-user tokens via the web app and
    the Pipelines UI. This CLI command is kept for reference but no
    longer performs a live Gmail sync.
    """
    console.print("[bold blue]Gmail extract via CLI is disabled.[/bold blue]")
    console.print(
        "[yellow]Use the web app Pipelines tab to run a Gmail pipeline "
        "for the currently signed-in user.[/yellow]"
    )


@cli.command()
def gmail_stats():
    """Show Gmail database statistics."""
    console.print("[bold blue]Gmail Database Statistics[/bold blue]")
    
    try:
        db = DatabaseManager()
        stats = db.get_gmail_statistics()
        
        table = Table()
        table.add_column("Category", style="cyan")
        table.add_column("Count", style="green")
        
        table.add_row("Accounts", str(stats.get('accounts', 0)))
        table.add_row("Labels", str(stats.get('labels', 0)))
        table.add_row("Messages", str(stats.get('messages', 0)))
        table.add_row("Threads", str(stats.get('threads', 0)))
        table.add_row("Attachments", str(stats.get('attachments', 0)))
        
        console.print(table)
        
        # Show account details
        with db.get_session() as session:
            from database.models import GmailAccount
            account = session.query(GmailAccount).first()
            if account:
                console.print(f"\n[bold]Account Details:[/bold]")
                console.print(f"  Email: {account.email}")
                console.print(f"  Total Messages: {account.messages_total}")
                console.print(f"  Total Threads: {account.threads_total}")
                console.print(f"\nUnread: {account.unread_count}")
                console.print(f"Starred: {account.starred_count}")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def export_to_notion():
    """Export all Slack data to a Notion page."""
    console.print("[bold blue]Exporting Slack data to Notion...[/bold blue]")
    
    try:
        from notion_export import NotionClient, NotionExporter
        
        notion_client = NotionClient()
        if not notion_client.test_connection():
            console.print("[red]Notion connection failed. Check your NOTION_TOKEN[/red]")
            return
        
        exporter = NotionExporter(notion_client=notion_client)
        page_id = exporter.export_slack_data()
        
        if page_id:
            console.print(f"[green]✓ Exported to Notion page: {page_id}[/green]")
        else:
            console.print("[red]Export failed[/red]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def gmail_notion():
    """Export Gmail data to a Notion page."""
    console.print("[bold blue]Exporting Gmail data to Notion...[/bold blue]")
    
    try:
        from notion_export import NotionClient, NotionExporter
        
        notion_client = NotionClient()
        if not notion_client.test_connection():
            console.print("[red]Notion connection failed. Check your NOTION_TOKEN[/red]")
            return
        
        exporter = NotionExporter(notion_client=notion_client)
        page_id = exporter.export_gmail_data()
        
        if page_id:
            console.print(f"[green]✓ Exported to Notion page: {page_id}[/green]")
        else:
            console.print("[red]Export failed[/red]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


@cli.command()
def export_all_to_notion():
    """Export ENTIRE database (all tables) to a single Notion page."""
    console.print("[bold blue]Exporting entire database to Notion...[/bold blue]")
    
    try:
        from notion_export import NotionClient, FullDatabaseExporter
        
        notion_client = NotionClient()
        if not notion_client.test_connection():
            console.print("[red]Notion connection failed. Check your NOTION_TOKEN[/red]")
            return
        
        exporter = FullDatabaseExporter(notion_client=notion_client)
        page_id = exporter.export_all()
        
        if page_id:
            console.print(f"[green]✓ Exported all data to Notion page: {page_id}[/green]")
        else:
            console.print("[red]Export failed[/red]")
    
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise


if __name__ == "__main__":
    cli()
