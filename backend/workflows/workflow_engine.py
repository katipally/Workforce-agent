"""
Modular Workflow Execution Engine.

Executes workflows with three blocks:
1. Source Block: Fetches data from Slack, Gmail, Notion
2. AI Prompt Block: Processes data with LLM
3. Output Block: Sends results to destination (Notion, Slack, Gmail, etc.)
"""

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from openai import AsyncOpenAI

from config import Config
from core.database.db_manager import DatabaseManager
from utils.logger import get_logger

logger = get_logger(__name__)

# System prompt for intelligent AI agent workflow execution
AI_AGENT_SYSTEM_PROMPT = """You are an advanced AI workflow agent with full access to Slack, Gmail, Notion, and Calendar APIs.

## YOUR CAPABILITIES
You can read from and write to:
- **Slack**: Read messages, channels, users, threads, reactions. Send messages, reply to threads, react to messages.
- **Gmail**: Read emails, search inbox, get attachments. Send emails, create drafts.
- **Notion**: Read pages, databases, blocks, comments. Create pages, add database rows, update content, create subpages.
- **Calendar**: Read events, check availability. Create events, update events, delete events.

## INPUT FORMAT
You will receive:
1. **SOURCE DATA**: Information fetched from configured sources (Slack channels, Gmail labels, Notion pages)
2. **DESTINATION STATE**: Current state of output targets (page content, database schema, existing rows)
3. **USER INSTRUCTIONS**: Main workflow instructions
4. **OUTPUT INSTRUCTIONS**: Specific instructions for each output destination

## OUTPUT FORMAT
You MUST respond in exactly this format:

### THINKING
Explain your analysis step-by-step:
1. What data did you receive from sources?
2. What is the current state of destinations?
3. What do the user's instructions require?
4. What specific actions will accomplish this?

### ACTIONS_TAKEN
List what you are doing in human-readable form:
- "Reading 15 messages from #engineering channel"
- "Found 3 action items that need to be tracked"
- "Adding 3 new rows to the Tasks database"
- "Updating the 'Last Synced' field on the summary page"

### ACTIONS
```json
[
  {"type": "action_type", "parameters": {...}, "reason": "why this action"}
]
```

## AVAILABLE ACTIONS

### Notion Actions
- `{"type": "update_page_content", "page_id": "...", "content": "...", "strategy": "replace|append"}`
- `{"type": "add_database_row", "database_id": "...", "properties": {"Column": "value", ...}}`
- `{"type": "update_database_row", "page_id": "row_page_id", "properties": {"Column": "new_value"}}`
- `{"type": "create_subpage", "parent_id": "...", "title": "...", "content": "..."}`
- `{"type": "create_page", "title": "...", "content": "..."}`
- `{"type": "add_comment", "page_id": "...", "comment": "..."}`

### Slack Actions
- `{"type": "send_slack_message", "channel": "channel_id_or_name", "message": "..."}`
- `{"type": "reply_to_thread", "channel": "...", "thread_ts": "...", "message": "..."}`
- `{"type": "add_reaction", "channel": "...", "timestamp": "...", "emoji": "white_check_mark"}`

### Gmail Actions
- `{"type": "send_email", "to": "...", "subject": "...", "body": "..."}`
- `{"type": "create_draft", "to": "...", "subject": "...", "body": "..."}`

### Control Actions
- `{"type": "no_action", "reason": "..."}`

## RULES
1. Always explain your reasoning in THINKING section
2. List human-readable actions in ACTIONS_TAKEN
3. Use exact IDs from destination state (don't make up IDs)
4. For databases, match property names exactly as shown in schema
5. Process ALL relevant source data - don't skip items
6. If no action needed, use no_action with clear reason
7. Be thorough but concise
"""


TOOL_CALLING_SYSTEM_PROMPT = """You are an AI agent executing an automated workflow that syncs data between apps.

## EXECUTION PROCESS (follow strictly)

### Phase 1: UNDERSTAND SOURCE DATA
- Read and analyze the source data provided (Slack messages, Gmail emails, etc.)
- Extract key information: status changes, action items, dates, people, decisions
- Identify what has changed since last sync

### Phase 2: UNDERSTAND DESTINATION STRUCTURE
- Before writing ANYTHING, first query the destination to understand its structure
- For Notion databases: use `query_notion_database` to see the schema, existing rows, and current values
- For Notion pages: use `get_notion_structured_context` to see the page structure, sections, and content
- Identify WHERE updates should go (which row, which field, which section)
 - If the destination is a Notion database row page, and you need to query the database, use the **Parent Database ID** from destination state (do NOT pass the row page_id to `query_notion_database`).

### Phase 3: PLAN TARGETED UPDATES
- Determine exactly what needs to change based on source vs destination comparison
- Plan specific updates: which field to change, what value to set
- DO NOT plan to append raw summaries - plan to UPDATE specific fields/rows

### Phase 4: EXECUTE PRECISE UPDATES
For Notion destinations:

1) If the destination is a **Notion database row page** (a page whose parent is a database_id):
- Update the **page properties** (Status / Next Step / values) using entry_id-based tools.
- Prefer `update_notion_database_entry_properties` (multi-field) or `update_notion_database_entry` (single-field).
- Do NOT replace or rewrite the page body. Do NOT remove headings/toggles.

2) If the destination is a **Notion database** (database_id):
- Update a specific row by entry_id (preferred) or by name if unambiguous.
- Create a new row only if no existing row matches.

3) Only if the destination is a **regular Notion page** (not a database row):
- Prefer targeted edits using block-level tools.
- Use `replace_notion_page_content` ONLY when the workflow output explicitly configured mode='replace'.

## CRITICAL RULES

1. **NEVER append raw AI thinking/planning to destinations** - Users don't want to see "### THINKING" or "### ACTIONS_TAKEN" in their Notion pages

2. **Update existing data, don't just append** - If a Status field says "Waiting for files" and files arrived, UPDATE the Status to "Files received", don't append text saying "files were received"

3. **Match destination schema** - If Notion has a "Status" select field, update THAT field. If it has a "Next Steps" text field, update THAT field. Don't create unstructured text.

4. **Be surgical** - Only change what needs to change. If source says "project paused", update the Status field to "Paused" and maybe Next Steps to the reason - don't rewrite the whole page.

5. **Respect field types** - Select fields need valid option values; dates need date format; multi-select needs array format.

## OUTPUT FORMAT
Always include a **PLAN** section (at least 3 bullet points) in the assistant message before any tool calls.
Always include an **Update status:** line (e.g. "Update status: No changes required" or "Update status: Updated Status and Next Step").
This is for logs/UI only; it is NOT written to destinations.
"""


class WorkflowCancelledException(Exception):
    """Raised when a workflow run is cancelled by user."""
    pass


class WorkflowExecutionEngine:
    """Executes modular workflows with Source → AI → Output pipeline."""

    def __init__(self, db_manager: DatabaseManager, user_id: str):
        self.db_manager = db_manager
        self.user_id = user_id
        self.openai_client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)

    async def close(self) -> None:
        try:
            client = getattr(self, "openai_client", None)
            if client and hasattr(client, "close"):
                await client.close()
        except Exception:
            return

    def _check_cancelled(self, run_id: str) -> None:
        """Check if the run has been cancelled and raise exception if so."""
        run = self.db_manager.get_workflow_run(run_id)
        if run and run.status == "cancelled":
            raise WorkflowCancelledException("Workflow cancelled by user")

    async def _chat_completion(
        self,
        *,
        model: str,
        messages: List[Dict[str, str]],
        max_output_tokens: int,
        temperature: Optional[float] = None,
        run_id: Optional[str] = None,
    ) -> str:
        """Create a chat completion with model-specific token parameter compatibility.

        - gpt-5-* models: use `max_completion_tokens` (sent via extra_body for SDK compatibility)
        - other models: use `max_tokens`
        """
        create_fn = self.openai_client.chat.completions.create
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
        }

        if model.startswith("gpt-5"):
            # Many installed SDK versions don't accept max_completion_tokens as a keyword yet.
            # extra_body is the forward-compatible way to pass it through to the API.
            kwargs["extra_body"] = {"max_completion_tokens": max_output_tokens}
        else:
            kwargs["max_tokens"] = max_output_tokens
            if temperature is not None:
                kwargs["temperature"] = temperature

        try:
            response = await create_fn(**kwargs)
            return response.choices[0].message.content or ""
        except TypeError as e:
            # If the SDK doesn't accept extra_body, we can't safely call gpt-5 models.
            if model.startswith("gpt-5"):
                msg = (
                    "OpenAI SDK does not support required gpt-5 parameters. "
                    "Please upgrade the `openai` Python package to a newer version. "
                    f"Original error: {e}"
                )
                if run_id:
                    self._log(run_id, "error", msg)
                raise

            # Non-gpt-5 fallback: try again without extra_body.
            kwargs.pop("extra_body", None)
            response = await create_fn(**kwargs)
            return response.choices[0].message.content or ""

    async def _chat_completion_with_tools(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        max_output_tokens: int,
        temperature: Optional[float] = None,
        run_id: Optional[str] = None,
    ):
        """Chat completion that supports OpenAI tool calling, with gpt-5 token param compatibility."""
        create_fn = self.openai_client.chat.completions.create
        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
        }

        if model.startswith("gpt-5"):
            kwargs["extra_body"] = {"max_completion_tokens": max_output_tokens}
        else:
            kwargs["max_tokens"] = max_output_tokens
            if temperature is not None:
                kwargs["temperature"] = temperature

        try:
            return await create_fn(**kwargs)
        except TypeError as e:
            if model.startswith("gpt-5"):
                msg = (
                    "OpenAI SDK does not support required gpt-5 tool-calling parameters. "
                    "Please upgrade the `openai` Python package to a newer version. "
                    f"Original error: {e}"
                )
                if run_id:
                    self._log(run_id, "error", msg)
            raise

    def _workflow_tools_schema(
        self,
        output_config: Dict[str, Any],
        notion_row_page_targets: Optional[set[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Tool schema exposed to the LLM during workflow runs.

        We always allow read/search tools. Write tools are limited to the selected
        output destinations so the agent cannot write somewhere the user didn't select.
        """

        allowed_writes: set[str] = set()
        for o in output_config.get("outputs", []):
            t = (o.get("type") or "").lower()
            if t == "slack_message":
                allowed_writes.add("send_slack_message")
                allowed_writes.add("add_slack_reaction")
            elif t == "gmail_draft":
                allowed_writes.add("create_gmail_draft")
            elif t == "notion_page":
                target_page_id = o.get("page_id")
                is_row_page = bool(target_page_id and notion_row_page_targets and target_page_id in notion_row_page_targets)
                allow_body_edits = bool(o.get("allow_body_edits"))

                allowed_writes.add("update_notion_entry_by_name")
                allowed_writes.add("update_notion_database_entry")
                allowed_writes.add("update_notion_database_entry_properties")

                if allow_body_edits and target_page_id:
                    allowed_writes.add("upsert_notion_toggle_section")

                if not is_row_page:
                    allowed_writes.add("append_to_notion_page")
                    mode = (o.get("mode") or "append").lower()
                    if mode == "replace":
                        allowed_writes.add("replace_notion_page_content")
                    allowed_writes.add("update_notion_database_row_content")
                    allowed_writes.add("update_notion_database_schema")
                    allowed_writes.add("update_notion_todo_checked")
                    allowed_writes.add("update_notion_block_text")
                    allowed_writes.add("add_notion_database_entry")
                    allowed_writes.add("delete_notion_database_entry")
                # If no target page provided, allow creation.
                if not o.get("page_id"):
                    allowed_writes.add("create_notion_page")

        base_tools: List[Dict[str, Any]] = [
            {
                "type": "function",
                "function": {
                    "name": "search_slack",
                    "description": "Search Slack messages for a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "channel": {"type": "string"},
                            "limit": {"type": "integer", "default": 10},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_channel_messages",
                    "description": "Get recent Slack messages for a channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string"},
                            "limit": {"type": "integer", "default": 100},
                        },
                        "required": ["channel"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_thread_replies",
                    "description": "Get replies for a Slack thread.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string"},
                            "thread_ts": {"type": "string"},
                        },
                        "required": ["channel", "thread_ts"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "search_gmail",
                    "description": "Search Gmail using a query.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string"},
                            "limit": {"type": "integer", "default": 10},
                        },
                        "required": ["query"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_full_email_content",
                    "description": "Get full Gmail message content by message_id.",
                    "parameters": {
                        "type": "object",
                        "properties": {"message_id": {"type": "string"}},
                        "required": ["message_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_notion_page_content",
                    "description": "Get Notion page content.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string"},
                            "include_subpages": {"type": "boolean", "default": False},
                            "max_blocks": {"type": "integer", "default": 500},
                        },
                        "required": ["page_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_notion_page_outline",
                    "description": "Get a lightweight outline of a Notion page with toggle/heading sections and their block IDs. Use this before editing dropdown/toggle sections.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string"},
                            "max_depth": {"type": "integer", "default": 2},
                        },
                        "required": ["page_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_notion_pages",
                    "description": "List Notion pages.",
                    "parameters": {
                        "type": "object",
                        "properties": {"limit": {"type": "integer", "default": 20}},
                        "required": [],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "query_notion_database",
                    "description": "Query a Notion database and return matching rows.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {"type": "string"},
                            "filter_json": {"type": "string"},
                            "sort_json": {"type": "string"},
                            "search_text": {"type": "string", "description": "Optional: simple text search across row properties (preferred over filter_json if you are unsure)."},
                            "page_size": {"type": "integer", "default": 50},
                        },
                        "required": ["database_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_notion_structured_context",
                    "description": "Get structured JSON context of a Notion page or database with all IDs for precise edits. Use this before making targeted updates.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string", "description": "Notion page or database ID"},
                            "include_blocks": {"type": "boolean", "default": True},
                            "include_database_rows": {"type": "boolean", "default": True},
                            "max_depth": {"type": "integer", "default": 3},
                        },
                        "required": ["page_id"],
                    },
                },
            },
        ]

        write_tool_defs: Dict[str, Dict[str, Any]] = {
            "send_slack_message": {
                "type": "function",
                "function": {
                    "name": "send_slack_message",
                    "description": "Send a Slack message to a channel.",
                    "parameters": {
                        "type": "object",
                        "properties": {"channel": {"type": "string"}, "text": {"type": "string"}},
                        "required": ["channel", "text"],
                    },
                },
            },
            "add_slack_reaction": {
                "type": "function",
                "function": {
                    "name": "add_slack_reaction",
                    "description": "Add an emoji reaction to a Slack message.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "channel": {"type": "string"},
                            "timestamp": {"type": "string"},
                            "emoji": {"type": "string"},
                        },
                        "required": ["channel", "timestamp", "emoji"],
                    },
                },
            },
            "create_gmail_draft": {
                "type": "function",
                "function": {
                    "name": "create_gmail_draft",
                    "description": "Create a Gmail draft (does not send).",
                    "parameters": {
                        "type": "object",
                        "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
                        "required": ["to", "subject", "body"],
                    },
                },
            },
            "create_notion_page": {
                "type": "function",
                "function": {
                    "name": "create_notion_page",
                    "description": "Create a Notion page.",
                    "parameters": {
                        "type": "object",
                        "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["title", "content"],
                    },
                },
            },
            "append_to_notion_page": {
                "type": "function",
                "function": {
                    "name": "append_to_notion_page",
                    "description": "Append content to a Notion page.",
                    "parameters": {
                        "type": "object",
                        "properties": {"page_id": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["page_id", "content"],
                    },
                },
            },
            "upsert_notion_toggle_section": {
                "type": "function",
                "function": {
                    "name": "upsert_notion_toggle_section",
                    "description": "Safely create or update a toggle/dropdown section inside a Notion page by section title. Only edits that section's children and preserves the rest of the page.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "page_id": {"type": "string"},
                            "section_title": {"type": "string"},
                            "content": {"type": "string"},
                            "replace_children": {"type": "boolean", "default": True},
                            "max_depth": {"type": "integer", "default": 3},
                        },
                        "required": ["page_id", "section_title", "content"],
                    },
                },
            },
            "replace_notion_page_content": {
                "type": "function",
                "function": {
                    "name": "replace_notion_page_content",
                    "description": "Replace the content of a Notion page.",
                    "parameters": {
                        "type": "object",
                        "properties": {"page_id": {"type": "string"}, "content": {"type": "string"}},
                        "required": ["page_id", "content"],
                    },
                },
            },
            "update_notion_database_row_content": {
                "type": "function",
                "function": {
                    "name": "update_notion_database_row_content",
                    "description": "Update a specific Notion database row's page content by row title.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {"type": "string"},
                            "entry_name": {"type": "string"},
                            "entry_id": {"type": "string"},
                            "content": {"type": "string"},
                            "mode": {"type": "string", "default": "replace"},
                        },
                        "required": ["database_id", "entry_name", "content"],
                    },
                },
            },
            "update_notion_entry_by_name": {
                "type": "function",
                "function": {
                    "name": "update_notion_entry_by_name",
                    "description": "Update a specific property of a Notion database entry by name. Use for changing status, checkbox, numbers, dates, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {"type": "string", "description": "Database ID"},
                            "entry_name": {"type": "string", "description": "Row/entry name to find"},
                            "entry_id": {"type": "string", "description": "Optional: exact row page ID to update (recommended in workflows)"},
                            "property_name": {"type": "string", "description": "Property/column name to update"},
                            "new_value": {"type": "string", "description": "New value"},
                            "property_type": {"type": "string", "description": "Optional: number, text, select, date, checkbox, url"},
                        },
                        "required": ["database_id", "entry_name", "property_name", "new_value"],
                    },
                },
            },
            "update_notion_database_entry": {
                "type": "function",
                "function": {
                    "name": "update_notion_database_entry",
                    "description": "Update a specific property of a Notion database row by entry/page ID (recommended for workflows).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entry_id": {"type": "string", "description": "Row page ID"},
                            "property_name": {"type": "string", "description": "Property/column name to update"},
                            "new_value": {"description": "New value"},
                            "property_type": {"type": "string", "description": "Optional: title, rich_text, number, select, status, date, checkbox, url, email"},
                        },
                        "required": ["entry_id", "property_name", "new_value"],
                    },
                },
            },
            "update_notion_database_entry_properties": {
                "type": "function",
                "function": {
                    "name": "update_notion_database_entry_properties",
                    "description": "Update multiple properties of a Notion database row by entry/page ID in one call. updates_json should be a JSON object of property_name -> value.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entry_id": {"type": "string", "description": "Row page ID"},
                            "updates_json": {"type": "string", "description": "JSON object mapping property names to values"},
                        },
                        "required": ["entry_id", "updates_json"],
                    },
                },
            },
            "update_notion_database_schema": {
                "type": "function",
                "function": {
                    "name": "update_notion_database_schema",
                    "description": "Add, rename, or remove columns in a Notion database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {"type": "string"},
                            "add_columns": {"type": "object", "description": "Dict of column_name: type (rich_text, number, select, checkbox, date, url, email, files, people)"},
                            "rename_columns": {"type": "object", "description": "Dict of old_name: new_name"},
                            "remove_columns": {"type": "array", "items": {"type": "string"}, "description": "List of column names to remove"},
                        },
                        "required": ["database_id"],
                    },
                },
            },
            "update_notion_todo_checked": {
                "type": "function",
                "function": {
                    "name": "update_notion_todo_checked",
                    "description": "Check or uncheck a to-do item in Notion. Use get_notion_structured_context first to get block IDs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "block_id": {"type": "string", "description": "The to_do block ID"},
                            "checked": {"type": "boolean", "description": "True to check, False to uncheck"},
                        },
                        "required": ["block_id", "checked"],
                    },
                },
            },
            "update_notion_block_text": {
                "type": "function",
                "function": {
                    "name": "update_notion_block_text",
                    "description": "Update the text content of a Notion block. Use get_notion_structured_context first to get block IDs.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "block_id": {"type": "string", "description": "The block ID to update"},
                            "new_text": {"type": "string", "description": "New text content"},
                        },
                        "required": ["block_id", "new_text"],
                    },
                },
            },
            "add_notion_database_entry": {
                "type": "function",
                "function": {
                    "name": "add_notion_database_entry",
                    "description": "Add a new row/entry to a Notion database.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "database_id": {"type": "string"},
                            "properties": {"type": "object", "description": "Dict of property_name: value pairs"},
                        },
                        "required": ["database_id", "properties"],
                    },
                },
            },
            "delete_notion_database_entry": {
                "type": "function",
                "function": {
                    "name": "delete_notion_database_entry",
                    "description": "Archive (delete) a Notion database entry by ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "entry_id": {"type": "string", "description": "Entry/page ID to archive"},
                        },
                        "required": ["entry_id"],
                    },
                },
            },
        }

        for name in sorted(allowed_writes):
            tool_def = write_tool_defs.get(name)
            if tool_def:
                base_tools.append(tool_def)

        return base_tools

    def _execute_workflow_tool(
        self,
        tools_handler,
        tool_name: str,
        arguments: Dict[str, Any],
        run_id: str,
        gmail_account_email: Optional[str],
    ) -> str:
        """Execute one tool by name against WorkforceTools."""
        try:
            args_preview = json.dumps(arguments, ensure_ascii=False)
        except Exception:
            args_preview = str(arguments)
        self._log(run_id, "info", f"Agent tool: {tool_name} {args_preview}")

        if tool_name == "search_slack":
            return tools_handler.search_slack_messages(
                query=arguments.get("query", ""),
                channel=arguments.get("channel") or None,
                limit=int(arguments.get("limit", 10) or 10),
                workflow_mode=True,
            )
        if tool_name == "get_channel_messages":
            return tools_handler.get_channel_messages(
                channel=arguments.get("channel", ""),
                limit=int(arguments.get("limit", 100) or 100),
                workflow_mode=True,
            )
        if tool_name == "get_thread_replies":
            return tools_handler.get_thread_replies(
                channel=arguments.get("channel", ""),
                thread_ts=arguments.get("thread_ts", ""),
            )
        if tool_name == "send_slack_message":
            return tools_handler.send_slack_message(
                channel=arguments.get("channel", ""),
                text=arguments.get("text", ""),
            )
        if tool_name == "add_slack_reaction":
            return tools_handler.add_slack_reaction(
                channel=arguments.get("channel", ""),
                timestamp=arguments.get("timestamp", ""),
                emoji=arguments.get("emoji", ""),
            )
        if tool_name == "search_gmail":
            return tools_handler.search_gmail_messages(
                query=arguments.get("query", ""),
                limit=int(arguments.get("limit", 10) or 10),
                gmail_account_email=gmail_account_email,
            )
        if tool_name == "get_full_email_content":
            return tools_handler.get_full_email_content(
                message_id=arguments.get("message_id", "")
            )
        if tool_name == "create_gmail_draft":
            return tools_handler.create_gmail_draft(
                to=arguments.get("to", ""),
                subject=arguments.get("subject", ""),
                body=arguments.get("body", ""),
            )
        if tool_name == "list_notion_pages":
            return tools_handler.list_notion_pages(limit=int(arguments.get("limit", 20) or 20))
        if tool_name == "get_notion_page_content":
            return tools_handler.get_notion_page_content(
                page_id=arguments.get("page_id", ""),
                include_subpages=bool(arguments.get("include_subpages", False)),
                max_blocks=int(arguments.get("max_blocks", 500) or 500),
            )
        if tool_name == "get_notion_page_outline":
            return tools_handler.get_notion_page_outline(
                page_id=arguments.get("page_id", ""),
                max_depth=int(arguments.get("max_depth", 2) or 2),
            )
        if tool_name == "query_notion_database":
            return tools_handler.query_notion_database(
                database_id=arguments.get("database_id", ""),
                filter_json=arguments.get("filter_json"),
                sort_json=arguments.get("sort_json"),
                search_text=arguments.get("search_text"),
                page_size=int(arguments.get("page_size", 50) or 50),
            )
        if tool_name == "create_notion_page":
            return tools_handler.create_notion_page(
                title=arguments.get("title", ""),
                content=arguments.get("content", ""),
            )
        if tool_name == "append_to_notion_page":
            return tools_handler.append_to_notion_page(
                page_id=arguments.get("page_id", ""),
                content=arguments.get("content", ""),
            )
        if tool_name == "upsert_notion_toggle_section":
            return tools_handler.upsert_notion_toggle_section(
                page_id=arguments.get("page_id", ""),
                section_title=arguments.get("section_title", ""),
                content=arguments.get("content", ""),
                replace_children=bool(arguments.get("replace_children", True)),
                max_depth=int(arguments.get("max_depth", 3) or 3),
                workflow_mode=True,
            )
        if tool_name == "replace_notion_page_content":
            return tools_handler.replace_notion_page_content(
                page_id=arguments.get("page_id", ""),
                content=arguments.get("content", ""),
            )
        if tool_name == "update_notion_database_row_content":
            return tools_handler.update_notion_database_row_content(
                database_id=arguments.get("database_id", ""),
                entry_name=arguments.get("entry_name", ""),
                entry_id=arguments.get("entry_id") or None,
                content=arguments.get("content", ""),
                mode=arguments.get("mode", "replace"),
                workflow_mode=True,
            )
        
        # Advanced Notion tools - Dec 2025
        if tool_name == "get_notion_structured_context":
            result = tools_handler.get_notion_structured_context(
                page_id=arguments.get("page_id", ""),
                include_blocks=bool(arguments.get("include_blocks", True)),
                include_database_rows=bool(arguments.get("include_database_rows", True)),
                max_depth=int(arguments.get("max_depth", 3) or 3),
            )
            self._log(run_id, "info", f"Retrieved structured Notion context for {arguments.get('page_id', '')}")
            return result
        
        if tool_name == "update_notion_database_schema":
            result = tools_handler.update_notion_database_schema(
                database_id=arguments.get("database_id", ""),
                add_columns=arguments.get("add_columns"),
                rename_columns=arguments.get("rename_columns"),
                remove_columns=arguments.get("remove_columns"),
            )
            self._log(run_id, "info", f"Schema update result: {result}")
            return result
        
        if tool_name == "update_notion_todo_checked":
            result = tools_handler.update_notion_todo_checked(
                block_id=arguments.get("block_id", ""),
                checked=bool(arguments.get("checked", False)),
            )
            self._log(run_id, "info", f"To-do update result: {result}")
            return result
        
        if tool_name == "update_notion_block_text":
            result = tools_handler.update_notion_block_text(
                block_id=arguments.get("block_id", ""),
                new_text=arguments.get("new_text", ""),
            )
            self._log(run_id, "info", f"Block text update result: {result}")
            return result
        
        if tool_name == "update_notion_entry_by_name":
            result = tools_handler.update_notion_entry_by_name(
                database_id=arguments.get("database_id", ""),
                entry_name=arguments.get("entry_name", ""),
                entry_id=arguments.get("entry_id") or None,
                property_name=arguments.get("property_name", ""),
                new_value=arguments.get("new_value"),
                property_type=arguments.get("property_type"),
                workflow_mode=True,
            )
            self._log(run_id, "info", f"Entry property update result: {result}")
            return result

        if tool_name == "update_notion_database_entry":
            result = tools_handler.update_notion_database_entry(
                entry_id=arguments.get("entry_id", ""),
                property_name=arguments.get("property_name", ""),
                new_value=arguments.get("new_value"),
                property_type=arguments.get("property_type"),
            )
            self._log(run_id, "info", f"Entry property update result: {result}")
            return result

        if tool_name == "update_notion_database_entry_properties":
            result = tools_handler.update_notion_database_entry_properties(
                entry_id=arguments.get("entry_id", ""),
                updates_json=arguments.get("updates_json", ""),
            )
            self._log(run_id, "info", f"Entry properties update result: {result}")
            return result
        
        if tool_name == "add_notion_database_entry":
            result = tools_handler.add_notion_database_entry(
                database_id=arguments.get("database_id", ""),
                properties=arguments.get("properties", {}),
            )
            self._log(run_id, "info", f"New entry result: {result}")
            return result
        
        if tool_name == "delete_notion_database_entry":
            result = tools_handler.delete_notion_database_entry(
                entry_id=arguments.get("entry_id", ""),
            )
            self._log(run_id, "info", f"Delete entry result: {result}")
            return result

        return f"Unknown tool: {tool_name}"

    def _parse_conflict_result(self, result: Any) -> Optional[Dict[str, Any]]:
        """Detect a structured conflict result returned by a tool.

        Tools may return a JSON string like:
        {"__workforce_conflict__": true, "options": [...], ...}
        """
        if not isinstance(result, str):
            return None
        try:
            data = json.loads(result)
        except Exception:
            return None
        if isinstance(data, dict) and data.get("__workforce_conflict__") is True:
            return data
        return None

    async def _run_tool_calling_agent(
        self,
        *,
        source_data: str,
        destination_state: str,
        prompt_config: Dict[str, Any],
        output_config: Dict[str, Any],
        run_id: str,
        resume_state: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run an OpenAI tool-calling loop to decide and execute actions.

        Returns dict with keys:
        - final_response: assistant final message
        - tool_calls: list of executed tool calls
        - iterations: number of tool iterations
        """
        from agent.langchain_tools import WorkforceTools

        tools_handler = WorkforceTools(user_id=self.user_id)
        gmail_account_email = None
        try:
            gmail_account_email = getattr(getattr(tools_handler, "gmail_client", None), "user_email", None)
        except Exception:
            gmail_account_email = None

        user_instructions = prompt_config.get("user_instructions", "")
        output_instructions = []
        for i, out in enumerate(output_config.get("outputs", [])):
            otype = out.get("type")
            oprompt = out.get("output_prompt")
            if oprompt:
                output_instructions.append(f"Output {i+1} ({otype}): {oprompt}")

        outputs_summary = json.dumps(output_config.get("outputs", []), ensure_ascii=False)
        out_instr = "\n".join(output_instructions) if output_instructions else ""

        notion_row_page_targets: set[str] = set()
        if Config.NOTION_TOKEN:
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                    "Notion-Version": Config.NOTION_VERSION,
                }
                for o in output_config.get("outputs", []):
                    if (o.get("type") == "notion_page") and o.get("page_id"):
                        pid = o.get("page_id")
                        try:
                            resp = requests.get(
                                f"https://api.notion.com/v1/pages/{pid}",
                                headers=headers,
                                timeout=12,
                            )
                            if resp.status_code == 200:
                                parent = (resp.json() or {}).get("parent", {}) or {}
                                if parent.get("type") in {"database_id", "data_source_id"}:
                                    notion_row_page_targets.add(pid)
                        except Exception:
                            continue
            except Exception:
                notion_row_page_targets = set()

        tool_schema = self._workflow_tools_schema(
            output_config,
            notion_row_page_targets=notion_row_page_targets,
        )

        allowed_notion_targets = {
            o.get("page_id")
            for o in output_config.get("outputs", [])
            if (o.get("type") == "notion_page" and o.get("page_id"))
        }
        allow_body_edit_targets = {
            o.get("page_id")
            for o in output_config.get("outputs", [])
            if (o.get("type") == "notion_page" and o.get("page_id") and bool(o.get("allow_body_edits")))
        }
        allow_create_notion_page = any(
            (o.get("type") == "notion_page" and not o.get("page_id"))
            for o in output_config.get("outputs", [])
        )

        if resume_state:
            messages = list(resume_state.get("messages") or [])
            executed_calls = list(resume_state.get("executed_calls") or [])
            iterations = int(resume_state.get("iterations") or 0)
            plan_candidate = str(resume_state.get("plan_candidate") or "")
        else:
            messages = [
                {"role": "system", "content": TOOL_CALLING_SYSTEM_PROMPT},
                {"role": "system", "content": "Workflow outputs configuration (do not write elsewhere):\n" + outputs_summary},
            ]

            user_prompt = (
                "## SOURCE DATA\n" + (source_data[:10000] or "") +
                "\n\n## DESTINATION STATE\n" + (destination_state[:5000] or "") +
                "\n\n## USER INSTRUCTIONS\n" + (user_instructions or "") +
                ("\n\n## OUTPUT-SPECIFIC INSTRUCTIONS\n" + out_instr if out_instr else "") +
                "\n\nUse tool calling to perform any required writes. Finish with a short summary."
            )
            messages.append({"role": "user", "content": user_prompt})

            executed_calls = []
            iterations = 0
            plan_candidate = ""

        max_iterations = 8

        while iterations < max_iterations:
            iterations += 1
            self._check_cancelled(run_id)

            resp = await self._chat_completion_with_tools(
                model="gpt-5-nano",
                messages=messages,
                tools=tool_schema,
                max_output_tokens=3500,
                temperature=0.5,
                run_id=run_id,
            )

            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None) or []
            content = getattr(msg, "content", None) or ""

            if content and not plan_candidate:
                plan_candidate = content[:4000]

            if not tool_calls:
                return {
                    "final_response": content,
                    "tool_calls": executed_calls,
                    "iterations": iterations,
                    "plan": plan_candidate,
                }

            assistant_tool_calls: List[Dict[str, Any]] = []
            for tc in tool_calls:
                fn = getattr(tc, "function", None)
                name = getattr(fn, "name", None) if fn else None
                arg_str = getattr(fn, "arguments", "{}") if fn else "{}"
                tc_id = getattr(tc, "id", None) or f"call_{iterations}_{len(assistant_tool_calls)}"
                assistant_tool_calls.append(
                    {
                        "id": tc_id,
                        "type": "function",
                        "function": {"name": name, "arguments": arg_str},
                    }
                )

            messages.append({"role": "assistant", "content": content, "tool_calls": assistant_tool_calls})

            for tc in assistant_tool_calls:
                self._check_cancelled(run_id)
                name = tc.get("function", {}).get("name") or ""
                arg_str = tc.get("function", {}).get("arguments") or "{}"
                try:
                    args = json.loads(arg_str)
                except Exception:
                    args = {}

                if name == "upsert_notion_toggle_section":
                    target_id = args.get("page_id")
                    if allowed_notion_targets and target_id not in allowed_notion_targets:
                        result = "❌ Blocked: Notion write target does not match workflow output configuration."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                    if target_id and (target_id not in allow_body_edit_targets):
                        result = "❌ Blocked: Notion body edits are disabled for this workflow output. Enable allow_body_edits to use section updates."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                if name in {"append_to_notion_page", "replace_notion_page_content"}:
                    target_id = args.get("page_id")
                    if allowed_notion_targets and target_id not in allowed_notion_targets:
                        result = "❌ Blocked: Notion write target does not match workflow output configuration."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                    if target_id and target_id in notion_row_page_targets:
                        result = "❌ Blocked: Notion database-row destinations are properties-only; page body writes are disabled."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                if name in {"update_notion_block_text", "update_notion_todo_checked"}:
                    target_id = args.get("page_id")
                    if target_id and target_id in notion_row_page_targets:
                        result = "❌ Blocked: Notion database-row destinations are properties-only; block edits are disabled."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                if name == "update_notion_database_row_content":
                    target_id = args.get("database_id")
                    if target_id and target_id in notion_row_page_targets:
                        result = "❌ Blocked: Notion database-row destinations are properties-only; row content edits are disabled."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                if name == "update_notion_entry_by_name":
                    # For workflows targeting a single Notion row/page, require entry_id to avoid wrong-row updates.
                    entry_id = args.get("entry_id")
                    target_db = args.get("database_id")

                    allowed = True
                    if allowed_notion_targets:
                        if entry_id:
                            allowed = entry_id in allowed_notion_targets
                        else:
                            # Only allow name-based updates when the output target is a database (not a row page).
                            allowed = target_db in allowed_notion_targets

                    if not allowed:
                        result = "❌ Blocked: update_notion_entry_by_name requires entry_id for workflows targeting a specific Notion row/page."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                if name in {"update_notion_database_entry", "update_notion_database_entry_properties"}:
                    entry_id = args.get("entry_id")
                    allowed = (not allowed_notion_targets) or (entry_id in allowed_notion_targets)
                    if (not allowed) and Config.NOTION_TOKEN and entry_id:
                        try:
                            import requests
                            headers = {
                                "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                                "Notion-Version": Config.NOTION_VERSION,
                            }
                            resp = requests.get(
                                f"https://api.notion.com/v1/pages/{entry_id}",
                                headers=headers,
                                timeout=15,
                            )
                            if resp.status_code == 200:
                                parent = (resp.json() or {}).get("parent", {}) or {}
                                if parent.get("type") in {"database_id", "data_source_id"} and parent.get("database_id") in allowed_notion_targets:
                                    allowed = True
                        except Exception:
                            pass

                    if not allowed:
                        result = "❌ Blocked: Notion entry target does not match workflow output configuration."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                if name == "update_notion_database_row_content":
                    target_id = args.get("database_id")
                    if allowed_notion_targets and target_id not in allowed_notion_targets:
                        result = "❌ Blocked: Notion database target does not match workflow output configuration."
                        executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tc.get("id"),
                                "name": name,
                                "content": result,
                            }
                        )
                        continue

                if name == "create_notion_page" and not allow_create_notion_page:
                    result = "❌ Blocked: Workflow output configuration targets an existing Notion page/database; new page creation not allowed."
                    executed_calls.append({"name": name, "arguments": args, "result_preview": result})
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.get("id"),
                            "name": name,
                            "content": result,
                        }
                    )
                    continue

                result = self._execute_workflow_tool(
                    tools_handler,
                    name,
                    args,
                    run_id,
                    gmail_account_email,
                )

                conflict = self._parse_conflict_result(result)
                if conflict:
                    pending = {
                        "tool_call_id": tc.get("id"),
                        "tool_name": name,
                        "tool_arguments": args,
                        "conflict": conflict,
                    }
                    # Persist minimal agent state so we can resume deterministically.
                    state = {
                        "messages": messages[-30:],
                        "executed_calls": executed_calls,
                        "iterations": iterations,
                        "plan_candidate": plan_candidate,
                    }
                    self._update_run(
                        run_id,
                        status="awaiting_user_input",
                        current_step="awaiting_user_input",
                        progress_percent=65,
                        output_result={"pending_user_input": pending, "agent_state": state},
                    )
                    self._log(run_id, "info", "Workflow paused: awaiting user input to resolve a conflict")
                    return {
                        "status": "awaiting_user_input",
                        "final_response": "",
                        "tool_calls": executed_calls,
                        "iterations": iterations,
                        "pending_user_input": pending,
                        "plan": plan_candidate,
                    }

                executed_calls.append({"name": name, "arguments": args, "result_preview": str(result)[:500]})
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.get("id"),
                        "name": name,
                        "content": str(result),
                    }
                )

        # If we hit iteration limit, return best-effort summary.
        return {
            "final_response": "Reached tool-iteration limit; partial execution may have occurred.",
            "tool_calls": executed_calls,
            "iterations": iterations,
            "plan": plan_candidate,
        }

    async def resume_workflow_run(self, workflow_id: str, run_id: str, selection: str) -> Dict[str, Any]:
        """Resume a paused workflow run after user selects a disambiguation option."""
        try:
            workflow = self.db_manager.get_user_workflow(workflow_id, self.user_id)
            if not workflow:
                return {"error": "Workflow not found", "status": "failed"}

            run = self.db_manager.get_workflow_run(run_id)
            if not run or run.workflow_id != workflow_id:
                return {"error": "Run not found", "status": "failed"}

            output_result = run.output_result or {}
            pending = (output_result.get("pending_user_input") or {}) if isinstance(output_result, dict) else {}
            agent_state = (output_result.get("agent_state") or {}) if isinstance(output_result, dict) else {}

            tool_name = pending.get("tool_name") or ""
            tool_call_id = pending.get("tool_call_id")
            tool_arguments = dict(pending.get("tool_arguments") or {})
            conflict = pending.get("conflict") or {}

            patch_key = conflict.get("patch_key")
            if patch_key:
                tool_arguments[patch_key] = selection

            # Clear pending state and mark as running.
            self._update_run(
                run_id,
                status="running",
                current_step="processing_ai",
                progress_percent=65,
                error_message=None,
                output_result={"pending_user_input": None, "agent_state": agent_state},
            )

            from agent.langchain_tools import WorkforceTools

            tools_handler = WorkforceTools(user_id=self.user_id)
            gmail_account_email = None
            try:
                gmail_account_email = getattr(getattr(tools_handler, "gmail_client", None), "user_email", None)
            except Exception:
                gmail_account_email = None

            # Re-hydrate messages and inject the resolved tool result.
            messages = list(agent_state.get("messages") or [])
            executed_calls = list(agent_state.get("executed_calls") or [])
            iterations = int(agent_state.get("iterations") or 0)

            # Execute the resolved tool call deterministically.
            resolved_result = self._execute_workflow_tool(
                tools_handler,
                tool_name,
                tool_arguments,
                run_id,
                gmail_account_email,
            )
            executed_calls.append({"name": tool_name, "arguments": tool_arguments, "result_preview": str(resolved_result)[:500]})
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call_id or "call_resumed",
                    "name": tool_name,
                    "content": str(resolved_result),
                }
            )

            # Continue the tool-calling loop.
            resumed = await self._run_tool_calling_agent(
                source_data="",
                destination_state="",
                prompt_config=workflow.prompt_config,
                output_config=workflow.output_config,
                run_id=run_id,
                resume_state={
                    "messages": messages,
                    "executed_calls": executed_calls,
                    "iterations": iterations,
                    "plan_candidate": agent_state.get("plan_candidate") or "",
                },
            )
            return resumed
        finally:
            await self.close()

    async def execute_workflow(self, workflow_id: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        """Execute a complete workflow run.
        
        Returns:
            Dict with run_id, status, and results
        """
        # Get workflow
        workflow = self.db_manager.get_user_workflow(workflow_id, self.user_id)
        if not workflow:
            return {"error": "Workflow not found", "status": "failed"}

        # Create or re-use run record
        if run_id:
            run = self.db_manager.get_workflow_run(run_id)
            if not run or run.workflow_id != workflow_id:
                return {"error": "Run not found", "status": "failed"}
        else:
            run = self.db_manager.create_workflow_run(workflow_id)
            run_id = run.id

        try:
            # Start run
            self._update_run(run_id, 
                status="running",
                started_at=datetime.utcnow(),
                current_step="fetching_sources",
                progress_percent=5
            )
            self._log(run_id, "info", "Starting workflow execution")

            # 1. FETCH SOURCES
            self._check_cancelled(run_id)
            self._update_run(run_id, current_step="fetching_sources", progress_percent=10)
            self._log(run_id, "info", "Fetching source data...")
            
            source_data, source_count = await self._fetch_sources(
                workflow.source_config, run_id
            )

            if not source_data.strip():
                self._log(run_id, "info", "No new data from sources")
                self._update_run(run_id,
                    status="completed",
                    completed_at=datetime.utcnow(),
                    current_step="completed",
                    progress_percent=100,
                    source_items_count=0,
                    ai_response="No data to process",
                    output_result={"message": "No new data from sources"}
                )
                return {"run_id": run_id, "status": "completed", "message": "No new data"}

            self._update_run(run_id, 
                source_items_count=source_count,
                source_data_preview=source_data[:2000],
                progress_percent=25
            )
            self._log(run_id, "info", f"Fetched {source_count} source items")

            # 2. FETCH DESTINATION STATE (for intelligent update)
            self._check_cancelled(run_id)
            self._update_run(run_id, current_step="fetching_destination", progress_percent=30)
            self._log(run_id, "info", "Fetching destination state...")
            
            destination_state = await self._fetch_destination_state(
                workflow.output_config, run_id
            )
            self._log(run_id, "info", "Destination state fetched")

            # 3. PROCESS + ACT (tool-calling agent)
            self._check_cancelled(run_id)
            self._update_run(run_id, current_step="processing_ai", progress_percent=40)
            self._log(run_id, "info", "Processing with AI (tool-calling mode)...")

            output_results: Dict[str, Any] = {}
            final_response = ""
            executed_tool_calls: List[Dict[str, Any]] = []

            try:
                agent_result = await self._run_tool_calling_agent(
                    source_data=source_data,
                    destination_state=destination_state,
                    prompt_config=workflow.prompt_config,
                    output_config=workflow.output_config,
                    run_id=run_id,
                )
                if agent_result.get("status") == "awaiting_user_input":
                    return {
                        "run_id": run_id,
                        "status": "awaiting_user_input",
                        "pending_user_input": agent_result.get("pending_user_input"),
                    }
                final_response = agent_result.get("final_response") or ""
                executed_tool_calls = agent_result.get("tool_calls") or []
                agent_plan = agent_result.get("plan") or ""
            except Exception as e:
                # Fall back to legacy JSON-action agent if tool calling fails
                self._log(run_id, "error", f"Tool-calling agent failed, falling back to legacy mode: {e}")
                final_response = await self._process_with_ai_intelligent(
                    source_data, destination_state, workflow.prompt_config, workflow.output_config, run_id
                )
                agent_plan = ""

            self._update_run(
                run_id,
                ai_response=final_response,
                progress_percent=65,
            )
            self._log(run_id, "info", "AI processing complete")

            def _ai_indicates_no_action(text: str) -> bool:
                t = (text or "").strip().lower()
                if not t:
                    return False
                triggers = [
                    "no changes required",
                    "no change required",
                    "no updates required",
                    "no update required",
                    "no changes needed",
                    "no update needed",
                    "no updates needed",
                    "no action required",
                    "nothing to update",
                    "already up to date",
                ]
                return any(x in t for x in triggers)

            def _extract_plan(text: str) -> str:
                if not text:
                    return ""
                lines = text.splitlines()
                plan_lines: List[str] = []
                in_plan = False
                for line in lines:
                    s = (line or "").strip()
                    lower = s.lower()
                    if not in_plan:
                        if lower in {"plan", "## plan", "### plan"}:
                            in_plan = True
                        continue

                    if not s and plan_lines:
                        break
                    if lower.startswith("update status") or lower.startswith("output result"):
                        break
                    plan_lines.append(line)
                    if len(plan_lines) >= 50:
                        break
                return "\n".join(plan_lines).strip()

            def _extract_update_status(text: str) -> str:
                if not text:
                    return ""
                for line in text.splitlines():
                    if "update status" in (line or "").lower():
                        return (line or "").strip()
                return ""

            # 4. Ensure outputs are satisfied (fallback per destination)
            self._check_cancelled(run_id)
            self._update_run(run_id, current_step="executing_actions", progress_percent=70)

            write_tools = {
                "send_slack_message",
                "create_gmail_draft",
                "create_notion_page",
                "append_to_notion_page",
                "replace_notion_page_content",
                "update_notion_entry_by_name",
                "update_notion_database_entry",
                "update_notion_database_entry_properties",
                "update_notion_database_row_content",
            }
            executed_write_tools = {c.get("name") for c in executed_tool_calls if c.get("name") in write_tools}

            outputs = workflow.output_config.get("outputs", [])
            display_outputs = [o for o in outputs if o.get("type") == "display"]
            non_display_outputs = [o for o in outputs if o.get("type") != "display"]

            results: List[Dict[str, Any]] = []
            if display_outputs:
                results.append(
                    {
                        "type": "display",
                        "success": True,
                        "details": {"message": final_response},
                    }
                )

            text_for_extraction = (agent_plan or final_response or "")

            no_action_required = _ai_indicates_no_action(final_response)
            if (not no_action_required) and (not executed_tool_calls) and agent_plan:
                no_action_required = _ai_indicates_no_action(agent_plan)

            if no_action_required:
                for o in non_display_outputs:
                    ot = o.get("type")
                    if ot == "slack_message":
                        results.append(
                            {
                                "type": "slack",
                                "success": True,
                                "details": {"action": "no_action_required", "result": "✅ No update required"},
                            }
                        )
                    elif ot == "gmail_draft":
                        results.append(
                            {
                                "type": "gmail_draft",
                                "success": True,
                                "details": {"action": "no_action_required", "result": "✅ No update required"},
                            }
                        )
                    elif ot == "notion_page":
                        results.append(
                            {
                                "type": "notion",
                                "success": True,
                                "details": {
                                    "page_id": o.get("page_id"),
                                    "action": "no_action_required",
                                    "result": "✅ No update required",
                                },
                            }
                        )
            else:
                missing_outputs: List[Dict[str, Any]] = []
                for o in non_display_outputs:
                    ot = o.get("type")
                    if ot == "slack_message" and "send_slack_message" not in executed_write_tools:
                        missing_outputs.append(o)
                    elif ot == "gmail_draft" and "create_gmail_draft" not in executed_write_tools:
                        missing_outputs.append(o)
                    elif ot == "notion_page" and not (
                        {
                            "create_notion_page",
                            "append_to_notion_page",
                            "replace_notion_page_content",
                            "update_notion_entry_by_name",
                            "update_notion_database_entry",
                            "update_notion_database_entry_properties",
                            "update_notion_database_row_content",
                        }
                        & executed_write_tools
                    ):
                        missing_outputs.append(o)

                if missing_outputs:
                    self._log(run_id, "info", f"Falling back to deterministic outputs for {len(missing_outputs)} destination(s)")
                    fallback_result = await self._execute_outputs(
                        final_response,
                        {"outputs": missing_outputs},
                        run_id,
                    )
                    results.extend(fallback_result.get("outputs", []))

            output_results["outputs"] = results
            output_results["success"] = all(r.get("success") for r in results) if results else True
            output_results["agent_tool_calls"] = executed_tool_calls

            plan_text = _extract_plan(text_for_extraction)
            if plan_text:
                output_results["ai_thinking"] = plan_text[:2000]
            else:
                output_results["ai_thinking"] = (text_for_extraction or "")[:800]

            if executed_tool_calls:
                output_results["ai_actions_taken"] = "\n".join(
                    [
                        f"{c.get('name')}: {json.dumps(c.get('arguments', {}), ensure_ascii=False)}"
                        for c in executed_tool_calls
                    ]
                )
            else:
                status_line = _extract_update_status(text_for_extraction)
                if status_line:
                    output_results["ai_actions_taken"] = status_line
                elif no_action_required:
                    output_results["ai_actions_taken"] = "No external actions executed (no updates required)."
                else:
                    output_results["ai_actions_taken"] = "No tool calls were executed."

            if (not executed_tool_calls) and no_action_required:
                output_results["agent_tool_calls"] = [
                    {
                        "name": "no_action_required",
                        "arguments": {},
                        "result_preview": "✅ No update required",
                    }
                ]

            # If legacy mode produced an ACTIONS JSON response, execute it as a last resort
            if (not results) and final_response:
                try:
                    thinking, actions_taken, actions = self._parse_ai_response(final_response, run_id)
                    if actions:
                        self._log(run_id, "info", f"Legacy action fallback: executing {len(actions)} action(s)")
                        legacy_exec = await self._execute_ai_actions(actions, run_id)
                        output_results.update(legacy_exec)
                        output_results["ai_thinking"] = thinking[:1000] if thinking else ""
                        output_results["ai_actions_taken"] = actions_taken
                except Exception:
                    pass

            # 4. COMPLETE
            self._update_run(run_id,
                status="completed",
                completed_at=datetime.utcnow(),
                current_step="completed",
                progress_percent=100,
                output_result=output_results
            )

            if output_results.get("success") is False:
                self._log(run_id, "warning", "Workflow completed with output errors")
            else:
                self._log(run_id, "info", "Workflow completed successfully")

            # Update workflow last_run_at
            self.db_manager.update_user_workflow(
                workflow_id, self.user_id,
                last_run_at=datetime.utcnow()
            )

            return {
                "run_id": run_id,
                "status": "completed",
                "source_count": source_count,
                "output_results": output_results
            }

        except WorkflowCancelledException:
            logger.info(f"Workflow {workflow_id} run {run_id} was cancelled by user")
            self._log(run_id, "info", "Workflow cancelled by user")
            return {"run_id": run_id, "status": "cancelled", "message": "Cancelled by user"}

        except Exception as e:
            logger.error(f"Workflow execution failed: {e}", exc_info=True)
            self._log(run_id, "error", f"Execution failed: {str(e)}")
            self._update_run(run_id,
                status="failed",
                completed_at=datetime.utcnow(),
                current_step="failed",
                error_message=str(e)
            )
            return {"run_id": run_id, "status": "failed", "error": str(e)}

        finally:
            await self.close()

    async def _fetch_sources(
        self, source_config: Dict[str, Any], run_id: str
    ) -> tuple[str, int]:
        """Fetch data from all configured sources.
        
        Returns:
            Tuple of (formatted_data_string, item_count)
        """
        sources = source_config.get("sources", [])
        all_data = []
        total_count = 0

        for source in sources:
            source_type = source.get("type")
            time_range = source.get("time_range", "last_24h")
            since = self._calculate_since(time_range)

            if source_type == "slack":
                channel_ids = source.get("channels", [])
                if channel_ids:
                    since_ts = since.timestamp() if since else None
                    messages = self.db_manager.get_slack_messages_for_workflow(
                        channel_ids=channel_ids,
                        since_timestamp=since_ts,
                        limit=source.get("limit", 200)
                    )
                    if messages:
                        formatted = self._format_slack_messages(messages)
                        all_data.append(f"## Slack Messages\n{formatted}")
                        total_count += len(messages)
                        self._log(run_id, "info", f"Fetched {len(messages)} Slack messages")

            elif source_type == "gmail":
                label_ids = source.get("labels", [])
                messages = self.db_manager.get_gmail_messages_for_workflow(
                    label_ids=label_ids if label_ids else None,
                    since_date=since,
                    limit=source.get("limit", 100)
                )
                if messages:
                    formatted = self._format_gmail_messages(messages)
                    all_data.append(f"## Gmail Emails\n{formatted}")
                    total_count += len(messages)
                    self._log(run_id, "info", f"Fetched {len(messages)} Gmail emails")

            elif source_type == "notion":
                page_ids = source.get("pages", [])
                if page_ids:
                    pages = self.db_manager.get_notion_pages_for_workflow(page_ids)
                    if pages:
                        formatted = self._format_notion_pages(pages)
                        all_data.append(f"## Notion Pages\n{formatted}")
                        total_count += len(pages)
                        self._log(run_id, "info", f"Fetched {len(pages)} Notion pages")

        return "\n\n---\n\n".join(all_data), total_count

    def _calculate_since(self, time_range: str) -> Optional[datetime]:
        """Calculate the 'since' datetime based on time range string."""
        now = datetime.utcnow()
        
        if time_range == "last_1h":
            return now - timedelta(hours=1)
        elif time_range == "last_24h":
            return now - timedelta(hours=24)
        elif time_range == "last_7d":
            return now - timedelta(days=7)
        elif time_range == "last_30d":
            return now - timedelta(days=30)
        elif time_range == "since_last_run":
            # This would need the workflow's last_run_at
            return now - timedelta(hours=24)  # Default fallback
        else:
            return None  # All time

    def _format_slack_messages(self, messages: List) -> str:
        """Format Slack messages for AI processing."""
        formatted = []
        for msg in messages:
            user_id = msg.user_id or "Unknown"
            text = msg.text or ""
            ts = datetime.fromtimestamp(msg.timestamp).strftime("%Y-%m-%d %H:%M")
            formatted.append(f"[{ts}] {user_id}: {text}")
        return "\n".join(formatted)

    def _format_gmail_messages(self, messages: List) -> str:
        """Format Gmail messages for AI processing."""
        formatted = []
        for msg in messages:
            date_str = msg.date.strftime("%Y-%m-%d %H:%M") if msg.date else "Unknown date"
            subject = msg.subject or "(No subject)"
            sender = msg.from_address or "Unknown"
            body = msg.body_text or msg.snippet or ""
            # Truncate long bodies
            if len(body) > 1000:
                body = body[:1000] + "..."
            formatted.append(f"From: {sender}\nDate: {date_str}\nSubject: {subject}\n\n{body}")
        return "\n\n---\n\n".join(formatted)

    def _format_notion_pages(self, pages: List) -> str:
        """Format Notion pages for AI processing."""
        def _flatten_block_tree(blocks: Any) -> List[Dict[str, Any]]:
            flat: List[Dict[str, Any]] = []
            stack: List[Dict[str, Any]] = []
            if isinstance(blocks, list):
                for b in blocks:
                    if isinstance(b, dict):
                        stack.append(b)
            while stack:
                block = stack.pop()
                if not isinstance(block, dict):
                    continue
                flat.append(block)
                children = block.get("_children")
                if isinstance(children, list) and children:
                    for child in children:
                        if isinstance(child, dict):
                            stack.append(child)
            return flat

        def _rich_text_to_plain(rt: Any) -> str:
            if not isinstance(rt, list):
                return ""
            parts: List[str] = []
            for item in rt:
                if isinstance(item, dict):
                    txt = item.get("plain_text")
                    if txt:
                        parts.append(str(txt))
            return "".join(parts).strip()

        def _extract_block_line(block: Dict[str, Any]) -> str:
            b_type = block.get("type")
            if not b_type:
                return ""
            payload = block.get(b_type)
            payload = payload if isinstance(payload, dict) else {}

            if b_type in {"child_page", "child_database"}:
                title = payload.get("title")
                if title:
                    return f"[{b_type}] {title}"
                return f"[{b_type}]"

            text = _rich_text_to_plain(payload.get("rich_text"))
            if not text:
                # Some blocks may store text in other keys
                text = _rich_text_to_plain(payload.get("title"))
            if not text:
                return ""

            if b_type.startswith("heading_"):
                level = b_type.split("_", 1)[1]
                prefix = {"1": "#", "2": "##", "3": "###"}.get(level, "#")
                return f"{prefix} {text}"
            if b_type == "bulleted_list_item":
                return f"- {text}"
            if b_type == "numbered_list_item":
                return f"1. {text}"
            if b_type == "to_do":
                checked = bool(payload.get("checked"))
                return f"[{'x' if checked else ' '}] {text}"
            if b_type == "quote":
                return f"> {text}"
            if b_type == "code":
                lang = payload.get("language") or ""
                lang = f" ({lang})" if lang else ""
                return f"[code{lang}] {text}"
            return text

        formatted: List[str] = []
        for page in pages:
            title = getattr(page, "title", None) or "Untitled"
            page_id = getattr(page, "page_id", None) or ""
            obj_type = (getattr(page, "object_type", None) or "page").lower()

            header = f"### {title}\nID: {page_id}\nType: {obj_type}"
            body = ""

            if obj_type == "database":
                schema = getattr(page, "schema_data", None) or {}
                schema = schema if isinstance(schema, dict) else {}
                cached_entries = schema.get("cached_entries")
                cached_columns = schema.get("cached_columns")
                cached_total = schema.get("cached_total")
                cached_error = schema.get("cached_error")

                if isinstance(cached_entries, list) and cached_entries:
                    cols = cached_columns if isinstance(cached_columns, list) else []
                    total = cached_total if isinstance(cached_total, int) else len(cached_entries)

                    sample = cached_entries[:10]
                    rows: List[str] = []
                    for entry in sample:
                        if not isinstance(entry, dict):
                            continue
                        props = entry.get("properties") if isinstance(entry.get("properties"), dict) else {}
                        row_bits: List[str] = []
                        for col in cols[:8]:
                            val = props.get(col)
                            if val is None or val == "":
                                continue
                            if isinstance(val, list):
                                row_bits.append(f"{col}: {', '.join(str(x) for x in val[:3])}{'...' if len(val) > 3 else ''}")
                            else:
                                row_bits.append(f"{col}: {val}")
                        row_line = "; ".join(row_bits) if row_bits else (entry.get("title") or entry.get("id") or "(row)")
                        rows.append(f"- {row_line}")

                    body = "\n".join(
                        [
                            f"Cached rows: {total}",
                            "\n".join(rows),
                        ]
                    ).strip()
                else:
                    note = "Database rows not cached. Refresh this database (or its parent page) in Pipelines to persist entries into Supabase."
                    if cached_error:
                        note = f"{note}\nLast error: {cached_error}"
                    body = note

            else:
                blocks = getattr(page, "blocks_data", None)
                if isinstance(blocks, list) and blocks:
                    flat = _flatten_block_tree(blocks)
                    lines: List[str] = []
                    budget = 3500
                    used = 0
                    for b in flat:
                        line = _extract_block_line(b)
                        if not line:
                            continue
                        if used + len(line) + 1 > budget:
                            break
                        lines.append(line)
                        used += len(line) + 1
                    body = "\n".join(lines).strip() or "(No readable text blocks found.)"
                else:
                    # Titles-only pipeline will populate title/metadata, but not blocks.
                    body = "Page content not cached. Click Refresh on this page in Pipelines to fetch and persist blocks into Supabase."

            formatted.append(f"{header}\n\n{body}")

        return "\n\n---\n\n".join(formatted)

    async def _fetch_destination_state(
        self, output_config: Dict[str, Any], run_id: str
    ) -> str:
        """Fetch current state of output destinations for intelligent update.
        
        Returns:
            Formatted string describing destination state (page content, database schema, subpages)
        """
        from agent.langchain_tools import WorkforceTools
        
        outputs = output_config.get("outputs", [])
        destination_parts = []
        tools = WorkforceTools(user_id=self.user_id)
        
        for output in outputs:
            output_type = output.get("type")
            
            try:
                if output_type == "notion_page":
                    page_id = output.get("page_id")
                    if page_id:
                        # Fetch page content and structure
                        state = self._fetch_notion_page_state(tools, page_id)
                        if bool(output.get("allow_body_edits")):
                            outline = tools.get_notion_page_outline(page_id=page_id, max_depth=2)
                            destination_parts.append(
                                f"## Notion Destination (page_id: {page_id})\n{state}\n\n## Notion Page Outline (safe body edits enabled)\n{outline}"
                            )
                        else:
                            destination_parts.append(f"## Notion Destination (page_id: {page_id})\n{state}")
                    else:
                        destination_parts.append("## Notion Destination\nNo target page specified. AI will create a new page.")
                        
                elif output_type == "slack_message":
                    channel = output.get("channel")
                    if channel:
                        destination_parts.append(f"## Slack Destination (channel: {channel})\nMessages will be sent to this channel.")
                        
                elif output_type == "gmail_draft":
                    to = output.get("to", "")
                    subject = output.get("subject", "")
                    destination_parts.append(f"## Gmail Draft Destination\nTo: {to}\nSubject: {subject}")
                    
                elif output_type == "display":
                    destination_parts.append("## Display Only\nOutput will be shown in UI.")
                    
            except Exception as e:
                self._log(run_id, "warning", f"Error fetching destination state for {output_type}: {e}")
                destination_parts.append(f"## {output_type} Destination\nCould not fetch state: {e}")
        
        return "\n\n---\n\n".join(destination_parts) if destination_parts else "No destinations configured."

    def _fetch_notion_page_state(self, tools, page_id: str) -> str:
        """Fetch detailed state of a Notion page including content, structure, and subpages."""
        import requests
        
        if not Config.NOTION_TOKEN:
            return "Notion not configured."
        
        headers = {
            "Authorization": f"Bearer {Config.NOTION_TOKEN}",
            "Notion-Version": Config.NOTION_VERSION,
            "Content-Type": "application/json",
        }
        
        try:
            # First check if this ID is a database
            db_resp = requests.get(
                f"https://api.notion.com/v1/databases/{page_id}",
                headers=headers,
                timeout=30,
            )
            if db_resp.status_code == 200:
                return self._fetch_notion_database_state(headers, page_id, db_resp.json())

            # First, get the page metadata
            page_resp = requests.get(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                timeout=30
            )
            
            if page_resp.status_code != 200:
                return f"Could not fetch page: {page_resp.status_code}"
            
            page_data = page_resp.json()
            object_type = page_data.get("object", "page")
            parent = page_data.get("parent", {})

            if object_type == "database":
                return self._fetch_notion_database_state(headers, page_id, page_data)

            # Database row page: show properties + parent schema (do NOT treat the row ID as a database)
            if parent.get("type") in {"database_id", "data_source_id"}:
                return self._fetch_notion_database_row_state(headers, page_data)
            
            # It's a regular page - get its content
            state_parts = []
            
            # Get page title
            title = self._extract_notion_title(page_data)
            state_parts.append(f"**Page Title:** {title}")
            state_parts.append(f"**Type:** Page")
            
            # Get page content (blocks)
            content = tools.get_notion_page_content(page_id=page_id, include_subpages=True, max_blocks=100)
            if content and content != "No content":
                state_parts.append(f"\n**Current Content:**\n{content[:3000]}")
            else:
                state_parts.append("\n**Current Content:** Empty page")
            
            # Check for child pages/databases
            children = self._get_notion_children(headers, page_id)
            if children:
                state_parts.append(f"\n**Child Pages/Databases:**\n{children}")
            
            return "\n".join(state_parts)
            
        except Exception as e:
            logger.error(f"Error fetching Notion page state: {e}", exc_info=True)
            return f"Error fetching page state: {e}"

    def _fetch_notion_database_row_state(self, headers: Dict, page_data: Dict) -> str:
        import requests

        state_parts: List[str] = []
        title = self._extract_notion_title(page_data)
        state_parts.append(f"**Page Title:** {title}")
        state_parts.append("**Type:** Database Row")

        parent = page_data.get("parent", {}) or {}
        parent_type = parent.get("type")
        db_id = parent.get("database_id")
        data_source_id = parent.get("data_source_id") if parent_type == "data_source_id" else None
        if db_id:
            state_parts.append(f"**Parent Database ID:** {db_id}")
            try:
                db_resp = requests.get(
                    f"https://api.notion.com/v1/databases/{db_id}",
                    headers=headers,
                    timeout=30,
                )
                if db_resp.status_code == 200:
                    db_data = db_resp.json() or {}
                    db_title = self._extract_notion_title(db_data)
                    state_parts.append(f"**Parent Database Title:** {db_title}")

                    ds_id = data_source_id
                    if (not ds_id) and isinstance(db_data.get("data_sources"), list) and db_data.get("data_sources"):
                        first = db_data.get("data_sources")[0]
                        if isinstance(first, dict):
                            ds_id = first.get("id")

                    if ds_id:
                        ds_resp = requests.get(
                            f"https://api.notion.com/v1/data_sources/{ds_id}",
                            headers=headers,
                            timeout=30,
                        )
                        if ds_resp.status_code == 200:
                            ds_data = ds_resp.json() or {}
                            properties = ds_data.get("properties", {}) or {}
                            if properties:
                                schema_lines = ["**Schema (Columns):**"]
                                for prop_name, prop_def in properties.items():
                                    prop_type = (prop_def or {}).get("type", "unknown")
                                    schema_lines.append(f"  - {prop_name} ({prop_type})")
                                state_parts.append("\n".join(schema_lines))
            except Exception:
                pass

        # Current property values
        props = page_data.get("properties", {}) or {}
        if props:
            lines = ["**Current Properties (Values):**"]
            for prop_name, prop in props.items():
                try:
                    ptype = (prop or {}).get("type")
                    val = None
                    if ptype == "title":
                        val = "".join(t.get("plain_text", "") for t in (prop.get("title") or []))
                    elif ptype == "rich_text":
                        val = "".join(t.get("plain_text", "") for t in (prop.get("rich_text") or []))
                    elif ptype == "number":
                        val = prop.get("number")
                    elif ptype == "status":
                        st = prop.get("status") or {}
                        val = st.get("name")
                    elif ptype == "select":
                        st = prop.get("select") or {}
                        val = st.get("name")
                    elif ptype == "multi_select":
                        val = [o.get("name") for o in (prop.get("multi_select") or []) if isinstance(o, dict)]
                    elif ptype == "checkbox":
                        val = prop.get("checkbox")
                    elif ptype == "url":
                        val = prop.get("url")
                    elif ptype == "email":
                        val = prop.get("email")
                    elif ptype == "phone_number":
                        val = prop.get("phone_number")
                    elif ptype == "date":
                        d = prop.get("date") or {}
                        val = d.get("start")
                    elif ptype == "people":
                        val = [p.get("name") or p.get("id") for p in (prop.get("people") or []) if isinstance(p, dict)]
                    else:
                        val = f"<{ptype}>"

                    if val is None or val == "" or val == []:
                        disp = "<empty>"
                    else:
                        disp = str(val)
                    lines.append(f"  - {prop_name}: {disp}")
                except Exception:
                    continue
            state_parts.append("\n".join(lines))

        state_parts.append(
            "\n**Update guidance:** This destination is a database row. Prefer updating properties (Status / Next Step / values) using entry_id-based tools. Avoid replacing page content." 
        )

        return "\n".join(state_parts)

    def _fetch_notion_database_state(self, headers: Dict, database_id: str, db_data: Dict = None) -> str:
        """Fetch state of a Notion database including schema and sample rows."""
        import requests
        
        try:
            # Get database schema
            if not db_data:
                db_resp = requests.get(
                    f"https://api.notion.com/v1/databases/{database_id}",
                    headers=headers,
                    timeout=30
                )
                if db_resp.status_code != 200:
                    return f"Could not fetch database: {db_resp.status_code}"
                db_data = db_resp.json()
            
            state_parts = []
            title = self._extract_notion_title(db_data)
            state_parts.append(f"**Database Title:** {title}")
            state_parts.append(f"**Type:** Database")
            
            # Extract schema (properties/columns)
            ds_id = None
            if isinstance(db_data, dict):
                data_sources = db_data.get("data_sources")
                if isinstance(data_sources, list) and data_sources:
                    first = data_sources[0]
                    if isinstance(first, dict):
                        ds_id = first.get("id")

            properties: Dict[str, Any] = {}
            if ds_id:
                ds_resp = requests.get(
                    f"https://api.notion.com/v1/data_sources/{ds_id}",
                    headers=headers,
                    timeout=30,
                )
                if ds_resp.status_code == 200:
                    ds_data = ds_resp.json() or {}
                    properties = ds_data.get("properties", {}) or {}
            if properties:
                schema_lines = ["**Schema (Columns):**"]
                for prop_name, prop_def in properties.items():
                    prop_type = prop_def.get("type", "unknown")
                    schema_lines.append(f"  - {prop_name} ({prop_type})")
                state_parts.append("\n".join(schema_lines))
            
            # Get sample rows
            query_resp = None
            if ds_id:
                query_resp = requests.post(
                    f"https://api.notion.com/v1/data_sources/{ds_id}/query",
                    headers=headers,
                    json={"page_size": 10},
                    timeout=30,
                )
            
            if query_resp is not None and query_resp.status_code == 200:
                rows = query_resp.json().get("results", [])
                if rows:
                    state_parts.append(f"\n**Existing Rows ({len(rows)} shown):**")
                    for row in rows[:10]:
                        row_id = row.get("id", "")
                        row_title = self._extract_row_title(row)
                        state_parts.append(f"  - [ID: {row_id[:8]}...] {row_title}")
                else:
                    state_parts.append("\n**Existing Rows:** None (empty database)")
            
            return "\n".join(state_parts)
            
        except Exception as e:
            logger.error(f"Error fetching Notion database state: {e}", exc_info=True)
            return f"Error fetching database state: {e}"

    def _extract_notion_title(self, obj: Dict) -> str:
        """Extract title from a Notion page or database object."""
        properties = obj.get("properties", {})
        for prop in properties.values():
            if prop.get("type") == "title":
                title_parts = prop.get("title", [])
                if title_parts:
                    return "".join(p.get("plain_text", "") for p in title_parts)
        
        # Try top-level title (for databases)
        top_title = obj.get("title", [])
        if isinstance(top_title, list) and top_title:
            return "".join(p.get("plain_text", "") for p in top_title if isinstance(p, dict))
        
        return "Untitled"

    def _extract_row_title(self, row: Dict) -> str:
        """Extract title from a database row."""
        properties = row.get("properties", {})
        for prop in properties.values():
            if prop.get("type") == "title":
                title_parts = prop.get("title", [])
                if title_parts:
                    return "".join(p.get("plain_text", "") for p in title_parts)
        return "(No title)"

    def _get_notion_children(self, headers: Dict, page_id: str) -> str:
        """Get child pages and databases of a Notion page."""
        import requests
        
        try:
            resp = requests.get(
                f"https://api.notion.com/v1/blocks/{page_id}/children",
                headers=headers,
                params={"page_size": 50},
                timeout=30
            )
            
            if resp.status_code != 200:
                return ""
            
            blocks = resp.json().get("results", [])
            children = []
            
            for block in blocks:
                block_type = block.get("type", "")
                block_id = block.get("id", "")
                
                if block_type == "child_page":
                    title = block.get("child_page", {}).get("title", "Untitled")
                    children.append(f"  - Subpage: {title} (ID: {block_id})")
                elif block_type == "child_database":
                    title = block.get("child_database", {}).get("title", "Untitled")
                    children.append(f"  - Database: {title} (ID: {block_id})")
            
            return "\n".join(children) if children else ""
            
        except Exception as e:
            logger.error(f"Error getting Notion children: {e}")
            return ""

    async def _process_with_ai_intelligent(
        self, source_data: str, destination_state: str, prompt_config: Dict[str, Any], 
        output_config: Dict[str, Any], run_id: str
    ) -> str:
        """Process with AI agent - considers source, destination, and output-specific instructions."""
        user_instructions = prompt_config.get("user_instructions", "")
        
        # Extract output-specific instructions
        output_instructions = []
        for i, output in enumerate(output_config.get("outputs", [])):
            output_type = output.get("type", "unknown")
            output_prompt = output.get("output_prompt", "")
            if output_prompt:
                output_instructions.append(f"**Output {i+1} ({output_type}):** {output_prompt}")
        
        output_instructions_text = "\n".join(output_instructions) if output_instructions else "No specific output instructions provided."
        
        # Build the comprehensive prompt
        full_prompt = f"""## SOURCE DATA (Information from configured sources):
{source_data[:10000]}

## DESTINATION STATE (Current state of output targets):
{destination_state[:5000]}

## USER INSTRUCTIONS (Main workflow goal):
{user_instructions}

## OUTPUT-SPECIFIC INSTRUCTIONS:
{output_instructions_text}

Analyze the source data, understand the destination state, and execute the user's instructions. 
Respond with your THINKING, ACTIONS_TAKEN (human-readable), and ACTIONS (JSON) as specified."""

        try:
            return await self._chat_completion(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": AI_AGENT_SYSTEM_PROMPT},
                    {"role": "user", "content": full_prompt},
                ],
                max_output_tokens=6000,
                temperature=0.5,
                run_id=run_id,
            )
        except Exception as e:
            self._log(run_id, "error", f"AI processing error: {e}")
            raise

    def _parse_ai_response(self, ai_response: str, run_id: str) -> Tuple[str, str, List[Dict[str, Any]]]:
        """Parse AI response to extract THINKING, ACTIONS_TAKEN, and ACTIONS.
        
        Returns:
            Tuple of (thinking, actions_taken, actions_list)
        """
        thinking = ""
        actions_taken = ""
        actions = []
        
        # Extract THINKING section
        thinking_match = re.search(r'###?\s*THINKING\s*\n([\s\S]*?)(?=###?\s*ACTIONS|$)', ai_response, re.IGNORECASE)
        if thinking_match:
            thinking = thinking_match.group(1).strip()
            self._log(run_id, "info", f"AI Thinking: {thinking[:500]}...")
        
        # Extract ACTIONS_TAKEN section (human-readable)
        actions_taken_match = re.search(r'###?\s*ACTIONS_TAKEN\s*\n([\s\S]*?)(?=###?\s*ACTIONS|```|$)', ai_response, re.IGNORECASE)
        if actions_taken_match:
            actions_taken = actions_taken_match.group(1).strip()
            # Log each action taken
            for line in actions_taken.split('\n'):
                line = line.strip()
                if line and line.startswith('-'):
                    self._log(run_id, "info", f"Agent: {line[1:].strip()}")
        
        # Extract JSON actions
        try:
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', ai_response)
            if json_match:
                json_str = json_match.group(1).strip()
                parsed = json.loads(json_str)
                if isinstance(parsed, list):
                    actions = parsed
                else:
                    actions = [parsed]
            else:
                # Try to find JSON array directly
                array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', ai_response)
                if array_match:
                    parsed = json.loads(array_match.group(0))
                    if isinstance(parsed, list):
                        actions = parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI actions JSON: {e}")
            self._log(run_id, "error", f"Failed to parse AI actions: {e}")
        
        return thinking, actions_taken, actions

    def _parse_ai_actions(self, ai_response: str) -> List[Dict[str, Any]]:
        """Parse AI response to extract JSON actions (legacy compatibility)."""
        try:
            # Look for JSON in code blocks
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', ai_response)
            if json_match:
                json_str = json_match.group(1).strip()
                actions = json.loads(json_str)
                if isinstance(actions, list):
                    return actions
                return [actions]
            
            # Try to find JSON array directly
            array_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', ai_response)
            if array_match:
                actions = json.loads(array_match.group(0))
                if isinstance(actions, list):
                    return actions
            
            # If no JSON found, return empty list
            logger.warning("No JSON actions found in AI response")
            return []
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI actions JSON: {e}")
            return []

    async def _execute_ai_actions(self, actions: List[Dict[str, Any]], run_id: str) -> Dict[str, Any]:
        """Execute the actions decided by AI."""
        from agent.langchain_tools import WorkforceTools
        
        tools = WorkforceTools(user_id=self.user_id)
        results = []
        
        for i, action in enumerate(actions):
            # Check for cancellation before each action
            self._check_cancelled(run_id)
            
            action_type = action.get("type", "unknown")
            self._log(run_id, "info", f"Executing action {i+1}/{len(actions)}: {action_type}")
            
            try:
                result = await self._execute_single_action(tools, action, run_id)
                results.append({"action": action_type, "success": True, "details": result})
            except WorkflowCancelledException:
                raise  # Re-raise cancellation to stop execution
            except Exception as e:
                self._log(run_id, "error", f"Action {action_type} failed: {e}")
                results.append({"action": action_type, "success": False, "error": str(e)})
        
        return {
            "actions_executed": len(results),
            "results": results,
            "success": all(r.get("success") for r in results) if results else True
        }

    async def _execute_single_action(
        self, tools, action: Dict[str, Any], run_id: str
    ) -> Dict[str, Any]:
        """Execute a single AI-decided action."""
        action_type = action.get("type", "")
        
        if action_type == "update_page_content":
            page_id = action.get("page_id", "")
            content = action.get("content", "")
            strategy = action.get("strategy", "append")
            
            if strategy == "replace":
                result = tools.replace_notion_page_content(page_id=page_id, content=content)
            else:
                result = tools.append_to_notion_page(page_id=page_id, content=content)
            return {"page_id": page_id, "strategy": strategy, "result": result}
        
        elif action_type == "add_database_row":
            database_id = action.get("database_id", "")
            properties = action.get("properties", {})
            result = self._add_notion_database_row(database_id, properties)
            return {"database_id": database_id, "result": result}
        
        elif action_type == "update_database_row":
            page_id = action.get("page_id", "")
            properties = action.get("properties", {})
            result = self._update_notion_database_row(page_id, properties)
            return {"page_id": page_id, "result": result}
        
        elif action_type == "create_subpage":
            parent_id = action.get("parent_id", "")
            title = action.get("title", "Untitled")
            content = action.get("content", "")
            result = self._create_notion_subpage(parent_id, title, content)
            return {"parent_id": parent_id, "title": title, "result": result}
        
        elif action_type == "create_page":
            title = action.get("title", "Workflow Output")
            content = action.get("content", "")
            result = tools.create_notion_page(title=title, content=content)
            return {"title": title, "result": result}
        
        elif action_type == "send_slack_message":
            channel = action.get("channel", "")
            message = action.get("message", "")
            result = tools.send_slack_message(channel=channel, text=message)
            return {"channel": channel, "result": result}
        
        elif action_type == "reply_to_thread":
            channel = action.get("channel", "")
            thread_ts = action.get("thread_ts", "")
            message = action.get("message", "")
            result = self._reply_to_slack_thread(tools, channel, thread_ts, message)
            return {"channel": channel, "thread_ts": thread_ts, "result": result}
        
        elif action_type == "add_reaction":
            channel = action.get("channel", "")
            timestamp = action.get("timestamp", "")
            emoji = action.get("emoji", "white_check_mark")
            result = self._add_slack_reaction(tools, channel, timestamp, emoji)
            return {"channel": channel, "timestamp": timestamp, "emoji": emoji, "result": result}
        
        elif action_type == "add_comment":
            page_id = action.get("page_id", "")
            comment = action.get("comment", "")
            result = self._add_notion_comment(page_id, comment)
            return {"page_id": page_id, "result": result}
        
        elif action_type == "send_email":
            to = action.get("to", "")
            subject = action.get("subject", "")
            body = action.get("body", "")
            result = tools.send_email(to=to, subject=subject, body=body)
            return {"to": to, "subject": subject, "result": result}
        
        elif action_type == "create_draft":
            to = action.get("to", "")
            subject = action.get("subject", "")
            body = action.get("body", "")
            result = tools.create_gmail_draft(to=to, subject=subject, body=body)
            return {"to": to, "subject": subject, "result": result}
        
        elif action_type == "no_action":
            reason = action.get("reason", "No action needed")
            self._log(run_id, "info", f"No action taken: {reason}")
            return {"reason": reason}
        
        else:
            self._log(run_id, "warning", f"Unknown action type: {action_type}")
            return {"error": f"Unknown action type: {action_type}"}

    def _add_notion_database_row(self, database_id: str, properties: Dict[str, Any]) -> str:
        """Add a row to a Notion database."""
        import requests
        
        if not Config.NOTION_TOKEN:
            return "❌ NOTION_TOKEN not configured"
        
        headers = {
            "Authorization": f"Bearer {Config.NOTION_TOKEN}",
            "Notion-Version": Config.NOTION_VERSION,
            "Content-Type": "application/json",
        }
        
        # Convert simple properties to Notion format
        notion_properties = {}
        for key, value in properties.items():
            if isinstance(value, str):
                # Check if it might be a title property
                if key.lower() in ["name", "title", "task"]:
                    notion_properties[key] = {"title": [{"text": {"content": value}}]}
                else:
                    notion_properties[key] = {"rich_text": [{"text": {"content": value}}]}
            elif isinstance(value, bool):
                notion_properties[key] = {"checkbox": value}
            elif isinstance(value, (int, float)):
                notion_properties[key] = {"number": value}
            else:
                notion_properties[key] = {"rich_text": [{"text": {"content": str(value)}}]}
        
        try:
            from core.notion_export.client import NotionClient

            client = NotionClient(Config.NOTION_TOKEN)
            created = client.create_database_entry(database_id=database_id, properties=notion_properties)
            if created and isinstance(created, dict) and created.get("id"):
                page_id = created.get("id")
                return f"✅ Added row to database (ID: {page_id[:8]}...)"
            return "❌ Failed to add row. Check that the integration has access and the database/data source ID is correct."
                
        except Exception as e:
            return f"❌ Error adding row: {e}"

    def _update_notion_database_row(self, page_id: str, properties: Dict[str, Any]) -> str:
        """Update properties of a Notion database row (page)."""
        import requests
        
        if not Config.NOTION_TOKEN:
            return "❌ NOTION_TOKEN not configured"
        
        headers = {
            "Authorization": f"Bearer {Config.NOTION_TOKEN}",
            "Notion-Version": Config.NOTION_VERSION,
            "Content-Type": "application/json",
        }
        
        # Convert simple properties to Notion format
        notion_properties = {}
        for key, value in properties.items():
            if isinstance(value, str):
                notion_properties[key] = {"rich_text": [{"text": {"content": value}}]}
            elif isinstance(value, bool):
                notion_properties[key] = {"checkbox": value}
            elif isinstance(value, (int, float)):
                notion_properties[key] = {"number": value}
            else:
                notion_properties[key] = {"rich_text": [{"text": {"content": str(value)}}]}
        
        try:
            resp = requests.patch(
                f"https://api.notion.com/v1/pages/{page_id}",
                headers=headers,
                json={"properties": notion_properties},
                timeout=30
            )
            
            if resp.status_code == 200:
                return f"✅ Updated row {page_id[:8]}..."
            else:
                return f"❌ Failed to update row: {resp.status_code}"
                
        except Exception as e:
            return f"❌ Error updating row: {e}"

    def _create_notion_subpage(self, parent_id: str, title: str, content: str) -> str:
        """Create a subpage under a parent Notion page."""
        import requests
        
        if not Config.NOTION_TOKEN:
            return "❌ NOTION_TOKEN not configured"
        
        headers = {
            "Authorization": f"Bearer {Config.NOTION_TOKEN}",
            "Notion-Version": Config.NOTION_VERSION,
            "Content-Type": "application/json",
        }
        
        # Create page with content
        children = []
        for para in content.split("\n\n"):
            if para.strip():
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": para.strip()}}]
                    }
                })
        
        try:
            resp = requests.post(
                "https://api.notion.com/v1/pages",
                headers=headers,
                json={
                    "parent": {"page_id": parent_id},
                    "properties": {
                        "title": {"title": [{"text": {"content": title}}]}
                    },
                    "children": children[:100]  # Notion limit
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                page_id = resp.json().get("id", "")
                return f"✅ Created subpage '{title}' (ID: {page_id[:8]}...)"
            else:
                return f"❌ Failed to create subpage: {resp.status_code}"
                
        except Exception as e:
            return f"❌ Error creating subpage: {e}"

    def _reply_to_slack_thread(self, tools, channel: str, thread_ts: str, message: str) -> str:
        """Reply to a Slack thread."""
        try:
            if not tools.slack_client:
                return "❌ Slack client not available"
            
            result = tools.slack_client.chat_postMessage(
                channel=channel,
                text=message,
                thread_ts=thread_ts
            )
            if result.get("ok"):
                return f"✅ Replied to thread in {channel}"
            else:
                return f"❌ Failed to reply: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Error replying to thread: {e}"

    def _add_slack_reaction(self, tools, channel: str, timestamp: str, emoji: str) -> str:
        """Add a reaction to a Slack message."""
        try:
            if not tools.slack_client:
                return "❌ Slack client not available"
            
            result = tools.slack_client.reactions_add(
                channel=channel,
                timestamp=timestamp,
                name=emoji.strip(":")
            )
            if result.get("ok"):
                return f"✅ Added :{emoji}: reaction"
            else:
                return f"❌ Failed to add reaction: {result.get('error', 'Unknown error')}"
        except Exception as e:
            return f"❌ Error adding reaction: {e}"

    def _add_notion_comment(self, page_id: str, comment: str) -> str:
        """Add a comment to a Notion page."""
        import requests
        
        if not Config.NOTION_TOKEN:
            return "❌ NOTION_TOKEN not configured"
        
        headers = {
            "Authorization": f"Bearer {Config.NOTION_TOKEN}",
            "Notion-Version": Config.NOTION_VERSION,
            "Content-Type": "application/json",
        }
        
        try:
            resp = requests.post(
                "https://api.notion.com/v1/comments",
                headers=headers,
                json={
                    "parent": {"page_id": page_id},
                    "rich_text": [{"type": "text", "text": {"content": comment}}]
                },
                timeout=30
            )
            
            if resp.status_code == 200:
                return f"✅ Added comment to page"
            else:
                return f"❌ Failed to add comment: {resp.status_code} - {resp.text[:100]}"
                
        except Exception as e:
            return f"❌ Error adding comment: {e}"

    async def _process_with_ai(
        self, source_data: str, prompt_config: Dict[str, Any], run_id: str
    ) -> str:
        """Process source data with AI using configured prompt."""
        system_prompt = prompt_config.get(
            "system_prompt",
            "You are a helpful assistant that processes and analyzes data."
        )
        user_instructions = prompt_config.get("user_instructions", "")
        output_format = prompt_config.get("output_format", "markdown")

        # Build the full prompt
        full_prompt = f"""## Source Data:
{source_data}

## Your Task:
{user_instructions}

Please provide your response in {output_format} format."""

        try:
            return await self._chat_completion(
                model="gpt-5-nano",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": full_prompt},
                ],
                max_output_tokens=4000,
                temperature=0.7,
                run_id=run_id,
            )
        except Exception as e:
            self._log(run_id, "error", f"AI processing error: {e}")
            raise

    async def _execute_outputs(
        self, ai_response: str, output_config: Dict[str, Any], run_id: str
    ) -> Dict[str, Any]:
        """Execute configured output actions."""
        outputs = output_config.get("outputs", [])
        results = []

        def _looks_successful(details: Any) -> bool:
            if details is None:
                return False
            if isinstance(details, str):
                return details.strip().startswith("✅")
            if isinstance(details, dict):
                res = details.get("result")
                if isinstance(res, str):
                    return res.strip().startswith("✅")
            return True

        for output in outputs:
            output_type = output.get("type")
            
            try:
                if output_type == "notion_page":
                    result = await self._output_to_notion(ai_response, output, run_id)
                    ok = _looks_successful(result)
                    if not ok:
                        self._log(run_id, "error", f"Notion output failed: {result}")
                    results.append({"type": "notion", "success": ok, "details": result})
                    
                elif output_type == "slack_message":
                    result = await self._output_to_slack(ai_response, output, run_id)
                    results.append({"type": "slack", "success": True, "details": result})
                    
                elif output_type == "gmail_draft":
                    result = await self._output_to_gmail_draft(ai_response, output, run_id)
                    results.append({"type": "gmail_draft", "success": True, "details": result})
                    
                elif output_type == "display":
                    # Just display in UI, no external action
                    results.append({
                        "type": "display",
                        "success": True,
                        "details": {"message": "Output displayed in UI"}
                    })
                else:
                    self._log(run_id, "warning", f"Unknown output type: {output_type}")
                    
            except Exception as e:
                self._log(run_id, "error", f"Output {output_type} failed: {e}")
                results.append({
                    "type": output_type,
                    "success": False,
                    "error": str(e)
                })

        return {"outputs": results, "success": all(r.get("success") for r in results)}

    async def _output_to_notion(
        self, content: str, output_config: Dict[str, Any], run_id: str
    ) -> Dict[str, Any]:
        """Create or append to a Notion page.
        
        IMPORTANT: This is a FALLBACK method called when the tool-calling agent
        didn't already write to the destination. It should NOT dump raw AI thinking.
        """
        from agent.langchain_tools import WorkforceTools
        import requests
        
        tools = WorkforceTools(user_id=self.user_id)
        page_id = output_config.get("page_id")
        mode = output_config.get("mode", "append")
        title = output_config.get("title", f"Workflow Output - {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        output_prompt = (output_config.get("output_prompt") or "").strip()

        # ----------------------------------------------------------------
        # STRIP AI THINKING/PLANNING from content - users don't want this
        # ----------------------------------------------------------------
        def _clean_ai_response(text: str) -> str:
            """Remove AI thinking/planning sections from response."""
            if not text:
                return ""
            lines = text.split("\n")
            clean_lines = []
            skip_section = False
            for line in lines:
                lower = line.lower().strip()
                # Skip known AI thinking headers
                if lower.startswith("### thinking") or lower.startswith("## thinking"):
                    skip_section = True
                    continue
                if lower.startswith("### actions_taken") or lower.startswith("## actions_taken"):
                    skip_section = True
                    continue
                if lower.startswith("### actions") or lower.startswith("## actions"):
                    skip_section = True
                    continue
                # Resume on new major section
                if skip_section and (lower.startswith("### ") or lower.startswith("## ")) and "thinking" not in lower and "action" not in lower:
                    skip_section = False
                if not skip_section:
                    clean_lines.append(line)
            result = "\n".join(clean_lines).strip()
            # If we stripped everything, return empty
            return result

        cleaned_content = _clean_ai_response(content)

        def _extract_row_name(text: str) -> Optional[str]:
            if not text:
                return None
            m = re.search(r"find\s+(?:the\s+)?(.+?)\s+row", text, flags=re.IGNORECASE)
            if m:
                candidate = m.group(1).strip().strip('"\'')
                return candidate or None
            return None

        if page_id:
            # If the target is a database, the user often expects us to update a specific row (page).
            is_database = False
            if Config.NOTION_TOKEN:
                try:
                    headers = {
                        "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                        "Notion-Version": Config.NOTION_VERSION,
                        "Content-Type": "application/json",
                    }
                    db_resp = requests.get(
                        f"https://api.notion.com/v1/databases/{page_id}",
                        headers=headers,
                        timeout=20,
                    )
                    if db_resp.status_code == 200:
                        is_database = True
                    else:
                        ds_resp = requests.get(
                            f"https://api.notion.com/v1/data_sources/{page_id}",
                            headers=headers,
                            timeout=20,
                        )
                        if ds_resp.status_code == 200:
                            is_database = True
                except Exception:
                    is_database = False

            # If the target is a database ROW page, do not rewrite body in deterministic fallback.
            if (not is_database) and Config.NOTION_TOKEN:
                try:
                    headers = {
                        "Authorization": f"Bearer {Config.NOTION_TOKEN}",
                        "Notion-Version": Config.NOTION_VERSION,
                        "Content-Type": "application/json",
                    }
                    page_resp = requests.get(
                        f"https://api.notion.com/v1/pages/{page_id}",
                        headers=headers,
                        timeout=20,
                    )
                    if page_resp.status_code == 200:
                        parent = (page_resp.json() or {}).get("parent", {}) or {}
                        if parent.get("type") in {"database_id", "data_source_id"}:
                            self._log(
                                run_id,
                                "warning",
                                "Notion destination is a database row page; deterministic fallback will not rewrite page body. Use entry_id property update tools.",
                            )
                            return {
                                "page_id": page_id,
                                "action": "skipped",
                                "result": "❌ Target is a Notion database row. Fallback refuses to replace/append page body. Use entry_id property update tools.",
                            }
                except Exception:
                    pass

            if is_database:
                row_name = _extract_row_name(output_prompt)
                if row_name and cleaned_content:
                    result = tools.update_notion_database_row_content(
                        database_id=page_id,
                        entry_name=row_name,
                        content=cleaned_content,
                        mode=mode,
                    )
                    self._log(run_id, "info", f"Updated Notion database row '{row_name}' in {page_id}")
                    return {"database_id": page_id, "row": row_name, "action": "row_updated", "result": result}

                # For databases without a row name, DON'T append raw text - that's not how databases work
                self._log(
                    run_id,
                    "warning",
                    "Notion target is a database - use update_notion_entry_by_name tool to update specific rows. Skipping raw text append.",
                )
                return {
                    "database_id": page_id,
                    "action": "skipped",
                    "result": "❌ Cannot append raw text to a Notion database. Use targeted row updates instead.",
                }

            # Only append if we have meaningful cleaned content
            if not cleaned_content:
                self._log(run_id, "info", "No content to write after cleaning AI thinking sections")
                return {"page_id": page_id, "action": "skipped", "result": "No meaningful content to write"}

            if mode == "append":
                result = tools.append_to_notion_page(page_id=page_id, content=cleaned_content)
                self._log(run_id, "info", f"Appended to Notion page {page_id}")
                return {"page_id": page_id, "action": "appended", "result": result}

        if page_id and mode == "replace":
            if not cleaned_content:
                self._log(run_id, "info", "No content to write after cleaning AI thinking sections")
                return {"page_id": page_id, "action": "skipped", "result": "No meaningful content to write"}
            result = tools.replace_notion_page_content(page_id=page_id, content=cleaned_content)
            self._log(run_id, "info", f"Replaced content in Notion page {page_id}")
            return {"page_id": page_id, "action": "replaced", "result": result}

        # Create new page - only if we have content
        if not cleaned_content:
            self._log(run_id, "info", "No content to write after cleaning AI thinking sections")
            return {"action": "skipped", "result": "No meaningful content to write"}
        result = tools.create_notion_page(title=title, content=cleaned_content)
        self._log(run_id, "info", f"Created Notion page: {title}")
        return {"title": title, "action": "created", "result": result}

    async def _output_to_slack(
        self, content: str, output_config: Dict[str, Any], run_id: str
    ) -> Dict[str, Any]:
        """Send message to Slack channel."""
        from agent.langchain_tools import WorkforceTools
        
        tools = WorkforceTools(user_id=self.user_id)
        channel = output_config.get("channel")
        
        if not channel:
            raise ValueError("Slack channel not specified in output config")

        result = tools.send_slack_message(channel=channel, text=content)
        self._log(run_id, "info", f"Sent message to Slack channel {channel}")
        return {"channel": channel, "result": result}

    async def _output_to_gmail_draft(
        self, content: str, output_config: Dict[str, Any], run_id: str
    ) -> Dict[str, Any]:
        """Create Gmail draft."""
        from agent.langchain_tools import WorkforceTools
        
        tools = WorkforceTools(user_id=self.user_id)
        to = output_config.get("to", "")
        subject = output_config.get("subject", "Workflow Output")

        result = tools.create_gmail_draft(to=to, subject=subject, body=content)
        self._log(run_id, "info", f"Created Gmail draft to {to}")
        return {"to": to, "subject": subject, "result": result}

    def _update_run(self, run_id: str, **fields):
        """Update workflow run fields."""
        self.db_manager.update_workflow_run(run_id, **fields)

    def _log(self, run_id: str, level: str, message: str):
        """Add log entry to workflow run."""
        self.db_manager.add_workflow_run_log(run_id, level, message)
        if level == "error":
            logger.error(f"[Run {run_id}] {message}")
        else:
            logger.info(f"[Run {run_id}] {message}")
