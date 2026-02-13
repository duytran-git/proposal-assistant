"""Unit tests for config module."""

from unittest.mock import patch

import pytest

from proposal_assistant.config import Config, get_config, _get_required_env

# All required env vars for a valid config
REQUIRED_ENV_VARS = {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "SLACK_APP_TOKEN": "xapp-test",
    "SLACK_SIGNING_SECRET": "test-secret",
    "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}',
    "GOOGLE_DRIVE_ROOT_FOLDER_ID": "folder-123",
    "ANTHROPIC_API_KEY": "sk-ant-test-key",
}


@pytest.fixture(autouse=True)
def clear_config_cache():
    """Clear lru_cache before each test."""
    get_config.cache_clear()
    yield
    get_config.cache_clear()


class TestGetRequiredEnv:
    """Tests for _get_required_env helper."""

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "test-value")
        assert _get_required_env("TEST_VAR") == "test-value"

    def test_raises_when_missing(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ValueError, match="Missing required environment variable: MISSING_VAR"):
            _get_required_env("MISSING_VAR")

    def test_raises_when_empty(self, monkeypatch):
        monkeypatch.setenv("EMPTY_VAR", "")
        with pytest.raises(ValueError, match="Missing required environment variable: EMPTY_VAR"):
            _get_required_env("EMPTY_VAR")


class TestGetConfig:
    """Tests for get_config function."""

    def test_valid_load_with_all_required(self, monkeypatch):
        """Config loads correctly when all required vars are set."""
        for key, value in REQUIRED_ENV_VARS.items():
            monkeypatch.setenv(key, value)
        # Ensure optional template vars use defaults
        monkeypatch.delenv("PROPOSAL_TEMPLATE_SLIDE_ID", raising=False)
        monkeypatch.delenv("PROPOSAL_TEMPLATE_PATH", raising=False)

        with patch("proposal_assistant.config.load_dotenv"):
            config = get_config()

        assert config.slack_bot_token == "xoxb-test"
        assert config.slack_app_token == "xapp-test"
        assert config.slack_signing_secret == "test-secret"
        assert config.google_service_account_json == '{"type": "service_account"}'
        assert config.google_drive_root_folder_id == "folder-123"
        assert config.anthropic_api_key == "sk-ant-test-key"
        assert config.proposal_template_slide_id == ""
        assert config.proposal_template_path == "template/Renessai basic template 10_2025.pptx"

    def test_missing_required_raises_value_error(self, monkeypatch):
        """ValueError raised when required var is missing."""
        # Set all but one
        for key, value in REQUIRED_ENV_VARS.items():
            if key != "SLACK_BOT_TOKEN":
                monkeypatch.setenv(key, value)
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

        with patch("proposal_assistant.config.load_dotenv"):
            with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
                get_config()

    def test_defaults_used_when_optional_not_set(self, monkeypatch):
        """Default values used for optional vars when not set."""
        for key, value in REQUIRED_ENV_VARS.items():
            monkeypatch.setenv(key, value)
        # Ensure optional vars are not set
        for var in [
            "ANTHROPIC_MODEL",
            "ANTHROPIC_MAX_TOKENS",
            "ANTHROPIC_TEMPERATURE",
            "ANTHROPIC_MAX_RETRIES",
            "ANTHROPIC_RETRY_BACKOFF",
            "ANTHROPIC_CHUNK_THRESHOLD",
            "ANTHROPIC_CHUNK_SIZE",
            "LOG_LEVEL",
            "ENVIRONMENT",
            "BOT_ENABLED",
            "SLACK_ALERT_CHANNEL",
            "PROPOSAL_TEMPLATE_SLIDE_ID",
            "PROPOSAL_TEMPLATE_PATH",
        ]:
            monkeypatch.delenv(var, raising=False)

        with patch("proposal_assistant.config.load_dotenv"):
            config = get_config()

        assert config.anthropic_model == "claude-sonnet-4-5-20250929"
        assert config.anthropic_max_tokens == 8192
        assert config.anthropic_temperature == 0.3
        assert config.anthropic_max_retries == 3
        assert config.anthropic_retry_backoff == "1,2,4"
        assert config.anthropic_chunk_threshold == 32000
        assert config.anthropic_chunk_size == 8000
        assert config.log_level == "INFO"
        assert config.environment == "development"
        assert config.bot_enabled is True
        assert config.slack_alert_channel == ""
        assert config.proposal_template_slide_id == ""
        assert config.proposal_template_path == "template/Renessai basic template 10_2025.pptx"

    def test_optional_vars_override_defaults(self, monkeypatch):
        """Optional vars override defaults when set."""
        for key, value in REQUIRED_ENV_VARS.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
        monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "8192")
        monkeypatch.setenv("ANTHROPIC_TEMPERATURE", "0.7")
        monkeypatch.setenv("ANTHROPIC_MAX_RETRIES", "5")
        monkeypatch.setenv("ANTHROPIC_RETRY_BACKOFF", "2,4,8,16")
        monkeypatch.setenv("ANTHROPIC_CHUNK_THRESHOLD", "64000")
        monkeypatch.setenv("ANTHROPIC_CHUNK_SIZE", "16000")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("BOT_ENABLED", "false")
        monkeypatch.setenv("SLACK_ALERT_CHANNEL", "#alerts")
        monkeypatch.setenv("PROPOSAL_TEMPLATE_SLIDE_ID", "slide-override")
        monkeypatch.setenv("PROPOSAL_TEMPLATE_PATH", "/custom/template.pptx")

        config = get_config()

        assert config.anthropic_model == "claude-haiku-4-5-20251001"
        assert config.anthropic_max_tokens == 8192
        assert config.anthropic_temperature == 0.7
        assert config.anthropic_max_retries == 5
        assert config.anthropic_retry_backoff == "2,4,8,16"
        assert config.anthropic_chunk_threshold == 64000
        assert config.anthropic_chunk_size == 16000
        assert config.log_level == "DEBUG"
        assert config.environment == "production"
        assert config.bot_enabled is False
        assert config.slack_alert_channel == "#alerts"
        assert config.proposal_template_slide_id == "slide-override"
        assert config.proposal_template_path == "/custom/template.pptx"

    def test_singleton_returns_same_instance(self, monkeypatch):
        """get_config returns cached instance."""
        for key, value in REQUIRED_ENV_VARS.items():
            monkeypatch.setenv(key, value)

        config1 = get_config()
        config2 = get_config()

        assert config1 is config2


class TestConfigDataclass:
    """Tests for Config dataclass."""

    def test_config_is_frozen(self):
        """Config instance is immutable."""
        config = Config(
            slack_bot_token="token",
            slack_app_token="app-token",
            slack_signing_secret="secret",
            google_service_account_json="{}",
            google_drive_root_folder_id="folder",
            anthropic_api_key="sk-ant-test",
        )

        with pytest.raises(AttributeError):
            config.slack_bot_token = "new-token"
