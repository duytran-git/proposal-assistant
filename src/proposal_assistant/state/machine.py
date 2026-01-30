"""State machine for managing thread conversation flow."""

from datetime import datetime
from typing import Any, Optional, Protocol

from proposal_assistant.state.models import Event, State, ThreadState


# Valid state transitions: (current_state, event) -> next_state
TRANSITIONS: dict[tuple[State, Event], State] = {
    (State.IDLE, Event.ANALYSE_REQUESTED): State.GENERATING_DEAL_ANALYSIS,
    (State.IDLE, Event.INPUTS_MISSING): State.WAITING_FOR_INPUTS,
    (State.GENERATING_DEAL_ANALYSIS, Event.DEAL_ANALYSIS_CREATED): State.WAITING_FOR_APPROVAL,
    (State.GENERATING_DEAL_ANALYSIS, Event.FAILED): State.ERROR,
    (State.WAITING_FOR_APPROVAL, Event.APPROVED): State.GENERATING_DECK,
    (State.WAITING_FOR_APPROVAL, Event.REJECTED): State.DONE,
    (State.WAITING_FOR_APPROVAL, Event.UPDATED_DEAL_ANALYSIS_PROVIDED): State.GENERATING_DECK,
    (State.WAITING_FOR_APPROVAL, Event.REGENERATE_REQUESTED): State.GENERATING_DEAL_ANALYSIS,
    (State.GENERATING_DECK, Event.DECK_CREATED): State.DONE,
    (State.GENERATING_DECK, Event.FAILED): State.ERROR,
    (State.ERROR, Event.ANALYSE_REQUESTED): State.GENERATING_DEAL_ANALYSIS,
    (State.ERROR, Event.CLOUD_CONSENT_GIVEN): State.GENERATING_DEAL_ANALYSIS,
    (State.ERROR, Event.REJECTED): State.DONE,  # User declines cloud consent
}


class StateStorage(Protocol):
    """Protocol for state persistence backends."""

    def load(self, thread_ts: str, channel_id: str) -> Optional[ThreadState]:
        """Load thread state from storage."""
        ...

    def save(self, state: ThreadState) -> None:
        """Save thread state to storage."""
        ...


class InvalidTransitionError(Exception):
    """Raised when an invalid state transition is attempted."""

    def __init__(self, current_state: State, event: Event) -> None:
        self.current_state = current_state
        self.event = event
        super().__init__(
            f"Invalid transition: cannot apply {event.value} in state {current_state.value}"
        )


class StateMachine:
    """Manages state transitions for Slack thread conversations."""

    def __init__(self, storage: Optional[StateStorage] = None) -> None:
        self._storage = storage
        self._cache: dict[str, ThreadState] = {}

    def _make_key(self, thread_ts: str, channel_id: str) -> str:
        """Create unique key for thread state lookup."""
        return f"{channel_id}_{thread_ts}"

    def get_state(self, thread_ts: str, channel_id: str, user_id: str = "") -> ThreadState:
        """Get existing thread state or create new one."""
        key = self._make_key(thread_ts, channel_id)

        # Check cache first
        if key in self._cache:
            return self._cache[key]

        # Try loading from storage
        if self._storage:
            state = self._storage.load(thread_ts, channel_id)
            if state:
                self._cache[key] = state
                return state

        # Create new state
        state = ThreadState(
            thread_ts=thread_ts,
            channel_id=channel_id,
            user_id=user_id,
        )
        self._cache[key] = state
        if self._storage:
            self._storage.save(state)
        return state

    def can_transition(self, current_state: State, event: Event) -> bool:
        """Check if a transition is valid for the given state and event."""
        return (current_state, event) in TRANSITIONS

    def transition(
        self, thread_ts: str, channel_id: str, event: Event, **kwargs: Any
    ) -> ThreadState:
        """Execute a state transition and update thread state.

        Args:
            thread_ts: Slack thread timestamp
            channel_id: Slack channel ID
            event: Event triggering the transition
            **kwargs: Additional fields to update on ThreadState

        Returns:
            Updated ThreadState

        Raises:
            InvalidTransitionError: If transition is not valid
        """
        state = self.get_state(thread_ts, channel_id)

        if not self.can_transition(state.state, event):
            raise InvalidTransitionError(state.state, event)

        # Perform transition
        new_state = TRANSITIONS[(state.state, event)]
        state.previous_state = state.state
        state.state = new_state
        state.updated_at = datetime.utcnow()

        # Apply additional updates
        for key, value in kwargs.items():
            if hasattr(state, key):
                setattr(state, key, value)

        # Persist
        if self._storage:
            self._storage.save(state)

        return state
