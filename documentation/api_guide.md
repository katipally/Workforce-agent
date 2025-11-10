# API Setup Guide

Complete guide for setting up Slack, Notion, and Gmail APIs for the Workspace Agent.

---

## Table of Contents

1. [Slack API Setup](#slack-api-setup)
2. [Notion API Setup](#notion-api-setup)
3. [Gmail API Setup](#gmail-api-setup)
4. [Quick Reference](#quick-reference)

---

## Slack API Setup

### Prerequisites
- Slack workspace with admin access
- Ability to install apps in your workspace

### Step 1: Create Slack App

1. **Go to Slack API Portal**
   - Visit: https://api.slack.com/apps
   - Sign in with your Slack workspace credentials

2. **Create New App**
   - Click **"Create New App"**
   - Select **"From scratch"**
   - **App Name**: Enter a name (e.g., "Workforce Agent")
   - **Pick a workspace**: Select your workspace
   - Click **"Create App"**

### Step 2: Configure OAuth Scopes

OAuth scopes define what your app can do. We need comprehensive access.

1. **Navigate to OAuth & Permissions**
   - Left sidebar → **"OAuth & Permissions"**

2. **Add Bot Token Scopes**
   Scroll to **"Scopes"** → **"Bot Token Scopes"** → Click **"Add an OAuth Scope"**
   
   Add these scopes:
   
   **User & Team Info:**
   - `users:read` - View users in workspace
   - `users:read.email` - View email addresses
   - `team:read` - View workspace name and domain
   
   **Channels:**
   - `channels:read` - View public channels
   - `channels:history` - View messages in public channels
   - `channels:manage` - Manage public channels
   - `groups:read` - View private channels
   - `groups:history` - View messages in private channels
   - `im:read` - View direct messages
   - `im:history` - View DM message history
   - `mpim:read` - View group DMs
   - `mpim:history` - View group DM history
   
   **Messages:**
   - `chat:write` - Send messages
   - `chat:write.public` - Send messages to public channels (without joining)
   
   **Files:**
   - `files:read` - View files
   - `files:write` - Upload files
   
   **Reactions:**
   - `reactions:read` - View reactions
   - `reactions:write` - Add/remove reactions

3. **Save Changes**

### Step 3: Enable Socket Mode

Socket Mode allows real-time event streaming.

1. **Navigate to Socket Mode**
   - Left sidebar → **"Socket Mode"**

2. **Enable Socket Mode**
   - Toggle **"Enable Socket Mode"** to ON
   - Click **"Generate"** when prompted for app-level token
   - **Token Name**: "Socket Mode Token"
   - Click **"Generate"**
   - **IMPORTANT**: Copy the token (starts with `xapp-`)
   - Store it as `SLACK_APP_TOKEN` in your `.env`

### Step 4: Subscribe to Events

1. **Navigate to Event Subscriptions**
   - Left sidebar → **"Event Subscriptions"**

2. **Enable Events**
   - Toggle **"Enable Events"** to ON

3. **Subscribe to Bot Events**
   Scroll to **"Subscribe to bot events"** → Click **"Add Bot User Event"**
   
   Add these events:
   - `message.channels` - Messages in public channels
   - `message.groups` - Messages in private channels
   - `message.im` - Direct messages
   - `message.mpim` - Group DMs
   - `reaction_added` - Reactions added
   - `reaction_removed` - Reactions removed
   - `file_shared` - Files shared
   - `member_joined_channel` - User joins channel
   - `member_left_channel` - User leaves channel

4. **Save Changes**
   - Click **"Save Changes"** at bottom

### Step 5: Install App to Workspace

1. **Navigate to Install App**
   - Left sidebar → **"Install App"**

2. **Install to Workspace**
   - Click **"Install to Workspace"**
   - Review permissions
   - Click **"Allow"**

3. **Copy Bot Token**
   - After installation, you'll see **"Bot User OAuth Token"**
   - Starts with `xoxb-`
   - **IMPORTANT**: Copy this token
   - Store it as `SLACK_BOT_TOKEN` in your `.env`

### Step 6: Get Additional App Credentials

1. **Navigate to Basic Information**
   - Left sidebar → **"Basic Information"**

2. **Copy App Credentials**
   - **App ID**: Copy and store as `SLACK_APP_ID`
   - Scroll to **"App Credentials"**
   - **Client ID**: Store as `SLACK_CLIENT_ID`
   - **Client Secret**: Click "Show" → Copy → Store as `SLACK_CLIENT_SECRET`
   - **Signing Secret**: Click "Show" → Copy → Store as `SLACK_SIGNING_SECRET`
   - **Verification Token**: Copy → Store as `SLACK_VERIFICATION_TOKEN`

### Step 7: Configure Environment Variables

Add to `.env`:
```bash
# Slack API Tokens (Required)
SLACK_BOT_TOKEN=xoxb-your-bot-token-here
SLACK_APP_TOKEN=xapp-your-app-token-here

# Slack App Credentials (Optional but recommended)
SLACK_APP_ID=A09R6CU0295
SLACK_CLIENT_ID=9884788367585.9856436002311
SLACK_CLIENT_SECRET=your-client-secret-here
SLACK_SIGNING_SECRET=your-signing-secret-here
SLACK_VERIFICATION_TOKEN=your-verification-token-here
```

### Step 8: Test Connection

```bash
python main.py init
```

Expected output:
```
✓ Connected to Slack
  Workspace: Your Workspace Name
  User: your_bot_name
  Team ID: T12345678
  Bot User ID: U12345678
✓ Database initialized
Initialization complete!
```

### Slack API Rate Limits

- **Tier 1** (most methods): 1 request/minute
- **Tier 2**: 20 requests/minute
- **Tier 3**: 50 requests/minute
- **Tier 4** (lists): 100 requests/minute

The agent automatically handles rate limiting with exponential backoff.

---

## Notion API Setup

### Prerequisites
- Notion account (free or paid)
- Notion workspace

### Step 1: Create Notion Integration

1. **Go to Notion Integrations**
   - Visit: https://www.notion.so/my-integrations
   - Sign in to your Notion account

2. **Create New Integration**
   - Click **"+ New integration"**
   - **Name**: "Workspace Agent" (or any name)
   - **Associated workspace**: Select your workspace
   - **Type**: Leave as "Internal integration"
   - Click **"Submit"**

3. **Copy Integration Token**
   - After creation, you'll see **"Internal Integration Token"**
   - Starts with `secret_` or `ntn_`
   - Click **"Show"** → **"Copy"**
   - Store it as `NOTION_TOKEN` in your `.env`

### Step 2: Get Parent Page ID

The parent page is where exported data will be created as child pages.

1. **Open Notion**
   - Go to your Notion workspace
   - Create or open a page where you want exports

2. **Copy Page URL**
   - Click **"Share"** → **"Copy link"**
   - URL looks like: `https://www.notion.so/Page-Name-abc123def456...`

3. **Extract Page ID**
   - The page ID is the part after the last dash
   - Example: `https://www.notion.so/My-Page-1234567890abcdef1234567890abcdef`
   - Page ID: `1234567890abcdef1234567890abcdef`
   
   **OR if URL has dashes in ID:**
   - Example: `https://www.notion.so/My-Page-12345678-90ab-cdef-1234-567890abcdef`
   - Page ID: `1234567890abcdef1234567890abcdef` (without dashes)
   - Or use the full ID with dashes, the code normalizes it

4. **Store Page ID**
   - Copy the ID
   - Store it as `NOTION_PARENT_PAGE_ID` in your `.env`

### Step 3: Share Page with Integration

This step is CRITICAL - without it, the integration cannot access the page.

1. **Open the Parent Page in Notion**

2. **Share with Integration**
   - Click **"•••"** (three dots) menu at top right
   - Hover over **"Connections"**
   - Click **"Add connections"**
   - Search for your integration name (e.g., "Workspace Agent")
   - Click on it to add

3. **Verify Connection**
   - You should see your integration listed under connections
   - Icon appears at top of page

### Step 4: Configure Environment Variables

Add to `.env`:
```bash
# Notion API
NOTION_TOKEN=secret_your-notion-token-here
NOTION_PARENT_PAGE_ID=your-parent-page-id-here
```

### Step 5: Test Connection

```bash
python test_notion.py
```

Expected: 10/10 tests pass ✅

### Notion API Rate Limits

- **Rate limit**: 3 requests per second per integration
- **Burst allowance**: Short bursts are allowed
- **Block limit**: Maximum 100 blocks per request

The agent automatically handles these limits.

---

## Gmail API Setup

### Prerequisites
- Google account with Gmail
- Access to Google Cloud Console

### Step 1: Create Google Cloud Project

1. **Go to Google Cloud Console**
   - Visit: https://console.cloud.google.com/
   - Sign in with your Google account

2. **Create New Project**
   - Click project dropdown at top (says "Select a project")
   - Click **"NEW PROJECT"**
   - **Project name**: "Gmail Extractor" (or any name)
   - **Organization**: Leave as "No organization" (unless you have one)
   - Click **"CREATE"**
   - Wait ~10 seconds for project creation

3. **Select Your Project**
   - Ensure your new project is selected in the dropdown

### Step 2: Enable Gmail API

1. **Open API Library**
   - Left sidebar → **"APIs & Services"** → **"Library"**

2. **Search for Gmail API**
   - In search box, type: "Gmail API"
   - Click on **"Gmail API"** in results

3. **Enable the API**
   - Click blue **"ENABLE"** button
   - Wait for confirmation (few seconds)

### Step 3: Configure OAuth Consent Screen

Before creating credentials, you must configure the consent screen.

1. **Navigate to OAuth Consent Screen**
   - Left sidebar → **"APIs & Services"** → **"OAuth consent screen"**

2. **Choose User Type**
   - Select **"External"** (unless you have Google Workspace)
   - Click **"CREATE"**

3. **Fill App Information (Page 1)**
   - **App name**: `Gmail Extractor` (or your preferred name)
   - **User support email**: Select your email from dropdown
   - **App logo**: Skip (optional)
   - **App domain**: Skip (optional)
   - **Authorized domains**: Skip
   - **Developer contact information**: Enter your email address
   - Click **"SAVE AND CONTINUE"**

4. **Scopes (Page 2)**
   - Click **"SAVE AND CONTINUE"** (don't add scopes here, we'll specify in code)

5. **Test Users (Page 3)**
   - Click **"+ ADD USERS"**
   - Enter your Gmail address (the one you want to access)
   - Click **"ADD"**
   - Click **"SAVE AND CONTINUE"**

6. **Summary (Page 4)**
   - Review your settings
   - Click **"BACK TO DASHBOARD"**

### Step 4: Create OAuth 2.0 Credentials

1. **Navigate to Credentials**
   - Left sidebar → **"APIs & Services"** → **"Credentials"**

2. **Create Credentials**
   - Click **"+ CREATE CREDENTIALS"** at top
   - Select **"OAuth client ID"**

3. **Configure OAuth Client**
   - **Application type**: Select **"Desktop app"**
   - **Name**: `Gmail Desktop Client` (or any name)
   - Click **"CREATE"**

4. **Download Credentials**
   - A popup appears: "OAuth client created"
   - Click **"DOWNLOAD JSON"** button (or download icon)
   - Save the file

5. **Rename and Move File**
   - Rename downloaded file to: `credentials.json`
   - Move it to your project root directory:
   ```
   Workforce-agent/
   ├── credentials.json  ← Place here
   ├── gmail/
   ├── main.py
   └── ...
   ```

### Step 5: Configure Environment Variables

Add to `.env`:
```bash
# Gmail API
GMAIL_CREDENTIALS_FILE=credentials.json
GMAIL_TOKEN_FILE=data/gmail_token.pickle
```

### Step 6: First-Time Authentication

This triggers the OAuth flow and saves your token.

```bash
python test_gmail.py
```

**What happens:**
1. A browser window opens automatically
2. Google asks you to sign in (if not already signed in)
3. You see a warning: **"Google hasn't verified this app"**
   - This is NORMAL for apps in testing mode
   - Click **"Advanced"**
   - Click **"Go to Gmail Extractor (unsafe)"**
4. Google shows permissions request:
   - "Read, compose, send, and permanently delete all your email from Gmail"
   - Click **"Continue"** or **"Allow"**
5. Browser shows: "The authentication flow has completed. You may close this window."
6. Token saved to `data/gmail_token.pickle`

**IMPORTANT**: You only do this OAuth flow ONCE. The token is saved and automatically refreshed.

### Step 7: Test Connection

```bash
python test_gmail.py
```

Expected: 10/10 tests pass ✅

### Gmail API Quota Limits (Free Tier)

**Daily Limits:**
- **1 billion quota units per day** (project-wide)
- **250 units per second** (per user)

**Quota Costs per Operation:**
- `messages.list`: 5 units
- `messages.get`: 5 units
- `messages.attachments.get`: 5 units
- `threads.list`: 5 units
- `threads.get`: 5 units
- `labels.list`: 1 unit
- `users.getProfile`: 1 unit

**Real-World Examples:**
- Extract 100 emails: 500 units (0.00005% of daily limit)
- Extract 1,000 emails: 5,000 units
- Extract 10,000 emails: 50,000 units
- **Maximum per day**: ~200,000 emails

**Best Practices:**
- Start with small extractions (50-100 emails)
- Use Gmail search queries to filter
- Exclude spam/trash (saves quota)
- Monitor usage in Google Cloud Console

### Monitoring API Usage

1. **Go to Google Cloud Console**
   - Visit: https://console.cloud.google.com/

2. **View API Usage**
   - Left sidebar → **"APIs & Services"** → **"Dashboard"**
   - Select your project
   - View quota usage graphs

---

## Quick Reference

### Required Tokens

| Service | Variable | Format | Where to Get |
|---------|----------|--------|--------------|
| Slack | `SLACK_BOT_TOKEN` | `xoxb-...` | Slack App → Install App |
| Slack | `SLACK_APP_TOKEN` | `xapp-...` | Slack App → Socket Mode |
| Notion | `NOTION_TOKEN` | `secret_...` or `ntn_...` | Notion → My Integrations |
| Gmail | `credentials.json` | JSON file | Google Cloud Console → Credentials |

### Setup Summary

**Slack:**
1. Create app at https://api.slack.com/apps
2. Add OAuth scopes
3. Enable Socket Mode → Get app token
4. Install app → Get bot token
5. Add tokens to `.env`

**Notion:**
1. Create integration at https://www.notion.so/my-integrations
2. Copy integration token
3. Get parent page ID from URL
4. Share page with integration
5. Add token and page ID to `.env`

**Gmail:**
1. Create project at https://console.cloud.google.com/
2. Enable Gmail API
3. Configure OAuth consent screen
4. Create OAuth credentials (Desktop app)
5. Download `credentials.json`
6. Run `python test_gmail.py` (OAuth flow)

### Test Commands

```bash
# Slack
python main.py init
python test_slack.py

# Notion
python test_notion.py

# Gmail
python test_gmail.py
```

### Common Issues

**Slack:**
- ❌ `invalid_auth`: Check bot token starts with `xoxb-`
- ❌ `missing_scope`: Add required OAuth scope in Slack app settings
- ❌ Socket Mode error: Ensure app token starts with `xapp-`

**Notion:**
- ❌ `unauthorized`: Page not shared with integration
- ❌ `validation_error`: Invalid page ID format
- ❌ `object_not_found`: Page ID doesn't exist or no access

**Gmail:**
- ❌ `credentials.json not found`: Download from Google Cloud Console
- ❌ OAuth warning: Normal for testing - click "Advanced" → "Go to app"
- ❌ `insufficient_permissions`: Re-run OAuth flow
- ❌ `quota_exceeded`: Check usage in Google Cloud Console

### Security Best Practices

1. **Never commit secrets to git**
   - Add `.env` to `.gitignore`
   - Add `credentials.json` to `.gitignore`
   - Add `*.pickle` to `.gitignore`

2. **Token storage**
   - Store tokens in `.env` file only
   - Use environment variables in production
   - Rotate tokens periodically

3. **Access control**
   - Use minimum required scopes
   - Test with personal workspace first
   - Review app permissions regularly

4. **Monitoring**
   - Check API usage regularly
   - Set up quota alerts in Google Cloud
   - Monitor Slack app activity

---

## Support & Resources

### Official Documentation

**Slack:**
- API Docs: https://api.slack.com/
- Scopes: https://api.slack.com/scopes
- Rate Limits: https://api.slack.com/docs/rate-limits

**Notion:**
- API Docs: https://developers.notion.com/
- Integration Guide: https://www.notion.so/help/create-integrations-with-the-notion-api

**Gmail:**
- API Docs: https://developers.google.com/gmail/api
- Quotas: https://developers.google.com/gmail/api/reference/quota
- Python Quickstart: https://developers.google.com/gmail/api/quickstart/python

### Troubleshooting

If you encounter issues:

1. **Check logs**: `logs/slack_agent.log`
2. **Verify tokens**: Run test commands
3. **Review documentation**: See links above
4. **Check API status**: Visit status pages
5. **Re-run OAuth**: Delete tokens and re-authenticate

---

## 🆕 November 2025 API Updates

### Slack API Changes

**Important Rate Limit Updates (May 29, 2025)**
- `conversations.history` and `conversations.replies` now limited to **1 request/min** for non-Marketplace apps
- Apps created before May 29, 2025 maintain existing rate limits
- Marketplace apps unaffected
- **Action Required**: If building for distribution, consider Marketplace listing

**File Upload Deprecation (March 11, 2025 deadline)**
- `files.upload` API method is **deprecated**
- Must migrate to **new asynchronous upload flow** before March 11, 2025
- Current implementation uses old method - update recommended
- See: https://api.slack.com/methods/files.upload

**API Terms of Service Updates (June 30, 2025)**
- Data usage restrictions strengthened
- Commercial distribution must use Slack Marketplace
- Discovery API and Data Access API have specific usage guidelines

**Slack CLI is now Open Source**
- Available on GitHub for community contributions
- Enhanced for Bolt framework support

### Gmail API Changes

**New Features (September 2025)**
- **Deal Cards in Promotions Tab**: Use annotations to create Deal Cards
- See: https://developers.google.com/workspace/gmail/promotab/overview

**Smart Cards for CSE (May 2025)**
- Hardware key encryption support for Client-Side Encryption
- `CseIdentity` and `CseKeyPair` resources for Google Workspace with hardware keys
- Only applicable for organizations using CSE

**Performance Improvements**
- `messages.import` method uses faster backend implementation
- Supports parallel import calls for higher migration throughput
- Quota cost decreased to reflect improved performance

### Notion API Changes

**Major Update: Multi-Source Databases (September 3, 2025)**
- **API Version 2025-09-03** separates "databases" (containers) from "data sources" (tables)
- Existing single-source databases continue working
- Update to new API version to support multi-source databases
- **Webhook versioning** introduced
- See: https://developers.notion.com/docs/upgrade-guide-2025-09-03

**SDK v5.1.0 (September 13, 2025)**
- `is_locked` parameter support for pages and databases
- `dataSource.update` can change parent database
- `request_id` added to client log lines
- Not compatible with API versions older than 2025-09-03

**Developer Terms Updated (December 2024)**
- Section 1.1: Refined scope of application
- Section 3.1: Clarified prohibited uses
- New Section 3.2 created for formatting

### Required Actions

#### Slack
1. ✅ **Immediate**: Review rate limiting in code (already configured for 1 req/min)
2. ⚠️ **Before March 11, 2025**: Migrate to new file upload API
3. ✅ **Optional**: Apply for Marketplace listing if distributing commercially

#### Gmail  
1. ✅ **No Action Required**: Current implementation compatible
2. ℹ️ **Optional**: Explore Deal Cards if using Promotions tab
3. ℹ️ **Optional**: Utilize parallel `messages.import` for bulk operations

#### Notion
1. ✅ **No Action Required**: Single-source databases still work
2. ℹ️ **Optional**: Upgrade to API version 2025-09-03 for multi-source support
3. ℹ️ **Optional**: Update to SDK v5.1.0 for latest features

---

**Last Updated**: November 9, 2025
**Version**: 2.0 (PostgreSQL + 2025 API Updates)
