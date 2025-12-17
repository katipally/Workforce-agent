"""Message extractor."""
import os
import sys
from typing import Optional, List, Callable, Dict, Any
from tqdm import tqdm
import time
from datetime import datetime

from .base_extractor import BaseExtractor
from utils.logger import get_logger
from utils.rate_limiter import get_rate_limit_for_method
from config import Config

logger = get_logger(__name__)

# Get rate limit for conversations.history to calculate ETA
_HISTORY_RATE_LIMIT, _ = get_rate_limit_for_method("conversations.history")
# For non-Marketplace apps, Slack caps limit param at 15 messages per request
_SLACK_MAX_LIMIT_NON_MARKETPLACE = int(os.getenv("SLACK_MAX_LIMIT_NON_MARKETPLACE", "15"))


class MessageExtractor(BaseExtractor):
    """Extract message history."""
    
    def extract_channel_history(
        self,
        channel_id: str,
        oldest: Optional[float] = None,
        latest: Optional[float] = None,
        include_threads: bool = True,
        progress_callback: Optional[Callable[[Dict[str, float]], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
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
        
        # Calculate effective limit (Slack caps at 15 for non-Marketplace apps)
        configured_limit = int(getattr(Config, "SLACK_CONVERSATIONS_HISTORY_LIMIT", 15))
        effective_limit = min(configured_limit, _SLACK_MAX_LIMIT_NON_MARKETPLACE)
        
        # Rate limit info for ETA calculation
        seconds_per_request = 60 / _HISTORY_RATE_LIMIT  # e.g., 60s for 1 req/min
        
        logger.info(
            f"conversations.history rate limit: {_HISTORY_RATE_LIMIT} req/min, "
            f"{effective_limit} messages/page. Each page takes ~{seconds_per_request:.0f}s."
        )
        
        # Paginate through messages with progress tracking
        params = {
            "channel": channel_id,
            "limit": max(1, min(configured_limit, 200)),
        }
        
        if oldest:
            params["oldest"] = oldest
        if latest:
            params["latest"] = latest
        
        # Track pagination progress
        pages_fetched = 0
        fetch_start_time = time.time()
        
        for message in self._paginate_with_progress(
            "conversations.history",
            "conversations_history",
            "messages",
            progress_callback=progress_callback,
            cancel_check=cancel_check,
            seconds_per_request=seconds_per_request,
            **params
        ):
            if cancel_check and cancel_check():
                logger.info("Message extraction cancelled during pagination")
                raise KeyboardInterrupt()
            messages_list.append(message)
            ts = float(message.get("ts", 0))
            if not latest_ts or ts > latest_ts:
                latest_ts = ts
        
        fetch_duration = time.time() - fetch_start_time
        logger.info(f"Fetched {len(messages_list)} messages in {fetch_duration:.1f}s. Saving to database...")

        if progress_callback:
            progress_callback(
                {
                    "stage": "saving",
                    "stage_description": "Saving messages to database",
                    "total_messages": len(messages_list),
                    "processed_messages": 0,
                    "progress": 0.85,
                    "eta_seconds": 5,  # Saving is fast
                }
            )
        
        # Save messages
        commit_batch_size = max(1, int(getattr(Config, "BATCH_SIZE", 100)))
        progress_step = max(1, len(messages_list) // 20) if messages_list else 1
        use_tqdm = sys.stderr.isatty()
        with self.db_manager.get_session() as session:
            if use_tqdm:
                with tqdm(total=len(messages_list), desc=f"Saving messages") as pbar:
                    for i, message in enumerate(messages_list, 1):
                        try:
                            if cancel_check and cancel_check():
                                logger.info("Message extraction cancelled during save loop")
                                raise KeyboardInterrupt()
                            self.db_manager.save_message(message, channel_id, session=session, commit=False)
                            count += 1
                            pbar.update(1)

                            # Extract threads if present
                            if include_threads and message.get("reply_count", 0) > 0:
                                thread_ts = message.get("ts")
                                thread_count = self.extract_thread_replies(channel_id, thread_ts)
                                logger.debug(f"Extracted {thread_count} thread replies")

                            if i % commit_batch_size == 0:
                                session.commit()

                            if progress_callback and (i % progress_step == 0 or i == len(messages_list)):
                                frac = i / len(messages_list) if len(messages_list) else 1.0
                                progress_callback(
                                    {
                                        "stage": "saving",
                                        "stage_description": f"Saving messages to database ({i}/{len(messages_list)})",
                                        "processed_messages": i,
                                        "total_messages": len(messages_list),
                                        "messages_fetched": len(messages_list),
                                        "progress": 0.85 + 0.1 * frac,
                                        "eta_seconds": max(1, int((len(messages_list) - i) / 100)),
                                    }
                                )
                        except Exception as e:
                            logger.error(f"Failed to save message: {e}")
            else:
                for i, message in enumerate(messages_list, 1):
                    try:
                        if cancel_check and cancel_check():
                            logger.info("Message extraction cancelled during save loop")
                            raise KeyboardInterrupt()
                        self.db_manager.save_message(message, channel_id, session=session, commit=False)
                        count += 1

                        # Extract threads if present
                        if include_threads and message.get("reply_count", 0) > 0:
                            thread_ts = message.get("ts")
                            thread_count = self.extract_thread_replies(channel_id, thread_ts)
                            logger.debug(f"Extracted {thread_count} thread replies")

                        if i % commit_batch_size == 0:
                            session.commit()

                        if progress_callback and (i % progress_step == 0 or i == len(messages_list)):
                            frac = i / len(messages_list) if len(messages_list) else 1.0
                            progress_callback(
                                {
                                    "stage": "saving",
                                    "stage_description": f"Saving messages to database ({i}/{len(messages_list)})",
                                    "processed_messages": i,
                                    "total_messages": len(messages_list),
                                    "messages_fetched": len(messages_list),
                                    "progress": 0.85 + 0.1 * frac,
                                    "eta_seconds": max(1, int((len(messages_list) - i) / 100)),
                                }
                            )
                    except Exception as e:
                        logger.error(f"Failed to save message: {e}")

            session.commit()
        
        # Update sync status
        if latest_ts:
            self.db_manager.update_sync_status(channel_id, latest_ts, is_complete=True)

        if progress_callback:
            progress_callback(
                {
                    "stage": "completed",
                    "stage_description": "Sync complete",
                    "processed_messages": len(messages_list),
                    "total_messages": len(messages_list),
                    "messages_fetched": len(messages_list),
                    "progress": 1.0,
                }
            )
        
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
        include_archived: bool = False,
        include_threads: bool = False
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
                count = self.extract_channel_history(channel_id, include_threads=include_threads)
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
