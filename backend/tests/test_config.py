import pytest
from backend.app.config import get_settings


def test_default_rag_min_score_matches_local_calibration(monkeypatch) -> None:
    monkeypatch.delenv("RAG_MIN_SCORE", raising=False)
    get_settings.cache_clear()

    try:
        assert get_settings().rag_min_score == 0.10
    finally:
        get_settings.cache_clear()


def test_index_settings_have_stable_defaults(monkeypatch) -> None:
    for name in ("EMBEDDING_DIMENSIONS", "CHUNK_SIZE", "CHUNK_OVERLAP"):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    try:
        settings = get_settings()

        assert settings.embedding_dimensions == 1536
        assert settings.chunk_size == 900
        assert settings.chunk_overlap == 150
    finally:
        get_settings.cache_clear()


def test_index_settings_accept_valid_overrides(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_DIMENSIONS", "768")
    monkeypatch.setenv("CHUNK_SIZE", "1200")
    monkeypatch.setenv("CHUNK_OVERLAP", "200")
    get_settings.cache_clear()

    try:
        settings = get_settings()

        assert settings.embedding_dimensions == 768
        assert settings.chunk_size == 1200
        assert settings.chunk_overlap == 200
    finally:
        get_settings.cache_clear()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("EMBEDDING_DIMENSIONS", "255", "EMBEDDING_DIMENSIONS"),
        ("CHUNK_SIZE", "199", "CHUNK_SIZE"),
        ("CHUNK_OVERLAP", "900", "CHUNK_OVERLAP"),
        ("CHUNK_OVERLAP", "-1", "CHUNK_OVERLAP"),
        ("CHUNK_SIZE", "not-an-int", "CHUNK_SIZE"),
    ],
)
def test_index_settings_reject_invalid_values(monkeypatch, name, value, message) -> None:
    monkeypatch.setenv(name, value)
    get_settings.cache_clear()

    try:
        with pytest.raises(ValueError, match=message):
            get_settings()
    finally:
        get_settings.cache_clear()
