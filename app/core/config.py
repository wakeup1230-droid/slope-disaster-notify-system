"""
Application configuration using pydantic-settings.
Loads from environment variables / .env file.
"""

from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # --- LINE Bot ---
    line_channel_secret: str = Field(default="", description="LINE Channel Secret")
    line_channel_access_token: str = Field(default="", description="LINE Channel Access Token")

    # --- Application ---
    app_env: str = Field(default="development", description="Environment: development, staging, production")
    app_host: str = Field(default="0.0.0.0", description="Server host")
    app_port: int = Field(default=8000, description="Server port")
    app_base_url: str = Field(default="http://localhost:8000", description="Public base URL")

    # --- Storage ---
    storage_root: Path = Field(default=Path("./storage"), description="Root directory for file storage")

    # --- Vendor API ---
    vendor_api_key: str = Field(default="", description="API key for vendor access")

    # --- Bootstrap Admin ---
    bootstrap_admin_line_id: str = Field(default="", description="LINE User ID of bootstrap admin")
    bootstrap_admin_name: str = Field(default="系統管理員", description="Display name for bootstrap admin")

    # --- LRS Service ---
    lrs_csv_path: Path = Field(default=Path("./app/data/lrs_milepost.csv"), description="Path to LRS milepost CSV")
    lrs_max_distance_m: float = Field(default=500.0, description="Max distance (meters) for LRS matching")
    lrs_grid_size_deg: float = Field(default=0.01, description="Grid cell size in degrees for spatial index")

    # --- Image Processing ---
    max_image_size_mb: int = Field(default=10, description="Maximum image file size in MB")
    thumbnail_size: int = Field(default=300, description="Thumbnail dimension in pixels")
    accepted_image_formats: str = Field(
        default="image/jpeg,image/png,image/heic",
        description="Comma-separated accepted MIME types",
    )

    # --- PDF Parser ---
    tesseract_cmd: str = Field(default="tesseract", description="Tesseract executable path")
    tesseract_lang: str = Field(default="chi_tra", description="Tesseract OCR language")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    # --- Derived Properties ---

    @property
    def cases_dir(self) -> Path:
        return self.storage_root / "cases"

    @property
    def users_dir(self) -> Path:
        return self.storage_root / "users"

    @property
    def sessions_dir(self) -> Path:
        return self.storage_root / "sessions"

    @property
    def locks_dir(self) -> Path:
        return self.storage_root / "locks"

    @property
    def accepted_formats_list(self) -> list[str]:
        return [f.strip() for f in self.accepted_image_formats.split(",")]

    def ensure_directories(self) -> None:
        """Create all required storage directories if they don't exist."""
        for d in [self.cases_dir, self.users_dir, self.sessions_dir, self.locks_dir]:
            d.mkdir(parents=True, exist_ok=True)


# Singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create the application settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings
