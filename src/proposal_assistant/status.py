"""Status tracking for Proposal Assistant."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import ClassVar


@dataclass
class BotStatus:
    """Singleton status tracker for the bot.

    Tracks operational status and request metrics.
    """

    _instance: ClassVar["BotStatus | None"] = None

    start_time: datetime
    last_request_time: datetime | None = None
    total_requests: int = 0

    def __new__(cls, *args, **kwargs) -> "BotStatus":
        """Ensure only one instance exists."""
        if cls._instance is None:
            instance = super().__new__(cls)
            instance.start_time = datetime.now(timezone.utc)
            instance.last_request_time = None
            instance.total_requests = 0
            cls._instance = instance
        return cls._instance

    @classmethod
    def get(cls) -> "BotStatus":
        """Get the singleton instance."""
        if cls._instance is None:
            cls._instance = cls(start_time=datetime.now(timezone.utc))
        return cls._instance

    def record_request(self) -> None:
        """Record a new request."""
        self.last_request_time = datetime.now(timezone.utc)
        self.total_requests += 1

    def uptime_str(self) -> str:
        """Get human-readable uptime string."""
        delta = datetime.now(timezone.utc) - self.start_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, _ = divmod(remainder, 60)

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")

        return " ".join(parts)

    def last_request_str(self) -> str:
        """Get human-readable last request time."""
        if self.last_request_time is None:
            return "No requests yet"

        delta = datetime.now(timezone.utc) - self.last_request_time
        total_seconds = int(delta.total_seconds())

        if total_seconds < 60:
            return f"{total_seconds}s ago"
        elif total_seconds < 3600:
            minutes = total_seconds // 60
            return f"{minutes}m ago"
        elif total_seconds < 86400:
            hours = total_seconds // 3600
            return f"{hours}h ago"
        else:
            days = total_seconds // 86400
            return f"{days}d ago"
