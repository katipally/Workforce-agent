#!/usr/bin/env python3
"""Migration script from SQLite to PostgreSQL with pgvector support.

This script performs a complete database migration from SQLite to PostgreSQL,
enabling production-ready storage with AI/RAG capabilities.

Steps performed:
1. Create PostgreSQL database schema (all tables with indexes)
2. Copy all data from SQLite to PostgreSQL (Slack + Gmail)
3. Verify migration (ensure all records match)
4. Enable pgvector extension (for AI/RAG semantic search)

Usage:
    python migrate_to_postgres.py --yes
    
Environment Variables:
    SQLITE_URL: Source SQLite database (default: sqlite:///data/slack_data.db)
    DATABASE_URL: Target PostgreSQL database (default: postgresql://localhost/workforce_agent)

Requirements:
    - PostgreSQL 14+ running locally or remotely
    - pip install psycopg2-binary pgvector
    - Database must already exist: createdb workforce_agent
"""

import os
import sys
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from rich.console import Console
from rich.progress import track
from rich.table import Table
from rich.panel import Panel

from database.models import Base
from database.models import (
    Workspace, User, Channel, Message, File, MessageFile, Reaction, SyncStatus,
    GmailAccount, GmailLabel, GmailThread, GmailMessage, GmailAttachment
)

console = Console()


class DatabaseMigrator:
    """Migrate data from SQLite to PostgreSQL."""
    
    def __init__(self, sqlite_url: str, postgres_url: str):
        """Initialize migrator.
        
        Args:
            sqlite_url: SQLite database URL
            postgres_url: PostgreSQL database URL
        """
        self.sqlite_url = sqlite_url
        self.postgres_url = postgres_url
        
        console.print(f"[cyan]SQLite database:[/] {sqlite_url}")
        console.print(f"[green]PostgreSQL database:[/] {postgres_url}")
        
        # Create engines
        self.sqlite_engine = create_engine(sqlite_url)
        self.postgres_engine = create_engine(postgres_url)
        
        # Create sessions
        SqliteSession = sessionmaker(bind=self.sqlite_engine)
        PostgresSession = sessionmaker(bind=self.postgres_engine)
        
        self.sqlite_session = SqliteSession()
        self.postgres_session = PostgresSession()
    
    def create_postgres_schema(self):
        """Create all tables in PostgreSQL."""
        console.print("\n[bold yellow]Step 1:[/] Creating PostgreSQL schema...")
        
        try:
            # Create all tables
            Base.metadata.create_all(self.postgres_engine)
            console.print("[green]✓[/] Schema created successfully")
            
            # Try to create pgvector extension
            try:
                with self.postgres_engine.connect() as conn:
                    conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
                    conn.commit()
                console.print("[green]✓[/] pgvector extension enabled")
            except Exception as e:
                console.print(f"[yellow]⚠[/] pgvector extension not available: {e}")
                console.print("[yellow]  Vector columns will be created but not functional")
                console.print("[yellow]  Install pgvector to enable semantic search features")
            
            return True
        except Exception as e:
            console.print(f"[red]✗[/] Schema creation failed: {e}")
            return False
    
    def migrate_table(self, model_class, table_name: str):
        """Migrate a single table.
        
        Args:
            model_class: SQLAlchemy model class
            table_name: Display name for progress
        """
        # Check if table exists in SQLite
        inspector = inspect(self.sqlite_engine)
        if model_class.__tablename__ not in inspector.get_table_names():
            console.print(f"[yellow]  Skipping {table_name} (not in SQLite)[/]")
            return 0
        
        # Get all records from SQLite
        sqlite_records = self.sqlite_session.query(model_class).all()
        
        if not sqlite_records:
            console.print(f"[yellow]  Skipping {table_name} (empty)[/]")
            return 0
        
        # Copy to PostgreSQL
        count = 0
        for record in track(sqlite_records, description=f"  Migrating {table_name}"):
            try:
                # Create a dict of all attributes
                record_dict = {}
                for column in model_class.__table__.columns:
                    value = getattr(record, column.name)
                    # Skip embedding column if it exists (will be None anyway)
                    if column.name == 'embedding':
                        continue
                    record_dict[column.name] = value
                
                # Create new record in PostgreSQL
                new_record = model_class(**record_dict)
                self.postgres_session.merge(new_record)
                count += 1
                
                # Commit in batches
                if count % 100 == 0:
                    self.postgres_session.commit()
            
            except Exception as e:
                console.print(f"[red]    Error migrating record: {e}[/]")
                self.postgres_session.rollback()
        
        # Final commit
        self.postgres_session.commit()
        console.print(f"[green]  ✓ Migrated {count} {table_name}[/]")
        
        return count
    
    def migrate_all_data(self):
        """Migrate all tables."""
        console.print("\n[bold yellow]Step 2:[/] Migrating data...")
        
        stats = {}
        
        # Migrate in order of dependencies
        migration_order = [
            (Workspace, "Workspaces"),
            (User, "Users"),
            (Channel, "Channels"),
            (Message, "Messages"),
            (File, "Files"),
            (MessageFile, "Message-File Links"),
            (Reaction, "Reactions"),
            (SyncStatus, "Sync Status"),
            (GmailAccount, "Gmail Accounts"),
            (GmailLabel, "Gmail Labels"),
            (GmailThread, "Gmail Threads"),
            (GmailMessage, "Gmail Messages"),
            (GmailAttachment, "Gmail Attachments"),
        ]
        
        for model, name in migration_order:
            stats[name] = self.migrate_table(model, name)
        
        return stats
    
    def verify_migration(self):
        """Verify data was migrated correctly."""
        console.print("\n[bold yellow]Step 3:[/] Verifying migration...")
        
        table = Table(title="Migration Verification")
        table.add_column("Table", style="cyan")
        table.add_column("SQLite", justify="right", style="yellow")
        table.add_column("PostgreSQL", justify="right", style="green")
        table.add_column("Status", justify="center")
        
        all_models = [
            ("Workspaces", Workspace),
            ("Users", User),
            ("Channels", Channel),
            ("Messages", Message),
            ("Files", File),
            ("Message-File Links", MessageFile),
            ("Reactions", Reaction),
            ("Sync Status", SyncStatus),
            ("Gmail Accounts", GmailAccount),
            ("Gmail Labels", GmailLabel),
            ("Gmail Threads", GmailThread),
            ("Gmail Messages", GmailMessage),
            ("Gmail Attachments", GmailAttachment),
        ]
        
        all_match = True
        
        for name, model in all_models:
            # Check if table exists in SQLite
            inspector = inspect(self.sqlite_engine)
            if model.__tablename__ not in inspector.get_table_names():
                continue
            
            sqlite_count = self.sqlite_session.query(model).count()
            postgres_count = self.postgres_session.query(model).count()
            
            match = sqlite_count == postgres_count
            status = "[green]✓[/]" if match else "[red]✗[/]"
            
            table.add_row(
                name,
                str(sqlite_count),
                str(postgres_count),
                status
            )
            
            if not match:
                all_match = False
        
        console.print(table)
        
        if all_match:
            console.print("\n[bold green]✓ Migration verified successfully![/]")
        else:
            console.print("\n[bold red]✗ Migration verification failed - counts don't match[/]")
        
        return all_match
    
    def cleanup(self):
        """Close sessions and engines."""
        self.sqlite_session.close()
        self.postgres_session.close()
        self.sqlite_engine.dispose()
        self.postgres_engine.dispose()


def main():
    """Run migration."""
    # Check for --yes flag
    auto_confirm = '--yes' in sys.argv or '-y' in sys.argv
    
    console.print(Panel.fit(
        "[bold cyan]PostgreSQL Migration Tool[/]\n"
        "Migrating from SQLite to PostgreSQL with pgvector support",
        title="Database Migration",
        border_style="cyan"
    ))
    
    # Get database URLs
    sqlite_url = os.getenv("SQLITE_URL", "sqlite:///data/slack_data.db")
    postgres_url = os.getenv("DATABASE_URL", "postgresql://localhost/workforce_agent")
    
    console.print(f"\n[bold]Source:[/] {sqlite_url}")
    console.print(f"[bold]Destination:[/] {postgres_url}")
    
    # Confirm
    console.print("\n[yellow]⚠ This will copy all data to PostgreSQL.[/]")
    console.print("[yellow]  Existing data in PostgreSQL will be merged/updated.[/]")
    
    if not auto_confirm:
        response = console.input("\n[bold]Continue? (yes/no):[/] ")
        if response.lower() not in ['yes', 'y']:
            console.print("[red]Migration cancelled.[/]")
            return
    else:
        console.print("\n[green]Auto-confirmed (--yes flag)[/]")
    
    # Run migration
    migrator = DatabaseMigrator(sqlite_url, postgres_url)
    
    try:
        # Step 1: Create schema
        if not migrator.create_postgres_schema():
            console.print("[red]Migration failed at schema creation.[/]")
            return
        
        # Step 2: Migrate data
        stats = migrator.migrate_all_data()
        
        # Step 3: Verify
        success = migrator.verify_migration()
        
        # Summary
        console.print("\n" + "="*60)
        console.print("[bold cyan]Migration Summary:[/]")
        total_records = sum(stats.values())
        console.print(f"  Total records migrated: [green]{total_records}[/]")
        console.print(f"  Verification: {'[green]PASSED[/]' if success else '[red]FAILED[/]'}")
        console.print("="*60)
        
        if success:
            console.print("\n[bold green]✓ Migration completed successfully![/]")
            console.print("\n[cyan]Next steps:[/]")
            console.print("  1. Update .env to use PostgreSQL:")
            console.print(f"     DATABASE_URL={postgres_url}")
            console.print("  2. Test your application with PostgreSQL")
            console.print("  3. Backup your SQLite database (keep as backup)")
            console.print("  4. Install pgvector to enable semantic search:")
            console.print("     See documentation/DATABASE_RECOMMENDATIONS.md")
        else:
            console.print("\n[bold red]✗ Migration completed with errors.[/]")
            console.print("  Please review the verification results above.")
    
    except Exception as e:
        console.print(f"\n[bold red]Migration failed: {e}[/]")
        import traceback
        console.print(traceback.format_exc())
    
    finally:
        migrator.cleanup()


if __name__ == "__main__":
    main()
