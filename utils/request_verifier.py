"""Request verification for Slack webhooks."""
import hashlib
import hmac
import time
from typing import Optional

from config import Config
from .logger import get_logger

logger = get_logger(__name__)


class RequestVerifier:
    """Verify requests from Slack using signing secret."""
    
    def __init__(self, signing_secret: Optional[str] = None):
        """Initialize request verifier."""
        self.signing_secret = signing_secret or Config.SLACK_SIGNING_SECRET
        
        if not self.signing_secret:
            logger.warning("No signing secret configured - request verification disabled")
    
    def verify_request(
        self,
        timestamp: str,
        signature: str,
        body: str
    ) -> bool:
        """
        Verify that a request came from Slack.
        
        Args:
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header
            body: Raw request body
        
        Returns:
            True if request is valid, False otherwise
        """
        if not self.signing_secret:
            logger.warning("Cannot verify request - no signing secret configured")
            return False
        
        # Check timestamp is within 5 minutes
        current_time = int(time.time())
        request_time = int(timestamp)
        
        if abs(current_time - request_time) > 60 * 5:
            logger.warning("Request timestamp is too old or too new")
            return False
        
        # Compute signature
        sig_basestring = f"v0:{timestamp}:{body}"
        computed_signature = "v0=" + hmac.new(
            self.signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Compare signatures
        is_valid = hmac.compare_digest(computed_signature, signature)
        
        if not is_valid:
            logger.warning("Request signature verification failed")
        
        return is_valid
    
    def verify_verification_token(self, token: str) -> bool:
        """
        Verify using legacy verification token (deprecated).
        
        Args:
            token: Token from request
        
        Returns:
            True if token matches, False otherwise
        """
        if not Config.SLACK_VERIFICATION_TOKEN:
            logger.warning("No verification token configured")
            return False
        
        is_valid = token == Config.SLACK_VERIFICATION_TOKEN
        
        if not is_valid:
            logger.warning("Verification token mismatch")
        
        return is_valid


# Global verifier instance
_verifier = None


def get_request_verifier() -> RequestVerifier:
    """Get global request verifier instance."""
    global _verifier
    if _verifier is None:
        _verifier = RequestVerifier()
    return _verifier
