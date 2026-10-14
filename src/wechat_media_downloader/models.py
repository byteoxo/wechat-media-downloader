from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class Asset:
    index: int
    kind: str
    url: str
    downloadable: bool = True
    local_path: str | None = None
    content_type: str | None = None
    size: int | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Article:
    source_url: str
    title: str
    author: str | None
    published_at: str | None
    assets: list[Asset] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "title": self.title,
            "author": self.author,
            "published_at": self.published_at,
            "assets": [asset.as_dict() for asset in self.assets],
        }


@dataclass(slots=True)
class DownloadResult:
    url: str
    output_dir: Path | None = None
    title: str | None = None
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.failed == 0
