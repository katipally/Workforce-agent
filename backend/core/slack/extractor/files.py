"""File extractor."""
import os
from typing import Optional, List
from pathlib import Path
import requests
from tqdm import tqdm
from slack_sdk.errors import SlackApiError

from .base_extractor import BaseExtractor
from utils.logger import get_logger
from config import Config

logger = get_logger(__name__)


class FileExtractor(BaseExtractor):
    """Extract file information and downloads."""
    
    def __init__(self, *args, **kwargs):
        """Initialize file extractor."""
        super().__init__(*args, **kwargs)
        self.files_dir = Config.FILES_DIR
        self.files_dir.mkdir(parents=True, exist_ok=True)
    
    def extract_all_files(
        self,
        user: Optional[str] = None,
        channel: Optional[str] = None,
        types: Optional[str] = None,
        download: bool = False
    ) -> int:
        """Extract all files from workspace."""
        logger.info("Starting file extraction")
        
        count = 0
        files_list = []
        
        params = {
            "limit": Config.DEFAULT_PAGE_SIZE
        }
        
        if user:
            params["user"] = user
        if channel:
            params["channel"] = channel
        if types:
            params["types"] = types
        
        # Paginate through files. The Slack API's files.list endpoint can return
        # workspace-scoped infrastructure errors like "solr_failed" which are
        # outside the caller's control. We treat those as non-fatal for the
        # overall pipeline: log them and proceed with whatever data we have
        # instead of crashing the entire Slack extraction run.
        try:
            for file in self._paginate(
                "files.list",
                "files_list",
                "files",
                **params
            ):
                files_list.append(file)
        except SlackApiError as e:
            logger.error(f"Slack API error while listing files: {e}")
        except Exception as e:  # pragma: no cover - defensive logging
            logger.error(f"Unexpected error while listing files: {e}")

        if not files_list:
            logger.warning("No files fetched from Slack; skipping file persistence step.")
            return 0

        logger.info(f"Fetched {len(files_list)} files. Saving to database...")
        
        # Save files with progress bar
        with tqdm(total=len(files_list), desc="Processing files") as pbar:
            for file in files_list:
                try:
                    self.db_manager.save_file(file)
                    count += 1
                    
                    # Download if requested
                    if download:
                        self.download_file(file)
                    
                    pbar.update(1)
                
                except Exception as e:
                    logger.error(f"Failed to save file {file.get('id')}: {e}")
        
        logger.info(f"File extraction complete. Processed {count} files")
        return count
    
    def download_file(self, file_data: dict) -> Optional[str]:
        """Download a file."""
        file_id = file_data.get("id")
        file_name = file_data.get("name", file_id)
        url_private = file_data.get("url_private")
        
        if not url_private:
            logger.warning(f"No download URL for file {file_id}")
            return None
        
        # Create safe filename
        safe_name = "".join(c for c in file_name if c.isalnum() or c in "._- ")
        file_path = self.files_dir / f"{file_id}_{safe_name}"
        
        # Skip if already downloaded
        if file_path.exists():
            logger.debug(f"File already downloaded: {file_path}")
            return str(file_path)
        
        try:
            logger.info(f"Downloading file: {file_name}")
            
            headers = {"Authorization": f"Bearer {Config.SLACK_BOT_TOKEN}"}
            response = requests.get(url_private, headers=headers, stream=True)
            response.raise_for_status()
            
            # Write file
            with open(file_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"File downloaded: {file_path}")
            return str(file_path)
        
        except Exception as e:
            logger.error(f"Failed to download file {file_id}: {e}")
            return None
    
    def download_all_files(self, file_ids: Optional[List[str]] = None) -> int:
        """Download all files."""
        logger.info("Starting bulk file download")
        
        # Get file list from database
        # For simplicity, we'll query files that haven't been downloaded
        # This would need proper implementation with database query
        
        count = 0
        # Implementation would query DB and download files
        
        logger.info(f"Downloaded {count} files")
        return count
    
    def get_file_info(self, file_id: str):
        """Get file information."""
        logger.info(f"Getting file info: {file_id}")
        
        try:
            response = self._call_api(
                "files.info",
                "files_info",
                file=file_id
            )
            
            file = response.get("file", {})
            if file:
                self.db_manager.save_file(file)
                return file
        
        except Exception as e:
            logger.error(f"Failed to get file info {file_id}: {e}")
            raise
