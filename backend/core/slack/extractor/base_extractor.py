"""Base extractor class."""
from typing import Optional, Dict, Any
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import Config
from database.db_manager import DatabaseManager
from utils.logger import get_logger
from utils.rate_limiter import get_rate_limiter
from utils.backoff import sync_retry_with_backoff

logger = get_logger(__name__)


class BaseExtractor:
    """Base class for extractors."""
    
    def __init__(
        self,
        client: Optional[WebClient] = None,
        db_manager: Optional[DatabaseManager] = None
    ):
        """Initialize base extractor."""
        # Use 60-second timeout to prevent indefinite hangs on EC2
        self.client = client or WebClient(token=Config.SLACK_BOT_TOKEN, timeout=60)
        self.db_manager = db_manager or DatabaseManager()
        self.rate_limiter = get_rate_limiter()
        self.workspace_id = None
    
    def _call_api(
        self,
        method_name: str,
        api_method: str,
        **kwargs
    ) -> Dict[str, Any]:
        """Call Slack API with rate limiting and retries."""
        # Apply rate limiting
        wait_time = self.rate_limiter.wait_if_needed(method_name)
        
        if wait_time > 0:
            logger.debug(f"Waited {wait_time:.2f}s for rate limit")
        
        # Make API call with retry
        try:
            response = sync_retry_with_backoff(
                lambda: getattr(self.client, api_method)(**kwargs),
                max_attempts=Config.MAX_RETRIES
            )
            
            if not response.get("ok", False):
                error = response.get("error", "unknown_error")
                logger.error(f"API call failed: {method_name} - {error}")
                raise SlackApiError(error, response)
            
            return response
        
        except SlackApiError as e:
            logger.error(f"Slack API error in {method_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {method_name}: {e}")
            raise
    
    def _paginate(
        self,
        method_name: str,
        api_method: str,
        result_key: str,
        **kwargs
    ):
        """Paginate through API results."""
        cursor = None
        total_items = 0
        
        while True:
            params = {**kwargs}
            if cursor:
                params["cursor"] = cursor
            
            response = self._call_api(method_name, api_method, **params)
            
            items = response.get(result_key, [])
            total_items += len(items)
            
            yield from items
            
            # Check for next cursor
            metadata = response.get("response_metadata", {})
            cursor = metadata.get("next_cursor", "")
            
            if not cursor:
                logger.info(f"Pagination complete for {method_name}. Total items: {total_items}")
                break
            
            logger.debug(f"Fetched {total_items} items so far from {method_name}")
    
    def get_workspace_info(self) -> Dict[str, Any]:
        """Get workspace information."""
        try:
            response = self._call_api("team.info", "team_info")
            team = response.get("team", {})
            self.workspace_id = team.get("id")
            return team
        except Exception as e:
            logger.error(f"Failed to get workspace info: {e}")
            # Fallback: get from auth.test
            response = self._call_api("auth.test", "auth_test")
            self.workspace_id = response.get("team_id")
            return {"id": self.workspace_id, "name": response.get("team")}
