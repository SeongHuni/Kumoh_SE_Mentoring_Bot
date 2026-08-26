from backend.app import main
from backend.app.config import Settings


def test_openapi_documents_chat_and_health_endpoints() -> None:
    schema = main.app.openapi()

    assert schema["info"]["title"] == "SE Mentor Bot API"
    assert schema["paths"]["/api/health"]["get"]["tags"] == ["System"]
    assert schema["paths"]["/api/chat"]["post"]["tags"] == ["Chat"]
    assert "409" in schema["paths"]["/api/chat"]["post"]["responses"]


def test_get_rag_service_wires_store_and_scoring(monkeypatch, tmp_path) -> None:
    """RAGService 에 벡터 스토어와 중요도 규칙이 들어가는지 확인한다.

    전에는 topic_catalog 와 게시글 목록을 넣었다. 주제 분류로 검색 범위를
    좁히던 방식인데, 분류를 완벽히 맞혀도 Recall@5 이득이 6.3pp뿐이고
    틀리면 정답이 통째로 빠져서 뺐다. 지금은 검색 계획기가 질의를 다시 쓰고
    중요도 가중치와 다양성이 순위를 잡는다.
    """
    importance = tmp_path / "importance.json"
    importance.write_text(
        '{"recency": {"decay_per_year": 0.012, "max_decay": 0.04},'
        ' "rules": [{"name": "테스트", "match": {"title": "이정연"}, "boost": 0.05}]}',
        encoding="utf-8",
    )

    settings = Settings(
        ai_provider="local",
        openai_api_key=None,
        chat_model="test-chat",
        embedding_model="test-embedding",
        chroma_path=tmp_path / "chroma",
        chroma_collection="test_posts",
        chroma_url=None,
        importance_path=importance,
        session_ttl_seconds=1800,
        raw_posts_path=tmp_path / "posts.json",
        topic_rules_path=tmp_path / "topic_rules.json",
        rag_top_k=7,
        rag_min_score=0.0,
        crawler_delay_seconds=0.0,
        crawler_timeout_seconds=1.0,
        seboard_api_url=None,
        seboard_headless=False,
        cors_origins=("http://testserver",),
    )
    provider = object()
    vector_store = object()

    class FakeRAGService:
        def __init__(self, **kwargs) -> None:
            self.provider = kwargs["provider"]
            self.vector_store = kwargs["vector_store"]
            self.top_k = kwargs["top_k"]
            self.scoring = kwargs["scoring"]

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "create_provider", lambda settings: provider)
    monkeypatch.setattr(main, "get_vector_store", lambda: vector_store)
    monkeypatch.setattr(main, "RAGService", FakeRAGService)
    main.get_rag_service.cache_clear()

    try:
        service = main.get_rag_service()
    finally:
        main.get_rag_service.cache_clear()

    assert isinstance(service, FakeRAGService)
    assert service.provider is provider
    assert service.vector_store is vector_store
    assert service.top_k == 7
    assert len(service.scoring.rules) == 1
    assert service.scoring.recency["decay_per_year"] == 0.012
