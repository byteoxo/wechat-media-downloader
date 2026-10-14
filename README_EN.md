# WeChat Media Downloader

English | [简体中文](README.md)

A small, concurrent Python CLI for archiving media from public WeChat Official
Account articles (`mp.weixin.qq.com`). It uses `uv` for dependency and project
management.

For each article it saves:

- every discoverable inline image, animated GIF, audio file, and direct video;
- the cover image and video poster images;
- a readable offline `article.html` with local media links;
- the untouched response as `original.html`;
- `metadata.json`, including source URLs, local filenames, sizes, content types,
  failures, and embeds that could not be downloaded directly.

Native WeChat article videos are downloaded at the highest quality exposed by
the public article page. Embedded players that do not expose a public media URL
are preserved in the manifest as `embed` entries.

## Install

```bash
uv sync
```

No browser or browser driver is required.

## Usage

Download one article:

```bash
uv run wechat-media-download \
  "https://mp.weixin.qq.com/s/m_LqhFwiy-NSYe_xAKpQcg"
```

Download several articles concurrently:

```bash
uv run wechat-media-download URL_1 URL_2 URL_3 \
  --output downloads \
  --concurrency 3
```

Or read URLs from a file (blank lines and lines beginning with `#` are ignored):

```bash
uv run wechat-media-download --input urls.txt --output downloads
```

Useful options:

```text
-o, --output PATH          Output root (default: downloads)
-c, --concurrency N        Articles processed at once (default: 4)
--asset-concurrency N      Media requests per article (default: 8)
--retries 0-5              Retry count (default: 2)
--max-asset-mb N           Per-file size limit (default: 500)
```

The command exits with status `1` if an article or downloadable asset fails;
successful articles are still retained. Re-running the same URL uses the same
article folder and safely replaces files with matching names.

## Output layout

```text
downloads/
└── Article title-a1b2c3d4/
    ├── article.html
    ├── original.html
    ├── metadata.json
    └── media/
        ├── 001-image.jpg
        ├── 002-video.mp4
        └── ...
```

## Development

```bash
uv run pytest
```

Only download content you are authorized to archive. WeChat can rate-limit or
show a verification page after aggressive request volumes; keep concurrency at
a reasonable level.
