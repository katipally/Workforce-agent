"""Event handlers for real-time Slack events."""
from typing import Optional
from slack_sdk import WebClient

from config import Config
from database.db_manager import DatabaseManager
from utils.logger import get_logger

logger = get_logger(__name__)


class EventHandlers:
    """Handles real-time Slack events."""
    
    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        client: Optional[WebClient] = None
    ):
        """Initialize event handlers."""
        self.db_manager = db_manager or DatabaseManager()
        self.client = client or WebClient(token=Config.SLACK_BOT_TOKEN)
        self.workspace_id = None
        
        # Get workspace ID
        self._initialize_workspace()
    
    def _initialize_workspace(self):
        """Initialize workspace ID."""
        try:
            response = self.client.auth_test()
            self.workspace_id = response.get("team_id")
            logger.info(f"Initialized workspace: {self.workspace_id}")
        except Exception as e:
            logger.error(f"Failed to get workspace ID: {e}")
    
    async def handle_message(self, event, say):
        """Handle message event."""
        try:
            subtype = event.get("subtype")
            channel = event.get("channel")
            user = event.get("user")
            text = event.get("text", "")
            ts = event.get("ts")
            
            logger.info(f"Message received: {channel} / {user} / {text[:50]}")
            
            # Handle different message subtypes
            if subtype == "message_changed":
                # Message was edited
                message = event.get("message", {})
                self.db_manager.save_message(message, channel)
                logger.debug(f"Message edited: {channel} / {message.get('ts')}")
            
            elif subtype == "message_deleted":
                # Message was deleted
                deleted_ts = event.get("deleted_ts")
                logger.debug(f"Message deleted: {channel} / {deleted_ts}")
                # Mark as deleted in database
                # This would require an update method
            
            elif not subtype:
                # Regular message
                self.db_manager.save_message(event, channel)
                logger.debug(f"Message saved: {channel} / {ts}")
            
            # Handle file attachments
            if "files" in event:
                for file_data in event["files"]:
                    self.db_manager.save_file(file_data)
                    message_id = f"{channel}_{ts}"
                    self.db_manager.link_message_file(message_id, file_data["id"])
        
        except Exception as e:
            logger.error(f"Error handling message event: {e}")
    
    async def handle_reaction_added(self, event):
        """Handle reaction_added event."""
        try:
            user = event.get("user")
            emoji = event.get("reaction")
            item = event.get("item", {})
            channel = item.get("channel")
            ts = item.get("ts")
            
            logger.info(f"Reaction added: {emoji} by {user} on {channel}/{ts}")
            
            # Get the message and update reactions
            message_id = f"{channel}_{ts}"
            from database.models import Reaction
            
            # Save reaction
            with self.db_manager.get_session() as session:
                reaction = Reaction(
                    message_id=message_id,
                    user_id=user,
                    emoji_name=emoji
                )
                session.add(reaction)
                session.commit()
        
        except Exception as e:
            logger.error(f"Error handling reaction_added event: {e}")
    
    async def handle_reaction_removed(self, event):
        """Handle reaction_removed event."""
        try:
            user = event.get("user")
            emoji = event.get("reaction")
            item = event.get("item", {})
            channel = item.get("channel")
            ts = item.get("ts")
            
            logger.info(f"Reaction removed: {emoji} by {user} on {channel}/{ts}")
            
            # Remove reaction from database
            message_id = f"{channel}_{ts}"
            from database.models import Reaction
            
            with self.db_manager.get_session() as session:
                reaction = session.query(Reaction).filter_by(
                    message_id=message_id,
                    user_id=user,
                    emoji_name=emoji
                ).first()
                
                if reaction:
                    session.delete(reaction)
                    session.commit()
        
        except Exception as e:
            logger.error(f"Error handling reaction_removed event: {e}")
    
    async def handle_channel_created(self, event):
        """Handle channel_created event."""
        try:
            channel = event.get("channel", {})
            channel_id = channel.get("id")
            channel_name = channel.get("name")
            
            logger.info(f"Channel created: {channel_name} ({channel_id})")
            
            # Get full channel info and save
            response = self.client.conversations_info(channel=channel_id)
            channel_data = response.get("channel", {})
            self.db_manager.save_channel(channel_data, self.workspace_id)
        
        except Exception as e:
            logger.error(f"Error handling channel_created event: {e}")
    
    async def handle_channel_deleted(self, event):
        """Handle channel_deleted event."""
        try:
            channel_id = event.get("channel")
            logger.info(f"Channel deleted: {channel_id}")
            
            # Mark channel as deleted in database
            # This would require an update method
        
        except Exception as e:
            logger.error(f"Error handling channel_deleted event: {e}")
    
    async def handle_channel_rename(self, event):
        """Handle channel_rename event."""
        try:
            channel = event.get("channel", {})
            channel_id = channel.get("id")
            new_name = channel.get("name")
            
            logger.info(f"Channel renamed: {channel_id} -> {new_name}")
            
            # Update channel in database
            response = self.client.conversations_info(channel=channel_id)
            channel_data = response.get("channel", {})
            self.db_manager.save_channel(channel_data, self.workspace_id)
        
        except Exception as e:
            logger.error(f"Error handling channel_rename event: {e}")
    
    async def handle_channel_archive(self, event):
        """Handle channel_archive event."""
        try:
            channel_id = event.get("channel")
            logger.info(f"Channel archived: {channel_id}")
            
            # Update channel in database
            response = self.client.conversations_info(channel=channel_id)
            channel_data = response.get("channel", {})
            self.db_manager.save_channel(channel_data, self.workspace_id)
        
        except Exception as e:
            logger.error(f"Error handling channel_archive event: {e}")
    
    async def handle_channel_unarchive(self, event):
        """Handle channel_unarchive event."""
        try:
            channel_id = event.get("channel")
            logger.info(f"Channel unarchived: {channel_id}")
            
            # Update channel in database
            response = self.client.conversations_info(channel=channel_id)
            channel_data = response.get("channel", {})
            self.db_manager.save_channel(channel_data, self.workspace_id)
        
        except Exception as e:
            logger.error(f"Error handling channel_unarchive event: {e}")
    
    async def handle_team_join(self, event):
        """Handle team_join event."""
        try:
            user = event.get("user", {})
            user_id = user.get("id")
            user_name = user.get("name")
            
            logger.info(f"User joined: {user_name} ({user_id})")
            
            # Save user to database
            self.db_manager.save_user(user, self.workspace_id)
        
        except Exception as e:
            logger.error(f"Error handling team_join event: {e}")
    
    async def handle_user_change(self, event):
        """Handle user_change event."""
        try:
            user = event.get("user", {})
            user_id = user.get("id")
            
            logger.info(f"User updated: {user_id}")
            
            # Update user in database
            self.db_manager.save_user(user, self.workspace_id)
        
        except Exception as e:
            logger.error(f"Error handling user_change event: {e}")
    
    async def handle_file_shared(self, event):
        """Handle file_shared event."""
        try:
            file_id = event.get("file_id")
            user_id = event.get("user_id")
            
            logger.info(f"File shared: {file_id} by {user_id}")
            
            # Get file info and save
            response = self.client.files_info(file=file_id)
            file_data = response.get("file", {})
            self.db_manager.save_file(file_data)
        
        except Exception as e:
            logger.error(f"Error handling file_shared event: {e}")
    
    async def handle_file_deleted(self, event):
        """Handle file_deleted event."""
        try:
            file_id = event.get("file_id")
            logger.info(f"File deleted: {file_id}")
            
            # Mark file as deleted in database
            # This would require an update method
        
        except Exception as e:
            logger.error(f"Error handling file_deleted event: {e}")
    
    async def handle_app_mention(self, event, say):
        """Handle app_mention event."""
        try:
            user = event.get("user")
            text = event.get("text", "")
            channel = event.get("channel")
            
            logger.info(f"App mentioned: {channel} by {user}")
            
            # Save the mention message
            self.db_manager.save_message(event, channel)
            
            # Optionally respond
            # await say(f"Hello <@{user}>! I received your message.")
        
        except Exception as e:
            logger.error(f"Error handling app_mention event: {e}")
