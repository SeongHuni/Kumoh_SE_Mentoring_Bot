"""기타_검토_체크리스트.md 에서 사용자가 [x]로 체크한 게시글을 _removed/ 로 이동한다.

사용법:
    python apply_review.py
"""

import re
import sys
from pathlib import Path

BOARD_ROOT = Path("se게시판 data")
CHECKLIST_PATH = BOARD_ROOT / "기타_검토_체크리스트.md"

ROW_RE = re.compile(
    r"^\|\s*-\s*\[( |x|X)\]\s*\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|"
)


def parse_checked_rows(checklist_path: Path):
    checked = []
    for line in checklist_path.read_text(encoding="utf-8").splitlines():
        m = ROW_RE.match(line)
        if not m:
            continue
        checked_mark, article_no, period_folder = m.groups()
        if checked_mark.lower() == "x":
            checked.append((int(article_no), period_folder.strip()))
    return checked


def run() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

    if not CHECKLIST_PATH.exists():
        print(f"체크리스트 파일을 찾을 수 없습니다: {CHECKLIST_PATH}")
        sys.exit(1)

    checked = parse_checked_rows(CHECKLIST_PATH)
    print(f"체크된 항목 {len(checked)}건 발견")

    moved = 0
    skipped = 0
    for article_no, period_folder in checked:
        src = BOARD_ROOT / period_folder / "posts" / f"{article_no}.json"
        if not src.exists():
            print(f"  ⚠ 원본 파일 없음 (이미 이동됐을 수 있음): {src}")
            skipped += 1
            continue
        dest_dir = BOARD_ROOT / "_removed" / period_folder
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        src.rename(dest)
        print(f"  이동: {src} -> {dest}")
        moved += 1

    print()
    print(f"완료: {moved}건 이동, {skipped}건 건너뜀")


if __name__ == "__main__":
    run()
