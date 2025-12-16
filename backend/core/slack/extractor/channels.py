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
        exclude_archived: bool = False,
        progress_callback=None,
        cancel_check=None,
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

        total = len(channels_list)
        if progress_callback:
            try:
                progress_callback({"stage": "fetched", "progress": 0.1 if total else 1.0, "total": total})
            except Exception:
                logger.debug("progress_callback failed at fetched stage", exc_info=True)
        
        # Save to database with progress bar
        with tqdm(total=total, desc="Saving channels") as pbar:
            for idx, channel in enumerate(channels_list, 1):
                try:
                    if cancel_check and cancel_check():
                        logger.info("Channel extraction cancelled")
                        raise KeyboardInterrupt()
                    self.db_manager.save_channel(channel, self.workspace_id)
                    count += 1
                    pbar.update(1)
                    if progress_callback and (idx % max(1, total // 20) == 0 or idx == total):
                        try:
                            frac = idx / total if total else 1.0
                            progress_callback({"stage": "saving", "progress": 0.1 + 0.85 * frac, "saved": idx, "total": total})
                        except Exception:
                            logger.debug("progress_callback failed during saving stage", exc_info=True)
                except Exception as e:
                    logger.error(f"Failed to save channel {channel.get('id')}: {e}")
        
        if progress_callback:
            try:
                progress_callback({"stage": "completed", "progress": 1.0, "saved": count, "total": total})
            except Exception:
                logger.debug("progress_callback failed at completed stage", exc_info=True)

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
