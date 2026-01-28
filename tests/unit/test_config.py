"""Unit tests for config module."""

import pytest

from proposal_assistant.config import Config, get_config, _get_required_env


# All required env vars for a valid config
REQUIRED_ENV_VARS = {
    "SLACK_BOT_TOKEN": "xoxb-test",
    "SLACK_APP_TOKEN": "xapp-test",
    "SLACK_SIGNING_SECRET": "test-secret",
    "GOOGLE_SERVICE_ACCOUNT_JSON": '{"type": "service_account"}',
    "GOOGLE_DRIVE_ROOT_FOLDER_ID": "folder-123",
    "OLLAMA_BASE_URL": "http://localhost:11434/v1",
    "OLLAMA_MODEL": "qwen2.5:14b",
    "PROPOSAL_TEMPLATE_SLIDE_ID": "slide-123",
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
        with pytest.raises(
            ValueError, match="Missing required environment variable: MISSING_VAR"
        ):
            _get_required_env("MISSING_VAR")

    def test_raises_when_empty(self, monkeypatch):
        monkeypatch.setenv("EMPTY_VAR", "")
        with pytest.raises(
            ValueError, match="Missing required environment variable: EMPTY_VAR"
        ):
            _get_required_env("EMPTY_VAR")


class TestGetConfig:
    """Tests for get_config function."""

    def test_valid_load_with_all_required(self, monkeypatch):
        """Config loads correctly when all required vars are set."""
        for key, value in REQUIRED_ENV_VARS.items():
            monkeypatch.setenv(key, value)

        config = get_config()

        assert config.slack_bot_token == "xoxb-test"
        assert config.slack_app_token == "xapp-test"
        assert config.slack_signing_secret == "test-secret"
        assert config.google_service_account_json == '{"type": "service_account"}'
        assert config.google_drive_root_folder_id == "folder-123"
        assert config.ollama_base_url == "http://localhost:11434/v1"
        assert config.ollama_model == "qwen2.5:14b"
        assert config.proposal_template_slide_id == "slide-123"

    def test_missing_required_raises_value_error(self, monkeypatch):
        """ValueError raised when required var is missing."""
        # Set all but one
        for key, value in REQUIRED_ENV_VARS.items():
            if key != "SLACK_BOT_TOKEN":
                monkeypatch.setenv(key, value)
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)

        with pytest.raises(ValueError, match="SLACK_BOT_TOKEN"):
            get_config()

    def test_defaults_used_when_optional_not_set(self, monkeypatch):
        """Default values used for optional vars when not set."""
        for key, value in REQUIRED_ENV_VARS.items():
            monkeypatch.setenv(key, value)
        # Ensure optional vars are not set
        monkeypatch.delenv("OLLAMA_NUM_CTX", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)
        monkeypatch.delenv("ENVIRONMENT", raising=False)

        config = get_config()

        assert config.ollama_num_ctx == 32768
        assert config.log_level == "INFO"
        assert config.environment == "development"

    def test_optional_vars_override_defaults(self, monkeypatch):
        """Optional vars override defaults when set."""
        for key, value in REQUIRED_ENV_VARS.items():
            monkeypatch.setenv(key, value)
        monkeypatch.setenv("OLLAMA_NUM_CTX", "16384")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")
        monkeypatch.setenv("ENVIRONMENT", "production")

        config = get_config()

        assert config.ollama_num_ctx == 16384
        assert config.log_level == "DEBUG"
        assert config.environment == "production"

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
            ollama_base_url="http://localhost",
            ollama_model="model",
            proposal_template_slide_id="slide",
        )

        with pytest.raises(AttributeError):
            config.slack_bot_token = "new-token"
