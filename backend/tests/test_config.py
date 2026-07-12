from backend.app.config import get_settings


def test_default_rag_min_score_matches_local_calibration(monkeypatch) -> None:
    monkeypatch.delenv("RAG_MIN_SCORE", raising=False)
    get_settings.cache_clear()

    try:
        assert get_settings().rag_min_score == 0.09
    finally:
        get_settings.cache_clear()
