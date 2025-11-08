"""File sender for uploading files to Slack."""
from typing import Optional, List
from pathlib import Path
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import Config
from utils.logger import get_logger
from utils.rate_limiter import get_rate_limiter
from utils.backoff import sync_retry_with_backoff

logger = get_logger(__name__)


class FileSender:
    """Upload files to Slack."""
    
    def __init__(self, client: Optional[WebClient] = None):
        """Initialize file sender."""
        self.client = client or WebClient(token=Config.SLACK_BOT_TOKEN)
        self.rate_limiter = get_rate_limiter()
    
    def upload_file(
        self,
        channels: str,
        file_path: Optional[str] = None,
        content: Optional[str] = None,
        filename: Optional[str] = None,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None,
        thread_ts: Optional[str] = None
    ):
        """Upload a file using the new upload flow."""
        logger.info(f"Uploading file to {channels}")
        
        try:
            # Step 1: Get upload URL
            if file_path:
                file_size = Path(file_path).stat().st_size
                filename = filename or Path(file_path).name
            elif content:
                file_size = len(content.encode('utf-8'))
                filename = filename or "file.txt"
            else:
                raise ValueError("Either file_path or content must be provided")
            
            self.rate_limiter.wait_if_needed("files.getUploadURLExternal")
            
            response = sync_retry_with_backoff(
                lambda: self.client.files_getUploadURLExternal(
                    filename=filename,
                    length=file_size
                )
            )
            
            if not response.get("ok"):
                raise SlackApiError(response.get("error"), response)
            
            upload_url = response["upload_url"]
            file_id = response["file_id"]
            
            # Step 2: Upload file to URL
            import requests
            
            if file_path:
                with open(file_path, 'rb') as f:
                    file_data = f.read()
            else:
                file_data = content.encode('utf-8')
            
            upload_response = requests.post(upload_url, data=file_data)
            upload_response.raise_for_status()
            
            # Step 3: Complete the upload
            self.rate_limiter.wait_if_needed("files.completeUploadExternal")
            
            files_data = [{
                "id": file_id,
                "title": title or filename
            }]
            
            complete_params = {
                "files": files_data,
                "channel_id": channels
            }
            
            if initial_comment:
                complete_params["initial_comment"] = initial_comment
            if thread_ts:
                complete_params["thread_ts"] = thread_ts
            
            complete_response = sync_retry_with_backoff(
                lambda: self.client.files_completeUploadExternal(**complete_params)
            )
            
            if complete_response.get("ok"):
                logger.info(f"✓ File uploaded successfully: {filename}")
                return complete_response.data
            else:
                raise SlackApiError(complete_response.get("error"), complete_response)
        
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            raise
    
    def upload_file_v2(
        self,
        channel: str,
        file_path: str,
        title: Optional[str] = None,
        initial_comment: Optional[str] = None
    ):
        """Upload file using files_upload_v2 (simplified method)."""
        logger.info(f"Uploading file to {channel}: {file_path}")
        
        self.rate_limiter.wait_if_needed("files.upload")
        
        try:
            with open(file_path, 'rb') as f:
                response = sync_retry_with_backoff(
                    lambda: self.client.files_upload_v2(
                        channel=channel,
                        file=f,
                        title=title or Path(file_path).name,
                        initial_comment=initial_comment
                    )
                )
            
            if response.get("ok"):
                logger.info(f"✓ File uploaded: {file_path}")
                return response.data
            else:
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            raise
    
    def delete_file(self, file_id: str):
        """Delete a file."""
        logger.info(f"Deleting file: {file_id}")
        
        self.rate_limiter.wait_if_needed("files.delete")
        
        try:
            response = sync_retry_with_backoff(
                lambda: self.client.files_delete(file=file_id)
            )
            
            if response.get("ok"):
                logger.info(f"✓ File deleted: {file_id}")
                return response.data
            else:
                raise SlackApiError(response.get("error"), response)
        
        except Exception as e:
            logger.error(f"Error deleting file: {e}")
            raise
