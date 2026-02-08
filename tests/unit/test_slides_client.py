"""Unit tests for Google Slides client and Proposal Deck population."""

from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.slides.client import SCOPES, SlidesClient
from proposal_assistant.slides.proposal_deck import (
    FOOTER_TEXT,
    SLIDE_CONTENT_KEYS,
    SLIDE_LAYOUTS,
    _PLACEHOLDER_FIELDS,
    populate_proposal_deck,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_config():
    """Create a mock Config with Google credentials."""
    config = MagicMock()
    config.google_service_account_json = (
        '{"type": "service_account", "project_id": "test"}'
    )
    config.proposal_template_slide_id = "template_123"
    return config


@pytest.fixture
def slides_client(mock_config):
    """Create a SlidesClient with mocked Google APIs."""
    with (
        patch("proposal_assistant.slides.client.Credentials") as mock_creds,
        patch("proposal_assistant.slides.client.build") as mock_build,
    ):
        mock_creds.from_service_account_info.return_value = MagicMock()
        mock_slides_service = MagicMock()
        mock_drive_service = MagicMock()

        def build_side_effect(service_name, version, credentials=None):
            if service_name == "slides":
                return mock_slides_service
            return mock_drive_service

        mock_build.side_effect = build_side_effect

        client = SlidesClient(mock_config)
        client._mock_slides_service = mock_slides_service
        client._mock_drive_service = mock_drive_service
        yield client


@pytest.fixture
def sample_slide_content():
    """Sample proposal deck content for testing."""
    return {
        "slide_1_cover": {
            "center_title": "Acme Corp x Renessai - Digital Transformation",
            "subtitle": "Prepared for Jane Smith",
        },
        "slide_2_executive_summary": {
            "title": "Executive Summary",
            "body": "Acme Corp seeks to modernize their legacy systems.",
        },
        "slide_3_client_context": {
            "title": "Client Context & Objectives",
            "body_left": "Current: Legacy ERP system",
            "body_right": "Desired: Cloud-native platform",
        },
        "slide_4_challenges": {
            "title": "Challenges & Business Impact",
            "body": "Manual processes causing delays and errors.",
        },
        "slide_5_proposed_solution": {
            "title": "Proposed Solution",
            "subtitle": "Modern cloud platform",
            "body": "Key capabilities: automation, integration, analytics",
        },
        "slide_6_solution_scope": {
            "title": "Solution Details & Scope",
            "body": "Must-haves: API integration, data migration",
        },
        "slide_7_implementation": {
            "title": "Implementation Approach",
            "body_left": "Phase 1: Discovery\nPhase 2: Build",
            "body_right": "8 weeks total",
        },
        "slide_8_value_case": {
            "title": "30% Cost Reduction",
            "body": "Through automation of manual processes",
        },
        "slide_9_commercials": {
            "title": "Investment & Terms",
            "body": "Budget: $500K - $750K",
        },
        "slide_10_risk_mitigation": {
            "title": "Risk Mitigation",
            "body_left": "Data migration risks",
            "body_right": "Phased rollout approach",
        },
        "slide_11_proof_of_success": {
            "title": "Proven Results",
            "body": "Similar project: 40% efficiency gain",
        },
        "slide_12_next_steps": {
            "title": "Next Steps",
            "body": "1. Sign SOW by Jan 15\n2. Kickoff meeting Jan 20",
        },
    }


# ── SlidesClient Init ──────────────────────────────────────────────


class TestSlidesClientInit:
    """Tests for SlidesClient initialization."""

    def test_creates_credentials_with_correct_scopes(self, mock_config):
        with (
            patch("proposal_assistant.slides.client.Credentials") as mock_creds,
            patch("proposal_assistant.slides.client.build"),
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            SlidesClient(mock_config)

            mock_creds.from_service_account_info.assert_called_once()
            call_kwargs = mock_creds.from_service_account_info.call_args
            assert call_kwargs[0][0] == {
                "type": "service_account",
                "project_id": "test",
            }
            assert call_kwargs[1]["scopes"] == SCOPES

    def test_builds_slides_v1_service(self, mock_config):
        with (
            patch("proposal_assistant.slides.client.Credentials") as mock_creds,
            patch("proposal_assistant.slides.client.build") as mock_build,
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            SlidesClient(mock_config)

            calls = [c for c in mock_build.call_args_list if c[0][0] == "slides"]
            assert len(calls) == 1
            assert calls[0][0] == ("slides", "v1")

    def test_builds_drive_v3_service(self, mock_config):
        with (
            patch("proposal_assistant.slides.client.Credentials") as mock_creds,
            patch("proposal_assistant.slides.client.build") as mock_build,
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            SlidesClient(mock_config)

            calls = [c for c in mock_build.call_args_list if c[0][0] == "drive"]
            assert len(calls) == 1
            assert calls[0][0] == ("drive", "v3")

    def test_stores_template_id(self, mock_config):
        with (
            patch("proposal_assistant.slides.client.Credentials") as mock_creds,
            patch("proposal_assistant.slides.client.build"),
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            client = SlidesClient(mock_config)

            assert client._template_id == "template_123"


# ── duplicate_template ─────────────────────────────────────────────


class TestDuplicateTemplate:
    """Tests for template duplication."""

    def test_returns_presentation_id_and_web_link(self, slides_client):
        slides_client._mock_drive_service.files().copy().execute.return_value = {
            "id": "new_pres_456",
            "webViewLink": "https://docs.google.com/presentation/d/new_pres_456",
        }

        pres_id, web_link = slides_client.duplicate_template(
            "Test Proposal", "folder_789"
        )

        assert pres_id == "new_pres_456"
        assert web_link == "https://docs.google.com/presentation/d/new_pres_456"

    def test_sends_correct_copy_request(self, slides_client):
        slides_client._mock_drive_service.files().copy().execute.return_value = {
            "id": "new_pres_456",
            "webViewLink": "https://example.com",
        }

        slides_client.duplicate_template("My Proposal", "target_folder")

        slides_client._mock_drive_service.files().copy.assert_called_with(
            fileId="template_123",
            body={"name": "My Proposal", "parents": ["target_folder"]},
            fields="id,webViewLink",
        )

    def test_uses_template_id_from_config(self, slides_client):
        slides_client._template_id = "custom_template_999"
        slides_client._mock_drive_service.files().copy().execute.return_value = {
            "id": "new_id",
            "webViewLink": "https://example.com",
        }

        slides_client.duplicate_template("Title", "folder")

        call_kwargs = slides_client._mock_drive_service.files().copy.call_args
        assert call_kwargs[1]["fileId"] == "custom_template_999"


# ── get_layout_by_name ─────────────────────────────────────────────


class TestGetLayoutByName:
    """Tests for layout selection by name."""

    def test_returns_layout_id_when_found(self, slides_client):
        slides_client._mock_slides_service.presentations().get().execute.return_value = {
            "layouts": [
                {
                    "objectId": "layout_001",
                    "layoutProperties": {"displayName": "TITLE"},
                },
                {
                    "objectId": "layout_002",
                    "layoutProperties": {"displayName": "TITLE_AND_BODY"},
                },
            ]
        }

        result = slides_client.get_layout_by_name("pres_123", "TITLE_AND_BODY")

        assert result == "layout_002"

    def test_returns_none_when_not_found(self, slides_client):
        slides_client._mock_slides_service.presentations().get().execute.return_value = {
            "layouts": [
                {
                    "objectId": "layout_001",
                    "layoutProperties": {"displayName": "TITLE"},
                },
            ]
        }

        result = slides_client.get_layout_by_name("pres_123", "NONEXISTENT")

        assert result is None

    def test_returns_none_for_empty_layouts(self, slides_client):
        slides_client._mock_slides_service.presentations().get().execute.return_value = {
            "layouts": []
        }

        result = slides_client.get_layout_by_name("pres_123", "TITLE")

        assert result is None

    def test_calls_get_with_correct_fields(self, slides_client):
        slides_client._mock_slides_service.presentations().get().execute.return_value = {
            "layouts": []
        }

        slides_client.get_layout_by_name("pres_abc", "TITLE")

        slides_client._mock_slides_service.presentations().get.assert_called_with(
            presentationId="pres_abc",
            fields="layouts(objectId,layoutProperties.displayName)",
        )

    def test_handles_missing_layout_properties(self, slides_client):
        slides_client._mock_slides_service.presentations().get().execute.return_value = {
            "layouts": [
                {"objectId": "layout_001"},  # No layoutProperties
            ]
        }

        result = slides_client.get_layout_by_name("pres_123", "TITLE")

        assert result is None


# ── populate_proposal_deck ─────────────────────────────────────────


class TestPopulateProposalDeck:
    """Tests for proposal deck population."""

    def test_calls_batch_update_with_presentation_id(
        self, slides_client, sample_slide_content
    ):
        # Mock presentation structure
        slides_client._slides_service.presentations().get().execute.return_value = {
            "slides": [self._make_slide_page(i) for i in range(1, 13)]
        }
        slides_client._slides_service.presentations().batchUpdate().execute.return_value = (
            {}
        )

        populate_proposal_deck(slides_client, "pres_123", sample_slide_content)

        slides_client._slides_service.presentations().batchUpdate.assert_called()
        call_kwargs = (
            slides_client._slides_service.presentations().batchUpdate.call_args
        )
        assert call_kwargs[1]["presentationId"] == "pres_123"

    def test_generates_requests_for_all_slides(
        self, slides_client, sample_slide_content
    ):
        slides_client._slides_service.presentations().get().execute.return_value = {
            "slides": [self._make_slide_page(i) for i in range(1, 13)]
        }
        slides_client._slides_service.presentations().batchUpdate().execute.return_value = (
            {}
        )

        populate_proposal_deck(slides_client, "pres_123", sample_slide_content)

        call_kwargs = (
            slides_client._slides_service.presentations().batchUpdate.call_args
        )
        requests = call_kwargs[1]["body"]["requests"]

        # Should have requests for text deletion and insertion for each placeholder,
        # plus footer creation for each slide
        assert len(requests) > 0

    def test_handles_missing_content_gracefully(self, slides_client):
        slides_client._slides_service.presentations().get().execute.return_value = {
            "slides": [self._make_slide_page(i) for i in range(1, 13)]
        }
        slides_client._slides_service.presentations().batchUpdate().execute.return_value = (
            {}
        )

        # Provide only partial content
        partial_content = {
            "slide_1_cover": {
                "center_title": "Test",
                "subtitle": "Subtitle",
            }
        }

        # Should not raise
        populate_proposal_deck(slides_client, "pres_123", partial_content)

    def test_adds_footer_to_slides(self, slides_client, sample_slide_content):
        slides_client._slides_service.presentations().get().execute.return_value = {
            "slides": [self._make_slide_page(i) for i in range(1, 13)]
        }
        slides_client._slides_service.presentations().batchUpdate().execute.return_value = (
            {}
        )

        populate_proposal_deck(slides_client, "pres_123", sample_slide_content)

        call_kwargs = (
            slides_client._slides_service.presentations().batchUpdate.call_args
        )
        requests = call_kwargs[1]["body"]["requests"]

        # Find footer text insertions
        footer_inserts = [
            r
            for r in requests
            if "insertText" in r and r["insertText"].get("text") == FOOTER_TEXT
        ]
        assert len(footer_inserts) == 12  # Footer for each slide

    def test_deletes_existing_text_before_insert(
        self, slides_client, sample_slide_content
    ):
        slides_client._slides_service.presentations().get().execute.return_value = {
            "slides": [self._make_slide_page(1)]
        }
        slides_client._slides_service.presentations().batchUpdate().execute.return_value = (
            {}
        )

        populate_proposal_deck(slides_client, "pres_123", sample_slide_content)

        call_kwargs = (
            slides_client._slides_service.presentations().batchUpdate.call_args
        )
        requests = call_kwargs[1]["body"]["requests"]

        # For each placeholder, deleteText should come before insertText
        delete_count = sum(1 for r in requests if "deleteText" in r)
        insert_content = sum(
            1
            for r in requests
            if "insertText" in r and r["insertText"].get("text") != FOOTER_TEXT
        )

        # Each placeholder should have a delete followed by an insert
        assert delete_count == insert_content

    @staticmethod
    def _make_slide_page(slide_num: int) -> dict:
        """Create a mock slide page with expected placeholder structure."""
        layout_name = SLIDE_LAYOUTS.get(slide_num, "TITLE_AND_BODY")
        field_map = _PLACEHOLDER_FIELDS.get(layout_name, {})

        page_elements = []
        for field_name, (ph_type, ph_index) in field_map.items():
            page_elements.append(
                {
                    "objectId": f"slide_{slide_num}_{field_name}",
                    "placeholder": {
                        "type": ph_type,
                        "index": ph_index,
                    },
                }
            )

        return {
            "objectId": f"slide_page_{slide_num}",
            "pageElements": page_elements,
        }


# ── Slide Configuration Constants ──────────────────────────────────


class TestSlideConstants:
    """Tests for slide configuration constants."""

    def test_slide_layouts_covers_12_slides(self):
        assert len(SLIDE_LAYOUTS) == 12
        assert all(i in SLIDE_LAYOUTS for i in range(1, 13))

    def test_slide_content_keys_covers_12_slides(self):
        assert len(SLIDE_CONTENT_KEYS) == 12
        assert all(i in SLIDE_CONTENT_KEYS for i in range(1, 13))

    def test_content_keys_match_expected_pattern(self):
        for slide_num, key in SLIDE_CONTENT_KEYS.items():
            assert key.startswith(f"slide_{slide_num}_")

    def test_all_layouts_have_placeholder_fields(self):
        layout_names = set(SLIDE_LAYOUTS.values())
        for layout_name in layout_names:
            assert layout_name in _PLACEHOLDER_FIELDS

    def test_title_layout_has_center_title_and_subtitle(self):
        assert "center_title" in _PLACEHOLDER_FIELDS["TITLE"]
        assert "subtitle" in _PLACEHOLDER_FIELDS["TITLE"]

    def test_title_and_body_layout_has_title_and_body(self):
        assert "title" in _PLACEHOLDER_FIELDS["TITLE_AND_BODY"]
        assert "body" in _PLACEHOLDER_FIELDS["TITLE_AND_BODY"]

    def test_two_columns_layout_has_body_left_and_right(self):
        assert "title" in _PLACEHOLDER_FIELDS["TITLE_AND_TWO_COLUMNS"]
        assert "body_left" in _PLACEHOLDER_FIELDS["TITLE_AND_TWO_COLUMNS"]
        assert "body_right" in _PLACEHOLDER_FIELDS["TITLE_AND_TWO_COLUMNS"]

    def test_section_layout_has_title_subtitle_body(self):
        assert "title" in _PLACEHOLDER_FIELDS["SECTION_TITLE_AND_DESCRIPTION"]
        assert "subtitle" in _PLACEHOLDER_FIELDS["SECTION_TITLE_AND_DESCRIPTION"]
        assert "body" in _PLACEHOLDER_FIELDS["SECTION_TITLE_AND_DESCRIPTION"]

    def test_big_number_layout_has_title_and_body(self):
        assert "title" in _PLACEHOLDER_FIELDS["BIG_NUMBER"]
        assert "body" in _PLACEHOLDER_FIELDS["BIG_NUMBER"]
