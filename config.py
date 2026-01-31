"""
Configuration module for Discord Archiver.

Centralizes all configuration constants and environment variable handling.
"""

import os
from typing import Optional


class Config:
    """Application configuration with environment variable support."""
    
    # Paths
    TEMP_DIR: str = os.getenv("TEMP_DIR", "Temp_Export_UI")
    TEMP_DIR_LOCAL: str = os.getenv("TEMP_DIR_LOCAL", "Temp_Export_Local")
    LOCAL_BACKUP_DIR: str = os.getenv("LOCAL_BACKUP_DIR", "Local_Backup_PDFs")
    
    # Google Drive
    SCOPES: list[str] = ['https://www.googleapis.com/auth/drive']
    
    # Discord
    DISCORD_TOKEN: Optional[str] = os.getenv("DISCORD_BOT_TOKEN")
    
    # Cloud Configuration
    IS_CLOUD: bool = os.getenv("IS_CLOUD", "false").lower() == "true"
    GOOGLE_DRIVE_TOKEN_BASE64: Optional[str] = os.getenv("GOOGLE_DRIVE_TOKEN_BASE64")
    
    # Worker Configuration
    MAX_WORKERS: int = int(os.getenv("MAX_WORKERS", "4"))
    
    # Upload Configuration
    MAX_UPLOAD_RETRIES: int = int(os.getenv("MAX_UPLOAD_RETRIES", "3"))
    
    @classmethod
    def get_discord_token(cls) -> Optional[str]:
        """Get Discord token from environment variable."""
        return cls.DISCORD_TOKEN
    
    @classmethod
    def is_cloud_environment(cls) -> bool:
        """Check if running in cloud environment."""
        return cls.IS_CLOUD


def sanitize_filename(name: str) -> str:
    """
    Sanitize a string for use as a filename.
    
    Args:
        name: The original filename/string to sanitize.
        
    Returns:
        A sanitized string safe for use as a filename.
    """
    return "".join(c for c in name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
