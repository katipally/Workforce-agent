"""
Self-Aware AI Agent Brain for Workforce Agent.

This module implements a production-ready AI agent that:
1. Knows its identity and capabilities
2. Can use tools (Slack, Gmail, Notion)
3. Has access to RAG for context retrieval
4. Uses gpt-5-nano (or compatible gpt-5 family models) for lightweight reasoning
"""

import json
from typing import List, Dict, Any, Optional, AsyncIterator
from openai import AsyncOpenAI
import sys
from pathlib import Path

# Setup paths
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir.parent / 'core'))

from config import Config
from utils.logger import get_logger
from agent.langchain_tools import WorkforceTools
from agent.hybrid_rag import HybridRAGEngine

logger = get_logger(__name__)


# System prompt that makes the AI self-aware
SYSTEM_PROMPT = """You are the Workforce AI Assistant - a powerful, autonomous AI agent that is the SINGLE SOURCE OF CONTROL for Slack, Gmail, and Notion.

## CORE PRINCIPLES - READ THIS FIRST

### 1. BE AUTONOMOUS AND DECISIVE
- **DO NOT ask unnecessary questions** - if you can figure it out, just do it
- **DO NOT list options** - pick the best one and proceed
- **DO NOT explain your plan repeatedly** - just execute
- When user asks for something, GET IT DONE in the fewest steps possible

### 2. CONTEXT AWARENESS
- **REMEMBER everything from the conversation** - if you already found data, USE IT
- When you retrieve an entry (like "CloudFactory — Clara Analytics"), you ALREADY HAVE its database_id and entry_id - USE THEM for updates
- Never re-search for data you already have in the conversation

### 3. SINGLE CONFIRMATION RULE FOR WRITES
- **READ operations**: Execute immediately, no confirmation needed
- **WRITE operations**: Ask for confirmation ONCE with a clear summary, then EXECUTE IMMEDIATELY after user confirms
- After user confirms (says "yes", "proceed", "do it", "confirmed", etc.) - EXECUTE THE ACTION IMMEDIATELY with confirmed=true
- **NEVER ask twice** - if user already confirmed, just do it

### 4. EFFICIENCY IS KEY
- User says "get info about X" → Fetch it immediately and present ALL details
- User says "update X to Y" → Show what will change, ask for confirmation ONCE
- User says "yes" or "proceed" → Execute IMMEDIATELY, no more questions

## YOUR IDENTITY
- Name: Workforce AI Assistant
- Purpose: Single command center for Slack, Gmail, and Notion - making the user's life EASY
- Capabilities: Full read/write access to all workspace tools

## YOUR TOOLS
You have access to many powerful tools (60+ as of Nov 2025) to interact with the user's workspace.

### SLACK TOOLS (5 tools)
1. **get_all_slack_channels** - List ALL Slack channels
   - Get complete list of workspace channels with names and IDs
   - Example: "What channels are available?"

2. **get_channel_messages** - Get ALL messages from a channel
   - Retrieve complete conversation history from any channel
   - Can get up to 100 recent messages
   - Example: "Get all messages from #social-slack-channel"

3. **summarize_slack_channel** - Summarize channel activity
   - Get messages and provide intelligent summary
   - Identifies key topics, decisions, and action items
   - Example: "Summarize what was discussed in #general this week"

4. **search_slack** - Search Slack messages
   - Targeted keyword search across messages
   - Example: "Find messages about the deadline"

5. **send_slack_message** - Send message to channel
   - Post messages to any Slack channel
   - Example: "Send 'Meeting at 3pm' to #general"

### GMAIL TOOLS (core examples)
6. **get_emails_from_sender** - Get ALL emails from a person
   - Retrieve all emails from a specific sender
   - Example: "Get all emails from john@company.com"

7. **get_email_by_subject** - Find emails by subject
   - Search for emails with specific subject keywords
   - Returns full email content
   - Example: "Get the email about quarterly review"

8. **search_gmail** - Search Gmail
   - Broad keyword search across all emails
   - Example: "Find emails about the project budget"

9. **send_gmail** - Send email
   - Send emails to any recipient
   - Example: "Send an email to team@company.com"

### NOTION TOOLS (core examples)
10. **list_notion_pages** - List Notion pages
    - Get list of pages in workspace
    - Example: "Show me my Notion pages"

11. **search_notion_content** - Search Notion
    - Find pages by content
    - Example: "Find Notion pages about meetings"

12. **create_notion_page** - Create Notion page
    - Create new pages with rich content
    - Example: "Save these notes to Notion"

### WORKSPACE SEARCH (core examples)
13. **search_workspace** - Search EVERYTHING
    - Semantic search across Slack, Gmail, and Notion
    - Uses AI to find most relevant information
    - Example: "What did anyone say about Q4 across all platforms?"

## CAPABILITIES
- **SLACK**: List channels, get ALL messages, summarize channels, search, send messages, manage pins, channels, and users
- **GMAIL**: Full email bodies, advanced search with ALL operators, complete thread retrieval (all messages), search email threads, get unread counts, send emails
- **NOTION**: FULL DATABASE CRUD - read all entries, update entries by name, add new entries, delete entries. Also: list pages, search content, create pages
- **WORKSPACE**: Cross-platform semantic search and project tracking across Slack, Gmail, and Notion
- **INTELLIGENCE**: Analyze, summarize, and provide insights from retrieved data
- **AUTOMATION**: Perform actions (send, create, update, delete) on behalf of user with complete freedom

## ADVANCED TOOLS (NOV 2025)
- **GMAIL THREADS**:
  - `search_email_threads` – find email threads (conversations) using any Gmail query
  - `get_complete_email_thread` – retrieve the ENTIRE thread with ALL messages and full bodies
  - `get_recent_email_thread_between_people` – get the most recent thread between two people (names or emails)
- **NOTION WORKSPACE**:
  - `list_notion_pages` – list recent pages in the workspace via Notion Search API
  - `search_notion_workspace` – search for pages anywhere in the workspace
  - `append_to_notion_page` – update existing Notion pages with new content (DO NOT create duplicates)
- **NOTION DATABASE CRUD** (IMPORTANT - use these for database operations):
  - `query_notion_database` – get all entries from a database with search_text filter
  - `update_notion_entry_by_name` – BEST WAY to update: find entry by name and update any property (e.g., update Alegion's Estimated Value to 3000)
  - `add_notion_database_entry` – add new row/entry to a database
  - `delete_notion_database_entry` – archive/delete an entry by ID
- **PROJECT TRACKING**:
  - `track_project` – aggregate project updates from Slack, Gmail, and Notion
  - `generate_project_report` – create stakeholder-ready project reports
  - `update_project_notion_page` – write project status updates into existing Notion pages
- **CROSS-PLATFORM UTILITIES**:
  - `search_all_platforms` – search Slack, Gmail, and Notion simultaneously
  - `get_team_activity_summary` – summarize a team member's activity across tools
  - `analyze_slack_channel` – channel analytics and engagement metrics

## TOOL SELECTION GUIDE
- User asks "get all messages from #channel" → Use `get_channel_messages`
- User asks "summarize #channel" → Use `summarize_slack_channel`
- User asks "list channels" → Use `get_all_slack_channels`
- User asks "emails from person@email.com" → Use `get_emails_from_sender` or `advanced_gmail_search` with a `from:` query
- User asks "find email about X" → Use `get_email_by_subject` or `advanced_gmail_search`
- User asks "get our recent email thread between A and B" → Prefer `get_recent_email_thread_between_people`
- User asks "show all Notion pages" → Use `list_notion_pages`
- User asks "find Notion pages about X" → Use `search_notion_workspace` or `search_notion_content`
- User asks "what channels exist" → Use `get_all_slack_channels`
- User asks "overall project status" → Use `track_project`
- User asks "search everywhere for X" → Use `search_all_platforms`
- User asks for summary → Get data first with tools, then summarize in your response

### NOTION DATABASE OPERATIONS (MOST IMPORTANT - USE THESE)
- User asks "get info about X" → Use `find_notion_entry(search_text="X")` - this searches ALL databases and returns full details with database_id ready for updates
- User asks "update X's value to Y" → If you already have database_id from earlier search, use `update_notion_entry_by_name` directly. Otherwise, first use `find_notion_entry` to get the database_id
- User says "yes" or "proceed" after you showed the change → IMMEDIATELY call `update_notion_entry_by_name` with confirmed=true
- User asks "add a new entry" → Use `add_notion_database_entry`
- User asks "delete entry X" → Use `delete_notion_database_entry`

### THE IDEAL FLOW (2-3 messages max):
1. User: "Get info about CloudFactory from Yash Exploration"
   You: Call `find_notion_entry(search_text="CloudFactory", database_hint="Yash Exploration")`
   → Show ALL properties with database_id and entry_id

2. User: "Change the value to 500"
   You: "I'll update CloudFactory's Estimated Value from 456.95 to 500. Proceed?"

3. User: "yes"
   You: Call `update_notion_entry_by_name(database_id="...", entry_name="CloudFactory", property_name="Estimated Value Annually", new_value="500", confirmed=true)`
   → "Done! Updated CloudFactory's Estimated Value to 500."

## MULTI-TOOL WORKFLOWS
You can call MULTIPLE tools in sequence for complex tasks:

**Example 1**: "Get messages from #channel and save to Notion"
1. Call `get_channel_messages(channel="#channel")`
2. Call `create_notion_page(title="...", content=<results from step 1>)`

**Example 2**: "Summarize #channel and email it to team@company.com"
1. Call `summarize_slack_channel(channel="#channel")`
2. Call `send_gmail(to="team@company.com", subject="Summary", body=<results from step 1>)`

**Example 3**: "List all channels, get messages from each, and create summary"
1. Call `get_all_slack_channels()`
2. For each channel, call `get_channel_messages(channel=...)`
3. Aggregate results and provide summary

**IMPORTANT**: After calling a tool, GPT-4 will analyze the results and decide:
- Should I call another tool with these results?
- Should I transform/summarize the data first?
- Is this enough to answer the user's question?

## YOUR BEHAVIOR - BE AN AUTONOMOUS AGENT
1. **Be Decisive**: Pick the best action and DO IT - don't list options
2. **Be Fast**: Minimize back-and-forth - get things done in fewest messages
3. **Be Smart**: Use context from earlier messages - never re-search for data you already have
4. **Be Action-Oriented**: Execute tasks, don't just explain plans
5. **Be Efficient**: Chain multiple tool calls if needed to complete the task

## EXAMPLES OF GOOD BEHAVIOR

**Good - Autonomous and Efficient:**
User: "Get info about CloudFactory from Yash Exploration page"
You: [Immediately call query_notion_database with search for "CloudFactory"]
Result: "Found CloudFactory — Clara Analytics with these details: [all properties]"

**Good - Single Confirmation:**
User: "Update the value to 500"  
You: "I'll update CloudFactory's Estimated Value to 500. Confirm?" (ONE question)
User: "yes"
You: [Immediately execute with confirmed=true] "Done! Updated to 500."

**BAD - Never do this:**
- Asking "which database?" when you already retrieved the data
- Asking "do you want option 1 or 2?" - just pick the best option
- Asking for confirmation multiple times
- Explaining your plan without executing
- Re-searching for data you already found

## CRITICAL RULES

### READ OPERATIONS → EXECUTE IMMEDIATELY
No confirmation. No asking. Just fetch and show ALL the data.
- `get_notion_page_content`, `query_notion_database`, `search_notion_workspace`
- `get_channel_messages`, `search_slack`, `summarize_slack_channel`
- `search_gmail`, `get_emails_from_sender`, `get_complete_email_thread`

### WRITE OPERATIONS → SINGLE CONFIRMATION, THEN EXECUTE
1. Show what you will do: "I'll update [entry] [property] from [old] to [new]"
2. Wait for "yes" / "proceed" / "do it" / "confirmed"
3. IMMEDIATELY execute with confirmed=true - NO MORE QUESTIONS

### CONTEXT MEMORY
When you query a database and find an entry:
- You HAVE the database_id (from the query)
- You HAVE the entry name and all properties
- When user asks to update → USE THIS DATA, don't re-search

### SMART DATA RETRIEVAL
When searching for something:
- If first search doesn't find exact match, try broader search
- If you find multiple matches, pick the BEST one (most relevant) and proceed
- Don't list options unless absolutely necessary

Now, BE THE AUTONOMOUS AGENT and help the user efficiently!"""


class WorkforceAIBrain:
    """Self-aware AI agent with tool calling and RAG capabilities."""
    
    def __init__(
        self,
        openai_api_key: str,
        rag_engine: HybridRAGEngine,
        model: str = "gpt-5-nano",
        temperature: float = 0.7,
        user_id: Optional[str] = None
    ):
        """Initialize the AI brain.
        
        Args:
            openai_api_key: OpenAI API key
            rag_engine: RAG engine for context retrieval
            model: OpenAI model to use (default: gpt-5-nano - fast, cost-efficient reasoning, Nov 2025)
                   Examples: gpt-5-nano (default), gpt-5-mini, gpt-5 (if available)
            temperature: Model temperature (0.7 for balanced creativity)
            user_id: User ID for loading OAuth credentials (Gmail, etc.)
        """
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.temperature = temperature
        self.rag_engine = rag_engine
        self.user_id = user_id
        self.tools_handler = WorkforceTools(user_id=user_id)
        
        # Get available tools
        self.tools = self._define_tools()
        
        logger.info(f"✓ AI Brain initialized with model: {model}")
        logger.info(f"Available tools: {len(self.tools)}")
    
    def _define_tools(self) -> List[Dict[str, Any]]:
        """Define tools in OpenAI function calling format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "get_all_slack_channels",
                    "description": "Get a list of ALL Slack channels in the workspace with names and IDs.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_channel_messages",
                    "description": "Get ALL messages from a specific Slack channel. Use this when user asks for 'all messages' or wants to see entire channel conversation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Channel name (without #) or channel ID"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum messages to retrieve (default: 100)",
                                "default": 100
                            }
                        },
                        "required": ["channel"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "summarize_slack_channel",
                    "description": "Get messages from a Slack channel for summarization. Use when user asks for a summary of channel activity.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Channel name or ID to summarize"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Number of recent messages (default: 100)",
                                "default": 100
                            }
                        },
                        "required": ["channel"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_slack",
                    "description": "Search through Slack messages for specific keywords or topics. Use for targeted searches, not for getting all messages.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query (keywords or natural language)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_slack_message",
                    "description": "Send a message to a Slack channel. Requires channel ID and message text.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Slack channel ID (e.g., C01234ABCD)"
                            },
                            "text": {
                                "type": "string",
                                "description": "Message text to send"
                            }
                        },
                        "required": ["channel", "text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_emails_from_sender",
                    "description": "Get ALL emails from a specific person/sender. Use when user asks for emails from a particular person.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "sender": {
                                "type": "string",
                                "description": "Sender email address or name"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum emails to retrieve (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["sender"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_email_by_subject",
                    "description": "Get emails matching a specific subject line. Returns full email content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "subject": {
                                "type": "string",
                                "description": "Subject keywords to search for"
                            }
                        },
                        "required": ["subject"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_gmail",
                    "description": "Search through Gmail emails for specific keywords or topics. Use for broad searches.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query (keywords or Gmail search syntax)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_gmail",
                    "description": "Send an email via Gmail. Requires recipient email, subject, and body.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject line"
                            },
                            "body": {
                                "type": "string",
                                "description": "Email body (plain text or HTML)"
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed sending this email.",
                                "default": False
                            }
                        },
                        "required": ["to", "subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_notion_pages",
                    "description": "List Notion pages in the workspace.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum pages to list (default: 20)",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_notion_page_content",
                    "description": "Get flattened text content of a Notion page, optionally including subpages.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Notion page ID to read",
                            },
                            "include_subpages": {
                                "type": "boolean",
                                "description": "Whether to also traverse and include subpages in the content",
                                "default": False,
                            },
                            "max_blocks": {
                                "type": "integer",
                                "description": "Maximum number of blocks to read (safety cap, default 500)",
                                "default": 500,
                            },
                        },
                        "required": ["page_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_notion_database",
                    "description": "Query a Notion database and list matching rows with ALL properties. Use search_text to find specific entries (e.g., 'CCHP Health Plan') and get their full details in JSON format.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {
                                "type": "string",
                                "description": "Notion database ID to query"
                            },
                            "filter_json": {
                                "type": "string",
                                "description": "Optional JSON string for Notion filter object (e.g., status or owner filters)",
                                "nullable": True
                            },
                            "page_size": {
                                "type": "integer",
                                "description": "Maximum rows to return (default: 100)",
                                "default": 100
                            },
                            "search_text": {
                                "type": "string",
                                "description": "Optional text to search for. When provided, returns FULL JSON details for matching entries (e.g., 'CCHP Health Plan' to find that specific entry)",
                                "nullable": True
                            }
                        },
                        "required": ["database_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_notion_database_item",
                    "description": "Update properties of an existing Notion database item (page) using raw Notion property JSON. For easier updates, use update_notion_entry_by_name instead.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Notion page ID belonging to the database"
                            },
                            "properties_json": {
                                "type": "string",
                                "description": "JSON string representing Notion properties to set (e.g., status, owner)"
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed updating this database item.",
                                "default": False
                            }
                        },
                        "required": ["page_id", "properties_json"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "find_notion_entry",
                    "description": "POWERFUL SEARCH: Find a database entry by name across ALL Notion databases. Returns all details (database_id, entry_id, properties) needed for updates. Use this when you need to find an entry but don't know which database it's in.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "search_text": {
                                "type": "string",
                                "description": "Entry name to search for (e.g., 'CloudFactory', 'Alegion', 'CCHP Health Plan')"
                            },
                            "database_hint": {
                                "type": "string",
                                "description": "Optional: Name of database to search first (e.g., 'Yash Exploration')"
                            }
                        },
                        "required": ["search_text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_notion_entry_by_name",
                    "description": "BEST WAY to update a Notion database entry. Find an entry by its name/title and update any property. Example: update_notion_entry_by_name(database_id='...', entry_name='Alegion', property_name='Estimated Value', new_value=3000)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {
                                "type": "string",
                                "description": "Database ID or URL containing the entry"
                            },
                            "entry_name": {
                                "type": "string",
                                "description": "Name/title of the entry to find (e.g., 'Alegion', 'CCHP Health Plan')"
                            },
                            "property_name": {
                                "type": "string",
                                "description": "Property/column name to update (e.g., 'Estimated Value Annually', 'Status')"
                            },
                            "new_value": {
                                "type": "string",
                                "description": "New value to set (number, text, date, etc.)"
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after user explicitly confirmed the update.",
                                "default": False
                            }
                        },
                        "required": ["database_id", "entry_name", "property_name", "new_value"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_notion_database_entry",
                    "description": "Add a new entry/row to a Notion database. Provide property names and values as a JSON object.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {
                                "type": "string",
                                "description": "Database ID or URL to add entry to"
                            },
                            "properties_json": {
                                "type": "string",
                                "description": "JSON object of property names to values, e.g. {\"Name\": \"New Project\", \"Status\": \"Active\", \"Value\": 5000}"
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after user explicitly confirmed creating this entry.",
                                "default": False
                            }
                        },
                        "required": ["database_id", "properties_json"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_notion_database_entry",
                    "description": "Archive/delete a Notion database entry by its ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entry_id": {
                                "type": "string",
                                "description": "Entry/page ID to archive"
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after user explicitly confirmed deleting this entry.",
                                "default": False
                            }
                        },
                        "required": ["entry_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_notion_page_content",
                    "description": "Find and replace text inside a Notion page (and optionally subpages). Use for targeted edits like changing dates.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "Notion page ID whose content should be updated",
                            },
                            "find_text": {
                                "type": "string",
                                "description": "Exact text to search for in page blocks",
                            },
                            "replace_text": {
                                "type": "string",
                                "description": "Replacement text",
                            },
                            "include_subpages": {
                                "type": "boolean",
                                "description": "Whether to also search and replace inside subpages",
                                "default": False,
                            },
                            "max_matches": {
                                "type": "integer",
                                "description": "Maximum number of matches to replace across the page tree (default 50)",
                                "default": 50,
                            },
                        },
                        "required": ["page_id", "find_text", "replace_text"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_notion_content",
                    "description": "Search Notion pages by content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_notion_databases",
                    "description": "List all databases in the Notion workspace. Use this to find the correct database ID before querying. Returns ORIGINAL databases (not linked views).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title_filter": {
                                "type": "string",
                                "description": "Optional filter to search databases by title (case-insensitive)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_notion_page",
                    "description": "Create a new page in Notion with specified title and content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {
                                "type": "string",
                                "description": "Page title"
                            },
                            "content": {
                                "type": "string",
                                "description": "Page content (supports markdown)"
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed creating this page.",
                                "default": False
                            }
                        },
                        "required": ["title", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_workspace",
                    "description": "Semantic search across all workspace tools (Slack, Gmail, Notion). Use for general questions that may span multiple tools.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "The search query"
                            },
                            "sources": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": ["slack", "gmail", "notion"]
                                },
                                "description": "Which sources to search (default: all)"
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            # NEW GMAIL TOOLS - Nov 2025
            {
                "type": "function",
                "function": {
                    "name": "get_full_email_content",
                    "description": "Get COMPLETE email content with full body (not just snippet). Use this when user wants to read entire email.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "Gmail message ID from search results"
                            }
                        },
                        "required": ["message_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_unread_email_count",
                    "description": "Get exact count of unread emails. Use when user asks 'how many unread emails'.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "advanced_gmail_search",
                    "description": "Advanced Gmail search with ALL operators: from:, to:, subject:, has:attachment, is:unread, is:starred, label:, after:, before:, filename:, larger:, smaller:. Use for complex email searches.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Gmail search query with operators (e.g., 'from:john has:attachment is:unread')"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum results (default: 20)",
                                "default": 20
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_complete_email_thread",
                    "description": "Get COMPLETE email thread with ALL messages - CRITICAL for long company email threads. Retrieves entire conversation history no matter how many messages. Use this when user wants full thread/conversation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "thread_id": {
                                "type": "string",
                                "description": "Gmail thread ID (from search results)"
                            }
                        },
                        "required": ["thread_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_email_threads",
                    "description": "Search for email threads (conversations) and get thread summaries with message counts. Use this to find threads, then get_complete_email_thread to read full content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Gmail search query (supports all operators: from:, to:, subject:, etc.)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum threads to return (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_recent_email_thread_between_people",
                    "description": "Get the most recent email thread between two people (names or email addresses) and return the FULL thread content. Use this when user asks for 'recent thread between X and Y'.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "person_a": {
                                "type": "string",
                                "description": "First person (name or email)"
                            },
                            "person_b": {
                                "type": "string",
                                "description": "Second person (name or email)"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "How many days back to search (default: 60)",
                                "default": 60
                            }
                        },
                        "required": ["person_a", "person_b"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_gmail_attachments_for_message",
                    "description": "List all attachments for a Gmail message and show their filenames, sizes, and attachment IDs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "Gmail message ID whose attachments should be listed"
                            }
                        },
                        "required": ["message_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "download_gmail_attachment",
                    "description": "Download a Gmail attachment and save it into the local files directory for the agent to use.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message_id": {
                                "type": "string",
                                "description": "Gmail message ID containing the attachment"
                            },
                            "attachment_id": {
                                "type": "string",
                                "description": "Attachment ID as returned by list_gmail_attachments_for_message"
                            },
                            "filename": {
                                "type": "string",
                                "description": "Preferred filename for storing the attachment locally"
                            }
                        },
                        "required": ["message_id", "attachment_id", "filename"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_gmail_with_attachments",
                    "description": "Send an email via Gmail with one or more local files attached. Use after the user uploads or references files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to": {
                                "type": "string",
                                "description": "Recipient email address"
                            },
                            "subject": {
                                "type": "string",
                                "description": "Email subject line"
                            },
                            "body": {
                                "type": "string",
                                "description": "Plain-text email body"
                            },
                            "file_paths": {
                                "type": "string",
                                "description": "Comma-separated list of local file paths to attach"
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed sending this email with attachments.",
                                "default": False
                            }
                        },
                        "required": ["to", "subject", "body", "file_paths"]
                    }
                }
            },
            # NEW SLACK TOOLS - Nov 2025
            {
                "type": "function",
                "function": {
                    "name": "upload_file_to_slack",
                    "description": "Upload a file to Slack channel. Use when user wants to share/upload files.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Channel ID"
                            },
                            "file_content": {
                                "type": "string",
                                "description": "File path or content to upload"
                            },
                            "filename": {
                                "type": "string",
                                "description": "Name for the file"
                            },
                            "title": {
                                "type": "string",
                                "description": "Optional file title"
                            }
                        },
                        "required": ["channel", "file_content", "filename"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "pin_slack_message",
                    "description": "Pin a message in Slack channel for visibility.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Channel ID"
                            },
                            "timestamp": {
                                "type": "string",
                                "description": "Message timestamp"
                            }
                        },
                        "required": ["channel", "timestamp"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "unpin_slack_message",
                    "description": "Unpin a message from Slack channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Channel ID"},
                            "timestamp": {"type": "string", "description": "Message timestamp"}
                        },
                        "required": ["channel", "timestamp"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_pinned_messages",
                    "description": "Get all pinned messages in a Slack channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Channel ID"}
                        },
                        "required": ["channel"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_slack_channel",
                    "description": "Create a new Slack channel (public or private).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Channel name (lowercase, no spaces)"
                            },
                            "is_private": {
                                "type": "boolean",
                                "description": "Create as private channel (default: false)",
                                "default": False
                            }
                        },
                        "required": ["name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "archive_slack_channel",
                    "description": "Archive a Slack channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Channel ID to archive"},
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed archiving this channel.",
                                "default": False
                            }
                        },
                        "required": ["channel"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "invite_to_slack_channel",
                    "description": "Invite users to a Slack channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Channel ID"},
                            "users": {"type": "string", "description": "Comma-separated user IDs"}
                        },
                        "required": ["channel", "users"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_slack_message",
                    "description": "Update/edit a previously sent Slack message.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Channel ID"},
                            "timestamp": {"type": "string", "description": "Message timestamp"},
                            "text": {"type": "string", "description": "New message text"},
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed editing this message.",
                                "default": False
                            }
                        },
                        "required": ["channel", "timestamp", "text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "delete_slack_message",
                    "description": "Delete a Slack message.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string", "description": "Channel ID"},
                            "timestamp": {"type": "string", "description": "Message timestamp"},
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed deleting this message.",
                                "default": False
                            }
                        },
                        "required": ["channel", "timestamp"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_all_slack_users",
                    "description": "List all users in the Slack workspace with emails and IDs.",
                    "parameters": {
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                }
            },
            # NEW NOTION TOOLS - Nov 2025
            {
                "type": "function",
                "function": {
                    "name": "append_to_notion_page",
                    "description": "Append content to an existing Notion page. Use to add content to pages.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string", "description": "Page ID to append to"},
                            "content": {"type": "string", "description": "Content to append"},
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed appending to this page.",
                                "default": False
                            }
                        },
                        "required": ["page_id", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_notion_databases",
                    "description": "List Notion databases in the workspace using the Notion Search API. Use when user asks about available databases or project tables.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum databases to list (default: 20)",
                                "default": 20
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_notion_workspace",
                    "description": "Search across entire Notion workspace for pages and databases.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            },
            # PROJECT TRACKING TOOLS - Nov 2025
            {
                "type": "function",
                "function": {
                    "name": "track_project",
                    "description": "Track a project across Slack, Gmail, and Notion. POWERFUL cross-platform aggregation that gathers updates from all sources, analyzes them, identifies key points, action items, blockers, and calculates progress. Use when user asks about project status or wants to see all updates.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_name": {
                                "type": "string",
                                "description": "Name of the project to track (e.g., 'Q4 Dashboard', 'Agent Project', 'Mobile App')"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Number of days of history to include (default: 7)",
                                "default": 7
                            },
                            "notion_page_id": {
                                "type": "string",
                                "description": "Optional Notion page ID to associate with project",
                                "default": None
                            }
                        },
                        "required": ["project_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_project_report",
                    "description": "Generate a comprehensive formatted project report suitable for stakeholders. Creates detailed ASCII report with progress bars, statistics, and organized sections. Use when user wants a formal project report or summary to share.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "project_name": {
                                "type": "string",
                                "description": "Name of the project"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Number of days to include in report (default: 7)",
                                "default": 7
                            }
                        },
                        "required": ["project_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "update_project_notion_page",
                    "description": "Update existing Notion page with current project status. IMPORTANT: This UPDATES an existing page, does NOT create new one. Automatically tracks project across all platforms and appends formatted status update to the specified Notion page. Use when user wants to update project documentation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {
                                "type": "string",
                                "description": "ID of existing Notion page to update"
                            },
                            "project_name": {
                                "type": "string",
                                "description": "Name of the project"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Days of history to include (default: 7)",
                                "default": 7
                            },
                            "confirmed": {
                                "type": "boolean",
                                "description": "MUST be true ONLY after the user explicitly confirmed updating this Notion project page.",
                                "default": False
                            }
                        },
                        "required": ["page_id", "project_name"]
                    }
                }
            },
            # UTILITY TOOLS - Nov 2025
            {
                "type": "function",
                "function": {
                    "name": "search_all_platforms",
                    "description": "Search across ALL platforms (Slack, Gmail, Notion) simultaneously for a query. Returns unified results from all sources. Use when user wants comprehensive search across everything.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query to use across all platforms"
                            },
                            "limit_per_platform": {
                                "type": "integer",
                                "description": "Max results per platform (default: 10)",
                                "default": 10
                            }
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_team_activity_summary",
                    "description": "Get activity summary for a team member across all platforms. Shows their Slack messages, emails, and Notion updates. Use when user asks about what someone is working on or their recent activity.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "person_name": {
                                "type": "string",
                                "description": "Name or email of the person"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Days of history (default: 7)",
                                "default": 7
                            }
                        },
                        "required": ["person_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "analyze_slack_channel",
                    "description": "Analyze a Slack channel's activity, most active users, common topics, and engagement patterns. Use when user wants channel analytics or insights.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {
                                "type": "string",
                                "description": "Channel name or ID"
                            },
                            "days_back": {
                                "type": "integer",
                                "description": "Days to analyze (default: 7)",
                                "default": 7
                            }
                        },
                        "required": ["channel"]
                    }
                }
            }
        ]
    
    async def _execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        user_email: Optional[str] = None,
        source_prefs: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Execute a tool and return the result.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            
        Returns:
            Tool result as string
        """
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Arguments: {arguments}")
        
        destructive_tools = {
            "send_gmail": "sending an email",
            "send_gmail_with_attachments": "sending an email with attachments",
            "archive_slack_channel": "archiving a Slack channel",
            "update_slack_message": "editing a Slack message",
            "delete_slack_message": "deleting a Slack message",
            "create_notion_page": "creating a new Notion page",
            "append_to_notion_page": "appending content to a Notion page",
            "update_project_notion_page": "updating a Notion project page",
            "update_notion_database_item": "updating a Notion database item",
            "update_notion_entry_by_name": "updating a Notion database entry",
            "add_notion_database_entry": "adding a new Notion database entry",
            "delete_notion_database_entry": "deleting a Notion database entry",
        }

        if tool_name in destructive_tools:
            confirmed = bool(arguments.get("confirmed"))
            if not confirmed:
                explanation = destructive_tools[tool_name]
                return (
                    f"⚠️ Confirmation needed for {explanation}. "
                    "Present ONE concise confirmation message showing: what will change, from what, to what. "
                    "Example: 'I'll update CloudFactory's Estimated Value from 456 to 500. Proceed?' "
                    "When user says yes/proceed/confirmed/do it, IMMEDIATELY call this tool with confirmed=true. "
                    "DO NOT ask again or explain more - just execute."
                )

        try:
            # SLACK TOOLS
            if tool_name == "get_all_slack_channels":
                result = self.tools_handler.get_all_slack_channels()
            
            elif tool_name == "get_channel_messages":
                result = self.tools_handler.get_channel_messages(
                    channel=arguments.get("channel", ""),
                    limit=arguments.get("limit", 100)
                )
            
            elif tool_name == "summarize_slack_channel":
                result = self.tools_handler.summarize_slack_channel(
                    channel=arguments.get("channel", ""),
                    limit=arguments.get("limit", 100)
                )
            
            elif tool_name == "search_slack":
                result = self.tools_handler.search_slack_messages(
                    query=arguments.get("query", ""),
                    channel=arguments.get("channel"),
                    limit=arguments.get("limit", 10)
                )
            
            elif tool_name == "send_slack_message":
                result = self.tools_handler.send_slack_message(
                    channel=arguments.get("channel", ""),
                    text=arguments.get("text", "")
                )
            
            # GMAIL TOOLS
            elif tool_name == "get_emails_from_sender":
                result = self.tools_handler.get_emails_from_sender(
                    sender=arguments.get("sender", ""),
                    limit=arguments.get("limit", 10)
                )
            
            elif tool_name == "get_email_by_subject":
                result = self.tools_handler.get_email_by_subject(
                    subject=arguments.get("subject", "")
                )
            
            elif tool_name == "search_gmail":
                result = self.tools_handler.search_gmail_messages(
                    query=arguments.get("query", ""),
                    limit=arguments.get("limit", 10),
                    gmail_account_email=user_email,
                )
            
            elif tool_name == "send_gmail":
                result = self.tools_handler.send_email(
                    to=arguments.get("to", ""),
                    subject=arguments.get("subject", ""),
                    body=arguments.get("body", "")
                )
            
            # NOTION TOOLS
            elif tool_name == "list_notion_pages":
                result = self.tools_handler.list_notion_pages(
                    limit=arguments.get("limit", 20)
                )
            
            elif tool_name == "get_notion_page_content":
                result = self.tools_handler.get_notion_page_content(
                    page_id=arguments.get("page_id", ""),
                    include_subpages=arguments.get("include_subpages", False),
                    max_depth=3,
                    max_blocks=arguments.get("max_blocks", 500),
                )
            
            elif tool_name == "update_notion_page_content":
                result = self.tools_handler.update_notion_page_content(
                    page_id=arguments.get("page_id", ""),
                    find_text=arguments.get("find_text", ""),
                    replace_text=arguments.get("replace_text", ""),
                    include_subpages=arguments.get("include_subpages", False),
                    max_matches=arguments.get("max_matches", 50),
                )
            
            elif tool_name == "search_notion_content":
                result = self.tools_handler.search_notion_content(
                    query=arguments.get("query", "")
                )
            
            elif tool_name == "list_notion_databases":
                result = self.tools_handler.list_notion_databases(
                    title_filter=arguments.get("title_filter")
                )
            
            elif tool_name == "create_notion_page":
                result = self.tools_handler.create_notion_page(
                    title=arguments.get("title", ""),
                    content=arguments.get("content", "")
                )
            
            elif tool_name == "search_workspace":
                # Use RAG engine; scope Gmail results to the caller's Gmail account
                query = arguments.get("query", "")
                arg_sources = arguments.get("sources")

                base_sources = arg_sources or ["slack", "gmail", "notion"]
                if source_prefs:
                    allowed_sources = [
                        s for s in base_sources
                        if bool(source_prefs.get(s, True))
                    ]
                    if not allowed_sources:
                        allowed_sources = base_sources
                else:
                    allowed_sources = base_sources

                rag_results = self.rag_engine._retrieve_context(
                    query,
                    top_k=5,
                    gmail_account_email=user_email,
                    sources=allowed_sources,
                )
                result = f"Found {len(rag_results)} relevant results:\n\n{rag_results}"
            
            # NEW GMAIL TOOLS - Nov 2025
            elif tool_name == "get_full_email_content":
                result = self.tools_handler.get_full_email_content(
                    message_id=arguments.get("message_id", "")
                )
            
            elif tool_name == "get_unread_email_count":
                result = self.tools_handler.get_unread_email_count()
            
            elif tool_name == "advanced_gmail_search":
                result = self.tools_handler.advanced_gmail_search(
                    query=arguments.get("query", ""),
                    limit=arguments.get("limit", 20)
                )
            
            elif tool_name == "get_complete_email_thread":
                result = self.tools_handler.get_complete_email_thread(
                    thread_id=arguments.get("thread_id", "")
                )
            
            elif tool_name == "search_email_threads":
                result = self.tools_handler.search_email_threads(
                    query=arguments.get("query", ""),
                    limit=arguments.get("limit", 10)
                )
            
            elif tool_name == "get_recent_email_thread_between_people":
                result = self.tools_handler.get_recent_email_thread_between_people(
                    person_a=arguments.get("person_a", ""),
                    person_b=arguments.get("person_b", ""),
                    days_back=arguments.get("days_back", 60)
                )
            
            elif tool_name == "list_gmail_attachments_for_message":
                result = self.tools_handler.list_gmail_attachments_for_message(
                    message_id=arguments.get("message_id", "")
                )
            
            elif tool_name == "download_gmail_attachment":
                result = self.tools_handler.download_gmail_attachment(
                    message_id=arguments.get("message_id", ""),
                    attachment_id=arguments.get("attachment_id", ""),
                    filename=arguments.get("filename", "attachment")
                )
            
            elif tool_name == "send_gmail_with_attachments":
                result = self.tools_handler.send_gmail_with_attachments(
                    to=arguments.get("to", ""),
                    subject=arguments.get("subject", ""),
                    body=arguments.get("body", ""),
                    file_paths=arguments.get("file_paths", "")
                )
            
            # NEW SLACK TOOLS - Nov 2025
            elif tool_name == "upload_file_to_slack":
                result = self.tools_handler.upload_file_to_slack(
                    channel=arguments.get("channel", ""),
                    file_content=arguments.get("file_content", ""),
                    filename=arguments.get("filename", ""),
                    title=arguments.get("title")
                )
            
            elif tool_name == "pin_slack_message":
                result = self.tools_handler.pin_slack_message(
                    channel=arguments.get("channel", ""),
                    timestamp=arguments.get("timestamp", "")
                )
            
            elif tool_name == "unpin_slack_message":
                result = self.tools_handler.unpin_slack_message(
                    channel=arguments.get("channel", ""),
                    timestamp=arguments.get("timestamp", "")
                )
            
            elif tool_name == "get_pinned_messages":
                result = self.tools_handler.get_pinned_messages(
                    channel=arguments.get("channel", "")
                )
            
            elif tool_name == "create_slack_channel":
                result = self.tools_handler.create_slack_channel(
                    name=arguments.get("name", ""),
                    is_private=arguments.get("is_private", False)
                )
            
            elif tool_name == "archive_slack_channel":
                result = self.tools_handler.archive_slack_channel(
                    channel=arguments.get("channel", "")
                )
            
            elif tool_name == "invite_to_slack_channel":
                result = self.tools_handler.invite_to_slack_channel(
                    channel=arguments.get("channel", ""),
                    users=arguments.get("users", "")
                )
            
            elif tool_name == "update_slack_message":
                result = self.tools_handler.update_slack_message(
                    channel=arguments.get("channel", ""),
                    timestamp=arguments.get("timestamp", ""),
                    text=arguments.get("text", "")
                )
            
            elif tool_name == "delete_slack_message":
                result = self.tools_handler.delete_slack_message(
                    channel=arguments.get("channel", ""),
                    timestamp=arguments.get("timestamp", "")
                )
            
            elif tool_name == "list_all_slack_users":
                result = self.tools_handler.list_all_slack_users()
            
            # NEW NOTION TOOLS - Nov 2025
            elif tool_name == "append_to_notion_page":
                result = self.tools_handler.append_to_notion_page(
                    page_id=arguments.get("page_id", ""),
                    content=arguments.get("content", "")
                )
            
            elif tool_name == "list_notion_databases":
                result = self.tools_handler.list_notion_databases(
                    limit=arguments.get("limit", 20)
                )
            
            elif tool_name == "search_notion_workspace":
                result = self.tools_handler.search_notion_workspace(
                    query=arguments.get("query", "")
                )
            
            elif tool_name == "query_notion_database":
                result = self.tools_handler.query_notion_database(
                    database_id=arguments.get("database_id", ""),
                    filter_json=arguments.get("filter_json"),
                    page_size=arguments.get("page_size", 100),
                    search_text=arguments.get("search_text")
                )
            
            elif tool_name == "update_notion_database_item":
                result = self.tools_handler.update_notion_database_item(
                    page_id=arguments.get("page_id", ""),
                    properties_json=arguments.get("properties_json", "")
                )
            
            elif tool_name == "find_notion_entry":
                result = self.tools_handler.find_notion_entry(
                    search_text=arguments.get("search_text", ""),
                    database_hint=arguments.get("database_hint"),
                )
            
            elif tool_name == "update_notion_entry_by_name":
                result = self.tools_handler.update_notion_entry_by_name(
                    database_id=arguments.get("database_id", ""),
                    entry_name=arguments.get("entry_name", ""),
                    property_name=arguments.get("property_name", ""),
                    new_value=arguments.get("new_value", ""),
                )
            
            elif tool_name == "add_notion_database_entry":
                props_json = arguments.get("properties_json", "{}")
                try:
                    properties = json.loads(props_json)
                except json.JSONDecodeError:
                    properties = {}
                result = self.tools_handler.add_notion_database_entry(
                    database_id=arguments.get("database_id", ""),
                    properties=properties,
                )
            
            elif tool_name == "delete_notion_database_entry":
                result = self.tools_handler.delete_notion_database_entry(
                    entry_id=arguments.get("entry_id", ""),
                )
            
            # PROJECT TRACKING TOOLS
            elif tool_name == "track_project":
                result = await self.tools_handler.track_project(
                    project_name=arguments.get("project_name", ""),
                    days_back=arguments.get("days_back", 7),
                    notion_page_id=arguments.get("notion_page_id"),
                    gmail_account_email=user_email,
                )
            
            elif tool_name == "generate_project_report":
                result = await self.tools_handler.generate_project_report(
                    project_name=arguments.get("project_name", ""),
                    days_back=arguments.get("days_back", 7),
                    gmail_account_email=user_email,
                )
            
            elif tool_name == "update_project_notion_page":
                result = await self.tools_handler.update_project_notion_page(
                    page_id=arguments.get("page_id", ""),
                    project_name=arguments.get("project_name", ""),
                    days_back=arguments.get("days_back", 7),
                    gmail_account_email=user_email,
                )
            
            # UTILITY TOOLS
            elif tool_name == "search_all_platforms":
                result = await self.tools_handler.search_all_platforms(
                    query=arguments.get("query", ""),
                    limit_per_platform=arguments.get("limit_per_platform", 10),
                    gmail_account_email=user_email,
                )
            
            elif tool_name == "get_team_activity_summary":
                result = await self.tools_handler.get_team_activity_summary(
                    person_name=arguments.get("person_name", ""),
                    days_back=arguments.get("days_back", 7),
                    gmail_account_email=user_email,
                )
            
            elif tool_name == "analyze_slack_channel":
                result = await self.tools_handler.analyze_slack_channel(
                    channel=arguments.get("channel", ""),
                    days_back=arguments.get("days_back", 7)
                )
            
            # GOOGLE CALENDAR TOOLS
            elif tool_name == "list_calendar_events":
                result = self.tools_handler.list_calendar_events(
                    days=arguments.get("days", 7),
                    max_results=arguments.get("max_results", 20)
                )
            
            elif tool_name == "create_calendar_event":
                result = self.tools_handler.create_calendar_event(
                    summary=arguments.get("summary", ""),
                    start_time=arguments.get("start_time", ""),
                    end_time=arguments.get("end_time", ""),
                    description=arguments.get("description"),
                    location=arguments.get("location"),
                    attendees=arguments.get("attendees")
                )
            
            elif tool_name == "update_calendar_event":
                result = self.tools_handler.update_calendar_event(
                    event_id=arguments.get("event_id", ""),
                    summary=arguments.get("summary"),
                    start_time=arguments.get("start_time"),
                    end_time=arguments.get("end_time"),
                    description=arguments.get("description"),
                    location=arguments.get("location")
                )
            
            elif tool_name == "delete_calendar_event":
                result = self.tools_handler.delete_calendar_event(
                    event_id=arguments.get("event_id", "")
                )
            
            elif tool_name == "check_calendar_availability":
                result = self.tools_handler.check_calendar_availability(
                    start_time=arguments.get("start_time", ""),
                    end_time=arguments.get("end_time", "")
                )
            
            else:
                result = f"Unknown tool: {tool_name}"
            
            logger.info(f"Tool {tool_name} executed successfully")
            return str(result)
        
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return f"Tool execution error: {str(e)}"
    
    def _select_tools_for_query(
        self,
        query: str,
        source_prefs: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Return a subset of tools that are most relevant for this query.

        This makes tool usage more adaptive by biasing the model toward
        Slack-only, Gmail-only, Notion-only, or project/workspace tools when
        the user's wording clearly targets one of those domains. When the
        query is ambiguous, the full tool set is used.
        """

        try:
            q = (query or "").lower()

            # Define tool sets FIRST (before they are used)
            slack_tools = {
                "get_all_slack_channels",
                "get_channel_messages",
                "summarize_slack_channel",
                "search_slack",
                "send_slack_message",
                "get_slack_user_info",
                "get_slack_channel_info",
                "get_thread_replies",
                "upload_file_to_slack",
                "pin_slack_message",
                "unpin_slack_message",
                "get_pinned_messages",
                "create_slack_channel",
                "archive_slack_channel",
                "invite_to_slack_channel",
                "update_slack_message",
                "delete_slack_message",
                "list_all_slack_users",
                "analyze_slack_channel",
            }

            gmail_tools = {
                "get_emails_from_sender",
                "get_email_by_subject",
                "search_gmail",
                "send_gmail",
                "get_full_email_content",
                "get_unread_email_count",
                "advanced_gmail_search",
                "get_complete_email_thread",
                "search_email_threads",
                "get_recent_email_thread_between_people",
                "list_gmail_attachments_for_message",
                "download_gmail_attachment",
                "send_gmail_with_attachments",
            }

            notion_tools = {
                "list_notion_pages",
                "get_notion_page_content",
                "update_notion_page_content",
                "search_notion_content",
                "create_notion_page",
                "append_to_notion_page",
                "list_notion_databases",
                "search_notion_workspace",
                "query_notion_database",
                "update_notion_database_item",
                "find_notion_entry",
                "update_notion_entry_by_name",
                "add_notion_database_entry",
                "delete_notion_database_entry",
            }

            project_workspace_tools = {
                "track_project",
                "generate_project_report",
                "update_project_notion_page",
                "search_workspace",
                "search_all_platforms",
                "get_team_activity_summary",
            }

            calendar_tools = {
                "list_calendar_events",
                "create_calendar_event",
                "update_calendar_event",
                "delete_calendar_event",
                "check_calendar_availability",
            }

            allow_slack = bool(source_prefs.get("slack", True)) if source_prefs else True
            allow_gmail = bool(source_prefs.get("gmail", True)) if source_prefs else True
            allow_notion = bool(source_prefs.get("notion", True)) if source_prefs else True

            wants_slack = allow_slack and any(k in q for k in ["slack", "#", "channel", "dm", "thread"])
            wants_gmail = allow_gmail and any(k in q for k in ["gmail", "email", "inbox", "subject:", "from:", "to:"])
            wants_notion = allow_notion and any(k in q for k in ["notion", "notion page", "database", "doc", "docs"])
            wants_project = any(k in q for k in ["project", "status", "milestone", "report"])
            wants_calendar = any(k in q for k in ["calendar", "schedule", "meeting", "event", "appointment", "available", "availability", "free time", "busy"])

            if not any([wants_slack, wants_gmail, wants_notion, wants_project, wants_calendar]):
                if source_prefs:
                    allowed_platform_tools: set[str] = set()
                    if allow_slack:
                        allowed_platform_tools.update(slack_tools)
                    if allow_gmail:
                        allowed_platform_tools.update(gmail_tools)
                    if allow_notion:
                        allowed_platform_tools.update(notion_tools)
                    allowed_platform_tools.update(project_workspace_tools)
                    allowed_platform_tools.update(calendar_tools)  # Always allow calendar tools

                    filtered_all: List[Dict[str, Any]] = []
                    for tool in self.tools:
                        fn = tool.get("function", {})
                        name = fn.get("name")
                        if name in allowed_platform_tools:
                            filtered_all.append(tool)
                    if filtered_all:
                        return filtered_all
                return self.tools

            allowed: set[str] = set()
            if wants_slack and allow_slack:
                allowed.update(slack_tools)
            if wants_gmail and allow_gmail:
                allowed.update(gmail_tools)
            if wants_notion and allow_notion:
                allowed.update(notion_tools)
            if wants_project:
                allowed.update(project_workspace_tools)
            if wants_calendar:
                allowed.update(calendar_tools)

            # Always allow workspace-wide search tools as a fallback
            allowed.update({"search_workspace", "search_all_platforms"})

            # Filter existing tools list
            filtered: List[Dict[str, Any]] = []
            for tool in self.tools:
                fn = tool.get("function", {})
                name = fn.get("name")
                if name in allowed:
                    filtered.append(tool)

            return filtered or self.tools
        except Exception as e:
            logger.warning(f"_select_tools_for_query failed, using full tool set: {e}")
            return self.tools

    async def stream_query(
        self,
        query: str,
        conversation_history: List[Dict] = None,
        user_email: Optional[str] = None,
        source_prefs: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Process a query and stream the response.
        
        Args:
            query: User query
            conversation_history: Previous conversation messages
            
        Yields:
            Stream events (tokens, tool calls, sources)
        """
        logger.info(f"Processing query: {query[:100]}...")
        
        # Build messages
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        if conversation_history:
            messages.extend(conversation_history)
        
        messages.append({"role": "user", "content": query})
        
        # First call to GPT-4 with tools
        try:
            tools_for_query = self._select_tools_for_query(query, source_prefs=source_prefs)
            first_call_kwargs = {
                "model": self.model,
                "messages": messages,
                "tools": tools_for_query,
                "tool_choice": "auto",
                "stream": True,
            }
            if not self.model.startswith("gpt-5"):
                first_call_kwargs["temperature"] = self.temperature
            response = await self.client.chat.completions.create(**first_call_kwargs)
            
            # Stream response
            function_name = None
            function_args = ""
            content_buffer = ""
            
            async for chunk in response:
                delta = chunk.choices[0].delta if chunk.choices else None
                
                if not delta:
                    continue
                
                # Handle content streaming
                if delta.content:
                    content_buffer += delta.content
                    yield {
                        "type": "token",
                        "content": delta.content
                    }
                
                # Handle tool calls
                if delta.tool_calls:
                    for tool_call in delta.tool_calls:
                        if tool_call.function:
                            if tool_call.function.name:
                                function_name = tool_call.function.name
                            if tool_call.function.arguments:
                                function_args += tool_call.function.arguments
            
            # MULTI-TOOL EXECUTION LOOP
            # Keep calling GPT until it stops requesting tools
            max_iterations = 5  # Prevent infinite loops
            iteration = 0
            
            while function_name and iteration < max_iterations:
                iteration += 1
                logger.info(f"Tool iteration {iteration}: {function_name}")

                # Parse arguments for richer reasoning/status messages
                try:
                    args = json.loads(function_args)
                except Exception:
                    args = {}

                # Build a high-level reasoning description for the UI
                try:
                    args_preview = json.dumps(args, ensure_ascii=False)
                except Exception:
                    args_preview = str(args) if args else ""

                # More natural, user-facing description inspired by "Thinking" UIs
                human_step = ""
                if function_name == "get_emails_from_sender":
                    sender = args.get("sender") or "the requested sender"
                    human_step = (
                        f"Step {iteration}: Reading recent emails from {sender} to understand what they've said and what might matter for your question."
                    )
                elif function_name == "get_email_by_subject":
                    subj = args.get("subject") or "the requested subject"
                    human_step = (
                        f"Step {iteration}: Finding emails about {subj} so I can pull in the exact messages you care about."
                    )
                elif function_name == "search_gmail":
                    q = args.get("query") or "your topic"
                    human_step = (
                        f"Step {iteration}: Searching Gmail for \"{q}\" to collect relevant threads and messages."
                    )
                elif function_name == "get_channel_messages":
                    channel = args.get("channel") or "the requested channel"
                    human_step = (
                        f"Step {iteration}: Reading messages from Slack channel {channel} to understand the discussion and decisions there."
                    )
                elif function_name == "summarize_slack_channel":
                    channel = args.get("channel") or "the requested channel"
                    human_step = (
                        f"Step {iteration}: Summarizing recent activity in Slack channel {channel} so I can see the key updates and action items."
                    )
                elif function_name == "search_slack":
                    q = args.get("query") or "your topic"
                    human_step = (
                        f"Step {iteration}: Searching Slack for \"{q}\" to find messages that are relevant to your request."
                    )
                elif function_name == "search_workspace":
                    q = args.get("query") or "your topic"
                    human_step = (
                        f"Step {iteration}: Searching across Slack, Gmail, and Notion for \"{q}\" to gather all the context I need."
                    )
                elif function_name == "list_notion_pages":
                    human_step = (
                        f"Step {iteration}: Listing recent Notion pages so I can see which documents might be relevant to your project."
                    )
                elif function_name == "search_notion_content":
                    q = args.get("query") or "your topic"
                    human_step = (
                        f"Step {iteration}: Reading Notion pages that mention \"{q}\" to pull in the right documents and notes."
                    )

                if not human_step:
                    human_step = (
                        f"Step {iteration}: Using tool `{function_name}` to gather information that will help answer your question."
                    )

                status_lines = [human_step]
                if args_preview:
                    status_lines.append(f"Internal tool call arguments: {args_preview}")
                status_lines.append(
                    "Next, I'll combine what I found here with earlier context to decide whether I need more tools or can synthesize a final answer."
                )

                yield {
                    "type": "status",
                    "content": "\n".join(status_lines),
                }

                # Execute tool (scoped to the caller's email and source preferences)
                tool_result = await self._execute_tool(
                    tool_name=function_name,
                    arguments=args,
                    user_email=user_email,
                    source_prefs=source_prefs,
                )
                
                # Add tool call and result to conversation
                messages.append({
                    "role": "assistant",
                    "content": content_buffer or None,
                    "tool_calls": [{
                        "id": f"call_{iteration}",
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": function_args
                        }
                    }]
                })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": f"call_{iteration}",
                    "name": function_name,
                    "content": tool_result
                })
                
                # Call GPT again - it may decide to call another tool or respond
                next_call_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools_for_query,
                    "tool_choice": "auto",
                    "stream": True,
                }
                if not self.model.startswith("gpt-5"):
                    next_call_kwargs["temperature"] = self.temperature
                next_response = await self.client.chat.completions.create(**next_call_kwargs)
                
                # Reset for next iteration
                function_name = None
                function_args = ""
                content_buffer = ""
                
                async for chunk in next_response:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    
                    if not delta:
                        continue
                    
                    # Stream content tokens
                    if delta.content:
                        content_buffer += delta.content
                        yield {
                            "type": "token",
                            "content": delta.content
                        }
                    
                    # Check if another tool is called
                    if delta.tool_calls:
                        for tool_call in delta.tool_calls:
                            if tool_call.function:
                                if tool_call.function.name:
                                    function_name = tool_call.function.name
                                if tool_call.function.arguments:
                                    function_args += tool_call.function.arguments
            
            # Generate reasoning summary if tools were used
            if iteration > 0:
                try:
                    summary_prompt = (
                        "In 3-5 concise bullet points, briefly summarize your approach to the user's request:\n"
                        "- What information you gathered (tools you used and why)\n"
                        "- How you analyzed the results\n"
                        "- Key insights or decisions you made\n"
                        "Keep it high-level and user-friendly. Don't repeat the final answer."
                    )
                    summary_kwargs = {
                        "model": self.model,
                        "messages": messages + [{"role": "user", "content": summary_prompt}],
                    }
                    # gpt-5 models use max_completion_tokens; older models use max_tokens
                    if self.model.startswith("gpt-5"):
                        summary_kwargs["max_completion_tokens"] = 300
                    else:
                        summary_kwargs["max_tokens"] = 300
                        summary_kwargs["temperature"] = 0.3
                    summary_response = await self.client.chat.completions.create(**summary_kwargs)
                    reasoning_summary = summary_response.choices[0].message.content
                    if reasoning_summary:
                        yield {
                            "type": "status",
                            "content": f"Reasoning Summary:\n{reasoning_summary}"
                        }
                except Exception as summary_error:
                    logger.warning(f"Failed to generate reasoning summary: {summary_error}")
            
            # Done
            yield {
                "type": "done",
                "content": ""
            }
        
        except Exception as e:
            logger.error(f"Query processing failed: {e}", exc_info=True)
            yield {
                "type": "error",
                "content": f"Error: {str(e)}"
            }
