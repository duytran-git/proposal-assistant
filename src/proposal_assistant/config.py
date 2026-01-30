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

    # LLM (Required)
    ollama_base_url: str
    ollama_model: str

    # Templates (Required)
    proposal_template_slide_id: str

    # Optional with defaults
    ollama_num_ctx: int = 32768
    log_level: str = "INFO"
    environment: str = "development"

    # Cloud LLM (Optional - for fallback when Ollama is offline)
    cloud_provider: str | None = None  # "openai" or "anthropic"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-20250514"


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
        # LLM
        ollama_base_url=_get_required_env("OLLAMA_BASE_URL"),
        ollama_model=_get_required_env("OLLAMA_MODEL"),
        # Templates
        proposal_template_slide_id=_get_required_env("PROPOSAL_TEMPLATE_SLIDE_ID"),
        # Optional
        ollama_num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "32768")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        environment=os.getenv("ENVIRONMENT", "development"),
        # Cloud LLM (Optional)
        cloud_provider=os.getenv("CLOUD_PROVIDER"),  # "openai" or "anthropic"
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o"),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
    )
