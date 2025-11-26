"""Core logic for Slack → Notion workflows.

This module implements a single synchronous entry point
`process_workflow_once(workflow_id: str)` that:

- Loads the workflow and its channel mappings from the database
- Ensures per-channel Notion subpages exist under the master page
- Polls Slack for recent messages in each channel
- Mirrors new messages and their thread replies into Notion
- Records Slack→Notion mappings to guarantee idempotency
- Updates the workflow's `last_run_at` timestamp

The worker process and the /api/workflows/{id}/run-once endpoint both call
this function.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Set

from core.database.db_manager import DatabaseManager
from core.slack.client import SlackClient
from core.notion_export.client import NotionClient
from core.utils.logger import get_logger
from settings.service import get_effective_slack_bot_token, get_effective_notion_token

logger = get_logger(__name__)

# Best-effort deletion sync can be noisy for some workspaces (e.g. when
# messages are pruned frequently or workflows are re-created). Gate it behind
# a module-level flag so we can disable it in hosting environments.
DELETION_SYNC_ENABLED = False


def _build_message_text(message: Dict[str, Any], is_reply: bool = False) -> str:
    """Format a Slack message into a human-readable text block.

    We keep this compact but informative: timestamp, author, text, reactions, files.
    """
    ts_raw = message.get("ts") or "0"
    try:
        ts = float(ts_raw)
    except Exception:
        ts = 0.0
    ts_str = datetime.fromtimestamp(ts).isoformat() if ts > 0 else ""

    author = (
        message.get("__wf_author_name")
        or message.get("user")
        or message.get("username")
        or message.get("bot_id")
        or "someone"
    )

    prefix = f"{ts_str} – {author}"
    if is_reply:
        prefix += " (reply)"

    text = (message.get("text") or "").strip()
    if len(text) > 800:
        text = text[:800] + "…"

    reactions = message.get("reactions") or []
    reactions_str = ""
    if reactions:
        parts: List[str] = []
        for r in reactions:
            name = r.get("name") or "?"
            count = r.get("count") or 0
            parts.append(f"{name}×{count}")
        reactions_str = f"[reactions: {', '.join(parts)}]"

    files = message.get("files") or []
    files_str = ""
    if files:
        names: List[str] = []
        for f in files:
            name = f.get("name") or f.get("title") or "file"
            names.append(name)
        files_str = f"[files: {', '.join(names)}]"

    lines: List[str] = [prefix]
    if text:
        lines.append(text)
    if reactions_str:
        lines.append(reactions_str)
    if files_str:
        lines.append(files_str)

    return "\n".join(lines)


def process_workflow_once(workflow_id: str) -> Dict[str, Any]:
    """Run a Slack → Notion workflow once.

    Returns a small stats dict suitable for logging / API responses.
    """
    db = DatabaseManager()
    workflow = db.get_workflow(workflow_id)
    if not workflow:
        raise ValueError(f"Workflow {workflow_id} not found")

    if workflow.type != "slack_to_notion":
        logger.info("Workflow %s is type %s, skipping", workflow_id, workflow.type)
        return {
            "workflow_id": workflow_id,
            "messages_synced": 0,
            "replies_synced": 0,
            "channels_processed": 0,
            "skipped": True,
            "reason": "unsupported_type",
        }

    if workflow.status != "active":
        logger.info("Workflow %s is not active (status=%s), skipping", workflow_id, workflow.status)
        return {
            "workflow_id": workflow_id,
            "messages_synced": 0,
            "replies_synced": 0,
            "channels_processed": 0,
            "skipped": True,
            "reason": "inactive",
        }

    if not workflow.notion_master_page_id:
        logger.warning("Workflow %s has no notion_master_page_id; nothing to do", workflow_id)
        return {
            "workflow_id": workflow_id,
            "messages_synced": 0,
            "replies_synced": 0,
            "channels_processed": 0,
            "skipped": True,
            "reason": "missing_notion_master_page_id",
        }

    channels = db.get_workflow_channels(workflow_id)
    if not channels:
        logger.info("Workflow %s has no channel mappings; nothing to do", workflow_id)
        return {
            "workflow_id": workflow_id,
            "messages_synced": 0,
            "replies_synced": 0,
            "channels_processed": 0,
            "skipped": True,
            "reason": "no_channels",
        }

    try:
        slack_token = get_effective_slack_bot_token(db)
        slack = SlackClient(token=slack_token)
    except Exception as e:  # pragma: no cover - defensive
        logger.error("Failed to initialize Slack client: %s", e, exc_info=True)
        return {
            "workflow_id": workflow_id,
            "messages_synced": 0,
            "replies_synced": 0,
            "channels_processed": 0,
            "skipped": True,
            "reason": "slack_init_failed",
        }

    notion_token = get_effective_notion_token(db)
    notion = NotionClient(token=notion_token)
    if not notion.client:
        logger.error("Notion client not initialized (missing NOTION_TOKEN)")
        return {
            "workflow_id": workflow_id,
            "messages_synced": 0,
            "replies_synced": 0,
            "channels_processed": 0,
            "skipped": True,
            "reason": "notion_init_failed",
        }

    messages_synced = 0
    replies_synced = 0
    channels_processed = 0

    # Simple in-memory cache for Slack user display names so we only call
    # users.info once per user per run.
    user_name_cache: Dict[str, str] = {}

    def _resolve_user_name(user_id: str | None) -> str:
        if not user_id:
            return "someone"
        if user_id in user_name_cache:
            return user_name_cache[user_id]
        try:
            resp = slack.users_info(user=user_id)
        except Exception:  # pragma: no cover - defensive
            user_name_cache[user_id] = user_id
            return user_id

        data = resp.get("user") or {}
        profile = data.get("profile") or {}
        name = (
            profile.get("real_name")
            or profile.get("display_name")
            or data.get("name")
            or user_id
        )
        user_name_cache[user_id] = name
        return name

    started_at = datetime.utcnow()

    for mapping in channels:
        channel_id = mapping.slack_channel_id
        channel_name = mapping.slack_channel_name or channel_id

        # Ensure a Notion subpage exists for this channel
        notion_subpage_id = mapping.notion_subpage_id

        # If the existing subpage has been archived in Notion, automatically
        # repair the mapping by creating a fresh subpage and updating the DB
        # so workflows can keep running without manual intervention.
        if notion_subpage_id:
            is_archived = notion.is_block_archived(notion_subpage_id)
            if is_archived:
                logger.info(
                    "Notion subpage %s for workflow %s channel %s is archived; "
                    "creating a new subpage and remapping this channel.",
                    notion_subpage_id,
                    workflow_id,
                    channel_id,
                )
                title = f"#{channel_name} – Slack feed"
                new_page_id = notion.create_page(
                    parent_page_id=workflow.notion_master_page_id,
                    title=title,
                    children=None,
                )
                if not new_page_id:
                    logger.error(
                        "Failed to recreate Notion subpage for workflow %s channel %s",
                        workflow_id,
                        channel_id,
                    )
                    channels_processed += 1
                    continue
                mapping = db.add_workflow_channel(
                    workflow_id=workflow_id,
                    slack_channel_id=channel_id,
                    slack_channel_name=channel_name,
                    notion_subpage_id=new_page_id,
                )
                notion_subpage_id = new_page_id

        if not notion_subpage_id:
            title = f"#{channel_name} – Slack feed"
            page_id = notion.create_page(
                parent_page_id=workflow.notion_master_page_id,
                title=title,
                children=None,
            )
            if not page_id:
                logger.error(
                    "Failed to create Notion subpage for workflow %s channel %s",
                    workflow_id,
                    channel_id,
                )
                continue
            mapping = db.add_workflow_channel(
                workflow_id=workflow_id,
                slack_channel_id=channel_id,
                slack_channel_name=channel_name,
                notion_subpage_id=page_id,
            )
            notion_subpage_id = page_id

        # Fetch recent messages (most recent first); we rely on mappings to avoid
        # duplicates instead of tracking a strict timestamp offset.
        seen_ts: Set[float] = set()
        try:
            history = slack.conversations_history(
                channel=channel_id,
                limit=200,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.error(
                "Error fetching Slack history for channel %s: %s",
                channel_id,
                e,
                exc_info=True,
            )
            continue

        slack_messages = history.get("messages", [])
        if not slack_messages:
            continue

        # Process oldest → newest to keep Notion ordering intuitive.
        slack_messages = sorted(slack_messages, key=lambda m: float(m.get("ts", "0")))

        for msg in slack_messages:
            ts_raw = msg.get("ts")
            if not ts_raw:
                continue
            try:
                ts = float(ts_raw)
            except Exception:
                continue

            # Track all message timestamps we see so we can later detect
            # best-effort deletions for recent messages.
            seen_ts.add(ts)

            # Check if we've already mirrored this root message.
            existing = db.get_slack_notion_mapping(workflow_id, channel_id, ts)
            if existing:
                notion_root_block_id = existing.notion_block_id

                # Refresh the Notion block so edits and reaction changes are reflected.
                raw_user_id = msg.get("user") or msg.get("user_id")
                msg["__wf_author_name"] = _resolve_user_name(raw_user_id)
                text = _build_message_text(msg, is_reply=False)
                updated = notion.update_bulleted_list_item(notion_root_block_id, text)
                if not updated:
                    is_archived_root = notion.is_block_archived(notion_root_block_id)
                    if is_archived_root:
                        db.delete_slack_notion_mapping(workflow_id, channel_id, ts)
            else:
                # Resolve human-friendly author name for the root message.
                raw_user_id = msg.get("user") or msg.get("user_id")
                msg["__wf_author_name"] = _resolve_user_name(raw_user_id)

                text = _build_message_text(msg, is_reply=False)

                block = notion.create_bulleted_list_item(text)
                block_ids = notion.append_blocks_and_get_ids(notion_subpage_id, [block])
                if not block_ids:
                    logger.error(
                        "Failed to append Notion block for workflow %s channel %s message %s",
                        workflow_id,
                        channel_id,
                        ts_raw,
                    )
                    continue
                notion_root_block_id = block_ids[0]
                db.create_slack_notion_mapping(
                    workflow_id=workflow_id,
                    slack_channel_id=channel_id,
                    slack_ts=ts,
                    parent_slack_ts=None,
                    notion_block_id=notion_root_block_id,
                )
                messages_synced += 1

            # If this message has a thread, fetch replies and attach as children
            reply_count = msg.get("reply_count") or 0
            if reply_count > 0:
                try:
                    thread = slack.conversations_replies(channel=channel_id, ts=ts_raw)
                except Exception as e:  # pragma: no cover - defensive
                    logger.error(
                        "Error fetching replies for channel %s ts=%s: %s",
                        channel_id,
                        ts_raw,
                        e,
                        exc_info=True,
                    )
                    continue

                thread_messages = thread.get("messages", [])
                # First element is the root; skip it and process only replies.
                for reply in thread_messages[1:]:
                    r_ts_raw = reply.get("ts")
                    if not r_ts_raw:
                        continue
                    try:
                        r_ts = float(r_ts_raw)
                    except Exception:
                        continue

                    seen_ts.add(r_ts)

                    existing_reply = db.get_slack_notion_mapping(
                        workflow_id,
                        channel_id,
                        r_ts,
                    )
                    if existing_reply:
                        # Update existing reply so edits and reactions are reflected.
                        raw_reply_user_id = reply.get("user") or reply.get("user_id")
                        reply["__wf_author_name"] = _resolve_user_name(raw_reply_user_id)

                        reply_text = _build_message_text(reply, is_reply=True)
                        updated_reply = notion.update_bulleted_list_item(
                            existing_reply.notion_block_id, reply_text
                        )
                        if not updated_reply:
                            is_archived_reply = notion.is_block_archived(existing_reply.notion_block_id)
                            if is_archived_reply:
                                db.delete_slack_notion_mapping(workflow_id, channel_id, r_ts)
                        continue

                    # Resolve human-friendly author name for the reply.
                    raw_reply_user_id = reply.get("user") or reply.get("user_id")
                    reply["__wf_author_name"] = _resolve_user_name(raw_reply_user_id)

                    reply_text = _build_message_text(reply, is_reply=True)
                    reply_block = notion.create_bulleted_list_item(reply_text)

                    # If the root Notion block for this thread has been archived,
                    # skip syncing replies instead of repeatedly raising API errors.
                    is_root_archived = notion.is_block_archived(notion_root_block_id)
                    if is_root_archived:
                        logger.warning(
                            "Notion root block %s for workflow %s channel %s ts=%s is archived; "
                            "skipping replies for this thread. Unarchive or delete the block to resume syncing.",
                            notion_root_block_id,
                            workflow_id,
                            channel_id,
                            r_ts_raw,
                        )
                        continue

                    child_ids = notion.append_blocks_and_get_ids(
                        notion_root_block_id,
                        [reply_block],
                    )
                    if not child_ids:
                        logger.error(
                            "Failed to append reply block for workflow %s channel %s ts=%s",
                            workflow_id,
                            channel_id,
                            r_ts_raw,
                        )
                        continue

                    db.create_slack_notion_mapping(
                        workflow_id=workflow_id,
                        slack_channel_id=channel_id,
                        slack_ts=r_ts,
                        parent_slack_ts=ts,
                        notion_block_id=child_ids[0],
                    )
                    replies_synced += 1

        # After processing all visible messages for this channel, we optionally
        # perform a best-effort deletion sync for recent messages: any mapped
        # message whose Slack timestamp is within the current history window
        # but whose ts is no longer present in `seen_ts` is treated as deleted
        # in Slack and marked accordingly in Notion. This behavior is gated
        # behind DELETION_SYNC_ENABLED because it can be surprising in some
        # deployments.
        if DELETION_SYNC_ENABLED and seen_ts:
            try:
                min_seen_ts = min(seen_ts)
                recent_mappings = db.list_slack_notion_mappings_for_channel_since(
                    workflow_id=workflow_id,
                    slack_channel_id=channel_id,
                    min_slack_ts=min_seen_ts,
                )

                for m in recent_mappings:
                    # Only consider mappings in the recent window which are
                    # missing from the latest Slack history as deleted.
                    if m.slack_ts in seen_ts:
                        continue

                    if not m.slack_ts:
                        continue

                    ts_str = datetime.fromtimestamp(m.slack_ts).isoformat()
                    deleted_text = f"{ts_str} - [deleted in Slack]"
                    try:
                        notion.update_bulleted_list_item(m.notion_block_id, deleted_text)
                    except Exception as e:  # pragma: no cover - defensive
                        logger.error(
                            "Failed to mark deleted message for workflow %s channel %s ts=%s: %s",
                            workflow_id,
                            channel_id,
                            m.slack_ts,
                            e,
                            exc_info=True,
                        )
            except Exception as e:  # pragma: no cover - defensive
                logger.error(
                    "Error during deletion sync for workflow %s channel %s: %s",
                    workflow_id,
                    channel_id,
                    e,
                    exc_info=True,
                )

        channels_processed += 1

    finished_at = datetime.utcnow()
    db.update_workflow(workflow_id, last_run_at=finished_at)

    stats = {
        "workflow_id": workflow_id,
        "messages_synced": messages_synced,
        "replies_synced": replies_synced,
        "channels_processed": channels_processed,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_ms": int((finished_at - started_at).total_seconds() * 1000),
    }

    logger.info("Workflow %s run complete: %s", workflow_id, stats)
    return stats
