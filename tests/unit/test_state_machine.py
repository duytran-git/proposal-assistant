"""Unit tests for state machine module."""

import pytest

from proposal_assistant.state import (
    Event,
    InvalidTransitionError,
    State,
    StateMachine,
    TRANSITIONS,
)


class TestTransitionsDict:
    """Tests for TRANSITIONS configuration."""

    def test_all_transitions_defined(self):
        """All expected transitions are in TRANSITIONS dict."""
        expected = [
            (State.IDLE, Event.ANALYSE_REQUESTED, State.GENERATING_DEAL_ANALYSIS),
            (State.IDLE, Event.INPUTS_MISSING, State.WAITING_FOR_INPUTS),
            (
                State.GENERATING_DEAL_ANALYSIS,
                Event.DEAL_ANALYSIS_CREATED,
                State.WAITING_FOR_APPROVAL,
            ),
            (State.GENERATING_DEAL_ANALYSIS, Event.FAILED, State.ERROR),
            (State.WAITING_FOR_APPROVAL, Event.APPROVED, State.GENERATING_DECK),
            (State.WAITING_FOR_APPROVAL, Event.REJECTED, State.DONE),
            (
                State.WAITING_FOR_APPROVAL,
                Event.UPDATED_DEAL_ANALYSIS_PROVIDED,
                State.GENERATING_DECK,
            ),
            (
                State.WAITING_FOR_APPROVAL,
                Event.REGENERATE_REQUESTED,
                State.GENERATING_DEAL_ANALYSIS,
            ),
            (State.GENERATING_DECK, Event.DECK_CREATED, State.DONE),
            (State.GENERATING_DECK, Event.FAILED, State.ERROR),
            (State.ERROR, Event.ANALYSE_REQUESTED, State.GENERATING_DEAL_ANALYSIS),
            (State.ERROR, Event.CLOUD_CONSENT_GIVEN, State.GENERATING_DEAL_ANALYSIS),
            (State.ERROR, Event.REJECTED, State.DONE),
        ]

        for from_state, event, to_state in expected:
            assert (from_state, event) in TRANSITIONS
            assert TRANSITIONS[(from_state, event)] == to_state

    def test_transition_count(self):
        """Correct number of transitions defined."""
        assert len(TRANSITIONS) == 13


class TestCanTransition:
    """Tests for StateMachine.can_transition method."""

    @pytest.fixture
    def machine(self):
        return StateMachine()

    @pytest.mark.parametrize(
        "state,event",
        [
            (State.IDLE, Event.ANALYSE_REQUESTED),
            (State.IDLE, Event.INPUTS_MISSING),
            (State.GENERATING_DEAL_ANALYSIS, Event.DEAL_ANALYSIS_CREATED),
            (State.GENERATING_DEAL_ANALYSIS, Event.FAILED),
            (State.WAITING_FOR_APPROVAL, Event.APPROVED),
            (State.WAITING_FOR_APPROVAL, Event.REJECTED),
            (State.WAITING_FOR_APPROVAL, Event.UPDATED_DEAL_ANALYSIS_PROVIDED),
            (State.WAITING_FOR_APPROVAL, Event.REGENERATE_REQUESTED),
            (State.GENERATING_DECK, Event.DECK_CREATED),
            (State.GENERATING_DECK, Event.FAILED),
            (State.ERROR, Event.ANALYSE_REQUESTED),
        ],
    )
    def test_valid_transitions_return_true(self, machine, state, event):
        """can_transition returns True for all valid transitions."""
        assert machine.can_transition(state, event) is True

    @pytest.mark.parametrize(
        "state,event",
        [
            (State.IDLE, Event.APPROVED),
            (State.IDLE, Event.DECK_CREATED),
            (State.GENERATING_DEAL_ANALYSIS, Event.APPROVED),
            (State.WAITING_FOR_APPROVAL, Event.ANALYSE_REQUESTED),
            (State.GENERATING_DECK, Event.APPROVED),
            (State.DONE, Event.ANALYSE_REQUESTED),
            (State.DONE, Event.APPROVED),
        ],
    )
    def test_invalid_transitions_return_false(self, machine, state, event):
        """can_transition returns False for invalid transitions."""
        assert machine.can_transition(state, event) is False


class TestTransition:
    """Tests for StateMachine.transition method."""

    @pytest.fixture
    def machine(self):
        return StateMachine()

    def test_idle_to_generating_deal_analysis(self, machine):
        """IDLE -> GENERATING_DEAL_ANALYSIS on ANALYSE_REQUESTED."""
        machine.get_state("123", "C001", "U001")
        state = machine.transition("123", "C001", Event.ANALYSE_REQUESTED)

        assert state.state == State.GENERATING_DEAL_ANALYSIS
        assert state.previous_state == State.IDLE

    def test_idle_to_waiting_for_inputs(self, machine):
        """IDLE -> WAITING_FOR_INPUTS on INPUTS_MISSING."""
        machine.get_state("123", "C001", "U001")
        state = machine.transition("123", "C001", Event.INPUTS_MISSING)

        assert state.state == State.WAITING_FOR_INPUTS
        assert state.previous_state == State.IDLE

    def test_generating_to_waiting_for_approval(self, machine):
        """GENERATING_DEAL_ANALYSIS -> WAITING_FOR_APPROVAL on DEAL_ANALYSIS_CREATED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        state = machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)

        assert state.state == State.WAITING_FOR_APPROVAL
        assert state.previous_state == State.GENERATING_DEAL_ANALYSIS

    def test_generating_to_error(self, machine):
        """GENERATING_DEAL_ANALYSIS -> ERROR on FAILED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        state = machine.transition("123", "C001", Event.FAILED)

        assert state.state == State.ERROR
        assert state.previous_state == State.GENERATING_DEAL_ANALYSIS

    def test_approval_to_generating_deck(self, machine):
        """WAITING_FOR_APPROVAL -> GENERATING_DECK on APPROVED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)
        state = machine.transition("123", "C001", Event.APPROVED)

        assert state.state == State.GENERATING_DECK
        assert state.previous_state == State.WAITING_FOR_APPROVAL

    def test_approval_to_done_on_rejected(self, machine):
        """WAITING_FOR_APPROVAL -> DONE on REJECTED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)
        state = machine.transition("123", "C001", Event.REJECTED)

        assert state.state == State.DONE
        assert state.previous_state == State.WAITING_FOR_APPROVAL

    def test_approval_to_deck_on_updated_doc(self, machine):
        """WAITING_FOR_APPROVAL -> GENERATING_DECK on UPDATED_DEAL_ANALYSIS_PROVIDED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)
        state = machine.transition("123", "C001", Event.UPDATED_DEAL_ANALYSIS_PROVIDED)

        assert state.state == State.GENERATING_DECK
        assert state.previous_state == State.WAITING_FOR_APPROVAL

    def test_approval_to_regenerate(self, machine):
        """WAITING_FOR_APPROVAL -> GENERATING_DEAL_ANALYSIS on REGENERATE_REQUESTED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)
        state = machine.transition("123", "C001", Event.REGENERATE_REQUESTED)

        assert state.state == State.GENERATING_DEAL_ANALYSIS
        assert state.previous_state == State.WAITING_FOR_APPROVAL

    def test_deck_to_done(self, machine):
        """GENERATING_DECK -> DONE on DECK_CREATED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)
        machine.transition("123", "C001", Event.APPROVED)
        state = machine.transition("123", "C001", Event.DECK_CREATED)

        assert state.state == State.DONE
        assert state.previous_state == State.GENERATING_DECK

    def test_deck_to_error(self, machine):
        """GENERATING_DECK -> ERROR on FAILED."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)
        machine.transition("123", "C001", Event.APPROVED)
        state = machine.transition("123", "C001", Event.FAILED)

        assert state.state == State.ERROR
        assert state.previous_state == State.GENERATING_DECK

    def test_error_recovery(self, machine):
        """ERROR -> GENERATING_DEAL_ANALYSIS on ANALYSE_REQUESTED (retry)."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        machine.transition("123", "C001", Event.FAILED)
        state = machine.transition("123", "C001", Event.ANALYSE_REQUESTED)

        assert state.state == State.GENERATING_DEAL_ANALYSIS
        assert state.previous_state == State.ERROR

    def test_updates_timestamp(self, machine):
        """Transition updates updated_at timestamp."""
        state = machine.get_state("123", "C001", "U001")
        original_updated = state.updated_at

        state = machine.transition("123", "C001", Event.ANALYSE_REQUESTED)

        assert state.updated_at >= original_updated

    def test_kwargs_update_state_fields(self, machine):
        """Additional kwargs update ThreadState fields."""
        machine.get_state("123", "C001", "U001")
        state = machine.transition(
            "123",
            "C001",
            Event.ANALYSE_REQUESTED,
            client_name="Acme Corp",
            client_folder_id="folder-123",
        )

        assert state.client_name == "Acme Corp"
        assert state.client_folder_id == "folder-123"


class TestInvalidTransitions:
    """Tests for invalid transition handling."""

    @pytest.fixture
    def machine(self):
        return StateMachine()

    def test_invalid_transition_raises_error(self, machine):
        """InvalidTransitionError raised for invalid transitions."""
        machine.get_state("123", "C001", "U001")

        with pytest.raises(InvalidTransitionError) as exc_info:
            machine.transition("123", "C001", Event.APPROVED)

        assert exc_info.value.current_state == State.IDLE
        assert exc_info.value.event == Event.APPROVED

    def test_error_message_contains_details(self, machine):
        """Error message includes state and event details."""
        machine.get_state("123", "C001", "U001")

        with pytest.raises(InvalidTransitionError) as exc_info:
            machine.transition("123", "C001", Event.DECK_CREATED)

        assert "IDLE" in str(exc_info.value)
        assert "DECK_CREATED" in str(exc_info.value)


class TestApprovalGate:
    """Tests ensuring approval gate is enforced."""

    @pytest.fixture
    def machine(self):
        return StateMachine()

    def test_cannot_generate_deck_from_idle(self, machine):
        """Cannot jump to GENERATING_DECK from IDLE."""
        machine.get_state("123", "C001", "U001")

        with pytest.raises(InvalidTransitionError):
            machine.transition("123", "C001", Event.APPROVED)

    def test_cannot_generate_deck_from_generating_analysis(self, machine):
        """Cannot jump to GENERATING_DECK from GENERATING_DEAL_ANALYSIS."""
        machine.get_state("123", "C001", "U001")
        machine.transition("123", "C001", Event.ANALYSE_REQUESTED)

        with pytest.raises(InvalidTransitionError):
            machine.transition("123", "C001", Event.APPROVED)

    def test_must_go_through_approval_for_deck(self, machine):
        """Must reach WAITING_FOR_APPROVAL before generating deck."""
        machine.get_state("123", "C001", "U001")

        # Cannot skip straight to deck
        assert not machine.can_transition(State.IDLE, Event.APPROVED)
        assert not machine.can_transition(
            State.GENERATING_DEAL_ANALYSIS, Event.APPROVED
        )

        # Must go through approval
        assert machine.can_transition(State.WAITING_FOR_APPROVAL, Event.APPROVED)

    def test_happy_path_requires_approval(self, machine):
        """Full happy path must pass through approval state."""
        machine.get_state("123", "C001", "U001")

        # Start
        state = machine.transition("123", "C001", Event.ANALYSE_REQUESTED)
        assert state.state == State.GENERATING_DEAL_ANALYSIS

        # Analysis complete
        state = machine.transition("123", "C001", Event.DEAL_ANALYSIS_CREATED)
        assert state.state == State.WAITING_FOR_APPROVAL

        # Must approve to proceed
        state = machine.transition("123", "C001", Event.APPROVED)
        assert state.state == State.GENERATING_DECK

        # Complete
        state = machine.transition("123", "C001", Event.DECK_CREATED)
        assert state.state == State.DONE


class TestGetState:
    """Tests for StateMachine.get_state method."""

    @pytest.fixture
    def machine(self):
        return StateMachine()

    def test_creates_new_state(self, machine):
        """get_state creates new ThreadState if not exists."""
        state = machine.get_state("123", "C001", "U001")

        assert state.thread_ts == "123"
        assert state.channel_id == "C001"
        assert state.user_id == "U001"
        assert state.state == State.IDLE

    def test_returns_cached_state(self, machine):
        """get_state returns same instance for same thread."""
        state1 = machine.get_state("123", "C001", "U001")
        state2 = machine.get_state("123", "C001")

        assert state1 is state2

    def test_different_threads_different_states(self, machine):
        """Different threads have independent states."""
        state1 = machine.get_state("123", "C001", "U001")
        state2 = machine.get_state("456", "C001", "U001")

        assert state1 is not state2
        assert state1.thread_ts == "123"
        assert state2.thread_ts == "456"

    def test_different_channels_different_states(self, machine):
        """Same thread_ts in different channels are independent."""
        state1 = machine.get_state("123", "C001", "U001")
        state2 = machine.get_state("123", "C002", "U001")

        assert state1 is not state2
        assert state1.channel_id == "C001"
        assert state2.channel_id == "C002"


class TestStateMachineWithStorage:
    """Tests for StateMachine with storage backend."""

    @pytest.fixture
    def storage(self):
        """Create mock storage."""
        from unittest.mock import Mock

        return Mock()

    @pytest.fixture
    def machine(self, storage):
        return StateMachine(storage=storage)

    def test_loads_from_storage(self, machine, storage):
        """get_state loads existing state from storage."""
        from proposal_assistant.state import ThreadState

        existing = ThreadState(
            thread_ts="123",
            channel_id="C001",
            user_id="U001",
            client_name="Loaded Client",
        )
        storage.load.return_value = existing

        state = machine.get_state("123", "C001")

        storage.load.assert_called_once_with("123", "C001")
        assert state.client_name == "Loaded Client"

    def test_saves_new_state_to_storage(self, machine, storage):
        """get_state saves new state to storage when not found."""
        storage.load.return_value = None

        state = machine.get_state("123", "C001", "U001")

        storage.load.assert_called_once()
        storage.save.assert_called_once_with(state)

    def test_transition_saves_to_storage(self, machine, storage):
        """transition saves updated state to storage."""
        storage.load.return_value = None

        machine.get_state("123", "C001", "U001")
        storage.save.reset_mock()

        state = machine.transition("123", "C001", Event.ANALYSE_REQUESTED)

        storage.save.assert_called_once_with(state)

    def test_caches_loaded_state(self, machine, storage):
        """Loaded state is cached, storage not called twice."""
        from proposal_assistant.state import ThreadState

        existing = ThreadState(thread_ts="123", channel_id="C001", user_id="U001")
        storage.load.return_value = existing

        machine.get_state("123", "C001")
        machine.get_state("123", "C001")

        # Should only load once
        assert storage.load.call_count == 1
