from __future__ import annotations

from dataclasses import dataclass

import requests

from src.news.feed_parser import MAX_FEED_BYTES

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_USER_AGENT = "CVMAnalytics News/0.1"
FETCH_CHUNK_SIZE = 64 * 1024


@dataclass(frozen=True)
class FeedFetchResult:
    status: str
    payload: bytes = b""
    http_status: int | None = None
    final_url: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    error_message: str | None = None


class NewsFeedFetcher:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = MAX_FEED_BYTES,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes
        self.user_agent = user_agent

    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FeedFetchResult:
        headers = {
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
            "User-Agent": self.user_agent,
        }
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        try:
            response = self.session.get(
                url,
                headers=headers,
                timeout=self.timeout_seconds,
                stream=True,
                allow_redirects=True,
            )
        except requests.Timeout:
            return FeedFetchResult(status="error", error_message="Feed request timed out")
        except requests.RequestException as exc:
            return FeedFetchResult(status="error", error_message=f"Feed request failed: {exc}")

        result_headers = getattr(response, "headers", {}) or {}
        final_url = getattr(response, "url", url)
        http_status = int(getattr(response, "status_code", 0) or 0)
        result_etag = result_headers.get("ETag")
        result_last_modified = result_headers.get("Last-Modified")

        if http_status == 304:
            return FeedFetchResult(
                status="not_modified",
                http_status=http_status,
                final_url=final_url,
                etag=result_etag,
                last_modified=result_last_modified,
            )
        if http_status < 200 or http_status >= 300:
            return FeedFetchResult(
                status="error",
                http_status=http_status,
                final_url=final_url,
                etag=result_etag,
                last_modified=result_last_modified,
                error_message=f"Feed request returned HTTP {http_status}",
            )

        payload = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=FETCH_CHUNK_SIZE):
                if not chunk:
                    continue
                payload.extend(chunk)
                if len(payload) > self.max_bytes:
                    return FeedFetchResult(
                        status="error",
                        http_status=http_status,
                        final_url=final_url,
                        etag=result_etag,
                        last_modified=result_last_modified,
                        error_message=f"Feed payload exceeds {self.max_bytes} bytes",
                    )
        except requests.RequestException as exc:
            return FeedFetchResult(
                status="error",
                http_status=http_status,
                final_url=final_url,
                etag=result_etag,
                last_modified=result_last_modified,
                error_message=f"Feed response read failed: {exc}",
            )

        return FeedFetchResult(
            status="success",
            payload=bytes(payload),
            http_status=http_status,
            final_url=final_url,
            etag=result_etag,
            last_modified=result_last_modified,
        )
