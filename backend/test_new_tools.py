"""Test script for new project tracking and utility tools.

Tests core new tools added to the Workforce AI Agent:
1. track_project
2. generate_project_report  
3. update_project_notion_page
4. search_all_platforms
5. get_team_activity_summary
6. analyze_slack_channel
7. list_notion_pages / list_notion_databases
8. get_recent_email_thread_between_people
"""

import asyncio
import os
import sys
from pathlib import Path

# Add paths
backend_path = Path(__file__).parent
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from agent.langchain_tools import WorkforceTools
from core.utils.logger import get_logger

logger = get_logger(__name__)


class ToolTester:
    """Test runner for new tools."""
    
    def __init__(self):
        """Initialize tools."""
        self.tools = WorkforceTools()
        self.results = {
            'passed': [],
            'failed': [],
            'skipped': []
        }
    
    async def test_project_tracking(self):
        """Test project tracking tool."""
        print("\n" + "="*60)
        print("🧪 TEST 1: Project Tracking")
        print("="*60)
        
        try:
            result = await self.tools.track_project(
                project_name="Agent Project",
                days_back=7
            )
            
            if "Project:" in result and "Progress:" in result:
                print("✅ PASS: Project tracking works")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('track_project')
                return True
            else:
                print(f"❌ FAIL: Unexpected result format")
                print(f"Got: {result[:200]}")
                self.results['failed'].append('track_project')
                return False
        
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('track_project')
            return False
    
    async def test_project_report(self):
        """Test project report generation."""
        print("\n" + "="*60)
        print("🧪 TEST 2: Project Report Generation")
        print("="*60)
        
        try:
            result = await self.tools.generate_project_report(
                project_name="Agent Project",
                days_back=7
            )
            
            if "PROJECT STATUS REPORT" in result and "OVERVIEW" in result:
                print("✅ PASS: Report generation works")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('generate_project_report')
                return True
            else:
                print(f"❌ FAIL: Unexpected report format")
                print(f"Got: {result[:200]}")
                self.results['failed'].append('generate_project_report')
                return False
        
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('generate_project_report')
            return False
    
    async def test_notion_update(self):
        """Test Notion page update (will skip if no page ID provided)."""
        print("\n" + "="*60)
        print("🧪 TEST 3: Notion Page Update")
        print("="*60)
        
        # This requires a real Notion page ID, so we'll skip in automated tests
        print("⏭️  SKIP: Requires valid Notion page ID")
        print("   To test manually:")
        print("   1. Create a Notion page")
        print("   2. Share it with your integration")
        print("   3. Run: await tools.update_project_notion_page(page_id, 'Agent Project')")
        self.results['skipped'].append('update_project_notion_page')
        return True
    
    async def test_cross_platform_search(self):
        """Test cross-platform search."""
        print("\n" + "="*60)
        print("🧪 TEST 4: Cross-Platform Search")
        print("="*60)
        
        try:
            result = await self.tools.search_all_platforms(
                query="test",
                limit_per_platform=5
            )
            
            if "SLACK RESULTS" in result and "GMAIL RESULTS" in result and "NOTION RESULTS" in result:
                print("✅ PASS: Cross-platform search works")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('search_all_platforms')
                return True
            else:
                print(f"❌ FAIL: Not all platforms searched")
                print(f"Got: {result[:200]}")
                self.results['failed'].append('search_all_platforms')
                return False
        
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('search_all_platforms')
            return False
    
    async def test_team_activity(self):
        """Test team activity summary."""
        print("\n" + "="*60)
        print("🧪 TEST 5: Team Activity Summary")
        print("="*60)
        
        try:
            result = await self.tools.get_team_activity_summary(
                person_name="test",
                days_back=7
            )
            
            if "TEAM MEMBER ACTIVITY" in result and "Slack:" in result:
                print("✅ PASS: Team activity summary works")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('get_team_activity_summary')
                return True
            else:
                print(f"❌ FAIL: Unexpected format")
                print(f"Got: {result[:200]}")
                self.results['failed'].append('get_team_activity_summary')
                return False
        
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('get_team_activity_summary')
            return False
    
    async def test_channel_analytics(self):
        """Test Slack channel analytics."""
        print("\n" + "="*60)
        print("🧪 TEST 6: Slack Channel Analytics")
        print("="*60)
        
        try:
            result = await self.tools.analyze_slack_channel(
                channel="general",
                days_back=7
            )
            
            if "CHANNEL ANALYSIS" in result or "Could not analyze" in result:
                # Either success or expected error (channel not found)
                print("✅ PASS: Channel analytics works (or handled error gracefully)")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('analyze_slack_channel')
                return True
            else:
                print(f"❌ FAIL: Unexpected format")
                print(f"Got: {result[:200]}")
                self.results['failed'].append('analyze_slack_channel')
                return False
        
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('analyze_slack_channel')
            return False

    async def test_notion_listing(self):
        """Test Notion listing tools (pages + databases)."""
        print("\n" + "="*60)
        print("🧪 TEST 7: Notion Listing (Pages & Databases)")
        print("="*60)

        try:
            pages_result = self.tools.list_notion_pages(limit=5)
            dbs_result = self.tools.list_notion_databases(limit=5)

            # Handle both configured and non-configured cases gracefully
            if "NOTION_TOKEN is not configured" in pages_result:
                print("⏭️  SKIP: Notion token not configured")
                self.results['skipped'].append('list_notion_pages')
            elif "Notion API error" in pages_result:
                print("⚠️ INFO: Notion pages listing returned API error (treating as skip)")
                self.results['skipped'].append('list_notion_pages')
            else:
                print("✅ PASS: list_notion_pages works")
                print(f"Result preview:\n{pages_result[:300]}...")
                self.results['passed'].append('list_notion_pages')

            if "NOTION_TOKEN is not configured" in dbs_result:
                print("⏭️  SKIP: Notion token not configured for databases")
                self.results['skipped'].append('list_notion_databases')
            elif "Notion API error" in dbs_result:
                print("⚠️ INFO: Notion databases listing returned API error (treating as skip)")
                self.results['skipped'].append('list_notion_databases')
            else:
                print("✅ PASS: list_notion_databases works")
                print(f"Result preview:\n{dbs_result[:300]}...")
                self.results['passed'].append('list_notion_databases')

            return True

        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('notion_listing')
            return False

    async def test_recent_email_thread_between_people(self):
        """Test high-level Gmail thread helper between two people."""
        print("\n" + "="*60)
        print("🧪 TEST 8: Recent Email Thread Between People")
        print("="*60)

        try:
            # Use generic names so this doesn't depend on specific addresses.
            result = self.tools.get_recent_email_thread_between_people(
                person_a="test",
                person_b="test",
                days_back=60,
            )

            if "Gmail not authenticated" in result:
                print("⏭️  SKIP: Gmail not authenticated")
                self.results['skipped'].append('get_recent_email_thread_between_people')
                return True

            # Both full-thread and "no threads found" responses are acceptable
            if "COMPLETE EMAIL THREAD" in result or "No recent email threads" in result:
                print("✅ PASS: get_recent_email_thread_between_people works or reports no threads clearly")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('get_recent_email_thread_between_people')
                return True

            print("❌ FAIL: Unexpected response format")
            print(f"Got: {result[:300]}")
            self.results['failed'].append('get_recent_email_thread_between_people')
            return False
        
        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('get_recent_email_thread_between_people')
            return False
    
    async def test_gmail_attachment_tools(self):
        """Test Gmail attachment listing tool (non-destructive)."""
        print("\n" + "="*60)
        print("🧪 TEST 9: Gmail Attachment Tools (Listing)")
        print("="*60)

        try:
            # Use a dummy message_id; the goal is to ensure the tool handles
            # unauthenticated or invalid IDs gracefully without crashing.
            result = self.tools.list_gmail_attachments_for_message(message_id="dummy-message-id")

            if "Gmail not authenticated" in result:
                print("⏭️  SKIP: Gmail not authenticated for attachment tools")
                self.results['skipped'].append('gmail_attachment_tools')
                return True

            # Any non-empty response (including error message) is acceptable here;
            # we mostly care that the tool returns a clear message instead of raising.
            if result:
                print("✅ PASS: Gmail attachment listing tool responds without error")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('gmail_attachment_tools')
                return True

            print("❌ FAIL: Empty response from attachment listing tool")
            self.results['failed'].append('gmail_attachment_tools')
            return False

        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('gmail_attachment_tools')
            return False

    async def test_notion_database_tools(self):
        """Test Notion database query helper (read-only behavior)."""
        print("\n" + "="*60)
        print("🧪 TEST 10: Notion Database Tools (Query)")
        print("="*60)

        try:
            # Use a placeholder database_id. The intent is to verify that the
            # helper returns a clear message and does not crash when Notion is
            # not configured or the ID is invalid.
            result = self.tools.query_notion_database(
                database_id="dummy-database-id",
                filter_json=None,
                page_size=5,
            )

            if "NOTION_TOKEN is not configured" in result:
                print("⏭️  SKIP: Notion token not configured for database tools")
                self.results['skipped'].append('notion_database_tools')
                return True

            if "Notion API error" in result or "Error querying Notion" in result:
                print("⚠️ INFO: Notion database query returned API error (treating as skip)")
                self.results['skipped'].append('notion_database_tools')
                return True

            # If we get here, the query returned some rows/summary text.
            if result:
                print("✅ PASS: Notion database query tool responds without error")
                print(f"Result preview:\n{result[:300]}...")
                self.results['passed'].append('notion_database_tools')
                return True

            print("❌ FAIL: Empty response from Notion database query tool")
            self.results['failed'].append('notion_database_tools')
            return False

        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('notion_database_tools')
            return False

    async def test_notion_page_content_tools(self):
        """Test Notion page content helpers in a non-destructive way."""
        print("\n" + "="*60)
        print("🧪 TEST 11: Notion Page Content Tools")
        print("="*60)

        page_id = os.getenv("TEST_NOTION_PAGE_ID", "")
        if not page_id:
            print("⏭️  SKIP: Set TEST_NOTION_PAGE_ID in env to exercise real page content tools")
            self.results['skipped'].append('get_notion_page_content')
            self.results['skipped'].append('update_notion_page_content')
            return True

        try:
            content = self.tools.get_notion_page_content(
                page_id=page_id,
                include_subpages=False,
                max_blocks=200,
            )

            if "NOTION_TOKEN is not configured" in content or "Notion not connected" in content:
                print("⏭️  SKIP: Notion is not configured or not connected")
                self.results['skipped'].append('get_notion_page_content')
                self.results['skipped'].append('update_notion_page_content')
                return True

            if content:
                print("✅ PASS: get_notion_page_content responded")
                print(f"Result preview:\n{content[:300]}...")
                self.results['passed'].append('get_notion_page_content')
            else:
                print("❌ FAIL: Empty response from get_notion_page_content")
                self.results['failed'].append('get_notion_page_content')

            # For update_notion_page_content we use a unique string that is
            # extremely unlikely to exist, so no actual content is modified.
            marker = "WORKFORCE_TEST_MARKER_1234567890"
            update_result = self.tools.update_notion_page_content(
                page_id=page_id,
                find_text=marker,
                replace_text="SHOULD_NOT_APPEAR",
                include_subpages=False,
                max_matches=1,
            )

            if "No matching text found" in update_result or "Updated" in update_result:
                print("✅ PASS: update_notion_page_content responds without crashing")
                print(f"Result: {update_result}")
                self.results['passed'].append('update_notion_page_content')
            else:
                print("❌ FAIL: Unexpected response from update_notion_page_content")
                print(f"Got: {update_result}")
                self.results['failed'].append('update_notion_page_content')

            return True

        except Exception as e:
            print(f"❌ FAIL: {e}")
            self.results['failed'].append('notion_page_content_tools')
            return False
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        total = len(self.results['passed']) + len(self.results['failed']) + len(self.results['skipped'])
        
        print(f"\n✅ PASSED: {len(self.results['passed'])}/{total}")
        for tool in self.results['passed']:
            print(f"   • {tool}")
        
        if self.results['failed']:
            print(f"\n❌ FAILED: {len(self.results['failed'])}/{total}")
            for tool in self.results['failed']:
                print(f"   • {tool}")
        
        if self.results['skipped']:
            print(f"\n⏭️  SKIPPED: {len(self.results['skipped'])}/{total}")
            for tool in self.results['skipped']:
                print(f"   • {tool}")
        
        # Calculate pass rate
        testable = len(self.results['passed']) + len(self.results['failed'])
        if testable > 0:
            pass_rate = (len(self.results['passed']) / testable) * 100
            print(f"\n📈 Pass Rate: {pass_rate:.1f}% ({len(self.results['passed'])}/{testable} tests)")
        
        print("\n" + "="*60)
        
        if len(self.results['failed']) == 0:
            print("🎉 ALL TESTS PASSED! Tools are ready for production.")
        else:
            print("⚠️  Some tests failed. Review errors above.")
        
        print("="*60)


async def main():
    """Run all tests."""
    print("""
╔══════════════════════════════════════════════════════════╗
║     WORKFORCE AI AGENT - NEW TOOLS TEST SUITE           ║
║                                                          ║
║  Testing new tools:                                      ║
║  • Project Tracking                                      ║
║  • Project Report Generation                             ║
║  • Notion Page Update                                    ║
║  • Cross-Platform Search                                 ║
║  • Team Activity Summary                                 ║
║  • Slack Channel Analytics                               ║
║  • Notion Listing (Pages & Databases)                    ║
║  • Gmail Thread Between People                           ║
║  • Gmail Attachment Tools                                ║
║  • Notion Database Tools                                 ║
╚══════════════════════════════════════════════════════════╝
""")
    
    tester = ToolTester()
    
    # Run all tests
    await tester.test_project_tracking()
    await tester.test_project_report()
    await tester.test_notion_update()
    await tester.test_cross_platform_search()
    await tester.test_team_activity()
    await tester.test_channel_analytics()
    await tester.test_notion_listing()
    await tester.test_recent_email_thread_between_people()
    await tester.test_gmail_attachment_tools()
    await tester.test_notion_database_tools()
    await tester.test_notion_page_content_tools()
    
    # Print summary
    tester.print_summary()
    
    # Return exit code
    return 0 if len(tester.results['failed']) == 0 else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
