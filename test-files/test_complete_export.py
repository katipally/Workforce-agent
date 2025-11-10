"""Test complete database to Notion export."""

from rich.console import Console
from rich.table import Table

console = Console()

def test_export():
    """Test that export command works end-to-end."""
    
    console.print("[bold cyan]Testing Complete Database Export[/bold cyan]\n")
    
    # Check 1: Verify database has data
    console.print("[cyan]1. Checking database...[/cyan]")
    from database.db_manager import DatabaseManager
    from database.models import (
        Workspace, User, Channel, Message, File, Reaction,
        GmailAccount, GmailLabel, GmailThread, GmailMessage, GmailAttachment
    )
    
    db = DatabaseManager()
    with db.get_session() as session:
        slack_counts = {
            "Workspaces": session.query(Workspace).count(),
            "Users": session.query(User).count(),
            "Channels": session.query(Channel).count(),
            "Messages": session.query(Message).count(),
            "Files": session.query(File).count(),
            "Reactions": session.query(Reaction).count(),
        }
        
        gmail_counts = {
            "Accounts": session.query(GmailAccount).count(),
            "Labels": session.query(GmailLabel).count(),
            "Threads": session.query(GmailThread).count(),
            "Messages": session.query(GmailMessage).count(),
            "Attachments": session.query(GmailAttachment).count(),
        }
    
    table = Table(show_header=True, title="Database Contents")
    table.add_column("Table", style="cyan")
    table.add_column("Count", style="green", justify="right")
    
    console.print("\n[bold]Slack Tables:[/bold]")
    slack_table = Table(show_header=False)
    slack_table.add_column("Table", style="cyan")
    slack_table.add_column("Count", style="green", justify="right")
    for name, count in slack_counts.items():
        slack_table.add_row(name, str(count))
    console.print(slack_table)
    
    console.print("\n[bold]Gmail Tables:[/bold]")
    gmail_table = Table(show_header=False)
    gmail_table.add_column("Table", style="cyan")
    gmail_table.add_column("Count", style="green", justify="right")
    for name, count in gmail_counts.items():
        gmail_table.add_row(name, str(count))
    console.print(gmail_table)
    
    total_records = sum(slack_counts.values()) + sum(gmail_counts.values())
    console.print(f"\n[bold]Total Records:[/bold] {total_records}")
    
    if total_records == 0:
        console.print("\n[yellow]⚠ Warning: No data in database![/yellow]")
        console.print("Run these first:")
        console.print("  python main.py extract-all")
        console.print("  python main.py gmail-extract")
        return False
    
    console.print("\n[green]✓ Database has data[/green]")
    
    # Check 2: Verify GmailMessage attributes
    console.print("\n[cyan]2. Verifying GmailMessage model...[/cyan]")
    
    if gmail_counts["Messages"] > 0:
        with db.get_session() as session:
            msg = session.query(GmailMessage).first()
            
            # Check for correct attributes
            required_attrs = ['message_id', 'subject', 'from_email', 'date', 'is_read']
            missing_attrs = []
            
            for attr in required_attrs:
                if not hasattr(msg, attr):
                    missing_attrs.append(attr)
            
            if missing_attrs:
                console.print(f"[red]✗ Missing attributes: {missing_attrs}[/red]")
                return False
            
            console.print("[green]✓ GmailMessage model has correct attributes[/green]")
            console.print(f"  Sample message: {msg.subject or 'No subject'}")
            console.print(f"  From: {msg.from_email or 'N/A'}")
            console.print(f"  Date: {msg.date or 'N/A'}")
            console.print(f"  Read: {msg.is_read}")
    else:
        console.print("[yellow]⚠ No Gmail messages to verify[/yellow]")
    
    # Check 3: Verify exporter can load
    console.print("\n[cyan]3. Testing exporter initialization...[/cyan]")
    
    try:
        from notion_export.full_database_exporter import FullDatabaseExporter
        exporter = FullDatabaseExporter()
        console.print("[green]✓ Exporter initialized successfully[/green]")
    except Exception as e:
        console.print(f"[red]✗ Exporter failed to initialize: {e}[/red]")
        return False
    
    # Check 4: Verify data can be loaded
    console.print("\n[cyan]4. Testing data loading...[/cyan]")
    
    try:
        data = exporter._load_all_data()
        console.print("[green]✓ All data loaded successfully[/green]")
        console.print(f"  Loaded {len(data)} table types")
    except Exception as e:
        console.print(f"[red]✗ Data loading failed: {e}[/red]")
        return False
    
    # Check 5: Verify formatting works
    console.print("\n[cyan]5. Testing data formatting...[/cyan]")
    
    try:
        blocks = exporter._format_all_data(data)
        console.print(f"[green]✓ Data formatted successfully[/green]")
        console.print(f"  Created {len(blocks)} Notion blocks")
        
        if len(blocks) < 10:
            console.print("[yellow]⚠ Warning: Very few blocks created[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Formatting failed: {e}[/red]")
        import traceback
        traceback.print_exc()
        return False
    
    # Summary
    console.print("\n" + "="*60)
    console.print("[bold green]✅ All checks passed![/bold green]\n")
    console.print("[cyan]Ready to export:[/cyan]")
    console.print("  python main.py export-all-to-notion\n")
    console.print(f"[dim]Will export {total_records} records in {len(blocks)} Notion blocks[/dim]")
    
    return True


if __name__ == "__main__":
    success = test_export()
    exit(0 if success else 1)
