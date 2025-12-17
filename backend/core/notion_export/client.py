"""Notion API client."""

from typing import List, Dict, Any, Optional
import time

from notion_client import Client
from notion_client.errors import APIResponseError, RequestTimeoutError

from config import Config
from utils.logger import get_logger

logger = get_logger(__name__)


class NotionClient:
    """Notion API client for creating and managing pages."""
    
    def __init__(self, token: str = None):
        """Initialize Notion client.
        
        Args:
            token: Notion integration token
        """
        self.token = token or Config.NOTION_TOKEN
        self.client = None
        self._database_to_data_source: Dict[str, str] = {}
        
        if self.token:
            self.client = Client(auth=self.token, notion_version=Config.NOTION_VERSION)

    def _headers(self, *, content_type: bool = False) -> Dict[str, str]:
        headers: Dict[str, str] = {
            "Authorization": f"Bearer {self.token}",
            "Notion-Version": Config.NOTION_VERSION,
        }
        if content_type:
            headers["Content-Type"] = "application/json"
        return headers

    def _resolve_data_source_id(self, database_or_data_source_id: str) -> Optional[str]:
        import requests

        if not self.token:
            return None

        key = (database_or_data_source_id or "").strip()
        if not key:
            return None

        cached = self._database_to_data_source.get(key)
        if cached:
            return cached

        # Prefer treating the ID as a database_id first.
        try:
            resp = requests.get(
                f"https://api.notion.com/v1/databases/{key}",
                headers=self._headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json() or {}
                data_sources = data.get("data_sources") or []
                if isinstance(data_sources, list) and data_sources:
                    first = data_sources[0] if isinstance(data_sources[0], dict) else None
                    ds_id = (first or {}).get("id")
                    if ds_id:
                        self._database_to_data_source[key] = ds_id
                        return ds_id
                return None
        except Exception:
            pass

        # Fall back to treating the ID as a data_source_id.
        try:
            resp = requests.get(
                f"https://api.notion.com/v1/data_sources/{key}",
                headers=self._headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                return key
        except Exception:
            pass

        return None
    
    def test_connection(self) -> bool:
        """Test Notion API connection.
        
        Returns:
            True if connection successful
        """
        if not self.client:
            logger.error("Notion token not configured")
            return False
        
        try:
            # Try to get current user
            self.client.users.me()
            logger.info("Notion connection successful")
            return True
        
        except APIResponseError as error:
            logger.error(f"Notion API error: {error}")
            return False
    
    def create_page(
        self,
        parent_page_id: str,
        title: str,
        children: List[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Create a new page.
        
        Args:
            parent_page_id: Parent page ID
            title: Page title
            children: List of block children
            
        Returns:
            Created page ID or None
        """
        if not self.client:
            logger.error("Notion client not initialized")
            return None
        
        try:
            properties = {
                "title": {
                    "title": [
                        {
                            "text": {
                                "content": title
                            }
                        }
                    ]
                }
            }
            
            params = {
                "parent": {"page_id": parent_page_id},
                "properties": properties
            }
            
            if children:
                params["children"] = children
            
            response = self.client.pages.create(**params)
            page_id = response['id']
            
            logger.info(f"Created Notion page: {title} ({page_id})")
            return page_id
        
        except APIResponseError as error:
            logger.error(f"Error creating page: {error}")
            return None
        except Exception as error:
            # Catch network / timeout errors from the underlying HTTP client so
            # callers never see unhandled exceptions.
            logger.error(
                "Unexpected error creating Notion page %s: %s",
                title,
                error,
                exc_info=True,
            )
            return None
    
    def append_blocks(
        self,
        page_id: str,
        blocks: List[Dict[str, Any]]
    ) -> bool:
        """Append blocks to a page.
        
        Args:
            page_id: Page ID
            blocks: List of blocks to append
            
        Returns:
            True if successful
        """
        if not self.client:
            logger.error("Notion client not initialized")
            return False
        
        try:
            # Notion API limit: 100 blocks per request
            for i in range(0, len(blocks), 100):
                batch = blocks[i:i+100]
                self.client.blocks.children.append(
                    block_id=page_id,
                    children=batch
                )
            
            logger.info(f"Appended {len(blocks)} blocks to page {page_id}")
            return True
        
        except APIResponseError as error:
            logger.error(f"Error appending blocks: {error}")
            return False
        except Exception as error:
            logger.error(
                "Unexpected error appending blocks to page %s: %s",
                page_id,
                error,
                exc_info=True,
            )
            return False
    
    def append_blocks_and_get_ids(
        self,
        block_id: str,
        blocks: List[Dict[str, Any]],
    ) -> List[str]:
        """Append blocks and return their Notion IDs.

        This is similar to append_blocks but collects the IDs of the newly
        created child blocks so callers can keep precise mappings.
        """
        if not self.client:
            logger.error("Notion client not initialized")
            return []

        created_ids: List[str] = []
        try:
            for i in range(0, len(blocks), 100):
                batch = blocks[i : i + 100]
                resp = self.client.blocks.children.append(
                    block_id=block_id,
                    children=batch,
                )
                for child in resp.get("results", []):
                    child_id = child.get("id")
                    if child_id:
                        created_ids.append(child_id)

            logger.info(f"Appended {len(blocks)} blocks to {block_id} (ids={len(created_ids)})")
            return created_ids
        except APIResponseError as error:
            msg = str(error).lower()
            if "archived" in msg:
                logger.warning(
                    "Cannot append blocks to archived Notion block %s; skipping. Error: %s",
                    block_id,
                    error,
                )
            else:
                logger.error(f"Error appending blocks with ids: {error}")
            return []
        except Exception as error:
            logger.error(
                "Unexpected error appending blocks with ids for %s: %s",
                block_id,
                error,
                exc_info=True,
            )
            return []
    
    def update_bulleted_list_item(self, block_id: str, text: str) -> bool:
        """Update the text content of an existing bulleted list item block."""
        if not self.client:
            logger.error("Notion client not initialized")
            return False

        # Retry a few times on transient network issues (timeouts, disconnects)
        # so that short-lived Notion API problems do not cause noisy errors.
        max_attempts = 3
        delay_seconds = 1.0

        for attempt in range(1, max_attempts + 1):
            try:
                self.client.blocks.update(
                    block_id=block_id,
                    bulleted_list_item={
                        "rich_text": [
                            {
                                "type": "text",
                                "text": {"content": text},
                            }
                        ]
                    },
                )
                return True
            except APIResponseError as error:
                # API errors (4xx/5xx with structured response) are not
                # generally recoverable by retrying the same request, so we
                # log once and stop.
                msg = str(error).lower()
                if "archived" in msg:
                    logger.warning(
                        "Cannot update archived Notion block %s; skipping. Error: %s",
                        block_id,
                        error,
                    )
                else:
                    logger.error(
                        "Error updating bulleted list item %s (API error): %s",
                        block_id,
                        error,
                    )
                return False
            except Exception as error:
                # Handle transport-level issues like timeouts and remote
                # disconnects from the underlying HTTP client.
                if isinstance(error, RequestTimeoutError):
                    logger.warning(
                        "Timeout updating Notion block %s (attempt %d/%d): %s",
                        block_id,
                        attempt,
                        max_attempts,
                        error,
                    )
                else:
                    logger.warning(
                        "Network error updating Notion block %s (attempt %d/%d): %s",
                        block_id,
                        attempt,
                        max_attempts,
                        error,
                    )

                if attempt == max_attempts:
                    logger.error(
                        "Giving up updating Notion block %s after %d attempts due to repeated errors",
                        block_id,
                        max_attempts,
                    )
                    return False

                time.sleep(delay_seconds)
                delay_seconds *= 2
    
    def create_heading(self, text: str, level: int = 2) -> Dict[str, Any]:
        """Create heading block.
        
        Args:
            text: Heading text
            level: Heading level (1, 2, or 3)
            
        Returns:
            Heading block dict
        """
        heading_type = f"heading_{level}"
        return {
            "object": "block",
            "type": heading_type,
            heading_type: {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }
    
    def create_paragraph(self, text: str) -> Dict[str, Any]:
        """Create paragraph block.
        
        Args:
            text: Paragraph text
            
        Returns:
            Paragraph block dict
        """
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }
    
    def create_code_block(self, code: str, language: str = "plain text") -> Dict[str, Any]:
        """Create code block.
        
        Args:
            code: Code content
            language: Programming language
            
        Returns:
            Code block dict
        """
        return {
            "object": "block",
            "type": "code",
            "code": {
                "rich_text": [{"type": "text", "text": {"content": code}}],
                "language": language
            }
        }
    
    def create_bulleted_list_item(self, text: str) -> Dict[str, Any]:
        """Create bulleted list item.
        
        Args:
            text: List item text
            
        Returns:
            Bulleted list item block dict
        """
        return {
            "object": "block",
            "type": "bulleted_list_item",
            "bulleted_list_item": {
                "rich_text": [{"type": "text", "text": {"content": text}}]
            }
        }
    
    def create_divider(self) -> Dict[str, Any]:
        """Create divider block.
        
        Returns:
            Divider block dict
        """
        return {
            "object": "block",
            "type": "divider",
            "divider": {}
        }

    def is_block_archived(self, block_id: str) -> Optional[bool]:
        """Return True if the given block/page is archived in Notion.

        Tries to retrieve the object first as a block, then as a page.
        Returns None if it cannot be retrieved.
        """
        if not self.client:
            logger.error("Notion client not initialized")
            return None

        # Try as a block first
        try:
            block = self.client.blocks.retrieve(block_id=block_id)
            return bool(block.get("archived"))
        except APIResponseError as block_error:
            # If it isn't a block, try retrieving as a page
            try:
                page = self.client.pages.retrieve(page_id=block_id)
                return bool(page.get("archived"))
            except APIResponseError as page_error:
                logger.error(
                    "Failed to retrieve Notion block/page %s: %s / %s",
                    block_id,
                    block_error,
                    page_error,
                )
                return None
        except Exception as error:
            # Network / timeout issues when checking archive state should never
            # crash callers; treat as unknown (None) and log once.
            logger.warning(
                "Error retrieving archive state for Notion block/page %s: %s",
                block_id,
                error,
            )
            return None

    # =========================================================================
    # DATABASE OPERATIONS
    # =========================================================================

    def get_database(self, database_id: str) -> Optional[Dict[str, Any]]:
        """Get database metadata including schema/properties.
        
        Uses direct HTTP API for compatibility.
        """
        import requests
        
        if not self.token:
            return None
        
        headers = self._headers()
        
        try:
            response = requests.get(
                f"https://api.notion.com/v1/databases/{database_id}",
                headers=headers,
                timeout=30,
            )
            
            if response.status_code == 404:
                logger.debug(f"Database {database_id} not found")
                return None
            
            if response.status_code == 200:
                db_obj = response.json() or {}
                ds_id = self._resolve_data_source_id(database_id)
                if not ds_id:
                    return db_obj

                ds_resp = requests.get(
                    f"https://api.notion.com/v1/data_sources/{ds_id}",
                    headers=headers,
                    timeout=30,
                )
                if ds_resp.status_code != 200:
                    return db_obj

                ds_obj = ds_resp.json() or {}
                merged = dict(db_obj)
                merged["properties"] = ds_obj.get("properties")
                merged["data_source_id"] = ds_id
                return merged

            # Not a database_id; try treating as data_source_id
            ds_resp = requests.get(
                f"https://api.notion.com/v1/data_sources/{database_id}",
                headers=headers,
                timeout=30,
            )
            if ds_resp.status_code == 200:
                return ds_resp.json()

            logger.debug(f"Not a database or access error for {database_id}: {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Error retrieving database {database_id}: {e}")
            return None

    def search(
        self,
        query: str = "",
        filter_type: Optional[str] = None,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """Search across Notion workspace for pages and/or databases.
        
        This is the general-purpose search method that can find both pages and databases.
        
        Args:
            query: Search query text (can be empty to list all)
            filter_type: Optional filter - "page" or "database" to filter results
            max_results: Maximum number of results to return
            
        Returns:
            List of matching page/database objects
        """
        import requests
        
        if not self.token:
            return []
        
        results: List[Dict[str, Any]] = []
        cursor: Optional[str] = None
        
        headers = self._headers(content_type=True)
        
        try:
            while len(results) < max_results:
                payload: Dict[str, Any] = {"page_size": min(100, max_results - len(results))}
                if query:
                    payload["query"] = query
                if filter_type in ("page", "database", "data_source"):
                    value = "data_source" if filter_type == "database" else filter_type
                    payload["filter"] = {"value": value, "property": "object"}
                if cursor:
                    payload["start_cursor"] = cursor
                
                response = requests.post(
                    "https://api.notion.com/v1/search",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                batch = data.get("results", [])
                results.extend(batch)
                
                if not data.get("has_more") or not data.get("next_cursor"):
                    break
                cursor = data.get("next_cursor")
            
            logger.info(f"Search found {len(results)} results for query='{query}' filter={filter_type}")
            return results[:max_results]
            
        except Exception as e:
            logger.error(f"Error in Notion search: {e}")
            return []

    def search_databases(self, title: Optional[str] = None) -> List[Dict[str, Any]]:
        """Search for all databases in the workspace, optionally filtering by title.
        
        This is useful for finding the ORIGINAL database when you have a linked view.
        Linked databases cannot be queried - you must query the original.
        
        Args:
            title: Optional title to filter by (case-insensitive contains match)
            
        Returns:
            List of database objects
        """
        import requests
        
        if not self.token:
            return []
        
        databases: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        headers = self._headers(content_type=True)
        
        try:
            while True:
                payload: Dict[str, Any] = {"page_size": 100}
                if title:
                    payload["query"] = title
                if cursor:
                    payload["start_cursor"] = cursor
                
                response = requests.post(
                    "https://api.notion.com/v1/search",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                
                for item in results:
                    if item.get("object") in ("database", "data_source"):
                        if title:
                            db_title_parts = item.get("title", [])
                            db_title = "".join(t.get("plain_text", "") for t in db_title_parts)
                            if title.lower() in db_title.lower():
                                databases.append(item)
                        else:
                            databases.append(item)
                
                if not data.get("has_more"):
                    break
                cursor = data.get("next_cursor")
                if not cursor:
                    break
            
            logger.info(f"Found {len(databases)} databases" + (f" matching '{title}'" if title else ""))
            return databases
            
        except Exception as e:
            logger.error(f"Error searching databases: {e}")
            return []

    def find_database_by_title(self, title: str) -> Optional[Dict[str, Any]]:
        """Find a database by its title (exact match, case-insensitive).
        
        This is the primary way to get the queryable database when you
        only have a linked view's title.
        """
        databases = self.search_databases(title)
        
        for db in databases:
            db_title_parts = db.get("title", [])
            db_title = "".join(t.get("plain_text", "") for t in db_title_parts)
            if db_title.lower().strip() == title.lower().strip():
                logger.info(f"Found exact match database '{title}' with ID {db.get('id')}")
                return db
        
        # Return first partial match if no exact match
        if databases:
            logger.info(f"No exact match for '{title}', returning first partial match")
            return databases[0]
        
        return None

    def query_database(
        self,
        database_id: str,
        filter_obj: Optional[Dict[str, Any]] = None,
        sorts: Optional[List[Dict[str, Any]]] = None,
        page_size: int = 100,
        max_results: int = 500,
    ) -> List[Dict[str, Any]]:
        """Query a Notion database and return all entries with pagination.
        
        Uses direct HTTP API for compatibility with all SDK versions.
        
        Args:
            database_id: The database ID to query
            filter_obj: Optional Notion filter object
            sorts: Optional list of sort objects
            page_size: Results per page (max 100)
            max_results: Maximum total results to return
        
        Returns:
            List of database entries (pages) with their properties
        """
        import requests
        
        if not self.token:
            logger.error("Notion token not configured")
            return []

        results: List[Dict[str, Any]] = []
        cursor: Optional[str] = None

        headers = self._headers(content_type=True)

        data_source_id = self._resolve_data_source_id(database_id)
        if not data_source_id:
            logger.warning(
                "Could not resolve data_source_id for %s; cannot query database in Notion-Version %s",
                database_id,
                Config.NOTION_VERSION,
            )
            return []

        try:
            while len(results) < max_results:
                payload: Dict[str, Any] = {"page_size": min(page_size, 100)}
                if filter_obj:
                    payload["filter"] = filter_obj
                if sorts:
                    payload["sorts"] = sorts
                if cursor:
                    payload["start_cursor"] = cursor

                response = requests.post(
                    f"https://api.notion.com/v1/data_sources/{data_source_id}/query",
                    headers=headers,
                    json=payload,
                    timeout=30,
                )
                
                if response.status_code == 404:
                    logger.warning(f"Database {database_id} not found or not accessible")
                    return []
                
                response.raise_for_status()
                data = response.json()
                batch = data.get("results", [])
                results.extend(batch)

                if not data.get("has_more") or not data.get("next_cursor"):
                    break
                cursor = data.get("next_cursor")

            logger.info(f"Queried database {database_id}, got {len(results)} entries")
            return results[:max_results]

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error querying database {database_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error querying database {database_id}: {e}", exc_info=True)
            return []

    def extract_property_value(self, prop: Dict[str, Any]) -> Any:
        """Extract the actual value from a Notion property object.
        
        Handles all Notion property types: title, rich_text, number, select,
        multi_select, date, checkbox, url, email, phone_number, formula,
        relation, rollup, people, files, created_time, last_edited_time, etc.
        """
        prop_type = prop.get("type")
        if not prop_type:
            return None

        type_data = prop.get(prop_type)
        if type_data is None:
            return None

        # Title and rich_text: extract plain text
        if prop_type in ("title", "rich_text"):
            if isinstance(type_data, list):
                return "".join(rt.get("plain_text", "") for rt in type_data).strip()
            return ""

        # Number
        if prop_type == "number":
            return type_data

        # Select
        if prop_type == "select":
            return type_data.get("name") if type_data else None

        # Multi-select
        if prop_type == "multi_select":
            if isinstance(type_data, list):
                return [item.get("name") for item in type_data if item.get("name")]
            return []

        # Status (similar to select)
        if prop_type == "status":
            return type_data.get("name") if type_data else None

        # Date
        if prop_type == "date":
            if not type_data:
                return None
            start = type_data.get("start", "")
            end = type_data.get("end")
            if end:
                return f"{start} → {end}"
            return start

        # Checkbox
        if prop_type == "checkbox":
            return type_data

        # URL, email, phone_number
        if prop_type in ("url", "email", "phone_number"):
            return type_data

        # People
        if prop_type == "people":
            if isinstance(type_data, list):
                names = []
                for person in type_data:
                    name = person.get("name") or person.get("id", "Unknown")
                    names.append(name)
                return names
            return []

        # Files
        if prop_type == "files":
            if isinstance(type_data, list):
                urls = []
                for f in type_data:
                    # Could be external or file type
                    if f.get("type") == "external":
                        urls.append(f.get("external", {}).get("url", ""))
                    elif f.get("type") == "file":
                        urls.append(f.get("file", {}).get("url", ""))
                    elif f.get("name"):
                        urls.append(f.get("name"))
                return urls
            return []

        # Formula
        if prop_type == "formula":
            formula_type = type_data.get("type")
            if formula_type:
                return type_data.get(formula_type)
            return None

        # Relation
        if prop_type == "relation":
            if isinstance(type_data, list):
                return [rel.get("id") for rel in type_data if rel.get("id")]
            return []

        # Rollup
        if prop_type == "rollup":
            rollup_type = type_data.get("type")
            if rollup_type == "array":
                arr = type_data.get("array", [])
                return [self.extract_property_value(item) for item in arr]
            elif rollup_type:
                return type_data.get(rollup_type)
            return None

        # Created/edited time
        if prop_type in ("created_time", "last_edited_time"):
            return type_data

        # Created/edited by
        if prop_type in ("created_by", "last_edited_by"):
            return type_data.get("name") or type_data.get("id")

        # Unique ID
        if prop_type == "unique_id":
            prefix = type_data.get("prefix", "")
            number = type_data.get("number", "")
            return f"{prefix}{number}" if prefix else str(number)

        # Fallback: return raw data
        return type_data

    def format_database_entry(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Format a database entry (page) into a clean dictionary with extracted values."""
        result = {
            "id": entry.get("id", ""),
            "url": entry.get("url", ""),
            "created_time": entry.get("created_time", ""),
            "last_edited_time": entry.get("last_edited_time", ""),
            "properties": {},
        }

        properties = entry.get("properties", {})
        for prop_name, prop_value in properties.items():
            result["properties"][prop_name] = self.extract_property_value(prop_value)

        return result

    def update_database_entry(
        self,
        page_id: str,
        properties: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update properties of a database entry (page).
        
        Args:
            page_id: The page ID to update
            properties: Dict of property name -> new value (in Notion API format)
        
        Returns:
            Updated page object or None on error
        """
        if not self.client:
            logger.error("Notion client not initialized")
            return None

        try:
            response = self.client.pages.update(page_id=page_id, properties=properties)
            logger.info(f"Updated database entry {page_id}")
            return response
        except APIResponseError as e:
            logger.error(f"API error updating page {page_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error updating page {page_id}: {e}", exc_info=True)
            return None

    def build_property_update(
        self,
        prop_type: str,
        value: Any,
    ) -> Dict[str, Any]:
        """Build a Notion property update object from a type and value.
        
        Args:
            prop_type: The property type (title, rich_text, number, select, etc.)
            value: The new value
        
        Returns:
            Notion API property update object
        """
        if prop_type in ("title", "rich_text"):
            text_content = str(value) if value is not None else ""
            return {
                prop_type: [{"type": "text", "text": {"content": text_content}}]
            }

        if prop_type == "number":
            return {"number": float(value) if value is not None else None}

        if prop_type == "select":
            if value:
                return {"select": {"name": str(value)}}
            return {"select": None}

        if prop_type == "multi_select":
            if isinstance(value, list):
                return {"multi_select": [{"name": str(v)} for v in value]}
            elif value:
                return {"multi_select": [{"name": str(value)}]}
            return {"multi_select": []}

        if prop_type == "status":
            if value:
                return {"status": {"name": str(value)}}
            return {"status": None}

        if prop_type == "date":
            if value:
                # Value can be a single date string or dict with start/end
                if isinstance(value, dict):
                    return {"date": value}
                return {"date": {"start": str(value)}}
            return {"date": None}

        if prop_type == "checkbox":
            return {"checkbox": bool(value)}

        if prop_type == "url":
            return {"url": str(value) if value else None}

        if prop_type == "email":
            return {"email": str(value) if value else None}

        if prop_type == "phone_number":
            return {"phone_number": str(value) if value else None}

        # People: expects list of user IDs
        if prop_type == "people":
            if isinstance(value, list):
                return {"people": [{"id": str(uid)} for uid in value if uid]}
            elif value:
                return {"people": [{"id": str(value)}]}
            return {"people": []}

        # Relation: expects list of page IDs
        if prop_type == "relation":
            if isinstance(value, list):
                return {"relation": [{"id": str(pid)} for pid in value if pid]}
            elif value:
                return {"relation": [{"id": str(value)}]}
            return {"relation": []}

        # Files: expects list of external URLs or file objects
        if prop_type == "files":
            files_list = []
            items = value if isinstance(value, list) else [value] if value else []
            for item in items:
                if isinstance(item, dict):
                    # Already formatted file object
                    files_list.append(item)
                elif isinstance(item, str):
                    # URL string - create external file object
                    name = item.split("/")[-1][:100] or "file"
                    files_list.append({
                        "name": name,
                        "type": "external",
                        "external": {"url": item}
                    })
            return {"files": files_list}

        # For unsupported types, return empty dict
        logger.warning(f"Property type {prop_type} not supported for updates")
        return {}

    def update_database_schema(
        self,
        database_id: str,
        properties_updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update database schema (add/rename/remove columns).
        
        Args:
            database_id: The database ID to update
            properties_updates: Dict of property updates:
                - To add: {"New Column": {"type": "rich_text", ...}}
                - To rename: {"Old Name": {"name": "New Name"}}
                - To remove: {"Column Name": None}
        
        Returns:
            Updated database object or None on error
        """
        import requests
        
        if not self.token:
            logger.error("Notion token not configured")
            return None

        try:
            ds_id = self._resolve_data_source_id(database_id)
            if not ds_id:
                logger.error(f"Could not resolve data_source_id for database {database_id}")
                return None

            response = requests.patch(
                f"https://api.notion.com/v1/data_sources/{ds_id}",
                headers=self._headers(content_type=True),
                json={"properties": properties_updates},
                timeout=30,
            )
            
            if response.status_code == 200:
                logger.info(f"Updated database schema {database_id}")
                return response.json()
            else:
                logger.error(f"Error updating database schema: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Error updating database schema {database_id}: {e}", exc_info=True)
            return None

    def update_block(
        self,
        block_id: str,
        block_type: str,
        block_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Update a block's content.
        
        Args:
            block_id: The block ID to update
            block_type: Block type (paragraph, to_do, heading_1, etc.)
            block_data: Block-specific data to update
        
        Returns:
            Updated block object or None on error
        """
        import requests
        
        if not self.token:
            logger.error("Notion token not configured")
            return None

        try:
            response = requests.patch(
                f"https://api.notion.com/v1/blocks/{block_id}",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": Config.NOTION_VERSION,
                    "Content-Type": "application/json",
                },
                json={block_type: block_data},
                timeout=30,
            )
            
            if response.status_code == 200:
                logger.info(f"Updated block {block_id}")
                return response.json()
            else:
                logger.error(f"Error updating block: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Error updating block {block_id}: {e}", exc_info=True)
            return None

    def update_todo_checked(self, block_id: str, checked: bool) -> Optional[Dict[str, Any]]:
        """Update a to_do block's checked status.
        
        Args:
            block_id: The to_do block ID
            checked: Whether the to_do should be checked
        
        Returns:
            Updated block object or None on error
        """
        return self.update_block(block_id, "to_do", {"checked": checked})

    def get_block(self, block_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single block by ID.
        
        Args:
            block_id: The block ID to retrieve
        
        Returns:
            Block object or None on error
        """
        import requests
        
        if not self.token:
            logger.error("Notion token not configured")
            return None

        try:
            response = requests.get(
                f"https://api.notion.com/v1/blocks/{block_id}",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": Config.NOTION_VERSION,
                },
                timeout=30,
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error retrieving block: {response.status_code}")
                return None
        except Exception as e:
            logger.error(f"Error retrieving block {block_id}: {e}", exc_info=True)
            return None

    def get_block_children(
        self,
        block_id: str,
        max_depth: int = 3,
    ) -> List[Dict[str, Any]]:
        """Recursively fetch all block children with their IDs.
        
        Args:
            block_id: Parent block/page ID
            max_depth: Maximum recursion depth
        
        Returns:
            List of block objects with nested _children
        """
        import requests
        import time
        
        if not self.token:
            return []

        def fetch_children(parent_id: str, depth: int) -> List[Dict[str, Any]]:
            if depth > max_depth:
                return []
            
            blocks: List[Dict[str, Any]] = []
            cursor: Optional[str] = None
            
            while True:
                time.sleep(0.35)  # Rate limiting
                params: Dict[str, Any] = {"page_size": 100}
                if cursor:
                    params["start_cursor"] = cursor
                
                try:
                    resp = requests.get(
                        f"https://api.notion.com/v1/blocks/{parent_id}/children",
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Notion-Version": Config.NOTION_VERSION,
                        },
                        params=params,
                        timeout=30,
                    )
                    if resp.status_code != 200:
                        break
                    
                    data = resp.json()
                    results = data.get("results", []) or []
                    
                    for block in results:
                        block_copy = dict(block)
                        blocks.append(block_copy)
                        if block.get("has_children"):
                            block_copy["_children"] = fetch_children(block.get("id"), depth + 1)
                    
                    if not data.get("has_more"):
                        break
                    cursor = data.get("next_cursor")
                except Exception as e:
                    logger.warning(f"Error fetching block children for {parent_id}: {e}")
                    break
            
            return blocks
        
        return fetch_children(block_id, 0)

    def create_database_entry(
        self,
        database_id: str,
        properties: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Create a new entry (row) in a Notion database.
        
        Args:
            database_id: The database ID to add entry to
            properties: Dict of property name -> Notion API property object
        
        Returns:
            Created page object or None on error
        """
        import requests
        
        if not self.token:
            logger.error("Notion token not configured")
            return None

        try:
            data_source_id = self._resolve_data_source_id(database_id)
            if not data_source_id:
                logger.error(
                    "Could not resolve data_source_id for %s; cannot create row in Notion-Version %s",
                    database_id,
                    Config.NOTION_VERSION,
                )
                return None

            response = requests.post(
                "https://api.notion.com/v1/pages",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": Config.NOTION_VERSION,
                    "Content-Type": "application/json",
                },
                json={
                    "parent": {"type": "data_source_id", "data_source_id": data_source_id},
                    "properties": properties,
                },
                timeout=30,
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Created database entry in {database_id}: {result.get('id')}")
                return result
            else:
                logger.error(f"Error creating database entry: {response.status_code} - {response.text[:200]}")
                return None
        except Exception as e:
            logger.error(f"Error creating database entry in {database_id}: {e}", exc_info=True)
            return None
