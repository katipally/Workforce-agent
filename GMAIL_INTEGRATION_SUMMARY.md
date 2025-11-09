# Gmail Integration Summary

## ✅ What Was Added

### 1. CLI Commands (main.py)

Three new commands added:

#### `gmail-extract` - Extract emails from Gmail
```bash
# Basic extraction
python main.py gmail-extract

# Extract from specific sender (e.g., Ivan Lee)
python main.py gmail-extract --query "from:ivanlee@example.com" --max-messages 100

# Extract with date filter
python main.py gmail-extract --query "after:2024/11/01" --max-messages 200

# Extract threads instead of individual messages
python main.py gmail-extract --extract-threads --max-threads 50

# Download attachments
python main.py gmail-extract --download-attachments
```

Options:
- `--query` - Gmail search query (e.g., "from:user@example.com")
- `--max-messages` - Maximum messages to extract (default: 100)
- `--extract-threads` - Extract as threads instead of individual messages
- `--max-threads` - Maximum threads to extract (default: 50)
- `--download-attachments` - Download email attachments

#### `gmail-notion` - Export Gmail data to Notion
```bash
# Using .env NOTION_PARENT_PAGE_ID
python main.py gmail-notion

# Or specify page ID directly
python main.py gmail-notion --parent-page-id YOUR_PAGE_ID --max-emails 100
```

Options:
- `--parent-page-id` - Notion parent page ID (or use NOTION_PARENT_PAGE_ID from .env)
- `--max-emails` - Maximum emails to include in export (default: 50)

#### `gmail-stats` - Show Gmail database statistics
```bash
python main.py gmail-stats
```

Shows:
- Account details (email, total messages, total threads)
- Labels count
- Messages count
- Threads count
- Attachments count
- Unread messages count
- Starred messages count

### 2. Documentation Folder

Created `documentation/api_guide.md` with comprehensive setup instructions for:

#### Slack API Setup
- Creating Slack app
- Configuring OAuth scopes
- Enabling Socket Mode
- Subscribing to events
- Installing app to workspace
- Getting all required tokens and credentials

#### Notion API Setup
- Creating Notion integration
- Getting integration token
- Extracting page ID from URL
- Sharing page with integration
- Testing connection

#### Gmail API Setup
- Creating Google Cloud project
- Enabling Gmail API
- Configuring OAuth consent screen
- Creating OAuth 2.0 credentials
- Downloading credentials.json
- First-time authentication flow
- Understanding quota limits

### 3. README Updates

Updated README.md with:
- Documentation section linking to `documentation/api_guide.md`
- Gmail CLI command examples
- Extract from specific sender example
- Updated quick start summary
- Updated project structure

---

## 📝 Usage Examples

### Extract emails from Ivan Lee

```bash
# Extract up to 100 emails from Ivan Lee
python main.py gmail-extract --query "from:ivanlee@example.com" --max-messages 100

# View what was extracted
python main.py gmail-stats

# Export to Notion
python main.py gmail-notion
```

### Extract recent emails with attachments

```bash
# Extract recent 50 emails and download attachments
python main.py gmail-extract --max-messages 50 --download-attachments

# View statistics
python main.py gmail-stats
```

### Extract threads (conversations)

```bash
# Extract 30 email threads
python main.py gmail-extract --extract-threads --max-threads 30

# Export to Notion
python main.py gmail-notion --max-emails 50
```

---

## 🔍 Gmail Search Query Examples

The `--query` option supports Gmail's search syntax:

```bash
# From specific sender
--query "from:ivanlee@example.com"

# Date range
--query "after:2024/11/01 before:2024/11/30"

# Has attachments
--query "has:attachment"

# Important emails
--query "is:important"

# Unread emails
--query "is:unread"

# Combine filters
--query "from:ivanlee@example.com has:attachment after:2024/11/01"

# Subject line
--query "subject:meeting"

# Multiple senders
--query "from:(ivanlee@example.com OR john@example.com)"
```

---

## 📊 Database Tables

Gmail data is stored in these tables:

- `gmail_accounts` - Account information
- `gmail_labels` - Gmail labels/folders (Inbox, Sent, etc.)
- `gmail_threads` - Email conversation threads
- `gmail_messages` - Individual email messages
- `gmail_attachments` - Email attachments metadata

---

## 🎯 Complete Workflow Example

### 1. Setup
```bash
# Install dependencies
pip install -r requirements.txt

# See documentation for API setup
cat documentation/api_guide.md
# Follow Gmail API Setup section

# Test connection (triggers OAuth)
python test_gmail.py
```

### 2. Extract Data
```bash
# Extract emails from Ivan Lee
python main.py gmail-extract --query "from:ivanlee@example.com" --max-messages 100

# View what was extracted
python main.py gmail-stats
```

### 3. Export to Notion
```bash
# Export to Notion
python main.py gmail-notion

# Opens in browser to show the created page
```

---

## 📚 Files Modified/Created

### New Files
- ✅ `gmail/__init__.py`
- ✅ `gmail/client.py` - Gmail API wrapper
- ✅ `gmail/extractor.py` - Extract emails, threads, attachments
- ✅ `gmail/exporter.py` - Export to Notion
- ✅ `test_gmail.py` - Comprehensive test suite
- ✅ `documentation/api_guide.md` - Complete API setup guide

### Modified Files
- ✅ `cli/main.py` - Added 3 Gmail CLI commands
- ✅ `database/models.py` - Added 5 Gmail database models
- ✅ `requirements.txt` - Added Gmail API dependencies
- ✅ `.env.example` - Added Gmail environment variables
- ✅ `README.md` - Updated with Gmail documentation

---

## ✨ Key Features

1. **CLI Integration**: Works just like Slack commands
2. **Smart Query Filtering**: Use Gmail search syntax
3. **Thread Support**: Extract complete conversations
4. **Attachment Download**: Save email attachments locally
5. **Notion Export**: Beautiful formatted pages
6. **Quota Optimized**: Designed for free tier limits
7. **Complete Documentation**: Step-by-step setup guide

---

**All features tested and working! ✅**
