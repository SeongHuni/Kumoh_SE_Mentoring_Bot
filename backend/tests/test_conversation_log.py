"""사용자(세션)별 대화 기록 테스트."""

from __future__ import annotations

import json

from backend.app.conversation_log import _safe_folder_name, log_turn
from backend.app.schemas import ChatResponse, ClarificationOption


def make_response(**overrides) -> ChatResponse:
    defaults = dict(
        response_type="answer",
        answer="학생회비는 1학기당 3만원입니다[1].",
        sources=[],
        grounded=True,
        clarification_options=[],
    )
    defaults.update(overrides)
    return ChatResponse(**defaults)


def test_folder_name_strips_characters_invalid_on_windows() -> None:
    # 콜론은 Windows 폴더명에 쓸 수 없다. IP 기반 키의 점도 섞이면
    # 지저분해지지만 최소한 안전해야 한다.
    assert ":" not in _safe_folder_name("sid:abc-123")
    assert ":" not in _safe_folder_name("ip:192.168.0.190")
    assert _safe_folder_name("sid:abc-123") == "sid_abc-123"


def test_log_turn_creates_one_folder_per_session(tmp_path) -> None:
    log_turn(tmp_path, "sid:user-1", "학생회비는 얼마야?", make_response())
    log_turn(tmp_path, "sid:user-2", "캡스톤디자인 일정이 어떻게 돼?", make_response())

    folders = sorted(p.name for p in tmp_path.iterdir())
    assert folders == ["sid_user-1", "sid_user-2"]


def test_log_turn_appends_jsonl_with_sources_and_timestamp(tmp_path) -> None:
    response = make_response(
        sources=[
            {
                "index": 1,
                "title": "학생회비 납부 안내",
                "url": "https://example.com/1",
                "source": "se게시판",
                "score": 0.9,
                "kind": "notice",
            }
        ]
    )
    log_turn(tmp_path, "sid:user-1", "학생회비는 얼마야?", response)
    log_turn(tmp_path, "sid:user-1", "그럼 언제까지 내야 해?", make_response(answer="3월 15일까지입니다[1]."))

    lines = (tmp_path / "sid_user-1" / "log.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2

    first = json.loads(lines[0])
    assert first["question"] == "학생회비는 얼마야?"
    assert first["sources"] == [{"index": 1, "title": "학생회비 납부 안내", "url": "https://example.com/1", "kind": "notice"}]
    assert "timestamp" in first

    second = json.loads(lines[1])
    assert second["question"] == "그럼 언제까지 내야 해?"


def test_log_turn_writes_readable_transcript(tmp_path) -> None:
    log_turn(tmp_path, "sid:user-1", "학생회비는 얼마야?", make_response())

    transcript = (tmp_path / "sid_user-1" / "transcript.md").read_text(encoding="utf-8")
    assert "학생회비는 얼마야?" in transcript
    assert "학생회비는 1학기당 3만원입니다" in transcript


def test_log_turn_records_clarification_options(tmp_path) -> None:
    response = make_response(
        response_type="clarification",
        answer="어떤 장학금에 대해 알고 싶으신가요?",
        grounded=False,
        clarification_options=[
            ClarificationOption(topic_key="a", intent_key="aa", label="장학금 종류", example="장학금 종류"),
            ClarificationOption(topic_key="b", intent_key="bb", label="장학금 신청", example="장학금 신청 방법"),
        ],
    )
    log_turn(tmp_path, "sid:user-1", "장학금", response)

    entry = json.loads((tmp_path / "sid_user-1" / "log.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert entry["clarification_options"] == ["장학금 종류", "장학금 신청"]

    transcript = (tmp_path / "sid_user-1" / "transcript.md").read_text(encoding="utf-8")
    assert "장학금 종류, 장학금 신청" in transcript
