"""청중 대화 기록을 사용자(세션)별 폴더에 남긴다.

지금까지 대화는 메모리에만 있었다(Session 객체, 서버 재시작하면 사라짐).
발표장에서 청중이 무엇을 물었는지 나중에 살펴보려면 디스크에 남겨야 한다.

폴더 하나 = 사용자 하나다. session_key 는 main.py 가 이미 만든다.
  프론트가 session_id 를 보내면    "sid:<브라우저별 고유 ID>"
  안 보내면(구버전 등)            "ip:<접속 주소>"

이 키를 그대로 폴더 이름으로 쓰지 않는다. 콜론(:)은 Windows 폴더명에
쓸 수 없고, IP 주소의 점(.)도 섞이면 폴더 이름이 지저분해진다.
_safe_folder_name 이 사람이 봐도 알아볼 수 있는 형태로 바꾼다.
  "sid:1a2b3c-..."   -> "sid_1a2b3c-..."
  "ip:192.168.0.190" -> "ip_192-168-0-190"

폴더 안에 두 파일을 쓴다.
  log.jsonl       구조화된 기록. 나중에 스크립트로 다시 분석하려면 이걸 쓴다.
  transcript.md   사람이 바로 읽을 수 있는 대화록.

이 데이터는 청중 개인의 질문 내용이라 git 에 올리지 않는다(.gitignore 처리).
"""

from __future__ import annotations

import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path

from backend.app.schemas import ChatResponse

# 세션마다 같은 폴더에 동시에 쓸 일은 거의 없지만(한 사람이 한 번에 한
# 메시지만 보낸다), 서로 다른 세션의 쓰기가 겹쳐도 파일 핸들이 꼬이지
# 않도록 프로세스 전체에서 하나의 잠금을 쓴다. 트래픽 규모가 발표장
# 청중 수준이라 이걸로 충분하다.
_write_lock = threading.Lock()


def _safe_folder_name(session_key: str) -> str:
    name = re.sub(r"[^0-9A-Za-z._-]", "_", session_key)
    return name[:150] or "unknown"


def _source_summaries(response: ChatResponse) -> list[dict]:
    return [
        {
            "index": source.index,
            "title": source.title,
            "url": source.url,
            "kind": source.kind,
        }
        for source in response.sources
    ]


def log_turn(conversations_dir: Path, session_key: str, question: str, response: ChatResponse) -> None:
    """한 번의 질문-답변을 그 사용자의 폴더에 덧붙인다."""
    folder = conversations_dir / _safe_folder_name(session_key)
    now = datetime.now(UTC).isoformat(timespec="seconds")

    entry = {
        "timestamp": now,
        "question": question,
        "response_type": response.response_type,
        "answer": response.answer,
        "grounded": response.grounded,
        "sources": _source_summaries(response),
        "clarification_options": [o.label for o in response.clarification_options],
    }

    transcript_block = [f"## {now}", "", f"**질문**: {question}", "", f"**답변** ({response.response_type})", "", response.answer]
    if response.clarification_options:
        transcript_block += ["", "선택지: " + ", ".join(o.label for o in response.clarification_options)]
    if response.sources:
        transcript_block += ["", "근거:"]
        transcript_block += [f"- [{s.index}] {s.title}" for s in response.sources]
    transcript_block += ["", "---", ""]

    with _write_lock:
        folder.mkdir(parents=True, exist_ok=True)

        jsonl_path = folder / "log.jsonl"
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        transcript_path = folder / "transcript.md"
        is_new = not transcript_path.exists()
        with transcript_path.open("a", encoding="utf-8") as f:
            if is_new:
                f.write(f"# 대화 기록 — {session_key}\n\n")
            f.write("\n".join(transcript_block) + "\n")
