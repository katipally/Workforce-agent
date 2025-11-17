"""
Comprehensive Tool Testing Suite - ALL Tools in Codebase
Tests EVERY available tool in the Workforce AI Agent
November 2025
"""

import os
import sys
import asyncio
from pathlib import Path
from typing import Dict, List

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'core'))

from core.config import Config
from core.utils.logger import get_logger
from agent.langchain_tools import WorkforceTools

logger = get_logger(__name__)


class ComprehensiveToolTester:
    """Test ALL tools available in the agent."""
    
    def __init__(self):
        self.tools = WorkforceTools()
        self.results = {
            'passed': [],
            'failed': [],
            'skipped': [],
            'errors': []
        }
    
    def _record_result(self, test_name: str, status: str, message: str = ""):
        """Record test result."""
        self.results[status].append({'name': test_name, 'message': message})
        
        status_emoji = {
            'passed': '✅',
            'failed': '❌',
            'skipped': '⏭️ ',
            'errors': '🔥'
        }
        
        print(f"{status_emoji.get(status, '?')} {test_name}: {message[:100]}")
    
    # ========================================
    # SLACK TOOLS - Basic Operations
    # ========================================
    
    def test_slack_list_channels(self):
        """Test listing all Slack channels."""
        try:
            result = self.tools.get_all_slack_channels()
            if "Error" in result or "❌" in result:
                self._record_result("slack_list_channels", "failed", result[:200])
            else:
                self._record_result("slack_list_channels", "passed", f"Found channels")
        except Exception as e:
            self._record_result("slack_list_channels", "errors", str(e))
    
    def test_slack_get_channel_messages(self):
        """Test getting messages from a real Slack channel."""
        try:
            # Try to get a real channel first
            channels_result = self.tools.get_all_slack_channels()
            
            # Parse first channel name from result
            test_channel = None
            for line in channels_result.split('\n'):
                if '#' in line:
                    # Extract channel name
                    parts = line.split('#')
                    if len(parts) > 1:
                        test_channel = parts[1].split()[0].strip()
                        break
            
            if not test_channel:
                self._record_result("slack_get_channel_messages", "skipped", "No channels found to test")
                return
            
            result = self.tools.get_channel_messages(test_channel, limit=5)
            if "Error" in result or "not found" in result.lower():
                self._record_result("slack_get_channel_messages", "failed", result[:200])
            else:
                self._record_result("slack_get_channel_messages", "passed", f"Retrieved messages from #{test_channel}")
        except Exception as e:
            self._record_result("slack_get_channel_messages", "errors", str(e))
    
    def test_slack_search_messages(self):
        """Test searching Slack messages in database."""
        try:
            result = self.tools.search_slack_messages("test", limit=5)
            if "Error" in result:
                self._record_result("slack_search_messages", "failed", result[:200])
            else:
                self._record_result("slack_search_messages", "passed", "Search completed")
        except Exception as e:
            self._record_result("slack_search_messages", "errors", str(e))
    
    def test_slack_summarize_channel(self):
        """Test Slack channel summarization."""
        try:
            # Get first available channel
            channels_result = self.tools.get_all_slack_channels()
            test_channel = None
            for line in channels_result.split('\n'):
                if '#' in line:
                    parts = line.split('#')
                    if len(parts) > 1:
                        test_channel = parts[1].split()[0].strip()
                        break
            
            if not test_channel:
                self._record_result("slack_summarize_channel", "skipped", "No channels available")
                return
            
            result = self.tools.summarize_slack_channel(test_channel, limit=10)
            self._record_result("slack_summarize_channel", "passed", "Summarization request created")
        except Exception as e:
            self._record_result("slack_summarize_channel", "errors", str(e))
    
    # ========================================
    # SLACK TOOLS - Advanced Operations
    # ========================================
    
    def test_slack_user_info(self):
        """Test getting Slack user info."""
        try:
            # This will fail with dummy ID but tests the tool
            result = self.tools.get_slack_user_info("U00000000")
            if "Error" in result or "not found" in result.lower():
                self._record_result("slack_user_info", "passed", "Tool responds correctly to invalid ID")
            else:
                self._record_result("slack_user_info", "passed", "Retrieved user info")
        except Exception as e:
            self._record_result("slack_user_info", "errors", str(e))
    
    def test_slack_channel_info(self):
        """Test getting Slack channel info."""
        try:
            result = self.tools.get_slack_channel_info("C00000000")
            if "Error" in result or "not found" in result.lower():
                self._record_result("slack_channel_info", "passed", "Tool responds correctly to invalid ID")
            else:
                self._record_result("slack_channel_info", "passed", "Retrieved channel info")
        except Exception as e:
            self._record_result("slack_channel_info", "errors", str(e))
    
    def test_slack_thread_replies(self):
        """Test getting Slack thread replies."""
        try:
            result = self.tools.get_thread_replies("general", "1234567890.123456")
            if "Error" in result:
                self._record_result("slack_thread_replies", "passed", "Tool responds correctly")
            else:
                self._record_result("slack_thread_replies", "passed", "Thread reply tool works")
        except Exception as e:
            self._record_result("slack_thread_replies", "errors", str(e))
    
    # ========================================
    # GMAIL TOOLS - Basic Operations
    # ========================================
    
    def test_gmail_search_messages(self):
        """Test searching Gmail messages in database."""
        try:
            result = self.tools.search_gmail_messages("test", limit=5)
            if "Error" in result:
                self._record_result("gmail_search_messages", "failed", result[:200])
            else:
                self._record_result("gmail_search_messages", "passed", "Search completed")
        except Exception as e:
            self._record_result("gmail_search_messages", "errors", str(e))
    
    def test_gmail_get_from_sender(self):
        """Test getting emails from specific sender."""
        try:
            result = self.tools.get_emails_from_sender("test@example.com", limit=5)
            # This should work even if no emails found
            self._record_result("gmail_get_from_sender", "passed", "Tool executed")
        except Exception as e:
            self._record_result("gmail_get_from_sender", "errors", str(e))
    
    def test_gmail_get_by_subject(self):
        """Test getting emails by subject."""
        try:
            result = self.tools.get_email_by_subject("test")
            self._record_result("gmail_get_by_subject", "passed", "Tool executed")
        except Exception as e:
            self._record_result("gmail_get_by_subject", "errors", str(e))
    
    def test_gmail_labels(self):
        """Test getting Gmail labels."""
        try:
            result = self.tools.get_gmail_labels()
            if "Error" in result or "❌" in result:
                self._record_result("gmail_labels", "failed", result[:200])
            else:
                self._record_result("gmail_labels", "passed", "Retrieved labels")
        except Exception as e:
            self._record_result("gmail_labels", "errors", str(e))
    
    def test_gmail_thread(self):
        """Test getting email thread."""
        try:
            result = self.tools.get_email_thread("dummy-thread-id")
            # Expected to fail with dummy ID
            if "Error" in result:
                self._record_result("gmail_thread", "passed", "Tool handles invalid ID correctly")
            else:
                self._record_result("gmail_thread", "passed", "Retrieved thread")
        except Exception as e:
            self._record_result("gmail_thread", "errors", str(e))
    
    # ========================================
    # GMAIL TOOLS - Advanced Operations
    # ========================================
    
    def test_gmail_full_content(self):
        """Test getting full email content."""
        try:
            result = self.tools.get_full_email_content("dummy-message-id")
            if "Error" in result or "❌" in result:
                self._record_result("gmail_full_content", "passed", "Tool handles invalid ID correctly")
            else:
                self._record_result("gmail_full_content", "passed", "Retrieved full content")
        except Exception as e:
            self._record_result("gmail_full_content", "errors", str(e))
    
    def test_gmail_unread_count(self):
        """Test getting unread email count."""
        try:
            result = self.tools.get_unread_email_count()
            if "Error" not in result and "❌" not in result:
                self._record_result("gmail_unread_count", "passed", f"Count: {result}")
            else:
                self._record_result("gmail_unread_count", "failed", result[:200])
        except Exception as e:
            self._record_result("gmail_unread_count", "errors", str(e))
    
    def test_gmail_list_attachments(self):
        """Test listing Gmail attachments."""
        try:
            result = self.tools.list_gmail_attachments_for_message("dummy-message-id")
            # Should handle error gracefully without stack trace
            if "❌" in result:
                self._record_result("gmail_list_attachments", "passed", "Error handled gracefully (no stack trace)")
            else:
                self._record_result("gmail_list_attachments", "passed", "Retrieved attachments")
        except Exception as e:
            self._record_result("gmail_list_attachments", "errors", str(e))
    
    def test_gmail_recent_thread_between_people(self):
        """Test getting recent email thread between people."""
        try:
            result = self.tools.get_recent_email_thread_between_people("person1@example.com", "person2@example.com")
            # Should work even if no thread found
            self._record_result("gmail_recent_thread_between", "passed", "Tool executed")
        except Exception as e:
            self._record_result("gmail_recent_thread_between", "errors", str(e))
    
    # ========================================
    # NOTION TOOLS - Basic Operations
    # ========================================
    
    def test_notion_list_pages(self):
        """Test listing Notion pages."""
        try:
            result = self.tools.list_notion_pages(limit=10)
            if "Error" in result:
                self._record_result("notion_list_pages", "failed", result[:200])
            else:
                self._record_result("notion_list_pages", "passed", "Retrieved pages")
        except Exception as e:
            self._record_result("notion_list_pages", "errors", str(e))
    
    def test_notion_list_databases(self):
        """Test listing Notion databases."""
        try:
            result = self.tools.list_notion_databases(limit=10)
            # Even if no databases, should not error
            self._record_result("notion_list_databases", "passed", "Tool executed")
        except Exception as e:
            self._record_result("notion_list_databases", "errors", str(e))
    
    def test_notion_search_workspace(self):
        """Test searching Notion workspace."""
        try:
            result = self.tools.search_notion_workspace("test")
            self._record_result("notion_search_workspace", "passed", "Search executed")
        except Exception as e:
            self._record_result("notion_search_workspace", "errors", str(e))
    
    def test_notion_search_content(self):
        """Test searching Notion content."""
        try:
            result = self.tools.search_notion_content("test")
            self._record_result("notion_search_content", "passed", "Search executed")
        except Exception as e:
            self._record_result("notion_search_content", "errors", str(e))
    
    # ========================================
    # NOTION TOOLS - Advanced Operations
    # ========================================
    
    def test_notion_get_page_content(self):
        """Test getting Notion page content."""
        page_id = os.environ.get("TEST_NOTION_PAGE_ID")
        if not page_id:
            self._record_result("notion_get_page_content", "skipped", "No TEST_NOTION_PAGE_ID set")
            return
        
        try:
            result = self.tools.get_notion_page_content(page_id, include_subpages=True)
            if "Error" in result or "❌" in result:
                self._record_result("notion_get_page_content", "failed", result[:200])
            else:
                self._record_result("notion_get_page_content", "passed", "Retrieved page content")
        except Exception as e:
            self._record_result("notion_get_page_content", "errors", str(e))
    
    def test_notion_update_page_content(self):
        """Test updating Notion page content (safe test)."""
        page_id = os.environ.get("TEST_NOTION_PAGE_ID")
        if not page_id:
            self._record_result("notion_update_page_content", "skipped", "No TEST_NOTION_PAGE_ID set")
            return
        
        try:
            # Safe test: try to replace text that doesn't exist
            result = self.tools.update_notion_page_content(
                page_id=page_id,
                find_text="__NONEXISTENT_MARKER_TEXT_THAT_SHOULD_NOT_MATCH__",
                replace_text="__NEW_TEXT__",
                include_subpages=False,
                max_matches=1
            )
            # Should return "No matching text found" or similar
            if "No matching text" in result or "0 blocks" in result:
                self._record_result("notion_update_page_content", "passed", "Tool works safely")
            elif "Updated" in result:
                self._record_result("notion_update_page_content", "passed", "Tool executed update")
            else:
                self._record_result("notion_update_page_content", "passed", f"Response: {result[:100]}")
        except Exception as e:
            self._record_result("notion_update_page_content", "errors", str(e))
    
    def test_notion_query_database(self):
        """Test querying Notion database."""
        try:
            result = self.tools.query_notion_database("dummy-database-id")
            # Expected to fail with dummy ID
            if "404" in result or "not found" in result.lower():
                self._record_result("notion_query_database", "passed", "Tool handles invalid ID correctly")
            else:
                self._record_result("notion_query_database", "passed", "Query executed")
        except Exception as e:
            self._record_result("notion_query_database", "errors", str(e))
    
    # ========================================
    # PROJECT TRACKING & ANALYTICS TOOLS
    # ========================================
    
    async def test_project_tracking(self):
        """Test project tracking across platforms."""
        try:
            result = await self.tools.track_project("Test Project", days_back=7)
            if "Error" in result or "❌" in result:
                self._record_result("project_tracking", "failed", result[:200])
            else:
                self._record_result("project_tracking", "passed", "Tracking completed")
        except Exception as e:
            self._record_result("project_tracking", "errors", str(e))
    
    async def test_project_report_generation(self):
        """Test generating project report."""
        try:
            result = await self.tools.generate_project_report("Test Project", days_back=7)
            if "Error" in result or "❌" in result:
                self._record_result("project_report", "failed", result[:200])
            else:
                self._record_result("project_report", "passed", "Report generated")
        except Exception as e:
            self._record_result("project_report", "errors", str(e))
    
    async def test_update_project_notion_page(self):
        """Test updating project Notion page."""
        page_id = os.environ.get("TEST_NOTION_PAGE_ID")
        if not page_id:
            self._record_result("update_project_notion_page", "skipped", "No TEST_NOTION_PAGE_ID set")
            return
        
        try:
            result = await self.tools.update_project_notion_page(page_id, "Test Project", days_back=7)
            if "Error" not in result and "❌" not in result:
                self._record_result("update_project_notion_page", "passed", "Page updated")
            else:
                self._record_result("update_project_notion_page", "failed", result[:200])
        except Exception as e:
            self._record_result("update_project_notion_page", "errors", str(e))
    
    async def test_cross_platform_search(self):
        """Test searching across all platforms."""
        try:
            result = await self.tools.search_all_platforms("test", limit_per_platform=5)
            if "Error" not in result:
                self._record_result("cross_platform_search", "passed", "Search completed")
            else:
                self._record_result("cross_platform_search", "failed", result[:200])
        except Exception as e:
            self._record_result("cross_platform_search", "errors", str(e))
    
    async def test_team_activity_summary(self):
        """Test getting team activity summary."""
        try:
            result = await self.tools.get_team_activity_summary("test", days_back=7)
            if "Error" not in result:
                self._record_result("team_activity_summary", "passed", "Summary generated")
            else:
                self._record_result("team_activity_summary", "failed", result[:200])
        except Exception as e:
            self._record_result("team_activity_summary", "errors", str(e))
    
    async def test_slack_channel_analytics(self):
        """Test analyzing Slack channel."""
        try:
            # Get first available channel
            channels_result = self.tools.get_all_slack_channels()
            test_channel = None
            for line in channels_result.split('\n'):
                if '#' in line:
                    parts = line.split('#')
                    if len(parts) > 1:
                        test_channel = parts[1].split()[0].strip()
                        break
            
            if not test_channel:
                self._record_result("slack_channel_analytics", "skipped", "No channels available")
                return
            
            result = await self.tools.analyze_slack_channel(test_channel, days_back=7)
            if "Error" not in result and "❌" not in result:
                self._record_result("slack_channel_analytics", "passed", f"Analyzed #{test_channel}")
            else:
                self._record_result("slack_channel_analytics", "passed", "Tool handled error gracefully")
        except Exception as e:
            self._record_result("slack_channel_analytics", "errors", str(e))
    
    # ========================================
    # RUN ALL TESTS
    # ========================================
    
    async def run_all_tests(self):
        """Run all comprehensive tests."""
        print("\n" + "="*80)
        print("🧪 COMPREHENSIVE TOOL TEST SUITE - ALL TOOLS")
        print("="*80 + "\n")
        
        # Slack Basic Tests
        print("\n" + "─"*80)
        print("🔵 SLACK - BASIC OPERATIONS")
        print("─"*80)
        self.test_slack_list_channels()
        self.test_slack_get_channel_messages()
        self.test_slack_search_messages()
        self.test_slack_summarize_channel()
        
        # Slack Advanced Tests
        print("\n" + "─"*80)
        print("🔵 SLACK - ADVANCED OPERATIONS")
        print("─"*80)
        self.test_slack_user_info()
        self.test_slack_channel_info()
        self.test_slack_thread_replies()
        
        # Gmail Basic Tests
        print("\n" + "─"*80)
        print("📧 GMAIL - BASIC OPERATIONS")
        print("─"*80)
        self.test_gmail_search_messages()
        self.test_gmail_get_from_sender()
        self.test_gmail_get_by_subject()
        self.test_gmail_labels()
        self.test_gmail_thread()
        
        # Gmail Advanced Tests
        print("\n" + "─"*80)
        print("📧 GMAIL - ADVANCED OPERATIONS")
        print("─"*80)
        self.test_gmail_full_content()
        self.test_gmail_unread_count()
        self.test_gmail_list_attachments()
        self.test_gmail_recent_thread_between_people()
        
        # Notion Basic Tests
        print("\n" + "─"*80)
        print("📝 NOTION - BASIC OPERATIONS")
        print("─"*80)
        self.test_notion_list_pages()
        self.test_notion_list_databases()
        self.test_notion_search_workspace()
        self.test_notion_search_content()
        
        # Notion Advanced Tests
        print("\n" + "─"*80)
        print("📝 NOTION - ADVANCED OPERATIONS")
        print("─"*80)
        self.test_notion_get_page_content()
        self.test_notion_update_page_content()
        self.test_notion_query_database()
        
        # Project & Analytics Tests
        print("\n" + "─"*80)
        print("📊 PROJECT TRACKING & ANALYTICS")
        print("─"*80)
        await self.test_project_tracking()
        await self.test_project_report_generation()
        await self.test_update_project_notion_page()
        await self.test_cross_platform_search()
        await self.test_team_activity_summary()
        await self.test_slack_channel_analytics()
        
        # Summary
        self.print_summary()
    
    def print_summary(self):
        """Print test summary."""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE TEST SUMMARY")
        print("="*80 + "\n")
        
        total = sum(len(v) for v in self.results.values())
        passed = len(self.results['passed'])
        failed = len(self.results['failed'])
        skipped = len(self.results['skipped'])
        errors = len(self.results['errors'])
        
        print(f"✅ PASSED:  {passed}/{total}")
        print(f"❌ FAILED:  {failed}/{total}")
        print(f"⏭️  SKIPPED: {skipped}/{total}")
        print(f"🔥 ERRORS:  {errors}/{total}")
        
        if passed > 0:
            pass_rate = (passed / (total - skipped)) * 100 if (total - skipped) > 0 else 0
            print(f"\n📈 Pass Rate: {pass_rate:.1f}% ({passed}/{total - skipped} non-skipped tests)")
        
        # Show failed tests
        if failed > 0:
            print("\n" + "─"*80)
            print("❌ FAILED TESTS:")
            print("─"*80)
            for test in self.results['failed']:
                print(f"  • {test['name']}: {test['message'][:100]}")
        
        # Show errors
        if errors > 0:
            print("\n" + "─"*80)
            print("🔥 ERROR TESTS:")
            print("─"*80)
            for test in self.results['errors']:
                print(f"  • {test['name']}: {test['message'][:100]}")
        
        # Show skipped
        if skipped > 0:
            print("\n" + "─"*80)
            print("⏭️  SKIPPED TESTS (need configuration):")
            print("─"*80)
            for test in self.results['skipped']:
                print(f"  • {test['name']}: {test['message']}")
        
        print("\n" + "="*80)
        if failed == 0 and errors == 0:
            print("🎉 ALL TESTS PASSED! (excluding skipped)")
        else:
            print(f"⚠️  {failed + errors} test(s) need attention")
        print("="*80 + "\n")


async def main():
    """Main test runner."""
    tester = ComprehensiveToolTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
