# Auth Plan – Google OAuth + Gmail for Workforce Agent

## 1. Goals & Requirements

- **Single auth method:** Google OAuth (no passwords).
- **Unified signup + login:** First Google login creates an account, subsequent logins reuse it.
- **Gmail access:** Same OAuth flow must request Gmail API scopes so backend can read/send/modify emails on behalf of that user.
- **Per-user tokens:** No more `gmail_credentials.json` + `gmail_token.pickle` for the web app. Instead, store Google tokens per user in the database.
- **Full-stack integration:** Auth state applies across **all tabs** in the React UI:
  - Chat
  - Pipelines
  - Projects
  - Workflows
- **Account/Profile UI:** A dedicated profile area showing user info (name, email, avatar, Gmail connection status) and a **Logout** button.
- **Secure & deployable:** Suitable for production hosting with HTTPS and Google OAuth verification.


## 2. High-Level Architecture

### 2.1 Components

- **Backend:** FastAPI app (`backend/api/main.py`)
  - Owns Google OAuth logic and sessions.
  - Stores app users and Google tokens in Postgres.
  - Calls Gmail API on behalf of each user (no tokens in frontend).

- **Frontend:** React + Vite app (`frontend/`)
  - Talks to backend via REST/WebSocket.
  - Gets current user via `/auth/me`.
  - Redirects to Google login via backend when needed.
  - Has dedicated **Sign In** and **Profile** views.

- **Database:** Existing Postgres + SQLAlchemy models (`backend/core/database/models.py`)
  - New tables/models will be added for app-level users and OAuth tokens.
  - Existing `GmailAccount`/`GmailMessage` stay to represent data pulled from Gmail.

- **Google Cloud Project:**
  - OAuth 2.0 **Web Application** client.
  - Scopes: identity + Gmail.
  - Consent screen configured for Gmail access.


## 3. Google OAuth Configuration (External Setup)

### 3.1 OAuth Client

1. Create / use a Google Cloud project.
2. Enable **Gmail API**.
3. Create OAuth 2.0 **Client ID** of type **Web application**.
4. Configure **Authorized redirect URIs**, e.g.:
   - Local dev: `http://localhost:8000/auth/google/callback`
   - Prod: `https://api.yourdomain.com/auth/google/callback` (or similar backend domain)
5. Configure **Authorized JavaScript origins** if needed:
   - `http://localhost:5173` (dev frontend)
   - `https://app.yourdomain.com` (prod frontend)

### 3.2 Scopes

Requested scopes (can be adjusted later):

- Identity:
  - `openid`
  - `email`
  - `profile`
- Gmail (minimal working set):
  - `https://www.googleapis.com/auth/gmail.readonly`
  - Optionally also:
    - `https://www.googleapis.com/auth/gmail.modify`
    - `https://www.googleapis.com/auth/gmail.send`

All are **sensitive/restricted**; production use will require Google app verification.

### 3.3 Environment Variables

New env vars to add to `.env` (local) and hosting provider:

- `GOOGLE_CLIENT_ID` – from Google Cloud console.
- `GOOGLE_CLIENT_SECRET` – from Google Cloud console.
- `GOOGLE_OAUTH_REDIRECT_BASE` – e.g. `http://localhost:8000` or `https://api.yourdomain.com`.
- `SESSION_SECRET` – strong random string for signing session cookies.
- `FRONTEND_BASE_URL` – e.g. `http://localhost:5173` or `https://app.yourdomain.com`.

Notes:
- For the hosted app, **do not rely on** `GMAIL_CREDENTIALS_FILE` or `GMAIL_TOKEN_FILE`. Those become optional and only used for CLI/desktop-style dev flows if needed.


## 4. Backend Design (FastAPI)

### 4.1 Data Model Changes

Existing `User` model is for **Slack users**. Introduce new app-specific user models to avoid confusion.

#### 4.1.1 `AppUser` (new)

Represents a human user of the Workforce app (logged in with Google):

- `id` (string/UUID, primary key)
- `google_sub` (string, unique) – Google subject ID from ID token.
- `email` (string, unique)
- `name` (string)
- `picture_url` (string, nullable) – profile image URL.
- `created_at` (datetime)
- `updated_at` (datetime)
- `last_login_at` (datetime)
- Optional flags:
  - `has_gmail_access` (bool) – derived from tokens/scopes.
  - `is_admin` (bool) – for future features.

Relationship (optional):
- Link to `GmailAccount` via `email` (logical association) – no strict FK to keep Gmail ingestion flexible.

#### 4.1.2 `UserOAuthToken` (new)

Per-user OAuth credentials for Gmail (and potentially other providers later):

- `id` (int PK or UUID)
- `user_id` (FK to `AppUser.id`)
- `provider` (string) – e.g. `google`.
- `access_token` (encrypted string)
- `refresh_token` (encrypted string, nullable if not requested)
- `expires_at` (datetime)
- `scope` (JSON/text) – list of granted scopes.
- `token_type` (string) – usually `Bearer`.
- `created_at` (datetime)
- `updated_at` (datetime)
- Flags:
  - `revoked` (bool, default False) – set true if refresh fails due to revocation.

Indexing:
- Index on `(user_id, provider)` and `expires_at`.

### 4.2 Session Management

Use **HTTP-only, secure cookies** with FastAPI.

- Cookie name: e.g. `wf_session`.
- Cookie value: **opaque session ID** (random string), not user ID.
- Session store (simple option): DB table `AppSession` (optional, can also be JWT-based).

#### 4.2.1 `AppSession` (optional but recommended)

- `id` (string/UUID PK) – stored in cookie.
- `user_id` (FK to `AppUser.id`)
- `created_at` (datetime)
- `expires_at` (datetime)
- `last_seen_at` (datetime)
- `ip_address` (optional)
- `user_agent` (optional)

On each request:
- Read `wf_session` cookie.
- Load `AppSession`, check `expires_at`.
- Load associated `AppUser`.

Security:
- Mark cookie `HttpOnly`, `Secure` (in prod), `SameSite=Lax`.

### 4.3 Auth Endpoints

All endpoints reside under `/auth/*`.

#### 4.3.1 `GET /auth/google/login`

- Purpose: Start Google OAuth flow.
- Behavior:
  - Build Google authorization URL with:
    - `client_id = GOOGLE_CLIENT_ID`
    - `redirect_uri = {GOOGLE_OAUTH_REDIRECT_BASE}/auth/google/callback`
    - `response_type = code`
    - `scope = openid email profile gmail scopes`
    - `access_type = offline` (to receive refresh_token)
    - `prompt = consent` (on first time to ensure refresh_token)
  - Optional: include a `state` parameter containing:
    - CSRF token
    - original path to redirect back to (e.g. which tab user was on).
  - Redirect browser to Google.

#### 4.3.2 `GET /auth/google/callback`

- Invoked by Google with `code` and `state`.
- Steps:
  1. Validate `state` (CSRF + optional redirect path).
  2. Exchange `code` for tokens via Google token endpoint.
  3. Extract from response:
     - `id_token` (decode JWT to get `sub`, `email`, `name`, `picture`).
     - `access_token`, `refresh_token`, `expires_in`, `scope`, `token_type`.
  4. Upsert `AppUser`:
     - Look up by `google_sub` or `email`.
     - If not found: create new `AppUser`.
     - Update `name`, `picture_url`, `last_login_at`.
  5. Upsert `UserOAuthToken` for this user and provider `google`.
     - Encrypt store `access_token`, `refresh_token`.
     - Set `expires_at = now + expires_in`.
     - Mark `revoked = False`.
  6. Create `AppSession` row and set `wf_session` cookie.
  7. Redirect browser to frontend, e.g.:
     - `FRONTEND_BASE_URL` or `FRONTEND_BASE_URL + state.return_path`.

Error handling:
- If exchange fails or scopes missing, redirect to frontend with error query param (e.g. `?auth_error=...`).

#### 4.3.3 `POST /auth/logout`

- Purpose: Log the user out.
- Behavior:
  - Read `wf_session` cookie.
  - Delete or mark `AppSession` as expired.
  - Clear `wf_session` cookie (set expired cookie).
  - Return 204 or JSON success.

#### 4.3.4 `GET /auth/me`

- Purpose: Return current app user profile.
- Behavior:
  - Use dependency `get_current_user()` to resolve `AppUser` from session.
  - Response includes:
    - `id`, `email`, `name`, `picture_url`.
    - Flags: `has_gmail_access` (based on presence of non-revoked tokens/scopes).
  - If no valid session: return 401.


### 4.4 Dependencies & Middleware

#### 4.4.1 `get_current_user` dependency

- Reads `wf_session` cookie.
- Loads `AppSession` and `AppUser`.
- Raises 401 if missing/invalid/expired.
- Used in all protected routes, especially:
  - Chat endpoints.
  - Pipelines (Slack, Gmail, Notion) – if desired.
  - Projects, Workflows.

#### 4.4.2 `get_current_user_with_gmail`

- Extends `get_current_user`.
- Verifies user has a non-revoked `UserOAuthToken` for `google` with required Gmail scopes.
- If not:
  - Return 403 with a message like `GMAIL_NOT_AUTHORIZED` so frontend can prompt the user to (re)connect Gmail.


### 4.5 GmailClient Refactor (Multi-User)

Current implementation:
- Uses `InstalledAppFlow` with `credentials_file` and a single `GMAIL_TOKEN_FILE`.
- This is single-user / desktop behavior.

Target behavior:
- **No token files** for the web app.
- Build Gmail `Credentials` from `UserOAuthToken` for the **current AppUser**.

#### 4.5.1 Construction

- Create a helper: `build_gmail_credentials_for_user(user: AppUser) -> Credentials | None`.
- Steps:
  - Load `UserOAuthToken` for `(user_id=user.id, provider='google')`.
  - If not found or `revoked = True`: return None.
  - Create `Credentials` object from stored tokens and scopes.
  - If `expires_at` is in the past and `refresh_token` exists:
    - Call `.refresh(Request())`.
    - On success: update `access_token`, `expires_at` in DB.
    - On failure (e.g. revoked): set `revoked = True` and return None.

#### 4.5.2 GmailClient usage

- Modify `GmailClient` to accept `credentials: Credentials` directly instead of reading from file.
- Remove `InstalledAppFlow` usage for web backend paths.
- For the pipelines and API endpoints (e.g. `/api/pipelines/gmail/labels`, `_run_gmail_pipeline`):
  - Require `AppUser` with `get_current_user_with_gmail`.
  - Build `Credentials` from user tokens.
  - Instantiate `GmailClient(credentials=...)`.

Development-only fallback:
- Optionally keep a CLI-only path that still uses `InstalledAppFlow` and token pickle **for local testing**.
- Clearly separate this from web flow and keep out of deployed environment.


### 4.6 Protecting Existing Gmail Endpoints

Endpoints such as:
- `GET /api/pipelines/gmail/labels`
- `POST /api/pipelines/gmail/run` (or similar)

Adjustments:
- Add `get_current_user_with_gmail` dependency.
- Use user-specific `GmailClient` instead of global one.
- If Gmail not authorized, return an empty list or a 403 with a clear error code for the frontend to handle.


## 5. Frontend Design (React + Vite)

### 5.1 Auth-Aware App Shell

Current `App.tsx` has a simple tabbed layout for:
- Chat
- Pipelines
- Projects
- Workflows

Plan:
- Introduce a top-level **AuthProvider** / store (Zustand or React context) that:
  - On initial load, calls `/auth/me` once.
  - Stores `user` state (or `null` if not logged in).
  - Exposes `signIn`, `signOut`, `refreshUser` helpers.

- While `user` is loading:
  - Show a centered loading or splash screen.

- If `user` is `null` (not logged in):
  - Redirect to **SignInPage** or show sign-in UI instead of the main tabs.

### 5.2 New Pages/Components

#### 5.2.1 `SignInPage`

- Contains:
  - App logo/name.
  - Simple text: "Sign in with Google to use Workforce Agent".
  - A single primary button: **Continue with Google**.

- Behavior:
  - Clicking the button sends the browser to backend endpoint `/auth/google/login` (full navigation, not XHR).
  - After Google and backend callback, user is redirected back to frontend (e.g. `/`), `AuthProvider` calls `/auth/me` and initializes user state.

- Routing:
  - If using a simple router, `SignInPage` can be at `/signin`.
  - Or can be the default screen when `user == null`.

#### 5.2.2 `ProfilePage` (Account/Profile tab)

- Accessible from a **Profile** menu/tab visible when logged in.
- Shows:
  - User name
  - Email
  - Profile picture
  - Gmail connection status:
    - Connected (scopes present) – maybe show primary Gmail address.
    - Not connected / revoked – show a warning and a button to reconnect (triggers `/auth/google/login` again, possibly with Gmail scopes only).
- Contains **Logout** button.

#### 5.2.3 Logout Flow

- When user clicks Logout:
  - Frontend calls `POST /auth/logout` (via `fetch` or react-query mutation).
  - On success:
    - Clear `user` in AuthProvider.
    - Redirect to `SignInPage`.

### 5.3 Integrating with Existing Tabs

- **App-level behavior:**
  - If `user` is not set, do **not** render `ChatInterface`, `PipelinesInterface`, `ProjectsInterface`, `WorkflowsInterface`.
  - Instead, show `SignInPage` or a message with button linking to sign-in.

- **After login:**
  - All existing tabs work as today but requests now carry the session cookie.
  - Gmail-related tabs will only function if backend confirms Gmail is connected; otherwise, show a prompt: "Connect Gmail in your profile to use this feature".

- **Navigation for profile:**
  - Add either:
    - A **fifth tab**: `Profile`, or
    - A button/avatar in the header that opens a small menu: `Profile`, `Logout`.


## 6. Edge Cases & Scenarios

### 6.1 User Denies Gmail Scope on First Login

- They may still grant `openid email profile` but refuse Gmail.
- Backend behavior:
  - `AppUser` is created.
  - `UserOAuthToken` may have missing Gmail scopes / absent record.
  - `has_gmail_access = False`.
- Frontend:
  - User is logged in to app.
  - Profile page shows Gmail status as "Not connected".
  - Gmail-dependent features:
    - Backend returns 403 or an empty label list with a specific error code.
    - UI surfaces a "Connect Gmail" CTA that redirects to `/auth/google/login` again, now emphasizing Gmail usage (incremental auth).

### 6.2 User Revokes Gmail Access Later (Google Account Settings)

- Token refresh will fail with a `RefreshError` or 4xx.
- Backend:
  - Mark `UserOAuthToken.revoked = True`.
  - Future Gmail calls for this user return `GMAIL_NOT_AUTHORIZED` error.
- Frontend:
  - On receiving such an error, show in UI that Gmail is disconnected and offer a "Reconnect Gmail" button.

### 6.3 Token Expiry

- Access tokens expire (e.g. 1 hour).
- Backend should:
  - Check `expires_at` before each Gmail call.
  - If expired and `refresh_token` present:
    - Refresh silently and update DB.
  - If refresh fails: treat as **revoked**.

### 6.4 Multiple Devices / Browsers

- Each login can create a separate `AppSession` entry.
- All sessions map to the same `AppUser` and share one set of Gmail tokens.
- Logging out from one device does not auto-logout all others (unless specifically implemented by invalidating all sessions for user).

### 6.5 Backward Compatibility / Local CLI

- Existing `GmailClient` desktop-style behavior can remain **only for local CLI tools** if needed, but:
  - Clearly separate CLI entry points from web backend.
  - In production web deployment, only the new per-user web flow should be used.


## 7. Configuration & Environment Notes

- `.env` should be updated to include new Google and session settings.
- Document that `GMAIL_CREDENTIALS_FILE` and `GMAIL_TOKEN_FILE` are **deprecated for the hosted web app**.
- For local dev, you can:
  - Either use the web OAuth flow even on localhost.
  - Or keep CLI tools for quick one-off experiments.


## 8. Deployment Considerations

- **HTTPS required** in production for secure cookies (`Secure` flag).
- Google OAuth **Authorized redirect URIs** must match the backend base URL exactly.
- Ensure CORS is correctly configured in FastAPI for the production frontend domain.
- Privacy Policy and Terms URLs required for Google OAuth verification (can be static pages hosted in the frontend).


## 9. Implementation Phases

This is the suggested order to implement the plan.

### Phase 0 – External Setup

1. Configure Google Cloud project, OAuth client, and Gmail API.
2. Add `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_OAUTH_REDIRECT_BASE`, `FRONTEND_BASE_URL`, `SESSION_SECRET` to `.env`.

### Phase 1 – Backend Models & Sessions

1. Add `AppUser`, `UserOAuthToken`, and optionally `AppSession` models.
2. Run DB migration / schema update.
3. Implement session middleware / helper functions (`create_session`, `get_session`, `destroy_session`).

### Phase 2 – Auth Endpoints

1. Implement `/auth/google/login` (redirect to Google).
2. Implement `/auth/google/callback` (code exchange, user creation, token storage, session cookie, redirect).
3. Implement `/auth/logout` and `/auth/me`.
4. Basic tests: hitting `/auth/me` before/after login.

### Phase 3 – GmailClient Refactor

1. Implement helper to build `Credentials` from `UserOAuthToken`.
2. Refactor `GmailClient` to accept `Credentials` instead of reading token files (for web paths).
3. Update Gmail-related endpoints and pipelines to:
   - Require authenticated `AppUser`.
   - Use per-user Gmail credentials.
4. Test Gmail pipeline with a real Google account in **test mode**.

### Phase 4 – Frontend Auth Integration

1. Create AuthProvider / global auth store.
2. Call `/auth/me` on app startup; store user.
3. Implement `SignInPage` and route it.
4. Add Sign In button that navigates to `/auth/google/login`.
5. Implement `ProfilePage` showing user details and Gmail status.
6. Add Logout button calling `/auth/logout` and clearing local auth state.
7. Protect main tabs: only show if `user` exists; otherwise, show sign-in.

### Phase 5 – Edge Cases & Polish

1. Handle Gmail not connected / revoked errors gracefully in UI.
2. Add visual cues for Gmail connection status on Pipelines tab.
3. Ensure CORS and cookies work in both local dev and production builds.
4. Add minimal tests (backend + frontend) for auth and Gmail flows.

---

This document defines the **architecture and behavior** of the new Google OAuth-based authentication system for Workforce Agent. Next steps are to implement these phases incrementally in the existing codebase without breaking current Slack/Notion features.
