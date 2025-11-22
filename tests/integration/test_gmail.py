"""Comprehensive Gmail API Integration Test Suite.

Tests all Gmail functionality:
- Authentication
- Profile/account extraction
- Labels extraction
- Message extraction
- Thread extraction
- Attachments
- Notion export
- Database operations
"""

import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Ensure backend core modules are importable when running from repo root
ROOT = Path(__file__).resolve().parents[2]
BACKEND_CORE = ROOT / "backend" / "core"
if str(BACKEND_CORE) not in sys.path:
    sys.path.insert(0, str(BACKEND_CORE))

from config import Config
from database.db_manager import DatabaseManager
from gmail import GmailClient, GmailExtractor, GmailNotionExporter

console = Console()


class GmailIntegrationTest:
    """Comprehensive Gmail integration test."""
    
    def __init__(self):
        self.results = []
        self.client = None
        self.db = None
        self.extractor = None
    
    def log_result(self, test_name: str, passed: bool, message: str = ""):
        """Log test result."""
        self.results.append({"test": test_name, "passed": passed, "message": message})
        status = "✓" if passed else "✗"
        color = "green" if passed else "red"
        console.print(f"[{color}]{status}[/{color}] {test_name}")
        if message:
            console.print(f"   {message}")
    
    def test_configuration(self) -> bool:
        """Test Gmail configuration."""
        console.print("\n[bold cyan]1. Configuration[/bold cyan]")
        
        import os
        credentials_file = os.getenv('GMAIL_CREDENTIALS_FILE', 'credentials.json')
        
        if not os.path.exists(credentials_file):
            self.log_result(
                "Credentials File",
                False,
                f"File not found: {credentials_file}\nDownload from Google Cloud Console"
            )
            return False
        
        self.log_result("Credentials File", True, f"Found: {credentials_file}")
        return True
    
    def test_authentication(self) -> bool:
        """Test Gmail API authentication."""
        console.print("\n[bold cyan]2. Authentication[/bold cyan]")
        
        try:
            self.client = GmailClient()
            success = self.client.authenticate()
            
            if success and self.client.user_email:
                self.log_result(
                    "Gmail Authentication",
                    True,
                    f"Connected: {self.client.user_email}"
                )
                return True
            else:
                self.log_result("Gmail Authentication", False, "Authentication failed")
                return False
        except Exception as e:
            self.log_result("Gmail Authentication", False, f"Error: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test API connection."""
        console.print("\n[bold cyan]3. API Connection[/bold cyan]")
        
        if not self.client:
            self.log_result("API Connection", False, "Client not initialized")
            return False
        
        try:
            if self.client.test_connection():
                profile = self.client.get_profile()
                email = profile.get('emailAddress', 'Unknown')
                msg_total = profile.get('messagesTotal', 0)
                thread_total = profile.get('threadsTotal', 0)
                
                self.log_result(
                    "API Connection",
                    True,
                    f"{email}: {msg_total} messages, {thread_total} threads"
                )
                return True
            else:
                self.log_result("API Connection", False, "Connection test failed")
                return False
        except Exception as e:
            self.log_result("API Connection", False, f"Error: {e}")
            return False
    
    def test_database(self) -> bool:
        """Test database initialization."""
        console.print("\n[bold cyan]4. Database[/bold cyan]")
        
        try:
            self.db = DatabaseManager()
            self.log_result("Database Init", True, "Database initialized")
            return True
        except Exception as e:
            self.log_result("Database Init", False, f"Error: {e}")
            return False
    
    def test_extractor_init(self) -> bool:
        """Test extractor initialization."""
        console.print("\n[bold cyan]5. Extractor Initialization[/bold cyan]")
        
        try:
            self.extractor = GmailExtractor(gmail_client=self.client, db_manager=self.db)
            self.log_result("Extractor Init", True, "Extractor initialized")
            return True
        except Exception as e:
            self.log_result("Extractor Init", False, f"Error: {e}")
            return False
    
    def test_extract_profile(self) -> bool:
        """Test profile extraction."""
        console.print("\n[bold cyan]6. Extract Profile[/bold cyan]")
        
        if not self.extractor:
            self.log_result("Extract Profile", False, "Extractor not initialized")
            return False
        
        try:
            profile = self.extractor.extract_profile()
            if profile:
                email = profile.get('emailAddress', 'Unknown')
                self.log_result("Extract Profile", True, f"Profile saved: {email}")
                return True
            else:
                self.log_result("Extract Profile", False, "No profile data")
                return False
        except Exception as e:
            self.log_result("Extract Profile", False, f"Error: {e}")
            return False
    
    def test_extract_labels(self) -> bool:
        """Test labels extraction."""
        console.print("\n[bold cyan]7. Extract Labels[/bold cyan]")
        
        if not self.extractor:
            self.log_result("Extract Labels", False, "Extractor not initialized")
            return False
        
        try:
            count = self.extractor.extract_labels()
            if count > 0:
                self.log_result("Extract Labels", True, f"Extracted {count} labels")
                return True
            else:
                self.log_result("Extract Labels", False, "No labels found")
                return False
        except Exception as e:
            self.log_result("Extract Labels", False, f"Error: {e}")
            return False
    
    def test_extract_messages(self) -> bool:
        """Test message extraction (limited to 10 for testing)."""
        console.print("\n[bold cyan]8. Extract Messages[/bold cyan]")
        
        if not self.extractor:
            self.log_result("Extract Messages", False, "Extractor not initialized")
            return False
        
        try:
            # Extract only 10 recent messages for testing
            console.print("   [dim]Extracting 10 recent messages...[/dim]")
            count = self.extractor.extract_messages(max_messages=10)
            
            if count >= 0:
                self.log_result("Extract Messages", True, f"Extracted {count} messages")
                return True
            else:
                self.log_result("Extract Messages", False, "Extraction failed")
                return False
        except Exception as e:
            self.log_result("Extract Messages", False, f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def test_database_queries(self) -> bool:
        """Test database query operations."""
        console.print("\n[bold cyan]9. Database Queries[/bold cyan]")
        
        if not self.db:
            self.log_result("Database Queries", False, "Database not initialized")
            return False
        
        try:
            from database.models import GmailAccount, GmailLabel, GmailMessage, GmailThread
            
            with self.db.get_session() as session:
                accounts = session.query(GmailAccount).all()
                labels = session.query(GmailLabel).all()
                messages = session.query(GmailMessage).all()
                threads = session.query(GmailThread).all()
            
            self.log_result(
                "Database Queries",
                True,
                f"{len(accounts)} accounts, {len(labels)} labels, {len(messages)} messages, {len(threads)} threads"
            )
            return True
        except Exception as e:
            self.log_result("Database Queries", False, f"Error: {e}")
            return False
    
    def test_notion_export(self) -> bool:
        """Test Notion export (optional - only if Notion configured)."""
        console.print("\n[bold cyan]10. Notion Export[/bold cyan]")
        
        import os
        if not os.getenv('NOTION_TOKEN') or not os.getenv('NOTION_PARENT_PAGE_ID'):
            self.log_result(
                "Notion Export",
                True,
                "SKIPPED - Notion not configured (optional)"
            )
            return True
        
        try:
            exporter = GmailNotionExporter()
            # Don't actually export in test, just verify it can be initialized
            self.log_result("Notion Export", True, "Exporter initialized (export skipped in test)")
            return True
        except Exception as e:
            self.log_result("Notion Export", False, f"Error: {e}")
            return False
    
    def run_all_tests(self):
        """Run all tests (deprecated file-based Gmail flow).

        Gmail now uses OAuth-based per-user tokens via the web app.
        This integration test suite is kept for historical reference
        but no longer exercises live Gmail APIs.
        """
        console.print(Panel.fit(
            "[bold cyan]Gmail Integration Test Suite[/bold cyan]\n"
            "[yellow]SKIPPED: Gmail now uses OAuth via the Workforce web app.[/yellow]",
            border_style="cyan"
        ))
        console.print(
            "\n[cyan]To verify Gmail, sign in through the web UI and run a Gmail pipeline "
            "from the Pipelines tab.[/cyan]\n"
        )
    
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
            console.print("\n[bold green]✅ All Gmail tests passed![/bold green]")
            console.print("\n[cyan]Gmail integration fully operational:[/cyan]")
            console.print("  • Authentication working")
            console.print("  • Data extraction working")
            console.print("  • Database operations working")
            console.print("\n[cyan]You can now:[/cyan]")
            console.print("  • Extract emails: python main.py gmail-extract")
            console.print("  • Export to Notion: python main.py gmail-notion")
        else:
            console.print("\n[bold red]❌ Some tests failed[/bold red]")
            console.print("\n[yellow]Common fixes:[/yellow]")
            console.print("1. Download credentials.json from Google Cloud Console")
            console.print("2. Enable Gmail API in your Google Cloud project")
            console.print("3. Run authentication flow (opens browser)")


def main():
    """Run tests."""
    tester = GmailIntegrationTest()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
