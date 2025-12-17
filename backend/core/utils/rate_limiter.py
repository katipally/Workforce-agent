"""Rate limiting for Slack API calls."""
import asyncio
import json
import os
import time
from collections import defaultdict
from typing import Dict, Optional, Callable, Any
from threading import Lock
from datetime import datetime, timedelta
from functools import wraps

try:
    import fcntl  # type: ignore
except Exception:  # pragma: no cover
    fcntl = None

from .logger import get_logger

# Slack API rate limit tiers (requests per minute)
# For non-Marketplace apps, conversations.history and conversations.replies are severely limited
# See: https://api.slack.com/apis/rate-limits
_SLACK_SPECIAL_RATE_LIMIT = int(os.getenv("SPECIAL_RATE_LIMIT", "1"))  # 1 req/min for non-Marketplace

_SLACK_FILE_RATE_LIMIT_ENABLED = os.getenv("SLACK_FILE_RATE_LIMIT_ENABLED", "true").lower() in (
    "1",
    "true",
    "yes",
)
_SLACK_FILE_RATE_LIMIT_PATH = os.getenv(
    "SLACK_FILE_RATE_LIMIT_PATH",
    "/tmp/workforce_slack_rate_limit.json",
)
_SLACK_FILE_RATE_LIMIT_METHODS = {"conversations.history", "conversations.replies"}

_SLACK_RATE_LIMITS = {
    # Tier 1 - Most restricted (1 req/min for non-Marketplace)
    "conversations.history": _SLACK_SPECIAL_RATE_LIMIT,
    "conversations.replies": _SLACK_SPECIAL_RATE_LIMIT,
    # Tier 2 - Moderate (20 req/min)
    "conversations.list": 20,
    "files.list": 20,
    "reactions.list": 20,
    "users.list": 20,
    # Tier 3 - Good (50 req/min)
    "chat.postMessage": 50,
    "chat.update": 50,
    "chat.delete": 50,
    "conversations.info": 50,
    "conversations.members": 50,
    "files.info": 50,
    "reactions.add": 50,
    "reactions.remove": 50,
    "users.conversations": 50,
    # Tier 4 - Highest (100 req/min)
    "api.test": 100,
    "auth.test": 100,
    "users.info": 100,
    "team.info": 100,
    "emoji.list": 100,
    "bots.info": 100,
}

def get_rate_limit_for_method(method: str) -> tuple:
    """Get rate limit for a method. Returns (calls, period_seconds)."""
    # Check Slack-specific limits first
    if method in _SLACK_RATE_LIMITS:
        return (_SLACK_RATE_LIMITS[method], 60)
    
    # Generic defaults for non-Slack APIs
    defaults = {
        "default": (100, 60),  # 100 calls per minute
        "slack_api": (50, 60),  # 50 calls per minute for Slack (generic)
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

    def _wait_if_needed_file(self, method: str, max_calls: int, period_seconds: int) -> float:
        if fcntl is None:
            return 0

        dir_path = os.path.dirname(_SLACK_FILE_RATE_LIMIT_PATH)
        if dir_path:
            os.makedirs(dir_path, exist_ok=True)
        with open(_SLACK_FILE_RATE_LIMIT_PATH, "a+") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_EX)
            try:
                f.seek(0)
                raw = f.read() or "{}"
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {}

                now = time.time()
                last = float(data.get(method, 0) or 0)
                interval = float(period_seconds) / max(1, int(max_calls))
                wait_time = max(0.0, (last + interval) - now)

                if wait_time > 0:
                    if wait_time > 5:
                        logger.info(
                            f"Rate limit for {method}: waiting {wait_time:.0f}s "
                            f"(global lock; limit: {max_calls}/{period_seconds}s)."
                        )
                    time.sleep(wait_time)

                data[method] = time.time()
                f.seek(0)
                f.truncate()
                f.write(json.dumps(data))
                f.flush()
                os.fsync(f.fileno())

                return float(wait_time)
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    
    def wait_if_needed(self, method: str) -> float:
        """Wait if rate limit would be exceeded. Returns wait time."""
        # get_rate_limit_for_method returns (max_calls, period_seconds)
        max_calls, _ = get_rate_limit_for_method(method)

        if (
            _SLACK_FILE_RATE_LIMIT_ENABLED
            and method in _SLACK_FILE_RATE_LIMIT_METHODS
            and max_calls <= 2
        ):
            return self._wait_if_needed_file(method, max_calls, self._window_seconds)

        with self._locks[method]:
            wait_time = self._get_wait_time(method, max_calls)
            
            if wait_time > 0:
                # Use INFO level for long waits so user can see progress
                if wait_time > 5:
                    logger.info(
                        f"Rate limit for {method}: waiting {wait_time:.0f}s "
                        f"(limit: {max_calls}/min). This is normal for Slack's strict rate limits."
                    )
                else:
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
