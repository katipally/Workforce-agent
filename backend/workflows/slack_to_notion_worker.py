"""Background worker for Slack → Notion workflows.

Run this script as a separate process:

    python backend/workflows/slack_to_notion_worker.py

It will:
- Poll the database for active `slack_to_notion` workflows
- Respect each workflow's `poll_interval_seconds`
- Call `process_workflow_once` when a workflow is due
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

# Ensure project root is on sys.path so `core` and `workflows` packages resolve
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Also add the core directory so imports like `utils.logger` and `database.*`
# (used by existing core modules) resolve the same way as in api/main.py.
core_path = project_root / "core"
if str(core_path) not in sys.path:
    sys.path.insert(0, str(core_path))

from core.database.db_manager import DatabaseManager
from core.utils.logger import get_logger
from workflows.slack_to_notion_core import process_workflow_once

logger = get_logger(__name__)

TICK_SECONDS = 1


def run_scheduler(stop_event=None) -> None:
    """Run the Slack → Notion workflow scheduler loop.

    If stop_event is provided, the loop will exit when it is set. This allows
    the scheduler to be used both as a standalone script and as a background
    thread inside the FastAPI app.
    """

    db = DatabaseManager()
    logger.info("Slack → Notion workflow scheduler started")

    while True:
        if stop_event is not None and stop_event.is_set():
            logger.info("Stop event set; exiting workflow scheduler loop")
            break

        try:
            now = datetime.now(timezone.utc)
            workflows = db.list_workflows(limit=500)

            for wf in workflows:
                if wf.type != "slack_to_notion" or wf.status != "active":
                    continue

                interval = wf.poll_interval_seconds or 30

                # Treat DB timestamps as UTC and attach an explicit timezone so we
                # can safely compare against timezone-aware `now`.
                if wf.last_run_at is not None:
                    last_run = wf.last_run_at.replace(tzinfo=timezone.utc)
                else:
                    last_run = now - timedelta(seconds=interval * 2)

                next_due = last_run + timedelta(seconds=interval)

                if now >= next_due:
                    logger.info(
                        "Running workflow %s (%s) interval=%ss", wf.id, wf.name, interval
                    )
                    try:
                        stats = process_workflow_once(wf.id)
                        logger.info("Workflow %s stats: %s", wf.id, stats)
                    except Exception as e:  # pragma: no cover - defensive
                        logger.error(
                            "Error processing workflow %s: %s", wf.id, e, exc_info=True
                        )

            time.sleep(TICK_SECONDS)
        except KeyboardInterrupt:
            logger.info("Worker interrupted, shutting down…")
            break
        except Exception as e:  # pragma: no cover - defensive
            logger.error("Worker loop error: %s", e, exc_info=True)
            time.sleep(TICK_SECONDS)


def main() -> None:
    run_scheduler()


if __name__ == "__main__":
    main()
