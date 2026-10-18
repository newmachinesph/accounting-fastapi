import os
import uuid
import time
from typing import Dict, Optional
from datetime import datetime, timedelta
import json

class TempDownloadManager:
    def __init__(self, temp_dir: str = "temp_downloads", expiry_hours: int = 1):
        self.temp_dir = temp_dir
        self.expiry_hours = expiry_hours
        self.downloads: Dict[str, dict] = {}
        
        # Create temp directory if it doesn't exist
        os.makedirs(temp_dir, exist_ok=True)
    
    def create_temp_download(self, content: str, filename: str, content_type: str) -> dict:
        """Create a temporary download and return metadata"""
        
        # Generate unique token
        token = str(uuid.uuid4())
        
        # Calculate expiry time
        expires_at = datetime.now() + timedelta(hours=self.expiry_hours)
        
        # Save file to temp directory
        file_path = os.path.join(self.temp_dir, f"{token}_{filename}")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        # Store download metadata
        download_info = {
            "token": token,
            "filename": filename,
            "file_path": file_path,
            "content_type": content_type,
            "created_at": datetime.now().isoformat(),
            "expires_at": expires_at.isoformat(),
            "downloaded": False,
            "download_count": 0
        }
        
        self.downloads[token] = download_info
        
        return {
            "download_url": f"/download/{token}",
            "filename": filename,
            "expires_at": expires_at.isoformat(),
            "expires_in": self.expiry_hours * 3600,  # seconds
            "token": token
        }
    
    def get_download(self, token: str) -> Optional[dict]:
        """Get download info and file content if valid"""
        
        if token not in self.downloads:
            return None
        
        download_info = self.downloads[token]
        
        # Check if expired
        expires_at = datetime.fromisoformat(download_info["expires_at"])
        if datetime.now() > expires_at:
            self.cleanup_download(token)
            return None
        
        # Check if file still exists
        if not os.path.exists(download_info["file_path"]):
            del self.downloads[token]
            return None
        
        # Update download count
        self.downloads[token]["download_count"] += 1
        self.downloads[token]["last_downloaded"] = datetime.now().isoformat()
        
        return download_info
    
    def cleanup_download(self, token: str):
        """Remove a specific download"""
        if token in self.downloads:
            download_info = self.downloads[token]
            
            # Remove file if it exists
            if os.path.exists(download_info["file_path"]):
                os.remove(download_info["file_path"])
            
            # Remove from memory
            del self.downloads[token]
    
    def cleanup_expired(self):
        """Remove all expired downloads"""
        now = datetime.now()
        expired_tokens = []
        
        for token, download_info in self.downloads.items():
            expires_at = datetime.fromisoformat(download_info["expires_at"])
            if now > expires_at:
                expired_tokens.append(token)
        
        for token in expired_tokens:
            self.cleanup_download(token)
        
        return len(expired_tokens)

# Global instance
temp_download_manager = TempDownloadManager()
