# Slack Workforce Agent

A comprehensive Python tool for extracting, monitoring, and exporting Slack workspace data. Supports real-time event streaming, data extraction, message operations, and Notion integration.

## ✨ Features

### Data Extraction
- **Users**: Extract all user profiles, roles, and metadata
- **Channels**: Public channels, private channels, and DMs
- **Messages**: Complete history with threads and replies
- **Files**: File metadata and optional downloads
- **Reactions**: Emoji reactions on messages

### Real-time Operations
- **Socket Mode Streaming**: Live event monitoring
- **Message Sending**: Text and rich-formatted messages
- **File Uploads**: Upload files to channels
- **Reactions**: Add/remove emoji reactions
- **Auto-save**: Events automatically saved to database

### Export & Integration
- **Notion Export**: Export all Slack data to formatted Notion pages
- **SQLite Database**: Local storage for all extracted data
- **Statistics**: View counts and analytics

---

## 📋 Requirements

- Python 3.8+
- Slack workspace with admin access
- Slack App with required scopes (see Setup)

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Slack App

1. Go to [https://api.slack.com/apps](https://api.slack.com/apps)
2. Click "Create New App" → "From scratch"
3. Name your app and select workspace

**Configure OAuth Scopes** (Settings → OAuth & Permissions):
- `channels:history`
- `channels:read`
- `chat:write`
- `files:read`
- `files:write`
- `reactions:read`
- `reactions:write`
- `users:read`
- `groups:history` (for private channels)
- `im:history` (for DMs)
- `mpim:history` (for group DMs)

**Enable Socket Mode** (Settings → Socket Mode):
- Toggle "Enable Socket Mode" to ON
- Click "Generate" to create App-Level Token
- Scopes needed: `connections:write`

**Install App to Workspace**:
- Go to "Install App"
- Click "Install to Workspace"
- Authorize the app

### 3. Configure Environment

Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```bash
# Required
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token

# Optional (for advanced features)
SLACK_APP_ID=A...
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_SIGNING_SECRET=...

# Notion (for export feature)
NOTION_TOKEN=ntn_... or secret_...
NOTION_PARENT_PAGE_ID=your-page-id
```

**Where to find tokens:**
- Bot Token: Settings → OAuth & Permissions → "Bot User OAuth Token"
- App Token: Settings → Basic Information → App-Level Tokens

### 4. Initialize

```bash
python main.py init
```

This will:
- Verify Slack connection
- Initialize database
- Show workspace info

---

## 📖 Usage

### Extract Data

```bash
# Extract everything
python main.py extract-all

# Extract specific data
python main.py extract-users
python main.py extract-channels
python main.py extract-messages
python main.py extract-files

# View what's in database
python main.py stats

# List channels
python main.py list-channels
```

### Send Messages & Files

```bash
# Send message
python main.py send "#channel-name" "Your message"

# Upload file
python main.py upload "#channel-name" /path/to/file.txt

# Add reaction
python main.py react "CHANNEL_ID" "MESSAGE_TS" "thumbsup"
```

### Real-time Streaming

```bash
# Start listening for live events
python main.py stream
```

Events are automatically saved to database. Press Ctrl+C to stop.

### Export to Notion

**Setup Notion Integration:**
1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations)
2. Click "New integration"
3. Name it (e.g., "Slack Exporter")
4. Select your workspace
5. Copy the "Internal Integration Token"
6. Add to `.env` as `NOTION_TOKEN`

**Get Parent Page ID:**
1. Open the Notion page where you want exports
2. Copy page URL: `https://notion.so/Page-Name-abc123...`
3. The ID is the part after the last dash: `abc123...`
4. Add to `.env` as `NOTION_PARENT_PAGE_ID`

**Share Page:**
1. Open the parent page in Notion
2. Click ••• menu → Add connections
3. Select your integration

**Export:**
```bash
python main.py export-to-notion
```

Creates a formatted page with:
- Workspace statistics
- User list
- Channel list
- Message samples
- File metadata

---

## 🧪 Testing

### Test Slack Integration

```bash
python test_slack.py
```

Tests:
- ✅ Bot authentication
- ✅ Data extraction
- ✅ Channel operations
- ✅ Message sending/deletion
- ✅ Rich formatting
- ✅ Reactions
- ✅ Socket Mode streaming
- ✅ Database queries

**Expected:** 10/10 tests pass

### Test Notion Integration

```bash
python test_notion.py
```

Tests:
- ✅ Configuration
- ✅ API connection
- ✅ Page access
- ✅ Page creation
- ✅ Data export

**Expected:** 10/10 tests pass

---

## 📁 Project Structure

```
Workforce-agent/
├── cli/                    # CLI commands
│   ├── __init__.py
│   └── main.py            # All CLI commands
├── config.py              # Configuration
├── database/              # SQLite database
│   ├── models.py          # Data models
│   └── db_manager.py      # Database operations
├── extractor/             # Data extraction
│   ├── users.py
│   ├── channels.py
│   ├── messages.py
│   ├── files.py
│   └── coordinator.py
├── sender/                # Sending messages/files
│   ├── message_sender.py
│   ├── file_sender.py
│   └── reaction_manager.py
├── realtime/              # Real-time streaming
│   ├── event_handlers.py
│   └── socket_client.py
├── notion_export/         # Notion integration
│   ├── client.py
│   └── exporter.py
├── utils/                 # Utilities
│   ├── logger.py
│   ├── rate_limiter.py
│   └── backoff.py
├── main.py                # Entry point
├── test_slack.py          # Slack tests
├── test_notion.py         # Notion tests
├── .env.example           # Environment template
└── requirements.txt       # Dependencies
```

---

## 🗄️ Database Schema

**SQLite database at:** `data/slack_data.db`

### Tables

**workspaces**
- Workspace metadata (team name, ID)

**users**
- User profiles, roles, status
- Fields: user_id, username, real_name, email, is_bot, is_admin, etc.

**channels**
- All conversation types
- Fields: channel_id, name, is_private, is_archived, num_members, etc.

**messages**
- Complete message history
- Fields: message_id, channel_id, user_id, text, timestamp, thread_ts, etc.

**files**
- File metadata
- Fields: file_id, name, size, mimetype, url_private, local_path, etc.

**reactions**
- Emoji reactions on messages
- Fields: id, message_id, user_id, emoji, etc.

**sync_status**
- Track extraction progress
- Fields: channel_id, last_synced_ts, is_complete, etc.

---

## 🔧 Configuration

### Environment Variables

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
| `DATABASE_URL` | ⚪ | SQLite database path (default: sqlite:///data/slack_data.db) |
| `LOG_LEVEL` | ⚪ | Logging level (default: INFO) |

### Rate Limits

The agent automatically respects Slack's rate limits:
- **Tier 4 methods**: 100 req/min (conversations.list, users.list)
- **Default methods**: 50 req/min
- **conversations.history**: 1 req/min (non-Marketplace apps)

Progress bars show extraction progress. Large workspaces may take time.

---

## 💡 Common Use Cases

### 1. Archive Workspace Data

```bash
# Extract all data
python main.py extract-all

# Export to Notion for easy browsing
python main.py export-to-notion
```

### 2. Monitor Live Activity

```bash
# Start real-time monitoring
python main.py stream

# All events saved to database automatically
# Query database: python main.py stats
```

### 3. Automated Bot Actions

```bash
# Send daily updates
python main.py send "#general" "Daily update: $(date)"

# Upload reports
python main.py upload "#reports" daily_report.pdf
```

### 4. Data Analysis

```bash
# Extract all messages
python main.py extract-messages

# Query database using Python
python
>>> from database import DatabaseManager
>>> db = DatabaseManager()
>>> stats = db.get_statistics()
>>> print(f"Total messages: {stats['messages']}")
```

---

## ⚠️ Troubleshooting

### Tests Failing?

**Run tests to diagnose:**
```bash
python test_slack.py
python test_notion.py
```

### Common Issues

**1. "not_authed" or "invalid_auth"**
- Check `SLACK_BOT_TOKEN` in `.env`
- Verify token starts with `xoxb-`
- Reinstall app to workspace if needed

**2. "missing_scope" errors**
- Go to Slack App Settings → OAuth & Permissions
- Add required scopes (see Setup section)
- Reinstall app to workspace

**3. "not_in_channel" errors**
- Bot needs to be invited to channel
- In Slack: `/invite @your-bot-name`
- Or use: `python main.py list-channels` to see accessible channels

**4. Socket Mode not connecting**
- Check `SLACK_APP_TOKEN` in `.env`
- Verify Socket Mode is enabled in app settings
- Token should start with `xapp-`

**5. Notion export failing**
- Run `python test_notion.py` to diagnose
- Verify `NOTION_TOKEN` and `NOTION_PARENT_PAGE_ID` are set
- Share parent page with integration (••• menu → Add connections)

**6. Rate limit errors**
- Agent automatically handles rate limits
- Progress may be slow for large workspaces (normal)
- Wait for completion or run extraction in stages

### Enable Debug Logging

```bash
python main.py --log-level DEBUG <command>
```

---

## 🔒 Security Notes

- **Never commit `.env`** - Contains sensitive tokens
- **Bot tokens** have access to workspace data - keep secure
- **Notion tokens** can modify Notion workspace - handle carefully
- **Database** may contain sensitive data - store securely
- **File downloads** stored in `data/files/` - review permissions

---

## 📊 Performance

- **Small workspace** (<100 channels, <10K messages): ~1-5 minutes
- **Medium workspace** (100-1000 channels, 10K-100K messages): ~10-60 minutes
- **Large workspace** (>1000 channels, >100K messages): 1+ hours

Extraction speed limited by Slack API rate limits. The agent will show progress bars and wait times.

---

## 🛠️ Development

### Dependencies

```
slack-sdk>=3.21.0       # Slack API
slack-bolt>=1.18.0      # Slack Apps framework
notion-client>=2.2.1    # Notion API
sqlalchemy>=2.0.0       # Database ORM
click>=8.1.0            # CLI framework
rich>=13.9.0            # Terminal UI
python-dotenv>=1.0.0    # Environment config
tenacity>=8.2.0         # Retry logic
aiohttp>=3.8.0          # Async HTTP
```

### Run Tests

```bash
# Test Slack functionality
python test_slack.py

# Test Notion integration
python test_notion.py

# Both tests should show 10/10 passed
```

### Add New Commands

Edit `cli/main.py`:
```python
@cli.command()
def your_command():
    """Your command description."""
    # Implementation
```

---

## 📝 CLI Reference

### Core Commands

| Command | Description |
|---------|-------------|
| `init` | Initialize database and verify connection |
| `verify-credentials` | Check all Slack API credentials |
| `stats` | Show database statistics |
| `list-channels` | List all channels |

### Extraction

| Command | Description |
|---------|-------------|
| `extract-all` | Extract everything (users, channels, messages, files) |
| `extract-users` | Extract all users |
| `extract-channels` | Extract all channels |
| `extract-messages` | Extract messages from all channels |
| `extract-files` | Extract file metadata (--download to save files) |

### Communication

| Command | Description |
|---------|-------------|
| `send CHANNEL TEXT` | Send message to channel |
| `upload CHANNEL FILE` | Upload file to channel |
| `react CHANNEL TS EMOJI` | Add reaction to message |

### Real-time

| Command | Description |
|---------|-------------|
| `stream` | Start Socket Mode event streaming |

### Export

| Command | Description |
|---------|-------------|
| `export-to-notion` | Export all data to Notion page |

---

## ✅ Status

**All features tested and working:**
- ✅ Slack authentication (10/10 tests pass)
- ✅ Data extraction (all types)
- ✅ Message operations (send, delete, format)
- ✅ Real-time streaming (Socket Mode)
- ✅ Notion integration (10/10 tests pass)
- ✅ Database operations (all queries work)

**Ready for production use!**

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🤝 Support

**Run into issues?**
1. Check troubleshooting section above
2. Run `python test_slack.py` to diagnose Slack issues
3. Run `python test_notion.py` to diagnose Notion issues
4. Check logs in `logs/slack_agent.log`

**Feature requests or bugs?**
- Open an issue on GitHub
- Include test results and log output

---

## 🎉 Quick Start Summary

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your tokens

# 3. Initialize
python main.py init

# 4. Test
python test_slack.py
python test_notion.py

# 5. Use
python main.py extract-all
python main.py export-to-notion
python main.py stream
```

**That's it! You're ready to go.** 🚀
