from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from backend.app.config import REPOSITORY_ROOT, get_settings
from backend.app.crawling.kumoh_static import KumohStaticCrawler
from backend.app.crawling.seboard import SeBoardCrawler
from backend.app.domain import BoardPost
from backend.app.storage import deduplicate_posts, save_posts


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "날짜는 YYYY-MM-DD 형식이어야 합니다."
        ) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="공개 게시글을 JSON으로 수집합니다.")
    parser.add_argument(
        "--kumoh-limit",
        type=int,
        default=0,
        help="학과 게시판 수집 건수(현재 정책상 0만 허용)",
    )
    parser.add_argument(
        "--kumoh-all",
        action="store_true",
        help="현재 정책상 허용되지 않는 과거 학과 게시판 전체 수집 옵션",
    )
    parser.add_argument(
        "--kumoh-all-boards",
        action="store_true",
        help="현재 정책상 허용되지 않는 과거 학과 게시판 범위 옵션",
    )
    parser.add_argument(
        "--kumoh-static",
        action="store_true",
        help=(
            "전공소개·교육목표·교육과정·주요성과·졸업 후 진로·"
            "비식별 교수·조교 소개·동아리 소개만 수집"
        ),
    )
    parser.add_argument(
        "--kumoh-since",
        type=_parse_iso_date,
        default=None,
        metavar="YYYY-MM-DD",
        help="이 날짜(포함) 이후에 게시된 금오공대 게시글만 저장",
    )
    parser.add_argument(
        "--seboard-limit",
        type=int,
        default=0,
        help="SE 게시판 수집 건수(기본값: 0, 수집 비활성화)",
    )
    parser.add_argument(
        "--seboard-permission-confirmed",
        action="store_true",
        help="운영자 서면 허가 또는 승인된 공식 API 사용 권한을 확인했음을 명시",
    )
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
    parser.add_argument(
        "--candidate-output",
        type=Path,
        default=None,
        help="성공한 전체 수집 결과를 운영 원본 대신 저장할 후보 파일 경로",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    if args.seboard_limit > 0 and not args.seboard_permission_confirmed:
        print(
            "오류 - SE 게시판 수집에는 운영자 서면 허가 또는 승인된 공식 API가 필요합니다.",
            file=sys.stderr,
        )
        return 2
    if (
        args.allow_partial
        and args.partial_output.resolve() == settings.raw_posts_path.resolve()
    ):
        print(
            "오류 - 부분 수집 후보는 운영 RAW_POSTS_PATH와 달라야 합니다.",
            file=sys.stderr,
        )
        return 2
    if (
        args.candidate_output is not None
        and args.candidate_output.resolve() == settings.raw_posts_path.resolve()
    ):
        print(
            "오류 - 전체 수집 후보는 운영 RAW_POSTS_PATH와 달라야 합니다.",
            file=sys.stderr,
        )
        return 2

    if args.kumoh_limit > 0 or args.kumoh_all or args.kumoh_all_boards:
        print(
            "오류 - 현재 금오공대 수집 정책은 허용된 정적 안내만 지원합니다. "
            "--kumoh-static을 사용하세요.",
            file=sys.stderr,
        )
        return 2

    posts: list[BoardPost] = []
    failures: list[str] = []

    if args.kumoh_static:
        try:
            kumoh_static = KumohStaticCrawler(
                delay_seconds=settings.crawler_delay_seconds,
                timeout_seconds=settings.crawler_timeout_seconds,
            )
            collected = kumoh_static.crawl()
            posts.extend(collected)
            print(f"학과 정적 안내: {len(collected)}건 수집")
        except Exception as exc:
            failures.append(f"학과 정적 안내: {exc}")

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
    output_path = args.candidate_output or settings.raw_posts_path
    if posts and not failures:
        save_posts(posts, output_path)
        label = "후보" if args.candidate_output is not None else "운영 원본"
        print(f"총 {len(posts)}건 {label} 저장: {output_path}")
    elif posts and failures and args.allow_partial:
        partial_path = args.candidate_output or args.partial_output
        save_posts(posts, partial_path)
        print(f"부분 수집 후보 {len(posts)}건 저장: {partial_path}")

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
