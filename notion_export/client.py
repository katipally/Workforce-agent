"""Notion API client wrapper."""

import os
from typing import List, Dict, Any
from notion_client import Client
from utils.logger import get_logger

logger = get_logger(__name__)


class NotionClient:
    """Simple Notion API client."""
    
    def __init__(self, token: str = None):
        """Initialize Notion client.
        
        Args:
            token: Notion integration token. If not provided, uses NOTION_TOKEN from env.
        """
        self.token = token or os.getenv('NOTION_TOKEN')
        
        if not self.token:
            raise ValueError("Notion token not provided. Set NOTION_TOKEN in .env or pass token parameter.")
        
        self.client = Client(auth=self.token)
        logger.info("Notion client initialized")
    
    @staticmethod
    def normalize_page_id(page_id: str) -> str:
        """Normalize page ID to include dashes.
        
        Args:
            page_id: Page ID with or without dashes
            
        Returns:
            Page ID in UUID format with dashes
        """
        # Remove any existing dashes
        clean_id = page_id.replace("-", "")
        
        # Add dashes in UUID format: 8-4-4-4-12
        if len(clean_id) == 32:
            return f"{clean_id[:8]}-{clean_id[8:12]}-{clean_id[12:16]}-{clean_id[16:20]}-{clean_id[20:]}"
        
        return page_id  # Return as-is if not 32 chars
    
    def create_page(self, parent_id: str, title: str, blocks: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a new Notion page.
        
        Args:
            parent_id: Parent page ID where this page will be created
            title: Page title
            blocks: List of block objects to add as content
            
        Returns:
            Created page object
        """
        try:
            # Normalize page ID
            parent_id = self.normalize_page_id(parent_id)
            
            page_data = {
                "parent": {"page_id": parent_id},
                "properties": {
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
            }
            
            # Add blocks if provided (max 100 per request)
            if blocks:
                page_data["children"] = blocks[:100]
            
            page = self.client.pages.create(**page_data)
            logger.info(f"Created Notion page: {title}")
            
            # If more than 100 blocks, append the rest
            if blocks and len(blocks) > 100:
                remaining_blocks = blocks[100:]
                self.append_blocks(page["id"], remaining_blocks)
            
            return page
        
        except Exception as e:
            logger.error(f"Failed to create Notion page: {e}")
            raise
    
    def append_blocks(self, block_id: str, blocks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Append blocks to existing page or block.
        
        Args:
            block_id: ID of page or block to append to
            blocks: List of block objects (max 100 per call)
            
        Returns:
            Response from API
        """
        try:
            # Notion API limits to 100 blocks per request
            batch_size = 100
            
            for i in range(0, len(blocks), batch_size):
                batch = blocks[i:i + batch_size]
                self.client.blocks.children.append(
                    block_id=block_id,
                    children=batch
                )
                logger.info(f"Appended {len(batch)} blocks (batch {i//batch_size + 1})")
            
            return {"success": True}
        
        except Exception as e:
            logger.error(f"Failed to append blocks: {e}")
            raise
    
    def test_connection(self) -> bool:
        """Test Notion connection.
        
        Returns:
            True if connection successful
        """
        try:
            # Try to list users to verify connection
            self.client.users.me()
            logger.info("Notion connection successful")
            return True
        except Exception as e:
            logger.error(f"Notion connection failed: {e}")
            return False
