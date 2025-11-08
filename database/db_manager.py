"""Database manager for Slack data."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from config import Config
from .models import (
    Base, Workspace, User, Channel, Message, File, 
    MessageFile, Reaction, SyncStatus
)
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Manages database operations."""
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager."""
        self.database_url = database_url or Config.DATABASE_URL
        self.engine = create_engine(
            self.database_url,
            echo=False,
            pool_pre_ping=True,
            pool_recycle=3600
        )
        self.SessionLocal = sessionmaker(bind=self.engine)
        self.init_db()
    
    def init_db(self):
        """Initialize database schema."""
        logger.info("Initializing database schema")
        Base.metadata.create_all(bind=self.engine)
        logger.info("Database schema initialized")
    
    def get_session(self) -> Session:
        """Get database session."""
        return self.SessionLocal()
    
    # Workspace operations
    def save_workspace(self, workspace_data: Dict[str, Any]) -> Workspace:
        """Save or update workspace."""
        with self.get_session() as session:
            workspace = session.query(Workspace).filter_by(
                workspace_id=workspace_data["id"]
            ).first()
            
            if workspace:
                for key, value in workspace_data.items():
                    if hasattr(workspace, key) and key != "id":
                        setattr(workspace, key, value)
                workspace.updated_at = datetime.utcnow()
            else:
                workspace = Workspace(
                    workspace_id=workspace_data["id"],
                    name=workspace_data.get("name", ""),
                    domain=workspace_data.get("domain", ""),
                    email_domain=workspace_data.get("email_domain", ""),
                    icon=workspace_data.get("icon", {}),
                    enterprise_id=workspace_data.get("enterprise_id"),
                    enterprise_name=workspace_data.get("enterprise_name")
                )
                session.add(workspace)
            
            session.commit()
            session.refresh(workspace)
            return workspace
    
    # User operations
    def save_user(self, user_data: Dict[str, Any], workspace_id: str) -> User:
        """Save or update user."""
        with self.get_session() as session:
            user = session.query(User).filter_by(user_id=user_data["id"]).first()
            
            profile = user_data.get("profile", {})
            
            if user:
                user.username = user_data.get("name", "")
                user.real_name = user_data.get("real_name", "")
                user.display_name = profile.get("display_name", "")
                user.email = profile.get("email", "")
                user.is_bot = user_data.get("is_bot", False)
                user.is_admin = user_data.get("is_admin", False)
                user.is_owner = user_data.get("is_owner", False)
                user.is_app_user = user_data.get("is_app_user", False)
                user.deleted = user_data.get("deleted", False)
                user.timezone = user_data.get("tz", "")
                user.timezone_offset = user_data.get("tz_offset", 0)
                user.status_text = profile.get("status_text", "")
                user.status_emoji = profile.get("status_emoji", "")
                user.profile_data = profile
                user.updated_at = datetime.utcnow()
            else:
                user = User(
                    user_id=user_data["id"],
                    workspace_id=workspace_id,
                    username=user_data.get("name", ""),
                    real_name=user_data.get("real_name", ""),
                    display_name=profile.get("display_name", ""),
                    email=profile.get("email", ""),
                    is_bot=user_data.get("is_bot", False),
                    is_admin=user_data.get("is_admin", False),
                    is_owner=user_data.get("is_owner", False),
                    is_app_user=user_data.get("is_app_user", False),
                    deleted=user_data.get("deleted", False),
                    timezone=user_data.get("tz", ""),
                    timezone_offset=user_data.get("tz_offset", 0),
                    status_text=profile.get("status_text", ""),
                    status_emoji=profile.get("status_emoji", ""),
                    profile_data=profile
                )
                session.add(user)
            
            session.commit()
            session.refresh(user)
            return user
    
    # Channel operations
    def save_channel(self, channel_data: Dict[str, Any], workspace_id: str) -> Channel:
        """Save or update channel."""
        with self.get_session() as session:
            channel = session.query(Channel).filter_by(
                channel_id=channel_data["id"]
            ).first()
            
            topic = channel_data.get("topic", {})
            purpose = channel_data.get("purpose", {})
            
            if channel:
                channel.name = channel_data.get("name", "")
                channel.name_normalized = channel_data.get("name_normalized", "")
                channel.is_channel = channel_data.get("is_channel", True)
                channel.is_group = channel_data.get("is_group", False)
                channel.is_im = channel_data.get("is_im", False)
                channel.is_mpim = channel_data.get("is_mpim", False)
                channel.is_private = channel_data.get("is_private", False)
                channel.is_archived = channel_data.get("is_archived", False)
                channel.is_general = channel_data.get("is_general", False)
                channel.is_shared = channel_data.get("is_shared", False)
                channel.is_org_shared = channel_data.get("is_org_shared", False)
                channel.is_member = channel_data.get("is_member", False)
                channel.topic = topic.get("value", "")
                channel.purpose = purpose.get("value", "")
                channel.creator = channel_data.get("creator", "")
                channel.num_members = channel_data.get("num_members", 0)
                channel.updated_at = datetime.utcnow()
            else:
                channel = Channel(
                    channel_id=channel_data["id"],
                    workspace_id=workspace_id,
                    name=channel_data.get("name", ""),
                    name_normalized=channel_data.get("name_normalized", ""),
                    is_channel=channel_data.get("is_channel", True),
                    is_group=channel_data.get("is_group", False),
                    is_im=channel_data.get("is_im", False),
                    is_mpim=channel_data.get("is_mpim", False),
                    is_private=channel_data.get("is_private", False),
                    is_archived=channel_data.get("is_archived", False),
                    is_general=channel_data.get("is_general", False),
                    is_shared=channel_data.get("is_shared", False),
                    is_org_shared=channel_data.get("is_org_shared", False),
                    is_member=channel_data.get("is_member", False),
                    topic=topic.get("value", ""),
                    purpose=purpose.get("value", ""),
                    creator=channel_data.get("creator", ""),
                    num_members=channel_data.get("num_members", 0)
                )
                session.add(channel)
            
            session.commit()
            session.refresh(channel)
            return channel
    
    # Message operations
    def save_message(self, message_data: Dict[str, Any], channel_id: str) -> Message:
        """Save or update message."""
        with self.get_session() as session:
            ts = float(message_data.get("ts", 0))
            message_id = f"{channel_id}_{ts}"
            
            message = session.query(Message).filter_by(message_id=message_id).first()
            
            if message:
                message.text = message_data.get("text", "")
                message.message_type = message_data.get("type", "message")
                message.subtype = message_data.get("subtype")
                message.blocks = message_data.get("blocks")
                message.attachments = message_data.get("attachments")
                message.raw_data = message_data
                
                if "edited" in message_data:
                    message.is_edited = True
                    message.edited_ts = float(message_data["edited"].get("ts", 0))
                
                message.updated_at = datetime.utcnow()
            else:
                message = Message(
                    message_id=message_id,
                    channel_id=channel_id,
                    user_id=message_data.get("user"),
                    text=message_data.get("text", ""),
                    timestamp=ts,
                    thread_ts=float(message_data["thread_ts"]) if "thread_ts" in message_data else None,
                    parent_user_id=message_data.get("parent_user_id"),
                    message_type=message_data.get("type", "message"),
                    subtype=message_data.get("subtype"),
                    reply_count=message_data.get("reply_count", 0),
                    reply_users_count=message_data.get("reply_users_count", 0),
                    blocks=message_data.get("blocks"),
                    attachments=message_data.get("attachments"),
                    raw_data=message_data
                )
                session.add(message)
            
            # Handle reactions
            if "reactions" in message_data:
                for reaction_data in message_data["reactions"]:
                    self._save_reactions(session, message_id, reaction_data)
            
            session.commit()
            session.refresh(message)
            return message
    
    def _save_reactions(self, session: Session, message_id: str, reaction_data: Dict[str, Any]):
        """Save reactions for a message."""
        emoji = reaction_data.get("name", "")
        users = reaction_data.get("users", [])
        
        for user_id in users:
            try:
                reaction = Reaction(
                    message_id=message_id,
                    user_id=user_id,
                    emoji_name=emoji
                )
                session.add(reaction)
            except IntegrityError:
                session.rollback()
    
    # File operations
    def save_file(self, file_data: Dict[str, Any]) -> File:
        """Save or update file."""
        with self.get_session() as session:
            file = session.query(File).filter_by(file_id=file_data["id"]).first()
            
            if file:
                file.name = file_data.get("name", "")
                file.title = file_data.get("title", "")
                file.mimetype = file_data.get("mimetype", "")
                file.filetype = file_data.get("filetype", "")
                file.pretty_type = file_data.get("pretty_type", "")
                file.size = file_data.get("size", 0)
                file.updated_at = datetime.utcnow()
            else:
                file = File(
                    file_id=file_data["id"],
                    user_id=file_data.get("user"),
                    name=file_data.get("name", ""),
                    title=file_data.get("title", ""),
                    mimetype=file_data.get("mimetype", ""),
                    filetype=file_data.get("filetype", ""),
                    pretty_type=file_data.get("pretty_type", ""),
                    size=file_data.get("size", 0),
                    mode=file_data.get("mode", ""),
                    is_external=file_data.get("is_external", False),
                    is_public=file_data.get("is_public", False),
                    url_private=file_data.get("url_private", ""),
                    url_private_download=file_data.get("url_private_download", ""),
                    permalink=file_data.get("permalink", ""),
                    permalink_public=file_data.get("permalink_public", ""),
                    timestamp=float(file_data.get("timestamp", 0))
                )
                session.add(file)
            
            session.commit()
            session.refresh(file)
            return file
    
    def link_message_file(self, message_id: str, file_id: str):
        """Link message to file."""
        with self.get_session() as session:
            try:
                link = MessageFile(message_id=message_id, file_id=file_id)
                session.add(link)
                session.commit()
            except IntegrityError:
                session.rollback()
    
    # Sync status operations
    def update_sync_status(self, channel_id: str, last_ts: float, is_complete: bool = False):
        """Update sync status for channel."""
        with self.get_session() as session:
            sync_status = session.query(SyncStatus).filter_by(channel_id=channel_id).first()
            
            if sync_status:
                sync_status.last_synced_ts = last_ts
                sync_status.last_sync_time = datetime.utcnow()
                sync_status.is_complete = is_complete
                sync_status.updated_at = datetime.utcnow()
            else:
                sync_status = SyncStatus(
                    channel_id=channel_id,
                    last_synced_ts=last_ts,
                    last_sync_time=datetime.utcnow(),
                    is_complete=is_complete
                )
                session.add(sync_status)
            
            session.commit()
    
    def get_sync_status(self, channel_id: str) -> Optional[SyncStatus]:
        """Get sync status for channel."""
        with self.get_session() as session:
            return session.query(SyncStatus).filter_by(channel_id=channel_id).first()
    
    # Query operations
    def get_all_channels(self, include_archived: bool = False) -> List[Channel]:
        """Get all channels."""
        with self.get_session() as session:
            query = session.query(Channel)
            if not include_archived:
                query = query.filter(Channel.is_archived == False)
            return query.all()
    
    def get_messages_count(self, channel_id: Optional[str] = None) -> int:
        """Get total message count."""
        with self.get_session() as session:
            query = session.query(func.count(Message.message_id))
            if channel_id:
                query = query.filter(Message.channel_id == channel_id)
            return query.scalar()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.get_session() as session:
            return {
                "users": session.query(func.count(User.user_id)).scalar(),
                "channels": session.query(func.count(Channel.channel_id)).scalar(),
                "messages": session.query(func.count(Message.message_id)).scalar(),
                "files": session.query(func.count(File.file_id)).scalar(),
                "reactions": session.query(func.count(Reaction.id)).scalar(),
            }
    
    def get_all_users(self) -> List[User]:
        """Get all users."""
        with self.get_session() as session:
            return session.query(User).all()
    
    def get_all_files(self) -> List[File]:
        """Get all files."""
        with self.get_session() as session:
            return session.query(File).all()
    
    def get_messages_by_channel(self, channel_id: str, limit: Optional[int] = None) -> List[Message]:
        """Get messages for a specific channel.
        
        Args:
            channel_id: Channel ID
            limit: Optional limit on number of messages
            
        Returns:
            List of messages
        """
        with self.get_session() as session:
            query = session.query(Message).filter(Message.channel_id == channel_id)
            query = query.order_by(Message.timestamp.desc())
            if limit:
                query = query.limit(limit)
            return query.all()
