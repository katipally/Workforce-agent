"""Message extractor."""
from typing import Optional, List
from tqdm import tqdm
import time

from .base_extractor import BaseExtractor
from utils.logger import get_logger
from config import Config

logger = get_logger(__name__)


class MessageExtractor(BaseExtractor):
    """Extract message history."""
    
    def extract_channel_history(
        self,
        channel_id: str,
        oldest: Optional[float] = None,
        latest: Optional[float] = None,
        include_threads: bool = True
    ) -> int:
        """Extract message history for a channel."""
        logger.info(f"Extracting messages from channel: {channel_id}")
        
        # Try to join the channel first to avoid "not_in_channel" errors
        try:
            self.client.conversations_join(channel=channel_id)
            logger.debug(f"Joined channel: {channel_id}")
        except Exception as e:
            # Ignore errors - might already be in channel, or it's a DM
            logger.debug(f"Could not join channel {channel_id}: {e}")
        
        # Check sync status
        sync_status = self.db_manager.get_sync_status(channel_id)
        if sync_status and sync_status.last_synced_ts and not oldest:
            oldest = sync_status.last_synced_ts
            logger.info(f"Resuming from last sync: {oldest}")
        
        count = 0
        messages_list = []
        latest_ts = None
        
        # Note: conversations.history has strict rate limits (1 req/min for non-Marketplace)
        logger.warning(
            "conversations.history has rate limit of 1 req/min for non-Marketplace apps. "
            "This may take a while..."
        )
        
        # Paginate through messages
        params = {
            "channel": channel_id,
            "limit": 200,  # Max for conversations.history
        }
        
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest
        
        for message in self._paginate(
            "conversations.history",
            "conversations_history",
            "messages",
            **params
        ):
            messages_list.append(message)
            ts = float(message.get("ts", 0))
            if not latest_ts or ts > latest_ts:
                latest_ts = ts
        
        logger.info(f"Fetched {len(messages_list)} messages. Saving to database...")
        
        # Save messages with progress bar
        with tqdm(total=len(messages_list), desc=f"Saving messages") as pbar:
            for message in messages_list:
                try:
                    self.db_manager.save_message(message, channel_id)
                    count += 1
                    pbar.update(1)
                    
                    # Extract threads if present
                    if include_threads and message.get("reply_count", 0) > 0:
                        thread_ts = message.get("ts")
                        thread_count = self.extract_thread_replies(channel_id, thread_ts)
                        logger.debug(f"Extracted {thread_count} thread replies")
                
                except Exception as e:
                    logger.error(f"Failed to save message: {e}")
        
        # Update sync status
        if latest_ts:
            self.db_manager.update_sync_status(channel_id, latest_ts, is_complete=True)
        
        logger.info(f"Message extraction complete for {channel_id}. Saved {count} messages")
        return count
    
    def extract_thread_replies(self, channel_id: str, thread_ts: str) -> int:
        """Extract replies in a thread."""
        logger.debug(f"Extracting thread replies: {channel_id} / {thread_ts}")
        
        count = 0
        
        try:
            for message in self._paginate(
                "conversations.replies",
                "conversations_replies",
                "messages",
                channel=channel_id,
                ts=thread_ts,
                limit=200
            ):
                # Skip the parent message (first in list)
                if message.get("ts") == thread_ts:
                    continue
                
                try:
                    self.db_manager.save_message(message, channel_id)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to save thread reply: {e}")
        
        except Exception as e:
            logger.error(f"Failed to extract thread replies: {e}")
        
        return count
    
    def extract_all_channels_history(
        self,
        channel_ids: Optional[List[str]] = None,
        include_archived: bool = False
    ) -> dict:
        """Extract history from all channels."""
        logger.info("Starting extraction of all channel histories")
        
        # Get channels if not provided
        if not channel_ids:
            channels = self.db_manager.get_all_channels(include_archived=include_archived)
            channel_ids = [ch.channel_id for ch in channels]
        
        logger.info(f"Extracting history from {len(channel_ids)} channels")
        
        results = {}
        total_messages = 0
        
        for i, channel_id in enumerate(channel_ids, 1):
            logger.info(f"[{i}/{len(channel_ids)}] Processing channel: {channel_id}")
            
            try:
                count = self.extract_channel_history(channel_id)
                results[channel_id] = {"status": "success", "count": count}
                total_messages += count
                
                # Brief pause between channels
                time.sleep(1)
            
            except Exception as e:
                logger.error(f"Failed to extract channel {channel_id}: {e}")
                results[channel_id] = {"status": "error", "error": str(e)}
        
        logger.info(f"Extraction complete. Total messages: {total_messages}")
        return results
    
    def get_message(self, channel_id: str, message_ts: str):
        """Get a specific message."""
        logger.info(f"Getting message: {channel_id} / {message_ts}")
        
        try:
            response = self._call_api(
                "conversations.history",
                "conversations_history",
                channel=channel_id,
                latest=message_ts,
                inclusive=True,
                limit=1
            )
            
            messages = response.get("messages", [])
            if messages:
                message = messages[0]
                self.db_manager.save_message(message, channel_id)
                return message
        
        except Exception as e:
            logger.error(f"Failed to get message: {e}")
            raise
