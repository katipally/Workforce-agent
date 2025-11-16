# Pipelines Architecture Plan

## Overview

We will add three ingestion pipelines (Slack, Gmail, Notion) to the Workforce Agent. Each pipeline can be manually triggered from a new "Pipelines" tab in the frontend, similar to a DAG run: it fetches data from the source API, normalizes it, stores it in structured tables, and exposes it via API for visualization.

Pipelines (v1):
- Slack: full history for current workspace, including message threads.
- Gmail: incremental sync for a chosen label (new emails since last run).
- Notion: all pages under `NOTION_PARENT_PAGE_ID`.

The goals are:
- Manual control (explicit trigger buttons).
- Clear status (per-run status and progress).
- Structured data for browsing and future analytics.
- Use existing backend integrations and database.

---

## 1. Backend Pipelines Layer

### 1.1 Abstraction

Each pipeline will be implemented as a Python function/class with the following conceptual interface:

- `name`: `"slack_history" | "gmail_label" | "notion_pages"`.
- `run(params) -> run_id`: starts a background job and returns a run identifier.
- `get_status(run_id) -> {status, progress, started_at, finished_at, error, stats}`.

We will introduce a shared `pipeline_runs` table/model:

- `id` (UUID or int primary key).
- `pipeline_type` ("slack", "gmail", "notion").
- `params` (JSON, e.g. `{ "label": "Datasaur" }`).
- `status` ("pending" | "running" | "completed" | "failed").
- `progress` (optional numeric or text summary).
- `started_at`, `finished_at`.
- `error` (text, nullable).

Each pipeline implementation will:
- Create a new `pipeline_runs` record with `status="running"`.
- Perform extraction, normalization, and upserts.
- Update `status` and `stats` (e.g. number of records processed).

We can start with FastAPI background tasks or a simple in-process worker (no separate queue for v1).

### 1.2 Endpoints (v1)

Common pattern:

- `POST /api/pipelines/{source}/run` → start a run, return `{run_id}`.
- `GET /api/pipelines/{source}/status/{run_id}` → return status payload.
- `GET /api/pipelines/{source}/data` → return structured data optimized for the UI.

Sources:
- `{source} = "slack" | "gmail" | "notion"`.

---

## 2. Slack Pipeline (Full History + Threads)

### 2.1 Requirements

- Current workspace only (no multi-workspace for v1).
- Full history per channel (initial backfill), including message threads.
- Incremental updates on subsequent runs (only new messages since last run per channel).

### 2.2 Data Model (Conceptual)

Reusing or introducing tables (names indicative; align with existing schema where possible):

- `slack_channels`
  - `id` (Slack channel ID).
  - `name`.
  - `is_private`.
  - `created_at`.
  - `is_archived`.

- `slack_users`
  - `id` (Slack user ID).
  - `real_name`.
  - `display_name`.
  - `email`.
  - `tz`.

- `slack_messages`
  - `id` (e.g., composite of channel + ts, or a synthetic key).
  - `channel_id`.
  - `user_id` (nullable for system messages).
  - `text`.
  - `ts`.
  - `thread_ts` (thread root timestamp, if any).
  - `parent_ts` (for replies).
  - `reactions` (JSON array).
  - `is_thread_root` (bool).

- `slack_channel_checkpoints`
  - `channel_id`.
  - `last_fetched_ts` (string timestamp or float).

### 2.3 Extraction Algorithm

For each run:

1. Fetch list of channels using existing Slack extractor utilities (e.g. `conversations.list`).
2. Upsert channels into `slack_channels`.
3. For each channel:
   - Read `last_fetched_ts` from `slack_channel_checkpoints`.
   - If missing (first run), treat as full history:
     - Call `conversations.history` with pagination until no more messages.
   - If present, fetch only messages with `ts > last_fetched_ts`.
4. For each message:
   - Upsert into `slack_messages`.
   - Capture `thread_ts`, `parent_ts`, reactions, etc.
5. For messages where `reply_count > 0` and/or `thread_ts` is set:
   - Use `conversations.replies` to fetch full threads if not already stored.
6. Update `slack_channel_checkpoints` for each channel with the max `ts` processed.

This provides:
- Full initial backfill.
- Incremental sync on later runs.

### 2.4 Slack API Endpoints

- `POST /api/pipelines/slack/run`
  - Triggers a background Slack pipeline run.
  - Returns `{ run_id }`.

- `GET /api/pipelines/slack/status/{run_id}`
  - Returns `{ status, progress, counts: { channels, messages }, started_at, finished_at, error }`.

- `GET /api/pipelines/slack/data`
  - Returns data for the UI, likely structured as:
    - `workspace`: metadata.
    - `channels`: list of channels (id, name, member count, last_message_ts...).
    - Optionally: summary counts per channel.

- For large data, we will also expose:
  - `GET /api/pipelines/slack/messages?channel_id=...&cursor=...&limit=...`
  - Returns paginated messages with basic thread grouping info.

---

## 3. Gmail Pipeline (Label-Based Incremental Sync)

### 3.1 Requirements

- Sync emails for a specific label.
- Only new emails since the last run per label.
- Frontend must show a dropdown of available labels fetched from Gmail API, not hard-coded.
- UI: accordion per email with summary header (from, subject, sent date) and full body on expand.

### 3.2 Data Model (Conceptual)

- `gmail_messages`
  - `id` (Gmail message ID).
  - `thread_id`.
  - `label` (human-readable label or label ID; align with current design).
  - `from_name`.
  - `from_email`.
  - `to_emails` (JSON array).
  - `subject`.
  - `sent_at`.
  - `snippet`.
  - `body_text`.
  - `body_html`.

- `gmail_label_checkpoints`
  - `label`.
  - `last_internal_date` (or equivalent timestamp / message ID).

### 3.3 Extraction Algorithm

Per pipeline run for a given label:

1. Resolve label to label ID using Gmail API.
2. Read `last_internal_date` for that label from `gmail_label_checkpoints`.
3. If no checkpoint, fetch all messages for that label (initial backfill).
4. If checkpoint exists, fetch only messages with `internalDate > last_internal_date`.
5. For each message:
   - Call `users.messages.get` with `format=full`.
   - Use existing hardened parsing to extract headers and bodies.
   - Upsert into `gmail_messages`.
6. Update `gmail_label_checkpoints` with the newest `internalDate`.

### 3.4 Gmail API Endpoints

- `GET /api/pipelines/gmail/labels`
  - Returns available Gmail labels for the authenticated account.
  - Used by the frontend to populate the label dropdown.

- `POST /api/pipelines/gmail/run`
  - Body or query: `{ label: string }`.
  - Triggers a pipeline run for that label, returns `{ run_id }`.

- `GET /api/pipelines/gmail/status/{run_id}`

- `GET /api/pipelines/gmail/messages?label=...&page=...`
  - Paginated list of emails for UI accordion.

---

## 4. Notion Pipeline (Pages Under Parent)

### 4.1 Requirements

- Use `NOTION_PARENT_PAGE_ID` as root.
- Fetch all pages under this parent (and nested where appropriate).
- Store basic page metadata and URLs.
- UI: list of page titles; clicking opens the Notion URL in a new tab.

### 4.2 Data Model (Conceptual)

- `notion_pages`
  - `page_id`.
  - `title`.
  - `url`.
  - `last_edited_time`.
  - `parent_id`.
  - `parent_type`.

### 4.3 Notion API Endpoints

- `POST /api/pipelines/notion/run`
- `GET /api/pipelines/notion/status/{run_id}`
- `GET /api/pipelines/notion/pages`
  - Returns list of `{ page_id, title, url, last_edited_time }`.

---

## 5. Frontend: Pipelines Tab & UI

We will extend the existing React frontend (Vite + React + Tailwind) with a new "Pipelines" view.

### 5.1 Layout

- Top-level navigation:
  - Keep current Chat view.
  - Add a new tab-like switch between **Chat** and **Pipelines**.
- Within the Pipelines view:
  - Three cards/sections for:
    - Slack Pipeline
    - Gmail Pipeline
    - Notion Pipeline

Each card shows:
- Last run status (status, timestamp, counts if available).
- A "Run Pipeline" button (manual trigger).
- A link or toggle to show the data view.

### 5.2 Slack UI (v1)

- List of channels on the left (name, message count, last message time).
- When a channel is selected:
  - Display messages in the main area.
  - Group messages by thread:
    - Thread root message with an expandable list of replies, or a simple inline grouping.
- Basic filters: optional (date range, search) for later versions.

### 5.3 Gmail UI (v1)

- Label selector (dropdown):
  - Populated via `GET /api/pipelines/gmail/labels`.
- Run button for the selected label.
- After completion, show an accordion list of messages for that label:
  - Header: sender name/email, subject, sent time.
  - On expand: full body (HTML rendering or text), plus metadata.

### 5.4 Notion UI (v1)

- Simple table or list of pages:
  - Title, last edited time.
- Clicking a row opens the Notion page URL in a new tab/window.

---

## 6. Performance & Limitations (v1)

- **Slack full history**:
  - First run may be long; we will use pagination and per-channel checkpoints.
  - Subsequent runs are incremental.

- **Gmail large labels**:
  - First run per label may be slow; acceptable as per requirements.
  - Incremental runs will be much faster using checkpoints.

- **Notion pages**:
  - Typically smaller volume; scanning under a single parent is manageable.

- **Background execution**:
  - Use FastAPI background tasks or a lightweight worker so the UI calls do not time out.
  - Frontend will poll `/status/{run_id}`.

This plan will guide implementation of the Slack pipeline and UI first, followed by Gmail and Notion using the same patterns.
