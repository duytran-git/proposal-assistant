"""Unit tests for Google Docs client and Deal Analysis population."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.docs.client import SCOPES, DocsClient
from proposal_assistant.docs.deal_analysis import (
    FOOTER_TEXT,
    SNAPSHOT_FIELDS,
    _Segment,
    _build_segments,
    _segments_to_requests,
    populate_deal_analysis,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "llm_responses"


# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def mock_config():
    """Create a mock Config with Google credentials."""
    config = MagicMock()
    config.google_service_account_json = (
        '{"type": "service_account", "project_id": "test"}'
    )
    config.google_drive_root_folder_id = "root_folder_123"
    return config


@pytest.fixture
def docs_client(mock_config):
    """Create a DocsClient with mocked Google APIs."""
    with (
        patch("proposal_assistant.docs.client.Credentials") as mock_creds,
        patch("proposal_assistant.docs.client.build") as mock_build,
    ):
        mock_creds.from_service_account_info.return_value = MagicMock()
        mock_docs_service = MagicMock()
        mock_drive_service = MagicMock()

        def build_side_effect(service_name, version, credentials=None):
            if service_name == "docs":
                return mock_docs_service
            return mock_drive_service

        mock_build.side_effect = build_side_effect

        client = DocsClient(mock_config)
        client._mock_docs_service = mock_docs_service
        client._mock_drive_service = mock_drive_service
        yield client


@pytest.fixture
def deal_content():
    """Load deal analysis content from fixture."""
    data = json.loads((FIXTURES_DIR / "deal_analysis_response.json").read_text())
    return data["deal_analysis"]


@pytest.fixture
def missing_info():
    """Load missing info from fixture."""
    data = json.loads((FIXTURES_DIR / "deal_analysis_response.json").read_text())
    return data["missing_info"]


# ── DocsClient Init ──────────────────────────────────────────────


class TestDocsClientInit:
    """Tests for DocsClient initialization."""

    def test_creates_credentials_with_correct_scopes(self, mock_config):
        with (
            patch("proposal_assistant.docs.client.Credentials") as mock_creds,
            patch("proposal_assistant.docs.client.build"),
        ):
            mock_creds.from_service_account_info.return_value = MagicMock()
            DocsClient(mock_config)

            mock_creds.from_service_account_info.assert_called_once()
            call_kwargs = mock_creds.from_service_account_info.call_args
            assert call_kwargs[0][0] == {
                "type": "service_account",
                "project_id": "test",
            }
            assert call_kwargs[1]["scopes"] == SCOPES

    def test_builds_docs_v1_service(self, mock_config):
        with (
            patch("proposal_assistant.docs.client.Credentials") as mock_creds,
            patch("proposal_assistant.docs.client.build") as mock_build,
        ):
            creds = MagicMock()
            mock_creds.from_service_account_info.return_value = creds
            mock_build.return_value = MagicMock()
            DocsClient(mock_config)

            calls = mock_build.call_args_list
            assert any(
                c.args == ("docs", "v1") and c.kwargs["credentials"] == creds
                for c in calls
            )

    def test_builds_drive_v3_service(self, mock_config):
        with (
            patch("proposal_assistant.docs.client.Credentials") as mock_creds,
            patch("proposal_assistant.docs.client.build") as mock_build,
        ):
            creds = MagicMock()
            mock_creds.from_service_account_info.return_value = creds
            mock_build.return_value = MagicMock()
            DocsClient(mock_config)

            calls = mock_build.call_args_list
            assert any(
                c.args == ("drive", "v3") and c.kwargs["credentials"] == creds
                for c in calls
            )


# ── Create Document ──────────────────────────────────────────────


class TestCreateDocument:
    """Tests for DocsClient.create_document."""

    def test_returns_doc_id_and_web_link(self, docs_client):
        mock_files = docs_client._mock_drive_service.files.return_value
        mock_files.create.return_value.execute.return_value = {
            "id": "doc_123",
            "webViewLink": "https://docs.google.com/document/d/doc_123/edit",
        }

        doc_id, web_link = docs_client.create_document("Test Doc", "folder_456")

        assert doc_id == "doc_123"
        assert web_link == "https://docs.google.com/document/d/doc_123/edit"

    def test_sends_correct_metadata(self, docs_client):
        mock_files = docs_client._mock_drive_service.files.return_value
        mock_files.create.return_value.execute.return_value = {
            "id": "doc_id",
            "webViewLink": "https://link",
        }

        docs_client.create_document("My Analysis", "folder_789")

        call_kwargs = mock_files.create.call_args[1]
        body = call_kwargs["body"]
        assert body["name"] == "My Analysis"
        assert body["mimeType"] == "application/vnd.google-apps.document"
        assert body["parents"] == ["folder_789"]
        assert call_kwargs["fields"] == "id,webViewLink"

    def test_uses_drive_service_not_docs_service(self, docs_client):
        mock_files = docs_client._mock_drive_service.files.return_value
        mock_files.create.return_value.execute.return_value = {
            "id": "id",
            "webViewLink": "link",
        }

        docs_client.create_document("Title", "folder")

        docs_client._mock_drive_service.files.assert_called()
        docs_client._mock_docs_service.documents.assert_not_called()


# ── Build Segments ───────────────────────────────────────────────


class TestBuildSegments:
    """Tests for _build_segments template assembly."""

    def test_includes_all_six_section_headings(self, deal_content):
        segments = _build_segments(deal_content, [])
        heading_texts = [s.text for s in segments if s.heading == 1]
        assert "1. Opportunity Snapshot\n" in heading_texts
        assert "2. Problem & Impact\n" in heading_texts
        assert "3. Current vs Desired State\n" in heading_texts
        assert "4. Buying Dynamics & Risk\n" in heading_texts
        assert "5. Renessai Fit & Strategy\n" in heading_texts
        assert "6. Proof & Next Actions\n" in heading_texts

    def test_includes_opportunity_snapshot_fields(self, deal_content):
        segments = _build_segments(deal_content, [])
        full_text = "".join(s.text for s in segments)
        assert "Company: " in full_text
        assert "Acme Corp" in full_text
        assert "Industry / Segment: " in full_text
        assert "Manufacturing" in full_text

    def test_snapshot_labels_are_bold(self, deal_content):
        segments = _build_segments(deal_content, [])
        bold_texts = [s.text for s in segments if s.bold]
        for label, _ in SNAPSHOT_FIELDS:
            assert f"{label}: " in bold_texts

    def test_includes_subsection_headings(self, deal_content):
        segments = _build_segments(deal_content, [])
        h2_texts = [s.text for s in segments if s.heading == 2]
        assert "2.1 Core Problem Statement\n" in h2_texts
        assert "2.2 Business Impact\n" in h2_texts
        assert "3.1 Current State\n" in h2_texts
        assert "3.2 Desired Future State\n" in h2_texts
        assert "6.2 Next Steps\n" in h2_texts

    def test_includes_content_values(self, deal_content):
        segments = _build_segments(deal_content, [])
        full_text = "".join(s.text for s in segments)
        assert "Legacy ERP system" in full_text
        assert "SAP R/3 on-prem" in full_text
        assert "CTO (decision maker)" in full_text

    def test_missing_fields_default_to_unknown(self):
        segments = _build_segments({}, [])
        full_text = "".join(s.text for s in segments)
        assert full_text.count("Unknown") >= 6

    def test_footer_is_last_segment(self, deal_content):
        segments = _build_segments(deal_content, [])
        last = segments[-1]
        assert FOOTER_TEXT in last.text

    def test_footer_is_italic_and_gray(self, deal_content):
        segments = _build_segments(deal_content, [])
        footer = segments[-1]
        assert footer.italic is True
        assert footer.color == (0.6, 0.6, 0.6)


# ── Missing Info Warning ─────────────────────────────────────────


class TestMissingInfoWarning:
    """Tests for missing info warning block."""

    def test_warning_appears_when_missing_info_provided(
        self, deal_content, missing_info
    ):
        segments = _build_segments(deal_content, missing_info)
        full_text = "".join(s.text for s in segments)
        assert "Missing Information" in full_text

    def test_no_warning_when_missing_info_empty(self, deal_content):
        segments = _build_segments(deal_content, [])
        full_text = "".join(s.text for s in segments)
        assert "Missing Information" not in full_text

    def test_warning_lists_each_item(self, deal_content, missing_info):
        segments = _build_segments(deal_content, missing_info)
        full_text = "".join(s.text for s in segments)
        for item in missing_info:
            assert item in full_text

    def test_warning_items_are_red(self, deal_content, missing_info):
        segments = _build_segments(deal_content, missing_info)
        red = (0.8, 0.0, 0.0)
        warning_segments = []
        for s in segments:
            if "Missing Information" in s.text:
                break
        # Collect all segments until we hit a non-colored one
        found_start = False
        for s in segments:
            if "Missing Information" in s.text:
                found_start = True
            if found_start and s.color == red:
                warning_segments.append(s)
            elif found_start and s.text == "\n":
                break
        assert len(warning_segments) >= 2  # heading + description + items

    def test_warning_heading_is_bold(self, deal_content, missing_info):
        segments = _build_segments(deal_content, missing_info)
        heading = next(s for s in segments if "Missing Information" in s.text)
        assert heading.bold is True
        assert heading.heading == 2

    def test_warning_precedes_section_1(self, deal_content, missing_info):
        segments = _build_segments(deal_content, missing_info)
        texts = [s.text for s in segments]
        warning_idx = next(i for i, t in enumerate(texts) if "Missing Information" in t)
        snapshot_idx = next(
            i for i, t in enumerate(texts) if "1. Opportunity Snapshot" in t
        )
        assert warning_idx < snapshot_idx


# ── Segments to Requests ─────────────────────────────────────────


class TestSegmentsToRequests:
    """Tests for _segments_to_requests API request generation."""

    def test_empty_segments_returns_empty(self):
        assert _segments_to_requests([]) == []

    def test_first_request_is_insert_text(self):
        segments = [_Segment("Hello\n")]
        requests = _segments_to_requests(segments)
        assert requests[0]["insertText"]["location"]["index"] == 1
        assert requests[0]["insertText"]["text"] == "Hello\n"

    def test_inserts_all_text_at_once(self, deal_content):
        segments = _build_segments(deal_content, [])
        requests = _segments_to_requests(segments)
        insert_requests = [r for r in requests if "insertText" in r]
        assert len(insert_requests) == 1

    def test_heading_generates_paragraph_style(self):
        segments = [_Segment("Title\n", heading=1)]
        requests = _segments_to_requests(segments)
        para_reqs = [r for r in requests if "updateParagraphStyle" in r]
        assert len(para_reqs) == 1
        style = para_reqs[0]["updateParagraphStyle"]
        assert style["paragraphStyle"]["namedStyleType"] == "HEADING_1"
        assert style["range"] == {"startIndex": 1, "endIndex": 7}

    def test_heading_2_generates_correct_style(self):
        segments = [_Segment("Sub\n", heading=2)]
        requests = _segments_to_requests(segments)
        para_reqs = [r for r in requests if "updateParagraphStyle" in r]
        style = para_reqs[0]["updateParagraphStyle"]
        assert style["paragraphStyle"]["namedStyleType"] == "HEADING_2"

    def test_bold_generates_text_style(self):
        segments = [_Segment("Bold text\n", bold=True)]
        requests = _segments_to_requests(segments)
        text_reqs = [r for r in requests if "updateTextStyle" in r]
        assert len(text_reqs) == 1
        style = text_reqs[0]["updateTextStyle"]
        assert style["textStyle"]["bold"] is True
        assert style["fields"] == "bold"

    def test_italic_generates_text_style(self):
        segments = [_Segment("Italic\n", italic=True)]
        requests = _segments_to_requests(segments)
        text_reqs = [r for r in requests if "updateTextStyle" in r]
        style = text_reqs[0]["updateTextStyle"]
        assert style["textStyle"]["italic"] is True
        assert style["fields"] == "italic"

    def test_color_generates_foreground_color(self):
        segments = [_Segment("Red\n", color=(0.8, 0.0, 0.0))]
        requests = _segments_to_requests(segments)
        text_reqs = [r for r in requests if "updateTextStyle" in r]
        rgb = text_reqs[0]["updateTextStyle"]["textStyle"]["foregroundColor"]["color"][
            "rgbColor"
        ]
        assert rgb == {"red": 0.8, "green": 0.0, "blue": 0.0}

    def test_combined_styles_in_single_request(self):
        segments = [_Segment("Styled\n", bold=True, color=(0.5, 0.5, 0.5))]
        requests = _segments_to_requests(segments)
        text_reqs = [r for r in requests if "updateTextStyle" in r]
        assert len(text_reqs) == 1
        style = text_reqs[0]["updateTextStyle"]
        assert style["textStyle"]["bold"] is True
        assert "foregroundColor" in style["textStyle"]
        assert "bold" in style["fields"]
        assert "foregroundColor" in style["fields"]

    def test_plain_segment_no_style_requests(self):
        segments = [_Segment("Plain text\n")]
        requests = _segments_to_requests(segments)
        assert len(requests) == 1  # Only insertText

    def test_index_tracking_across_segments(self):
        segments = [
            _Segment("AAAA\n", heading=1),  # 5 chars, indices 1-5
            _Segment("BB\n", bold=True),  # 3 chars, indices 6-8
        ]
        requests = _segments_to_requests(segments)
        para_req = next(r for r in requests if "updateParagraphStyle" in r)
        assert para_req["updateParagraphStyle"]["range"] == {
            "startIndex": 1,
            "endIndex": 6,
        }
        text_req = next(r for r in requests if "updateTextStyle" in r)
        assert text_req["updateTextStyle"]["range"] == {
            "startIndex": 6,
            "endIndex": 9,
        }


# ── Populate Deal Analysis (integration) ─────────────────────────


class TestPopulateDealAnalysis:
    """Tests for populate_deal_analysis end-to-end."""

    def test_calls_batch_update_with_doc_id(self, docs_client, deal_content):
        populate_deal_analysis(docs_client, "doc_abc", deal_content)

        mock_docs = docs_client._mock_docs_service
        mock_docs.documents.return_value.batchUpdate.assert_called_once()
        call_kwargs = mock_docs.documents.return_value.batchUpdate.call_args[1]
        assert call_kwargs["documentId"] == "doc_abc"

    def test_batch_update_body_has_requests(self, docs_client, deal_content):
        populate_deal_analysis(docs_client, "doc_abc", deal_content)

        call_kwargs = (
            docs_client._mock_docs_service.documents.return_value.batchUpdate.call_args[
                1
            ]
        )
        requests = call_kwargs["body"]["requests"]
        assert len(requests) > 0
        assert "insertText" in requests[0]

    def test_inserted_text_contains_all_sections(self, docs_client, deal_content):
        populate_deal_analysis(docs_client, "doc_abc", deal_content)

        call_kwargs = (
            docs_client._mock_docs_service.documents.return_value.batchUpdate.call_args[
                1
            ]
        )
        inserted = call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "1. Opportunity Snapshot" in inserted
        assert "2. Problem & Impact" in inserted
        assert "3. Current vs Desired State" in inserted
        assert "4. Buying Dynamics & Risk" in inserted
        assert "5. Renessai Fit & Strategy" in inserted
        assert "6. Proof & Next Actions" in inserted
        assert FOOTER_TEXT in inserted

    def test_inserted_text_contains_content_values(self, docs_client, deal_content):
        populate_deal_analysis(docs_client, "doc_abc", deal_content)

        call_kwargs = (
            docs_client._mock_docs_service.documents.return_value.batchUpdate.call_args[
                1
            ]
        )
        inserted = call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "Acme Corp" in inserted
        assert "Legacy ERP system" in inserted
        assert "Schedule technical deep-dive" in inserted

    def test_missing_info_appears_in_output(
        self, docs_client, deal_content, missing_info
    ):
        populate_deal_analysis(docs_client, "doc_abc", deal_content, missing_info)

        call_kwargs = (
            docs_client._mock_docs_service.documents.return_value.batchUpdate.call_args[
                1
            ]
        )
        inserted = call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "Missing Information" in inserted
        assert "Budget range" in inserted

    def test_no_missing_info_omits_warning(self, docs_client, deal_content):
        populate_deal_analysis(docs_client, "doc_abc", deal_content)

        call_kwargs = (
            docs_client._mock_docs_service.documents.return_value.batchUpdate.call_args[
                1
            ]
        )
        inserted = call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "Missing Information" not in inserted

    def test_empty_content_uses_unknown_defaults(self, docs_client):
        populate_deal_analysis(docs_client, "doc_abc", {})

        call_kwargs = (
            docs_client._mock_docs_service.documents.return_value.batchUpdate.call_args[
                1
            ]
        )
        inserted = call_kwargs["body"]["requests"][0]["insertText"]["text"]
        assert "Unknown" in inserted

    def test_requests_include_formatting(self, docs_client, deal_content):
        populate_deal_analysis(docs_client, "doc_abc", deal_content)

        call_kwargs = (
            docs_client._mock_docs_service.documents.return_value.batchUpdate.call_args[
                1
            ]
        )
        requests = call_kwargs["body"]["requests"]
        has_paragraph = any("updateParagraphStyle" in r for r in requests)
        has_text_style = any("updateTextStyle" in r for r in requests)
        assert has_paragraph
        assert has_text_style
