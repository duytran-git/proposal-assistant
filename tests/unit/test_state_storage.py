"""Unit tests for state storage module."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from proposal_assistant.state import JSONStorage, State, ThreadState


class TestJSONStorageInit:
    """Tests for JSONStorage initialization."""

    def test_creates_threads_directory(self):
        """Creates data/threads directory on init."""
        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "data"
            storage = JSONStorage(data_dir=data_dir)

            threads_dir = data_dir / "threads"
            assert threads_dir.exists()
            assert threads_dir.is_dir()

    def test_uses_default_data_dir(self):
        """Uses ./data as default directory."""
        storage = JSONStorage()
        assert storage._data_dir == Path("data")

    def test_accepts_custom_data_dir(self):
        """Accepts custom data directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_dir = Path(tmpdir) / "custom"
            storage = JSONStorage(data_dir=custom_dir)
            assert storage._data_dir == custom_dir


class TestJSONStorageSave:
    """Tests for JSONStorage.save method."""

    @pytest.fixture
    def storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield JSONStorage(data_dir=Path(tmpdir))

    def test_saves_state_to_file(self, storage):
        """Saves ThreadState to JSON file."""
        state = ThreadState(thread_ts="123.456", channel_id="C001", user_id="U001")
        storage.save(state)

        path = storage._threads_dir / "C001_123.456.json"
        assert path.exists()

    def test_file_contains_valid_json(self, storage):
        """Saved file contains valid JSON."""
        state = ThreadState(thread_ts="123.456", channel_id="C001", user_id="U001")
        storage.save(state)

        path = storage._threads_dir / "C001_123.456.json"
        data = json.loads(path.read_text())
        assert data["thread_ts"] == "123.456"
        assert data["channel_id"] == "C001"
        assert data["user_id"] == "U001"

    def test_serializes_state_enum(self, storage):
        """State enum serialized as string."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.state = State.WAITING_FOR_APPROVAL
        storage.save(state)

        path = storage._threads_dir / "C001_123.json"
        data = json.loads(path.read_text())
        assert data["state"] == "WAITING_FOR_APPROVAL"

    def test_serializes_previous_state_enum(self, storage):
        """Previous state enum serialized as string."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.state = State.GENERATING_DECK
        state.previous_state = State.WAITING_FOR_APPROVAL
        storage.save(state)

        path = storage._threads_dir / "C001_123.json"
        data = json.loads(path.read_text())
        assert data["previous_state"] == "WAITING_FOR_APPROVAL"

    def test_serializes_datetime_as_iso(self, storage):
        """Datetime fields serialized as ISO format."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        storage.save(state)

        path = storage._threads_dir / "C001_123.json"
        data = json.loads(path.read_text())
        # Should be valid ISO format
        datetime.fromisoformat(data["created_at"])
        datetime.fromisoformat(data["updated_at"])

    def test_saves_all_fields(self, storage):
        """All ThreadState fields are saved."""
        state = ThreadState(
            thread_ts="123",
            channel_id="C001",
            user_id="U001",
            user_email="user@example.com",
            client_name="Acme Corp",
            client_folder_id="folder-123",
            deal_analysis_doc_id="doc-456",
            deal_analysis_version=2,
            error_message="Test error",
            retry_count=3,
        )
        state.input_transcript_file_ids = ["file1", "file2"]
        state.missing_info_items = ["budget", "timeline"]
        storage.save(state)

        path = storage._threads_dir / "C001_123.json"
        data = json.loads(path.read_text())
        assert data["user_email"] == "user@example.com"
        assert data["client_name"] == "Acme Corp"
        assert data["client_folder_id"] == "folder-123"
        assert data["deal_analysis_doc_id"] == "doc-456"
        assert data["deal_analysis_version"] == 2
        assert data["error_message"] == "Test error"
        assert data["retry_count"] == 3
        assert data["input_transcript_file_ids"] == ["file1", "file2"]
        assert data["missing_info_items"] == ["budget", "timeline"]

    def test_overwrites_existing_file(self, storage):
        """Save overwrites existing file."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.client_name = "First"
        storage.save(state)

        state.client_name = "Second"
        storage.save(state)

        path = storage._threads_dir / "C001_123.json"
        data = json.loads(path.read_text())
        assert data["client_name"] == "Second"


class TestJSONStorageLoad:
    """Tests for JSONStorage.load method."""

    @pytest.fixture
    def storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield JSONStorage(data_dir=Path(tmpdir))

    def test_returns_none_for_missing_file(self, storage):
        """Returns None when file doesn't exist."""
        result = storage.load("999.999", "C999")
        assert result is None

    def test_loads_saved_state(self, storage):
        """Loads previously saved ThreadState."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.client_name = "Acme Corp"
        storage.save(state)

        loaded = storage.load("123", "C001")
        assert loaded is not None
        assert loaded.thread_ts == "123"
        assert loaded.channel_id == "C001"
        assert loaded.user_id == "U001"
        assert loaded.client_name == "Acme Corp"

    def test_deserializes_state_enum(self, storage):
        """State enum deserialized correctly."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.state = State.GENERATING_DEAL_ANALYSIS
        storage.save(state)

        loaded = storage.load("123", "C001")
        assert loaded.state == State.GENERATING_DEAL_ANALYSIS
        assert isinstance(loaded.state, State)

    def test_deserializes_previous_state_enum(self, storage):
        """Previous state enum deserialized correctly."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.state = State.WAITING_FOR_APPROVAL
        state.previous_state = State.GENERATING_DEAL_ANALYSIS
        storage.save(state)

        loaded = storage.load("123", "C001")
        assert loaded.previous_state == State.GENERATING_DEAL_ANALYSIS
        assert isinstance(loaded.previous_state, State)

    def test_deserializes_datetime_fields(self, storage):
        """Datetime fields deserialized correctly."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        storage.save(state)

        loaded = storage.load("123", "C001")
        assert isinstance(loaded.created_at, datetime)
        assert isinstance(loaded.updated_at, datetime)

    def test_loads_list_fields(self, storage):
        """List fields loaded correctly."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.input_transcript_file_ids = ["file1", "file2"]
        state.input_urls = ["https://example.com"]
        storage.save(state)

        loaded = storage.load("123", "C001")
        assert loaded.input_transcript_file_ids == ["file1", "file2"]
        assert loaded.input_urls == ["https://example.com"]

    def test_handles_none_previous_state(self, storage):
        """Handles None previous_state correctly."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        state.previous_state = None
        storage.save(state)

        loaded = storage.load("123", "C001")
        assert loaded.previous_state is None


class TestJSONStorageDelete:
    """Tests for JSONStorage.delete method."""

    @pytest.fixture
    def storage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield JSONStorage(data_dir=Path(tmpdir))

    def test_deletes_existing_file(self, storage):
        """Deletes existing state file."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        storage.save(state)

        path = storage._threads_dir / "C001_123.json"
        assert path.exists()

        result = storage.delete("123", "C001")
        assert result is True
        assert not path.exists()

    def test_returns_false_for_missing_file(self, storage):
        """Returns False when file doesn't exist."""
        result = storage.delete("999", "C999")
        assert result is False

    def test_delete_then_load_returns_none(self, storage):
        """Load returns None after delete."""
        state = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        storage.save(state)
        storage.delete("123", "C001")

        loaded = storage.load("123", "C001")
        assert loaded is None


class TestJSONStorageFilePath:
    """Tests for file path generation."""

    def test_path_format(self):
        """File path follows {channel}_{thread}.json format."""
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = JSONStorage(data_dir=Path(tmpdir))
            path = storage._get_path("123.456789", "C0123ABC")

            assert path.name == "C0123ABC_123.456789.json"
            assert path.parent == storage._threads_dir
