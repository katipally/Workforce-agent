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
        
        if self.token:
            self.client = Client(auth=self.token)
    
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
