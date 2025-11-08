"""Socket Mode client for real-time events."""
import asyncio
from typing import Optional, Callable
from slack_bolt.app.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

from config import Config
from database.db_manager import DatabaseManager
from utils.logger import get_logger

logger = get_logger(__name__)


class SocketModeClient:
    """WebSocket client for real-time Slack events."""
    
    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        event_handlers: Optional[object] = None
    ):
        """Initialize Socket Mode client."""
        self.db_manager = db_manager or DatabaseManager()
        self.app = AsyncApp(token=Config.SLACK_BOT_TOKEN)
        self.handler = None
        self.is_running = False
        
        # Register event handlers
        if event_handlers:
            self.register_handlers(event_handlers)
        
        logger.info("Socket Mode client initialized")
    
    def register_handlers(self, event_handlers):
        """Register event handlers."""
        # Message events
        @self.app.event("message")
        async def handle_message(event, say):
            await event_handlers.handle_message(event, say)
        
        # Reaction events
        @self.app.event("reaction_added")
        async def handle_reaction_added(event):
            await event_handlers.handle_reaction_added(event)
        
        @self.app.event("reaction_removed")
        async def handle_reaction_removed(event):
            await event_handlers.handle_reaction_removed(event)
        
        # Channel events
        @self.app.event("channel_created")
        async def handle_channel_created(event):
            await event_handlers.handle_channel_created(event)
        
        @self.app.event("channel_deleted")
        async def handle_channel_deleted(event):
            await event_handlers.handle_channel_deleted(event)
        
        @self.app.event("channel_rename")
        async def handle_channel_rename(event):
            await event_handlers.handle_channel_rename(event)
        
        @self.app.event("channel_archive")
        async def handle_channel_archive(event):
            await event_handlers.handle_channel_archive(event)
        
        @self.app.event("channel_unarchive")
        async def handle_channel_unarchive(event):
            await event_handlers.handle_channel_unarchive(event)
        
        # User events
        @self.app.event("team_join")
        async def handle_team_join(event):
            await event_handlers.handle_team_join(event)
        
        @self.app.event("user_change")
        async def handle_user_change(event):
            await event_handlers.handle_user_change(event)
        
        # File events
        @self.app.event("file_shared")
        async def handle_file_shared(event):
            await event_handlers.handle_file_shared(event)
        
        @self.app.event("file_deleted")
        async def handle_file_deleted(event):
            await event_handlers.handle_file_deleted(event)
        
        # App mention
        @self.app.event("app_mention")
        async def handle_app_mention(event, say):
            await event_handlers.handle_app_mention(event, say)
        
        logger.info("Event handlers registered")
    
    async def start(self):
        """Start Socket Mode connection."""
        logger.info("Starting Socket Mode connection...")
        
        try:
            self.handler = AsyncSocketModeHandler(
                app=self.app,
                app_token=Config.SLACK_APP_TOKEN
            )
            
            self.is_running = True
            logger.info("✓ Socket Mode connected successfully")
            logger.info("Listening for events...")
            
            await self.handler.start_async()
        
        except Exception as e:
            logger.error(f"Failed to start Socket Mode: {e}")
            self.is_running = False
            raise
    
    async def stop(self):
        """Stop Socket Mode connection."""
        logger.info("Stopping Socket Mode connection...")
        
        if self.handler:
            await self.handler.close_async()
        
        self.is_running = False
        logger.info("Socket Mode disconnected")
    
    async def run_forever(self):
        """Run Socket Mode indefinitely."""
        try:
            await self.start()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            await self.stop()
        except Exception as e:
            logger.error(f"Socket Mode error: {e}")
            await self.stop()
            raise
