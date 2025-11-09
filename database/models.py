"""SQLAlchemy models for Slack data."""
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, Integer, Float, DateTime,
    ForeignKey, Text, JSON, Index, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

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
# Gmail Models
# ============================================================================

class GmailAccount(Base):
    """Gmail account information."""
    __tablename__ = "gmail_accounts"
    
    email_address = Column(String(255), primary_key=True)
    messages_total = Column(Integer)
    threads_total = Column(Integer)
    history_id = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    emails = relationship("GmailMessage", back_populates="account", cascade="all, delete-orphan")
    threads = relationship("GmailThread", back_populates="account", cascade="all, delete-orphan")
    labels = relationship("GmailLabel", back_populates="account", cascade="all, delete-orphan")


class GmailLabel(Base):
    """Gmail labels (folders)."""
    __tablename__ = "gmail_labels"
    
    label_id = Column(String(100), primary_key=True)
    account_email = Column(String(255), ForeignKey("gmail_accounts.email_address"))
    name = Column(String(255))
    type = Column(String(50))  # system, user
    message_list_visibility = Column(String(50))
    label_list_visibility = Column(String(50))
    messages_total = Column(Integer)
    messages_unread = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    account = relationship("GmailAccount", back_populates="labels")


class GmailThread(Base):
    """Gmail conversation thread."""
    __tablename__ = "gmail_threads"
    
    thread_id = Column(String(100), primary_key=True)
    account_email = Column(String(255), ForeignKey("gmail_accounts.email_address"))
    snippet = Column(Text)
    history_id = Column(String(50))
    message_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    account = relationship("GmailAccount", back_populates="threads")
    messages = relationship("GmailMessage", back_populates="thread", cascade="all, delete-orphan")


class GmailMessage(Base):
    """Gmail email message."""
    __tablename__ = "gmail_messages"
    
    message_id = Column(String(100), primary_key=True)
    account_email = Column(String(255), ForeignKey("gmail_accounts.email_address"))
    thread_id = Column(String(100), ForeignKey("gmail_threads.thread_id"))
    
    # Message metadata
    history_id = Column(String(50))
    internal_date = Column(DateTime)
    size_estimate = Column(Integer)
    
    # Headers
    subject = Column(Text)
    from_email = Column(String(500))
    to_email = Column(Text)
    cc_email = Column(Text)
    bcc_email = Column(Text)
    reply_to = Column(String(500))
    date = Column(DateTime)
    
    # Content
    snippet = Column(Text)
    body_plain = Column(Text)
    body_html = Column(Text)
    
    # Labels
    label_ids = Column(JSON)  # List of label IDs
    
    # Flags
    is_read = Column(Boolean, default=False)
    is_starred = Column(Boolean, default=False)
    is_important = Column(Boolean, default=False)
    is_sent = Column(Boolean, default=False)
    is_draft = Column(Boolean, default=False)
    is_trash = Column(Boolean, default=False)
    is_spam = Column(Boolean, default=False)
    
    # Attachments
    has_attachments = Column(Boolean, default=False)
    attachment_count = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    account = relationship("GmailAccount", back_populates="emails")
    thread = relationship("GmailThread", back_populates="messages")
    attachments = relationship("GmailAttachment", back_populates="message", cascade="all, delete-orphan")
    
    # Indexes
    __table_args__ = (
        Index('idx_gmail_message_thread', 'thread_id'),
        Index('idx_gmail_message_date', 'date'),
        Index('idx_gmail_message_from', 'from_email'),
    )


class GmailAttachment(Base):
    """Gmail message attachment."""
    __tablename__ = "gmail_attachments"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(String(100), ForeignKey("gmail_messages.message_id"))
    attachment_id = Column(String(255))  # Gmail attachment ID
    
    # Attachment info
    filename = Column(String(500))
    mime_type = Column(String(255))
    size = Column(Integer)
    
    # Local storage
    local_path = Column(String(1000))
    is_downloaded = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    message = relationship("GmailMessage", back_populates="attachments")
    
    # Indexes
    __table_args__ = (
        Index('idx_gmail_attachment_message', 'message_id'),
    )
