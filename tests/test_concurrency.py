import asyncio
from pathlib import Path

from wechat_media_downloader import downloader
from wechat_media_downloader.models import DownloadResult


def test_download_many_processes_articles_concurrently(
    monkeypatch, tmp_path: Path
) -> None:
    active = 0
    peak = 0

    async def fake_download_article(client, url, output_root, *args, **kwargs):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return DownloadResult(url=url, output_dir=output_root)

    monkeypatch.setattr(downloader, "download_article", fake_download_article)
    results = asyncio.run(
        downloader.download_many(
            ["https://mp.weixin.qq.com/s/one", "https://mp.weixin.qq.com/s/two"],
            tmp_path,
            article_concurrency=2,
        )
    )

    assert peak == 2
    assert len(results) == 2
