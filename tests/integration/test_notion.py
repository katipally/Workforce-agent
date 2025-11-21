"""Comprehensive Notion Integration Test Suite.

Tests all Notion functionality:
- Authentication
- Connection
- Page creation
- Data export
- Block formatting
"""

import sys
from datetime import datetime
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
from notion_export import NotionClient, NotionExporter

console = Console()


class NotionIntegrationTest:
    """Comprehensive Notion integration test."""
    
    def __init__(self):
        self.results = []
        self.notion_client = None
        self.db = None
    
    def log_result(self, test_name: str, passed: bool, message: str = ""):
        """Log test result."""
        self.results.append({"test": test_name, "passed": passed, "message": message})
        status = "✓" if passed else "✗"
        color = "green" if passed else "red"
        console.print(f"[{color}]{status}[/{color}] {test_name}")
        if message:
            console.print(f"   {message}")
    
    def test_configuration(self) -> bool:
        """Test Notion configuration."""
        console.print("\n[bold cyan]1. Configuration[/bold cyan]")
        
        if not Config.NOTION_TOKEN:
            self.log_result("Notion Token", False, "NOTION_TOKEN not configured")
            return False
        
        if not (Config.NOTION_TOKEN.startswith("secret_") or Config.NOTION_TOKEN.startswith("ntn_")):
            self.log_result("Notion Token", False, "Invalid token format")
            return False
        
        self.log_result("Notion Token", True, f"Token configured ({Config.NOTION_TOKEN[:10]}...)")
        
        if not Config.NOTION_PARENT_PAGE_ID:
            self.log_result("Parent Page ID", False, "NOTION_PARENT_PAGE_ID not configured")
            return False
        
        self.log_result("Parent Page ID", True, f"Page ID: {Config.NOTION_PARENT_PAGE_ID}")
        return True
    
    def test_imports(self) -> bool:
        """Test module imports."""
        console.print("\n[bold cyan]2. Module Imports[/bold cyan]")
        
        try:
            from notion_client import Client
            self.log_result("notion-client SDK", True, "Module imported")
        except ImportError as e:
            self.log_result("notion-client SDK", False, f"Import failed: {e}")
            return False
        
        try:
            from notion_export import NotionClient, NotionExporter
            self.log_result("notion_export module", True, "Module imported")
            return True
        except ImportError as e:
            self.log_result("notion_export module", False, f"Import failed: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test Notion API connection."""
        console.print("\n[bold cyan]3. API Connection[/bold cyan]")
        
        try:
            self.notion_client = NotionClient()
            self.log_result("Client Initialization", True, "Client created")
        except Exception as e:
            self.log_result("Client Initialization", False, f"Error: {e}")
            return False
        
        try:
            if self.notion_client.test_connection():
                self.log_result("API Connection", True, "Connected to Notion")
                return True
            else:
                self.log_result("API Connection", False, "Connection test failed")
                return False
        except Exception as e:
            self.log_result("API Connection", False, f"Error: {e}")
            return False
    
    def test_page_access(self) -> bool:
        """Test parent page access."""
        console.print("\n[bold cyan]4. Parent Page Access[/bold cyan]")
        
        if not self.notion_client:
            self.log_result("Page Access", False, "Client not initialized")
            return False
        
        try:
            page_id = self.notion_client.normalize_page_id(Config.NOTION_PARENT_PAGE_ID)
            page = self.notion_client.client.pages.retrieve(page_id=page_id)
            
            page_title = "Untitled"
            if "properties" in page:
                for prop_name, prop_data in page["properties"].items():
                    if prop_data.get("type") == "title":
                        title_array = prop_data.get("title", [])
                        if title_array:
                            page_title = title_array[0].get("plain_text", "Untitled")
                        break
            
            self.log_result("Parent Page Access", True, f"Page found: '{page_title}'")
            return True
        except Exception as e:
            error_msg = str(e)
            
            if "object_not_found" in error_msg or "404" in error_msg:
                self.log_result("Parent Page Access", False, "Page not found. Check NOTION_PARENT_PAGE_ID")
            elif "unauthorized" in error_msg or "401" in error_msg:
                self.log_result("Parent Page Access", False, "Unauthorized. Check NOTION_TOKEN")
            elif "restricted" in error_msg or "403" in error_msg:
                self.log_result("Parent Page Access", False, "Access denied. Share page with integration (••• menu → Add connections)")
            else:
                self.log_result("Parent Page Access", False, f"Error: {error_msg}")
            return False
    
    def test_page_creation(self) -> bool:
        """Test page creation."""
        console.print("\n[bold cyan]5. Page Creation[/bold cyan]")
        
        if not self.notion_client:
            self.log_result("Page Creation", False, "Client not initialized")
            return False
        
        try:
            test_page = self.notion_client.create_page(
                parent_id=Config.NOTION_PARENT_PAGE_ID,
                title=f"Test Page - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                blocks=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"text": {"content": "✓ Test page created successfully"}}]
                        }
                    }
                ]
            )
            
            page_url = test_page.get("url", "N/A")
            self.log_result("Page Creation", True, f"Page created!\nURL: {page_url}")
            return True
        except Exception as e:
            self.log_result("Page Creation", False, f"Error: {e}")
            return False
    
    def test_database(self) -> bool:
        """Test Slack database access."""
        console.print("\n[bold cyan]6. Slack Database[/bold cyan]")
        
        try:
            self.db = DatabaseManager()
            stats = self.db.get_statistics()
            
            self.log_result("Database Connection", True, f"Users: {stats['users']}, Channels: {stats['channels']}, Messages: {stats['messages']}")
            return True
        except Exception as e:
            self.log_result("Database Connection", False, f"Error: {e}")
            return False
    
    def test_data_export(self) -> bool:
        """Test full data export."""
        console.print("\n[bold cyan]7. Data Export[/bold cyan]")
        
        if not self.db:
            self.log_result("Data Export", False, "Database not initialized")
            return False
        
        if not self.notion_client:
            self.log_result("Data Export", False, "Notion client not initialized")
            return False
        
        try:
            exporter = NotionExporter(notion_token=Config.NOTION_TOKEN)
            result = exporter.export_all(parent_page_id=Config.NOTION_PARENT_PAGE_ID)
            
            if result and result.get("url"):
                page_url = result.get("url")
                self.log_result("Data Export", True, f"Export successful!\nURL: {page_url}")
                return True
            else:
                self.log_result("Data Export", False, "Export failed")
                return False
        except Exception as e:
            self.log_result("Data Export", False, f"Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def run_all_tests(self):
        """Run all tests."""
        console.print(Panel.fit(
            "[bold cyan]Notion Integration Test Suite[/bold cyan]\n"
            "Testing Notion API functionality",
            border_style="cyan"
        ))
        
        config_ok = self.test_configuration()
        if not config_ok:
            self.print_summary()
            return
        
        import_ok = self.test_imports()
        if not import_ok:
            self.print_summary()
            return
        
        connection_ok = self.test_connection()
        page_access_ok = self.test_page_access() if connection_ok else False
        page_creation_ok = self.test_page_creation() if page_access_ok else False
        db_ok = self.test_database()
        export_ok = self.test_data_export() if db_ok and page_access_ok else False
        
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
            console.print("\n[bold green]✅ All Notion tests passed![/bold green]")
            console.print("\n[cyan]Notion integration fully operational:[/cyan]")
            console.print("  • Authentication working")
            console.print("  • Page creation working")
            console.print("  • Data export working")
            console.print("\n[cyan]You can now export Slack data to Notion:[/cyan]")
            console.print("  python main.py export-to-notion")
        else:
            console.print("\n[bold red]❌ Some tests failed[/bold red]")
            console.print("\n[yellow]Common fixes:[/yellow]")
            console.print("1. Set NOTION_TOKEN and NOTION_PARENT_PAGE_ID in .env")
            console.print("2. Share the parent page with your integration")
            console.print("3. Run: pip install notion-client")


def main():
    """Run tests."""
    tester = NotionIntegrationTest()
    tester.run_all_tests()


if __name__ == "__main__":
    main()
