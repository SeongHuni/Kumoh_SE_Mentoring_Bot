from backend.app.config import get_settings


def test_default_rag_min_score_is_disabled(monkeypatch) -> None:
    """점수 컷오프는 쓰지 않는다.

    근거가 부족한지는 답변 규칙이 판단하고(자료가 그 상황에 적용되는가),
    순위 조정은 중요도 가중치와 다양성이 한다. 유사도 절대값으로 자르면
    질의마다 점수 분포가 달라 기준을 정할 수 없다.
    """
    monkeypatch.delenv("RAG_MIN_SCORE", raising=False)
    get_settings.cache_clear()

    try:
        assert get_settings().rag_min_score == 0.0
    finally:
        get_settings.cache_clear()
