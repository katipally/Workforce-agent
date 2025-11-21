# Workflows Architecture Plan

This document describes the architecture for the **Workflows** system, with the first concrete workflow being a **live Slack → Notion pipeline**.

---

## 1. Goals

- Add a new **Workflows** tab in the UI, separate from Projects.
- Allow users to define workflows; v1 supports:
  - **Slack → Notion (live)**: continuously sync Slack channel activity into a Notion page tree.
- Requirements for Slack → Notion workflow:
  - Map **one or more Slack channels** to **one Notion master page**.
  - For each Slack channel, create a **subpage** under the master.
  - Continuously ingest:
    - New messages
    - Thread replies, nested under the correct root message
    - Reactions set
    - Files (at least as links + metadata)
  - **Idempotent**:
    - No duplicate messages or replies in Notion, safe across restarts and Slack retries.
  - **Live behavior via polling** (Option C):
    - Poll Slack every N seconds and push new content to Notion.
    - Default interval 30s.
    - User-controllable interval: **30s, 1min, 5min, 10min, 1hr**.
    - Changing the interval updates how often the pipeline runs (master control).
  - Provide a **countdown timer** in the UI showing `next run in Xs`, and a **manual trigger** button to run the workflow immediately.

---

## 2. High-Level Architecture

### 2.1 Components

- **Backend API (FastAPI)**
  - CRUD endpoints for Workflows and channel mappings.
  - Endpoint to **run a workflow once** on demand (manual trigger).
  - Shares DB models with the rest of the backend.

- **Workflow Worker Process (separate script)**
  - Lives under `backend/workflows/`.
  - Long-running process responsible for polling Slack and writing to Notion.
  - Respects per-workflow polling intervals.
  - Can be stopped/started independently of the main API.

- **Database** (PostgreSQL via SQLAlchemy models)
  - Stores workflow definitions, mappings from Slack channels to Notion subpages, and message-level mappings for idempotency.

- **Slack Integration**
  - Uses Slack Web API (`conversations.history`, `conversations.replies`, etc.).
  - Polling approach (Option C); no Events/RTM in v1.

- **Notion Integration**
  - Uses existing Notion client.
  - Creates subpages under the master page and appends blocks for messages/replies.

- **Frontend (React)**
  - New **Workflows** tab component (pattern similar to `ProjectsInterface.tsx`).
  - Timer UI showing countdown to the next automatic run.
  - Controls to change polling interval and to trigger manual runs.

---

## 3. Data Model

### 3.1 Workflow

New SQLAlchemy model `Workflow` (example fields):

- `id: String(50)` – primary key (UUID-like hex).
- `name: String(255)` – workflow name.
- `type: String(50)` – e.g. `"slack_to_notion"`.
- `status: String(20)` – `"active"` or `"paused"`.
- `notion_master_page_id: String(255)` – Notion page under which subpages live.
- `poll_interval_seconds: Integer` – one of:
  - 30, 60, 300, 600, 3600 (30s, 1m, 5m, 10m, 1h).
- `last_run_at: DateTime` – when the worker last completed a run for this workflow.
- `created_at: DateTime`
- `updated_at: DateTime`

Validation at API layer ensures `poll_interval_seconds` is one of the allowed values.

### 3.2 WorkflowChannelMapping

Model `WorkflowChannelMapping`:

- `id: Integer` – primary key.
- `workflow_id: String(50)` – FK → `Workflow.id`.
- `slack_channel_id: String(50)` – e.g. `C01234567`.
- `slack_channel_name: String(255)` – cached for UI (`#channel-name`).
- `notion_subpage_id: String(255)` – Notion page created under master.
- `last_slack_ts_synced: String(32)` – Slack timestamp (e.g. `"1732131234.1234"`) of the latest message processed for this channel.
- `created_at: DateTime`
- `updated_at: DateTime`

### 3.3 SlackNotionMessageMapping

Model `SlackNotionMessageMapping` (per-message idempotency and threading):

- `id: Integer`
- `workflow_id: String(50)` – scope mappings per workflow.
- `slack_channel_id: String(50)`
- `slack_ts: String(32)` – message `ts`.
- `parent_slack_ts: String(32) | None` – `None` for root messages; set to the root `ts` for replies.
- `notion_block_id: String(255)` – ID of the Notion block representing this message.
- `created_at: DateTime`

With this we can:

- Detect duplicates reliably by `(workflow_id, slack_channel_id, slack_ts)`.
- Find the correct Notion block for a Slack parent message when attaching replies.

---

## 4. API Design (Workflows)

All routes prefixed with `/api/workflows`.

### 4.1 List Workflows

- `GET /api/workflows`
- Returns list of workflows with basic metadata and grouped channels.

Example response:

```json
{
  "workflows": [
    {
      "id": "wf_1",
      "name": "Slack → Notion: Zephyr",
      "type": "slack_to_notion",
      "status": "active",
      "notion_master_page_id": "abcd-1234",
      "poll_interval_seconds": 30,
      "last_run_at": "2025-11-20T02:15:10Z",
      "channels": [
        {
          "slack_channel_id": "C0123",
          "slack_channel_name": "zephyr-mvp",
          "notion_subpage_id": "defg-5678",
          "last_slack_ts_synced": "1732131234.1234"
        }
      ]
    }
  ]
}
```

### 4.2 Create Workflow

- `POST /api/workflows`
- Payload:

```json
{
  "name": "Slack → Notion: Zephyr",
  "type": "slack_to_notion",
  "notion_master_page_id": "abcd-1234",
  "poll_interval_seconds": 30
}
```

- Status defaults to `"active"` or `"paused"` based on design choice (likely `"active"`).

### 4.3 Get Workflow Detail

- `GET /api/workflows/{workflow_id}`
- Returns a single workflow with channels array, similar to list item.

### 4.4 Update Workflow

- `PUT /api/workflows/{workflow_id}`
- Fields allowed to change:
  - `name`
  - `status`
  - `notion_master_page_id`
  - `poll_interval_seconds` (must be in allowed set).

When `poll_interval_seconds` changes:

- API updates DB.
- Worker uses the new interval on its next scheduling cycle.
- Frontend reloads workflow data and resets the local countdown timer to the new interval.

### 4.5 Manage Channels for a Workflow

- `POST /api/workflows/{workflow_id}/channels`
  - Payload: list of `{ slack_channel_id, slack_channel_name }`.
  - For each entry:
    - If mapping exists, update `slack_channel_name` if changed.
    - If not, create mapping and create a new Notion subpage under the master page.

- `DELETE /api/workflows/{workflow_id}/channels/{slack_channel_id}`
  - Marks mapping as removed (or deletes row). For v1 it is acceptable to delete.
  - Optionally we keep the Notion subpage as historical data.

### 4.6 Manual Run Trigger

- `POST /api/workflows/{workflow_id}/run-once`

Behavior:

- Calls a `process_workflow_once(workflow_id)` function (in workflows core module) within a controlled executor.
- Returns a summary:

```json
{
  "workflow_id": "wf_1",
  "messages_synced": 42,
  "replies_synced": 10,
  "channels_processed": 3,
  "duration_ms": 2300,
  "started_at": "...",
  "finished_at": "..."
}
```

- Updates `last_run_at` on success.

---

## 5. Worker Process (Polling Runner)

The worker is a separate Python script, e.g. `backend/workflows/slack_to_notion_worker.py`.

### 5.1 Scheduling Model with Per-Workflow Intervals

We want per-workflow intervals (30s, 1m, 5m, 10m, 1h) while keeping the worker simple.

Approach:

- Maintain `last_run_at` in DB for each workflow.
- Main loop runs in a **fixed short tick** (e.g. every 5 seconds) but only processes workflows that are due.

Pseudo-code:

```python
TICK_SECONDS = 5

while True:
    now = datetime.utcnow()
    workflows = db_manager.list_active_slack_to_notion_workflows()

    for wf in workflows:
        interval = wf.poll_interval_seconds or 30
        last_run = wf.last_run_at or (now - timedelta(seconds=interval * 2))
        next_run_due_at = last_run + timedelta(seconds=interval)

        if now >= next_run_due_at:
            stats = process_workflow_once(wf.id)
            db_manager.update_workflow_last_run(wf.id, datetime.utcnow())

    time.sleep(TICK_SECONDS)
```

- If the user changes the interval, the worker sees `poll_interval_seconds` change and thus changes `next_run_due_at` logic automatically.

### 5.2 `process_workflow_once`

Located in `backend/workflows/slack_to_notion_core.py` and imported by both API and worker.

Steps:

1. Load `Workflow` and its `WorkflowChannelMapping` rows.
2. For each channel mapping:
   - Ensure Notion subpage exists (create if missing and persist `notion_subpage_id`).
   - Poll Slack for **new messages**:
     - `conversations.history(channel, oldest=last_slack_ts_synced, inclusive=False, limit=200)`.
   - For each message:
     - Skip if already mapped in `SlackNotionMessageMapping`.
     - Create Notion block for root messages; track `notion_block_id`.
     - For messages that start/participate in a thread (`thread_ts`):
       - Use `conversations.replies` to retrieve the whole thread or replies since last known.
       - For each reply, create child block under the root’s Notion block.
   - Update mapping timestamps (`last_slack_ts_synced`) after successful write.
3. Accumulate counts (messages, replies) for stats.

All writes are wrapped so that we only advance checkpoints after Notion operations succeed.

---

## 6. Slack → Notion Mapping Details

### 6.1 What We Capture from Slack

For each message (root or reply):

- **Basic fields**:
  - `user`, `username` or `bot_id` to derive a display name.
  - `text`
  - `ts` (timestamp)

- **Reactions set** (if present):
  - `reactions: [{ name, count, users[] }]`.
  - Serialize into a short string, e.g. `"[reactions: 👍×3, 👀×1]"`.

- **Files** (if present):
  - `files: [{ name, mimetype, size, url_private, permalink, ... }]`.
  - Represent as a block like:
    - `"[files: design.pdf (application/pdf), spec.docx (application/vnd.openxmlformats-officedocument.wordprocessingml.document)]"`
  - We may also preserve the `permalink` as a URL property where appropriate.

### 6.2 Notion Block Structure

For each Slack **root** message:

- Create a top-level block in the channel’s subpage, probably as a `bulleted_list_item` or `toggle`.
- Example content:

```text
2025-11-20 15:42 – Alice
Message text here

[reactions: 👍×3, 👀×1]
[files: design.pdf, spec.docx]
```

For each **reply** in the thread:

- Use `SlackNotionMessageMapping` to find the parent root message’s `notion_block_id`.
- Insert a **child block** under the parent block.
- Example content:

```text
2025-11-20 15:45 – Bob (reply)
Reply text here

[reactions: …]
[files: …]
```

This mirrors Slack’s nesting and keeps an intuitive thread structure in Notion.

---

## 7. Idempotency Strategy

We must avoid duplicates even if:
- Worker restarts.
- Slack retries API requests.
- Manual trigger and scheduled run happen close together.

### 7.1 Message-level Idempotency

- For each Slack message (root or reply) we define a unique key:
  - `(workflow_id, slack_channel_id, slack_ts)`.
- Before creating a Notion block, we check `SlackNotionMessageMapping` with that key.
  - If a row exists → skip (already mirrored in Notion).
  - If not → create block and insert a new mapping row.

### 7.2 Checkpointing per Channel

- `WorkflowChannelMapping.last_slack_ts_synced` stores the **highest ts** successfully mirrored for that channel.
- Polling logic:
  - Request messages with `oldest = last_slack_ts_synced`, but in code skip anything with `ts <= last_slack_ts_synced`.
  - After successfully processing all new messages and replies in a batch:
    - Update `last_slack_ts_synced` to `max_ts_processed`.

This ensures:

- No messages are missed.
- Duplicates are eliminated both via checkpoint and the mapping table.

---

## 8. Frontend – Workflows Tab & Timer UX

### 8.1 Workflows Tab Layout

Similar pattern to `ProjectsInterface`:

- **Left sidebar**: list of workflows
  - Name, status.
  - On click → load workflow detail.

- **Right main panel**:
  - **Configuration card**:
    - Workflow name, status (`active/paused`).
    - Notion master page selector.
    - **Polling interval dropdown** with options:
      - `30s`, `1 min`, `5 min`, `10 min`, `1 hr`.
    - **Timer display**: `Next run in 21s` (counting down).
    - **Manual trigger button**: `Run now`.
  - **Channels card**:
    - Slack channel selector (reusing existing `/api/pipelines/slack/data`).
    - List of mapped channels (chips), each showing `#channel-name`.
  - (Optional later) `Recent activity / last run stats`.

### 8.2 Timer Behavior with Configurable Interval

Assumptions:
- The worker updates `last_run_at` for each workflow on every successful run.
- API exposes `poll_interval_seconds` and `last_run_at` in workflow detail.

In React:

1. When workflow detail is loaded:
   - Read `interval = poll_interval_seconds` (default 30).
   - Read `lastRunAt = new Date(last_run_at)` if present, otherwise treat as `now` minus `interval`.
   - Compute `remainingSeconds`:

   ```ts
   const now = Date.now()
   const last = lastRunAt ? lastRunAt.getTime() : now
   const elapsed = Math.max(0, (now - last) / 1000)
   const remaining = Math.max(0, interval - (elapsed % interval))
   ```

2. Start a `setInterval` (1000ms) to decrement `remainingSeconds` every second.
   - When `remainingSeconds` hits 0, show a brief state like `"Running…"` then reset to `interval`.
   - The actual run is handled by the worker; the timer is a **visual indicator**, not the scheduler.

3. When user changes the polling interval in the dropdown:
   - Call `PUT /api/workflows/{id}` with new `poll_interval_seconds`.
   - On success:
     - Update local `interval` to new value.
     - Reset `remainingSeconds` to `interval`.
   - The worker will see the new interval on its next tick and adjust scheduling.

4. When user clicks **Run now**:
   - Call `POST /api/workflows/{id}/run-once`.
   - On success:
     - Optionally show results (messages synced, etc.).
     - Refresh workflow detail (`GET /api/workflows/{id}`) to get new `last_run_at`.
     - Recompute `remainingSeconds` based on fresh `last_run_at` and current `interval`.

This provides a clear UX:
- User sees exactly when the next run will happen.
- Changing the interval immediately updates the countdown.
- Manual trigger resets the countdown to start from the moment of the manual run.

---

## 9. Future Enhancements (Beyond v1)

- **Slack Events / RTM** instead of polling for true real-time streams.
- Support editing existing Notion blocks when Slack messages are edited.
- Richer formatting in Notion (mentions, code blocks, etc.).
- Per-thread advanced controls (e.g. only sync threads with certain keywords).
- Workflow run logs and error dashboards.
- Additional workflow types (e.g. Gmail → Notion, Notion → Slack digests).

---

## 10. Summary

- The Workflows system introduces a structured, configurable way to run **live pipelines**.
- The initial Slack → Notion workflow:
  - Uses **polling** to achieve near-real-time sync (default 30s).
  - Supports user-controlled intervals: 30s, 1m, 5m, 10m, 1h.
  - Mirrors Slack channels into Notion subpages, including messages, threads, reactions, and files.
  - Is **idempotent** and resilient to restarts.
  - Exposes a **manual run** endpoint and a **countdown timer UX** in the Workflows tab.

This design keeps the pipeline worker isolated from the main API while sharing the same database and integrations, making it easy to evolve or replace individual workflow types later.
