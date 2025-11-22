"""Project Tracking System for Workforce AI Agent.

This module aggregates information across Slack, Gmail, and Notion to:
1. Track project updates from multiple sources
2. Maintain a unified project status
3. Automatically update Notion pages with project progress
4. Identify blockers and action items
5. Generate comprehensive project reports

Key Features:
- Cross-platform information aggregation
- Automatic Notion page updates (not creation)
- Project timeline tracking
- Team member activity tracking
- Smart summarization of updates
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
import asyncio
import json
import re
from pathlib import Path
import sys

from sqlalchemy import or_

# Add core directory to path
core_path = Path(__file__).parent.parent / 'core'
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

from utils.logger import get_logger
from database.models import Message, Channel, User, GmailMessage
from config import Config

logger = get_logger(__name__)


@dataclass
class ProjectUpdate:
    """Represents a single project update from any source."""
    source: str  # 'slack', 'gmail', or 'notion'
    timestamp: datetime
    author: str
    content: str
    channel_or_thread: str
    metadata: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'source': self.source,
            'timestamp': self.timestamp.isoformat(),
            'author': self.author,
            'content': self.content,
            'channel_or_thread': self.channel_or_thread,
            'metadata': self.metadata
        }


@dataclass
class ProjectStatus:
    """Comprehensive project status aggregated from all sources."""
    project_name: str
    last_updated: datetime
    slack_updates: List[ProjectUpdate]
    gmail_updates: List[ProjectUpdate]
    notion_updates: List[ProjectUpdate]
    key_points: List[str]
    action_items: List[str]
    blockers: List[str]
    team_members: List[str]
    progress_percentage: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for reports."""
        return {
            'project_name': self.project_name,
            'last_updated': self.last_updated.isoformat(),
            'total_updates': len(self.slack_updates) + len(self.gmail_updates) + len(self.notion_updates),
            'slack_updates_count': len(self.slack_updates),
            'gmail_updates_count': len(self.gmail_updates),
            'notion_updates_count': len(self.notion_updates),
            'key_points': self.key_points,
            'action_items': self.action_items,
            'blockers': self.blockers,
            'team_members': self.team_members,
            'progress_percentage': self.progress_percentage
        }


class ProjectTracker:
    """Main project tracking system that aggregates cross-platform data."""
    
    def __init__(self, tools_handler):
        """Initialize with access to all API tools.
        
        Args:
            tools_handler: WorkforceTools instance with Slack, Gmail, Notion access
        """
        self.tools = tools_handler
        self.project_registry = self._load_registry()
        logger.info("Project Tracker initialized")

    def _load_registry(self) -> Dict[str, Any]:
        """Load project registry from JSON file, if present.

        Expected format (example):
        {
          "Q4 Dashboard": {
            "slack_channels": ["engineering", "q4-dashboard"],
            "gmail_domains": ["@company.com"],
            "notion_page_id": "<notion-page-id>"
          }
        }
        """
        path = Config.PROJECT_REGISTRY_FILE
        try:
            if path.exists():
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    logger.info(f"Loaded project registry from {path}")
                    return data
            return {}
        except Exception as e:
            logger.warning(f"Failed to load project registry from {path}: {e}")
            return {}

    def _get_project_config(self, project_name: str) -> Optional[Dict[str, Any]]:
        """Return configuration for a given project name, if any.

        Matches keys in the registry case-insensitively.
        """
        if not self.project_registry:
            return None
        name_lower = project_name.lower()
        for key, cfg in self.project_registry.items():
            try:
                if key.lower() == name_lower and isinstance(cfg, dict):
                    return cfg
            except Exception:
                continue
        return None
    
    def extract_keywords(self, project_name: str) -> List[str]:
        """Extract search keywords from project name.
        
        Args:
            project_name: Name of the project
            
        Returns:
            List of keywords for searching
        """
        # Remove common words and split
        stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for'}
        words = re.findall(r'\w+', project_name.lower())
        keywords = [w for w in words if w not in stop_words and len(w) > 2]
        return keywords
    
    async def gather_slack_updates(
        self,
        project_name: str,
        days_back: int = 7,
        channels: Optional[List[str]] = None
    ) -> List[ProjectUpdate]:
        """Gather project updates from Slack via structured DB queries."""
        logger.info(f"Gathering Slack updates for '{project_name}' (last {days_back} days)")
        keywords = self.extract_keywords(project_name) or [project_name]
        cutoff_ts = (datetime.utcnow() - timedelta(days=days_back)).timestamp()

        def query_slack() -> List[ProjectUpdate]:
            updates: List[ProjectUpdate] = []
            with self.tools.db.get_session() as session:
                keyword_filters = [Message.text.ilike(f"%{kw}%") for kw in keywords]
                if channels:
                    channel_filters = [Channel.name.ilike(f"%{ch.strip('#')}%") for ch in channels]
                    keyword_filters.append(or_(*channel_filters))

                # Build base query and apply all filters BEFORE limit/offset
                message_query = (
                    session.query(Message, Channel, User)
                    .join(Channel, Message.channel_id == Channel.channel_id)
                    .outerjoin(User, Message.user_id == User.user_id)
                    .filter(Message.timestamp >= cutoff_ts)
                )

                if keyword_filters:
                    message_query = message_query.filter(or_(*keyword_filters))

                # Only after all filters are set, apply ordering and limit
                message_query = message_query.order_by(Message.timestamp.desc()).limit(200)

                for message, channel, user in message_query.all():
                    author = (
                        user.display_name
                        or user.real_name
                        or user.username
                        or message.user_id
                        or "Unknown"
                    ) if user else (message.user_id or "Unknown")

                    updates.append(
                        ProjectUpdate(
                            source='slack',
                            timestamp=datetime.fromtimestamp(message.timestamp),
                            author=author,
                            content=message.text or "(no content)",
                            channel_or_thread=f"#{channel.name}" if channel else message.channel_id,
                            metadata={
                                'message_id': message.message_id,
                                'channel_id': message.channel_id,
                            }
                        )
                    )
            return updates

        try:
            updates = await asyncio.to_thread(query_slack)
            logger.info(f"Found {len(updates)} Slack updates")
            return updates
        except Exception as e:
            logger.error(f"Error gathering Slack updates: {e}")
            return []
    
    async def gather_gmail_updates(
        self,
        project_name: str,
        days_back: int = 7,
        domains: Optional[List[str]] = None,
        gmail_account_email: Optional[str] = None,
    ) -> List[ProjectUpdate]:
        """Gather project updates from Gmail via structured DB queries.

        When ``gmail_account_email`` is provided, results are restricted to
        that Gmail account (``gmail_messages.account_email``) to ensure
        per-user data isolation in multi-tenant deployments.
        """
        logger.info(
            "Gathering Gmail updates for '%s' (last %s days) [account=%s]",
            project_name,
            days_back,
            gmail_account_email or "<any>",
        )
        keywords = self.extract_keywords(project_name) or [project_name]
        cutoff_date = datetime.utcnow() - timedelta(days=days_back)

        def query_gmail() -> List[ProjectUpdate]:
            updates: List[ProjectUpdate] = []
            with self.tools.db.get_session() as session:
                keyword_filters = [
                    GmailMessage.subject.ilike(f"%{kw}%")
                    | GmailMessage.body_text.ilike(f"%{kw}%")
                    for kw in keywords
                ]

                # Build base query and apply all filters BEFORE limit/offset
                message_query = session.query(GmailMessage).filter(
                    GmailMessage.date >= cutoff_date
                )

                # Scope to a specific Gmail account when provided
                if gmail_account_email:
                    message_query = message_query.filter(
                        GmailMessage.account_email == gmail_account_email
                    )

                if keyword_filters:
                    message_query = message_query.filter(or_(*keyword_filters))

                # If project-specific domains are provided, scope to those
                if domains:
                    domain_filters = [
                        GmailMessage.from_address.ilike(f"%{dom}%") for dom in domains
                    ]
                    message_query = message_query.filter(or_(*domain_filters))

                # Only after all filters are set, apply ordering and limit
                message_query = message_query.order_by(GmailMessage.date.desc()).limit(200)

                for message in message_query.all():
                    updates.append(
                        ProjectUpdate(
                            source='gmail',
                            timestamp=message.date or datetime.utcnow(),
                            author=message.from_address or "Unknown",
                            content=(
                                message.snippet
                                or message.body_text
                                or "(no content)"
                            )[:500],
                            channel_or_thread=message.subject or "(no subject)",
                            metadata={
                                'message_id': message.message_id,
                                'thread_id': message.thread_id,
                            },
                        )
                    )
            return updates

        try:
            updates = await asyncio.to_thread(query_gmail)
            logger.info(f"Found {len(updates)} Gmail updates")
            return updates
        except Exception as e:
            logger.error(f"Error gathering Gmail updates: {e}")
            return []
    
    async def gather_notion_updates(
        self,
        project_name: str,
        page_id: Optional[str] = None
    ) -> List[ProjectUpdate]:
        """Gather project updates from Notion.
        
        Args:
            project_name: Name of the project to track
            page_id: Optional specific Notion page ID
            
        Returns:
            List of Notion updates related to the project
        """
        logger.info(f"Gathering Notion updates for '{project_name}'")
        updates = []
        
        try:
            # Search Notion workspace
            keywords = self.extract_keywords(project_name)
            for keyword in keywords:
                result = self.tools.search_notion_workspace(query=keyword)
                
                # Parse Notion search results
                if "pages found" in result.lower():
                    # Extract page info and content
                    updates.append(ProjectUpdate(
                        source='notion',
                        timestamp=datetime.now(),
                        author='Notion',
                        content=result[:300],
                        channel_or_thread='Notion Workspace',
                        metadata={'keyword': keyword}
                    ))
            
            logger.info(f"Found {len(updates)} Notion updates")
            return updates
        
        except Exception as e:
            logger.error(f"Error gathering Notion updates: {e}")
            return []
    
    async def analyze_updates(
        self,
        all_updates: List[ProjectUpdate]
    ) -> Dict[str, Any]:
        """Analyze updates to extract key information.
        
        Args:
            all_updates: List of all project updates
            
        Returns:
            Dictionary with analysis results
        """
        logger.info(f"Analyzing {len(all_updates)} project updates")
        
        # Extract key information
        key_points = []
        action_items = []
        blockers = []
        team_members = set()
        
        # Common action item patterns
        action_patterns = [
            r'TODO:',
            r'Action item:',
            r'Next step:',
            r'Need to',
            r'Should',
            r'Will',
            r'Plan to'
        ]
        
        # Common blocker patterns
        blocker_patterns = [
            r'blocked by',
            r'waiting for',
            r'issue:',
            r'problem:',
            r'blocker:',
            r'stuck on'
        ]
        
        for update in all_updates:
            content_lower = update.content.lower()
            
            # Extract team members
            team_members.add(update.author)
            
            # Identify action items
            for pattern in action_patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    action_items.append(update.content[:200])
                    break
            
            # Identify blockers
            for pattern in blocker_patterns:
                if re.search(pattern, content_lower, re.IGNORECASE):
                    blockers.append(update.content[:200])
                    break
            
            # Extract key points (sentences with important keywords)
            important_keywords = ['completed', 'finished', 'ready', 'launched', 'deployed', 
                                'started', 'began', 'decided', 'approved', 'milestone']
            for keyword in important_keywords:
                if keyword in content_lower:
                    key_points.append(update.content[:200])
                    break
        
        return {
            'key_points': list(set(key_points))[:10],  # Top 10 unique points
            'action_items': list(set(action_items))[:10],
            'blockers': list(set(blockers))[:5],
            'team_members': list(team_members)
        }
    
    async def calculate_progress(
        self,
        updates: List[ProjectUpdate],
        project_name: str
    ) -> float:
        """Calculate estimated project progress percentage.
        
        Args:
            updates: List of all project updates
            project_name: Name of the project
            
        Returns:
            Progress percentage (0-100)
        """
        # Simple heuristic based on update content
        progress_keywords = {
            'completed': 10,
            'finished': 10,
            'done': 8,
            'ready': 7,
            'launched': 15,
            'deployed': 15,
            'testing': 5,
            'in progress': 3,
            'started': 2
        }
        
        total_score = 0
        for update in updates:
            content_lower = update.content.lower()
            for keyword, score in progress_keywords.items():
                if keyword in content_lower:
                    total_score += score
        
        # Normalize to 0-100 scale
        progress = min(100, (total_score / len(updates) * 10) if updates else 0)
        return round(progress, 1)
    
    async def track_project(
        self,
        project_name: str,
        days_back: int = 7,
        notion_page_id: Optional[str] = None,
        gmail_account_email: Optional[str] = None,
    ) -> ProjectStatus:
        """Main method to track a project across all platforms.
        
        Args:
            project_name: Name of the project to track
            days_back: Number of days to look back
            notion_page_id: Optional Notion page ID for the project
            
        Returns:
            Comprehensive project status
        """
        logger.info(f"=== Tracking Project: {project_name} ===")

        # Look up project-specific configuration (channels, domains, notion page)
        project_cfg = self._get_project_config(project_name)
        slack_channels: Optional[List[str]] = None
        gmail_domains: Optional[List[str]] = None
        effective_page_id: Optional[str] = notion_page_id

        if project_cfg:
            try:
                if isinstance(project_cfg.get("slack_channels"), list):
                    slack_channels = [str(ch) for ch in project_cfg.get("slack_channels", [])]
                if isinstance(project_cfg.get("gmail_domains"), list):
                    gmail_domains = [str(d) for d in project_cfg.get("gmail_domains", [])]
                # notion_page_id argument, if provided, always wins over registry
                if not effective_page_id and isinstance(project_cfg.get("notion_page_id"), str):
                    effective_page_id = project_cfg.get("notion_page_id")
            except Exception as cfg_err:
                logger.warning(f"Error parsing project registry entry for '{project_name}': {cfg_err}")
        
        # Gather updates from all sources, scoped by registry if available
        slack_updates = await self.gather_slack_updates(project_name, days_back, channels=slack_channels)
        gmail_updates = await self.gather_gmail_updates(
            project_name,
            days_back,
            domains=gmail_domains,
            gmail_account_email=gmail_account_email,
        )
        notion_updates = await self.gather_notion_updates(project_name, effective_page_id)
        
        # Combine all updates
        all_updates = slack_updates + gmail_updates + notion_updates
        
        # Analyze updates
        analysis = await self.analyze_updates(all_updates)
        
        # Calculate progress
        progress = await self.calculate_progress(all_updates, project_name)
        
        # Create project status
        status = ProjectStatus(
            project_name=project_name,
            last_updated=datetime.now(),
            slack_updates=slack_updates,
            gmail_updates=gmail_updates,
            notion_updates=notion_updates,
            key_points=analysis['key_points'],
            action_items=analysis['action_items'],
            blockers=analysis['blockers'],
            team_members=analysis['team_members'],
            progress_percentage=progress
        )
        
        logger.info(f"Project tracking complete: {len(all_updates)} total updates")
        return status
    
    async def update_notion_page(
        self,
        page_id: str,
        project_status: ProjectStatus
    ) -> str:
        """Update existing Notion page with project status.
        
        IMPORTANT: This UPDATES an existing page, does NOT create a new one.
        
        Args:
            page_id: ID of the existing Notion page to update
            project_status: Current project status to write
            
        Returns:
            Success message or error
        """
        logger.info(f"Updating Notion page {page_id} with project status")
        
        try:
            # Format update content
            update_content = self._format_notion_update(project_status)
            
            # Use append_to_notion_page tool to add update
            result = self.tools.append_to_notion_page(
                page_id=page_id,
                content=update_content
            )
            
            logger.info(f"Notion page updated successfully")
            return result
        
        except Exception as e:
            logger.error(f"Error updating Notion page: {e}")
            return f"Error: {str(e)}"
    
    def _format_notion_update(self, status: ProjectStatus) -> str:
        """Format project status for Notion page.
        
        Args:
            status: Project status to format
            
        Returns:
            Formatted markdown content
        """
        content = f"""
## 📊 Project Update: {status.project_name}
**Last Updated:** {status.last_updated.strftime("%Y-%m-%d %H:%M")}
**Progress:** {status.progress_percentage}%

### 📈 Summary
- **Total Updates:** {len(status.slack_updates) + len(status.gmail_updates) + len(status.notion_updates)}
  - Slack: {len(status.slack_updates)} messages
  - Gmail: {len(status.gmail_updates)} threads
  - Notion: {len(status.notion_updates)} pages

### ✅ Key Points
"""
        for point in status.key_points[:5]:
            content += f"- {point}\n"
        
        content += "\n### 📋 Action Items\n"
        for item in status.action_items[:5]:
            content += f"- [ ] {item}\n"
        
        if status.blockers:
            content += "\n### ⚠️ Blockers\n"
            for blocker in status.blockers:
                content += f"- 🚫 {blocker}\n"
        
        content += f"\n### 👥 Team Members\n"
        for member in status.team_members[:10]:
            content += f"- {member}\n"
        
        content += f"\n---\n*Auto-generated by Workforce AI Agent*\n"
        
        return content
    
    async def generate_report(
        self,
        project_name: str,
        days_back: int = 7
    ) -> str:
        """Generate a comprehensive project report.
        
        Args:
            project_name: Name of the project
            days_back: Number of days to include
            
        Returns:
            Formatted project report as string
        """
        logger.info(f"Generating report for project: {project_name}")
        
        # Track the project
        status = await self.track_project(project_name, days_back)
        
        # Format report
        report = f"""
╔══════════════════════════════════════════════════════════╗
║          PROJECT STATUS REPORT                            ║
║          {project_name.center(44)}          ║
╚══════════════════════════════════════════════════════════╝

📅 Report Period: Last {days_back} days
🕐 Generated: {status.last_updated.strftime("%Y-%m-%d %H:%M:%S")}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 OVERVIEW
  Progress: {'█' * int(status.progress_percentage/5)}{' ' * (20-int(status.progress_percentage/5))} {status.progress_percentage}%
  
  Updates Across Platforms:
  • Slack Messages:  {len(status.slack_updates)}
  • Email Threads:   {len(status.gmail_updates)}
  • Notion Pages:    {len(status.notion_updates)}
  • Total Updates:   {len(status.slack_updates) + len(status.gmail_updates) + len(status.notion_updates)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ KEY HIGHLIGHTS
"""
        
        for i, point in enumerate(status.key_points[:5], 1):
            report += f"  {i}. {point[:80]}...\n"
        
        report += "\n📋 ACTION ITEMS\n"
        for i, item in enumerate(status.action_items[:5], 1):
            report += f"  {i}. {item[:80]}...\n"
        
        if status.blockers:
            report += "\n⚠️  BLOCKERS & ISSUES\n"
            for i, blocker in enumerate(status.blockers, 1):
                report += f"  {i}. {blocker[:80]}...\n"
        
        report += f"\n👥 TEAM MEMBERS ({len(status.team_members)})\n"
        report += f"  {', '.join(status.team_members[:10])}\n"
        
        report += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        report += "  📎 Sources: Slack + Gmail + Notion\n"
        report += "  🤖 Generated by Workforce AI Agent\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        
        return report
