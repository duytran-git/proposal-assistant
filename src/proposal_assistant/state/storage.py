"""JSON file storage for thread state persistence."""

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from proposal_assistant.state.models import State, ThreadState


class JSONStorage:
    """Persists ThreadState to JSON files in data/threads/ directory."""

    def __init__(self, data_dir: Optional[Path] = None) -> None:
        """Initialize storage with data directory.

        Args:
            data_dir: Base directory for data storage. Defaults to ./data
        """
        self._data_dir = data_dir or Path("data")
        self._threads_dir = self._data_dir / "threads"
        self._threads_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, thread_ts: str, channel_id: str) -> Path:
        """Get file path for a thread state."""
        return self._threads_dir / f"{channel_id}_{thread_ts}.json"

    def _serialize(self, state: ThreadState) -> dict:
        """Convert ThreadState to JSON-serializable dict."""
        data = asdict(state)
        # Convert State enum to string
        data["state"] = state.state.value
        if state.previous_state:
            data["previous_state"] = state.previous_state.value
        # Convert datetime to ISO format
        data["created_at"] = state.created_at.isoformat()
        data["updated_at"] = state.updated_at.isoformat()
        return data

    def _deserialize(self, data: dict) -> ThreadState:
        """Convert dict to ThreadState."""
        # Convert string back to State enum
        data["state"] = State(data["state"])
        if data.get("previous_state"):
            data["previous_state"] = State(data["previous_state"])
        # Convert ISO format back to datetime
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return ThreadState(**data)

    def save(self, state: ThreadState) -> None:
        """Save thread state to JSON file."""
        path = self._get_path(state.thread_ts, state.channel_id)
        data = self._serialize(state)
        path.write_text(json.dumps(data, indent=2))

    def load(self, thread_ts: str, channel_id: str) -> Optional[ThreadState]:
        """Load thread state from JSON file.

        Returns:
            ThreadState if file exists, None otherwise
        """
        path = self._get_path(thread_ts, channel_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return self._deserialize(data)

    def delete(self, thread_ts: str, channel_id: str) -> bool:
        """Delete thread state file.

        Returns:
            True if file was deleted, False if it didn't exist
        """
        path = self._get_path(thread_ts, channel_id)
        if path.exists():
            path.unlink()
            return True
        return False
