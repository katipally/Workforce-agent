# 🤖 Workforce AI Agent

rm -rf node_modules package-lock.json
npm install

## 🔄 Complete Integration (Nov 2025)

**Pipeline → PostgreSQL → Embeddings → RAG → Chat flow is now fully automated:**
- ✅ All pipeline runs (Slack, Gmail, Notion) **automatically generate embeddings**
- ✅ Data synced to RAG in real-time (no manual steps)
- ✅ Idempotent updates (no duplicates, smart upserts)
- ✅ Works **with or without pgvector** (JSON fallback)
- ✅ All chat endpoints unified through AI Brain
- ✅ Projects tab connected to RAG for intelligent queries

---

## ✨ What Can It Do?

### 🚀 **50+ Powerful Tools Across 3 Platforms** (November 2025 Update)

The AI agent has access to **dozens of comprehensive tools** with all major API features including **cross-platform project tracking**:

### 📱 **Slack (30+ Tools)** ✨ EXPANDED

**Messages & Communication:**
- List all channels (names, IDs, members, privacy)
- Get ALL messages from any channel
- Send messages to channels
- Update/edit existing messages
- Delete messages
- Search messages by keyword
- Summarize channel activity
- Get thread replies

**File Management:**
- Upload files to channels
- Share files with comments

**Message Organization:**
- Pin important messages
- Unpin messages
- Get all pinned messages in channel
- Add/remove emoji reactions

**Channel Management:**
- Create new channels (public/private)
- Archive channels
- Rename channels
- Set channel topic/purpose
- Invite users to channels
- Remove users from channels
- List channel members

**User Management:**
- List all workspace users
- Get user information (name, email, title, timezone)
- Check user presence status

### 📧 **Gmail (22+ Tools)** ✨ EXPANDED + THREAD SUPPORT

**🎯 COMPLETE Thread Support (NEW!):**
- **Get COMPLETE email threads** - Retrieves ALL messages (no limit!)
  - Perfect for long company email chains with 50+ messages
  - Full body content for every message in thread
  - Complete thread history and context
- **Search email threads** - Find conversations, not just messages
- **Thread summaries** - See message count and participants

**Email Reading & Search:**
- **Get FULL email content** (complete body, not snippets!)
- Get emails from specific senders
- Find emails by subject keywords
- **Advanced search with ALL Gmail operators:**
  - `from:`, `to:`, `subject:`, `has:attachment`
  - `is:unread`, `is:starred`, `is:important`
  - `label:`, `after:`, `before:`, `filename:`
  - `larger:`, `smaller:` (size filters)
- **Get exact unread email count**
- Search all emails (basic keyword search)

**Email Management:**
- Send emails with full formatting
- List all labels/folders
- Mark emails as read/unread
- Archive emails (remove from inbox)
- Add labels to emails
- Get complete email threads
- Filter emails by labels
- *(Plus 6 more - see [TOOLS_CATALOG.md](./TOOLS_CATALOG.md))*

### 📝 **Notion (15+ Tools)** ✨ EXPANDED

**Page Operations:**
- Create new pages (markdown supported)
- **Update existing pages** (titles, properties)
- **Append content to existing pages**
- Read full page content with blocks
- Delete pages

**Workspace Features:**
- **Search entire workspace** (pages and databases)
- List all pages in workspace
- Get page metadata and properties
- Query databases with filters
- Access workspace-level information

**Content Management:**
- Create and manage blocks
- Add comments to pages
- Update page properties
- Organize with databases

### 🔍 **Workspace Search (1 Tool)**
- **Semantic Search**: AI-powered search across ALL platforms simultaneously using sentence-transformers vector embeddings

### 🎯 **Project Tracking & Utilities (6 Tools)** ✨ NEW - Nov 2025

**Cross-Platform Project Management:**
- **Track Projects**: Automatically aggregate project updates from Slack, Gmail, and Notion
  - Searches all platforms for project-related content
  - Identifies key points, action items, and blockers
  - Calculates progress percentage
  - Shows team member activity
- **Generate Reports**: Create comprehensive stakeholder-ready project reports
  - Formatted ASCII reports with progress bars
  - Statistics from all sources
  - Organized sections (highlights, action items, blockers)
- **Update Notion Pages**: Automatically update existing Notion pages with project status
  - **UPDATES existing pages** (doesn't create new ones)
  - Formatted markdown with timestamps
  - Appends latest project summary
  - Includes team members and progress

**Cross-Platform Utilities:**
- **Search All Platforms**: Search Slack, Gmail, and Notion simultaneously
  - Unified results from all sources
  - One query, all platforms
- **Team Activity Summary**: See what any team member is working on
  - Shows their Slack messages, emails, and Notion updates
  - Cross-platform view of activity
- **Slack Channel Analytics**: Analyze channel engagement and patterns
  - Message counts, active users, engagement metrics
  - Sentiment analysis (positive, negative, questions)
  - Activity trends and insights

**Example Commands:**
```
"Track the Q4 Dashboard project for the last 7 days"
"Generate a project report for Mobile App Redesign"
"Update Notion page abc123 with Agent Project status"
"Search all platforms for 'authentication'"
"What is Ivan working on?"
"Analyze the #engineering Slack channel"
```

### 🎯 **Smart Features**
- **Multi-Tool Workflows**: AI chains multiple actions automatically
  - Example: "Get emails from john@company.com and save to Notion" → AI does both steps
- **Conversation History**: AI remembers previous messages in the session  
- **Natural Language**: Just type what you want in plain English
- **Live Data**: Always fetches fresh data from APIs
- **Streaming Responses**: See results as they're generated
- **Session Management**: Create multiple conversations, switch between them - **FIXED Nov 2025!**
- **File Upload**: Drag & drop files, image previews, multi-file support - **NEW Nov 2025!**
- **Quick Actions**: One-click templates for common tasks
- **Workflow Templates**: Pre-built multi-step automations
- **Single Source of Truth**: All data synced to PostgreSQL with pgvector

### 🆕 **November 2025 Updates**
- ✨ **gpt-5-nano**: Upgraded to latest OpenAI lightweight reasoning model (optimized for speed & cost)
- 🎯 **PROJECT TRACKING**: Cross-platform project management! (**6 NEW TOOLS**)
  - Track projects across Slack, Gmail, and Notion automatically
  - Generate stakeholder-ready reports
  - Auto-update Notion pages with project status
  - Team activity summaries
  - Channel analytics
  - Cross-platform search
- 🛠️ **26+ NEW TOOLS**: Comprehensive API coverage (**50+ total tools active**)
  - **Slack**: File uploads, pins, channel management, user management
  - **Gmail**: Full email bodies, advanced search, unread count, all operators
  - **Notion**: Update pages, append content, workspace search
- 🎨 **Fixed Chat History**: Sessions now persist properly, switch without losing messages
- 📎 **File Upload**: Drag & drop interface with image previews (client-side validation)
- 🗑️ **Removed Right Sidebar**: Cleaner, more focused UI
- 🔧 **Improved RAG Reliability**: Vector search now uses sentence-transformers embeddings with correct dimensions
- ✅ **Extensive Test Coverage**: Core tools and integrations covered by Slack, Gmail, Notion, and project test suites

**📖 [View Complete Tool Catalog](./TOOLS_CATALOG.md)** - Detailed documentation of all 50+ tools

---

## 🚀 Quick Setup

### **Prerequisites**

**Windows:**
- Python 3.10 or higher ([Download](https://www.python.org/downloads/))
- Node.js 18 or higher ([Download](https://nodejs.org/))
- PostgreSQL 14+ ([Download](https://www.postgresql.org/download/windows/))

**Mac:**
```bash
# Install Homebrew if you don't have it
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python
brew install python@3.12

# Install Node.js
brew install node

# Install PostgreSQL
brew install postgresql@14
brew services start postgresql@14
```

---

## 📦 Installation

### **1. Clone Repository**

**Windows (Command Prompt):**
```cmd
git clone https://github.com/yourusername/Workforce-agent.git
cd Workforce-agent
```

**Mac (Terminal):**
```bash
git clone https://github.com/yourusername/Workforce-agent.git
cd Workforce-agent
```

### **2. Install Python Dependencies**

**Windows:**
```cmd
pip install -r requirements.txt
```

**Mac:**
```bash
pip3 install -r requirements.txt
```

### **3. Install Frontend Dependencies**

**Both Windows & Mac:**
```bash
cd frontend
npm install
cd ..
```

### **4. Create Database**

**Windows (Command Prompt):**
```cmd
createdb workforce_agent
```

**Mac (Terminal):**
```bash
createdb workforce_agent
```

### **5. Configure API Keys**

Copy the example environment file:

**Windows:**
```cmd
copy .env.example .env
```

**Mac:**
```bash
cp .env.example .env
```

Then edit `.env` file and add your API keys:

```bash
# Required
OPENAI_API_KEY=sk-your-openai-key-here
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_APP_TOKEN=xapp-your-slack-app-token

# Notion (optional)
NOTION_TOKEN=secret_your-notion-key
NOTION_PARENT_PAGE_ID=your-page-id

# Google OAuth (for login + per-user Gmail access)
GOOGLE_CLIENT_ID=your-google-oauth-client-id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_OAUTH_REDIRECT_BASE=http://localhost:8000
FRONTEND_BASE_URL=http://localhost:5173
SESSION_SECRET=change-me-to-a-long-random-string

# Database
DATABASE_URL=postgresql://localhost:5432/workforce_agent
```

---

## 🔑 Getting API Keys

### **OpenAI (Required)**
1. Go to https://platform.openai.com/api-keys
2. Click "Create new secret key"
3. Copy the key (starts with `sk-`)
4. Add to `.env` as `OPENAI_API_KEY`

### **Slack (Required for Slack features)**
1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name it "Workforce Agent", select your workspace
4. Go to "OAuth & Permissions"
   - Add scopes: `channels:history`, `channels:read`, `chat:write`, `users:read`
5. Go to "Socket Mode" → Enable it
   - Generate app token (starts with `xapp-`)
   - Add to `.env` as `SLACK_APP_TOKEN`
6. Install app to workspace
   - Copy Bot User OAuth Token (starts with `xoxb-`)
   - Add to `.env` as `SLACK_BOT_TOKEN`

**Full setup guide:** See `Documentation/api_guide.md`

### **Gmail (Optional, via Google OAuth)**
1. Go to https://console.cloud.google.com/
2. Create a project (or use an existing one)
3. Enable **Gmail API**
4. Create OAuth 2.0 **Web application** client
5. Add authorized redirect URI: `http://localhost:8000/auth/google/callback`
6. Copy the client ID and secret into `.env` as `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`

After configuring, start the backend and frontend, open the app, and
click "Continue with Google" to sign in and grant Gmail access.

**Full setup guide:** See `Documentation/Auth_plan.md`

### **Notion (Optional)**
1. Go to https://www.notion.so/my-integrations
2. Create new integration
3. Copy token (starts with `secret_`)
4. Share a Notion page with the integration
5. Copy page ID from URL
6. Add both to `.env`

**Full setup guide:** See `Documentation/api_guide.md`

---

## ▶️ Starting the Agent

### **Option 1: Use Startup Script (Recommended)**

**Mac/Linux:**
```bash
./START_SERVERS.sh
```

**Windows:**
```cmd
# Start backend
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

# In another terminal, start frontend
cd frontend
npm run dev
```

### **Option 2: Manual Start**

**Terminal 1 - Backend:**
```bash
cd backend
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd frontend
npm run dev
```

### **Access the Agent**

Open your browser to: **http://localhost:5173**

---

## 📊 Pipelines View (Slack, Gmail, Notion)

Once the backend and frontend are running, you can explore structured data via the **Pipelines** tab in the UI:

- **Where to find it:**
  - Open the web app at `http://localhost:5173`.
  - Switch from the chat view to the **Pipelines** view.
  - Use the small source switcher in the bottom-left to toggle between **Slack**, **Gmail**, and **Notion** pipelines.

- **Slack Pipeline:**
  - Click **Run Slack Pipeline** to sync your Slack workspace (users, channels, messages, files) into PostgreSQL.
  - Left panel shows channels with message counts and basic stats.
  - Selecting a channel loads recent messages, grouped by thread with root messages and replies.

- **Gmail Pipeline:**
  - Choose a Gmail **label** from the dropdown (e.g. `INBOX`, `Datasaur`, etc.).
  - Click **Run Gmail Pipeline** to incrementally sync new emails for that label into the database.
  - The **Gmail Messages** panel shows an accordion list:
    - Header: `from -> recipients · subject` with sent date.
    - Body: full HTML or text content when expanded.

- **Notion Pipeline:**
  - Click **Run Notion Pipeline** to sync pages and databases visible to your integration using `NOTION_TOKEN`.
  - The **Notion Pages** view shows your workspace name and a nested accordion of pages and subpages.
  - Expanding a page shows:
    - Page properties (Gmail-like info panel).
    - Actual page content (text blocks) and any file/image/pdf/video attachments.

---

## 💬 Example Queries

Try these in the chat interface:

### **Slack**
```
"Get all slack channel names"
"Show me messages from #social"
"Send a message to #team saying 'Hello everyone'"
"Get user info for U12345678"
"Summarize what happened in #engineering today"
```

### **Gmail**
```
"Get emails from john@company.com"
"Find emails with subject 'project'"
"Show me unread emails"
```

### **Notion**
```
"Create a Notion page titled 'Meeting Notes'"
"List all my Notion pages"
```

### **Multi-Tool (Advanced)**
```
"Get messages from #social and save them to Notion"
"Find emails about 'budget' and summarize them"
"Get all channels and list their members"
```

---

## 🛠️ Troubleshooting

### **Backend won't start**
- Check Python version: `python --version` (needs 3.10+)
- Install dependencies: `pip install -r requirements.txt`
- Check database: `psql -l` (should see `workforce_agent`)

### **Frontend won't start**
- Check Node version: `node --version` (needs 18+)
- Install dependencies: `cd frontend && npm install`
- Check port 5173 is free: `lsof -i:5173`

### **"Slack API not configured" error**
- Check `.env` file has `SLACK_BOT_TOKEN` starting with `xoxb-`
- Check `SLACK_APP_TOKEN` starting with `xapp-`
- Restart backend after adding keys

### **"Gmail not authenticated" error**
- Run first-time authentication: `cd backend && python -m core.gmail.extractor`
- Browser should open for OAuth
- After authentication, restart backend

### **Port already in use**

**Windows:**
```cmd
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

**Mac:**
```bash
lsof -ti:8000 | xargs kill -9
lsof -ti:5173 | xargs kill -9
```

---

## 📁 Project Structure

```
Workforce-agent/
├── backend/
│   ├── agent/                      # AI brain, RAG engine & tools
│   │   ├── ai_brain.py             # gpt-5-nano + multi-tool logic
│   │   ├── hybrid_rag.py           # Hybrid RAG over Slack, Gmail, Notion
│   │   ├── sentence_transformer_engine.py  # sentence-transformers embedding & reranker
│   │   └── langchain_tools.py      # Slack/Gmail/Notion/project tools
│   ├── api/                        # FastAPI server
│   │   └── main.py                 # REST & WebSocket endpoints
│   ├── core/                       # Config, DB models, and API integrations
│   │   ├── config.py               # Config & env loading
│   │   ├── database/               # PostgreSQL models
│   │   ├── slack/                  # Slack API
│   │   ├── gmail/                  # Gmail API
│   │   ├── notion_export/          # Notion API
│   │   └── cli/                    # CLI used by top-level main.py
│   ├── scripts/                    # Helper & maintenance scripts
│   ├── test_all_apis.py            # API permission test script
│   ├── test_comprehensive_tools.py # All tools test suite
│   └── test_new_tools.py           # New tools test suite
├── test-files/                     # Legacy end-to-end Slack/Gmail/Notion tests
├── frontend/                       # React UI
│   └── src/
│       └── components/             # Chat interface & pipelines views
├── data/                           # Local data (Gmail token, exports, files)
├── Documentation/                  # Full API setup guides
├── .env                            # Your API keys (create this)
├── .env.example                    # Template
├── START_SERVERS.sh                # Mac/Linux startup
└── STOP_SERVERS.sh                 # Shutdown script
```

---

## 📚 Documentation

- **📖 [Complete Tool Catalog](./TOOLS_CATALOG.md)** - All Slack, Gmail, Notion, workspace, and project tools with examples
- **🔑 [API Setup Guide](./Documentation/api_guide.md)** - Step-by-step API configuration
- **⚡ [API Endpoints](http://localhost:8000/docs)** - Interactive API docs (when running)

---

## 🆘 Getting Help

1. **Check logs:**
   - Backend: `tail -f logs/backend.log`
   - Frontend: Check browser console (F12)

2. **Test API connection:**
   ```bash
   curl http://localhost:8000/health
   ```

3. **Restart everything:**
   - Stop: `./STOP_SERVERS.sh` (Mac) or close terminals (Windows)
   - Start: `./START_SERVERS.sh` (Mac) or manual start (Windows)

---

## 🎯 What Makes This Special

- **Latest AI Model**: gpt-5-nano (Nov 2025) - fast, cost-efficient reasoning with tools
- **Single Source of Truth**: PostgreSQL with pgvector stores all cross-platform data
- **Hybrid Interface**: Chatbot UX + AI agent automation in one
- **Smart AI**: Automatically selects and chains tools
- **RAG-Powered**: Semantic search across all platforms using sentence-transformers embeddings (dimension depends on configured model)
- **Multi-Tool Workflows**: Complex automations handled automatically
- **Natural Language**: No commands to memorize
- **Production Ready**: Robust error handling, auto-reconnection, streaming responses

---

## 📝 License

MIT License - See LICENSE file

---

**Made with ❤️ | Built for productivity | Powered by gpt-5-nano (Nov 2025)**
