from __future__ import annotations

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib import import_module
from urllib.parse import quote, urlsplit

import requests

from src.news.feed_parser import MAX_FEED_BYTES

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_USER_AGENT = "CVMAnalytics News/0.1"
FETCH_CHUNK_SIZE = 64 * 1024
MAX_ARTICLE_BYTES = 768 * 1024
MIN_EXTRACTED_TEXT_CHARS = 240


@dataclass(frozen=True)
class FeedFetchResult:
    status: str
    payload: bytes = b""
    http_status: int | None = None
    final_url: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class UrlResolutionResult:
    status: str
    original_url: str
    final_url: str | None = None
    http_status: int | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class ArticleTextFetchResult:
    status: str
    final_url: str | None = None
    http_status: int | None = None
    content_text: str | None = None
    content_format: str | None = None
    storage_policy: str | None = None
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

    def resolve_url(self, url: str) -> UrlResolutionResult:
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.5",
            "User-Agent": self.user_agent,
        }
        try:
            response = self.session.head(
                url,
                headers=headers,
                timeout=min(self.timeout_seconds, 8),
                allow_redirects=True,
            )
            http_status = int(getattr(response, "status_code", 0) or 0)
            if http_status in {405, 403} or http_status < 200 or http_status >= 400:
                response = self.session.get(
                    url,
                    headers={**headers, "Range": "bytes=0-0"},
                    timeout=min(self.timeout_seconds, 8),
                    stream=True,
                    allow_redirects=True,
                )
                http_status = int(getattr(response, "status_code", 0) or 0)
            final_url = str(getattr(response, "url", url) or url)
            if http_status < 200 or http_status >= 400:
                return UrlResolutionResult(
                    status="error",
                    original_url=url,
                    final_url=final_url,
                    http_status=http_status,
                    error_message=f"URL resolution returned HTTP {http_status}",
                )
            if _is_google_news_url(final_url):
                decoded_url = self._resolve_google_news_url(final_url)
                if decoded_url:
                    return UrlResolutionResult(
                        status="success",
                        original_url=url,
                        final_url=decoded_url,
                        http_status=http_status,
                    )
            return UrlResolutionResult(
                status="success",
                original_url=url,
                final_url=final_url,
                http_status=http_status,
            )
        except requests.Timeout:
            return UrlResolutionResult(status="error", original_url=url, error_message="URL resolution timed out")
        except requests.RequestException as exc:
            return UrlResolutionResult(status="error", original_url=url, error_message=f"URL resolution failed: {exc}")

    def _resolve_google_news_url(self, url: str) -> str | None:
        article_id = _google_news_article_id(url)
        if not article_id:
            return None
        headers = {
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.5",
            "User-Agent": self.user_agent,
            "Referer": "https://news.google.com/",
        }
        try:
            response = self.session.get(
                url,
                headers=headers,
                timeout=min(self.timeout_seconds, 8),
                allow_redirects=True,
            )
            if int(getattr(response, "status_code", 0) or 0) >= 400:
                return None
            html = getattr(response, "text", None)
            if html is None:
                payload = b"".join(response.iter_content(chunk_size=FETCH_CHUNK_SIZE))
                html = payload.decode(getattr(response, "encoding", None) or "utf-8", errors="replace")
            timestamp = _first_regex_group(r'data-n-a-ts="(\d+)"', html)
            signature = _first_regex_group(r'data-n-a-sg="([^"]+)"', html)
            if not timestamp or not signature:
                return None
            request_payload = [
                [
                    [
                        "Fbv4je",
                        (
                            '["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
                            'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
                            f'"{article_id}",{timestamp},"{signature}"]'
                        ),
                    ]
                ]
            ]
            batch_response = self.session.post(
                "https://news.google.com/_/DotsSplashUi/data/batchexecute",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                    "User-Agent": self.user_agent,
                    "Referer": "https://news.google.com/",
                },
                data="f.req=" + quote(json.dumps(request_payload)),
                timeout=min(self.timeout_seconds, 8),
            )
            if int(getattr(batch_response, "status_code", 0) or 0) >= 400:
                return None
            return _extract_google_batch_url(getattr(batch_response, "text", ""))
        except requests.RequestException:
            return None

    def fetch_article_text(self, url: str) -> ArticleTextFetchResult:
        headers = {
            "Accept": "text/html,application/xhtml+xml;q=0.9,text/plain;q=0.8,*/*;q=0.3",
            "User-Agent": self.user_agent,
        }
        try:
            response = self.session.get(
                url,
                headers=headers,
                timeout=min(self.timeout_seconds, 12),
                stream=True,
                allow_redirects=True,
            )
        except requests.Timeout:
            return ArticleTextFetchResult(status="error", error_message="Article request timed out")
        except requests.RequestException as exc:
            return ArticleTextFetchResult(status="error", error_message=f"Article request failed: {exc}")

        final_url = str(getattr(response, "url", url) or url)
        http_status = int(getattr(response, "status_code", 0) or 0)
        headers_obj = getattr(response, "headers", {}) or {}
        content_type = str(headers_obj.get("Content-Type") or "").lower()

        if http_status in {401, 402, 403, 451}:
            return ArticleTextFetchResult(
                status="paywalled",
                final_url=final_url,
                http_status=http_status,
                error_message=f"Article request returned HTTP {http_status}",
            )
        if http_status < 200 or http_status >= 300:
            return ArticleTextFetchResult(
                status="error",
                final_url=final_url,
                http_status=http_status,
                error_message=f"Article request returned HTTP {http_status}",
            )
        if content_type and not any(token in content_type for token in ("html", "text/plain", "xhtml")):
            return ArticleTextFetchResult(
                status="unsupported",
                final_url=final_url,
                http_status=http_status,
                error_message=f"Unsupported article content type: {content_type}",
            )

        payload = bytearray()
        try:
            for chunk in response.iter_content(chunk_size=FETCH_CHUNK_SIZE):
                if not chunk:
                    continue
                payload.extend(chunk)
                if len(payload) > MAX_ARTICLE_BYTES:
                    return ArticleTextFetchResult(
                        status="error",
                        final_url=final_url,
                        http_status=http_status,
                        error_message=f"Article payload exceeds {MAX_ARTICLE_BYTES} bytes",
                    )
        except requests.RequestException as exc:
            return ArticleTextFetchResult(
                status="error",
                final_url=final_url,
                http_status=http_status,
                error_message=f"Article response read failed: {exc}",
            )

        encoding = getattr(response, "encoding", None) or "utf-8"
        html = bytes(payload).decode(encoding, errors="replace")
        if _looks_paywalled(html):
            return ArticleTextFetchResult(
                status="paywalled",
                final_url=final_url,
                http_status=http_status,
                error_message="Article appears to be paywalled",
            )
        text_value, extraction_method = _extract_article_text(html, final_url)
        if len(text_value) < MIN_EXTRACTED_TEXT_CHARS:
            return ArticleTextFetchResult(
                status="unavailable",
                final_url=final_url,
                http_status=http_status,
                error_message="Article text was not available in the fetched page",
            )
        return ArticleTextFetchResult(
            status="success",
            final_url=final_url,
            http_status=http_status,
            content_text=text_value,
            content_format="text",
            storage_policy=f"{extraction_method}_original_page_text_allowed",
        )


class _ReadableTextParser(HTMLParser):
    block_tags = {
        "article", "p", "div", "section", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
        "blockquote",
    }
    ignored_tags = {"script", "style", "noscript", "svg", "canvas", "iframe", "form", "nav", "footer", "header"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self.ignored_tags:
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.ignored_tags and self._ignored_depth:
            self._ignored_depth -= 1
            return
        if self._ignored_depth:
            return
        if tag in self.block_tags:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        value = " ".join(str(data or "").split())
        if value:
            self.parts.append(value)

    def text(self) -> str:
        lines: list[str] = []
        for raw_line in "".join(self.parts).splitlines():
            line = " ".join(raw_line.split())
            if not line:
                continue
            lowered = line.lower()
            if lowered in {"publicidade", "advertisement", "continua após publicidade"}:
                continue
            lines.append(line)
        return "\n\n".join(_dedupe_adjacent_lines(lines)).strip()


def _extract_article_text(html: str, url: str | None = None) -> tuple[str, str]:
    trafilatura_text = _extract_with_trafilatura(html, url)
    if len(trafilatura_text) >= MIN_EXTRACTED_TEXT_CHARS:
        return trafilatura_text, "trafilatura"
    return _extract_readable_text(html), "fallback"


def _extract_with_trafilatura(html: str, url: str | None = None) -> str:
    try:
        trafilatura = import_module("trafilatura")
        extracted = trafilatura.extract(
            html,
            url=url,
            output_format="txt",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
        )
    except Exception:
        return ""
    return _normalize_extracted_text(str(extracted or ""))


def _extract_readable_text(html: str) -> str:
    parser = _ReadableTextParser()
    parser.feed(html)
    return _normalize_extracted_text(parser.text())


def _normalize_extracted_text(value: str) -> str:
    lines: list[str] = []
    for raw_line in str(value or "").splitlines():
        line = " ".join(raw_line.split())
        if line:
            lines.append(line)
    return "\n\n".join(_dedupe_adjacent_lines(lines)).strip()


def _dedupe_adjacent_lines(lines: list[str]) -> list[str]:
    result: list[str] = []
    previous = ""
    for line in lines:
        if line == previous:
            continue
        result.append(line)
        previous = line
    return result


def _looks_paywalled(html: str) -> bool:
    lowered = html.lower()
    markers = (
        "paywall",
        "assinante",
        "assine para continuar",
        "subscribe to continue",
        "sign in to continue",
        "faça login para continuar",
        "conteúdo exclusivo para assinantes",
    )
    return any(marker in lowered for marker in markers)


def _is_google_news_url(url: str) -> bool:
    parsed = urlsplit(str(url or ""))
    return parsed.netloc.lower() == "news.google.com"


def _google_news_article_id(url: str) -> str | None:
    parsed = urlsplit(str(url or ""))
    if parsed.netloc.lower() != "news.google.com":
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[-2] == "articles":
        return parts[-1]
    return None


def _first_regex_group(pattern: str, value: str) -> str | None:
    match = re.search(pattern, value)
    return match.group(1) if match else None


def _extract_google_batch_url(value: str) -> str | None:
    try:
        payload = json.loads(value.split("\n\n", 1)[1])
    except Exception:
        return None
    for item in payload:
        if not isinstance(item, list) or len(item) < 3 or item[0] != "wrb.fr":
            continue
        try:
            decoded = json.loads(item[2])
        except Exception:
            continue
        if isinstance(decoded, list) and len(decoded) >= 2 and decoded[0] == "garturlres":
            url = str(decoded[1] or "").strip()
            if url and not _is_google_news_url(url):
                return url
    return None
