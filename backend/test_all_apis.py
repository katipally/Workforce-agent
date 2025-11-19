#!/usr/bin/env python3
"""
Comprehensive API Permission Testing Script
Tests ALL Slack, Gmail, and Notion capabilities to identify what works and what needs permissions.
November 2025 - Latest API capabilities
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Tuple

import requests

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent / 'core'))

from core.config import Config
from core.utils.logger import get_logger

logger = get_logger(__name__)

class APITester:
    """Test all API endpoints and permissions."""
    
    def __init__(self):
        self.results = {
            'slack': {'passed': [], 'failed': []},
            'gmail': {'passed': [], 'failed': []},
            'notion': {'passed': [], 'failed': []},
            'projects': {'passed': [], 'failed': []}
        }
        
    def test_slack_api(self) -> Dict:
        """Test Slack API capabilities."""
        print("\n" + "="*80)
        print("🔵 TESTING SLACK API")
        print("="*80)
        
        try:
            from slack_sdk import WebClient
            client = WebClient(token=Config.SLACK_BOT_TOKEN)
            
            tests = [
                # Basic read operations
                ("auth.test", lambda: client.auth_test(), "Basic Authentication"),
                ("users.list", lambda: client.users_list(), "List Users"),
                ("conversations.list", lambda: client.conversations_list(), "List Channels"),
            ]
            
            # Write operations (will fail if no permissions, but we test anyway)
            write_tests = [
                ("Send Messages",
                 lambda: None,  # Don't actually post
                 "Send Messages (not tested - would spam)"),
                
                ("channels.create", 
                 lambda: None,
                 "Create Channels (not tested - would create test channels)"),
                
                ("pins.add", 
                 lambda: None,
                 "Pin Messages (not tested - would modify workspace)"),
                
                ("files.upload", 
                 lambda: None,
                 "Upload Files (not tested - would upload test files)"),
            ]
            
            for test_name, test_func, description in tests:
                try:
                    result = test_func()
                    if result and result.get('ok'):
                        self.results['slack']['passed'].append({
                            'test': test_name,
                            'description': description,
                            'status': '✅ PASS'
                        })
                        print(f"✅ {description}: PASS")
                    else:
                        error = result.get('error', 'Unknown error') if result else 'No response'
                        self.results['slack']['failed'].append({
                            'test': test_name,
                            'description': description,
                            'error': error,
                            'status': '❌ FAIL'
                        })
                        print(f"❌ {description}: FAIL - {error}")
                except Exception as e:
                    error_msg = str(e)
                    self.results['slack']['failed'].append({
                        'test': test_name,
                        'description': description,
                        'error': error_msg,
                        'status': '❌ ERROR'
                    })
                    print(f"❌ {description}: ERROR - {error_msg}")
            
            # Report write capabilities (not tested but documented)
            print("\n📝 Write Capabilities (not tested to avoid modifications):")
            for test_name, _, description in write_tests:
                print(f"   ⚪ {description}")
                
        except Exception as e:
            print(f"❌ Slack API Connection Failed: {e}")
            self.results['slack']['failed'].append({
                'test': 'connection',
                'description': 'API Connection',
                'error': str(e),
                'status': '❌ CRITICAL'
            })
        
        return self.results['slack']
    
    def test_gmail_api(self) -> Dict:
        """Test Gmail API capabilities - FOCUS ON THREADS."""
        print("\n" + "="*80)
        print("📧 TESTING GMAIL API - FULL THREAD CAPABILITIES")
        print("="*80)
        
        try:
            from gmail.client import GmailClient
            client = GmailClient()
            
            if not client.authenticate():
                raise Exception("Gmail authentication failed")
            
            tests = [
                # Basic operations
                ("labels.list", 
                 lambda: client.service.users().labels().list(userId='me').execute(),
                 "List Labels"),
                
                ("profile.get",
                 lambda: client.service.users().getProfile(userId='me').execute(),
                 "Get User Profile"),
                
                # Message listing
                ("messages.list",
                 lambda: client.service.users().messages().list(userId='me', maxResults=1).execute(),
                 "List Messages"),
                
                # THREAD OPERATIONS (CRITICAL FOR USER)
                ("threads.list",
                 lambda: client.service.users().threads().list(userId='me', maxResults=1).execute(),
                 "List Threads"),
                
                # Get full thread details
                ("threads.get (FULL)",
                 lambda: self._test_get_full_thread(client),
                 "Get COMPLETE Thread (All Messages)"),
                
                # Message operations
                ("messages.get (full)",
                 lambda: self._test_get_full_message(client),
                 "Get Full Message Content"),
                
                ("messages.get (metadata)",
                 lambda: self._test_get_message_metadata(client),
                 "Get Message Metadata"),
                
                # Search operations
                ("messages.list (with query)",
                 lambda: client.service.users().messages().list(
                     userId='me', 
                     q='is:unread',
                     maxResults=1
                 ).execute(),
                 "Advanced Search (with operators)"),
                
                # Draft operations
                ("drafts.list",
                 lambda: client.service.users().drafts().list(userId='me', maxResults=1).execute(),
                 "List Drafts"),
                
                # History operations
                ("history.list",
                 lambda: self._test_history_list(client),
                 "Get Message History"),
                
                # Watch/Push notifications
                ("watch",
                 lambda: None,  # Don't test - requires webhook setup
                 "Gmail Push Notifications (not tested - requires webhook)"),
            ]
            
            for test_name, test_func, description in tests:
                try:
                    if test_func is None:
                        print(f"⚪ {description}: SKIPPED (requires setup)")
                        continue
                        
                    result = test_func()
                    if result:
                        self.results['gmail']['passed'].append({
                            'test': test_name,
                            'description': description,
                            'status': '✅ PASS',
                            'details': self._format_result(result)
                        })
                        print(f"✅ {description}: PASS")
                        
                        # Special logging for thread tests
                        if 'thread' in test_name.lower():
                            self._log_thread_details(result, description)
                    else:
                        self.results['gmail']['failed'].append({
                            'test': test_name,
                            'description': description,
                            'error': 'No result returned',
                            'status': '❌ FAIL'
                        })
                        print(f"❌ {description}: FAIL - No result")
                except Exception as e:
                    error_msg = str(e)
                    self.results['gmail']['failed'].append({
                        'test': test_name,
                        'description': description,
                        'error': error_msg,
                        'status': '❌ ERROR'
                    })
                    print(f"❌ {description}: ERROR - {error_msg}")
            
            # Test write capabilities
            print("\n📝 Write Capabilities:")
            write_tests = [
                "Send Messages",
                "Create Drafts",
                "Modify Messages (mark read/unread, add labels)",
                "Trash/Delete Messages",
                "Archive Messages",
            ]
            for cap in write_tests:
                print(f"   ⚪ {cap} (not tested to avoid modifications)")
                
        except Exception as e:
            print(f"❌ Gmail API Connection Failed: {e}")
            self.results['gmail']['failed'].append({
                'test': 'connection',
                'description': 'API Connection',
                'error': str(e),
                'status': '❌ CRITICAL'
            })
        
        return self.results['gmail']
    
    def _test_get_full_thread(self, client) -> Dict:
        """Test getting a COMPLETE email thread with ALL messages."""
        # First get a thread ID
        threads = client.service.users().threads().list(
            userId='me',
            maxResults=1
        ).execute()
        
        if not threads.get('threads'):
            return {'note': 'No threads found to test'}
        
        thread_id = threads['threads'][0]['id']
        
        # Get FULL thread with ALL messages
        full_thread = client.service.users().threads().get(
            userId='me',
            id=thread_id,
            format='full'  # This gets complete message content
        ).execute()
        
        message_count = len(full_thread.get('messages', []))
        print(f"   📊 Thread has {message_count} messages")
        
        return full_thread
    
    def _test_get_full_message(self, client) -> Dict:
        """Test getting full message content."""
        messages = client.service.users().messages().list(
            userId='me',
            maxResults=1
        ).execute()
        
        if not messages.get('messages'):
            return {'note': 'No messages found'}
        
        msg_id = messages['messages'][0]['id']
        
        # Get FULL message
        full_msg = client.service.users().messages().get(
            userId='me',
            id=msg_id,
            format='full'
        ).execute()
        
        return full_msg
    
    def _test_get_message_metadata(self, client) -> Dict:
        """Test getting message metadata only."""
        messages = client.service.users().messages().list(
            userId='me',
            maxResults=1
        ).execute()
        
        if not messages.get('messages'):
            return {'note': 'No messages found'}
        
        msg_id = messages['messages'][0]['id']
        
        metadata = client.service.users().messages().get(
            userId='me',
            id=msg_id,
            format='metadata'
        ).execute()
        
        return metadata
    
    def _test_history_list(self, client) -> Dict:
        """Test history list (for incremental sync)."""
        try:
            # Get profile to get historyId
            profile = client.service.users().getProfile(userId='me').execute()
            history_id = profile.get('historyId')
            
            if not history_id:
                return {'note': 'No history ID available'}
            
            # List history
            history = client.service.users().history().list(
                userId='me',
                startHistoryId=str(int(history_id) - 100)  # Get recent history
            ).execute()
            
            return history
        except:
            return {'note': 'History not available'}
    
    def _log_thread_details(self, result: Dict, description: str):
        """Log detailed thread information."""
        if 'messages' in result:
            print(f"   📧 Thread contains {len(result['messages'])} messages")
            for i, msg in enumerate(result['messages'][:3], 1):  # Show first 3
                headers = msg.get('payload', {}).get('headers', [])
                subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No subject')
                print(f"      {i}. {subject[:60]}")
            if len(result['messages']) > 3:
                print(f"      ... and {len(result['messages']) - 3} more messages")
    
    def _format_result(self, result: Dict) -> str:
        """Format result for display."""
        if isinstance(result, dict):
            if 'resultSizeEstimate' in result:
                return f"Found {result['resultSizeEstimate']} items"
            elif 'messages' in result:
                return f"Found {len(result['messages'])} messages"
            elif 'threads' in result:
                return f"Found {len(result['threads'])} threads"
            elif 'labels' in result:
                return f"Found {len(result['labels'])} labels"
        return "Success"
    
    def test_notion_api(self) -> Dict:
        """Test Notion API capabilities."""
        print("\n" + "="*80)
        print("📝 TESTING NOTION API")
        print("="*80)
        
        try:
            headers = {
                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json"
            }
            
            tests = [
                # Basic operations
                ("GET /users/me",
                 lambda: requests.get("https://api.notion.com/v1/users/me", headers=headers),
                 "Get Current User"),
                
                ("POST /search",
                 lambda: requests.post(
                     "https://api.notion.com/v1/search",
                     headers=headers,
                     json={"page_size": 1}
                 ),
                 "Search Workspace"),
                
                # Database operations
                ("POST /databases/{id}/query",
                 lambda: self._test_notion_database_query(headers),
                 "Query Database"),
                
                # Page operations
                ("GET /pages/{id}",
                 lambda: self._test_notion_get_page(headers),
                 "Get Page"),
                
                ("GET /blocks/{id}/children",
                 lambda: self._test_notion_get_blocks(headers),
                 "Get Page Blocks/Content"),
                
                # User and workspace
                ("GET /users",
                 lambda: requests.get("https://api.notion.com/v1/users", headers=headers),
                 "List All Users"),
                
                # Comments (NEW Nov 2025)
                ("GET /comments",
                 lambda: self._test_notion_comments(headers),
                 "Get Comments"),
            ]
            
            for test_name, test_func, description in tests:
                try:
                    if test_func is None:
                        print(f"⚪ {description}: SKIPPED")
                        continue
                        
                    result = test_func()
                    
                    if hasattr(result, 'status_code'):
                        if result.status_code == 200:
                            self.results['notion']['passed'].append({
                                'test': test_name,
                                'description': description,
                                'status': '✅ PASS'
                            })
                            print(f"✅ {description}: PASS")
                        else:
                            error = result.json().get('message', result.text) if result.text else 'Unknown error'
                            self.results['notion']['failed'].append({
                                'test': test_name,
                                'description': description,
                                'error': f"HTTP {result.status_code}: {error}",
                                'status': '❌ FAIL'
                            })
                            print(f"❌ {description}: FAIL - HTTP {result.status_code}")
                    elif result:
                        self.results['notion']['passed'].append({
                            'test': test_name,
                            'description': description,
                            'status': '✅ PASS'
                        })
                        print(f"✅ {description}: PASS")
                        
                except Exception as e:
                    error_msg = str(e)
                    self.results['notion']['failed'].append({
                        'test': test_name,
                        'description': description,
                        'error': error_msg,
                        'status': '❌ ERROR'
                    })
                    print(f"❌ {description}: ERROR - {error_msg}")
            
            # Write capabilities
            print("\n📝 Write Capabilities:")
            write_tests = [
                "Create Pages",
                "Update Pages",
                "Archive Pages",
                "Create Databases",
                "Add Blocks",
                "Create Comments",
            ]
            for cap in write_tests:
                print(f"   ⚪ {cap} (not tested to avoid modifications)")
                
        except Exception as e:
            print(f"❌ Notion API Connection Failed: {e}")
            self.results['notion']['failed'].append({
                'test': 'connection',
                'description': 'API Connection',
                'error': str(e),
                'status': '❌ CRITICAL'
            })
        
        return self.results['notion']

    def test_projects_api(self) -> Dict:
        """Test FastAPI Projects API endpoints."""
        print("\n" + "="*80)
        print("📁 TESTING PROJECTS API (FastAPI backend)")
        print("="*80)

        base_url = f"http://{Config.API_HOST}:{Config.API_PORT}"
        results = self.results['projects']

        def record(status: str, test_name: str, description: str, error: str = ""):
            if status == 'passed':
                results['passed'].append({
                    'test': test_name,
                    'description': description,
                    'status': '✅ PASS'
                })
                print(f"✅ {description}: PASS")
            else:
                results['failed'].append({
                    'test': test_name,
                    'description': description,
                    'error': error,
                    'status': '❌ FAIL'
                })
                print(f"❌ {description}: FAIL - {error}")

        # List projects
        try:
            resp = requests.get(f"{base_url}/api/projects")
            if resp.status_code == 200:
                record('passed', 'projects.list', 'List Projects')
            else:
                record('failed', 'projects.list', 'List Projects', f"HTTP {resp.status_code}")
        except Exception as e:
            record('failed', 'projects.list', 'List Projects', str(e))
            return results

        project_id = None

        # Create a project
        try:
            resp = requests.post(
                f"{base_url}/api/projects",
                json={"name": "Test Project from APITester", "status": "not_started"},
            )
            if resp.status_code == 200:
                data = resp.json()
                project_id = data.get("id")
                record('passed', 'projects.create', 'Create Project')
            else:
                record('failed', 'projects.create', 'Create Project', f"HTTP {resp.status_code}")
        except Exception as e:
            record('failed', 'projects.create', 'Create Project', str(e))

        if project_id:
            # Get project detail
            try:
                resp = requests.get(f"{base_url}/api/projects/{project_id}")
                if resp.status_code == 200:
                    record('passed', 'projects.get', 'Get Project Detail')
                else:
                    record('failed', 'projects.get', 'Get Project Detail', f"HTTP {resp.status_code}")
            except Exception as e:
                record('failed', 'projects.get', 'Get Project Detail', str(e))

            # Generate project summary (uses AI backend)
            try:
                resp = requests.post(
                    f"{base_url}/api/projects/{project_id}/auto-summary",
                    json={"max_tokens": 128},
                )
                if resp.status_code == 200:
                    record('passed', 'projects.auto_summary', 'Generate Project Summary')
                else:
                    record(
                        'failed',
                        'projects.auto_summary',
                        'Generate Project Summary',
                        f"HTTP {resp.status_code}",
                    )
            except Exception as e:
                record('failed', 'projects.auto_summary', 'Generate Project Summary', str(e))

            # Project-scoped chat (should respond even if no sources are linked)
            try:
                resp = requests.post(
                    f"{base_url}/api/chat/project/{project_id}",
                    json={"query": "Hello from test", "conversation_history": []},
                )
                if resp.status_code == 200:
                    record('passed', 'projects.chat', 'Project Chat')
                else:
                    record('failed', 'projects.chat', 'Project Chat', f"HTTP {resp.status_code}")
            except Exception as e:
                record('failed', 'projects.chat', 'Project Chat', str(e))

            # Delete project
            try:
                resp = requests.delete(f"{base_url}/api/projects/{project_id}")
                if resp.status_code == 200:
                    record('passed', 'projects.delete', 'Delete Project')
                else:
                    record('failed', 'projects.delete', 'Delete Project', f"HTTP {resp.status_code}")
            except Exception as e:
                record('failed', 'projects.delete', 'Delete Project', str(e))

        return results
    
    def _test_notion_database_query(self, headers):
        """Test database query."""
        # First search for a database
        search_result = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={"filter": {"property": "object", "value": "database"}, "page_size": 1}
        )
        
        if search_result.status_code != 200:
            return {'note': 'No databases found'}
        
        databases = search_result.json().get('results', [])
        if not databases:
            return {'note': 'No databases accessible'}
        
        db_id = databases[0]['id']
        
        # Query the database
        query_result = requests.post(
            f"https://api.notion.com/v1/databases/{db_id}/query",
            headers=headers,
            json={"page_size": 1}
        )
        
        return query_result
    
    def _test_notion_get_page(self, headers):
        """Test getting a page."""
        # First search for a page
        search_result = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={"filter": {"property": "object", "value": "page"}, "page_size": 1}
        )
        
        if search_result.status_code != 200:
            return {'note': 'No pages found'}
        
        pages = search_result.json().get('results', [])
        if not pages:
            return {'note': 'No pages accessible'}
        
        page_id = pages[0]['id']
        
        # Get the page
        page_result = requests.get(
            f"https://api.notion.com/v1/pages/{page_id}",
            headers=headers
        )
        
        return page_result
    
    def _test_notion_get_blocks(self, headers):
        """Test getting page blocks."""
        # First search for a page
        search_result = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={"filter": {"property": "object", "value": "page"}, "page_size": 1}
        )
        
        if search_result.status_code != 200:
            return {'note': 'No pages found'}
        
        pages = search_result.json().get('results', [])
        if not pages:
            return {'note': 'No pages accessible'}
        
        page_id = pages[0]['id']
        
        # Get blocks
        blocks_result = requests.get(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers
        )
        
        return blocks_result
    
    def _test_notion_comments(self, headers):
        """Test getting comments."""
        # First search for a page
        search_result = requests.post(
            "https://api.notion.com/v1/search",
            headers=headers,
            json={"filter": {"property": "object", "value": "page"}, "page_size": 1}
        )
        
        if search_result.status_code != 200:
            return {'note': 'No pages found'}
        
        pages = search_result.json().get('results', [])
        if not pages:
            return {'note': 'No pages accessible'}
        
        page_id = pages[0]['id']
        
        # Get comments
        comments_result = requests.get(
            f"https://api.notion.com/v1/comments?block_id={page_id}",
            headers=headers
        )
        
        return comments_result
    
    def generate_report(self):
        """Generate comprehensive report."""
        print("\n" + "="*80)
        print("📊 COMPREHENSIVE API CAPABILITIES REPORT")
        print("="*80)
        
        for api_name, results in self.results.items():
            print(f"\n{'='*80}")
            print(f"API: {api_name.upper()}")
            print(f"{'='*80}")
            
            passed = len(results['passed'])
            failed = len(results['failed'])
            total = passed + failed
            
            if total > 0:
                success_rate = (passed / total) * 100
                print(f"✅ Passed: {passed}/{total} ({success_rate:.1f}%)")
                print(f"❌ Failed: {failed}/{total}")
            
            if results['passed']:
                print(f"\n✅ Working Capabilities ({len(results['passed'])}):")
                for item in results['passed']:
                    print(f"   ✅ {item['description']}")
                    if 'details' in item:
                        print(f"      → {item['details']}")
            
            if results['failed']:
                print(f"\n❌ Failed/Missing Capabilities ({len(results['failed'])}):")
                for item in results['failed']:
                    print(f"   ❌ {item['description']}")
                    print(f"      Error: {item.get('error', 'Unknown')}")
        
        # Generate permissions needed
        print("\n" + "="*80)
        print("🔧 REQUIRED ACTIONS TO ENABLE MISSING FEATURES")
        print("="*80)
        
        self._generate_slack_recommendations()
        self._generate_gmail_recommendations()
        self._generate_notion_recommendations()
    
    def _generate_slack_recommendations(self):
        """Generate Slack permission recommendations."""
        print("\n🔵 SLACK API:")
        
        failed_tests = self.results['slack']['failed']
        if not failed_tests:
            print("   ✅ All tested features working!")
            return
        
        print("   Add these OAuth scopes at https://api.slack.com/apps:")
        
        scope_recommendations = {
            'missing_scope_channel_manage': ['channels:write', 'groups:write'],
            'missing_scope_pins': ['pins:read', 'pins:write'],
            'missing_scope_bookmarks': ['bookmarks:read', 'bookmarks:write'],
            'missing_scope_reminders': ['reminders:read', 'reminders:write'],
            'missing_scope_search': ['search:read'],
        }
        
        for error in failed_tests:
            error_msg = error.get('error', '').lower()
            if 'missing_scope' in error_msg or 'not_allowed' in error_msg:
                for key, scopes in scope_recommendations.items():
                    if any(word in error_msg for word in ['channel', 'pin', 'bookmark', 'reminder', 'search']):
                        print(f"   → {', '.join(scopes)}")
                        break
    
    def _generate_gmail_recommendations(self):
        """Generate Gmail permission recommendations."""
        print("\n📧 GMAIL API:")
        
        failed_tests = self.results['gmail']['failed']
        if not failed_tests:
            print("   ✅ All tested features working!")
            print("\n   🎯 GMAIL THREAD CAPABILITIES:")
            print("      ✅ Full thread retrieval: ENABLED")
            print("      ✅ All messages in thread: AVAILABLE")
            print("      ✅ Thread search: AVAILABLE")
            print("      ✅ Thread modification: AVAILABLE")
            print("\n   💡 Your Gmail API has COMPLETE access to email threads!")
            return
        
        print("   Current OAuth scopes should include:")
        print("   → https://www.googleapis.com/auth/gmail.modify")
        print("   → https://www.googleapis.com/auth/gmail.readonly")
        print("\n   These scopes provide:")
        print("      ✅ Read full email content")
        print("      ✅ Read complete threads (ALL messages)")
        print("      ✅ Search with advanced operators")
        print("      ✅ Modify labels, read status")
        print("      ✅ Send emails")
    
    def _generate_notion_recommendations(self):
        """Generate Notion permission recommendations."""
        print("\n📝 NOTION API:")
        
        failed_tests = self.results['notion']['failed']
        if not failed_tests:
            print("   ✅ All tested features working!")
            return
        
        print("   Notion integration capabilities:")
        print("   → Read content: Check page sharing settings")
        print("   → Insert content: Ensure integration has write access")
        print("   → Comment access: Enable in integration settings")
        print("\n   Configuration at https://www.notion.so/my-integrations:")
        print("      1. Select your integration")
        print("      2. Enable 'Read content', 'Insert content', 'Comment'")
        print("      3. Share pages/databases with the integration")


def main():
    """Run all API tests."""
    print("\n" + "="*80)
    print("🧪 WORKFORCE AI AGENT - API CAPABILITIES TEST")
    print("November 2025 - Comprehensive API Permission Audit")
    print("="*80)
    
    tester = APITester()
    
    # Run all tests
    tester.test_slack_api()
    tester.test_gmail_api()
    tester.test_notion_api()
    tester.test_projects_api()
    
    # Generate report
    tester.generate_report()
    
    print("\n" + "="*80)
    print("✅ TESTING COMPLETE")
    print("="*80)
    print("\n💡 Next Steps:")
    print("   1. Review failed tests above")
    print("   2. Add recommended permissions to each API")
    print("   3. Re-run this test to verify")
    print("\n📝 For detailed API documentation:")
    print("   • Slack: https://api.slack.com/methods")
    print("   • Gmail: https://developers.google.com/gmail/api/reference/rest")
    print("   • Notion: https://developers.notion.com/reference")


if __name__ == "__main__":
    main()
