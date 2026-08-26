from __future__ import annotations

import argparse
import sys

from backend.app.config import get_settings
from backend.app.crawling.kumoh import KumohBoardCrawler
from backend.app.crawling.seboard import SeBoardCrawler
from backend.app.domain import BoardPost
from backend.app.storage import deduplicate_posts, save_posts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공개 게시글을 JSON으로 수집합니다.")
    parser.add_argument("--kumoh-limit", type=int, default=50)
    parser.add_argument("--seboard-limit", type=int, default=50)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="한 소스가 실패해도 수집 결과를 저장",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = get_settings()
    posts: list[BoardPost] = []
    failures: list[str] = []

    if args.kumoh_limit > 0:
        try:
            crawler = KumohBoardCrawler(
                delay_seconds=settings.crawler_delay_seconds,
                timeout_seconds=settings.crawler_timeout_seconds,
            )
            collected = crawler.crawl(args.kumoh_limit)
            posts.extend(collected)
            print(f"학과 게시판: {len(collected)}건 수집")
        except Exception as exc:
            failures.append(f"학과 게시판: {exc}")

    if args.seboard_limit > 0:
        try:
            crawler = SeBoardCrawler(
                api_url=settings.seboard_api_url,
                delay_seconds=settings.crawler_delay_seconds,
                timeout_seconds=settings.crawler_timeout_seconds,
                headless=settings.seboard_headless,
            )
            collected = crawler.crawl(args.seboard_limit)
            posts.extend(collected)
            print(f"SE 게시판: {len(collected)}건 수집")
        except Exception as exc:
            failures.append(f"SE 게시판: {exc}")

    posts = deduplicate_posts(posts)
    if posts and (not failures or args.allow_partial):
        save_posts(posts, settings.raw_posts_path)
        print(f"총 {len(posts)}건 저장: {settings.raw_posts_path}")

    if failures:
        for failure in failures:
            print(f"오류 - {failure}", file=sys.stderr)
        return 2
    if not posts:
        print("수집된 게시글이 없습니다.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
