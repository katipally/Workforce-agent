# Complete Database to Notion Export Guide

Export your ENTIRE database (all tables, all data) to a beautifully formatted Notion page.

---

## 🎯 What Gets Exported

### Slack Data (6 Tables)
- ✅ **Workspaces** - Workspace information
- ✅ **Users** - All users with details
- ✅ **Channels** - All channels (public/private)
- ✅ **Messages** - Recent messages
- ✅ **Files** - File metadata
- ✅ **Reactions** - Reaction statistics

### Gmail Data (5 Tables)
- ✅ **Accounts** - Gmail account info
- ✅ **Labels** - All labels/folders
- ✅ **Threads** - Email conversations
- ✅ **Messages** - Email messages
- ✅ **Attachments** - Email attachments

---

## 🚀 Quick Start

### 1. Make sure you have data in the database

```bash
# Extract Slack data
python main.py extract-all

# Extract Gmail data
python main.py gmail-extract --max-messages 50
```

### 2. Export everything to Notion

```bash
python main.py export-all-to-notion
```

That's it! One command exports everything.

---

## 📖 Detailed Usage

### Using Environment Variable

1. Set `NOTION_PARENT_PAGE_ID` in your `.env` file:
   ```bash
   NOTION_PARENT_PAGE_ID=your-notion-page-id-here
   ```

2. Run the export:
   ```bash
   python main.py export-all-to-notion
   ```

### Using Command Line Option

```bash
python main.py export-all-to-notion --parent-page-id YOUR_PAGE_ID
```

---

## 📊 What the Notion Page Looks Like

The exported page is organized with:

### 📑 Table of Contents
Quick navigation to all sections

### 💬 Slack Data Section
Each table gets its own heading with:
- Count of total records
- Recent/important items
- Key details for each item

**Example - Users Table:**
```
👤 Users (45)

• @john_doe
  Real Name: John Doe
  Email: john@company.com
  Bot: No | Admin

• @jane_smith
  Real Name: Jane Smith
  Email: jane@company.com
  Bot: No

... and 43 more
```

**Example - Messages Table:**
```
💬 Messages (1,234)

• Hey team, meeting at 3pm
  User: U12345
  Time: 2025-11-08 15:00

• Great idea! I'm in
  User: U67890
  Time: 2025-11-08 15:01

... and 1,232 more messages
```

### 📧 Gmail Data Section
Each Gmail table with:
- Account statistics
- Labels with message counts
- Recent threads and messages
- Attachment information

**Example - Gmail Messages:**
```
✉️ Gmail Messages (50)

• Project Update - Q4 Review
  From: manager@company.com
  Date: 2025-11-08 10:30

• Meeting Notes from Yesterday
  From: colleague@company.com
  Date: 2025-11-08 09:15 | UNREAD

... and 48 more messages
```

---

## 🔍 How to View Your Data

### Open SQLite Database
```bash
sqlite3 data/slack_data.db
```

### Check Table Counts
```sql
-- Slack tables
SELECT COUNT(*) FROM workspaces;
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM channels;
SELECT COUNT(*) FROM messages;

-- Gmail tables
SELECT COUNT(*) FROM gmail_accounts;
SELECT COUNT(*) FROM gmail_messages;
```

### Preview Data
```sql
-- View recent messages
SELECT subject, sender, received_at 
FROM gmail_messages 
ORDER BY received_at DESC 
LIMIT 10;

-- View users
SELECT username, real_name, email 
FROM users 
LIMIT 10;
```

---

## 💡 Use Cases

### 1. Complete Data Backup
Export everything to Notion for easy browsing and reference.

```bash
python main.py extract-all
python main.py gmail-extract
python main.py export-all-to-notion
```

### 2. Team Data Review
Share comprehensive workspace data with your team.

### 3. Archive and Documentation
Create timestamped snapshots of your data.

### 4. Data Analysis
Review all data in one organized location.

---

## 🎨 Features

### Smart Limits
- Shows first 30-50 items per table
- Prevents hitting Notion's block limits
- Includes "...and X more" counters

### Rich Formatting
- Emoji icons for each section
- Organized hierarchical structure
- Clean, readable layout

### Comprehensive Coverage
- ALL database tables included
- No data left behind
- Complete statistics

### Timestamps
- Each export is timestamped
- Easy to track when data was exported

---

## 📝 Example Workflow

### Daily Backup
```bash
# Extract latest data
python main.py extract-all
python main.py gmail-extract --max-messages 100

# Export to Notion
python main.py export-all-to-notion
```

### Weekly Archive
```bash
# Full export with all details
python main.py extract-all --download-files
python main.py gmail-extract --max-messages 500 --download-attachments
python main.py export-all-to-notion
```

---

## 🔧 Troubleshooting

### "Notion connection failed"
- Check `NOTION_TOKEN` in `.env`
- Verify token is valid

### "Page not found"
- Check `NOTION_PARENT_PAGE_ID` is correct
- Ensure page is shared with integration

### "No data found"
- Run extraction commands first
- Check database has data: `python main.py stats`

### "Too many blocks"
If you have massive amounts of data:
- The exporter limits items per table automatically
- Recent/important items are shown first
- Full data remains in database

---

## 🆚 Export Comparison

### `export-to-notion` (Slack only)
- Exports only Slack data
- More detailed Slack formatting
- Good for Slack-focused reviews

### `gmail-notion` (Gmail only)
- Exports only Gmail data
- Detailed email information
- Good for email reviews

### `export-all-to-notion` (Everything!)
- Exports ALL tables
- Comprehensive overview
- Perfect for complete backups
- One command for everything

---

## 📊 Expected Output

```
📊 Full Database → Notion Export
Exporting ALL tables with complete data...

✓ Notion connected

Loading data from database...
✓ Data loaded

Database Summary:

Slack Data:
  • Workspaces: 1
  • Users: 45
  • Channels: 23
  • Messages: 1,234
  • Files: 89
  • Reactions: 567

Gmail Data:
  • Accounts: 1
  • Labels: 17
  • Threads: 20
  • Messages: 50
  • Attachments: 5

Formatting data for Notion...
Created 342 blocks

Creating Notion page...

✓ Export Complete!
Page URL: https://www.notion.so/Complete-Database-Export-2025-11-08...

✓ Complete database exported!
Total blocks created: 342
```

---

## 🎯 Summary

**One command, all your data:**
```bash
python main.py export-all-to-notion
```

**Result:**
- ✅ All Slack tables exported
- ✅ All Gmail tables exported
- ✅ Organized Notion page
- ✅ Easy to browse and share
- ✅ Timestamped for reference

---

**Questions?** Check the main README or `documentation/api_guide.md`
