"""Unit tests for WebFetcher."""

import socket
import urllib.error
from unittest.mock import MagicMock, patch

import pytest

from proposal_assistant.web.fetcher import WebFetcher


class TestFetchUrl:
    """Tests for WebFetcher.fetch_url method."""

    def test_returns_content_on_success(self):
        """Returns decoded content on successful fetch."""
        fetcher = WebFetcher()

        with patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"<html>Test content</html>"
            mock_response.headers.get_content_charset.return_value = "utf-8"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            result = fetcher.fetch_url("https://example.com")

        assert result == "<html>Test content</html>"

    def test_decodes_with_response_charset(self):
        """Uses charset from response headers."""
        fetcher = WebFetcher()

        with patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = "Héllo".encode("iso-8859-1")
            mock_response.headers.get_content_charset.return_value = "iso-8859-1"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            result = fetcher.fetch_url("https://example.com")

        assert result == "Héllo"

    def test_defaults_to_utf8_when_no_charset(self):
        """Defaults to UTF-8 when no charset in response."""
        fetcher = WebFetcher()

        with patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen:
            mock_response = MagicMock()
            mock_response.read.return_value = b"Test content"
            mock_response.headers.get_content_charset.return_value = None
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)
            urlopen.return_value = mock_response

            result = fetcher.fetch_url("https://example.com")

        assert result == "Test content"

    def test_retries_on_server_error(self):
        """Retries on 5xx server errors."""
        fetcher = WebFetcher()

        with (
            patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.web.fetcher.time.sleep"),
        ):
            # First two calls fail, third succeeds
            error = urllib.error.HTTPError(
                "https://example.com", 500, "Server Error", {}, None
            )
            mock_response = MagicMock()
            mock_response.read.return_value = b"Success"
            mock_response.headers.get_content_charset.return_value = "utf-8"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            urlopen.side_effect = [error, error, mock_response]

            result = fetcher.fetch_url("https://example.com")

        assert result == "Success"
        assert urlopen.call_count == 3

    def test_no_retry_on_client_error(self):
        """Does not retry on 4xx client errors."""
        fetcher = WebFetcher()

        with (
            patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.web.fetcher.time.sleep"),
        ):
            error = urllib.error.HTTPError(
                "https://example.com", 404, "Not Found", {}, None
            )
            urlopen.side_effect = error

            result = fetcher.fetch_url("https://example.com")

        assert result is None
        assert urlopen.call_count == 1

    def test_returns_none_after_max_retries(self):
        """Returns None when all retries exhausted."""
        fetcher = WebFetcher()

        with (
            patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.web.fetcher.time.sleep"),
        ):
            error = urllib.error.URLError("Connection refused")
            urlopen.side_effect = error

            result = fetcher.fetch_url("https://example.com")

        assert result is None
        assert urlopen.call_count == 3

    def test_handles_url_error(self):
        """Handles URLError and retries."""
        fetcher = WebFetcher()

        with (
            patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.web.fetcher.time.sleep"),
        ):
            error = urllib.error.URLError("DNS lookup failed")
            mock_response = MagicMock()
            mock_response.read.return_value = b"Content"
            mock_response.headers.get_content_charset.return_value = "utf-8"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            urlopen.side_effect = [error, mock_response]

            result = fetcher.fetch_url("https://example.com")

        assert result == "Content"
        assert urlopen.call_count == 2

    def test_handles_timeout_and_retries(self):
        """Handles socket timeout and retries."""
        fetcher = WebFetcher()

        with (
            patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.web.fetcher.time.sleep"),
        ):
            # Socket timeout is wrapped in URLError
            timeout_error = urllib.error.URLError(socket.timeout("timed out"))
            mock_response = MagicMock()
            mock_response.read.return_value = b"Content after timeout"
            mock_response.headers.get_content_charset.return_value = "utf-8"
            mock_response.__enter__ = MagicMock(return_value=mock_response)
            mock_response.__exit__ = MagicMock(return_value=False)

            urlopen.side_effect = [timeout_error, mock_response]

            result = fetcher.fetch_url("https://example.com")

        assert result == "Content after timeout"
        assert urlopen.call_count == 2

    def test_returns_none_after_repeated_timeouts(self):
        """Returns None when all retries timeout."""
        fetcher = WebFetcher()

        with (
            patch("proposal_assistant.web.fetcher.urllib.request.urlopen") as urlopen,
            patch("proposal_assistant.web.fetcher.time.sleep"),
        ):
            timeout_error = urllib.error.URLError(socket.timeout("timed out"))
            urlopen.side_effect = timeout_error

            result = fetcher.fetch_url("https://example.com")

        assert result is None
        assert urlopen.call_count == 3


class TestFetchMultiple:
    """Tests for WebFetcher.fetch_multiple method."""

    def test_returns_empty_list_for_empty_input(self):
        """Returns empty list when no URLs provided."""
        fetcher = WebFetcher()
        result = fetcher.fetch_multiple([])
        assert result == []

    def test_fetches_all_urls(self):
        """Fetches all URLs and returns results."""
        fetcher = WebFetcher()

        with patch.object(fetcher, "fetch_url") as mock_fetch:
            mock_fetch.side_effect = ["Content 1", "Content 2", "Content 3"]

            result = fetcher.fetch_multiple([
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
            ])

        assert len(result) == 3
        urls = [r[0] for r in result]
        assert "https://example.com/1" in urls
        assert "https://example.com/2" in urls
        assert "https://example.com/3" in urls

    def test_preserves_url_order(self):
        """Results are returned in same order as input URLs."""
        fetcher = WebFetcher()

        with patch.object(fetcher, "fetch_url") as mock_fetch:
            # Map URLs to content
            content_map = {
                "https://example.com/a": "A",
                "https://example.com/b": "B",
                "https://example.com/c": "C",
            }
            mock_fetch.side_effect = lambda url: content_map[url]

            urls = [
                "https://example.com/a",
                "https://example.com/b",
                "https://example.com/c",
            ]
            result = fetcher.fetch_multiple(urls)

        assert result == [
            ("https://example.com/a", "A"),
            ("https://example.com/b", "B"),
            ("https://example.com/c", "C"),
        ]

    def test_handles_mixed_success_and_failure(self):
        """Handles mix of successful and failed fetches."""
        fetcher = WebFetcher()

        with patch.object(fetcher, "fetch_url") as mock_fetch:
            # Use URL-based mapping since parallel execution order varies
            content_map = {
                "https://example.com/1": "Content 1",
                "https://example.com/2": None,
                "https://example.com/3": "Content 3",
            }
            mock_fetch.side_effect = lambda url: content_map[url]

            result = fetcher.fetch_multiple([
                "https://example.com/1",
                "https://example.com/2",
                "https://example.com/3",
            ])

        assert result[0] == ("https://example.com/1", "Content 1")
        assert result[1] == ("https://example.com/2", None)
        assert result[2] == ("https://example.com/3", "Content 3")

    def test_handles_exception_in_future(self):
        """Handles unexpected exception from fetch."""
        fetcher = WebFetcher()

        with patch.object(fetcher, "fetch_url") as mock_fetch:
            mock_fetch.side_effect = [RuntimeError("Unexpected"), "Content 2"]

            result = fetcher.fetch_multiple([
                "https://example.com/1",
                "https://example.com/2",
            ])

        # First URL should have None due to exception
        result_dict = dict(result)
        assert result_dict["https://example.com/1"] is None
        assert result_dict["https://example.com/2"] == "Content 2"
