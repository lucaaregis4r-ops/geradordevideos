"""Bounded Mixkit discovery; resolve individual licensed items, never crawl a catalog."""
from __future__ import annotations

import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from threading import Lock
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests

from app.services.media_ranker.schemas import MediaCandidate
from .base import MediaSourceProvider, ProviderCapabilities


class PageMetadata(HTMLParser):
    def __init__(self, html: str):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self.licenses: set[str] = set()
        self.documents: list[dict] = []
        self.modals: list[str] = []
        self.downloads: list[str] = []
        self._link = None
        self._script = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and "item-grid-video-player__overlay-link" in a.get("class", ""):
            self._link = [a.get("href", ""), ""]
        if a.get("data-license"):
            self.licenses.add(a["data-license"])
        if a.get("data-download--button-modal-url-value"):
            self.modals.append(a["data-download--button-modal-url-value"])
        if tag == "input" and a.get("data-download--video-options-target") == "downloadOption":
            self.modals.append(a.get("value", ""))
        if a.get("data-download--modal-url-value"):
            self.downloads.append(a["data-download--modal-url-value"])
        if tag == "a" and ".mp4" in a.get("href", ""):
            self.downloads.append(a["href"])
        if tag == "script" and a.get("type") == "application/ld+json":
            self._script = ""

    def handle_data(self, data):
        if self._link is not None:
            self._link[1] += data
        if self._script is not None:
            self._script += data

    def handle_endtag(self, tag):
        if tag == "a" and self._link is not None:
            self.links.append((self._link[0], " ".join(self._link[1].split())))
            self._link = None
        if tag == "script" and self._script is not None:
            try:
                doc = json.loads(self._script)
                nodes = doc if isinstance(doc, list) else doc.get("@graph", [doc])
                self.documents.extend(n for n in nodes if isinstance(n, dict))
            except (ValueError, AttributeError):
                pass
            self._script = None


class MixkitProvider(MediaSourceProvider):
    name = "mixkit"
    capabilities = ProviderCapabilities(("video",))
    origin = "https://mixkit.co"
    user_agent = "FabricaDeShorts/3.1 (+https://github.com/lucaaregis4r-ops/geradordevideos)"
    _lock = Lock()
    _last_request = 0.0

    def __init__(self, cache_dir: str | Path = "storage/media_cache/provider_pages"):
        self.cache_dir = Path(cache_dir)
        self._robots = None

    def is_available(self):
        return True

    def _request(self, url: str) -> str:
        for _ in range(3):
            parsed = urlparse(url)
            if parsed.scheme != "https" or parsed.netloc != "mixkit.co":
                raise ValueError("unsupported_mixkit_page")
            if self._robots and not self._robots.can_fetch(self.user_agent, url):
                raise ValueError("robots_disallowed")
            # One connection at a time, including same-origin redirects.
            with self._lock:
                time.sleep(max(0, 1 - (time.monotonic() - type(self)._last_request)))
                type(self)._last_request = time.monotonic()
                with requests.get(url, headers={"User-Agent": self.user_agent},
                                  timeout=(3, 8), stream=True, allow_redirects=False) as response:
                    response.raise_for_status()
                    if response.is_redirect:
                        url = urljoin(url, response.headers["Location"])
                        continue
                    chunks = []
                    size = 0
                    for chunk in response.iter_content(65536):
                        size += len(chunk)
                        if size > 2_000_000:
                            raise ValueError("mixkit_page_too_large")
                        chunks.append(chunk)
                    return b"".join(chunks).decode("utf-8", errors="replace")
        raise ValueError("mixkit_too_many_redirects")

    def _page(self, url: str) -> str:
        if self._robots is None:
            robots = RobotFileParser()
            robots.parse(self._request(self.origin + "/robots.txt").splitlines())
            self._robots = robots
        if not self._robots.can_fetch(self.user_agent, url):
            raise ValueError("robots_disallowed")
        key = hashlib.sha256(url.encode()).hexdigest()
        path = self.cache_dir / f"mixkit-{key}.html"
        if path.is_file() and time.time() - path.stat().st_mtime < 86400:
            return path.read_text(encoding="utf-8")
        html = self._request(url)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return html

    def search(self, query, media_type="video", aspect="portrait", limit=5):
        if media_type != "video" or limit <= 0:
            return []
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")
        if not slug:
            return []
        page = PageMetadata(self._page(f"{self.origin}/free-stock-video/discover/{slug}/"))
        candidates = []
        seen = set()
        for href, title in page.links:
            match = re.fullmatch(r"/free-stock-video/[a-z0-9-]+-(\d+)/", href)
            if not match or href in seen:
                continue
            seen.add(href)
            asset_id = match[1]
            candidates.append(MediaCandidate(
                provider=self.name, provider_asset_id=asset_id, asset_id=f"mixkit_{asset_id}",
                query=query, description=title, source_page=urljoin(self.origin, href),
                # Page URL is deliberately resolved before any media download.
                url=urljoin(self.origin, href), media_type="video",
            ))
            if len(candidates) >= min(max(limit, 0), 5):
                break
        return candidates

    def resolve_candidate(self, candidate: MediaCandidate) -> MediaCandidate:
        page = PageMetadata(self._page(candidate.source_page))
        videos = [n for n in page.documents if n.get("@type") == "VideoObject"]
        if not videos:
            raise ValueError("mixkit_missing_video_metadata")
        video = videos[0]
        # Some pages incorrectly label JSON-LD license as Free while the visible
        # license and copyrightNotice say Restricted. The restrictive signal wins.
        if ("videoRestricted" in page.licenses or "restricted" in str(video.get("copyrightNotice", "")).lower()
                or "videoFree" not in page.licenses):
            candidate.rights_status = "blocked_for_this_use"
            raise ValueError("mixkit_restricted_or_unconfirmed_license")
        urls = page.downloads
        if not urls and page.modals:
            chosen = max(page.modals, key=lambda u: 2 if "2160p" in u else 1 if "1080p" in u else 0)
            modal = PageMetadata(self._page(urljoin(self.origin, chosen)))
            urls = modal.downloads
        # Never derive a paid/HD rendition by changing a preview URL.
        urls = [u for u in urls if urlparse(u).scheme == "https"
                and urlparse(u).netloc == "assets.mixkit.co" and urlparse(u).path.endswith(".mp4")]
        if not urls:
            raise ValueError("mixkit_missing_download_link")
        candidate.url = urls[0]
        candidate.description = video.get("name", candidate.description)
        candidate.thumbnail = video.get("thumbnailUrl", "")
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?", video.get("duration", ""))
        if match:
            h, m, s = (float(v or 0) for v in match.groups())
            candidate.duration = h * 3600 + m * 60 + s
        creator = re.search(r"created by (.*?) that you can", video.get("description", ""))
        candidate.creator_name = creator[1] if creator else ""
        candidate.license_id = "Mixkit Stock Video Free License"
        candidate.license_url = self.origin + "/license/#videoFree"
        candidate.rights_status = "reviewed_allowed"
        return candidate
