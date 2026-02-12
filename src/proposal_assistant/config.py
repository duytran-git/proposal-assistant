"""Configuration management for Proposal Assistant."""

from dataclasses import dataclass
from functools import lru_cache
import os

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    """Application configuration loaded from environment variables."""

    # Slack (Required)
    slack_bot_token: str
    slack_app_token: str
    slack_signing_secret: str

    # Google (Required)
    google_service_account_json: str
    google_drive_root_folder_id: str

    # LLM — Anthropic (Required)
    anthropic_api_key: str

    # Templates
    proposal_template_slide_id: str = ""
    proposal_template_path: str = "template/Renessai basic template 10_2025.pptx"

    # Optional with defaults
    anthropic_model: str = "claude-sonnet-4-5-20250929"
    log_level: str = "INFO"
    environment: str = "development"


def _get_required_env(key: str) -> str:
    """Get required environment variable or raise error."""
    value = os.getenv(key)
    if not value:
        raise ValueError(f"Missing required environment variable: {key}")
    return value


@lru_cache(maxsize=1)
def get_config() -> Config:
    """Get singleton Config instance. Loads .env file if present."""
    load_dotenv()

    return Config(
        # Slack
        slack_bot_token=_get_required_env("SLACK_BOT_TOKEN"),
        slack_app_token=_get_required_env("SLACK_APP_TOKEN"),
        slack_signing_secret=_get_required_env("SLACK_SIGNING_SECRET"),
        # Google
        google_service_account_json=_get_required_env("GOOGLE_SERVICE_ACCOUNT_JSON"),
        google_drive_root_folder_id=_get_required_env("GOOGLE_DRIVE_ROOT_FOLDER_ID"),
        # LLM — Anthropic
        anthropic_api_key=_get_required_env("ANTHROPIC_API_KEY"),
        # Templates
        proposal_template_slide_id=os.getenv("PROPOSAL_TEMPLATE_SLIDE_ID", ""),
        proposal_template_path=os.getenv(
            "PROPOSAL_TEMPLATE_PATH", "template/Renessai basic template 10_2025.pptx"
        ),
        # Optional
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        environment=os.getenv("ENVIRONMENT", "development"),
    )
