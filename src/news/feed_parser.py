from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin
import re
import xml.etree.ElementTree as ET


MAX_FEED_BYTES = 2_000_000


class NewsFeedParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedFeedEntry:
    title: str
    url: str
    source_item_id: str | None
    published_at: str | None
    summary: str | None
    language: str | None = None


@dataclass(frozen=True)
class ParsedFeed:
    title: str | None
    language: str | None
    entries: tuple[ParsedFeedEntry, ...]


def parse_feed_bytes(payload: bytes, *, feed_url: str) -> ParsedFeed:
    if len(payload) > MAX_FEED_BYTES:
        raise NewsFeedParseError(f"Feed payload exceeds {MAX_FEED_BYTES} bytes")
    text = payload.decode("utf-8-sig", errors="replace")
    if re.search(r"<!DOCTYPE|<!ENTITY", text, flags=re.IGNORECASE):
        raise NewsFeedParseError("Feed XML contains unsupported DTD/entity declarations")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise NewsFeedParseError(f"Malformed feed XML: {exc}") from exc

    root_name = _local_name(root.tag)
    if root_name == "rss":
        return _parse_rss(root, feed_url=feed_url)
    if root_name == "feed":
        return _parse_atom(root, feed_url=feed_url)
    if root_name == "RDF":
        return _parse_rdf(root, feed_url=feed_url)
    raise NewsFeedParseError(f"Unsupported feed root: {root_name}")


def _parse_rss(root: ET.Element, *, feed_url: str) -> ParsedFeed:
    channel = _first_child(root, "channel")
    if channel is None:
        raise NewsFeedParseError("RSS feed is missing channel")
    feed_title = _child_text(channel, "title")
    language = _child_text(channel, "language")
    entries: list[ParsedFeedEntry] = []
    for item in _children(channel, "item"):
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        if not title or not link:
            continue
        entries.append(
            ParsedFeedEntry(
                title=title,
                url=urljoin(feed_url, link),
                source_item_id=_child_text(item, "guid"),
                published_at=_parse_date(_child_text(item, "pubDate") or _child_text(item, "dc:date")),
                summary=_child_text(item, "description"),
                language=language,
            )
        )
    return ParsedFeed(title=feed_title, language=language, entries=tuple(entries))


def _parse_atom(root: ET.Element, *, feed_url: str) -> ParsedFeed:
    feed_title = _child_text(root, "title")
    language = root.attrib.get("{http://www.w3.org/XML/1998/namespace}lang") or root.attrib.get("lang")
    entries: list[ParsedFeedEntry] = []
    for entry in _children(root, "entry"):
        title = _child_text(entry, "title")
        link = _atom_link(entry)
        if not title or not link:
            continue
        entry_language = (
            entry.attrib.get("{http://www.w3.org/XML/1998/namespace}lang")
            or entry.attrib.get("lang")
            or language
        )
        entries.append(
            ParsedFeedEntry(
                title=title,
                url=urljoin(feed_url, link),
                source_item_id=_child_text(entry, "id"),
                published_at=_parse_date(_child_text(entry, "published") or _child_text(entry, "updated")),
                summary=_child_text(entry, "summary") or _child_text(entry, "content"),
                language=entry_language,
            )
        )
    return ParsedFeed(title=feed_title, language=language, entries=tuple(entries))


def _parse_rdf(root: ET.Element, *, feed_url: str) -> ParsedFeed:
    channel = _first_child(root, "channel")
    feed_title = _child_text(channel, "title") if channel is not None else None
    language = _child_text(channel, "language") if channel is not None else None
    entries: list[ParsedFeedEntry] = []
    for item in _children(root, "item"):
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        if not title or not link:
            continue
        entries.append(
            ParsedFeedEntry(
                title=title,
                url=urljoin(feed_url, link),
                source_item_id=item.attrib.get("{http://www.w3.org/1999/02/22-rdf-syntax-ns#}about") or link,
                published_at=_parse_date(_child_text(item, "date")),
                summary=_child_text(item, "description"),
                language=language,
            )
        )
    return ParsedFeed(title=feed_title, language=language, entries=tuple(entries))


def _atom_link(entry: ET.Element) -> str | None:
    fallback: str | None = None
    for child in entry:
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href") or "").strip()
        if not href:
            continue
        rel = str(child.attrib.get("rel") or "alternate").strip().lower()
        if rel == "alternate":
            return href
        fallback = fallback or href
    return fallback


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    raw = value.strip()
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":", 1)[-1]


def _children(node: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in node if _local_name(child.tag) == name.split(":", 1)[-1]]


def _first_child(node: ET.Element, name: str) -> ET.Element | None:
    for child in _children(node, name):
        return child
    return None


def _child_text(node: ET.Element, name: str) -> str | None:
    child = _first_child(node, name)
    if child is None:
        return None
    text = "".join(child.itertext()).strip()
    return text or None
