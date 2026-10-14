from __future__ import annotations

import html as html_module
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup, Tag

from .models import Article, Asset

_MEDIA_HOSTS = (
    "mmbiz.qpic.cn",
    "mmbiz.qlogo.cn",
    "mpvideo.qpic.cn",
    "res.wx.qq.com",
    "res2.wx.qq.com",
)
_DIRECT_EXTENSIONS = {
    ".avif",
    ".gif",
    ".jpeg",
    ".jpg",
    ".m4a",
    ".mp3",
    ".mp4",
    ".ogg",
    ".png",
    ".svg",
    ".wav",
    ".webm",
    ".webp",
}
_CSS_URL = re.compile(r"url\(\s*(['\"]?)(.*?)\1\s*\)", re.IGNORECASE)
_MP4_URL = re.compile(
    r"url:\s*(?:JsDecode\()?\s*['\"]([^'\"]+\.f\d+\.mp4[^'\"]*)['\"]",
    re.IGNORECASE,
)
_MP4_ID = re.compile(r"/([0-9A-Za-z]+)\.f\d+\.mp4", re.IGNORECASE)
_PUBLISH_TIME = re.compile(r"(?:var\s+ct\s*=|create_time:)\s*['\"]([^'\"]+)['\"]")


class ExtractionError(ValueError):
    """Raised when a response is not a usable WeChat article."""


def normalize_url(value: str, base_url: str) -> str | None:
    value = html_module.unescape(value).replace("\\x26amp;", "&").replace("\\x26", "&")
    value = value.strip().strip("'\"")
    if value.lower().startswith(("http%3a%2f%2f", "https%3a%2f%2f")):
        value = unquote(value)
    if value.startswith("//"):
        value = "https:" + value
    elif value.startswith("/"):
        value = urljoin(base_url, value)
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if (
        parsed.hostname
        and parsed.hostname.endswith(_MEDIA_HOSTS)
        and parsed.scheme == "http"
    ):
        value = "https:" + value[5:]
    return value


def _first_text(soup: BeautifulSoup, selectors: Iterable[str]) -> str | None:
    for selector in selectors:
        node = soup.select_one(selector)
        if node:
            value = (
                node.get("content")
                if node.name == "meta"
                else node.get_text(" ", strip=True)
            )
            if value and value.strip():
                return value.strip()
    return None


def _kind_for(tag: Tag, url: str) -> tuple[str, bool]:
    name = tag.name.lower()
    if name == "img":
        return "image", True
    if name in {"video", "source"}:
        return "video", True
    if name == "audio":
        return "audio", True
    if name in {"iframe", "embed"}:
        return "embed", False

    path = urlparse(url).path.lower()
    suffix = next(
        (extension for extension in _DIRECT_EXTENSIONS if path.endswith(extension)), ""
    )
    if suffix in {".mp4", ".webm"} or "mpvideo.qpic.cn" in url:
        return "video", True
    if suffix in {".mp3", ".m4a", ".ogg", ".wav"}:
        return "audio", True
    return "image", True


def _candidate_values(tag: Tag) -> Iterable[str]:
    name = tag.name.lower()
    attributes: tuple[str, ...]
    if name == "img":
        attributes = ("data-src", "data-original", "data-backsrc", "src")
    elif name in {"video", "audio", "source", "iframe", "embed"}:
        attributes = ("data-src", "data-url", "src")
    else:
        attributes = ("data-src", "data-url")

    for attribute in attributes:
        value = tag.get(attribute)
        if isinstance(value, str) and value:
            yield value

    style = tag.get("style")
    if isinstance(style, str):
        for match in _CSS_URL.finditer(style):
            yield match.group(2)


def _looks_direct(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host.endswith(_MEDIA_HOSTS):
        return True
    return any(urlparse(url).path.lower().endswith(ext) for ext in _DIRECT_EXTENSIONS)


def _native_video_urls(page_html: str) -> list[str]:
    """Choose the first (normally highest-quality) CDN variant for each video."""
    selected: dict[str, str] = {}
    for match in _MP4_URL.finditer(page_html):
        url = (
            html_module.unescape(match.group(1))
            .replace(r"\x26amp;", "&")
            .replace(r"\x26", "&")
        )
        video_id = _MP4_ID.search(url)
        if video_id:
            selected.setdefault(video_id.group(1), url)
    return list(selected.values())


def _published_time(page_html: str) -> str | None:
    match = _PUBLISH_TIME.search(page_html)
    if not match:
        return None
    value = match.group(1)
    if value.isdigit():
        return datetime.fromtimestamp(int(value), tz=UTC).isoformat()
    return value


def extract_article(page_html: str, source_url: str) -> tuple[Article, BeautifulSoup]:
    soup = BeautifulSoup(page_html, "html.parser")
    content = soup.select_one("#js_content, .rich_media_content")
    title = _first_text(
        soup,
        (
            "#activity-name",
            "meta[property='og:title']",
            "meta[name='twitter:title']",
            "title",
        ),
    )
    if not content or not title:
        if "环境异常" in page_html or "访问过于频繁" in page_html:
            raise ExtractionError(
                "WeChat returned an access-verification page; try again later"
            )
        raise ExtractionError("the page does not look like a public WeChat article")

    author = _first_text(
        soup,
        (
            "#js_name",
            "#profileBt a",
            "meta[name='author']",
            "meta[property='article:author']",
        ),
    )
    published_at = _first_text(
        soup,
        ("#publish_time", "meta[property='article:published_time']"),
    ) or _published_time(page_html)

    assets: list[Asset] = []
    seen: set[str] = set()
    native_video_urls = _native_video_urls(page_html)
    native_iframe_index = 0

    def add(
        tag: Tag, raw_url: str, force: bool = False, kind_override: str | None = None
    ) -> None:
        url = normalize_url(raw_url, source_url)
        if not url or url in seen:
            return
        kind, downloadable = _kind_for(tag, url)
        if kind_override:
            kind, downloadable = kind_override, kind_override != "embed"
        if not force and kind not in {"embed"} and not _looks_direct(url):
            return
        seen.add(url)
        assets.append(Asset(len(assets) + 1, kind, url, downloadable))

    for tag in content.find_all(True):
        native_iframe_has_direct_url = False
        if tag.name == "iframe" and (tag.get("data-mpvid") or "").startswith("wxv_"):
            native_iframe_has_direct_url = native_iframe_index < len(native_video_urls)
            native_iframe_index += 1
        if not native_iframe_has_direct_url:
            for raw_url in _candidate_values(tag):
                add(
                    tag,
                    raw_url,
                    force=tag.name.lower()
                    in {"img", "video", "audio", "source", "iframe", "embed"},
                )
        for attribute in ("data-cover", "poster"):
            cover_url = tag.get(attribute)
            if isinstance(cover_url, str) and cover_url:
                add(tag, cover_url, force=True, kind_override="image")

    for video_url in native_video_urls:
        add(content, video_url, force=True, kind_override="video")

    cover = soup.select_one("meta[property='og:image'], meta[name='twitter:image']")
    if cover and isinstance(cover.get("content"), str):
        add(cover, str(cover["content"]), force=True)
        if assets and assets[-1].url == normalize_url(
            str(cover["content"]), source_url
        ):
            assets[-1].kind = "cover"

    return Article(source_url, title, author, published_at, assets), content


def rewrite_content(
    content: Tag,
    local_by_url: dict[str, str],
    source_url: str,
    native_video_paths: list[str] | None = None,
) -> str:
    """Return the article fragment with downloadable media pointed at local files."""
    fragment = BeautifulSoup(str(content), "html.parser")
    root = fragment.select_one("#js_content, .rich_media_content")
    if root and isinstance(root.get("style"), str):
        style = re.sub(
            r"(?:visibility\s*:\s*hidden|opacity\s*:\s*0)\s*;?",
            "",
            root["style"],
            flags=re.IGNORECASE,
        )
        root["style"] = style.strip()
    native_video_paths = native_video_paths or []
    native_index = 0
    for tag in fragment.find_all(True):
        for attribute in (
            "src",
            "data-src",
            "data-original",
            "data-backsrc",
            "data-url",
        ):
            value = tag.get(attribute)
            if not isinstance(value, str):
                continue
            normalized = normalize_url(value, source_url)
            if normalized in local_by_url:
                tag[attribute] = local_by_url[normalized]
                if attribute == "data-src" and tag.name in {
                    "img",
                    "video",
                    "audio",
                    "source",
                }:
                    tag["src"] = local_by_url[normalized]

        style = tag.get("style")
        if isinstance(style, str):

            def replace(match: re.Match[str]) -> str:
                normalized = normalize_url(match.group(2), source_url)
                return (
                    f"url('{local_by_url[normalized]}')"
                    if normalized in local_by_url
                    else match.group(0)
                )

            tag["style"] = _CSS_URL.sub(replace, style)
        if (
            tag.name == "iframe"
            and (tag.get("data-mpvid") or "").startswith("wxv_")
            and native_index < len(native_video_paths)
        ):
            video = fragment.new_tag("video", controls="", preload="metadata")
            video["src"] = native_video_paths[native_index]
            cover = tag.get("data-cover")
            normalized_cover = (
                normalize_url(cover, source_url) if isinstance(cover, str) else None
            )
            if normalized_cover in local_by_url:
                video["poster"] = local_by_url[normalized_cover]
            tag.replace_with(video)
            native_index += 1
    return str(fragment)
