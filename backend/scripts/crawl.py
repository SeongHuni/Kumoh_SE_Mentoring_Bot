from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.app.config import REPOSITORY_ROOT, get_settings
from backend.app.crawling.kumoh import KumohBoardCrawler
from backend.app.crawling.seboard import SeBoardCrawler
from backend.app.domain import BoardPost
from backend.app.storage import deduplicate_posts, save_posts


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공개 게시글을 JSON으로 수집합니다.")
    parser.add_argument("--kumoh-limit", type=int, default=50)
    parser.add_argument("--seboard-limit", type=int, default=50)
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="실패한 수집의 일부 결과를 후보 파일에 저장",
    )
    parser.add_argument(
        "--partial-output",
        type=Path,
        default=REPOSITORY_ROOT / "data" / "raw" / "candidates" / "posts-partial.json",
        help="부분 수집 후보 파일 경로",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    if (
        args.allow_partial
        and args.partial_output.resolve() == settings.raw_posts_path.resolve()
    ):
        print(
            "오류 - 부분 수집 후보는 운영 RAW_POSTS_PATH와 달라야 합니다.",
            file=sys.stderr,
        )
        return 2

    posts: list[BoardPost] = []
    failures: list[str] = []

    if args.kumoh_limit > 0:
        try:
            kumoh = KumohBoardCrawler(
                delay_seconds=settings.crawler_delay_seconds,
                timeout_seconds=settings.crawler_timeout_seconds,
            )
            collected = kumoh.crawl(args.kumoh_limit)
            posts.extend(collected)
            print(f"학과 게시판: {len(collected)}건 수집")
        except Exception as exc:
            failures.append(f"학과 게시판: {exc}")

    if args.seboard_limit > 0:
        try:
            seboard = SeBoardCrawler(
                api_url=settings.seboard_api_url,
                delay_seconds=settings.crawler_delay_seconds,
                timeout_seconds=settings.crawler_timeout_seconds,
                headless=settings.seboard_headless,
            )
            collected = seboard.crawl(args.seboard_limit)
            posts.extend(collected)
            print(f"SE 게시판: {len(collected)}건 수집")
        except Exception as exc:
            failures.append(f"SE 게시판: {exc}")

    posts = deduplicate_posts(posts)
    if posts and not failures:
        save_posts(posts, settings.raw_posts_path)
        print(f"총 {len(posts)}건 저장: {settings.raw_posts_path}")
    elif posts and failures and args.allow_partial:
        save_posts(posts, args.partial_output)
        print(f"부분 수집 후보 {len(posts)}건 저장: {args.partial_output}")

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
