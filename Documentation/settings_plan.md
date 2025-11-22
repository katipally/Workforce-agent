# Settings System Plan

This document defines how we will move configuration from the `.env` file into a settings system exposed in the **Profile** tab. In the Profile UI, we will **keep the existing Account tile unchanged**, and add two new tiles **below** it:

- **Personal Settings** (per-user)
- **Workspace Settings** (shared for all users)

The backend will store these settings in the database, replacing most `.env` configuration over time.

---

## 1. High-level goals

- Make configuration editable from the UI instead of editing `.env`.
- Support **per-user overrides** for things like personal OpenAI keys and preferences.
- Support **workspace-wide configuration** for shared integrations like Slack and Notion.
- Persist changes in the DB so they survive logout/login and deployment.
- Gradually make runtime code consume these settings instead of reading directly from `Config` / `.env`.

---

## 2. Mapping current `.env` to settings

Below is a classification of your current `.env` entries into **Personal** vs **Workspace** settings. In the final design, every key is backed by a Personal or Workspace setting, and **all values are entered and updated through the UI**. `.env` is only an optional backup used when no setting exists yet (for example on a fresh deployment with an empty database).

### 2.1 Slack

**Current `.env` keys**

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `SLACK_APP_ID`
- `SLACK_CLIENT_ID`
- `SLACK_CLIENT_SECRET`
- `SLACK_SIGNING_SECRET`
- `SLACK_VERIFICATION_TOKEN`
- `SLACK_USER_TOKEN` (optional)
- `SLACK_MODE`
- `SLACK_READONLY_CHANNELS`
- `SLACK_BLOCKED_CHANNELS`

**Workspace tile – Slack section (shared for all users)**

All Slack-related keys live in the single **Workspace** tile (Slack section). Every logged-in user is effectively an admin, so edits here affect the whole workspace:

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `SLACK_APP_ID`
- `SLACK_CLIENT_ID`
- `SLACK_CLIENT_SECRET`
- `SLACK_SIGNING_SECRET`
- `SLACK_VERIFICATION_TOKEN`
- Optional `SLACK_USER_TOKEN`
- `SLACK_MODE` (read_only / standard / admin)
- `SLACK_READONLY_CHANNELS` (as a list of channels/IDs)
- `SLACK_BLOCKED_CHANNELS` (as a list of channels/IDs)

`.env` values for these keys are optional backups used only when the database setting is missing (for example on a brand-new deployment). Once a setting exists, the Workspace tile value is the only source of truth.

### 2.2 Notion

**Current `.env` keys**

- `NOTION_TOKEN`
- `NOTION_PARENT_PAGE_ID`
- `NOTION_MODE`

**Workspace tile – Notion section (shared for all users)**

All Notion configuration lives in the Workspace tile under a Notion section:

- `NOTION_TOKEN` – stored as an encrypted secret, editable via the Workspace tile.
- `NOTION_MODE` – `standard` or `read_only`.
- `NOTION_PARENT_PAGE_ID` – workspace-level root page ID.

`.env` values for these keys are optional backups only when no workspace setting exists yet.

### 2.3 Google OAuth

**Current `.env` keys**

- `GOOGLE_CLIENT_ID`
- `GOOGLE_CLIENT_SECRET`
- `GOOGLE_OAUTH_REDIRECT_BASE`

These are **infrastructure / app credentials**, not per-user settings.
They are stored in the Workspace tile under a **Google OAuth** section and are edited through the UI. `.env` values, if present, are treated purely as backup when no setting exists yet.

Per-user Google/Gmail access is already handled via Google OAuth tokens stored per user in the DB.

### 2.4 Frontend / backend base URLs

**Current `.env` keys**

- `FRONTEND_BASE_URL`
- `GOOGLE_OAUTH_REDIRECT_BASE`

These are deployment-time settings and are treated as **workspace-wide settings**. They live in the Workspace tile under a **Runtime / URLs** section; some changes only take effect after a server restart. `.env` may provide a backup value when the setting is still empty.

### 2.5 Session / security

**Current `.env` keys**

- `SESSION_SECRET`

This is a core security secret. We store an **encrypted workspace setting** so it can be rotated from the UI. For new deployments you may also set it via `.env`, but once a workspace setting has been saved, that value is canonical and the env value is ignored unless the setting is missing.

### 2.6 Database and file paths

**Current `.env` keys**

- `DATABASE_URL`
- `DATA_DIR`
- `FILES_DIR`
- `EXPORT_DIR`
- `PROJECT_REGISTRY_FILE`

These are infrastructure / deployment settings and are surfaced in the Workspace tile (for example under a "Deployment" or "Storage" section). After a value has been saved, the database settings are the canonical source and `.env` is no longer required or read for that key.

### 2.7 Rate limiting, logging, runtime

**Current `.env` keys**

- `TIER_4_RATE_LIMIT`
- `DEFAULT_RATE_LIMIT`
- `LOG_LEVEL`
- `LOG_FILE`
- `SOCKET_MODE_ENABLED`
- `MAX_RECONNECT_ATTEMPTS`
- `API_PORT`
- `API_HOST`

These are operational/backend settings and are exposed in the Workspace tile (Runtime section). The Workspace tile is the primary place to view and change them (often requiring a restart to take effect). Once saved, the settings in the DB are what the app uses; `.env` only acts as a backup when the DB value is empty.

### 2.8 Workspace metadata

**Current `.env` keys**

- `WORKSPACE_NAME`
- `WORKSPACE_ID`

These are **workspace-level** and should be exposed in the **Workspace Settings** tile in a small section (e.g. "Workspace info"). The values are owned by the DB settings; `.env` is only consulted if the setting has not yet been filled in.

### 2.9 OpenAI / model configuration

**Current `.env` keys**

- `OPENAI_API_KEY`
- `EMBEDDING_MODEL`
- `RERANKER_MODEL`
- `LLM_MODEL`
- `EMBEDDING_BATCH_SIZE`
- `USE_GPU`

**Personal Settings (per-user)**

All LLM usage is configured **per user**. The AI agent in all tabs uses the current user's settings:

- `OPENAI_API_KEY` – required per user (encrypted personal key).
- `LLM_MODEL` – the user's chosen default chat / reasoning model.

These personal settings are the primary source for all LLM calls across tabs (Chat, Workflows, Projects, etc.).

**Workspace tile – AI section (shared infrastructure, read-only)**

The Workspace tile only holds **shared infrastructure AI settings** that are common for all users:

- `EMBEDDING_MODEL`
- `RERANKER_MODEL`
- `EMBEDDING_BATCH_SIZE`
- `USE_GPU`

In the initial implementation these fields are **display-only (read-only)** in the Workspace tile. They show which embedding / reranker models and performance configuration the backend is using, but cannot be changed from the UI because switching models or GPU usage typically requires deeper architectural and deployment changes.

### 2.10 Gmail safety and scope

**Current `.env` keys**

- `GMAIL_SEND_MODE`
- `GMAIL_ALLOWED_SEND_DOMAINS`
- `GMAIL_ALLOWED_READ_DOMAINS`
- `GMAIL_DEFAULT_LABEL`

All of these are **workspace-level policies** and belong in the **Workspace Settings** tile:

- `GMAIL_SEND_MODE` – `draft`, `confirm`, or `auto_limited`.
- `GMAIL_ALLOWED_SEND_DOMAINS` – list editor.
- `GMAIL_ALLOWED_READ_DOMAINS` – list editor.
- `GMAIL_DEFAULT_LABEL` – optional default label string.

---

## 3. Data model

We will add two core tables (or JSONB-backed models) in the backend database.

### 3.1 `UserSettings` (per-user)

- **Purpose**: store per-user preferences and secrets.
- **Scope**: one row per `AppUser`.

Suggested schema:

- `user_id` (PK, FK to `AppUser.id`)
- `settings` (JSONB, default `{}`)
- `updated_at` (timestamp)

Example `settings` payload:

```json
{
  "openai_api_key": "<encrypted>",
  "default_llm_model": "gpt-4o-mini",
  "timezone": "America/Los_Angeles"
}
```

### 3.2 `AppSettings` / `WorkspaceSettings` (shared)

- **Purpose**: store workspace-wide configuration.
- **Scope**: single row with `scope = "global"` for now.

Suggested schema:

- `id` (PK)
- `scope` (string, e.g. `"global"`)
- `settings` (JSONB, default `{}`)
- `updated_at` (timestamp)

Example `settings` payload:

```json
{
  "slack_bot_token": "<encrypted>",
  "notion_token": "<encrypted>",
  "notion_mode": "standard",
  "gmail_send_mode": "confirm",
  "gmail_allowed_send_domains": ["@company.com"],
  "gmail_allowed_read_domains": ["@company.com"],
  "gmail_default_label": "Datasaur",
  "workspace_name": "Agent- testing"
}
```

### 3.3 Secret encryption

- Secrets like `openai_api_key`, `slack_bot_token`, `notion_token` will be stored **encrypted**.
- Implement helpers in a small crypto utility using a symmetric key (derived from `SESSION_SECRET` or a dedicated `CONFIG_ENCRYPTION_KEY`).
- API responses will never return the full secret, only flags and partial info (e.g. `*_set: true`, `*_last4: "abcd"`).

---

## 4. Backend API design

Two main endpoints groups will back the Profile tiles.

### 4.1 Per-user settings endpoints

- `GET /api/settings/me`
  - Returns the current users settings in a UI-friendly shape:

    ```json
    {
      "openai_api_key_set": true,
      "openai_api_key_last4": "abcd",
      "default_llm_model": "gpt-4o-mini",
      "timezone": "America/Los_Angeles"
    }
    ```

- `PUT /api/settings/me`
  - Accepts partial updates, e.g.:

    ```json
    {
      "openai_api_key": "sk-...",
      "default_llm_model": "gpt-4o-mini"
    }
    ```

  - Encrypts secret fields before storing.
  - Allows clearing a secret (e.g. `"openai_api_key": ""`).

### 4.2 Workspace settings endpoints

- `GET /api/settings/workspace`
  - Returns workspace-level settings for the current deployment:

    ```json
    {
      "slack_bot_token_set": true,
      "notion_token_set": true,
      "notion_mode": "standard",
      "gmail_send_mode": "confirm",
      "gmail_allowed_send_domains": ["@company.com"],
      "gmail_allowed_read_domains": [],
      "gmail_default_label": "Datasaur",
      "workspace_name": "Agent- testing"
    }
    ```

- `PUT /api/settings/workspace`
  - Accepts partial updates for shared settings, encrypting secrets.
  - For now, **any authenticated user** can update these (everyone acts as admin). Later we can restrict to `is_admin` users.

### 4.3 Settings resolution helpers

Introduce a small `SettingsService` (e.g. `core/settings/service.py`) with helpers like:

- `get_effective_openai_key(user_id: str | None) -> str | None`
- `get_effective_llm_model(user_id: str | None) -> str`
- `get_effective_slack_bot_token() -> str | None`
- `get_effective_notion_token() -> str | None`
- `get_gmail_policy() -> GmailPolicy` (wrapper for send/read domains and mode)

Resolution order for something like the OpenAI key:

1. If user has personal `openai_api_key` in `UserSettings`, use that (this is the normal case).
2. Else fallback to `Config.OPENAI_API_KEY` from `.env` **only if** no personal setting exists yet (optional global backup for migration or brand-new deployments).

Over time we will migrate more runtime code (Slack, Notion, AI Brain, RAG) to use these helpers instead of reading directly from `Config`.

---

## 5. Frontend: Profile tab layout

We will update the Profile page to look like this:

1. **Account tile** (existing)
   - Shows Google account, Gmail connection, refresh button, Logout.
   - **We do not modify or move this tile.**

2. **Personal Settings tile** (new, below Account)
   - Fields:
     - Personal `OpenAI API key` (password input, shows only masked state + last 4 chars if set).
     - `Default model` (select from allowed options, e.g. `gpt-4o-mini`, `gpt-4.1`, etc.).
     - Optional: `Timezone` selector.
   - Buttons:
     - `Save` (enabled only when there are unsaved changes).
     - `Cancel` (resets to last saved values).

3. **Workspace Settings tile** (new, below Personal Settings)
   - Sections:
     - **Slack**
       - `Slack bot token` (masked, workspace-wide).
       - `Slack mode` (`read_only` / `standard` / `admin`).
       - `Read-only channels` (chips or comma-separated input).
       - `Blocked channels` (chips or comma-separated input).
     - **Notion**
       - `Notion token` (masked, workspace-wide).
       - `Notion mode` (`standard` / `read_only`).
       - `Parent page ID` (root Notion page ID used for Slack→Notion workflows).
     - **Gmail policies**
       - `Send mode` (`draft` / `confirm` / `auto_limited`).
       - `Allowed send domains` (list editor).
       - `Allowed read domains` (list editor).
       - `Default label`.
     - **Workspace info**
       - `Workspace name` (editable text).
       - `Workspace ID` (read-only or advanced).
     - **Runtime / URLs**
       - `Frontend base URL`.
       - `API host` and `API port`.
     - **Database / Storage**
       - `Database URL`.
       - `Data directory`, `Files directory`, `Export directory`, `Project registry file`.
     - **Runtime / Logging / Rate limits**
       - `Log level`, `Log file`.
       - `Tier 4 rate limit`, `Default rate limit`.
       - `Socket mode enabled`, `Max reconnect attempts`.
     - **AI infrastructure**
       - `Embedding model`, `Reranker model`.
       - `Embedding batch size`, `Use GPU` flag.
   - Buttons:
     - `Save` and `Cancel` with dirty-state tracking per tile.
   - Note explaining: "Changes here affect all users in this workspace. For now all users can edit these settings."

Both tiles will call the corresponding `/api/settings/me` and `/api/settings/workspace` endpoints on load and on save.

---

## 6. Migration strategy from `.env`

1. **Phase 1: Add settings tables and APIs**
   - Add `UserSettings` and `AppSettings` models and migrations.
   - Implement `SettingsService` helpers and new REST endpoints.

2. **Phase 2: Frontend Profile UI**
   - Add Personal and Workspace Settings tiles below the Account tile in the Profile page.
   - Wire them to the new endpoints with proper secret masking and dirty-state tracking.

3. **Phase 3: Runtime integration**
   - Update Slack client, Notion client, AI Brain, and Gmail policy checks to use `SettingsService` instead of reading directly from `Config`.
   - Use `.env` values only as backup when DB settings are not present (e.g. first deployment with empty settings tables).

4. **Phase 4: Hardening and cleanup**
   - Optionally add `is_admin` to `AppUser` and restrict workspace setting edits.
   - Treat the database-backed settings as the only source of truth; `.env` is used only for new deployments or emergency fallbacks.

This plan ensures you can control all configuration from the Profile tab (Personal + Workspace tiles), with `.env` used only to pre-fill values or as a last-resort fallback when no settings exist yet.
