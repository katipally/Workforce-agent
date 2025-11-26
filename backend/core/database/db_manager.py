"""Database manager for Workforce Agent.

Handles all database operations including:
- Connection management (PostgreSQL)
- Session handling
- Schema initialization
- CRUD operations for Slack and Gmail data
- Statistics and reporting
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import create_engine, func, text, inspect
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from config import Config
from .models import (
    Base,
    Workspace,
    User,
    Channel,
    Message,
    File,
    MessageFile,
    Reaction,
    SyncStatus,
    NotionWorkspace,
    NotionPage,
    GmailAccount,
    GmailLabel,
    GmailThread,
    GmailMessage,
    GmailAttachment,
    ChatSession,
    ChatMessage,
    Project,
    ProjectSource,
    Workflow,
    WorkflowChannelMapping,
    SlackNotionMessageMapping,
    AppUser,
    UserOAuthToken,
    AppSession,
    UserSettings,
    AppSettings,
)
from utils.logger import get_logger

logger = get_logger(__name__)


class DatabaseManager:
    """Manages database connections and operations for PostgreSQL.
    
    Features:
    - Automatic reconnection (pool_pre_ping)
    - Connection pooling with recycling
    - Transaction management
    - Context manager support for sessions
    """
    
    def __init__(self, database_url: Optional[str] = None):
        """Initialize database manager.
        
        Args:
            database_url: Database connection string. If None, uses Config.DATABASE_URL
                         Format: postgresql://user:pass@host:port/dbname
        """
        self.database_url = database_url or Config.DATABASE_URL
        self.engine = create_engine(
            self.database_url,
            echo=False,  # Set to True for SQL query debugging
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=3600  # Recycle connections after 1 hour
        )
        # expire_on_commit=False so objects (e.g., AppUser) remain usable after commits
        # in helper functions like get_current_user, where the session is closed
        # before the object is returned to FastAPI dependencies.
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.init_db()
    
    def init_db(self):
        """Initialize database schema."""
        logger.info("Initializing database schema")
        Base.metadata.create_all(bind=self.engine)
        self._run_schema_upgrades()
        logger.info("Database schema initialized")

    def _run_schema_upgrades(self):
        """Apply lightweight, in-process schema upgrades when needed."""

        try:
            inspector = inspect(self.engine)
            table_names = set(inspector.get_table_names())

            if "notion_pages" in table_names:
                columns = {col["name"] for col in inspector.get_columns("notion_pages")}
                needs_object_type = "object_type" not in columns
                needs_url = "url" not in columns
                needs_raw = "raw_data" not in columns

                if needs_object_type or needs_url or needs_raw:
                    dialect = self.engine.dialect.name
                    json_type = "JSON" if dialect == "postgresql" else "TEXT"

                    with self.engine.begin() as conn:
                        if needs_object_type:
                            conn.execute(
                                text("ALTER TABLE notion_pages ADD COLUMN object_type VARCHAR(20)")
                            )
                        if needs_url:
                            conn.execute(
                                text("ALTER TABLE notion_pages ADD COLUMN url VARCHAR(500)")
                            )
                        if needs_raw:
                            conn.execute(
                                text(f"ALTER TABLE notion_pages ADD COLUMN raw_data {json_type}")
                            )

                # Older schemas had a self-referential foreign key on parent_id
                # (notion_pages_parent_id_fkey). This breaks when Notion returns
                # parents that aren't stored locally (e.g., workspace or
                # un-synced pages). Drop that constraint if present.
                fks = inspector.get_foreign_keys("notion_pages")
                parent_fk_names = [
                    fk["name"]
                    for fk in fks
                    if "parent_id" in fk.get("constrained_columns", []) and fk.get("name")
                ]

                if parent_fk_names:
                    with self.engine.begin() as conn:
                        for fk_name in parent_fk_names:
                            conn.execute(
                                text(
                                    f"ALTER TABLE notion_pages DROP CONSTRAINT {fk_name}"
                                )
                            )

            # Chat sessions table: add owner_user_id for per-user chat history
            if "chat_sessions" in table_names:
                columns = {col["name"] for col in inspector.get_columns("chat_sessions")}
                needs_owner = "owner_user_id" not in columns
                if needs_owner:
                    with self.engine.begin() as conn:
                        conn.execute(
                            text("ALTER TABLE chat_sessions ADD COLUMN owner_user_id VARCHAR(50)")
                        )

            # Project table: add tracking columns for sync and summary freshness
            # and owner_user_id for per-user projects.
            if "projects" in table_names:
                columns = {col["name"] for col in inspector.get_columns("projects")}
                needs_owner = "owner_user_id" not in columns
                needs_last_sync = "last_project_sync_at" not in columns
                needs_last_summary = "last_summary_generated_at" not in columns

                if needs_owner or needs_last_sync or needs_last_summary:
                    with self.engine.begin() as conn:
                        if needs_owner:
                            conn.execute(
                                text("ALTER TABLE projects ADD COLUMN owner_user_id VARCHAR(50)")
                            )
                        if needs_last_sync:
                            conn.execute(
                                text(
                                    "ALTER TABLE projects ADD COLUMN last_project_sync_at TIMESTAMP"
                                )
                            )
                        if needs_last_summary:
                            conn.execute(
                                text(
                                    "ALTER TABLE projects ADD COLUMN last_summary_generated_at TIMESTAMP"
                                )
                            )

        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"Schema upgrade error: {e}", exc_info=True)
    
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
    
    def get_gmail_statistics(self) -> Dict[str, Any]:
        """Get Gmail database statistics."""
        with self.get_session() as session:
            return {
                "accounts": session.query(func.count(GmailAccount.email)).scalar(),
                "labels": session.query(func.count(GmailLabel.label_id)).scalar(),
                "messages": session.query(func.count(GmailMessage.message_id)).scalar(),
                "threads": session.query(func.count(func.distinct(GmailMessage.thread_id))).scalar(),
                "attachments": session.query(func.count(GmailAttachment.id)).scalar(),
            }

    # =========================================================================
    # Settings Operations (per-user and workspace-wide)
    # =========================================================================

    def get_user_settings(self, user_id: str) -> Optional[UserSettings]:
        """Return UserSettings row for the given AppUser, if any."""
        if not user_id:
            return None

        with self.get_session() as session:
            return session.query(UserSettings).filter_by(user_id=user_id).first()

    def upsert_user_settings(self, user_id: str, settings_patch: Dict[str, Any]) -> UserSettings:
        """Create or update per-user settings.

        The patch is merged into the existing JSON document. Keys with value
        None are removed from the settings dict; all other keys overwrite
        previous values.
        """
        if not user_id:
            raise ValueError("user_id is required for upsert_user_settings")

        with self.get_session() as session:
            row = session.query(UserSettings).filter_by(user_id=user_id).first()
            if not row:
                row = UserSettings(user_id=user_id, settings={})
                session.add(row)

            current = dict(row.settings or {})
            for key, value in (settings_patch or {}).items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value
            row.settings = current
            row.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(row)
            return row

    def get_app_settings(self, scope: str = "global") -> Optional[AppSettings]:
        """Return AppSettings for the given scope (default: 'global')."""
        with self.get_session() as session:
            return session.query(AppSettings).filter_by(scope=scope).first()

    def upsert_app_settings(self, settings_patch: Dict[str, Any], scope: str = "global") -> AppSettings:
        """Create or update workspace-wide application settings.

        Like user settings, this merges the patch into the existing JSON
        document, removing keys whose value is None.
        """
        with self.get_session() as session:
            row = session.query(AppSettings).filter_by(scope=scope).first()
            if not row:
                row = AppSettings(scope=scope, settings={})
                session.add(row)

            current = dict(row.settings or {})
            for key, value in (settings_patch or {}).items():
                if value is None:
                    current.pop(key, None)
                else:
                    current[key] = value
            row.settings = current
            row.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(row)
            return row
    
    # ============================================================================
    # Chat Session Operations
    # ============================================================================
    
    def create_chat_session(
        self,
        session_id: str,
        title: str = "New Chat",
        owner_user_id: Optional[str] = None,
    ) -> ChatSession:
        """Create a new chat session.
        
        Args:
            session_id: Unique session identifier
            title: Session title (defaults to "New Chat")
            
        Returns:
            Created or existing ChatSession
        """
        with self.get_session() as session:
            # If a session with this ID already exists, reuse it instead of
            # trying to insert a duplicate primary key. This makes the method
            # idempotent and also lets us "adopt" legacy sessions that were
            # created before owner_user_id was introduced.
            existing = (
                session.query(ChatSession)
                .filter_by(session_id=session_id)
                .first()
            )
            if existing:
                # If the existing row has no owner yet and we now know who
                # owns it, attach the owner and bump updated_at.
                if owner_user_id and not existing.owner_user_id:
                    existing.owner_user_id = owner_user_id
                    existing.updated_at = datetime.utcnow()
                    session.commit()
                    session.refresh(existing)
                return existing

            chat_session = ChatSession(
                session_id=session_id,
                title=title,
                owner_user_id=owner_user_id,
            )
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            return chat_session
    
    def get_chat_session(self, session_id: str, owner_user_id: Optional[str] = None) -> Optional[ChatSession]:
        """Get a chat session by ID.
        
        Args:
            session_id: Session identifier
            
        Returns:
            ChatSession if found, None otherwise
        """
        with self.get_session() as session:
            query = session.query(ChatSession).filter(ChatSession.session_id == session_id)
            if owner_user_id:
                query = query.filter(ChatSession.owner_user_id == owner_user_id)
            return query.first()
    
    def list_chat_sessions(self, owner_user_id: Optional[str] = None, limit: int = 50) -> List[ChatSession]:
        """List chat sessions ordered by last update.
        
        Args:
            limit: Maximum number of sessions to return
            
        Returns:
            List of ChatSession objects
        """
        with self.get_session() as session:
            query = session.query(ChatSession)
            if owner_user_id:
                query = query.filter(ChatSession.owner_user_id == owner_user_id)
            return (
                query.order_by(ChatSession.updated_at.desc())
                .limit(limit)
                .all()
            )
    
    def add_chat_message(self, session_id: str, role: str, content: str, sources: Optional[List[Dict]] = None) -> ChatMessage:
        """Add a message to a chat session.
        
        Args:
            session_id: Session identifier
            role: Message role ('user' or 'assistant')
            content: Message content
            sources: Optional list of sources for assistant messages
            
        Returns:
            Created ChatMessage
        """
        with self.get_session() as session:
            # Update session's updated_at timestamp
            chat_session = session.query(ChatSession).filter_by(session_id=session_id).first()
            if chat_session:
                chat_session.updated_at = datetime.utcnow()
            
            message = ChatMessage(
                session_id=session_id,
                role=role,
                content=content,
                sources=sources
            )
            session.add(message)
            session.commit()
            session.refresh(message)
            return message
    
    def get_chat_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get chat history for a session formatted for AI context.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to return
            
        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        with self.get_session() as session:
            messages = (
                session.query(ChatMessage)
                .filter_by(session_id=session_id)
                .order_by(ChatMessage.created_at.asc())
                .limit(limit)
                .all()
            )

            # Return rich message objects so the frontend can render full history
            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "sources": msg.sources,
                    "created_at": msg.created_at.isoformat() if msg.created_at else None,
                }
                for msg in messages
            ]
    
    def update_session_title(self, session_id: str, title: str) -> None:
        """Update a session's title.
        
        Args:
            session_id: Session identifier
            title: New title
        """
        with self.get_session() as session:
            chat_session = session.query(ChatSession).filter_by(session_id=session_id).first()
            if chat_session:
                chat_session.title = title
                chat_session.updated_at = datetime.utcnow()
                session.commit()
    
    def delete_chat_session(self, session_id: str, owner_user_id: Optional[str] = None) -> None:
        """Delete a chat session and all its messages.
        
        Args:
            session_id: Session identifier
        """
        with self.get_session() as session:
            query = session.query(ChatSession).filter(ChatSession.session_id == session_id)
            if owner_user_id:
                query = query.filter(ChatSession.owner_user_id == owner_user_id)
            chat_session = query.first()
            if chat_session:
                session.delete(chat_session)
                session.commit()

    # ============================================================================
    # Project Operations
    # ============================================================================
    
    def create_project(
        self,
        name: str,
        description: Optional[str] = None,
        status: str = "not_started",
        summary: Optional[str] = None,
        main_goal: Optional[str] = None,
        current_status_summary: Optional[str] = None,
        important_notes: Optional[str] = None,
        owner_user_id: Optional[str] = None,
    ) -> Project:
        """Create a new cross-application project."""
        with self.get_session() as session:
            project = Project(
                owner_user_id=owner_user_id,
                name=name,
                description=description,
                status=status,
                summary=summary,
                main_goal=main_goal,
                current_status_summary=current_status_summary,
                important_notes=important_notes,
            )
            session.add(project)
            session.commit()
            session.refresh(project)
            return project

    def list_projects(self, owner_user_id: Optional[str] = None, limit: int = 100) -> List[Project]:
        """List projects ordered by most recently updated."""
        with self.get_session() as session:
            query = session.query(Project)
            if owner_user_id:
                query = query.filter(Project.owner_user_id == owner_user_id)
            return query.order_by(Project.updated_at.desc()).limit(limit).all()

    def get_project(self, project_id: str, owner_user_id: Optional[str] = None) -> Optional[Project]:
        """Get a project by ID."""
        with self.get_session() as session:
            query = session.query(Project).filter(Project.id == project_id)
            if owner_user_id:
                query = query.filter(Project.owner_user_id == owner_user_id)
            return query.first()

    def update_project(self, project_id: str, owner_user_id: Optional[str] = None, **fields: Any) -> Optional[Project]:
        """Update a project's editable fields."""
        with self.get_session() as session:
            query = session.query(Project).filter(Project.id == project_id)
            if owner_user_id:
                query = query.filter(Project.owner_user_id == owner_user_id)
            project = query.first()
            if not project:
                return None

            summary_related_changed = False
            for key, value in fields.items():
                if value is not None and hasattr(project, key):
                    setattr(project, key, value)
                    if key in {
                        "description",
                        "summary",
                        "main_goal",
                        "current_status_summary",
                        "important_notes",
                    }:
                        summary_related_changed = True

            if summary_related_changed:
                project.last_summary_generated_at = datetime.utcnow()
            project.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(project)
            return project

    def delete_project(self, project_id: str, owner_user_id: Optional[str] = None) -> None:
        """Delete a project and all of its source mappings."""
        with self.get_session() as session:
            query = session.query(Project).filter(Project.id == project_id)
            if owner_user_id:
                query = query.filter(Project.owner_user_id == owner_user_id)
            project = query.first()
            if project:
                session.delete(project)
                session.commit()

    def add_project_source(
        self,
        project_id: str,
        source_type: str,
        source_id: str,
        display_name: Optional[str] = None,
    ) -> ProjectSource:
        """Add a source mapping to a project (idempotent on unique key)."""
        with self.get_session() as session:
            mapping = (
                session.query(ProjectSource)
                .filter_by(project_id=project_id, source_type=source_type, source_id=source_id)
                .first()
            )
            if mapping:
                # Update display name if provided
                if display_name and mapping.display_name != display_name:
                    mapping.display_name = display_name
                    session.commit()
                    session.refresh(mapping)
                return mapping

            mapping = ProjectSource(
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                display_name=display_name,
            )
            session.add(mapping)
            session.commit()
            session.refresh(mapping)
            return mapping

    def remove_project_source(self, project_id: str, source_type: str, source_id: str) -> None:
        """Remove a source mapping from a project."""
        with self.get_session() as session:
            mapping = (
                session.query(ProjectSource)
                .filter_by(project_id=project_id, source_type=source_type, source_id=source_id)
                .first()
            )
            if mapping:
                session.delete(mapping)
                session.commit()

    def get_project_sources(self, project_id: str) -> List[ProjectSource]:
        """List all source mappings for a project."""
        with self.get_session() as session:
            return (
                session.query(ProjectSource)
                .filter_by(project_id=project_id)
                .order_by(ProjectSource.created_at.asc())
                .all()
            )

    # ========================================================================
    # Workflow Operations
    # ========================================================================

    def create_workflow(
        self,
        name: str,
        type: str,
        status: str = "active",
        notion_master_page_id: Optional[str] = None,
        poll_interval_seconds: int = 30,
    ) -> Workflow:
        """Create a new workflow definition."""
        with self.get_session() as session:
            workflow = Workflow(
                name=name,
                type=type,
                status=status,
                notion_master_page_id=notion_master_page_id,
                poll_interval_seconds=poll_interval_seconds,
            )
            session.add(workflow)
            session.commit()
            session.refresh(workflow)
            return workflow

    def list_workflows(self, limit: int = 100) -> List[Workflow]:
        """List workflows ordered by most recently updated."""
        with self.get_session() as session:
            return (
                session.query(Workflow)
                .order_by(Workflow.updated_at.desc())
                .limit(limit)
                .all()
            )

    def get_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Get a workflow by ID."""
        with self.get_session() as session:
            return session.query(Workflow).filter_by(id=workflow_id).first()

    def update_workflow(self, workflow_id: str, **fields: Any) -> Optional[Workflow]:
        """Update a workflow's editable fields."""
        with self.get_session() as session:
            workflow = session.query(Workflow).filter_by(id=workflow_id).first()
            if not workflow:
                return None

            for key, value in fields.items():
                if value is not None and hasattr(workflow, key):
                    setattr(workflow, key, value)

            workflow.updated_at = datetime.utcnow()
            session.commit()
            session.refresh(workflow)
            return workflow

    def delete_workflow(self, workflow_id: str) -> None:
        """Delete a workflow and all of its mappings."""
        with self.get_session() as session:
            workflow = session.query(Workflow).filter_by(id=workflow_id).first()
            if workflow:
                session.delete(workflow)
                session.commit()

    def add_workflow_channel(
        self,
        workflow_id: str,
        slack_channel_id: str,
        slack_channel_name: Optional[str] = None,
        notion_subpage_id: Optional[str] = None,
    ) -> WorkflowChannelMapping:
        """Add or update a channel mapping for a workflow (idempotent on workflow+channel)."""
        with self.get_session() as session:
            mapping = (
                session.query(WorkflowChannelMapping)
                .filter_by(workflow_id=workflow_id, slack_channel_id=slack_channel_id)
                .first()
            )

            if mapping:
                changed = False
                if slack_channel_name and mapping.slack_channel_name != slack_channel_name:
                    mapping.slack_channel_name = slack_channel_name
                    changed = True
                if notion_subpage_id and mapping.notion_subpage_id != notion_subpage_id:
                    mapping.notion_subpage_id = notion_subpage_id
                    changed = True
                if changed:
                    mapping.updated_at = datetime.utcnow()
                    session.commit()
                    session.refresh(mapping)
                return mapping

            mapping = WorkflowChannelMapping(
                workflow_id=workflow_id,
                slack_channel_id=slack_channel_id,
                slack_channel_name=slack_channel_name,
                notion_subpage_id=notion_subpage_id,
            )
            session.add(mapping)
            session.commit()
            session.refresh(mapping)
            return mapping

    def get_workflow_channels(self, workflow_id: str) -> List[WorkflowChannelMapping]:
        """List all channel mappings for a workflow."""
        with self.get_session() as session:
            return (
                session.query(WorkflowChannelMapping)
                .filter_by(workflow_id=workflow_id)
                .order_by(WorkflowChannelMapping.created_at.asc())
                .all()
            )

    def remove_workflow_channel(self, workflow_id: str, slack_channel_id: str) -> None:
        """Remove a channel mapping from a workflow."""
        with self.get_session() as session:
            mapping = (
                session.query(WorkflowChannelMapping)
                .filter_by(workflow_id=workflow_id, slack_channel_id=slack_channel_id)
                .first()
            )
            if mapping:
                session.delete(mapping)
                session.commit()

    def create_slack_notion_mapping(
        self,
        workflow_id: str,
        slack_channel_id: str,
        slack_ts: float,
        notion_block_id: str,
        parent_slack_ts: Optional[float] = None,
    ) -> SlackNotionMessageMapping:
        """Create a Slack→Notion message mapping in an idempotent way.

        If the mapping already exists (based on the unique constraint), the
        existing row is returned instead of raising an error.
        """
        with self.get_session() as session:
            try:
                mapping = SlackNotionMessageMapping(
                    workflow_id=workflow_id,
                    slack_channel_id=slack_channel_id,
                    slack_ts=slack_ts,
                    parent_slack_ts=parent_slack_ts,
                    notion_block_id=notion_block_id,
                )
                session.add(mapping)
                session.commit()
                session.refresh(mapping)
                return mapping
            except IntegrityError:
                session.rollback()
                existing = (
                    session.query(SlackNotionMessageMapping)
                    .filter_by(
                        workflow_id=workflow_id,
                        slack_channel_id=slack_channel_id,
                        slack_ts=slack_ts,
                    )
                    .first()
                )
                if existing:
                    return existing
                raise

    def get_slack_notion_mapping(
        self,
        workflow_id: str,
        slack_channel_id: str,
        slack_ts: float,
    ) -> Optional[SlackNotionMessageMapping]:
        """Get a Slack→Notion message mapping if it exists."""
        with self.get_session() as session:
            return (
                session.query(SlackNotionMessageMapping)
                .filter_by(
                    workflow_id=workflow_id,
                    slack_channel_id=slack_channel_id,
                    slack_ts=slack_ts,
                )
                .first()
            )

    def list_slack_notion_mappings_for_channel_since(
        self,
        workflow_id: str,
        slack_channel_id: str,
        min_slack_ts: float,
    ) -> List[SlackNotionMessageMapping]:
        """List Slack→Notion mappings for a workflow/channel since a given ts.

        Used by the Slack → Notion workflow to perform best-effort deletion
        detection for recent messages.
        """
        with self.get_session() as session:
            return (
                session.query(SlackNotionMessageMapping)
                .filter(
                    SlackNotionMessageMapping.workflow_id == workflow_id,
                    SlackNotionMessageMapping.slack_channel_id == slack_channel_id,
                    SlackNotionMessageMapping.slack_ts >= min_slack_ts,
                )
                .all()
            )

    def delete_slack_notion_mapping(
        self,
        workflow_id: str,
        slack_channel_id: str,
        slack_ts: float,
    ) -> None:
        with self.get_session() as session:
            mapping = (
                session.query(SlackNotionMessageMapping)
                .filter_by(
                    workflow_id=workflow_id,
                    slack_channel_id=slack_channel_id,
                    slack_ts=slack_ts,
                )
                .first()
            )
            if mapping:
                session.delete(mapping)
                session.commit()
