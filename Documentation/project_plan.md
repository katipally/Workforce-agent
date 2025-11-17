# Projects Tab – End-to-End Design & Implementation Plan

_Last updated: Nov 2025_

This document describes the full design for the **Projects** tab in the Workforce Agent, including:

- How it uses **only data stored by the Slack/Gmail/Notion pipelines**.
- The data model for Projects and their source mappings.
- An idempotent **RAG (retrieval-augmented generation)** layer for project-scoped chat.
- Backend API design and frontend UX.
- Realistic implementation phases.

The goal is to have a **single source of truth per project** that unifies information from Slack, Gmail, and Notion, and exposes it via a clean UI and a project-scoped AI assistant (using the same ChatGPT API used for the main chat).

---

## 1. Goals & Constraints

### 1.1 Goals

- Provide a **Projects** tab where each project has:
  - **Summary** and **main goal**.
  - **Current status** (where we are now).
  - **Recent updates** and **major milestones**.
  - **Important notes / things to remember**.
  - A **unified activity feed** from Slack, Gmail, and Notion.
  - A **project-scoped chat** that only uses project data.

- Make the Projects tab the **single source of truth** for each project. An employee should be able to open a project and quickly understand everything from the start to the current progress.

### 1.2 Constraints

- **Data source**
  - The project tab **only** uses data that has been persisted by the existing pipelines:
    - Slack pipeline → DB tables (workspaces, users, channels, messages, files, reactions).
    - Gmail pipeline → DB tables (accounts, labels, threads, messages, attachments).
    - Notion pipeline → DB tables (workspaces, pages, hierarchy, content).
  - No live calls from the Projects tab directly to Slack/Gmail/Notion APIs.

- **Manual mapping of sources**
  - Projects are defined manually:
    - A project can be linked to **multiple Slack channels**.
    - A project can be linked to **multiple Gmail labels**.
    - A project can be linked to **multiple Notion pages**.
  - No automatic inference of which channels/labels/pages belong to a project in v1.

- **Data freshness**
  - Projects show **Last synced** timestamps for Slack, Gmail, Notion (based on pipeline runs).
  - A **Refresh** action triggers the corresponding pipelines (or a subset) to update the DB.
  - The project tab reads updated data from the DB once pipelines complete.

- **RAG idempotency**
  - Any RAG index / embeddings layer must be **idempotent**:
    - No duplicate embeddings when pipelines run multiple times.
    - Re-extraction should **update** existing embeddings, not create new ones.
    - Deleted/invalidated items must be removed or marked inactive so they are not retrieved.

- **AI API**
  - The project chat uses the **same ChatGPT API** (OpenAI Chat Completions) as the main chat, with an additional **project_id context** and RAG filters applied.

---

## 2. High-Level Architecture

We introduce a new layer on top of the existing Slack/Gmail/Notion pipelines.

### 2.1 Existing layers

1. **Pipelines layer (already exists)**
   - Slack extraction: populates `workspaces`, `users`, `channels`, `messages`, `files`, `reactions`, etc.
   - Gmail extraction: populates `gmail_accounts`, `gmail_labels`, `gmail_threads`, `gmail_messages`, `gmail_attachments`.
   - Notion extraction: populates `notion_workspaces`, `notion_pages`, plus any content tables.

2. **Chat / Agent layer (already exists)**
   - Chat sessions / messages stored in `chat_sessions` and `chat_messages`.
   - Uses ChatGPT API behind the scenes.

### 2.2 New layers

3. **Project layer (NEW)**
   - `Project` and `ProjectSource` models.
   - REST API to create/edit/delete projects and link them to Slack channels, Gmail labels, Notion pages.
   - Project activity endpoint that aggregates recent events from all linked sources.

4. **RAG layer for project chat (NEW)**
   - A global embeddings index over Slack/Gmail/Notion content.
   - Idempotent upsert logic keyed by concrete source IDs.
   - Project-scoped retrieval using metadata filters (no per-project copies of data).

5. **Project tab UI (NEW)**
   - New `Projects` tab alongside `Chat` and `Pipelines` in the frontend.
   - Project list sidebar.
   - Project detail view with overview, sources, activity, and project-scoped chat.

---

## 3. Data Model Design

### 3.1 Project & ProjectSource

**Project** (logical fields):

- `id` (UUID or short string)
- `name`
- `description`
- `status` (enum: `not_started | in_progress | blocked | completed`)
- `summary` (overall project summary)
- `main_goal` (what the project tries to achieve)
- `current_status_summary` (where we are now)
- `important_notes` (risks, reminders, special constraints)
- `created_at`, `updated_at`

**ProjectSource** (logical fields):

- `id` (integer PK)
- `project_id` → FK to `projects.id`
- `source_type`: `slack_channel | gmail_label | notion_page`
- `source_id` (string)
  - Slack: `channel_id`
  - Gmail: `label_id`
  - Notion: `page_id`
- `display_name` (cached title/label/channel name for faster UI)
- `created_at`

A single Project can have many `ProjectSource` entries of each type.

### 3.2 Sync metadata

Sync metadata is global (per pipeline), but exposed in project context:

- `slack_last_sync_at`
- `gmail_last_sync_at`
- `notion_last_sync_at`

These values are typically tracked by existing pipeline code or can be attached to a small table / state file read by the backend.

---

## 4. RAG / Embeddings Design

We design a **global** RAG index, not per-project, keyed by the underlying source objects. Projects only restrict which embeddings are used via metadata filters.

### 4.1 Indexed document schema (conceptual)

**IndexedDocument** (conceptual table):

- Identity:
  - `source_type` (`slack_message`, `gmail_message`, `notion_page_content`, etc.)
  - `source_id` (e.g. Slack `message_id`, Gmail `message_id`, Notion `page_id` or block ID)
  - `chunk_index` (integer; 0..N for chunked content)

- Metadata:
  - Slack: `slack_channel_id`
  - Gmail: `gmail_label_ids` (array of label IDs)
  - Notion: `notion_page_id`
  - `original_timestamp` (time of message/email/page update)
  - `content_hash` (hash of `text` for change detection)
  - `created_at`, `updated_at` (for index bookkeeping)

- Content:
  - `text` (the actual chunk)
  - `embedding` (vector) – stored via pgvector or JSON depending on environment.

**Primary key:** `(source_type, source_id, chunk_index)`

### 4.2 Idempotent indexing flow

For each source type (Slack, Gmail, Notion):

1. Maintain a `last_indexed_at_<source>` timestamp.
2. After a pipeline run completes:
   - Query DB for rows with `updated_at > last_indexed_at_<source>`.
3. For each changed row:
   - Generate `text` for indexing (message text, email body, Notion content).
   - Compute `content_hash` (e.g. SHA256 over normalized text).
   - Determine chunks and assign `chunk_index` values deterministically.
   - For each chunk, look up `IndexedDocument` by `(source_type, source_id, chunk_index)`:
     - If **no existing row**: insert new embedding row.
     - If **existing row** and `content_hash` unchanged: skip (idempotent).
     - If **existing row** and `content_hash` changed: recompute embedding and upsert row.
4. Handle deletions:
   - If DB marks items as deleted (`is_deleted` or similar), indexer removes or soft-deletes corresponding `IndexedDocument` rows.
5. Update `last_indexed_at_<source>` to the current time.

This ensures that re-running pipelines and indexers is **safe and idempotent**: no duplicate embeddings, only updated content.

### 4.3 Project-scoped retrieval

When querying in project chat:

1. From `project_id`, load all ProjectSource records:
   - Slack: `[channel_id1, channel_id2, ...]`
   - Gmail: `[label_id1, label_id2, ...]`
   - Notion: `[page_id1, page_id2, ...]`

2. Build a metadata filter for vector search, for example:

   - Slack messages:
     - `source_type = 'slack_message'` AND `slack_channel_id IN (channel_id1, channel_id2, ...)`
   - Gmail messages:
     - `source_type = 'gmail_message'` AND `gmail_label_ids` contains any of `[label_id1, label_id2, ...]`
   - Notion content:
     - `source_type = 'notion_page_content'` AND `notion_page_id IN (page_id1, page_id2, ...)`

3. Run semantic search with:
   - The query embedding.
   - The metadata filter restricting to those sources.

4. Use retrieved chunks as context for the ChatGPT call.

No additional per-project embeddings are created. Projects behave as **filters over the global index**.

---

## 5. Backend API Design

### 5.1 Project CRUD

**List projects**

- `GET /api/projects`
- Returns a list of projects with minimal fields: id, name, status, maybe a short summary snippet and counts of linked sources.

**Create project**

- `POST /api/projects`
- Body: `{ name, description?, status? }`.
- Returns created project object.

**Get project detail**

- `GET /api/projects/{project_id}`
- Returns project fields + linked sources + last sync timestamps:
  - Project: identity, status, overview fields.
  - Sources: arrays of Slack channels, Gmail labels, Notion pages.
  - Sync: `slack_last_sync_at`, `gmail_last_sync_at`, `notion_last_sync_at`.

**Update project**

- `PUT /api/projects/{project_id}`
- Body: any mutable fields (name, description, status, summary, main_goal, current_status_summary, important_notes).
- Returns updated project.

**Delete project**

- `DELETE /api/projects/{project_id}`
- Removes project and its ProjectSource mappings (cascade).

### 5.2 Project source mapping

**Add sources to project**

- `POST /api/projects/{project_id}/sources`
- Body: list of `{ source_type, source_id }` objects.
- Checks that:
  - `source_type` is one of `slack_channel | gmail_label | notion_page`.
  - `source_id` exists in the corresponding DB tables.
- Creates `ProjectSource` rows.

**Remove a source**

- `DELETE /api/projects/{project_id}/sources/{source_type}/{source_id}`
- Deletes the mapping row.

### 5.3 Project activity aggregation

**Unified activity endpoint**

- `GET /api/projects/{project_id}/activity?limit=N&source=all|slack|gmail|notion`
- Internal logic:
  - Load project’s `ProjectSource` mappings.
  - For Slack:
    - Query `messages` filtered by `channel_id IN [slack channel IDs]`.
  - For Gmail:
    - Query `gmail_messages` where `label_ids` intersect with `[gmail label IDs]`.
  - For Notion:
    - Query `notion_pages` and (optionally) any content table filtered by `[notion page IDs]`.
  - Combine into a unified list of activity events with fields like:
    - `timestamp`
    - `source` (`slack`, `gmail`, `notion`)
    - `title` / `header` (e.g., email subject, snippet of message, page title)
    - `snippet`
    - `origin_id` (message_id / page_id / etc.)
    - `origin_link` (link to Slack/Gmail/Notion if available)

- Return list sorted by `timestamp` descending.

### 5.4 Sync / Refresh

**Refresh project data**

For v1, refresh is global per pipeline (not project-specific).

- Endpoint: `POST /api/projects/{project_id}/refresh`
  - Body may optionally specify `sources: ['slack', 'gmail', 'notion']`.
  - Implementation:
    - Triggers the existing `/api/pipelines/slack/run`, `/api/pipelines/gmail/run`, and `/api/pipelines/notion/run` endpoints with appropriate options.
    - Returns early with run IDs, or waits until completion depending on design.

Projects then display global last sync times; they do not run pipeline subsets scoped to a single project (that can be a future enhancement).

### 5.5 Project-scoped chat

**Chat endpoint**

- `POST /api/chat/project/{project_id}`
- Request body (conceptual):
  - `message`: user text.
  - Optional `session_id` (to track project chat sessions separately).

**Server behavior:**

1. Load project by `project_id`.
2. Load its `ProjectSource` mappings.
3. Build retrieval filter for RAG index as described in section 4.3.
4. Retrieve relevant documents (Slack/Gmail/Notion) from the global index.
5. Construct a ChatGPT API request:
   - System prompt: describe that this is **project assistant** for Project X, restricted to specific sources.
   - Messages: include prior chat history (from `chat_sessions`/`chat_messages`) + context documents as tool/notes.
6. Call the same ChatGPT API used for main chat (e.g., OpenAI Chat Completions).
7. Store the assistant message in `chat_messages`, including a `sources` field summarizing which project docs were used.
8. Return the AI response and citations to the frontend.

---

## 6. Frontend UX – Project Tab

### 6.1 App-level changes

- In `App.tsx`, add a third tab `Projects` alongside `Chat` and `Pipelines`:
  - `activeTab` now supports: `'chat' | 'pipelines' | 'projects'`.
  - Keep all three views mounted and toggle visibility via CSS classes (like Chat/Pipelines currently).
  - Persist `activeTab` in `localStorage` so the app reopens on the last-used tab.

### 6.2 Layout of Projects tab

**Left sidebar: Project list**

- Components:
  - Search box (for filtering projects by name).
  - List of projects:
    - Name.
    - Status pill (color-coded: e.g., In Progress, Blocked, etc.).
    - Optionally a small summary snippet or counts of linked sources.
  - `+ New Project` button.

- Interactions:
  - Clicking a project → loads its details into the main panel.
  - `+ New Project` opens a create form (name, optional description/status).

**Main panel: Selected project view**

1. **Header**
   - Shows project name.
   - Status dropdown.
   - Buttons:
     - `Edit overview` (opens a form for summary, main goal, status summary, notes).
     - `Add sources` (opens mapping UI).
     - `Refresh data` (triggers pipelines).
   - Badges displaying last sync times, for example:
     - `Slack last synced: 2025-11-15 09:30`.
     - `Gmail last synced: 2025-11-15 09:31`.
     - `Notion last synced: 2025-11-15 09:32`.

2. **Overview section**
   - Cards (or stacked fields):
     - **Summary** – text area.
     - **Main goal** – short text.
     - **Current status** – text.
     - **Important notes** – text.
   - All fields are **plain text editable** in v1. Later we can add buttons to “Generate with AI” using project data.

3. **Sources section**
   - Three subsections for sources:

   - **Slack sources**
     - Multi-select dropdown listing Slack channels from DB:
       - Channel name + private/archived markers.
     - List of selected channels with remove icons.
     - Show count: `3 channels linked`.

   - **Gmail sources**
     - Multi-select dropdown listing Gmail labels.
     - Selected labels list with remove.

   - **Notion sources**
     - Multi-select dropdown listing Notion pages (optionally showing hierarchy).
     - Selected pages list with remove.

   - A small summary line: `Slack: 3 channels · Gmail: 2 labels · Notion: 1 page`.

4. **Activity timeline**

   - Unified feed of recent events across Slack/Gmail/Notion for this project.
   - Layout:
     - Vertical list with source icons.
     - Each item shows:
       - Timestamp.
       - Source type (Slack / Gmail / Notion).
       - Human-readable title:
         - Slack: `@user in #channel: message snippet`.
         - Gmail: `From: X – Subject`.
         - Notion: `Page title – latest edit snippet`.
       - Short snippet (1–2 lines).
       - Optional `Open in Slack/Gmail/Notion` link.
   - Filters above the list:
     - Source filter: `All | Slack | Gmail | Notion`.
     - Time filter: `Last 24h | Last 7 days | Last 30 days`.

5. **Project chat panel**

   - Can be on the right side or bottom of the main panel.

   - Elements:
     - Header: `Project chat – [Project Name]`.
     - Scope hint: `Using data from 3 Slack channels, 2 Gmail labels, 1 Notion page`.
     - Chat message list similar to Chat tab.
     - Input box.
   - Behavior:
     - On send:
       - Calls `POST /api/chat/project/{project_id}`.
       - Backend uses RAG layer with project-source filters.
     - AI responses can display which sources they used (e.g., small chips: Slack, Gmail, Notion).

---

## 7. Implementation Phases

To manage complexity, implementation is split into phases. The phases are structured so the UI is usable early (even without AI summaries), and RAG + project chat are layered on later.

### Phase P0 – Preparation

- Verify existing DB schema and migration strategy.
- Confirm vector/embeddings stack:
  - Use existing `Vector` columns in `messages` and `gmail_messages` (and any Notion content tables), or introduce a dedicated `IndexedDocument` table.
- Decide chunking rules per source type.

**Output:** Clear technical choices for vector storage and chunking.

### Phase P1 – Backend: Project & ProjectSource models + APIs

- Add `Project` and `ProjectSource` SQLAlchemy models to `backend/core/database/models.py`.
- Implement REST endpoints in `backend/api/main.py`:
  - `GET /api/projects`
  - `POST /api/projects`
  - `GET /api/projects/{project_id}`
  - `PUT /api/projects/{project_id}`
  - `DELETE /api/projects/{project_id}`
  - `POST /api/projects/{project_id}/sources`
  - `DELETE /api/projects/{project_id}/sources/{source_type}/{source_id}`
- Wire endpoints to `db_manager.get_session()` similar to existing pipeline endpoints.

**Output:** Backend supports project CRUD and manual mapping of Slack/Gmail/Notion sources, no UI yet.

### Phase P2 – Frontend: Basic Projects tab UI

- Update `frontend/src/App.tsx`:
  - Add `Projects` tab button.
  - Keep `Chat`, `Pipelines`, `Projects` mounted with CSS visibility toggles.
  - Persist last active tab in `localStorage` (reuse existing pattern).

- Create `frontend/src/components/projects/ProjectsInterface.tsx`:
  - Left sidebar listing projects (fetch from `/api/projects`).
  - Main panel showing basic project fields (name, description, status).
  - Simple forms for creating and editing projects.

- Add a basic `Sources` section to select Slack channels / Gmail labels / Notion pages:
  - Initially, use simple `<select>` or multiselect UI elements.
  - Fetch available sources via existing pipeline endpoints or new helper endpoints if needed.

**Output:** A functional Projects tab where you can define projects and connect them to Slack/Gmail/Notion sources.

### Phase P3 – Backend: RAG indexing and idempotent sync

- Implement an indexing job that reads from existing DB tables and upserts into the embeddings layer.
  - Slack: index `messages` rows (per message or per chunk of text).
  - Gmail: index `gmail_messages` rows.
  - Notion: index Notion page content (from existing content endpoints or a new table).

- Key features:
  - Use `(source_type, source_id, chunk_index)` as the identity key.
  - Compute `content_hash` on each text chunk to decide if re-indexing is needed.
  - Maintain `last_indexed_at_<source>` timestamps to only process changed rows.

- Integrate with existing Slack/Gmail/Notion pipeline completion:
  - After a pipeline run, trigger the corresponding indexer.

**Output:** A global, deduplicated embeddings index over pipeline data, ready to support project-scoped retrieval.

### Phase P4 – Backend: Project activity & project chat

- Implement `GET /api/projects/{id}/activity`:
  - Use `ProjectSource` mappings to query:
    - Slack messages for mapped channels.
    - Gmail messages for mapped labels.
    - Notion pages/updates for mapped pages.
  - Combine into a unified activity list with timestamps and basic metadata.

- Implement `POST /api/chat/project/{id}`:
  - Build RAG filters from `ProjectSource` mappings (Slack channels, Gmail labels, Notion pages).
  - Perform semantic search over the RAG index with those filters.
  - Compose prompt/context and call ChatGPT API (same client used for main chat).
  - Store chat messages in `chat_sessions`/`chat_messages` with `session_id` and `sources` metadata.

**Output:** Project activity and project-scoped chat available via backend APIs.

### Phase P5 – Frontend: Activity feed and chat integration

- Extend `ProjectsInterface`:
  - Add **Activity** section to call `/api/projects/{id}/activity` and render the unified timeline.
  - Add filters (All/Slack/Gmail/Notion, time range).

- Add **Project Chat** panel:
  - Use an interaction pattern similar to `ChatInterface`.
  - On send, call `POST /api/chat/project/{id}`.
  - Display assistant responses with source badges when possible.

**Output:** Fully functional Projects tab:

- Manual project setup and mapping.
- Unified activity timeline.
- Project-scoped chat using RAG over Slack/Gmail/Notion pipeline data.

### Phase P6 – Enhancements (optional / later)

- AI-assisted overview generation:
  - Buttons like “Generate summary from project data” that call ChatGPT with project RAG context.
  - Ability to accept/edit the generated summary/status.

- Project tasks and assignments:
  - Simple `ProjectTask` model with title, assignee, status, due date.
  - Agent can propose or update tasks based on project chat.

- Smart source suggestions:
  - Suggest Slack channels, Gmail labels, and Notion pages to add to a project based on naming similarities or overlapping content.

- Analytics & insights:
  - Activity over time.
  - Who participates most.
  - Automatic detection of blockers or risks.

---

## 8. Notes on AI / ChatGPT API

- The project chat uses the **same ChatGPT API integration** as the main agent chat.
- Differences are in **prompting and retrieval scope**:
  - System prompt tailored to “You are the assistant for Project X, using these project sources only”.
  - RAG retrieval restricted via metadata to Slack/Gmail/Notion data linked to that project.
- This makes the behavior consistent across Chat and Projects tabs while giving Projects a focused context.

---

This document serves as the authoritative design plan for the Projects tab. As implementation progresses, we can update this file with any deviations, decisions, or refinements made along the way.
