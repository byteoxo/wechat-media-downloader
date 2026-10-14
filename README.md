# WeChat Media Downloader

[English](README_EN.md) | 简体中文

一个用于归档微信公众号公开文章媒体资源的轻量级 Python 命令行工具，支持并发处理多个
`mp.weixin.qq.com` 文章链接，并使用 `uv` 管理项目和依赖。

每篇文章都会保存：

- 正文中可发现的所有图片、GIF 动图、音频和可直接下载的视频；
- 文章封面和视频封面；
- 媒体链接已替换为本地路径、可离线阅读的 `article.html`；
- 未经修改的原始响应 `original.html`；
- `metadata.json`，其中包含源地址、本地文件名、文件大小、内容类型、下载错误，以及无法直接下载的嵌入内容。

对于微信公众号原生视频，工具会下载公开文章页面提供的最高画质版本。未公开媒体直链的
播放器会作为 `embed` 条目记录在清单中，不会被静默忽略。

## 安装

```bash
uv sync
```

无需安装浏览器或浏览器驱动。

## 使用方法

下载单篇文章：

```bash
uv run wechat-media-download \
  "https://mp.weixin.qq.com/s/m_LqhFwiy-NSYe_xAKpQcg"
```

并发下载多篇文章：

```bash
uv run wechat-media-download URL_1 URL_2 URL_3 \
  --output downloads \
  --concurrency 3
```

也可以从文本文件读取链接。空行以及以 `#` 开头的行会被忽略：

```bash
uv run wechat-media-download --input urls.txt --output downloads
```

常用选项：

```text
-o, --output PATH          输出目录（默认：downloads）
-c, --concurrency N        同时处理的文章数（默认：4）
--asset-concurrency N      每篇文章同时下载的媒体数（默认：8）
--retries 0-5              重试次数（默认：2）
--max-asset-mb N           单个资源的大小上限（默认：500 MB）
```

如果任意文章或可下载资源处理失败，命令会以状态码 `1` 退出；已成功下载的文章仍会保留。
重复运行同一链接时会使用同一个文章目录，并安全替换同名文件。

## 输出结构

```text
downloads/
└── 文章标题-a1b2c3d4/
    ├── article.html
    ├── original.html
    ├── metadata.json
    └── media/
        ├── 001-image.jpg
        ├── 002-video.mp4
        └── ...
```

## 开发

```bash
uv run pytest
```

请仅下载你有权归档的内容。请求过于频繁时，微信可能会限制访问或显示验证页面，因此请将
并发数设置在合理范围内。
