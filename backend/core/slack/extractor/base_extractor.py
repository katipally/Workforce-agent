"""Base extractor class."""
from typing import Optional, Dict, Any, Callable
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

    def _paginate_with_progress(
        self,
        method_name: str,
        api_method: str,
        result_key: str,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
        seconds_per_request: float = 60.0,
        **kwargs
    ):
        """Paginate through API results with progress tracking and ETA calculation.
        
        Args:
            method_name: Slack API method name for rate limiting
            api_method: SDK method name to call
            result_key: Key in response containing items
            progress_callback: Callback for progress updates
            cancel_check: Callback to check if cancelled
            seconds_per_request: Estimated seconds per API request (based on rate limit)
            **kwargs: Additional params for API call
        """
        cursor = None
        total_items = 0
        pages_fetched = 0
        has_more = True
        
        # Send initial progress immediately so UI shows something
        if progress_callback:
            progress_callback({
                "stage": "fetching",
                "stage_description": f"Starting to fetch messages from Slack...",
                "pages_fetched": 0,
                "messages_fetched": 0,
                "progress": 0.02,
                "eta_seconds": int(seconds_per_request),
                "rate_limit_info": f"Slack rate limit: ~{seconds_per_request:.0f}s between API calls",
            })
        
        while has_more:
            # Check for cancellation
            if cancel_check and cancel_check():
                logger.info(f"Pagination cancelled for {method_name}")
                return
            
            params = {**kwargs}
            if cursor:
                params["cursor"] = cursor
            
            # Report progress before fetch (with ETA based on unknown remaining pages)
            if progress_callback and pages_fetched > 0:
                # Estimate: assume we're about 40% through fetching phase (max)
                # Progress: 0-40% for fetching, 40-95% for saving, 95-100% for completion
                fetch_progress = min(0.4, 0.05 + (pages_fetched * 0.05))
                progress_callback({
                    "stage": "fetching",
                    "stage_description": f"Fetching messages from Slack (page {pages_fetched + 1})",
                    "pages_fetched": pages_fetched,
                    "messages_fetched": total_items,
                    "progress": fetch_progress,
                    "eta_seconds": int(seconds_per_request),  # Time until next page
                    "rate_limit_info": f"{seconds_per_request:.0f}s between API calls due to Slack rate limits",
                })
            
            # Make API call
            response = self._call_api(method_name, api_method, **params)
            pages_fetched += 1
            
            items = response.get(result_key, [])
            total_items += len(items)
            
            # Check for next cursor
            metadata = response.get("response_metadata", {})
            cursor = metadata.get("next_cursor", "")
            has_more = bool(cursor)
            
            # Log progress at INFO level
            if has_more:
                logger.info(
                    f"Page {pages_fetched}: fetched {len(items)} items "
                    f"(total: {total_items}). More pages available..."
                )
            else:
                logger.info(
                    f"Page {pages_fetched}: fetched {len(items)} items "
                    f"(total: {total_items}). Pagination complete."
                )
            
            # Report updated progress
            if progress_callback:
                if has_more:
                    # Still more pages, estimate remaining time
                    # We don't know how many pages total, but we can show progress
                    fetch_progress = min(0.4, 0.05 + (pages_fetched * 0.05))
                    progress_callback({
                        "stage": "fetching",
                        "stage_description": f"Fetched page {pages_fetched} ({total_items} messages). Waiting for rate limit...",
                        "pages_fetched": pages_fetched,
                        "messages_fetched": total_items,
                        "progress": fetch_progress,
                        "eta_seconds": int(seconds_per_request),
                        "rate_limit_info": f"~{seconds_per_request:.0f}s wait between pages (Slack rate limit)",
                    })
                else:
                    # Done fetching
                    progress_callback({
                        "stage": "fetched",
                        "stage_description": f"Fetched all {total_items} messages in {pages_fetched} pages",
                        "pages_fetched": pages_fetched,
                        "messages_fetched": total_items,
                        "total_messages": total_items,
                        "progress": 0.4,
                        "eta_seconds": 5,  # Saving is fast
                    })
            
            yield from items
    
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
