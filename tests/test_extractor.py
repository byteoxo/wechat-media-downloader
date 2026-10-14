from wechat_media_downloader.downloader import (
    safe_slug,
    validate_article_url,
)
from wechat_media_downloader.extractor import (
    extract_article,
    rewrite_content,
)

SAMPLE = """<!doctype html>
<html><head>
<meta property="og:title" content="A test / article">
<meta property="og:image" content="https://mmbiz.qpic.cn/cover/0?wx_fmt=jpeg">
<meta name="author" content="Tester">
<script>var ct = "1700000000";</script>
</head><body>
<div id="js_content" style="visibility: hidden; opacity: 0">
  <img data-src="https://mmbiz.qpic.cn/a/640?wx_fmt=webp&amp;from=appmsg">
  <img src="https://mmbiz.qpic.cn/a/640?wx_fmt=webp&amp;from=appmsg">
  <video data-src="https://mpvideo.qpic.cn/movie.mp4"></video>
  <iframe data-mpvid="wxv_123" data-src="https://mp.weixin.qq.com/mp/videoplayer?action=get_mp_video"
          data-cover="https%3A%2F%2Fmmbiz.qpic.cn%2Fposter%2F0%3Fwx_fmt%3Djpeg"></iframe>
  <section style="background-image:url('https://mmbiz.qpic.cn/background/0?wx_fmt=png')"></section>
</div>
<script>var x = {url: 'http://mpvideo.qpic.cn/abc.f10002.mp4?x=1\\x26amp;y=2'};</script>
</body></html>"""


def test_extracts_metadata_deduplicates_and_classifies_assets() -> None:
    article, _ = extract_article(SAMPLE, "https://mp.weixin.qq.com/s/example")

    assert article.title == "A test / article"
    assert article.author == "Tester"
    assert article.published_at == "2023-11-14T22:13:20+00:00"
    assert [(asset.kind, asset.downloadable) for asset in article.assets] == [
        ("image", True),
        ("video", True),
        ("image", True),
        ("image", True),
        ("video", True),
        ("cover", True),
    ]
    assert "&from=appmsg" in article.assets[0].url


def test_rewrites_lazy_image_and_css_urls() -> None:
    _, content = extract_article(SAMPLE, "https://mp.weixin.qq.com/s/example")
    local = {
        "https://mmbiz.qpic.cn/a/640?wx_fmt=webp&from=appmsg": "media/001-image.webp",
        "https://mmbiz.qpic.cn/background/0?wx_fmt=png": "media/004-image.png",
    }
    rewritten = rewrite_content(
        content,
        local,
        "https://mp.weixin.qq.com/s/example",
        ["media/005-video.mp4"],
    )

    assert 'src="media/001-image.webp"' in rewritten
    assert "url('media/004-image.png')" in rewritten
    assert (
        '<video controls="" preload="metadata" src="media/005-video.mp4"></video>'
        in rewritten
    )
    assert "visibility: hidden" not in rewritten
    assert "opacity: 0" not in rewritten


def test_url_validation_and_slug() -> None:
    assert validate_article_url("https://mp.weixin.qq.com/s/abc").endswith("/abc")
    assert safe_slug("A / title", "https://mp.weixin.qq.com/s/abc").startswith(
        "A - title-"
    )
