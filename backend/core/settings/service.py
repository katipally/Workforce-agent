"""Settings service helpers for per-user and workspace-wide configuration.

This module sits between the API layer and the database and encapsulates:
- How settings are stored in UserSettings / AppSettings JSON fields.
- How to merge patches into existing settings.
- How to resolve effective values with sensible fallbacks (e.g. Config/env).

It intentionally groups workspace settings into sections (slack, notion, gmail,
workspace, runtime, database, ai_infra) to match the settings_plan.md.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import Config, env_path
from database.db_manager import DatabaseManager
from utils.crypto import encrypt_secret, decrypt_secret
from utils.logger import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _split_csv(value: str) -> List[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _secret_view(encrypted_value: Optional[str], fallback_plain: str = "") -> Dict[str, Any]:
    """Return a dict describing a secret without exposing its full value.

    Keys:
    - set: bool
    - last4: last 4 characters of the underlying secret (or "" if none)
    """

    plain = ""
    if encrypted_value:
        try:
            plain = decrypt_secret(encrypted_value) or ""
        except Exception:
            logger.error("Failed to decrypt secret for view", exc_info=True)
            plain = ""

    if not plain and fallback_plain:
        plain = fallback_plain

    if not plain:
        return {"set": False, "last4": ""}

    last4 = plain[-4:] if len(plain) >= 4 else plain
    return {"set": True, "last4": last4}


def _write_env_vars(updates: Dict[str, str]) -> None:
    if not updates:
        return

    path = env_path
    try:
        if not path.exists():
            lines: List[str] = []
        else:
            text = path.read_text()
            lines = text.splitlines()

        new_lines: List[str] = []
        seen_keys = set()

        for line in lines:
            stripped = line.lstrip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                new_lines.append(line)
                continue

            key, _ = stripped.split("=", 1)
            if key in updates:
                new_lines.append(f"{key}={updates[key]}")
                seen_keys.add(key)
            else:
                new_lines.append(line)

        for key, value in updates.items():
            if key not in seen_keys:
                new_lines.append(f"{key}={value}")

        path.write_text("\n".join(new_lines) + "\n")
    except Exception:
        logger.error("Failed to write env vars from workspace settings", exc_info=True)


# ---------------------------------------------------------------------------
# Personal (per-user) settings
# ---------------------------------------------------------------------------


def get_personal_settings_view(
    db: DatabaseManager,
    user_id: str,
    include_secret: bool = False,
) -> Dict[str, Any]:
    """Return a UI-friendly view of the current user's settings.

    When include_secret is True and a key is configured, the full decrypted
    value is included under openai_api_key_full in addition to the usual
    metadata fields.
    """

    row = db.get_user_settings(user_id)
    raw = row.settings if row and row.settings else {}

    enc_key = raw.get("openai_api_key")
    openai_plain = decrypt_secret(enc_key) if enc_key else ""

    llm_model = raw.get("llm_model") or Config.LLM_MODEL
    timezone = raw.get("timezone")

    result: Dict[str, Any] = {
        "openai_api_key_set": bool(openai_plain),
        "openai_api_key_last4": openai_plain[-4:] if openai_plain else "",
        "llm_model": llm_model,
        "timezone": timezone,
    }

    if include_secret and openai_plain:
        result["openai_api_key_full"] = openai_plain

    return result


def update_personal_settings(
    db: DatabaseManager,
    user_id: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply a partial update to the current user's personal settings."""

    patch: Dict[str, Any] = {}

    if "openai_api_key" in payload:
        val = payload.get("openai_api_key")
        if val is None or val == "":
            patch["openai_api_key"] = None
        else:
            patch["openai_api_key"] = encrypt_secret(str(val))

    if "llm_model" in payload:
        model = payload.get("llm_model")
        if model is None or model == "":
            patch["llm_model"] = None
        else:
            patch["llm_model"] = str(model)

    if "timezone" in payload:
        tz = payload.get("timezone")
        patch["timezone"] = tz if tz else None

    if patch:
        db.upsert_user_settings(user_id, patch)

    return get_personal_settings_view(db, user_id)


def get_effective_openai_key(db: DatabaseManager, user_id: str) -> Optional[str]:
    """Resolve the OpenAI API key for a given user.

    Order:
    1. Personal key in UserSettings (encrypted).
    2. Config.OPENAI_API_KEY from environment as optional global backup.
    """

    row = db.get_user_settings(user_id)
    raw = row.settings if row and row.settings else {}
    enc_key = raw.get("openai_api_key")
    if enc_key:
        key = decrypt_secret(enc_key)
        if key:
            return key

    return Config.OPENAI_API_KEY or None


def get_effective_llm_model(db: DatabaseManager, user_id: str) -> str:
    """Resolve the default LLM model for a given user."""

    row = db.get_user_settings(user_id)
    raw = row.settings if row and row.settings else {}
    model = raw.get("llm_model") or Config.LLM_MODEL
    return model


# ---------------------------------------------------------------------------
# Workspace / App settings (shared)
# ---------------------------------------------------------------------------


def _get_raw_app_settings(db: DatabaseManager) -> Dict[str, Any]:
    row = db.get_app_settings()
    if not row or not row.settings:
        return {}
    return dict(row.settings)


def get_workspace_settings_view(
    db: DatabaseManager,
    include_secrets: bool = False,
) -> Dict[str, Any]:
    """Return a structured view of workspace-wide settings for the UI.

    When include_secrets is True, decrypted secret values are included in the
    response where available (or fall back to Config/* where appropriate).
    """

    raw = _get_raw_app_settings(db)

    slack_raw = raw.get("slack") or {}
    notion_raw = raw.get("notion") or {}
    gmail_raw = raw.get("gmail") or {}
    workspace_raw = raw.get("workspace") or {}
    runtime_raw = raw.get("runtime") or {}
    database_raw = raw.get("database") or {}
    ai_infra_raw = raw.get("ai_infra") or {}

    # Slack secrets
    slack_bot = _secret_view(slack_raw.get("bot_token"), Config.SLACK_BOT_TOKEN)
    slack_user = _secret_view(slack_raw.get("user_token"), Config.SLACK_USER_TOKEN)

    slack_section: Dict[str, Any] = {
        "bot_token_set": slack_bot["set"],
        "bot_token_last4": slack_bot["last4"],
        "user_token_set": slack_user["set"],
        "user_token_last4": slack_user["last4"],
        "mode": slack_raw.get("mode") or Config.SLACK_MODE,
        "readonly_channels": slack_raw.get("readonly_channels")
        or _split_csv(Config.SLACK_READONLY_CHANNELS),
        "blocked_channels": slack_raw.get("blocked_channels")
        or _split_csv(Config.SLACK_BLOCKED_CHANNELS),
    }

    if include_secrets:
        bot_value: Optional[str] = None
        enc_bot = slack_raw.get("bot_token")
        if enc_bot:
            try:
                bot_value = decrypt_secret(enc_bot) or None
            except Exception:
                logger.error("Failed to decrypt Slack bot token from settings", exc_info=True)
        if not bot_value and Config.SLACK_BOT_TOKEN:
            bot_value = Config.SLACK_BOT_TOKEN
        slack_section["bot_token_value"] = bot_value

        user_value: Optional[str] = None
        enc_user = slack_raw.get("user_token")
        if enc_user:
            try:
                user_value = decrypt_secret(enc_user) or None
            except Exception:
                logger.error("Failed to decrypt Slack user token from settings", exc_info=True)
        if not user_value and Config.SLACK_USER_TOKEN:
            user_value = Config.SLACK_USER_TOKEN
        slack_section["user_token_value"] = user_value

    # Notion
    notion_token_view = _secret_view(notion_raw.get("token"), Config.NOTION_TOKEN)
    notion_section: Dict[str, Any] = {
        "token_set": notion_token_view["set"],
        "token_last4": notion_token_view["last4"],
        "mode": notion_raw.get("mode") or Config.NOTION_MODE,
        "parent_page_id": notion_raw.get("parent_page_id") or Config.NOTION_PARENT_PAGE_ID,
    }

    if include_secrets:
        notion_value: Optional[str] = None
        enc_token = notion_raw.get("token")
        if enc_token:
            try:
                notion_value = decrypt_secret(enc_token) or None
            except Exception:
                logger.error("Failed to decrypt Notion token from settings", exc_info=True)
        if not notion_value and Config.NOTION_TOKEN:
            notion_value = Config.NOTION_TOKEN
        notion_section["token_value"] = notion_value

    # Gmail
    gmail_section = {
        "send_mode": gmail_raw.get("send_mode") or Config.GMAIL_SEND_MODE,
        "allowed_send_domains": gmail_raw.get("allowed_send_domains")
        or _split_csv(Config.GMAIL_ALLOWED_SEND_DOMAINS),
        "allowed_read_domains": gmail_raw.get("allowed_read_domains")
        or _split_csv(Config.GMAIL_ALLOWED_READ_DOMAINS),
        "default_label": gmail_raw.get("default_label") or Config.GMAIL_DEFAULT_LABEL,
    }

    # Workspace info
    workspace_section = {
        "name": workspace_raw.get("name") or Config.WORKSPACE_NAME,
        "id": workspace_raw.get("id") or Config.WORKSPACE_ID,
    }

    # Runtime / URLs
    runtime_section = {
        "frontend_base_url": runtime_raw.get("frontend_base_url") or Config.FRONTEND_BASE_URL,
        "api_host": runtime_raw.get("api_host") or Config.API_HOST,
        "api_port": runtime_raw.get("api_port") or Config.API_PORT,
        "log_level": runtime_raw.get("log_level") or Config.LOG_LEVEL,
        "log_file": runtime_raw.get("log_file") or Config.LOG_FILE,
        "tier_4_rate_limit": runtime_raw.get("tier_4_rate_limit") or Config.TIER_4_RATE_LIMIT,
        "default_rate_limit": runtime_raw.get("default_rate_limit") or Config.DEFAULT_RATE_LIMIT,
        "socket_mode_enabled": runtime_raw.get("socket_mode_enabled")
        if "socket_mode_enabled" in runtime_raw
        else Config.SOCKET_MODE_ENABLED,
        "max_reconnect_attempts": runtime_raw.get("max_reconnect_attempts")
        or Config.MAX_RECONNECT_ATTEMPTS,
    }

    # Database / Storage
    database_section = {
        "database_url": database_raw.get("database_url") or Config.DATABASE_URL,
        "data_dir": database_raw.get("data_dir") or str(Config.DATA_DIR),
        "files_dir": database_raw.get("files_dir") or str(Config.FILES_DIR),
        "export_dir": database_raw.get("export_dir") or str(Config.EXPORT_DIR),
        "project_registry_file": database_raw.get("project_registry_file")
        or str(Config.PROJECT_REGISTRY_FILE),
    }

    # AI infrastructure (read-only in UI)
    ai_infra_section = {
        "embedding_model": ai_infra_raw.get("embedding_model") or Config.EMBEDDING_MODEL,
        "reranker_model": ai_infra_raw.get("reranker_model") or Config.RERANKER_MODEL,
        "embedding_batch_size": ai_infra_raw.get("embedding_batch_size")
        or Config.EMBEDDING_BATCH_SIZE,
        "use_gpu": ai_infra_raw.get("use_gpu") if "use_gpu" in ai_infra_raw else Config.USE_GPU,
        "editable": False,
    }

    return {
        "slack": slack_section,
        "notion": notion_section,
        "gmail": gmail_section,
        "workspace": workspace_section,
        "runtime": runtime_section,
        "database": database_section,
        "ai_infra": ai_infra_section,
    }


def update_workspace_settings(db: DatabaseManager, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Apply a partial update to workspace-wide settings.

    The payload is expected to be grouped by section (slack, notion, gmail,
    workspace, runtime, database). The ai_infra section is intentionally
    ignored for writes (read-only in UI).
    """

    raw = _get_raw_app_settings(db)
    patch: Dict[str, Any] = {}
    env_updates: Dict[str, str] = {}

    # Slack section
    slack_update = payload.get("slack")
    if isinstance(slack_update, dict):
        current = dict(raw.get("slack") or {})

        if "bot_token" in slack_update:
            val = slack_update.get("bot_token")
            if val:
                current["bot_token"] = encrypt_secret(str(val))
                env_updates["SLACK_BOT_TOKEN"] = str(val)
            else:
                current.pop("bot_token", None)
                env_updates["SLACK_BOT_TOKEN"] = ""

        if "app_token" in slack_update:
            val = slack_update.get("app_token")
            if val:
                current["app_token"] = encrypt_secret(str(val))
            else:
                current.pop("app_token", None)

        # Non-secret fields
        for key in [
            "app_id",
            "client_id",
            "client_secret",
            "signing_secret",
            "verification_token",
            "mode",
        ]:
            if key in slack_update:
                value = slack_update.get(key)
                current[key] = value

                if key == "mode" and value is not None:
                    env_updates["SLACK_MODE"] = str(value)

        if "user_token" in slack_update:
            val = slack_update.get("user_token")
            if val:
                current["user_token"] = encrypt_secret(str(val))
            else:
                current.pop("user_token", None)

        if "readonly_channels" in slack_update:
            current["readonly_channels"] = slack_update.get("readonly_channels") or []
            channels_list = current["readonly_channels"] or []
            env_updates["SLACK_READONLY_CHANNELS"] = ",".join(channels_list)

        if "blocked_channels" in slack_update:
            current["blocked_channels"] = slack_update.get("blocked_channels") or []
            channels_list = current["blocked_channels"] or []
            env_updates["SLACK_BLOCKED_CHANNELS"] = ",".join(channels_list)

        patch["slack"] = current

    # Notion section
    notion_update = payload.get("notion")
    if isinstance(notion_update, dict):
        current = dict(raw.get("notion") or {})

        if "token" in notion_update:
            val = notion_update.get("token")
            if val:
                current["token"] = encrypt_secret(str(val))
                env_updates["NOTION_TOKEN"] = str(val)
            else:
                current.pop("token", None)
                env_updates["NOTION_TOKEN"] = ""

        if "mode" in notion_update:
            mode_val = notion_update.get("mode")
            current["mode"] = mode_val
            if mode_val is not None:
                env_updates["NOTION_MODE"] = str(mode_val)

        if "parent_page_id" in notion_update:
            parent_id = notion_update.get("parent_page_id")
            current["parent_page_id"] = parent_id
            env_updates["NOTION_PARENT_PAGE_ID"] = str(parent_id or "")

        patch["notion"] = current

    # Gmail section
    gmail_update = payload.get("gmail")
    if isinstance(gmail_update, dict):
        current = dict(raw.get("gmail") or {})

        if "send_mode" in gmail_update:
            mode_val = gmail_update.get("send_mode")
            current["send_mode"] = mode_val
            if mode_val is not None:
                env_updates["GMAIL_SEND_MODE"] = str(mode_val)

        if "allowed_send_domains" in gmail_update:
            send_domains = gmail_update.get("allowed_send_domains") or []
            current["allowed_send_domains"] = send_domains
            env_updates["GMAIL_ALLOWED_SEND_DOMAINS"] = ",".join(send_domains)

        if "allowed_read_domains" in gmail_update:
            read_domains = gmail_update.get("allowed_read_domains") or []
            current["allowed_read_domains"] = read_domains
            env_updates["GMAIL_ALLOWED_READ_DOMAINS"] = ",".join(read_domains)

        if "default_label" in gmail_update:
            default_label = gmail_update.get("default_label")
            current["default_label"] = default_label
            env_updates["GMAIL_DEFAULT_LABEL"] = str(default_label or "")

        patch["gmail"] = current

    # Workspace info
    workspace_update = payload.get("workspace")
    if isinstance(workspace_update, dict):
        current = dict(raw.get("workspace") or {})
        if "name" in workspace_update:
            name_val = workspace_update.get("name")
            current["name"] = name_val
            env_updates["WORKSPACE_NAME"] = str(name_val or "")
        if "id" in workspace_update:
            workspace_id = workspace_update.get("id")
            current["id"] = workspace_id
            env_updates["WORKSPACE_ID"] = str(workspace_id or "")
        patch["workspace"] = current

    # Runtime / URLs and logging
    runtime_update = payload.get("runtime")
    if isinstance(runtime_update, dict):
        current = dict(raw.get("runtime") or {})
        for key in [
            "frontend_base_url",
            "api_host",
            "api_port",
            "log_level",
            "log_file",
            "tier_4_rate_limit",
            "default_rate_limit",
            "socket_mode_enabled",
            "max_reconnect_attempts",
        ]:
            if key in runtime_update:
                value = runtime_update.get(key)
                current[key] = value

                if key == "frontend_base_url" and value is not None:
                    env_updates["FRONTEND_BASE_URL"] = str(value)
                elif key == "api_host" and value is not None:
                    env_updates["API_HOST"] = str(value)
                elif key == "api_port":
                    env_updates["API_PORT"] = "" if value is None else str(value)
                elif key == "log_level" and value is not None:
                    env_updates["LOG_LEVEL"] = str(value)
                elif key == "log_file" and value is not None:
                    env_updates["LOG_FILE"] = str(value)
                elif key == "tier_4_rate_limit":
                    env_updates["TIER_4_RATE_LIMIT"] = "" if value is None else str(value)
                elif key == "default_rate_limit":
                    env_updates["DEFAULT_RATE_LIMIT"] = "" if value is None else str(value)
                elif key == "socket_mode_enabled" and value is not None:
                    env_updates["SOCKET_MODE_ENABLED"] = "true" if bool(value) else "false"
                elif key == "max_reconnect_attempts":
                    env_updates["MAX_RECONNECT_ATTEMPTS"] = "" if value is None else str(value)
        patch["runtime"] = current

    # Database / Storage
    database_update = payload.get("database")
    if isinstance(database_update, dict):
        current = dict(raw.get("database") or {})
        for key in [
            "database_url",
            "data_dir",
            "files_dir",
            "export_dir",
            "project_registry_file",
        ]:
            if key in database_update:
                current[key] = database_update.get(key)
        patch["database"] = current

    # ai_infra is intentionally read-only; we ignore any updates

    if patch:
        db.upsert_app_settings(patch)
        if env_updates:
            _write_env_vars(env_updates)

    return get_workspace_settings_view(db)


# ---------------------------------------------------------------------------
# Runtime helpers for Slack / Notion
# ---------------------------------------------------------------------------


def get_effective_slack_bot_token(db: DatabaseManager) -> Optional[str]:
    """Return the Slack bot token from workspace settings or Config.

    Order:
    1. Decrypted bot_token from AppSettings.slack.bot_token
    2. Config.SLACK_BOT_TOKEN
    """

    raw = _get_raw_app_settings(db)
    slack_raw = raw.get("slack") or {}
    enc = slack_raw.get("bot_token")
    if enc:
        try:
            token = decrypt_secret(enc)
            if token:
                return token
        except Exception:
            logger.error("Failed to decrypt Slack bot token from settings", exc_info=True)

    return Config.SLACK_BOT_TOKEN or None


def get_effective_notion_token(db: DatabaseManager) -> Optional[str]:
    """Return the Notion integration token from workspace settings or Config."""

    raw = _get_raw_app_settings(db)
    notion_raw = raw.get("notion") or {}
    enc = notion_raw.get("token")
    if enc:
        try:
            token = decrypt_secret(enc)
            if token:
                return token
        except Exception:
            logger.error("Failed to decrypt Notion token from settings", exc_info=True)

    return Config.NOTION_TOKEN or None


def bootstrap_app_settings_from_config_if_empty(db: DatabaseManager) -> None:
    raw = _get_raw_app_settings(db)
    if raw:
        return

    patch: Dict[str, Any] = {}

    slack_section: Dict[str, Any] = {}
    if Config.SLACK_BOT_TOKEN:
        slack_section["bot_token"] = encrypt_secret(Config.SLACK_BOT_TOKEN)
    if Config.SLACK_APP_TOKEN:
        slack_section["app_token"] = encrypt_secret(Config.SLACK_APP_TOKEN)
    if Config.SLACK_MODE:
        slack_section["mode"] = Config.SLACK_MODE
    readonly = _split_csv(Config.SLACK_READONLY_CHANNELS)
    if readonly:
        slack_section["readonly_channels"] = readonly
    blocked = _split_csv(Config.SLACK_BLOCKED_CHANNELS)
    if blocked:
        slack_section["blocked_channels"] = blocked
    if slack_section:
        patch["slack"] = slack_section

    notion_section: Dict[str, Any] = {}
    if Config.NOTION_TOKEN:
        notion_section["token"] = encrypt_secret(Config.NOTION_TOKEN)
    if Config.NOTION_MODE:
        notion_section["mode"] = Config.NOTION_MODE
    if Config.NOTION_PARENT_PAGE_ID:
        notion_section["parent_page_id"] = Config.NOTION_PARENT_PAGE_ID
    if notion_section:
        patch["notion"] = notion_section

    gmail_section: Dict[str, Any] = {}
    if Config.GMAIL_SEND_MODE:
        gmail_section["send_mode"] = Config.GMAIL_SEND_MODE
    send_domains = _split_csv(Config.GMAIL_ALLOWED_SEND_DOMAINS)
    if send_domains:
        gmail_section["allowed_send_domains"] = send_domains
    read_domains = _split_csv(Config.GMAIL_ALLOWED_READ_DOMAINS)
    if read_domains:
        gmail_section["allowed_read_domains"] = read_domains
    if Config.GMAIL_DEFAULT_LABEL:
        gmail_section["default_label"] = Config.GMAIL_DEFAULT_LABEL
    if gmail_section:
        patch["gmail"] = gmail_section

    workspace_section: Dict[str, Any] = {}
    if Config.WORKSPACE_NAME:
        workspace_section["name"] = Config.WORKSPACE_NAME
    if Config.WORKSPACE_ID:
        workspace_section["id"] = Config.WORKSPACE_ID
    if workspace_section:
        patch["workspace"] = workspace_section

    runtime_section: Dict[str, Any] = {}
    if Config.FRONTEND_BASE_URL:
        runtime_section["frontend_base_url"] = Config.FRONTEND_BASE_URL
    if Config.API_HOST:
        runtime_section["api_host"] = Config.API_HOST
    runtime_section["api_port"] = Config.API_PORT
    if Config.LOG_LEVEL:
        runtime_section["log_level"] = Config.LOG_LEVEL
    if Config.LOG_FILE:
        runtime_section["log_file"] = Config.LOG_FILE
    runtime_section["tier_4_rate_limit"] = Config.TIER_4_RATE_LIMIT
    runtime_section["default_rate_limit"] = Config.DEFAULT_RATE_LIMIT
    runtime_section["socket_mode_enabled"] = Config.SOCKET_MODE_ENABLED
    runtime_section["max_reconnect_attempts"] = Config.MAX_RECONNECT_ATTEMPTS
    if runtime_section:
        patch["runtime"] = runtime_section

    database_section: Dict[str, Any] = {}
    if Config.DATABASE_URL:
        database_section["database_url"] = Config.DATABASE_URL
    database_section["data_dir"] = str(Config.DATA_DIR)
    database_section["files_dir"] = str(Config.FILES_DIR)
    database_section["export_dir"] = str(Config.EXPORT_DIR)
    database_section["project_registry_file"] = str(Config.PROJECT_REGISTRY_FILE)
    if database_section:
        patch["database"] = database_section

    ai_infra_section: Dict[str, Any] = {}
    if Config.EMBEDDING_MODEL:
        ai_infra_section["embedding_model"] = Config.EMBEDDING_MODEL
    if Config.RERANKER_MODEL:
        ai_infra_section["reranker_model"] = Config.RERANKER_MODEL
    ai_infra_section["embedding_batch_size"] = Config.EMBEDDING_BATCH_SIZE
    ai_infra_section["use_gpu"] = Config.USE_GPU
    if ai_infra_section:
        patch["ai_infra"] = ai_infra_section

    if patch:
        db.upsert_app_settings(patch)
