"""Lightweight smoke tests for core Workforce Agent features.

Run with:
    python backend/smoke_test.py

This script is intentionally simple and should not be treated as a full
unit-test suite. It focuses on exercising the most important integration
paths (DB, Slack sending, Gmail DB search) and reporting any obvious
runtime errors.
"""
from __future__ import annotations

import os
from typing import Any, Dict

from agent.langchain_tools import WorkforceTools
from database.db_manager import DatabaseManager
from core.slack.sender.message_sender import MessageSender
from utils.logger import get_logger


logger = get_logger(__name__)


def _print_header(title: str) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def test_database() -> Dict[str, Any]:
    """Basic database connectivity and stats."""
    _print_header("DB STATS")
    db = DatabaseManager()
    try:
        stats = db.get_statistics()
        gmail_stats = db.get_gmail_statistics()
        print("Core stats:", stats)
        print("Gmail stats:", gmail_stats)
        return {"ok": True, "stats": stats, "gmail": gmail_stats}
    except Exception as e:  # pragma: no cover - diagnostic only
        print("DB test FAILED:", e)
        return {"ok": False, "error": str(e)}


def test_slack_send() -> Dict[str, Any]:
    """Exercise the Slack send path used by WorkforceTools.send_slack_message.

    Requires a valid Slack bot token (Config.SLACK_BOT_TOKEN) and a
    channel identifier in SMOKE_TEST_SLACK_CHANNEL. If no channel is
    configured, the test is skipped.
    """
    _print_header("SLACK SEND")
    channel = os.getenv("SMOKE_TEST_SLACK_CHANNEL")
    if not channel:
        print("Slack test SKIPPED: SMOKE_TEST_SLACK_CHANNEL not set")
        return {"ok": None, "reason": "channel_not_configured"}

    try:
        tools = WorkforceTools()
        result_str = tools.send_slack_message(channel=channel, text="Smoke test from Workforce Agent")
        print("Result:", result_str)
        ok = "✓" in result_str or "Message sent" in result_str
        return {"ok": ok, "result": result_str}
    except Exception as e:  # pragma: no cover - diagnostic only
        print("Slack send FAILED:", e)
        return {"ok": False, "error": str(e)}


def test_gmail_db_search() -> Dict[str, Any]:
    """Exercise Gmail DB search helper (no external Gmail API calls).

    This does not hit the live Gmail API; it only queries the local
    GmailMessage table via WorkforceTools.search_gmail_messages.
    """
    _print_header("GMAIL DB SEARCH")
    try:
        tools = WorkforceTools()
        preview = tools.search_gmail_messages("test", limit=1)
        print("Search output preview:\n", (preview or "").split("\n\n")[0][:500])
        return {"ok": True, "preview": preview[:500] if preview else ""}
    except Exception as e:  # pragma: no cover - diagnostic only
        print("Gmail DB search FAILED:", e)
        return {"ok": False, "error": str(e)}


def main() -> None:
    results = {
        "db": test_database(),
        "slack": test_slack_send(),
        "gmail_db": test_gmail_db_search(),
    }

    _print_header("SUMMARY")
    for name, res in results.items():
        print(f"{name}: {res}")


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()
