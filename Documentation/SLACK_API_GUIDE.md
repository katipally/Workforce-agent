# Slack API Guide - Complete Reference

## Overview

Slack provides a comprehensive API that allows you to extract information, stream real-time events, and send information back to workspaces. This guide covers everything you need to know about working with Slack's API as of October 2025.

---

## Authentication & Setup

### Token Types

**Bot Tokens** (Recommended)
- Start with `xoxb-`
- Not tied to a specific user
- App remains functional even if installing user is deactivated
- Requires individual scopes

**User Tokens**
- Tied to a specific user's identity
- Can act on behalf of users
- Requires user consent for scopes

**App-Level Tokens**
- Start with `xapp-`
- Used for Socket Mode connections
- Required for WebSocket-based event streaming

### Required Scopes

Here are common scopes you'll need:

**For Reading Messages & History:**
- `channels:history` - View messages in public channels
- `groups:history` - View messages in private channels
- `im:history` - View messages in direct messages
- `mpim:history` - View messages in group direct messages

**For Reading Channel/User Information:**
- `channels:read` - View basic info about public channels
- `groups:read` - View basic info about private channels
- `users:read` - View users in workspace
- `users:read.email` - Access user email addresses

**For Reading Files:**
- `files:read` - View files shared in channels

**For Sending Messages:**
- `chat:write` - Post messages in channels/DMs
- `chat:write.public` - Post messages to channels without joining

**For Reactions:**
- `reactions:read` - View reactions
- `reactions:write` - Add/remove reactions

---

## What Information Can You Extract?

### 1. **Messages & Conversation History**

You can retrieve:
- All messages from public channels
- Messages from private channels (if bot is member or has proper scopes)
- Direct messages
- Threaded messages (replies)
- Message metadata (timestamp, user, reactions, attachments)
- Edited message history
- Deleted message indicators

**Key API Methods:**
- `conversations.history` - Get messages from a conversation
- `conversations.replies` - Get thread replies
- `conversations.list` - List all channels

### 2. **Channels & Workspaces**

You can extract:
- Channel names, IDs, topics, purposes
- Channel membership lists
- Public vs private channel status
- Archived channel status
- Shared channel information (Slack Connect)

**Key API Methods:**
- `conversations.list` - List all channels
- `conversations.info` - Get channel details
- `conversations.members` - Get channel members

### 3. **Users & Profiles**

You can retrieve:
- User names, real names, display names
- User IDs
- Email addresses (with proper scope)
- User status and presence
- Profile photos
- Timezone information
- Custom profile fields

**Key API Methods:**
- `users.list` - List all users
- `users.info` - Get user details
- `users.profile.get` - Get user profile

### 4. **Files & Attachments**

You can access:
- Uploaded files
- File metadata (name, type, size, timestamp)
- File URLs (with authentication)
- File comments and reactions
- Shared file locations

**Key API Methods:**
- `files.list` - List files
- `files.info` - Get file details
- Note: `files.upload` is deprecated; use `files.getUploadURLExternal` + `files.completeUploadExternal` sequence

### 5. **Reactions & Interactions**

You can extract:
- All reactions on messages
- Who reacted with what emoji
- Reaction timestamps

**Key API Methods:**
- `reactions.get` - Get reactions for a message
- `reactions.list` - List user's reactions

---

## Real-Time Streaming

### Socket Mode (Recommended for Real-Time)

Socket Mode allows you to receive events via WebSocket without exposing a public HTTP endpoint.

**How It Works:**
1. Enable Socket Mode in your app settings
2. Generate an app-level token
3. Call `apps.connections.open` to get WebSocket URL
4. Connect to WebSocket
5. Receive events in real-time

**Features:**
- Supports up to 10 concurrent WebSocket connections
- No public URL required
- Automatic reconnection handling
- Connection typically lasts ~3600 seconds

**Events You Can Stream:**
- `message` - New messages posted
- `reaction_added` / `reaction_removed` - Reactions added/removed
- `channel_created` / `channel_deleted` - Channel changes
- `team_join` - New users join
- `user_change` - User profile updates
- `file_shared` - Files uploaded
- `app_mention` - Your app is mentioned
- And 50+ more event types

### Events API (HTTP-based alternative)

If you prefer HTTP callbacks over WebSockets:
- Slack sends POST requests to your public URL
- You must respond with HTTP 200 within 3 seconds
- Slack will retry failed deliveries
- Requires publicly accessible endpoint

**Both approaches support the same event types.**

---

## Two-Way Communication (YES!)

### You Can Send Information Back

Slack is fully bidirectional. You can:

**1. Post Messages**
- Send text messages to channels
- Send rich messages with Block Kit (buttons, dropdowns, etc.)
- Post threaded replies
- Post ephemeral messages (visible only to specific user)
- Update existing messages
- Delete messages

**Method:** `chat.postMessage`, `chat.update`, `chat.delete`

**2. Create & Manage Channels**
- Create new channels
- Archive channels
- Set channel topic/purpose
- Invite/remove users

**Methods:** `conversations.create`, `conversations.invite`, `conversations.archive`

**3. Upload Files**
- Upload files to channels
- Add files with comments
- Upload via URL or binary data

**Methods:** `files.getUploadURLExternal` → upload to URL → `files.completeUploadExternal`

**4. Add Reactions**
- Add emoji reactions to messages
- Remove reactions

**Methods:** `reactions.add`, `reactions.remove`

**5. Update User Profiles** (User token required)
- Update status
- Update profile fields

**Methods:** `users.profile.set`, `users.setPresence`

**6. Interactive Features**
- Respond to button clicks
- Handle slash commands
- Show modals
- Send interactive menus

---

## Rate Limits (Important!)

### Web API Rate Limits

Slack uses a tiered rate limit system (Tier 1-4 + Special):
- **Tier 1**: ~1 request/minute (most restrictive)
- **Tier 2**: ~20 requests/minute
- **Tier 3**: ~50 requests/minute
- **Tier 4**: ~100+ requests/minute (most permissive)

**Special Note on conversations.history:**
- For **non-Marketplace apps** created after May 29, 2025: **1 request/minute**
- Maximum 15 messages per request
- For Marketplace apps: Tier 3 (50+ requests/minute)

### Burst Limits

- Slack recommends max 1 request/second sustained
- Temporary bursts above this are allowed
- Exact burst limits are not published

### Message Posting Limits

- 1 message per second per channel recommended
- Rate limit headers included in responses:
  - `X-Rate-Limit-Limit`
  - `X-Rate-Limit-Remaining`
  - `Retry-After` (when rate limited)

### Best Practices

- Use cursor-based pagination for better rate limits
- Implement exponential backoff on rate limit errors
- Cache data when possible
- Use bulk methods when available

---

## Pagination

Most list methods support cursor-based pagination:

```
{
  "channels": [...],
  "response_metadata": {
    "next_cursor": "dGVhbTpDMDYxRkE1UEI="
  }
}
```

**How to paginate:**
1. Make initial request with `limit` parameter (default 100-200 depending on method)
2. Check `response_metadata.next_cursor`
3. If cursor exists, make next request with `cursor` parameter
4. Repeat until `next_cursor` is empty

**Methods supporting pagination:**
- `conversations.list`
- `conversations.history`
- `users.list`
- `files.list`
- And many more

---

## Data Structure & Storage

### Message Object Structure

```json
{
  "type": "message",
  "user": "U123456",
  "text": "Hello world",
  "ts": "1234567890.123456",
  "channel": "C123456",
  "thread_ts": "1234567890.123456",  // If part of thread
  "reactions": [
    {
      "name": "thumbsup",
      "count": 2,
      "users": ["U123", "U456"]
    }
  ],
  "files": [...],  // If has attachments
  "edited": {
    "user": "U123456",
    "ts": "1234567890.123456"
  }
}
```

### Conversation Object

```json
{
  "id": "C123456",
  "name": "general",
  "is_channel": true,
  "is_private": false,
  "is_archived": false,
  "is_shared": false,
  "topic": {...},
  "purpose": {...},
  "num_members": 150
}
```

### User Object

```json
{
  "id": "U123456",
  "name": "username",
  "real_name": "John Doe",
  "profile": {
    "email": "john@example.com",
    "display_name": "Johnny",
    "status_text": "Working",
    "image_512": "https://...",
    "fields": {...}
  },
  "is_bot": false,
  "is_admin": false,
  "tz": "America/Los_Angeles"
}
```

---

## Common Use Cases & Workflows

### 1. **Archive All Messages from Workspace**

```
1. Get all conversations (conversations.list with pagination)
2. For each conversation:
   - Get conversation history (conversations.history with pagination)
   - For messages with threads, get replies (conversations.replies)
   - Store messages with metadata
3. Handle rate limits with delays
```

### 2. **Real-Time Message Monitoring**

```
1. Enable Socket Mode
2. Connect to WebSocket
3. Subscribe to 'message' events
4. Process events as they arrive
5. Store in database with proper indexing
```

### 3. **Extract & Store Files**

```
1. List files (files.list with pagination)
2. Download file content using file.url_private
3. Store file metadata and content
4. Track file shares across channels
```

### 4. **Build Searchable Archive**

```
1. Extract all messages, users, channels
2. Store in structured format (database/JSON)
3. Index for full-text search
4. Maintain relationships (threads, reactions, mentions)
```

---

## SDK & Libraries

### Official SDKs

**Python:** `slack-sdk`
```bash
pip install slack-sdk
```

**Node.js:** `@slack/web-api` and `@slack/socket-mode`
```bash
npm install @slack/web-api @slack/socket-mode
```

**Java:** `slack-api-client`

**Bolt Framework** (Recommended for full apps)
- Bolt for Python
- Bolt for JavaScript
- Handles events, commands, shortcuts automatically

---

## Important Changes (As of Oct 2025)

1. **files.upload is deprecated** - Use three-step upload process instead
2. **Rate limits for non-Marketplace apps** - conversations.history limited to 1 req/min for new apps
3. **RTM API is legacy** - Use Socket Mode or Events API instead
4. **Socket Mode** - Preferred for real-time without public URLs

---

## Recommended Architecture for Your Agent

### For Extracting Historical Data:
```
[Your Agent]
    ↓
[Slack Web API]
    ↓
[Rate Limiter / Queue]
    ↓
[Data Storage (DB/Files)]
```

### For Real-Time Streaming:
```
[Slack Socket Mode WebSocket]
    ↓
[Your Agent Event Handler]
    ↓
[Event Queue/Processor]
    ↓
[Structured Storage]
```

### For Two-Way Communication:
```
[Your Agent Logic]
    ↓
[Slack Web API Client]
    ↓
[chat.postMessage / reactions.add / etc.]
    ↓
[Slack Workspace]
```

---

## Summary

**Can Extract:**
✅ All message history (with proper scopes)
✅ Real-time message streams
✅ User, channel, file information
✅ Reactions, threads, attachments
✅ Workspace metadata

**Real-Time Streaming:**
✅ Socket Mode (WebSocket, up to 10 connections)
✅ Events API (HTTP callbacks)
✅ 50+ event types available

**Two-Way Communication:**
✅ Post messages, files, reactions
✅ Create/manage channels
✅ Interactive UI components
✅ Update user presence/status

**Rate Limits:**
⚠️ Tiered system (1-100+ req/min depending on method)
⚠️ Special limits for conversations.history (1 req/min for non-Marketplace apps)
⚠️ Pagination recommended
⚠️ Cursor-based pagination gets better limits

**Storage Format:**
📦 JSON responses
📦 Structured objects for messages, users, channels
📦 Pagination cursors for large datasets
📦 Unique IDs for all entities (message timestamps, user IDs, channel IDs)
