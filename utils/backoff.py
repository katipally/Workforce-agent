"""Exponential backoff utilities."""
import asyncio
import time
import random
import logging
from typing import Callable, Optional, Any
from functools import wraps

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
from slack_sdk.errors import SlackApiError

from .logger import get_logger

logger = get_logger(__name__)


def exponential_backoff(
    max_attempts: int = 5,
    min_wait: float = 1,
    max_wait: float = 60,
    exceptions: tuple = (SlackApiError, ConnectionError, TimeoutError)
):
    """Decorator for exponential backoff retry."""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARN),
        reraise=True
    )


def should_retry_error(error: Exception) -> bool:
    """Check if error should be retried."""
    if isinstance(error, SlackApiError):
        # Retry on rate limit errors
        if error.response.status_code == 429:
            return True
        
        # Retry on server errors
        if error.response.status_code >= 500:
            return True
        
        # Check error codes
        error_code = error.response.get("error", "")
        retry_errors = ["timeout", "service_unavailable", "internal_error"]
        if error_code in retry_errors:
            return True
    
    return isinstance(error, (ConnectionError, TimeoutError))


def get_retry_after(error: Exception) -> Optional[float]:
    """Get Retry-After value from error."""
    if isinstance(error, SlackApiError):
        # Check for Retry-After header
        retry_after = error.response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    
    return None


async def async_retry_with_backoff(
    func: Callable,
    max_attempts: int = 5,
    base_delay: float = 1,
    max_delay: float = 60,
    *args,
    **kwargs
) -> Any:
    """Async retry with exponential backoff."""
    attempt = 0
    last_error = None
    
    while attempt < max_attempts:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_error = e
            attempt += 1
            
            if attempt >= max_attempts:
                logger.error(f"Max retry attempts ({max_attempts}) reached")
                raise
            
            if not should_retry_error(e):
                logger.error(f"Non-retryable error: {e}")
                raise
            
            # Check for Retry-After
            retry_after = get_retry_after(e)
            if retry_after:
                delay = retry_after
                logger.warning(f"Rate limited. Retry-After: {delay}s")
            else:
                # Exponential backoff with jitter
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                jitter = random.uniform(0, delay * 0.1)
                delay += jitter
                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed. "
                    f"Retrying in {delay:.2f}s. Error: {e}"
                )
            
            await asyncio.sleep(delay)
    
    raise last_error


def sync_retry_with_backoff(
    func: Callable,
    max_attempts: int = 5,
    base_delay: float = 1,
    max_delay: float = 60,
    *args,
    **kwargs
) -> Any:
    """Sync retry with exponential backoff."""
    attempt = 0
    last_error = None
    
    while attempt < max_attempts:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            attempt += 1
            
            if attempt >= max_attempts:
                logger.error(f"Max retry attempts ({max_attempts}) reached")
                raise
            
            if not should_retry_error(e):
                logger.error(f"Non-retryable error: {e}")
                raise
            
            # Check for Retry-After
            retry_after = get_retry_after(e)
            if retry_after:
                delay = retry_after
                logger.warning(f"Rate limited. Retry-After: {delay}s")
            else:
                # Exponential backoff with jitter
                delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
                jitter = random.uniform(0, delay * 0.1)
                delay += jitter
                logger.warning(
                    f"Attempt {attempt}/{max_attempts} failed. "
                    f"Retrying in {delay:.2f}s. Error: {e}"
                )
            
            time.sleep(delay)
    
    raise last_error
