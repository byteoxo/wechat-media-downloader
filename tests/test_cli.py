from pathlib import Path

import pytest

from wechat_media_downloader.cli import _collect_urls, build_parser


def test_collects_deduplicated_urls_from_args_and_file(tmp_path: Path) -> None:
    input_file = tmp_path / "urls.txt"
    input_file.write_text(
        "# comment\nhttps://mp.weixin.qq.com/s/two\n", encoding="utf-8"
    )
    parser = build_parser()
    arguments = parser.parse_args(
        ["https://mp.weixin.qq.com/s/one", "-i", str(input_file)]
    )

    assert _collect_urls(arguments, parser) == [
        "https://mp.weixin.qq.com/s/one",
        "https://mp.weixin.qq.com/s/two",
    ]


def test_rejects_non_wechat_urls() -> None:
    from wechat_media_downloader.downloader import validate_article_url

    with pytest.raises(ValueError):
        validate_article_url("https://example.com/article")
