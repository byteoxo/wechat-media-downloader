from __future__ import annotations

import asyncio
import hashlib
import html
import json
import mimetypes
import os
import re
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx

from .extractor import ExtractionError, extract_article, rewrite_content
from .models import Article, Asset, DownloadResult

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}
_CONTENT_EXTENSIONS = {
    "image/avif": ".avif",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "audio/aac": ".aac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
}


def validate_article_url(url: str) -> str:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or host not in {
        "mp.weixin.qq.com",
        "weixin.qq.com",
    }:
        raise ValueError(f"not a supported WeChat article URL: {url}")
    return url.strip()


def safe_slug(value: str, source_url: str) -> str:
    value = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")[:80].strip(" .-")
    if not value:
        value = "wechat-article"
    digest = hashlib.sha256(source_url.encode()).hexdigest()[:8]
    return f"{value}-{digest}"


def _extension(asset: Asset, content_type: str | None) -> str:
    normalized = (content_type or "").split(";", 1)[0].lower()
    if normalized in _CONTENT_EXTENSIONS:
        return _CONTENT_EXTENSIONS[normalized]
    query_format = parse_qs(urlparse(asset.url).query).get("wx_fmt", [""])[0].lower()
    if query_format in {"jpeg", "jpg", "png", "gif", "webp", "avif"}:
        return ".jpg" if query_format == "jpeg" else f".{query_format}"
    suffix = Path(urlparse(asset.url).path).suffix.lower()
    if 1 < len(suffix) <= 6:
        return suffix
    guessed = mimetypes.guess_extension(normalized) if normalized else None
    return guessed or {
        "image": ".img",
        "cover": ".img",
        "video": ".mp4",
        "audio": ".mp3",
    }.get(asset.kind, ".bin")


async def _get_with_retries(
    client: httpx.AsyncClient, url: str, referer: str, retries: int
) -> httpx.Response:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await client.get(url, headers={"Referer": referer})
            response.raise_for_status()
            return response
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            last_error = exc
            if attempt < retries:
                await asyncio.sleep(0.5 * (2**attempt))
    assert last_error is not None
    raise last_error


async def _download_asset(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    asset: Asset,
    media_dir: Path,
    referer: str,
    retries: int,
    max_asset_bytes: int,
) -> None:
    if not asset.downloadable:
        return
    async with semaphore:
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            temporary: Path | None = None
            try:
                async with client.stream(
                    "GET", asset.url, headers={"Referer": referer}
                ) as response:
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > max_asset_bytes:
                        raise ValueError(
                            f"asset exceeds limit of {max_asset_bytes} bytes"
                        )
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .lower()
                    )
                    if content_type in {"text/html", "application/json"}:
                        raise ValueError(f"media URL returned {content_type}")
                    extension = _extension(asset, content_type)
                    filename = f"{asset.index:03d}-{asset.kind}{extension}"
                    destination = media_dir / filename
                    temporary = destination.with_suffix(destination.suffix + ".part")
                    size = 0
                    with temporary.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > max_asset_bytes:
                                raise ValueError(
                                    f"asset exceeds limit of {max_asset_bytes} bytes"
                                )
                            output.write(chunk)
                os.replace(temporary, destination)
                asset.local_path = f"media/{filename}"
                asset.content_type = content_type or None
                asset.size = size
                return
            except (OSError, ValueError, httpx.HTTPError) as exc:
                last_error = exc
                if temporary:
                    temporary.unlink(missing_ok=True)
                if attempt < retries:
                    await asyncio.sleep(0.5 * (2**attempt))
        assert last_error is not None
        asset.error = str(last_error)


def _offline_html(article: Article, body: str) -> str:
    safe_title = html.escape(article.title)
    byline = html.escape(
        " · ".join(value for value in (article.author, article.published_at) if value)
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <style>
    body {{ color: #202124; font-family: system-ui, sans-serif; line-height: 1.75; margin: 0 auto; max-width: 760px; padding: 32px 20px; }}
    img, video {{ height: auto; max-width: 100%; }}
    .archive-meta {{ color: #687078; margin-bottom: 2rem; }}
  </style>
</head>
<body>
  <h1>{safe_title}</h1>
  <p class="archive-meta">{byline}</p>
  {body}
</body>
</html>
"""


async def download_article(
    client: httpx.AsyncClient,
    url: str,
    output_root: Path,
    asset_concurrency: int = 8,
    retries: int = 2,
    max_asset_bytes: int = 500 * 1024 * 1024,
) -> DownloadResult:
    result = DownloadResult(url=url)
    try:
        url = validate_article_url(url)
        response = await _get_with_retries(client, url, url, retries)
        article, content = extract_article(response.text, str(response.url))
        article.source_url = url
        article_dir = output_root / safe_slug(article.title, url)
        media_dir = article_dir / "media"
        media_dir.mkdir(parents=True, exist_ok=True)
        (article_dir / "original.html").write_text(response.text, encoding="utf-8")

        semaphore = asyncio.Semaphore(asset_concurrency)
        await asyncio.gather(
            *(
                _download_asset(
                    client,
                    semaphore,
                    asset,
                    media_dir,
                    str(response.url),
                    retries,
                    max_asset_bytes,
                )
                for asset in article.assets
            )
        )

        local_by_url = {
            asset.url: asset.local_path for asset in article.assets if asset.local_path
        }
        native_video_paths = [
            asset.local_path
            for asset in article.assets
            if asset.kind == "video"
            and asset.local_path
            and "mpvideo.qpic.cn" in asset.url
        ]
        rewritten = rewrite_content(
            content, local_by_url, str(response.url), native_video_paths
        )
        (article_dir / "article.html").write_text(
            _offline_html(article, rewritten), encoding="utf-8"
        )
        (article_dir / "metadata.json").write_text(
            json.dumps(article.as_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        result.output_dir = article_dir
        result.title = article.title
        result.downloaded = sum(
            asset.local_path is not None for asset in article.assets
        )
        result.skipped = sum(not asset.downloadable for asset in article.assets)
        result.failed = sum(
            asset.downloadable and asset.error is not None for asset in article.assets
        )
    except (ExtractionError, ValueError, OSError, httpx.HTTPError) as exc:
        result.error = str(exc)
    return result


async def download_many(
    urls: list[str],
    output_root: Path,
    article_concurrency: int = 4,
    asset_concurrency: int = 8,
    retries: int = 2,
    max_asset_bytes: int = 500 * 1024 * 1024,
) -> list[DownloadResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    article_semaphore = asyncio.Semaphore(article_concurrency)
    limits = httpx.Limits(
        max_connections=max(20, article_concurrency * asset_concurrency)
    )
    timeout = httpx.Timeout(60.0, connect=20.0)
    async with httpx.AsyncClient(
        headers=HEADERS,
        follow_redirects=True,
        timeout=timeout,
        limits=limits,
        http2=True,
    ) as client:

        async def run(url: str) -> DownloadResult:
            async with article_semaphore:
                return await download_article(
                    client,
                    url,
                    output_root,
                    asset_concurrency,
                    retries,
                    max_asset_bytes,
                )

        return list(await asyncio.gather(*(run(url) for url in urls)))
