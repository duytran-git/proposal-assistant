"""Tests for uploaded document parsing and deck generation flow."""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.slack.handlers import handle_approval, handle_updated_deal_analysis
from proposal_assistant.state.models import State, ThreadState


@pytest.fixture
def mock_say():
    return MagicMock()


@pytest.fixture
def mock_client():
    return MagicMock()


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.slack_bot_token = "xoxb-test"
    config.template_deck_id = "template_123"
    return config


class TestUploadedDocParsedForDeckGeneration:
    """Tests verifying uploaded docs are parsed and content used for deck generation."""

    def test_markdown_doc_parsed_and_used_for_deck(
        self, mock_say, mock_client, mock_config
    ):
        """Uploaded .md file is parsed and structured content passed to LLM."""
        file_upload_message = {
            "ts": "1706440000.000001",
            "thread_ts": "1706430000.000000",
            "channel": "C1234567890",
            "user": "U1234567890",
            "files": [
                {
                    "id": "F123",
                    "name": "deal-analysis.md",
                    "url_private_download": "https://slack.com/files/...",
                }
            ],
        }

        waiting_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.WAITING_FOR_APPROVAL,
            client_name="acme",
            proposals_folder_id="proposals_123",
            deal_analysis_content={"company": "Original"},
        )

        md_content = b"""## Opportunity Snapshot
Company: Acme Corp
Industry: Technology

## Problem & Impact
Core problem: Legacy systems causing delays
"""

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = waiting_state

            mock_response = MagicMock()
            mock_response.read.return_value = md_content
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        # Verify LLM received parsed structured content
        call_args = mock_llm.generate_proposal_deck_content.call_args[0][0]
        assert "opportunity_snapshot" in call_args
        assert "problem_impact" in call_args
        assert "Acme Corp" in call_args["opportunity_snapshot"]
        assert "Legacy systems" in call_args["problem_impact"]

    def test_docx_file_parsed_and_used_for_deck(
        self, mock_say, mock_client, mock_config
    ):
        """Uploaded .docx file is parsed and structured content passed to LLM."""
        file_upload_message = {
            "ts": "1706440000.000001",
            "thread_ts": "1706430000.000000",
            "channel": "C1234567890",
            "user": "U1234567890",
            "files": [
                {
                    "id": "F123",
                    "name": "deal-analysis.docx",
                    "url_private_download": "https://slack.com/files/...",
                }
            ],
        }

        waiting_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.WAITING_FOR_APPROVAL,
            client_name="acme",
            proposals_folder_id="proposals_123",
            deal_analysis_content={"company": "Original"},
        )

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
            patch(
                "proposal_assistant.utils.doc_parser.parse_docx"
            ) as mock_parse_docx,
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = waiting_state

            mock_response = MagicMock()
            mock_response.read.return_value = b"docx bytes"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            # Mock docx parsing to return markdown-like text
            mock_parse_docx.return_value = """## Opportunity Snapshot
Company: DOCX Corp

## Problem & Impact
Business challenge: Data silos
"""

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        # Verify LLM received parsed structured content from docx
        call_args = mock_llm.generate_proposal_deck_content.call_args[0][0]
        assert "opportunity_snapshot" in call_args
        assert "DOCX Corp" in call_args["opportunity_snapshot"]

    def test_json_formatted_doc_parsed_correctly(
        self, mock_say, mock_client, mock_config
    ):
        """Uploaded doc with JSON format is parsed correctly."""
        import json

        file_upload_message = {
            "ts": "1706440000.000001",
            "thread_ts": "1706430000.000000",
            "channel": "C1234567890",
            "user": "U1234567890",
            "files": [
                {
                    "id": "F123",
                    "name": "deal-analysis.md",
                    "url_private_download": "https://slack.com/files/...",
                }
            ],
        }

        waiting_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.WAITING_FOR_APPROVAL,
            client_name="acme",
            proposals_folder_id="proposals_123",
            deal_analysis_content={},
        )

        json_content = json.dumps({
            "opportunity_snapshot": {"company": "JSON Corp", "industry": "Finance"},
            "problem_impact": {"core_problem": "Manual reporting"},
            "current_desired_state": "Automated dashboards",
            "buying_dynamics": "CFO leads decision",
            "renessai_fit": "Full automation suite",
            "proof_next_actions": "Demo next week",
        }).encode("utf-8")

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = waiting_state

            mock_response = MagicMock()
            mock_response.read.return_value = json_content
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        # Verify LLM received parsed JSON content
        call_args = mock_llm.generate_proposal_deck_content.call_args[0][0]
        assert call_args["opportunity_snapshot"] == {
            "company": "JSON Corp",
            "industry": "Finance",
        }
        assert call_args["problem_impact"] == {"core_problem": "Manual reporting"}

    def test_approval_with_uploaded_doc_uses_parsed_content(
        self, mock_say, mock_client, mock_config
    ):
        """Approval flow with user_uploaded source parses content before LLM."""
        approval_body = {
            "actions": [{"action_id": "approve_deal_analysis"}],
            "message": {"ts": "1706430000.000000"},
            "channel": {"id": "C1234567890"},
            "user": {"id": "U1234567890"},
        }

        # State has raw uploaded content marked with source
        uploaded_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.WAITING_FOR_APPROVAL,
            client_name="acme",
            proposals_folder_id="proposals_123",
            deal_analysis_content={
                "raw_content": """## Opportunity Snapshot
Company: Uploaded Corp
Size: 500 employees

## Problem & Impact
System integration challenges
""",
                "source": "user_uploaded",
            },
        )

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = uploaded_state

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_approval(approval_body, mock_say, mock_client)

        # Verify LLM received parsed content (not raw wrapper)
        call_args = mock_llm.generate_proposal_deck_content.call_args[0][0]
        assert "raw_content" not in call_args
        assert "source" not in call_args
        assert "opportunity_snapshot" in call_args
        assert "Uploaded Corp" in call_args["opportunity_snapshot"]

    def test_missing_sections_filled_with_default(
        self, mock_say, mock_client, mock_config
    ):
        """Uploaded doc with missing sections gets default values."""
        file_upload_message = {
            "ts": "1706440000.000001",
            "thread_ts": "1706430000.000000",
            "channel": "C1234567890",
            "user": "U1234567890",
            "files": [
                {
                    "id": "F123",
                    "name": "partial.md",
                    "url_private_download": "https://slack.com/files/...",
                }
            ],
        }

        waiting_state = ThreadState(
            thread_ts="1706430000.000000",
            channel_id="C1234567890",
            user_id="U1234567890",
            state=State.WAITING_FOR_APPROVAL,
            client_name="acme",
            proposals_folder_id="proposals_123",
            deal_analysis_content={},
        )

        # Only one section provided
        partial_content = b"""## Opportunity Snapshot
Company: Partial Corp
"""

        with (
            patch("proposal_assistant.slack.handlers.get_config") as get_config,
            patch("proposal_assistant.slack.handlers.urllib.request.Request"),
            patch("proposal_assistant.slack.handlers.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.slack.handlers.StateMachine") as StateMachine,
            patch("proposal_assistant.slack.handlers.LLMClient") as LLMClient,
            patch("proposal_assistant.slack.handlers.SlidesClient") as SlidesClient,
            patch("proposal_assistant.slack.handlers.populate_proposal_deck"),
        ):
            get_config.return_value = mock_config
            StateMachine.return_value.get_state.return_value = waiting_state

            mock_response = MagicMock()
            mock_response.read.return_value = partial_content
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            mock_llm = MagicMock()
            mock_llm.generate_proposal_deck_content.return_value = {
                "content": {"slide_1_cover": {}},
            }
            LLMClient.return_value = mock_llm

            mock_slides = MagicMock()
            mock_slides.duplicate_template.return_value = ("deck_123", "link")
            SlidesClient.return_value = mock_slides

            handle_updated_deal_analysis(file_upload_message, mock_say, mock_client)

        # Verify missing sections have default value
        call_args = mock_llm.generate_proposal_deck_content.call_args[0][0]
        assert "Partial Corp" in call_args["opportunity_snapshot"]
        assert call_args["problem_impact"] == "Unknown / Not provided"
        assert call_args["buying_dynamics"] == "Unknown / Not provided"
        assert call_args["renessai_fit"] == "Unknown / Not provided"
