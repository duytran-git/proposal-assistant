"""Unit tests for Deal Analysis regeneration flow.

Tests that v1 documents remain accessible when v2 is created,
and that version numbering works correctly through the flow.
"""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.docs.deal_analysis import create_versioned_document_title
from proposal_assistant.slack.handlers import handle_regenerate
from proposal_assistant.slack.messages import ERROR_MESSAGES
from proposal_assistant.state.models import Event, State, ThreadState


class TestV1ExistsBeforeRegenerate:
    """Tests verifying v1 state exists before regeneration."""

    @pytest.fixture
    def thread_state_v1(self):
        """Thread state after v1 Deal Analysis is created."""
        return ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            client_name="acme",
            analyse_folder_id="analyse_folder_123",
            proposals_folder_id="proposals_folder_123",
            deal_analysis_doc_id="doc_v1_id",
            deal_analysis_link="https://docs.google.com/document/d/doc_v1_id",
            deal_analysis_content={"company": "Acme Corp"},
            deal_analysis_version=1,
            input_transcript_content=["# Meeting transcript\n\nDiscussion about project."],
            state=State.WAITING_FOR_APPROVAL,
        )

    def test_v1_doc_id_stored_in_state(self, thread_state_v1):
        """V1 document ID is stored in thread state."""
        assert thread_state_v1.deal_analysis_doc_id == "doc_v1_id"

    def test_v1_link_stored_in_state(self, thread_state_v1):
        """V1 document link is stored in thread state."""
        assert "doc_v1_id" in thread_state_v1.deal_analysis_link

    def test_v1_version_is_one(self, thread_state_v1):
        """Initial version is 1."""
        assert thread_state_v1.deal_analysis_version == 1

    def test_v1_content_stored_for_regeneration(self, thread_state_v1):
        """Transcript content is stored for potential regeneration."""
        assert len(thread_state_v1.input_transcript_content) == 1
        assert "Meeting transcript" in thread_state_v1.input_transcript_content[0]


class TestRegenerateCreatesV2:
    """Tests that regeneration creates v2 while preserving v1."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        config = MagicMock()
        config.google_credentials_path = "/path/to/creds.json"
        config.llm_api_key = "test-key"
        return config

    @pytest.fixture
    def thread_state_v1(self):
        """Thread state with v1 completed."""
        return ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            client_name="acme",
            analyse_folder_id="analyse_folder_123",
            proposals_folder_id="proposals_folder_123",
            deal_analysis_doc_id="doc_v1_id",
            deal_analysis_link="https://docs.google.com/document/d/doc_v1_id",
            deal_analysis_content={"company": "Acme Corp v1"},
            deal_analysis_version=1,
            input_transcript_content=["# Original transcript content"],
            state=State.WAITING_FOR_APPROVAL,
        )

    @pytest.fixture
    def regenerate_body(self):
        """Slack action body for regenerate button click."""
        return {
            "channel": {"id": "C1234567890"},
            "message": {"thread_ts": "1706430000.000000"},
            "user": {"id": "U1234567890"},
        }

    def test_regenerate_creates_v2_doc_with_new_id(
        self, mock_config, thread_state_v1, regenerate_body
    ):
        """Regenerate creates a new document with different ID than v1."""
        mock_say = MagicMock()
        mock_client = MagicMock()

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.share_with_channel_members"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = thread_state_v1

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme Corp v2"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2_id", "https://docs.google.com/document/d/doc_v2_id")
            DocsClient.return_value = mock_docs

            handle_regenerate(regenerate_body, mock_say, mock_client)

        # V2 has different doc ID than v1
        mock_docs.create_document.assert_called_once()
        v2_doc_id = mock_docs.create_document.return_value[0]
        assert v2_doc_id == "doc_v2_id"
        assert v2_doc_id != thread_state_v1.deal_analysis_doc_id

    def test_v1_doc_not_deleted_during_regenerate(
        self, mock_config, thread_state_v1, regenerate_body
    ):
        """V1 document is not deleted when v2 is created."""
        mock_say = MagicMock()
        mock_client = MagicMock()

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient") as DriveClient,
            patch("proposal_assistant.slack.handlers.share_with_channel_members"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = thread_state_v1

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme Corp v2"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2_id", "link_v2")
            DocsClient.return_value = mock_docs

            mock_drive = MagicMock()
            DriveClient.return_value = mock_drive

            handle_regenerate(regenerate_body, mock_say, mock_client)

        # Verify no delete calls were made
        mock_drive.delete_file.assert_not_called()
        mock_docs._docs_service.documents().delete.assert_not_called()

    def test_v2_title_includes_version_suffix(
        self, mock_config, thread_state_v1, regenerate_body
    ):
        """V2 document title includes 'v2' suffix."""
        mock_say = MagicMock()
        mock_client = MagicMock()

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.share_with_channel_members"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = thread_state_v1

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme Corp v2"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2_id", "link_v2")
            DocsClient.return_value = mock_docs

            handle_regenerate(regenerate_body, mock_say, mock_client)

        call_args = mock_docs.create_document.call_args[0]
        doc_title = call_args[0]
        assert "v2" in doc_title
        assert doc_title == "acme - Deal Analysis v2"

    def test_state_updated_to_version_2(
        self, mock_config, thread_state_v1, regenerate_body
    ):
        """Thread state is updated to version 2 after regeneration."""
        mock_say = MagicMock()
        mock_client = MagicMock()

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.share_with_channel_members"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = thread_state_v1

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme Corp v2"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2_id", "link_v2")
            DocsClient.return_value = mock_docs

            handle_regenerate(regenerate_body, mock_say, mock_client)

        state_machine = StateMachine.return_value
        transition_calls = state_machine.transition.call_args_list

        # First transition: REGENERATE_REQUESTED with version 2
        first_transition = transition_calls[0][1]
        assert first_transition["event"] == Event.REGENERATE_REQUESTED
        assert first_transition["deal_analysis_version"] == 2


class TestBothVersionsAccessible:
    """Tests verifying both v1 and v2 remain accessible."""

    def test_v1_title_has_no_version_suffix(self):
        """V1 document title has no version suffix for cleaner naming."""
        title = create_versioned_document_title("Acme - Deal Analysis", 1)
        assert title == "Acme - Deal Analysis"
        assert "v1" not in title

    def test_v2_title_has_version_suffix(self):
        """V2 document title includes version suffix."""
        title = create_versioned_document_title("Acme - Deal Analysis", 2)
        assert title == "Acme - Deal Analysis v2"

    def test_versions_have_distinct_titles(self):
        """V1 and V2 have distinct titles for easy identification."""
        v1_title = create_versioned_document_title("Client - Deal Analysis", 1)
        v2_title = create_versioned_document_title("Client - Deal Analysis", 2)

        assert v1_title != v2_title
        assert v1_title == "Client - Deal Analysis"
        assert v2_title == "Client - Deal Analysis v2"

    def test_multiple_regenerations_create_distinct_versions(self):
        """Multiple regenerations create v2, v3, v4, etc."""
        base_title = "Acme - Deal Analysis"

        v1 = create_versioned_document_title(base_title, 1)
        v2 = create_versioned_document_title(base_title, 2)
        v3 = create_versioned_document_title(base_title, 3)
        v4 = create_versioned_document_title(base_title, 4)

        # All versions are distinct
        versions = [v1, v2, v3, v4]
        assert len(set(versions)) == 4

        # Correct naming
        assert v1 == "Acme - Deal Analysis"
        assert v2 == "Acme - Deal Analysis v2"
        assert v3 == "Acme - Deal Analysis v3"
        assert v4 == "Acme - Deal Analysis v4"


class TestRegenerationPreservesOriginalInputs:
    """Tests that regeneration uses stored inputs, not new ones."""

    @pytest.fixture
    def mock_config(self):
        """Mock configuration."""
        config = MagicMock()
        config.google_credentials_path = "/path/to/creds.json"
        config.llm_api_key = "test-key"
        return config

    @pytest.fixture
    def thread_state_with_multiple_transcripts(self):
        """Thread state with multiple transcript files stored."""
        return ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            client_name="acme",
            analyse_folder_id="analyse_folder_123",
            proposals_folder_id="proposals_folder_123",
            deal_analysis_doc_id="doc_v1_id",
            deal_analysis_link="https://docs.google.com/document/d/doc_v1_id",
            deal_analysis_content={"company": "Acme Corp"},
            deal_analysis_version=1,
            input_transcript_content=[
                "# Meeting 1\n\nInitial discussion.",
                "# Meeting 2\n\nFollow-up points.",
            ],
            state=State.WAITING_FOR_APPROVAL,
        )

    @pytest.fixture
    def regenerate_body(self):
        """Slack action body."""
        return {
            "channel": {"id": "C1234567890"},
            "message": {"thread_ts": "1706430000.000000"},
            "user": {"id": "U1234567890"},
        }

    def test_regenerate_uses_all_stored_transcripts(
        self, mock_config, thread_state_with_multiple_transcripts, regenerate_body
    ):
        """Regeneration uses all originally provided transcript files."""
        mock_say = MagicMock()
        mock_client = MagicMock()

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.DocsClient") as DocsClient,
            patch("proposal_assistant.slack.handlers.DriveClient"),
            patch("proposal_assistant.slack.handlers.share_with_channel_members"),
            patch("proposal_assistant.slack.handlers.populate_deal_analysis"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = thread_state_with_multiple_transcripts

            mock_llm = MagicMock()
            mock_llm.generate_deal_analysis.return_value = {
                "content": {"company": "Acme"},
                "missing_info": [],
            }
            LLMClient.return_value = mock_llm

            mock_docs = MagicMock()
            mock_docs.create_document.return_value = ("doc_v2_id", "link_v2")
            DocsClient.return_value = mock_docs

            handle_regenerate(regenerate_body, mock_say, mock_client)

        # LLM called with both original transcripts
        mock_llm.generate_deal_analysis.assert_called_once()
        call_kwargs = mock_llm.generate_deal_analysis.call_args[1]
        assert call_kwargs["transcript"] == [
            "# Meeting 1\n\nInitial discussion.",
            "# Meeting 2\n\nFollow-up points.",
        ]

    def test_regenerate_fails_gracefully_if_transcripts_missing(self, regenerate_body):
        """Regeneration shows error if stored transcripts are missing."""
        mock_say = MagicMock()
        mock_client = MagicMock()

        empty_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            # No transcripts stored
            input_transcript_content=[],
            analyse_folder_id="folder_123",
        )

        with patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine:
            StateMachine.return_value.get_state.return_value = empty_state

            handle_regenerate(regenerate_body, mock_say, mock_client)

        mock_say.assert_called_once()
        call_kwargs = mock_say.call_args[1]
        assert call_kwargs["text"] == ERROR_MESSAGES["STATE_MISSING"]
