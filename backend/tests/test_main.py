from backend.app import main
from backend.app.config import Settings


def test_get_rag_service_injects_topic_context(monkeypatch, tmp_path) -> None:
    settings = Settings(
        ai_provider="local",
        openai_api_key=None,
        chat_model="test-chat",
        embedding_model="test-embedding",
        chroma_path=tmp_path / "chroma",
        chroma_collection="test_posts",
        raw_posts_path=tmp_path / "posts.json",
        topic_rules_path=tmp_path / "topic_rules.json",
        rag_top_k=7,
        rag_min_score=0.42,
        crawler_delay_seconds=0.0,
        crawler_timeout_seconds=1.0,
        seboard_api_url=None,
        seboard_headless=False,
        cors_origins=("http://testserver",),
    )
    provider = object()
    vector_store = object()
    catalog = object()
    posts = [object() for _ in range(46)]

    class FakeRAGService:
        def __init__(self, **kwargs) -> None:
            self.topic_catalog = kwargs["topic_catalog"]
            self.posts = kwargs["posts"]

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "create_provider", lambda settings: provider)
    monkeypatch.setattr(main, "get_vector_store", lambda: vector_store)
    monkeypatch.setattr(main, "get_topic_catalog", lambda: catalog)
    monkeypatch.setattr(main, "get_enriched_posts", lambda: posts)
    monkeypatch.setattr(main, "RAGService", FakeRAGService)
    main.get_rag_service.cache_clear()

    try:
        service = main.get_rag_service()
    finally:
        main.get_rag_service.cache_clear()

    assert isinstance(service, FakeRAGService)
    assert service.topic_catalog is catalog
    assert len(service.posts) == 46
