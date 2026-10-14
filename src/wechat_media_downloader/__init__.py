def hello() -> str:
    return "Hello from wechat-media-downloader!"


"""Download media assets from public WeChat Official Account articles."""

from .downloader import download_many

__all__ = ["download_many"]
