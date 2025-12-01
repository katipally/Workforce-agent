"""Extraction coordinator."""
from typing import Optional, Dict, Any
from slack_sdk import WebClient

from config import Config
from database.db_manager import DatabaseManager
from utils.logger import get_logger
from .users import UserExtractor
from .channels import ChannelExtractor
from .messages import MessageExtractor
from .files import FileExtractor

logger = get_logger(__name__)


class ExtractionCoordinator:
    """Coordinates extraction of all Slack data."""
    
    def __init__(
        self,
        client: Optional[WebClient] = None,
        db_manager: Optional[DatabaseManager] = None
    ):
        """Initialize extraction coordinator."""
        # Use 60-second timeout to prevent indefinite hangs on EC2
        self.client = client or WebClient(token=Config.SLACK_BOT_TOKEN, timeout=60)
        self.db_manager = db_manager or DatabaseManager()
        
        # Initialize extractors
        self.user_extractor = UserExtractor(self.client, self.db_manager)
        self.channel_extractor = ChannelExtractor(self.client, self.db_manager)
        self.message_extractor = MessageExtractor(self.client, self.db_manager)
        self.file_extractor = FileExtractor(self.client, self.db_manager)
        
        self.workspace_id = None
    
    def extract_workspace_info(self) -> Dict[str, Any]:
        """Extract workspace information."""
        logger.info("Extracting workspace information")
        
        workspace = self.user_extractor.get_workspace_info()
        self.workspace_id = workspace.get("id")
        
        # Save workspace
        self.db_manager.save_workspace(workspace)
        
        logger.info(f"Workspace: {workspace.get('name')} ({self.workspace_id})")
        return workspace
    
    def extract_all_users(self) -> int:
        """Extract all users."""
        logger.info("=" * 60)
        logger.info("EXTRACTING USERS")
        logger.info("=" * 60)
        
        if not self.workspace_id:
            self.extract_workspace_info()
        
        count = self.user_extractor.extract_all_users()
        logger.info(f"✓ Extracted {count} users")
        return count
    
    def extract_all_channels(self, exclude_archived: bool = False) -> int:
        """Extract all channels."""
        logger.info("=" * 60)
        logger.info("EXTRACTING CHANNELS")
        logger.info("=" * 60)
        
        if not self.workspace_id:
            self.extract_workspace_info()
        
        count = self.channel_extractor.extract_all_channels(
            exclude_archived=exclude_archived
        )
        logger.info(f"✓ Extracted {count} channels")
        return count
    
    def extract_all_messages(
        self,
        include_archived: bool = False,
        include_threads: bool = True
    ) -> Dict[str, Any]:
        """Extract all messages from all channels."""
        logger.info("=" * 60)
        logger.info("EXTRACTING MESSAGES")
        logger.info("=" * 60)
        
        if not self.workspace_id:
            self.extract_workspace_info()
        
        # Get channels
        channels = self.db_manager.get_all_channels(include_archived=include_archived)
        logger.info(f"Found {len(channels)} channels to process")
        
        results = self.message_extractor.extract_all_channels_history(
            channel_ids=[ch.channel_id for ch in channels],
            include_archived=include_archived
        )
        
        # Calculate totals
        total_success = sum(1 for r in results.values() if r["status"] == "success")
        total_messages = sum(r.get("count", 0) for r in results.values())
        
        logger.info(f"✓ Extracted messages from {total_success}/{len(channels)} channels")
        logger.info(f"✓ Total messages: {total_messages}")
        
        return results
    
    def extract_all_files(self, download: bool = False) -> int:
        """Extract all files."""
        logger.info("=" * 60)
        logger.info("EXTRACTING FILES")
        logger.info("=" * 60)
        
        if not self.workspace_id:
            self.extract_workspace_info()
        
        count = self.file_extractor.extract_all_files(download=download)
        logger.info(f"✓ Extracted {count} files")
        return count
    
    def extract_all(
        self,
        include_archived: bool = False,
        download_files: bool = False
    ) -> Dict[str, Any]:
        """Extract all data from workspace."""
        logger.info("=" * 80)
        logger.info("STARTING FULL WORKSPACE EXTRACTION")
        logger.info("=" * 80)
        
        results = {}
        
        try:
            # 1. Workspace info
            workspace = self.extract_workspace_info()
            results["workspace"] = workspace
            
            # 2. Users
            user_count = self.extract_all_users()
            results["users"] = user_count
            
            # 3. Channels
            channel_count = self.extract_all_channels(exclude_archived=not include_archived)
            results["channels"] = channel_count
            
            # 4. Messages (This will take the longest due to rate limits)
            message_results = self.extract_all_messages(
                include_archived=include_archived,
                include_threads=True
            )
            results["messages"] = message_results
            
            # 5. Files
            file_count = self.extract_all_files(download=download_files)
            results["files"] = file_count
            
            # 6. Get statistics
            stats = self.db_manager.get_statistics()
            results["statistics"] = stats
            
            logger.info("=" * 80)
            logger.info("EXTRACTION COMPLETE")
            logger.info("=" * 80)
            logger.info(f"Users: {stats['users']}")
            logger.info(f"Channels: {stats['channels']}")
            logger.info(f"Messages: {stats['messages']}")
            logger.info(f"Files: {stats['files']}")
            logger.info(f"Reactions: {stats['reactions']}")
            logger.info("=" * 80)
            
            return results
        
        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            raise
    
    def extract_incremental(self) -> Dict[str, Any]:
        """Extract only new data since last sync."""
        logger.info("Starting incremental extraction")
        
        results = {}
        
        # This would check sync status and only extract new data
        # For now, just extract new messages from channels
        channels = self.db_manager.get_all_channels()
        
        for channel in channels:
            sync_status = self.db_manager.get_sync_status(channel.channel_id)
            if sync_status:
                # Extract from last sync point
                count = self.message_extractor.extract_channel_history(
                    channel.channel_id,
                    oldest=sync_status.last_synced_ts
                )
                results[channel.channel_id] = count
        
        logger.info("Incremental extraction complete")
        return results
