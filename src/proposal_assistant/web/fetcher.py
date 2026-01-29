"""Web content fetcher with retry logic."""

import logging
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class WebFetcher:
    """Fetch web content with retry and parallel fetching support.

    Attributes:
        MAX_RETRIES: Maximum number of retry attempts per URL.
        BACKOFF_SECONDS: Sleep durations between retries.
        TIMEOUT: Request timeout in seconds.
        USER_AGENT: User agent string for requests.
    """

    MAX_RETRIES: int = 3
    BACKOFF_SECONDS: list[float] = [1.0, 2.0]
    TIMEOUT: int = 30
    USER_AGENT: str = "ProposalAssistant/1.0"

    def fetch_url(self, url: str) -> str | None:
        """Fetch content from a URL with retry logic.

        Args:
            url: The URL to fetch content from.

        Returns:
            The page content as a string, or None if all retries failed.
        """
        last_error: Exception | None = None

        for attempt in range(self.MAX_RETRIES):
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": self.USER_AGENT},
                )
                with urllib.request.urlopen(req, timeout=self.TIMEOUT) as response:
                    content = response.read()
                    charset = response.headers.get_content_charset() or "utf-8"
                    decoded = content.decode(charset, errors="replace")

                logger.info("Fetched %s (attempt %d)", url, attempt + 1)
                return decoded

            except urllib.error.HTTPError as e:
                last_error = e
                logger.warning(
                    "HTTP error fetching %s (attempt %d/%d): %s %s",
                    url,
                    attempt + 1,
                    self.MAX_RETRIES,
                    e.code,
                    e.reason,
                )
                # Don't retry client errors (4xx)
                if 400 <= e.code < 500:
                    break

            except urllib.error.URLError as e:
                last_error = e
                logger.warning(
                    "URL error fetching %s (attempt %d/%d): %s",
                    url,
                    attempt + 1,
                    self.MAX_RETRIES,
                    e.reason,
                )

            except Exception as e:
                last_error = e
                logger.warning(
                    "Error fetching %s (attempt %d/%d): %s",
                    url,
                    attempt + 1,
                    self.MAX_RETRIES,
                    e,
                )

            # Sleep before next retry (if not last attempt)
            if attempt < self.MAX_RETRIES - 1:
                sleep_time = self.BACKOFF_SECONDS[attempt]
                time.sleep(sleep_time)

        logger.error("Failed to fetch %s after %d attempts: %s", url, self.MAX_RETRIES, last_error)
        return None

    def fetch_multiple(
        self,
        urls: list[str],
        max_workers: int = 5,
    ) -> list[tuple[str, str | None]]:
        """Fetch multiple URLs in parallel.

        Args:
            urls: List of URLs to fetch.
            max_workers: Maximum number of parallel workers.

        Returns:
            List of (url, content) tuples in the same order as input.
            Content is None if fetch failed.
        """
        if not urls:
            return []

        results: dict[str, str | None] = {}

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_url = {
                executor.submit(self.fetch_url, url): url for url in urls
            }

            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    results[url] = future.result()
                except Exception as e:
                    logger.error("Unexpected error fetching %s: %s", url, e)
                    results[url] = None

        # Return in original order
        return [(url, results.get(url)) for url in urls]
