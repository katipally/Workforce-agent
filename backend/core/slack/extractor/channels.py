"""Channel extractor."""
from typing import List, Optional
from tqdm import tqdm

from .base_extractor import BaseExtractor
from utils.logger import get_logger
from config import Config

logger = get_logger(__name__)


class ChannelExtractor(BaseExtractor):
    """Extract channel information."""
    
    def extract_all_channels(
        self,
        types: str = "public_channel,private_channel,mpim,im",
        exclude_archived: bool = False
    ) -> int:
        """Extract all channels from workspace."""
        logger.info(f"Starting channel extraction (types: {types})")
        
        count = 0
        channels_list = []
        
        # Paginate through channels
        for channel in self._paginate(
            "conversations.list",
            "conversations_list",
            "channels",
            types=types,
            exclude_archived=exclude_archived,
            limit=Config.DEFAULT_PAGE_SIZE
        ):
            channels_list.append(channel)
        
        logger.info(f"Fetched {len(channels_list)} channels. Saving to database...")
        
        # Save to database with progress bar
        with tqdm(total=len(channels_list), desc="Saving channels") as pbar:
            for channel in channels_list:
                try:
                    self.db_manager.save_channel(channel, self.workspace_id)
                    count += 1
                    pbar.update(1)
                except Exception as e:
                    logger.error(f"Failed to save channel {channel.get('id')}: {e}")
        
        logger.info(f"Channel extraction complete. Saved {count} channels")
        return count
    
    def extract_channel(self, channel_id: str):
        """Extract specific channel."""
        logger.info(f"Extracting channel: {channel_id}")
        
        try:
            response = self._call_api(
                "conversations.info",
                "conversations_info",
                channel=channel_id
            )
            channel = response.get("channel", {})
            
            if channel:
                self.db_manager.save_channel(channel, self.workspace_id)
                logger.info(f"Channel {channel_id} saved")
                return channel
        
        except Exception as e:
            logger.error(f"Failed to extract channel {channel_id}: {e}")
            raise
    
    def get_channel_members(self, channel_id: str) -> List[str]:
        """Get list of channel members."""
        logger.info(f"Getting members for channel: {channel_id}")
        
        members = []
        for member_id in self._paginate(
            "conversations.members",
            "conversations_members",
            "members",
            channel=channel_id,
            limit=Config.DEFAULT_PAGE_SIZE
        ):
            members.append(member_id)
        
        logger.info(f"Channel {channel_id} has {len(members)} members")
        return members
    
    def join_channel(self, channel_id: str) -> bool:
        """Join a channel (required for accessing private channels)."""
        logger.info(f"Attempting to join channel: {channel_id}")
        
        try:
            response = self._call_api(
                "conversations.join",
                "conversations_join",
                channel=channel_id
            )
            
            if response.get("ok"):
                logger.info(f"Successfully joined channel {channel_id}")
                return True
        
        except Exception as e:
            logger.warning(f"Could not join channel {channel_id}: {e}")
            return False
