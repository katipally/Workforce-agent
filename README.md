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
```

---

## 🗄️ Database Schema

All data is stored in `data/slack_data.db`:

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

- **Tier 4** (100+ req/min): `users.info`, `team.info`
- **Tier 3** (50 req/min): `chat.postMessage`, `conversations.info`
- **Tier 2** (20 req/min): `conversations.list`, `users.list`
- **Special** (1 req/min): `conversations.history` for free workspaces

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
