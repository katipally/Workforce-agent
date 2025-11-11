# 🤖 Workforce AI Agent

---

## ✨ What Can It Do?

### 📱 **Slack (10 features)**
- Get all channel names
- Read messages from any channel  
- Send messages to channels
- Get user information (email, timezone)
- Get thread replies
- Add reactions to messages
- Set channel topics
- Search messages
- Summarize channel activity

### 📧 **Gmail (9 features)**
- Get emails from specific people
- Find emails by subject
- Send emails
- Mark emails as read
- Archive emails
- Add labels to emails
- Get email threads (conversations)
- List all labels/folders
- Search emails

### 📝 **Notion (5 features)**
- Create new pages
- Read page content
- Update page titles
- List all pages
- Search Notion content

### 🎯 **Smart Features**
- **Multi-Tool Workflows**: AI chains multiple actions automatically
  - Example: "Get messages from #team and save to Notion" → AI does both steps
- **Natural Language**: Just type what you want in plain English
- **Live Data**: Always fetches fresh data from APIs
- **Streaming Responses**: See results as they're generated

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

# Optional (add if you want Gmail/Notion)
GMAIL_CREDENTIALS_PATH=backend/core/credentials/gmail/credentials.json
NOTION_API_KEY=secret_your-notion-key
NOTION_PARENT_PAGE_ID=your-page-id

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

### **Gmail (Optional)**
1. Go to https://console.cloud.google.com/
2. Create new project
3. Enable Gmail API
4. Create OAuth credentials (Desktop app)
5. Download `credentials.json`
6. Place in `backend/core/credentials/gmail/`

**Full setup guide:** See `Documentation/api_guide.md`

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
│   ├── agent/              # AI brain & tools
│   │   ├── ai_brain.py     # GPT-4 + multi-tool logic
│   │   └── langchain_tools.py  # 26 API tools
│   ├── api/                # FastAPI server
│   │   └── main.py         # WebSocket endpoints
│   ├── core/               # API integrations
│   │   ├── slack/          # Slack API
│   │   ├── gmail/          # Gmail API
│   │   └── notion_export/  # Notion API
│   └── database/           # PostgreSQL models
├── frontend/               # React UI
│   └── src/
│       └── components/     # Chat interface
├── Documentation/          # Full API setup guides
├── .env                    # Your API keys (create this)
├── .env.example            # Template
├── START_SERVERS.sh        # Mac/Linux startup
└── STOP_SERVERS.sh         # Shutdown script
```

---

## 📚 Documentation

- **Full API Setup Guide:** `Documentation/api_guide.md`
- **Slack API Details:** `Documentation/SLACK_API_GUIDE.md`
- **API Endpoints:** http://localhost:8000/docs (when running)

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

- **No Database Setup Needed**: Just add API keys and go
- **Always Fresh Data**: Calls APIs in real-time
- **Smart AI**: GPT-4 decides which tools to use
- **Multi-Tool Workflows**: Chains actions automatically
- **Natural Language**: No commands to memorize
- **Production Ready**: Robust error handling, auto-reconnection

---

## 📝 License

MIT License - See LICENSE file

---

**Made with ❤️ | Built for productivity | Powered by GPT-4**
