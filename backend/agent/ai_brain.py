"""
Self-Aware AI Agent Brain for Workforce Agent.

This module implements a production-ready AI agent that:
1. Knows its identity and capabilities
2. Can use tools (Slack, Gmail, Notion)
3. Has access to RAG for context retrieval
4. Uses GPT-4 for better reasoning
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
SYSTEM_PROMPT = """You are the Workforce AI Assistant, an intelligent agent designed to help users manage their Slack, Gmail, and Notion workspace.

## YOUR IDENTITY
- Name: Workforce AI Assistant
- Purpose: Help users search, analyze, and take actions across their workspace tools
- Capabilities: You have direct access to Slack, Gmail, and Notion through API integrations

## YOUR TOOLS
You have access to 13 powerful tools to interact with the user's workspace:

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

### GMAIL TOOLS (4 tools)
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

### NOTION TOOLS (3 tools)
10. **list_notion_pages** - List Notion pages
    - Get list of pages in workspace
    - Example: "Show me my Notion pages"

11. **search_notion_content** - Search Notion
    - Find pages by content
    - Example: "Find Notion pages about meetings"

12. **create_notion_page** - Create Notion page
    - Create new pages with rich content
    - Example: "Save these notes to Notion"

### WORKSPACE SEARCH (1 tool)
13. **search_workspace** - Search EVERYTHING
    - Semantic search across Slack, Gmail, and Notion
    - Uses AI to find most relevant information
    - Example: "What did anyone say about Q4 across all platforms?"

## CAPABILITIES
- **SLACK**: List channels, get ALL messages, summarize channels, search, send messages
- **GMAIL**: Get emails from specific people, search by subject, broad search, send emails
- **NOTION**: List pages, search content, create new pages
- **WORKSPACE**: Cross-platform semantic search
- **INTELLIGENCE**: Can analyze, summarize, and provide insights from retrieved data
- **AUTOMATION**: Can perform actions (send, create) on behalf of user

## TOOL SELECTION GUIDE
- User asks "get all messages from #channel" → Use `get_channel_messages`
- User asks "summarize #channel" → Use `summarize_slack_channel`
- User asks "list channels" → Use `get_all_slack_channels`
- User asks "emails from person@email.com" → Use `get_emails_from_sender`
- User asks "find email about X" → Use `get_email_by_subject`
- User asks "what channels exist" → Use `get_all_slack_channels`
- User asks for summary → Get data first, then summarize in your response

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

## YOUR BEHAVIOR
1. **Be Proactive**: Understand user intent and suggest relevant actions
2. **Be Accurate**: Only use tools when you have the necessary information
3. **Be Transparent**: Explain what you're doing and why
4. **Be Helpful**: If you need more information, ask clarifying questions
5. **Be Efficient**: Use the most appropriate tool for each task

## EXAMPLES

User: "What did John say about the Q4 budget in Slack?"
You: I'll search for messages from John about Q4 budget in Slack.
[Use search_slack tool]

User: "Send a summary email to team@company.com"
You: I'll send an email to team@company.com with a summary. What would you like me to include in the summary?

User: "Create a Notion page with my meeting notes"
You: I'll create a Notion page for your meeting notes. Please provide the notes you'd like me to save.

## IMPORTANT RULES
- Always acknowledge the tool you're using
- If a tool fails, explain the error and suggest alternatives
- Never make up information - only use what's retrieved from tools
- Ask for clarification if the request is ambiguous
- Prioritize user privacy and data security

Now, help the user with their request!"""


class WorkforceAIBrain:
    """Self-aware AI agent with tool calling and RAG capabilities."""
    
    def __init__(
        self,
        openai_api_key: str,
        rag_engine: HybridRAGEngine,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7
    ):
        """Initialize the AI brain.
        
        Args:
            openai_api_key: OpenAI API key
            rag_engine: RAG engine for context retrieval
            model: OpenAI model to use (default: gpt-4o-mini - cost-efficient, Nov 2025)
                   Options: gpt-4o-mini (cheapest), gpt-4o (best), gpt-4-turbo (legacy)
            temperature: Model temperature (0.7 for balanced creativity)
        """
        self.client = AsyncOpenAI(api_key=openai_api_key)
        self.model = model
        self.temperature = temperature
        self.rag_engine = rag_engine
        self.tools_handler = WorkforceTools()
        
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
                            "channel": {"type": "string", "description": "Channel ID to archive"}
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
                            "text": {"type": "string", "description": "New message text"}
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
                            "timestamp": {"type": "string", "description": "Message timestamp"}
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
                            "content": {"type": "string", "description": "Content to append"}
                        },
                        "required": ["page_id", "content"]
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
    
    async def _execute_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Execute a tool and return the result.
        
        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments
            
        Returns:
            Tool result as string
        """
        logger.info(f"Executing tool: {tool_name}")
        logger.debug(f"Arguments: {arguments}")
        
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
                    limit=arguments.get("limit", 10)
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
            
            elif tool_name == "search_notion_content":
                result = self.tools_handler.search_notion_content(
                    query=arguments.get("query", "")
                )
            
            elif tool_name == "create_notion_page":
                result = self.tools_handler.create_notion_page(
                    title=arguments.get("title", ""),
                    content=arguments.get("content", "")
                )
            
            elif tool_name == "search_workspace":
                # Use RAG engine
                query = arguments.get("query", "")
                sources = arguments.get("sources", ["slack", "gmail"])
                
                rag_results = self.rag_engine._retrieve_context(query, top_k=5)
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
            
            elif tool_name == "search_notion_workspace":
                result = self.tools_handler.search_notion_workspace(
                    query=arguments.get("query", "")
                )
            
            # PROJECT TRACKING TOOLS
            elif tool_name == "track_project":
                result = await self.tools_handler.track_project(
                    project_name=arguments.get("project_name", ""),
                    days_back=arguments.get("days_back", 7),
                    notion_page_id=arguments.get("notion_page_id")
                )
            
            elif tool_name == "generate_project_report":
                result = await self.tools_handler.generate_project_report(
                    project_name=arguments.get("project_name", ""),
                    days_back=arguments.get("days_back", 7)
                )
            
            elif tool_name == "update_project_notion_page":
                result = await self.tools_handler.update_project_notion_page(
                    page_id=arguments.get("page_id", ""),
                    project_name=arguments.get("project_name", ""),
                    days_back=arguments.get("days_back", 7)
                )
            
            # UTILITY TOOLS
            elif tool_name == "search_all_platforms":
                result = await self.tools_handler.search_all_platforms(
                    query=arguments.get("query", ""),
                    limit_per_platform=arguments.get("limit_per_platform", 10)
                )
            
            elif tool_name == "get_team_activity_summary":
                result = await self.tools_handler.get_team_activity_summary(
                    person_name=arguments.get("person_name", ""),
                    days_back=arguments.get("days_back", 7)
                )
            
            elif tool_name == "analyze_slack_channel":
                result = await self.tools_handler.analyze_slack_channel(
                    channel=arguments.get("channel", ""),
                    days_back=arguments.get("days_back", 7)
                )
            
            else:
                result = f"Unknown tool: {tool_name}"
            
            logger.info(f"Tool {tool_name} executed successfully")
            return str(result)
        
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return f"Tool execution error: {str(e)}"
    
    async def stream_query(self, query: str, conversation_history: List[Dict] = None) -> AsyncIterator[Dict[str, Any]]:
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
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=self.tools,
                tool_choice="auto",
                temperature=self.temperature,
                stream=True
            )
            
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
                
                yield {
                    "type": "status",
                    "content": f"Step {iteration}: Using {function_name}..."
                }
                
                # Parse arguments
                try:
                    args = json.loads(function_args)
                except:
                    args = {}
                
                # Execute tool
                tool_result = await self._execute_tool(function_name, args)
                
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
                next_response = await self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=self.tools,
                    tool_choice="auto",
                    temperature=self.temperature,
                    stream=True
                )
                
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
