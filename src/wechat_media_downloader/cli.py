from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .downloader import download_many


def _positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wechat-media-download",
        description="Download media from one or more public WeChat Official Account articles.",
    )
    parser.add_argument("urls", nargs="*", help="mp.weixin.qq.com article URL(s)")
    parser.add_argument(
        "-i", "--input", type=Path, help="text file containing one URL per line"
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("downloads"),
        help="output directory (default: downloads)",
    )
    parser.add_argument(
        "-c",
        "--concurrency",
        type=_positive,
        default=4,
        help="articles processed concurrently (default: 4)",
    )
    parser.add_argument(
        "--asset-concurrency",
        type=_positive,
        default=8,
        help="downloads per article (default: 8)",
    )
    parser.add_argument(
        "--retries",
        type=int,
        choices=range(6),
        default=2,
        metavar="0-5",
        help="retry count (default: 2)",
    )
    parser.add_argument(
        "--max-asset-mb",
        type=_positive,
        default=500,
        help="maximum size of one asset (default: 500)",
    )
    return parser


def _collect_urls(
    arguments: argparse.Namespace, parser: argparse.ArgumentParser
) -> list[str]:
    urls: list[str] = list(arguments.urls)
    if arguments.input:
        try:
            lines = arguments.input.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            parser.error(f"cannot read {arguments.input}: {exc}")
        urls.extend(
            line.strip()
            for line in lines
            if line.strip() and not line.lstrip().startswith("#")
        )
    urls = list(dict.fromkeys(urls))
    if not urls:
        parser.error("provide at least one URL or use --input")
    return urls


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    urls = _collect_urls(arguments, parser)
    results = asyncio.run(
        download_many(
            urls,
            arguments.output,
            article_concurrency=arguments.concurrency,
            asset_concurrency=arguments.asset_concurrency,
            retries=arguments.retries,
            max_asset_bytes=arguments.max_asset_mb * 1024 * 1024,
        )
    )

    unsuccessful = 0
    for result in results:
        if result.error:
            unsuccessful += 1
            print(f"ERROR  {result.url}\n       {result.error}", file=sys.stderr)
            continue
        if result.failed:
            unsuccessful += 1
        status = "OK" if result.ok else "PARTIAL"
        print(
            f"{status:<7}{result.title}\n"
            f"       {result.downloaded} downloaded, {result.skipped} embeds recorded, "
            f"{result.failed} failed -> {result.output_dir}"
        )
    raise SystemExit(1 if unsuccessful else 0)


if __name__ == "__main__":
    main()
