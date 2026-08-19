from backend.app.config import get_settings


def test_defaults_target_the_prepared_chroma_collection(monkeypatch) -> None:
    for name in (
        "EMBEDDING_API_KEY",
        "ANSWER_API_KEY",
        "EMBEDDING_MODEL",
        "ANSWER_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.chroma_path.name == "chroma-data"
    assert settings.chroma_collection == "sw_notice_d500"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.chunk_size_tokens == 500
    assert settings.chunk_overlap_tokens == 0
    assert not settings.api_keys_configured
