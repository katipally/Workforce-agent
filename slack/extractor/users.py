"""User extractor."""
from typing import List
from tqdm import tqdm

from .base_extractor import BaseExtractor
from utils.logger import get_logger
from config import Config

logger = get_logger(__name__)


class UserExtractor(BaseExtractor):
    """Extract user information."""
    
    def extract_all_users(self) -> int:
        """Extract all users from workspace."""
        logger.info("Starting user extraction")
        
        count = 0
        users_list = []
        
        # Paginate through users
        for user in self._paginate(
            "users.list",
            "users_list",
            "members",
            limit=Config.DEFAULT_PAGE_SIZE
        ):
            users_list.append(user)
        
        logger.info(f"Fetched {len(users_list)} users. Saving to database...")
        
        # Save to database with progress bar
        with tqdm(total=len(users_list), desc="Saving users") as pbar:
            for user in users_list:
                try:
                    self.db_manager.save_user(user, self.workspace_id)
                    count += 1
                    pbar.update(1)
                except Exception as e:
                    logger.error(f"Failed to save user {user.get('id')}: {e}")
        
        logger.info(f"User extraction complete. Saved {count} users")
        return count
    
    def extract_user(self, user_id: str):
        """Extract specific user."""
        logger.info(f"Extracting user: {user_id}")
        
        try:
            response = self._call_api("users.info", "users_info", user=user_id)
            user = response.get("user", {})
            
            if user:
                self.db_manager.save_user(user, self.workspace_id)
                logger.info(f"User {user_id} saved")
                return user
        
        except Exception as e:
            logger.error(f"Failed to extract user {user_id}: {e}")
            raise
    
    def get_user_by_email(self, email: str):
        """Get user by email."""
        logger.info(f"Looking up user by email: {email}")
        
        try:
            response = self._call_api(
                "users.lookupByEmail",
                "users_lookupByEmail",
                email=email
            )
            user = response.get("user", {})
            
            if user:
                self.db_manager.save_user(user, self.workspace_id)
                return user
        
        except Exception as e:
            logger.error(f"Failed to lookup user by email {email}: {e}")
            raise
