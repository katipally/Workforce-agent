<<<<<<< Updated upstream
# 🤖 Slack Workspace Agent

Complete Slack workspace data extraction, real-time streaming, and two-way communication using the official Slack API with Nov 2025 methods.

---

## ✨ Features

- ✅ Extract all workspace data (users, channels, messages, files, reactions)
- ✅ Real-time event streaming via Socket Mode
- ✅ Send messages, upload files, add reactions
- ✅ Automatic rate limiting & retry logic
- ✅ SQLite database storage
- ✅ Progress tracking with beautiful CLI

---

## 🚀 Quick Setup
=======
# Workforce Agent

A production-ready Python agent for extracting, monitoring, and exporting data from Slack, Gmail, and Notion. Built with PostgreSQL for scalability and AI/RAG readiness with pgvector support.

**Key Highlights:**
- 🚀 **Production Database**: PostgreSQL with connection pooling and pgvector
- 🤖 **AI/RAG Ready**: Vector embeddings support for semantic search
- 📊 **18 CLI Commands**: Complete data extraction and export pipeline
- 🔄 **Real-Time Streaming**: Socket Mode for live Slack events
- 📧 **Full Email Bodies**: Complete Gmail message extraction (not just snippets)
- 📝 **Notion Export**: Beautiful formatted exports to Notion pages

## ✨ Features

### Slack Integration
- **Data Extraction**: Users, channels, messages, files, reactions
- **Real-time Streaming**: Socket Mode for live event monitoring
- **Message Operations**: Send, receive, format, delete
- **File Management**: Upload and download files
- **Notion Export**: Export Slack data to formatted Notion pages

### Gmail Integration ✨ NEW
- **Email Extraction**: Emails, threads, labels, attachments
- **Thread Support**: Complete conversation history
- **Attachment Download**: Save email attachments locally
- **Smart Queries**: Search and filter emails efficiently
- **Notion Export**: Export Gmail data to formatted Notion pages
- **Free Tier Optimized**: Quota-aware extraction

### Data Management
- **PostgreSQL Database**: Production-ready database with pgvector support
- **AI/RAG Ready**: Vector embeddings support for semantic search
- **Statistics**: View counts and analytics
- **Structured Storage**: Relational database with full indexing
- **Migration Tools**: Easy migration from SQLite to PostgreSQL

---

## 📋 Requirements

- Python 3.8+
- PostgreSQL 14+ (with pgvector for AI features)
- Slack workspace with admin access (for Slack integration)
- Google account with Gmail (for Gmail integration)
- Notion account (for Notion export)

---

## 📚 Documentation

**Complete API setup guides available in:** `documentation/api_guide.md`

This includes step-by-step instructions for:
- ✅ Slack API setup (app creation, tokens, scopes)
- ✅ Notion API setup (integration creation, page sharing)
- ✅ Gmail API setup (OAuth credentials, consent screen)

---

## 🚀 Quick Start
>>>>>>> Stashed changes

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Slack API
1. Create a Slack App at https://api.slack.com/apps
2. Add these **Bot Token Scopes**:
   - `channels:history`, `channels:read`, `channels:join`, `channels:manage`
   - `groups:history`, `groups:read`
   - `im:history`, `im:read`
   - `mpim:history`, `mpim:read`
   - `users:read`, `users:read.email`
   - `team:read`
   - `chat:write`, `chat:write.public`
   - `files:read`, `files:write`
   - `reactions:read`, `reactions:write`
   - `app_mentions:read`
   - `usergroups:read`

3. Enable **Socket Mode** and generate app-level token
4. Install app to workspace and copy tokens

### 3. Set Environment Variables
Copy `.env.example` to `.env` and fill in:
```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
```

### 4. Test Connection
```bash
python main.py init
```

---

## 📋 All Available Commands

### 🔍 Testing & Verification
```bash
# Test all API connections (comprehensive)
python test_slack_integration.py

# Verify credentials are configured
python main.py verify-credentials

# Check API scopes
python check_scopes.py

# Initialize and test basic connection
python main.py init
```

### 📊 Data Extraction
```bash
# Extract everything (users, channels, messages, files)
python main.py extract-all

# Extract everything excluding archived channels
python main.py extract-all --exclude-archived

# Extract everything and download files
python main.py extract-all --download-files

# Extract specific data types
python main.py extract-users          # Users only
python main.py extract-channels       # Channels only
python main.py extract-messages       # Messages only
python main.py extract-files          # File metadata only
python main.py extract-files --download  # Download files too
```

### 📡 Real-Time Streaming
```bash
# Start real-time event streaming (WebSocket)
python main.py stream

# Press Ctrl+C to stop streaming
```

### 💬 Send Messages
```bash
# Send message to channel
python main.py send "#general" "Hello from Slack Agent!"

# Send message to specific user (DM)
python main.py send "@username" "Private message"

# Reply in a thread
python main.py send "#general" "Reply message" --thread-ts 1234567890.123456
```

### 📤 Upload Files
```bash
# Upload file to channel
python main.py upload "#general" /path/to/file.pdf

# Upload with title
python main.py upload "#general" /path/to/file.pdf --title "Important Document"

# Upload with comment
python main.py upload "#general" /path/to/file.pdf --comment "Please review this"
```

### 😀 Reactions
```bash
# Add reaction to message
python main.py react CHANNEL_ID MESSAGE_TIMESTAMP emoji_name

# Example
python main.py react C09RMS36L66 1234567890.123456 thumbsup
```

### 📈 View Statistics
```bash
# Show database statistics
python main.py stats

# List all channels
python main.py list-channels
```

---

## 📁 Project Structure

```
Workforce-agent/
<<<<<<< Updated upstream
├── main.py                 # CLI entry point
├── config.py              # Configuration management
├── test_slack_integration.py  # Comprehensive test suite
├── check_scopes.py        # Scope verification tool
├── requirements.txt       # Python dependencies
├── .env                   # Your credentials (do not commit!)
├── .env.example          # Template for credentials
├── cli/
│   └── main.py           # CLI commands implementation
├── database/
│   ├── models.py         # SQLAlchemy data models
│   └── db_manager.py     # Database operations
├── extractor/
│   ├── base_extractor.py      # Base extractor class
│   ├── users.py              # User extraction
│   ├── channels.py           # Channel extraction
│   ├── messages.py           # Message extraction
│   ├── files.py              # File extraction
│   └── coordinator.py        # Orchestrates all extractors
├── realtime/
│   ├── socket_client.py      # Socket Mode client
│   └── event_handlers.py     # Real-time event handlers
├── sender/
│   ├── message_sender.py     # Send messages
│   ├── file_sender.py        # Upload files
│   └── reaction_manager.py   # Manage reactions
├── utils/
│   ├── logger.py             # Logging setup
│   ├── rate_limiter.py       # Rate limiting
│   ├── backoff.py            # Retry logic
│   ├── request_verifier.py   # Request verification
│   └── oauth_handler.py      # OAuth flow
└── data/
    ├── slack_data.db         # SQLite database (auto-created)
    ├── files/                # Downloaded files
    └── raw_exports/          # JSON exports
=======
├── cli/                    # CLI commands
│   ├── __init__.py
│   └── main.py            # All CLI commands
├── config.py              # Configuration
├── database/              # PostgreSQL database
│   ├── models.py          # Data models (with pgvector support)
│   └── db_manager.py      # Database operations
├── slack/                 # Slack integration (unified)
│   ├── __init__.py
│   ├── client.py          # Unified Slack API client
│   ├── extractor/         # Data extraction
│   │   ├── users.py
│   │   ├── channels.py
│   │   ├── messages.py
│   │   ├── files.py
│   │   └── coordinator.py
│   ├── sender/            # Sending messages/files
│   │   ├── message_sender.py
│   │   ├── file_sender.py
│   │   └── reaction_manager.py
│   └── realtime/          # Real-time streaming
│       ├── event_handlers.py
│       └── socket_client.py
├── notion_export/         # Notion integration
│   ├── client.py
│   ├── exporter.py
│   └── full_database_exporter.py
├── gmail/                 # Gmail integration
│   ├── client.py
│   ├── extractor.py
│   └── exporter.py
├── utils/                 # Utilities
│   ├── logger.py
│   ├── rate_limiter.py
│   └── backoff.py
├── documentation/         # API setup guides
│   └── api_guide.md       # Complete setup instructions (2025 updates)
├── test-files/            # All test files
│   ├── test_slack.py
│   ├── test_notion.py
│   ├── test_gmail.py
│   └── test_complete_export.py
├── main.py                # Entry point
├── migrate_to_postgres.py # Database migration tool
├── google-credentials.json # Gmail OAuth credentials
├── .env                   # Environment variables (not in repo)
├── .env.example           # Environment template
└── requirements.txt       # Dependencies
>>>>>>> Stashed changes
```

---

## 🗄️ Database Schema

<<<<<<< Updated upstream
All data is stored in `data/slack_data.db`:
=======
**PostgreSQL database:** `workforce_agent` (default connection: `postgresql://localhost/workforce_agent`)

**Features:**
- Relational integrity with foreign keys
- Full-text search ready
- pgvector support for AI/RAG semantic search
- Connection pooling and automatic reconnection
>>>>>>> Stashed changes

- **Workspaces** - Workspace metadata
- **Users** - User profiles and info
- **Channels** - All channel types (public, private, DMs)
- **Messages** - Complete message history
- **Files** - File metadata and paths
- **Reactions** - All emoji reactions
- **SyncStatus** - Track extraction progress

---

## ⚡ Rate Limits

The agent automatically handles Slack's rate limits:

<<<<<<< Updated upstream
- **Tier 4** (100+ req/min): `users.info`, `team.info`
- **Tier 3** (50 req/min): `chat.postMessage`, `conversations.info`
- **Tier 2** (20 req/min): `conversations.list`, `users.list`
- **Special** (1 req/min): `conversations.history` for free workspaces
=======
| Variable | Required | Description |
|----------|----------|-------------|
| `SLACK_BOT_TOKEN` | ✅ | Bot User OAuth Token (xoxb-...) |
| `SLACK_APP_TOKEN` | ✅ | App-Level Token for Socket Mode (xapp-...) |
| `SLACK_APP_ID` | ⚪ | App ID |
| `SLACK_CLIENT_ID` | ⚪ | OAuth Client ID |
| `SLACK_CLIENT_SECRET` | ⚪ | OAuth Client Secret |
| `SLACK_SIGNING_SECRET` | ⚪ | Request verification secret |
| `NOTION_TOKEN` | ⚪ | Notion Integration Token (for export) |
| `NOTION_PARENT_PAGE_ID` | ⚪ | Notion page ID for exports |
| `GMAIL_CREDENTIALS_FILE` | ⚪ | Gmail OAuth credentials JSON file (default: credentials.json) |
| `GMAIL_TOKEN_FILE` | ⚪ | Gmail token pickle file (default: data/gmail_token.pickle) |
| `DATABASE_URL` | ⚪ | PostgreSQL connection string (default: postgresql://localhost/workforce_agent) |
| `LOG_LEVEL` | ⚪ | Logging level (default: INFO) |
>>>>>>> Stashed changes

The 1 req/min limit means extracting 100 channels takes ~100 minutes. This is normal for non-Marketplace apps.

---

## 🔧 Common Use Cases

### Full Workspace Backup
```bash
python main.py extract-all --download-files
```
Downloads everything including file attachments.

### Monitor Real-Time Activity
```bash
python main.py stream
```
Listens to all events (messages, reactions, channel changes, etc.)

### Send Automated Messages
```bash
python main.py send "#announcements" "Weekly reminder: Submit your reports!"
```

### Check What's Extracted
```bash
python main.py stats
```
Shows counts of users, channels, messages, files, reactions.

### Incremental Updates
```bash
python main.py extract-messages
```
Only extracts new messages since last sync.

---

## 🐛 Troubleshooting

### "not_in_channel" errors
The bot automatically joins channels now. If you still see errors, manually invite the bot to private channels.

### "missing_scope" errors  
Run `python check_scopes.py` to see which scopes are missing, then add them in Slack App settings and reinstall.

### Extraction is slow
This is normal! `conversations.history` is limited to 1 request per minute on free workspaces. Use `--exclude-archived` to speed up.

### Database errors
Make sure you have write permissions in the project directory. The `data/` folder is created automatically.

---

## 🧪 Testing

### Run comprehensive integration test
```bash
python test_slack_integration.py
```
Tests all 24 API features end-to-end. Should show 24/24 passed ✅

### Quick scope check
```bash
python check_scopes.py
```
Verifies your bot has all required permissions.

---

## 📝 Data Storage Locations

- **Database**: `data/slack_data.db`
- **Files**: `data/files/`
- **Logs**: `logs/slack_agent.log`
- **Exports**: `data/raw_exports/`

---

## 🎯 What This Agent Can Do

### Extract & Archive
- ✅ Every user profile
- ✅ Every channel (public, private, DMs, group DMs)
- ✅ Every message ever sent
- ✅ All file attachments
- ✅ All emoji reactions
- ✅ Complete thread conversations

### Real-Time Monitor
- ✅ New messages as they're sent
- ✅ Reactions added/removed
- ✅ Channels created/updated
- ✅ Users joined/updated
- ✅ Files uploaded

### Send & Interact
- ✅ Post messages anywhere
- ✅ Upload files
- ✅ Add/remove reactions
- ✅ Update/delete messages
- ✅ Reply in threads

---

## 🔐 Security Notes

- ✅ Never commit `.env` to Git (already in `.gitignore`)
- ✅ Treat tokens like passwords
- ✅ Use signing secret for webhook verification
- ✅ Rotate tokens if exposed
- ✅ Enable 2FA on your Slack account

---

## 📚 Technology Stack

- **Python 3.10+**
- **slack-sdk 3.37+** - Official Slack SDK
- **slack-bolt** - Slack app framework
- **SQLAlchemy** - Database ORM
- **Rich** - Beautiful CLI output
- **Click** - Command-line interface
- **Asyncio** - Async operations

---

## ✅ Quick Reference Card

| Task | Command |
|------|---------|
| Test everything | `python test_slack_integration.py` |
| Extract all data | `python main.py extract-all` |
| Start monitoring | `python main.py stream` |
| Send message | `python main.py send "#channel" "text"` |
| Upload file | `python main.py upload "#channel" file.pdf` |
| View stats | `python main.py stats` |
| Check credentials | `python main.py verify-credentials` |
| Check scopes | `python check_scopes.py` |

---

## 🎉 You're All Set!

Your Slack Agent is ready to use. Start with:

```bash
python main.py init           # Test connection
python main.py extract-all    # Get all data
python main.py stream         # Monitor real-time
```

For issues or questions, check the logs in `logs/slack_agent.log` or run the test suite.

---

**Built with ❤️ using Nov 2025 Slack API methods**
