"""OAuth handler for Slack app installation."""
from typing import Optional, Dict, Any
from urllib.parse import urlencode
import requests

from config import Config
from .logger import get_logger

logger = get_logger(__name__)


class OAuthHandler:
    """Handle Slack OAuth flow for app installation."""
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        """Initialize OAuth handler."""
        self.client_id = client_id or Config.SLACK_CLIENT_ID
        self.client_secret = client_secret or Config.SLACK_CLIENT_SECRET
        
        if not self.client_id or not self.client_secret:
            logger.warning("Client ID or Client Secret not configured")
    
    def get_authorization_url(
        self,
        redirect_uri: str,
        scopes: list,
        state: Optional[str] = None,
        team: Optional[str] = None
    ) -> str:
        """
        Generate OAuth authorization URL.
        
        Args:
            redirect_uri: Where Slack should redirect after authorization
            scopes: List of permission scopes
            state: Optional state parameter for CSRF protection
            team: Optional team ID to pre-select workspace
        
        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.client_id,
            "scope": ",".join(scopes),
            "redirect_uri": redirect_uri,
        }
        
        if state:
            params["state"] = state
        if team:
            params["team"] = team
        
        url = f"https://slack.com/oauth/v2/authorize?{urlencode(params)}"
        logger.info(f"Generated OAuth URL for scopes: {scopes}")
        return url
    
    def exchange_code_for_token(
        self,
        code: str,
        redirect_uri: str
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from Slack
            redirect_uri: Same redirect URI used in authorization
        
        Returns:
            Token response from Slack
        """
        logger.info("Exchanging authorization code for access token")
        
        response = requests.post(
            "https://slack.com/api/oauth.v2.access",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            }
        )
        
        result = response.json()
        
        if not result.get("ok"):
            error = result.get("error", "unknown_error")
            logger.error(f"OAuth token exchange failed: {error}")
            raise Exception(f"OAuth failed: {error}")
        
        logger.info("✓ Access token obtained successfully")
        
        # Extract tokens
        access_token = result.get("access_token")
        bot_token = result.get("authed_user", {}).get("access_token")
        team_id = result.get("team", {}).get("id")
        
        logger.info(f"Team ID: {team_id}")
        logger.info(f"Bot Token: {bot_token[:20]}..." if bot_token else "No bot token")
        
        return result
    
    def revoke_token(self, token: str) -> bool:
        """
        Revoke an access token.
        
        Args:
            token: Token to revoke
        
        Returns:
            True if successful
        """
        logger.info("Revoking access token")
        
        response = requests.post(
            "https://slack.com/api/auth.revoke",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        result = response.json()
        
        if result.get("ok"):
            logger.info("✓ Token revoked successfully")
            return True
        else:
            logger.error(f"Token revocation failed: {result.get('error')}")
            return False
