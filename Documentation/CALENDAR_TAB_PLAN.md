# Calendar Tab Design

This document describes the design and V1 implementation plan for the **Calendar** tab in Workforce Agent.

## Goals

- Provide a **functional, interactive calendar UI** with:
  - `Today` (day view), `This week` (week view), and `This month` (month view).
  - Clickable events laid out on a time-based timeline/grid.
  - A detail panel that shows event details when an event is selected.
- Integrate with **Google Calendar** so each user sees their own events.
- Ensure all necessary Google Calendar permissions are requested **once at OAuth login** and then reused per user.
- Lay the groundwork to combine calendar data with **Slack, Gmail, Notion, and RAG** for a real meeting assistant.

---

## 1. UX & Layout

### 1.1 Tab placement

- Insert a new **Calendar** tab between **Workflows** and **Profile** in the main nav.
- Tabs now: `Chat`, `Pipelines`, `Projects`, `Workflows`, `Calendar`, `Profile`.

### 1.2 Calendar tab layout

Inside the Calendar tab:

- **Header / Toolbar**
  - Segmented view switch: `Today | This week | This month`.
  - Date navigator: `<`, `>` buttons plus a label:
    - Day view: `Nov 22, 2025`.
    - Week view: `Nov 17 – Nov 23, 2025`.
    - Month view: `November 2025`.
  - Optional: `Now` button to jump back to the current day/time.

- **Main calendar area (timeline)**
  - **Today (Day view)**
    - Vertical hour timeline (e.g. 06:00–22:00) with rows per hour.
    - Events are blocks spanning start–end time, stacked in a single column.
    - Current time indicator (red horizontal line) and auto-scroll to near "now".
  - **This week (Week view)**
    - 7 columns (Mon–Sun), hours on the y-axis.
    - Events grouped by day column; overlapping events rendered side-by-side.
  - **This month (Month view)**
    - Month grid (5–6 weeks x 7 days).
    - Each cell shows date and up to a few event pills (e.g. `09:00 Standup`).
    - `+N more` link in a cell to open a side panel or navigate to the day view.

- **Event detail panel** (bottom or right side)
  - Hidden until an event is selected from the timeline.
  - Shows:
    - Title, date/time, duration.
    - Location / Google Meet link (clickable).
    - Organizer and attendee list (mark internal vs external by domain).
    - Link: `Open in Google Calendar`.
    - Placeholder sections for:
      - Context summary (from Slack/Gmail/Notion via RAG).
      - Meeting notes (Notion page link / create button).
      - Actions (prepare agenda, send recap, etc.).

Interaction basics:

- Clicking an event sets `selectedEvent` and opens the detail panel.
- Switching view mode reloads events for the relevant time range.
- Navigating dates also refetches events.

---

## 2. Data & Integrations

### 2.1 Google Calendar

Use the **Google Calendar API** via the users OAuth token stored in `UserOAuthToken`.

- **Scopes**
  - Request Calendar access at login:
    - `https://www.googleapis.com/auth/calendar` (read/write) 
      - or `https://www.googleapis.com/auth/calendar.readonly` for read-only.
  - Add these scopes to the existing Google OAuth flow in `backend/api/main.py`:
    - `/auth/google/login` builds `scopes` as:
      - `['openid', 'email', 'profile'] + GmailClient.SCOPES + [calendar scopes]`.
- **API usage**
  - `events.list` for agenda/timeline data:
    - Use `timeMin` / `timeMax` derived from the current view (day/week/month).
    - `singleEvents=true`, `orderBy=startTime`.
  - `events.get` for event details.
  - Future phases could use `events.insert` / `events.patch` for scheduling, and `events.watch` for push notifications.

### 2.2 Other data sources (later phases)

Not all of this is needed for V1 implementation but they inform the design.

- **Gmail**
  - Invitations and meeting-related message threads.
  - Follow-up emails (summaries, action items).
- **Slack**
  - Channels and DMs involving event attendees.
  - Pre-meeting discussion and post-meeting debriefs.
- **Notion**
  - Project docs and past meeting notes.
  - Dedicated meeting notes page per calendar event.
- **RAG (HybridRAGEngine)**
  - Pull contextual snippets from Slack, Gmail, Notion based on event title, participants, and timeframe.
  - Generate concise context summaries and action lists.


---

## 3. Backend Design (V1)

### 3.1 OAuth scopes

**File:** `backend/api/main.py`

- In `/auth/google/login`, add Calendar scopes:

```python
scopes = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar",
] + GmailClient.SCOPES
```

- `/auth/google/callback` already stores the `scope` string into `UserOAuthToken.scope`. No schema changes are needed.
- Optionally compute and store `has_calendar_access` similar to `has_gmail_access` in `AppUser`, but this is not strictly required for the first cut of the Calendar UI.

### 3.2 Calendar endpoints

**New endpoints:**

- `GET /api/calendar/events`
  - Query params:
    - `view`: `day | week | month` (default `day`).
    - `date`: `YYYY-MM-DD` (default = today in users timezone or server timezone).
  - Behavior:
    1. Identify current user from session.
    2. Load their Google OAuth token (`UserOAuthToken` for provider `google`).
    3. Build a `google.oauth2.credentials.Credentials` instance from token fields.
    4. Construct `timeMin` / `timeMax` based on `view` & `date`.
    5. Call `calendar.events().list` with:
       - `calendarId='primary'`
       - `timeMin`, `timeMax`, `singleEvents=True`, `orderBy='startTime'`.
    6. Normalize results into a simple event DTO for the frontend, e.g.:

       ```json
       {
         "id": "string",
         "summary": "Team Sync",
         "description": "...",
         "start": { "dateTime": "2025-11-22T09:00:00Z" },
         "end": { "dateTime": "2025-11-22T09:30:00Z" },
         "organizer": { "email": "..." },
         "attendees": [ { "email": "...", "responseStatus": "accepted" } ],
         "hangoutLink": "https://meet.google.com/...",
         "location": "..."
       }
       ```

- `GET /api/calendar/events/{event_id}`
  - Fetches details for a specific event via `calendar.events().get`.
  - Returns a normalized DTO including all relevant metadata for the detail panel.

Implementation notes:

- Reuse the existing token storage (`UserOAuthToken`) and any existing utility/function used to build Google `Credentials` for Gmail.
- Handle error cases cleanly:
  - No Google token / missing Calendar scope  return `403` or a clear error message for the frontend.
  - Google API errors  log and surface a friendly error string.


---

## 4. Frontend Design (V1)

### 4.1 App navigation

**File:** `frontend/src/App.tsx`

- Extend `Tab` type:

```ts
type Tab = 'chat' | 'pipelines' | 'projects' | 'workflows' | 'calendar' | 'profile'
```

- Update persisted tab restore logic to accept `calendar` as a valid value.
- Add calendar button between Workflows and Profile:

```tsx
<button
  type="button"
  onClick={() => setActiveTab('calendar')}
  className={/* same style pattern as other tabs */}
>
  Calendar
</button>
```

- Add conditional rendering for a new `CalendarInterface` component:

```tsx
<div className={activeTab === 'calendar' ? 'h-full block' : 'h-full hidden'}>
  <CalendarInterface />
</div>
```

- Import `CalendarInterface` from `src/components/calendar/CalendarInterface`.

### 4.2 `CalendarInterface` component

**File:** `frontend/src/components/calendar/CalendarInterface.tsx`

State:

- `view: 'day' | 'week' | 'month'`.
- `selectedDate: Date`.
- `events: CalendarEvent[]` (normalized DTO from backend).
- `selectedEvent: CalendarEvent | null`.
- Loading/error flags.

Layout:

1. **Toolbar**
   - Segmented control for view type.
   - Date label + `<` / `>` navigation.
2. **Main timeline**
   - Render differently for day/week/month.
   - Clickable event blocks.
3. **Detail panel**
   - Renders when `selectedEvent` is not `null`.
   - Shows core event details and stub sections for context/notes/actions.

Data loading:

- On mount and whenever `view` or `selectedDate` changes, call:

  ```ts
  GET /api/calendar/events?view=${view}&date=${formatDate(selectedDate)}
  ```

- Handle loading & error states (e.g., show "Loading events," or error message card).

Interaction:

- Clicking an event sets `selectedEvent` and opens details.
- Clicking outside (or a close button) clears `selectedEvent`.


---

## 5. Phased Feature Roadmap

These are **future** enhancements beyond the initial V1 implementation.

### V2: Scheduling & Smart Reschedule

- "Find time with X" using Calendar free/busy information.
- Suggest candidate time slots across attendees.
- Reschedule existing events based on constraints.

### V2: Notion Meeting Docs & Follow-ups

- Automatically create or link a Notion page per event.
- After meeting, summarize notes or transcripts and:
  - Write structured notes into Notion.
  - Draft recap emails (Gmail) and Slack summaries.

### V3: RAG Context & Automation

- Pre-meeting context summary from Slack/Gmail/Notion.
- Post-meeting action extraction and reminder scheduling.
- Use Calendar `events.watch` to trigger just-in-time prep and follow-up prompts.


---

## 6. Testing Checklist

1. **OAuth & Permissions**
   - New login requests Calendar scope.
   - Re-login flow for existing users picks up Calendar scope.
2. **Calendar API**
   - `/api/calendar/events` returns events for day/week/month ranges.
   - `/api/calendar/events/{id}` returns full details.
3. **UI**
   - Calendar tab appears between Workflows and Profile.
   - `Today`, `This week`, `This month` views render correctly.
   - Events show up in the correct positions on the timeline.
   - Clicking an event opens the detail panel with correct data.
   - Loading and error states render gracefully.

This document is intended as the baseline reference for the Calendar tab implementation.
