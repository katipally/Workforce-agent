"""SQLAlchemy database models for Workforce Agent.

Defines all database tables for:
- Slack data (workspaces, users, channels, messages, files, reactions)
- Gmail data (accounts, labels, threads, messages, attachments)
- PostgreSQL with optional pgvector support for AI/RAG features
"""
from datetime import datetime
from uuid import uuid4
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
    
    # AI/RAG: Vector embeddings for semantic search
    # Dimension is managed dynamically via migration scripts (update_schema_dynamic.py).
    # If pgvector is not available, embeddings are stored as JSON arrays.
    embedding = Column(JSON)
    
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
    
    # AI/RAG: Vector embeddings for semantic search
    # Dimension is managed dynamically via migration scripts (update_schema_dynamic.py).
    # If pgvector is not available, embeddings are stored as JSON arrays.
    embedding = Column(JSON)
    
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
    owner_user_id = Column(String(50), ForeignKey("app_users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_chat_session_owner", "owner_user_id"),
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


class Project(Base):
    """Cross-application project definition for the Projects tab."""
    __tablename__ = "projects"

    id = Column(String(50), primary_key=True, default=lambda: uuid4().hex)
    owner_user_id = Column(String(50), ForeignKey("app_users.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="not_started")
    summary = Column(Text)
    main_goal = Column(Text)
    current_status_summary = Column(Text)
    important_notes = Column(Text)
    last_project_sync_at = Column(DateTime)
    last_summary_generated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sources = relationship("ProjectSource", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_project_owner", "owner_user_id"),
        Index("idx_project_status", "status"),
        Index("idx_project_updated", "updated_at"),
    )


class ProjectSource(Base):
    """Mapping between a project and its underlying data sources."""
    __tablename__ = "project_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(String(50), ForeignKey("projects.id"), nullable=False)
    source_type = Column(String(50), nullable=False)
    source_id = Column(String(255), nullable=False)
    display_name = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="sources")

    __table_args__ = (
        UniqueConstraint("project_id", "source_type", "source_id", name="uq_project_source"),
        Index("idx_project_source_project", "project_id"),
        Index("idx_project_source_type", "source_type"),
    )


class Workflow(Base):
    """Definition of a live workflow (e.g., Slack → Notion)."""
    __tablename__ = "workflows"

    id = Column(String(50), primary_key=True, default=lambda: uuid4().hex)
    name = Column(String(255), nullable=False)
    type = Column(String(50), nullable=False)
    status = Column(String(20), default="active")
    notion_master_page_id = Column(String(255))
    poll_interval_seconds = Column(Integer, default=30)
    last_run_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    channel_mappings = relationship(
        "WorkflowChannelMapping",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )
    message_mappings = relationship(
        "SlackNotionMessageMapping",
        back_populates="workflow",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_workflow_type", "type"),
        Index("idx_workflow_status", "status"),
        Index("idx_workflow_updated", "updated_at"),
    )


class WorkflowChannelMapping(Base):
    """Mapping between a workflow and its Slack channels / Notion subpages."""
    __tablename__ = "workflow_channel_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(50), ForeignKey("workflows.id"), nullable=False)
    slack_channel_id = Column(String(20), nullable=False)
    slack_channel_name = Column(String(255))
    notion_subpage_id = Column(String(50))
    last_slack_ts_synced = Column(Float)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="channel_mappings")

    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "slack_channel_id",
            name="uq_workflow_channel",
        ),
        Index("idx_workflow_channel_workflow", "workflow_id"),
        Index("idx_workflow_channel_slack", "slack_channel_id"),
    )


class SlackNotionMessageMapping(Base):
    """Mapping between individual Slack messages and Notion blocks per workflow."""
    __tablename__ = "slack_notion_message_mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(50), ForeignKey("workflows.id"), nullable=False)
    slack_channel_id = Column(String(20), nullable=False)
    slack_ts = Column(Float, nullable=False)
    parent_slack_ts = Column(Float)
    notion_block_id = Column(String(100), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    workflow = relationship("Workflow", back_populates="message_mappings")

    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "slack_channel_id",
            "slack_ts",
            name="uq_workflow_slack_message",
        ),
        Index("idx_slack_notion_workflow", "workflow_id"),
        Index("idx_slack_notion_channel", "slack_channel_id"),
        Index("idx_slack_notion_parent_ts", "parent_slack_ts"),
    )


class AppUser(Base):
    """Application user."""
    __tablename__ = "app_users"

    id = Column(String(50), primary_key=True, default=lambda: uuid4().hex)
    google_sub = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255))
    picture_url = Column(String(500))
    is_admin = Column(Boolean, default=False)
    has_gmail_access = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login_at = Column(DateTime)


class UserOAuthToken(Base):
    """User OAuth token."""
    __tablename__ = "user_oauth_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(50), ForeignKey("app_users.id"), nullable=False)
    provider = Column(String(50), nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text)
    expires_at = Column(DateTime)
    scope = Column(Text)
    token_type = Column(String(50))
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_oauth_provider"),
        Index("idx_user_oauth_user", "user_id"),
    )


class AppSession(Base):
    """Application session."""
    __tablename__ = "app_sessions"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(50), ForeignKey("app_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime)
    last_seen_at = Column(DateTime)
    ip_address = Column(String(100))
    user_agent = Column(String(500))

    __table_args__ = (
        Index("idx_app_session_user", "user_id"),
        Index("idx_app_session_expires", "expires_at"),
    )


class UserSettings(Base):
    """Per-user settings (e.g., personal API keys, preferences).

    Stored as a JSON document so we can evolve settings without schema
    migrations. There is at most one row per AppUser.
    """

    __tablename__ = "user_settings"

    user_id = Column(String(50), ForeignKey("app_users.id"), primary_key=True)
    settings = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppSettings(Base):
    """Application / workspace-wide settings.

    For now we treat a single row with scope="global" as the shared settings
    document for this deployment.
    """

    __tablename__ = "app_settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(50), unique=True, default="global")
    settings = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("idx_app_settings_scope", "scope"),
    )


class PipelineRun(Base):
    """Track pipeline run status across multiple workers.
    
    Stores status for Slack, Notion, Gmail pipelines so that
    status can be queried from any Uvicorn worker.
    """
    
    __tablename__ = "pipeline_runs"
    
    run_id = Column(String(64), primary_key=True)
    pipeline_type = Column(String(50), nullable=False)  # 'slack', 'notion', 'gmail'
    status = Column(String(50), default="pending")  # pending, running, completed, failed, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    stats = Column(JSON, default=dict)
    error = Column(Text, nullable=True)
    config = Column(JSON, default=dict)  # Store include_archived, download_files, etc.
    cancel_requested = Column(Boolean, default=False)
    
    __table_args__ = (
        Index("idx_pipeline_runs_type_status", "pipeline_type", "status"),
        Index("idx_pipeline_runs_created", "created_at"),
    )
