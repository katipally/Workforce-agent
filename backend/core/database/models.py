"""SQLAlchemy database models for Workforce Agent.

Defines all database tables for:
- Slack data (workspaces, users, channels, messages, files, reactions)
- Gmail data (accounts, labels, threads, messages, attachments)
- PostgreSQL with optional pgvector support for AI/RAG features
"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, DateTime,
    ForeignKey, Text, JSON, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

# Vector support for AI/RAG semantic search (requires PostgreSQL + pgvector extension)
# Install: brew install pgvector, then CREATE EXTENSION vector in database
try:
    from pgvector.sqlalchemy import Vector
    VECTOR_SUPPORT = True
except ImportError:
    VECTOR_SUPPORT = False
    Vector = None

Base = declarative_base()


class Workspace(Base):
    """Slack workspace/team."""
    __tablename__ = "workspaces"
    
    workspace_id = Column(String(20), primary_key=True)
    name = Column(String(255))
    domain = Column(String(255))
    email_domain = Column(String(255))
    icon = Column(JSON)
    enterprise_id = Column(String(20))
    enterprise_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    users = relationship("User", back_populates="workspace", cascade="all, delete-orphan")
    channels = relationship("Channel", back_populates="workspace", cascade="all, delete-orphan")


class User(Base):
    """Slack user."""
    __tablename__ = "users"
    
    user_id = Column(String(20), primary_key=True)
    workspace_id = Column(String(20), ForeignKey("workspaces.workspace_id"))
    username = Column(String(255))
    real_name = Column(String(255))
    display_name = Column(String(255))
    email = Column(String(255))
    is_bot = Column(Boolean, default=False)
    is_admin = Column(Boolean, default=False)
    is_owner = Column(Boolean, default=False)
    is_app_user = Column(Boolean, default=False)
    deleted = Column(Boolean, default=False)
    timezone = Column(String(100))
    timezone_offset = Column(Integer)
    status_text = Column(String(500))
    status_emoji = Column(String(100))
    profile_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    workspace = relationship("Workspace", back_populates="users")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    files = relationship("File", back_populates="user", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="user", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_user_workspace", "workspace_id"),
        Index("idx_user_email", "email"),
    )


class Channel(Base):
    """Slack channel/conversation."""
    __tablename__ = "channels"
    
    channel_id = Column(String(20), primary_key=True)
    workspace_id = Column(String(20), ForeignKey("workspaces.workspace_id"))
    name = Column(String(255))
    name_normalized = Column(String(255))
    is_channel = Column(Boolean, default=True)
    is_group = Column(Boolean, default=False)
    is_im = Column(Boolean, default=False)
    is_mpim = Column(Boolean, default=False)
    is_private = Column(Boolean, default=False)
    is_archived = Column(Boolean, default=False)
    is_general = Column(Boolean, default=False)
    is_shared = Column(Boolean, default=False)
    is_org_shared = Column(Boolean, default=False)
    is_member = Column(Boolean, default=False)
    topic = Column(Text)
    purpose = Column(Text)
    creator = Column(String(20))
    num_members = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    workspace = relationship("Workspace", back_populates="channels")
    messages = relationship("Message", back_populates="channel", cascade="all, delete-orphan")
    sync_status = relationship("SyncStatus", back_populates="channel", uselist=False)
    
    __table_args__ = (
        Index("idx_channel_workspace", "workspace_id"),
        Index("idx_channel_name", "name"),
        Index("idx_channel_archived", "is_archived"),
    )


class Message(Base):
    """Slack message."""
    __tablename__ = "messages"
    
    message_id = Column(String(50), primary_key=True)  # channel_id + ts
    channel_id = Column(String(20), ForeignKey("channels.channel_id"), nullable=False)
    user_id = Column(String(20), ForeignKey("users.user_id"))
    text = Column(Text)
    timestamp = Column(Float, nullable=False)
    thread_ts = Column(Float)  # NULL if not a thread
    parent_user_id = Column(String(20))
    message_type = Column(String(50), default="message")
    subtype = Column(String(50))
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    edited_ts = Column(Float)
    reply_count = Column(Integer, default=0)
    reply_users_count = Column(Integer, default=0)
    blocks = Column(JSON)
    attachments = Column(JSON)
    raw_data = Column(JSON)
    
    # AI/RAG: Vector embeddings for semantic search (8192 dimensions for Qwen3)
    embedding = Column(Vector(768) if VECTOR_SUPPORT else JSON)  # Legacy 768-dim
    qwen_embedding = Column(Vector(8192) if VECTOR_SUPPORT else JSON)  # Qwen3 8192-dim
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    channel = relationship("Channel", back_populates="messages")
    user = relationship("User", back_populates="messages")
    files = relationship("MessageFile", back_populates="message", cascade="all, delete-orphan")
    reactions = relationship("Reaction", back_populates="message", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_message_channel_ts", "channel_id", "timestamp"),
        Index("idx_message_thread", "thread_ts"),
        Index("idx_message_user", "user_id"),
        Index("idx_message_type", "message_type"),
    )


class File(Base):
    """Slack file."""
    __tablename__ = "files"
    
    file_id = Column(String(20), primary_key=True)
    user_id = Column(String(20), ForeignKey("users.user_id"))
    name = Column(String(500))
    title = Column(String(500))
    mimetype = Column(String(100))
    filetype = Column(String(50))
    pretty_type = Column(String(100))
    size = Column(Integer)
    mode = Column(String(50))
    is_external = Column(Boolean, default=False)
    is_public = Column(Boolean, default=False)
    url_private = Column(String(500))
    url_private_download = Column(String(500))
    permalink = Column(String(500))
    permalink_public = Column(String(500))
    local_path = Column(String(500))
    downloaded = Column(Boolean, default=False)
    timestamp = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = relationship("User", back_populates="files")
    messages = relationship("MessageFile", back_populates="file", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_file_user", "user_id"),
        Index("idx_file_type", "filetype"),
        Index("idx_file_downloaded", "downloaded"),
    )


class MessageFile(Base):
    """Many-to-many relationship between messages and files."""
    __tablename__ = "message_files"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(50), ForeignKey("messages.message_id"), nullable=False)
    file_id = Column(String(20), ForeignKey("files.file_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    message = relationship("Message", back_populates="files")
    file = relationship("File", back_populates="messages")
    
    __table_args__ = (
        UniqueConstraint("message_id", "file_id", name="uq_message_file"),
        Index("idx_message_file_message", "message_id"),
        Index("idx_message_file_file", "file_id"),
    )


class Reaction(Base):
    """Slack reaction."""
    __tablename__ = "reactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(50), ForeignKey("messages.message_id"), nullable=False)
    user_id = Column(String(20), ForeignKey("users.user_id"), nullable=False)
    emoji_name = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    message = relationship("Message", back_populates="reactions")
    user = relationship("User", back_populates="reactions")
    
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji_name", name="uq_reaction"),
        Index("idx_reaction_message", "message_id"),
        Index("idx_reaction_user", "user_id"),
    )


class SyncStatus(Base):
    """Track synchronization status for channels."""
    __tablename__ = "sync_status"
    
    channel_id = Column(String(20), ForeignKey("channels.channel_id"), primary_key=True)
    last_synced_ts = Column(Float)
    oldest_synced_ts = Column(Float)
    last_sync_time = Column(DateTime)
    is_complete = Column(Boolean, default=False)
    message_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    last_error = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    channel = relationship("Channel", back_populates="sync_status")


# ============================================================================
# Notion Models
# ============================================================================

class NotionWorkspace(Base):
    """Notion workspace."""
    __tablename__ = "notion_workspaces"
    
    workspace_id = Column(String(50), primary_key=True)
    name = Column(String(255))
    icon = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    pages = relationship("NotionPage", back_populates="workspace", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_notion_workspace_name", "name"),
    )


class NotionPage(Base):
    """Notion page."""
    __tablename__ = "notion_pages"
    
    page_id = Column(String(50), primary_key=True)
    workspace_id = Column(String(50), ForeignKey("notion_workspaces.workspace_id"), nullable=False)
    # Parent page/database/workspace ID; may refer to objects not stored locally,
    # so we deliberately avoid a foreign key constraint here.
    parent_id = Column(String(50))

    # Type: 'page' or 'database'
    object_type = Column(String(20))

    # Display metadata
    title = Column(String(255))
    icon = Column(JSON)
    url = Column(String(500))
    last_edited_time = Column(DateTime)

    # Raw payload for future enrichment
    raw_data = Column(JSON)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    workspace = relationship("NotionWorkspace", back_populates="pages")
    
    __table_args__ = (
        Index("idx_notion_page_workspace", "workspace_id"),
        Index("idx_notion_page_parent", "parent_id"),
        Index("idx_notion_page_last_edited", "last_edited_time"),
    )


# ============================================================================
# Gmail Models
# ============================================================================

class GmailAccount(Base):
    """Gmail account."""
    __tablename__ = "gmail_accounts"
    
    email = Column(String(255), primary_key=True)
    history_id = Column(String(50))
    messages_total = Column(Integer, default=0)
    threads_total = Column(Integer, default=0)
    unread_count = Column(Integer, default=0)
    starred_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship("GmailMessage", back_populates="account", cascade="all, delete-orphan")
    labels = relationship("GmailLabel", back_populates="account", cascade="all, delete-orphan")
    threads = relationship("GmailThread", back_populates="account", cascade="all, delete-orphan")


class GmailLabel(Base):
    """Gmail label."""
    __tablename__ = "gmail_labels"
    
    label_id = Column(String(100), primary_key=True)
    account_email = Column(String(255), ForeignKey("gmail_accounts.email"), nullable=False)
    name = Column(String(255))
    type = Column(String(50))  # user, system
    message_list_visibility = Column(String(50))
    label_list_visibility = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    account = relationship("GmailAccount", back_populates="labels")


class GmailThread(Base):
    """Gmail thread."""
    __tablename__ = "gmail_threads"
    
    thread_id = Column(String(100), primary_key=True)
    account_email = Column(String(255), ForeignKey("gmail_accounts.email"), nullable=False)
    snippet = Column(Text)
    history_id = Column(String(50))
    message_count = Column(Integer, default=0)
    unread = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    account = relationship("GmailAccount", back_populates="threads")
    messages = relationship("GmailMessage", back_populates="thread", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_gmail_thread_account", "account_email"),
    )


class GmailMessage(Base):
    """Gmail message."""
    __tablename__ = "gmail_messages"
    
    message_id = Column(String(100), primary_key=True)
    account_email = Column(String(255), ForeignKey("gmail_accounts.email"), nullable=False)
    thread_id = Column(String(100), ForeignKey("gmail_threads.thread_id"))
    history_id = Column(String(50))
    
    # Message metadata
    from_address = Column(String(255))
    to_addresses = Column(Text)  # JSON array
    cc_addresses = Column(Text)  # JSON array
    bcc_addresses = Column(Text)  # JSON array
    subject = Column(Text)
    date = Column(DateTime)
    
    # Message content
    body_text = Column(Text)
    body_html = Column(Text)
    snippet = Column(Text)
    
    # Labels and flags
    label_ids = Column(JSON)
    is_unread = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    is_important = Column(Boolean, default=False)
    is_draft = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)
    
    # AI/RAG: Vector embeddings for semantic search (8192 dimensions for Qwen3)
    embedding = Column(Vector(768) if VECTOR_SUPPORT else JSON)  # Legacy 768-dim
    qwen_embedding = Column(Vector(8192) if VECTOR_SUPPORT else JSON)  # Qwen3 8192-dim
    
    # Raw data
    raw_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    account = relationship("GmailAccount", back_populates="messages")
    thread = relationship("GmailThread", back_populates="messages")
    attachments = relationship("GmailAttachment", back_populates="message", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_gmail_message_account", "account_email"),
        Index("idx_gmail_message_thread", "thread_id"),
        Index("idx_gmail_message_date", "date"),
        Index("idx_gmail_message_from", "from_address"),
    )


class GmailAttachment(Base):
    """Gmail attachment."""
    __tablename__ = "gmail_attachments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(100), ForeignKey("gmail_messages.message_id"), nullable=False)
    attachment_id = Column(String(100))
    filename = Column(String(500))
    mimetype = Column(String(100))
    size = Column(Integer)
    local_path = Column(String(500))
    downloaded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    message = relationship("GmailMessage", back_populates="attachments")
    
    __table_args__ = (
        Index("idx_gmail_attachment_message", "message_id"),
    )


# ============================================================================
# Chat Conversation Models
# ============================================================================

class ChatSession(Base):
    """Chat conversation session."""
    __tablename__ = "chat_sessions"
    
    session_id = Column(String(50), primary_key=True)
    title = Column(String(255))  # Auto-generated from first message
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_chat_session_updated", "updated_at"),
    )


class ChatMessage(Base):
    """Individual chat message in a session."""
    __tablename__ = "chat_messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50), ForeignKey("chat_sessions.session_id"), nullable=False)
    role = Column(String(20), nullable=False)  # 'user' or 'assistant'
    content = Column(Text, nullable=False)
    sources = Column(JSON)  # Sources returned with assistant messages
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    session = relationship("ChatSession", back_populates="messages")
    
    __table_args__ = (
        Index("idx_chat_message_session", "session_id"),
        Index("idx_chat_message_created", "created_at"),
    )
