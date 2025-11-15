# 🛠️ Workforce AI Agent - Complete Tools Catalog

This document lists the core tools available in the Workforce AI Agent, organized by platform.

> 💡 **November 2025 Update**: The agent now has **60+ tools** including advanced Gmail thread tools, Notion workspace tools, cross-platform project tracking, and utilities. This catalog focuses on the core set; see the README for a high-level overview of all capabilities.

---

## 📱 SLACK TOOLS (20 Tools)

### **Core Message Operations**

#### 1. **get_all_slack_channels**
**What it does:** Lists ALL Slack channels in your workspace with names, IDs, member counts, and privacy status.

**Use when:** User asks "what channels are there?", "list all channels", "show me slack channels"

**Parameters:** None

**Example:**
```
User: "List all Slack channels"
AI calls: get_all_slack_channels()
Returns: Found 15 channels:
  #general - 🌐 Public - 45 members (ID: C01ABC123)
  #engineering - 🌐 Public - 12 members (ID: C01ABC456)
  #marketing - 🔒 Private - 8 members (ID: C01ABC789)
```

---

#### 2. **get_channel_messages**
**What it does:** Retrieves ALL messages from a specific Slack channel (up to 100 most recent).

**Use when:** User asks "get messages from #channel", "show me #social messages", "what's in #team channel"

**Parameters:**
- `channel` (required): Channel name or ID
- `limit` (optional): Max messages (default: 100)

**Example:**
```
User: "Get messages from #social-slack-channel"
AI calls: get_channel_messages(channel="social-slack-channel", limit=50)
Returns: 50 messages with timestamps, usernames, and content
```

---

#### 3. **send_slack_message**
**What it does:** Posts a message to any Slack channel.

**Use when:** User asks "send message to #channel", "post to slack", "tell #team that..."

**Parameters:**
- `channel` (required): Channel ID
- `text` (required): Message content

**Example:**
```
User: "Send 'Meeting at 3pm' to #team"
AI calls: send_slack_message(channel="C01ABC", text="Meeting at 3pm")
```

---

#### 4. **search_slack**
**What it does:** Searches Slack messages for specific keywords across all channels in database.

**Use when:** User asks "find slack messages about X", "search for Y in slack"

**Parameters:**
- `query` (required): Search keywords
- `channel` (optional): Limit to specific channel
- `limit` (optional): Max results (default: 10)

**Example:**
```
User: "Find messages about 'deadline' in Slack"
AI calls: search_slack(query="deadline", limit=10)
```

---

#### 5. **summarize_slack_channel**
**What it does:** Gets channel messages and prepares them for AI summarization.

**Use when:** User asks "summarize #channel", "what happened in #team", "recap #general"

**Parameters:**
- `channel` (required): Channel name or ID
- `limit` (optional): Messages to analyze (default: 100)

**Example:**
```
User: "Summarize #engineering channel"
AI calls: summarize_slack_channel(channel="engineering", limit=100)
AI then analyzes and provides summary
```

---

### **Thread Operations**

#### 6. **get_thread_replies**
**What it does:** Retrieves all replies in a Slack thread/conversation.

**Use when:** User references a specific thread, wants to see conversation details

**Parameters:**
- `channel` (required): Channel ID
- `thread_ts` (required): Thread timestamp

**Example:**
```
User: "Show me replies to that message"
AI calls: get_thread_replies(channel="C01ABC", thread_ts="1699123456.789")
```

---

### **User Operations**

#### 7. **get_slack_user_info**
**What it does:** Gets detailed information about a Slack user including email, title, timezone, status.

**Use when:** User asks "who is @user", "get info for U12345", "what's john's email"

**Parameters:**
- `user_id` (required): Slack user ID

**Example:**
```
User: "Get info for user U01ABC123"
AI calls: get_slack_user_info(user_id="U01ABC123")
Returns:
  User: John Doe (@johndoe)
  Email: john@company.com
  Title: Software Engineer
  Timezone: America/Los_Angeles
```

---

### **Channel Management**

#### 8. **get_slack_channel_info**
**What it does:** Gets detailed information about a channel including topic, purpose, member count, creation date.

**Use when:** User asks "what's #channel about", "channel info for #team"

**Parameters:**
- `channel_id` (required): Channel ID

**Example:**
```
User: "What's #engineering channel about?"
AI calls: get_slack_channel_info(channel_id="C01ABC")
Returns: Topic, purpose, members, created date
```

---

#### 9. **set_channel_topic**
**What it does:** Sets or updates the topic of a Slack channel.

**Use when:** User asks "set channel topic to X", "update #team topic"

**Parameters:**
- `channel` (required): Channel ID
- `topic` (required): New topic text

**Example:**
```
User: "Set #team topic to 'Q4 Planning'"
AI calls: set_channel_topic(channel="C01ABC", topic="Q4 Planning")
```

---

### **Reactions**

#### 10. **add_slack_reaction**
**What it does:** Adds an emoji reaction to a Slack message.

**Use when:** User asks "add thumbs up to that message", "react with :fire:"

**Parameters:**
- `channel` (required): Channel ID
- `timestamp` (required): Message timestamp
- `emoji` (required): Emoji name (without colons)

**Example:**
```
User: "Add thumbs up reaction"
AI calls: add_slack_reaction(channel="C01ABC", timestamp="1699123.456", emoji="thumbsup")
```

---

### **Advanced Features (Available in API)**

The following features are available via Slack API but not yet exposed as tools. They can be added:

#### 11. **upload_file** (Not yet implemented)
Upload files to Slack channels

#### 12. **schedule_message** (Not yet implemented)
Schedule messages to be sent later

#### 13. **create_channel** (Not yet implemented)
Create new Slack channels

#### 14. **archive_channel** (Not yet implemented)
Archive a channel

#### 15. **invite_user_to_channel** (Not yet implemented)
Invite users to channels

#### 16. **set_user_presence** (Not yet implemented)
Set user's presence (away/active)

#### 17. **add_bookmark** (Not yet implemented)
Add bookmarks to channels

#### 18. **pin_message** (Not yet implemented)
Pin important messages

#### 19. **create_reminder** (Not yet implemented)
Set reminders for users

#### 20. **update_message** (Not yet implemented)
Edit existing Slack messages

---

## 📧 GMAIL TOOLS (15+ Tools)

### **Core Email Operations**

#### 21. **get_emails_from_sender**
**What it does:** Retrieves ALL emails from a specific person/sender with full content.

**Use when:** User asks "get emails from john@company.com", "show messages from ivan"

**Parameters:**
- `sender` (required): Email address or name
- `limit` (optional): Max emails (default: 10)

**Example:**
```
User: "Get emails from ivan@datasaur.ai"
AI calls: get_emails_from_sender(sender="ivan@datasaur.ai", limit=10)
Returns: 10 emails with dates, subjects, and body previews
```

---

#### 22. **get_email_by_subject**
**What it does:** Finds emails matching specific subject keywords.

**Use when:** User asks "find email about project", "get email with subject X"

**Parameters:**
- `subject` (required): Subject keywords to search

**Example:**
```
User: "Find email about quarterly review"
AI calls: get_email_by_subject(subject="quarterly review")
```

---

#### 23. **send_gmail**
**What it does:** Sends an email via Gmail to any recipient.

**Use when:** User asks "send email to X", "email john@company.com"

**Parameters:**
- `to` (required): Recipient email
- `subject` (required): Email subject
- `body` (required): Email content

**Example:**
```
User: "Send summary email to team@company.com"
AI calls: send_gmail(
  to="team@company.com",
  subject="Meeting Summary",
  body="..."
)
```

---

#### 24. **search_gmail**
**What it does:** Searches Gmail using keywords or Gmail search operators.

**Use when:** User asks "search emails for X", "find emails about budget"

**Parameters:**
- `query` (required): Search query
- `limit` (optional): Max results (default: 10)

**Example:**
```
User: "Search for emails about invoice"
AI calls: search_gmail(query="invoice", limit=10)
```

---

### **Label & Organization**

#### 25. **get_gmail_labels**
**What it does:** Lists all Gmail labels/folders (INBOX, SENT, custom labels, etc.).

**Use when:** User asks "what labels do I have", "list gmail folders"

**Parameters:** None

**Example:**
```
User: "Show me my Gmail labels"
AI calls: get_gmail_labels()
Returns: List of all labels with IDs
```

---

#### 26. **mark_email_read**
**What it does:** Marks an email as read (removes UNREAD label).

**Use when:** User asks "mark email as read", "mark that email read"

**Parameters:**
- `message_id` (required): Gmail message ID

**Example:**
```
AI calls: mark_email_read(message_id="18abc123def")
```

---

#### 27. **archive_email**
**What it does:** Archives an email (removes from INBOX).

**Use when:** User asks "archive that email", "move to archive"

**Parameters:**
- `message_id` (required): Gmail message ID

**Example:**
```
AI calls: archive_email(message_id="18abc123def")
```

---

#### 28. **add_gmail_label**
**What it does:** Adds a label/tag to an email.

**Use when:** User asks "label email as important", "tag with 'project'"

**Parameters:**
- `message_id` (required): Gmail message ID
- `label_name` (required): Label name

**Example:**
```
AI calls: add_gmail_label(message_id="18abc", label_name="Important")
```

---

### **Thread Operations & Advanced Search (NEW - Nov 2025)**

#### 29. **search_email_threads**
**What it does:** Searches for email *threads* (conversations) using any Gmail search query and returns thread summaries with message counts.

**Use when:** User asks "find the thread about X" or "show conversations about Y".

**Parameters:**
- `query` (required): Gmail search query (supports `from:`, `to:`, `subject:`, `has:attachment`, `after:`, `before:`, etc.)
- `limit` (optional): Max threads (default: 10)

#### 30. **get_complete_email_thread**
**What it does:** Retrieves the **ENTIRE** email thread with *all messages* and full bodies, no matter how long the chain is.

**Use when:** User wants to read the full conversation history.

**Parameters:**
- `thread_id` (required): Gmail thread ID

#### 31. **get_recent_email_thread_between_people**
**What it does:** Finds the most recent email thread between two people (by name or email) and returns the full conversation.

**Use when:** User asks "get our recent email thread between Yash and Ivan Lee".

**Parameters:**
- `person_a` (required): First person (name or email)
- `person_b` (required): Second person (name or email)
- `days_back` (optional): How many days back to search (default: 60)

---

## 📝 NOTION TOOLS (10+ Tools)

### **Page Operations**

#### 36. **create_notion_page**
**What it does:** Creates a new Notion page with title and content (supports markdown).

**Use when:** User asks "create notion page", "save to notion", "make a note"

**Parameters:**
- `title` (required): Page title
- `content` (required): Page content (markdown supported)

**Example:**
```
User: "Create a Notion page with meeting notes"
AI calls: create_notion_page(
  title="Team Meeting - Nov 12",
  content="# Agenda\n1. Q4 Review\n2. Planning..."
)
```

---

#### 37. **list_notion_pages**
**What it does:** Lists recent Notion pages in workspace.

**Use when:** User asks "list my notion pages", "what pages do I have"

**Parameters:**
- `limit` (optional): Max pages (default: 20)

**Example:**
```
User: "Show me my Notion pages"
AI calls: list_notion_pages(limit=20)
```

---

#### 38. **get_notion_page_content**
**What it does:** Retrieves the full content of a Notion page.

**Use when:** User asks "read this notion page", "get content of page X"

**Parameters:**
- `page_id` (required): Notion page ID

**Example:**
```
User: "Read the project roadmap page"
AI calls: get_notion_page_content(page_id="abc123...")
```

---

#### 39. **update_notion_page**
**What it does:** Updates a Notion page title.

**Use when:** User asks "rename page", "update page title"

**Parameters:**
- `page_id` (required): Page ID
- `title` (required): New title

**Example:**
```
AI calls: update_notion_page(page_id="abc123", title="New Title")
```

---

#### 40. **search_notion_content**
**What it does:** Searches Notion pages by content keywords using the Notion Search API.

**Use when:** User asks "search notion for X", "find pages about Y".

**Parameters:**
- `query` (required): Search query

**Example:**
```
User: "Find Notion pages about budget"
AI calls: search_notion_content(query="budget")
```

---

### **Workspace Search & Databases (NEW - Nov 2025)**

#### 41. **search_notion_workspace**
**What it does:** Searches across the entire Notion workspace (pages + databases) for a query.

**Use when:** User asks "search all notion for X", "what pages mention Y".

#### 42. **list_notion_databases**
**What it does:** Lists recent Notion databases in the workspace using the Notion Search API.

**Use when:** User asks "what databases do we have", "list notion databases".

#### 43. **append_to_notion_page**
**What it does:** Appends formatted content blocks to an existing Notion page (used heavily by project tracking).

**Use when:** User asks "update the project page with latest status".

---

## 🔍 WORKSPACE & PROJECT TOOLS (4+ Tools)

#### 46. **search_workspace**
**What it does:** Semantic search across ALL platforms (Slack, Gmail, Notion) using AI embeddings.

**Use when:** User asks broad questions that may span multiple tools

**Parameters:**
- `query` (required): Search query
- `sources` (optional): Which platforms to search (default: all)

**Example:**
```
User: "What did anyone say about Q4 goals across all platforms?"
AI calls: search_workspace(
  query="Q4 goals",
  sources=["slack", "gmail", "notion"]
)
Returns: Top 10 most relevant results from all sources
```

---

### **Cross-Platform Project Tracking (NEW - Nov 2025)**

#### 47. **track_project**
Aggregates updates from Slack, Gmail, and Notion for a given project, analyzes key points/action items/blockers, and computes progress.

#### 48. **generate_project_report**
Produces a stakeholder-ready text report with progress bars and sections for highlights, action items, and blockers.

#### 49. **update_project_notion_page**
Takes the latest tracked project status and appends it to an existing Notion page (does **not** create new pages).

### **Cross-Platform Utilities**

#### 50. **search_all_platforms**
Runs a unified search across Slack, Gmail, and Notion and returns a combined view.

#### 51. **get_team_activity_summary**
Summarizes what a specific person has been doing across Slack, Gmail, and Notion.

#### 52. **analyze_slack_channel**
Analyzes a Slack channel for activity level, most active users, and basic sentiment (positive/negative/questions).

---

## 🎯 Tool Categories Summary

| Category | Approx. Count | Description |
|----------|---------------|-------------|
| **Slack** | 20+ tools | Messages, channels, users, threads, reactions, files |
| **Gmail** | 15+ tools | Send, read, search, labels, threads, advanced search |
| **Notion** | 10+ tools | Create, read, update, search pages & databases |
| **Workspace & Projects** | 6+ tools | Semantic search, project tracking, analytics |
| **TOTAL** | **60+ tools** | Comprehensive workspace automation |

---

## 🚀 Multi-Tool Workflows

The AI can chain multiple tools automatically:

### Example 1: Slack → Notion
```
User: "Get messages from #social and save to Notion"

AI Workflow:
1. get_channel_messages(channel="social", limit=50)
2. create_notion_page(
     title="Social Channel Messages",
     content=<messages from step 1>
   )
```

### Example 2: Gmail → Slack
```
User: "Find emails from ivan@datasaur.ai and send summary to #team"

AI Workflow:
1. get_emails_from_sender(sender="ivan@datasaur.ai")
2. <AI generates summary>
3. send_slack_message(channel="C01ABC", text=<summary>)
```

### Example 3: Multi-source Search → Notion
```
User: "Search all platforms for 'budget' and create a summary doc"

AI Workflow:
1. search_workspace(query="budget", sources=["slack","gmail","notion"])
2. <AI analyzes and summarizes results>
3. create_notion_page(title="Budget References", content=<summary>)
```

---

## 📊 Tool Usage by Permission Level

### **Read-Only Tools** (No destructive actions)
- All `get_*`, `list_*`, `search_*` tools
- Safe to use anytime
- Examples: get_channel_messages, list_notion_pages, search_gmail

### **Write Tools** (Modify data)
- `send_*`, `create_*`, `update_*`, `add_*`, `mark_*`, `archive_*`
- Require user confirmation for sensitive operations
- Examples: send_slack_message, create_notion_page, archive_email

---

## 🔧 Implementation Status

✅ **Fully Implemented / Active** (majority of tools)
- All core Slack, Gmail, Notion operations
- Advanced Gmail threads, Notion workspace search, project tracking
- Cross-platform semantic search and team analytics

🟡 **Planned / Experimental**
- Additional advanced Slack features (scheduling, bookmarks, reminders)
- Deeper Notion database automations and workflows

---

**Last Updated:** November 2025  
**Total Tools:** 60+ (majority active; some advanced tools planned)
