"""Notion API client."""

from typing import List, Dict, Any, Optional
from notion_client import Client
from notion_client.errors import APIResponseError

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
