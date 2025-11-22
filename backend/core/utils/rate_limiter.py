"""Rate limiting for Slack API calls."""
import asyncio
import time
from collections import defaultdict
from typing import Dict, Optional, Callable, Any
from threading import Lock
from datetime import datetime, timedelta
from functools import wraps

from .logger import get_logger

# Default rate limits if not configured
def get_rate_limit_for_method(method: str) -> tuple:
    """Get rate limit for a method. Returns (calls, period_seconds)."""
    defaults = {
        "default": (100, 60),  # 100 calls per minute
        "slack_api": (50, 60),  # 50 calls per minute for Slack
        "gmail_api": (250, 60),  # 250 calls per minute for Gmail
        "notion_api": (3, 1),  # 3 calls per second for Notion
    }
    return defaults.get(method, defaults["default"])

logger = get_logger(__name__)


class RateLimiter:
    """Rate limiter for Slack API methods."""
    
    def __init__(self):
        """Initialize rate limiter."""
        self._locks: Dict[str, Lock] = defaultdict(Lock)
        self._requests: Dict[str, list] = defaultdict(list)
        self._window_seconds = 60  # 1 minute window
    
    def _clean_old_requests(self, method: str):
        """Remove requests older than the time window."""
        now = time.time()
        cutoff = now - self._window_seconds
        self._requests[method] = [
            req_time for req_time in self._requests[method]
            if req_time > cutoff
        ]
    
    def _get_wait_time(self, method: str, limit: int) -> float:
        """Calculate wait time needed."""
        self._clean_old_requests(method)
        
        if len(self._requests[method]) < limit:
            return 0
        
        # Need to wait until oldest request expires
        oldest = self._requests[method][0]
        wait_time = (oldest + self._window_seconds) - time.time()
        return max(0, wait_time)
    
    def wait_if_needed(self, method: str) -> float:
        """Wait if rate limit would be exceeded. Returns wait time."""
        # get_rate_limit_for_method returns (max_calls, period_seconds)
        max_calls, _ = get_rate_limit_for_method(method)
        
        with self._locks[method]:
            wait_time = self._get_wait_time(method, max_calls)
            
            if wait_time > 0:
                logger.debug(
                    f"Rate limit approaching for {method}. "
                    f"Waiting {wait_time:.2f}s (limit: {max_calls}/min)"
                )
                time.sleep(wait_time)
            
            # Record this request
            self._requests[method].append(time.time())
            return wait_time
    
    async def async_wait_if_needed(self, method: str) -> float:
        """Async version of wait_if_needed."""
        max_calls, _ = get_rate_limit_for_method(method)
        
        # Use asyncio-compatible approach
        wait_time = self._get_wait_time(method, max_calls)
        
        if wait_time > 0:
            logger.debug(
                f"Rate limit approaching for {method}. "
                f"Waiting {wait_time:.2f}s (limit: {max_calls}/min)"
            )
            await asyncio.sleep(wait_time)
        
        # Record this request
        self._requests[method].append(time.time())
        return wait_time
    
    def get_current_usage(self, method: str) -> tuple[int, int]:
        """Get current usage (requests made, limit)."""
        self._clean_old_requests(method)
        max_calls, _ = get_rate_limit_for_method(method)
        return len(self._requests[method]), max_calls
    
    def reset(self, method: Optional[str] = None):
        """Reset rate limiter for method or all methods."""
        if method:
            self._requests[method] = []
        else:
            self._requests.clear()


# Global rate limiter instance
_rate_limiter = RateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Get global rate limiter instance."""
    return _rate_limiter
