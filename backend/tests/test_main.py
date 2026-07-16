import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import Mock

import httpx
import pytest
from backend.app import main
from backend.app.domain import TextChunk
from backend.app.index_manifest import (
    IndexCompatibility,
    build_index_manifest,
    build_index_signature,
    write_index_manifest,
)
from backend.app.schemas import ChatResponse
from backend.app.vector_store import ChromaVectorStore
from openai import APIConnectionError


def api_request(
    method: str,
    path: str,
    *,
    raise_app_exceptions: bool = True,
    **kwargs,
) -> httpx.Response:
    async def send() -> httpx.Response:
        transport = httpx.ASGITransport(
            app=main.app,
            raise_app_exceptions=raise_app_exceptions,
        )
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(send())


def test_live_reports_process_without_checking_index(monkeypatch) -> None:
    compatibility_check = Mock(side_effect=AssertionError("index must not be opened"))
    monkeypatch.setattr(main, "get_index_compatibility", compatibility_check)

    response = api_request("GET", "/api/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}
    compatibility_check.assert_not_called()


def compatibility(reason: str) -> IndexCompatibility:
    compatible = reason == "compatible"
    indexed_chunks = 0 if reason in {"empty_index", "index_unavailable"} else 3
    return IndexCompatibility(
        compatible=compatible,
        reason=reason,
        indexed_chunks=indexed_chunks,
        fingerprint="a" * 64 if compatible else None,
        generation="2026-07-15T00:00:00+00:00" if compatible else None,
    )


def test_index_compatibility_maps_store_open_failure_to_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "get_vector_store",
        Mock(side_effect=OSError("store unavailable")),
    )

    result = main.get_index_compatibility()

    assert result == IndexCompatibility(
        compatible=False,
        reason="index_unavailable",
        indexed_chunks=0,
    )


@pytest.mark.parametrize(
    ("provider", "key", "reason", "expected"),
    [
        ("openai", None, "compatible", "needs_configuration"),
        ("local", None, "index_unavailable", "unavailable"),
        ("local", None, "empty_index", "needs_index"),
        ("local", None, "content_mismatch", "needs_reindex"),
        ("local", None, "compatible", "ready"),
        ("openai", "test-key", "compatible", "ready"),
    ],
)
def test_health_status_matrix(monkeypatch, provider, key, reason, expected) -> None:
    settings = replace(main.settings, ai_provider=provider, openai_api_key=key)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main,
        "get_index_compatibility",
        lambda: compatibility(reason),
        raising=False,
    )

    response = api_request("GET", "/api/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == expected
    assert payload["index_reason"] == reason
    assert payload["index_compatible"] is (reason == "compatible")
    assert payload["openai_configured"] is bool(key)
    assert payload["indexed_chunks"] == compatibility(reason).indexed_chunks
    assert "fingerprint" not in payload
    assert "raw_posts_sha256" not in payload


def test_chat_returns_503_when_topic_catalog_is_missing(monkeypatch) -> None:
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    catalog_loader = Mock(side_effect=FileNotFoundError("topic rules missing"))
    configuration_check = Mock(side_effect=AssertionError("config must not be checked"))
    compatibility_check = Mock(side_effect=AssertionError("index must not be checked"))
    service_factory = Mock(side_effect=AssertionError("service must not be created"))
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "load_topic_catalog", catalog_loader)
    monkeypatch.setattr(main, "selected_provider_name", configuration_check)
    monkeypatch.setattr(main, "get_index_compatibility", compatibility_check)
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = api_request(
        "POST",
        "/api/chat",
        json={"question": "최근 공지 알려줘"},
        raise_app_exceptions=False,
    )

    assert response.status_code == 503
    assert "주제 규칙" in response.json()["detail"]
    assert "확인" in response.json()["detail"]
    catalog_loader.assert_called_once_with(settings.topic_rules_path)
    configuration_check.assert_not_called()
    compatibility_check.assert_not_called()
    service_factory.assert_not_called()


@pytest.mark.parametrize(
    "catalog_failure",
    [
        json.JSONDecodeError("invalid json", "topic_rules.json", 0),
        ValueError("invalid topic rules"),
    ],
    ids=["malformed-json", "invalid-catalog"],
)
def test_chat_returns_503_when_topic_catalog_is_malformed_or_invalid(
    monkeypatch, catalog_failure
) -> None:
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    catalog_loader = Mock(side_effect=catalog_failure)
    configuration_check = Mock(side_effect=AssertionError("config must not be checked"))
    compatibility_check = Mock(side_effect=AssertionError("index must not be checked"))
    service_factory = Mock(side_effect=AssertionError("service must not be created"))
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "load_topic_catalog", catalog_loader)
    monkeypatch.setattr(main, "selected_provider_name", configuration_check)
    monkeypatch.setattr(main, "get_index_compatibility", compatibility_check)
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = api_request(
        "POST",
        "/api/chat",
        json={"question": "최근 공지 알려줘"},
        raise_app_exceptions=False,
    )

    assert response.status_code == 503
    assert "주제 규칙" in response.json()["detail"]
    assert "확인" in response.json()["detail"]
    catalog_loader.assert_called_once_with(settings.topic_rules_path)
    configuration_check.assert_not_called()
    compatibility_check.assert_not_called()
    service_factory.assert_not_called()


def test_chat_checks_openai_configuration_before_index(monkeypatch) -> None:
    settings = replace(main.settings, ai_provider="openai", openai_api_key=None)
    compatibility_check = Mock()
    service_factory = Mock()
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main,
        "get_index_compatibility",
        compatibility_check,
        raising=False,
    )
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = api_request(
        "POST",
        "/api/chat",
        json={
            "question": "최근 공지 알려줘",
            "confirmed_intent_key": "general.recent",
        },
    )

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]
    compatibility_check.assert_not_called()
    service_factory.assert_not_called()


@pytest.mark.parametrize(
    ("reason", "status", "message"),
    [
        ("index_unavailable", 503, "상태"),
        ("empty_index", 409, "인덱싱"),
        ("missing_manifest", 409, "--reset"),
        ("invalid_manifest", 409, "--reset"),
        ("settings_mismatch", 409, "--reset"),
        ("content_mismatch", 409, "--reset"),
        ("chunk_count_mismatch", 409, "--reset"),
    ],
)
def test_chat_blocks_incompatible_index_before_service(
    monkeypatch, reason, status, message
) -> None:
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    service_factory = Mock()
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main,
        "get_index_compatibility",
        lambda: compatibility(reason),
        raising=False,
    )
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = api_request(
        "POST",
        "/api/chat",
        json={
            "question": "최근 공지 알려줘",
            "confirmed_intent_key": "general.recent",
        },
    )

    assert response.status_code == status
    assert message in response.json()["detail"]
    service_factory.assert_not_called()


def test_chat_passes_compatible_fingerprint_to_service(monkeypatch) -> None:
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    service = Mock()
    service.ask.return_value = ChatResponse(
        answer="확인했습니다.",
        sources=[],
        grounded=False,
        suggested_questions=[],
        recent_notices=[],
    )
    service_factory = Mock(return_value=service)
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main,
        "get_index_compatibility",
        lambda: compatibility("compatible"),
        raising=False,
    )
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = api_request(
        "POST",
        "/api/chat",
        json={
            "question": "최근 공지 알려줘",
            "confirmed_intent_key": "general.recent",
        },
    )

    assert response.status_code == 200
    service_factory.assert_called_once_with(
        "a" * 64,
        "2026-07-15T00:00:00+00:00",
    )
    service.ask.assert_called_once_with(
        "최근 공지 알려줘",
        confirmed_intent_key="general.recent",
    )


def test_chat_preserves_openai_api_error_mapping(monkeypatch) -> None:
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    service = Mock()
    service.ask.side_effect = APIConnectionError(
        request=httpx.Request("POST", "https://example.com")
    )
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(
        main,
        "get_index_compatibility",
        lambda: compatibility("compatible"),
        raising=False,
    )
    monkeypatch.setattr(main, "get_rag_service", Mock(return_value=service))

    response = api_request(
        "POST",
        "/api/chat",
        json={
            "question": "최근 공지 알려줘",
            "confirmed_intent_key": "general.recent",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "OpenAI API 요청에 실패했습니다."


def test_chat_free_text_returns_clarification_without_provider_or_index(monkeypatch) -> None:
    settings = replace(main.settings, ai_provider="openai", openai_api_key=None)
    compatibility_check = Mock(side_effect=AssertionError("index must not be checked"))
    vector_store_factory = Mock(side_effect=AssertionError("store must not open"))
    provider_factory = Mock(side_effect=AssertionError("provider must not be created"))
    service_factory = Mock(side_effect=AssertionError("service must not be created"))
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "get_index_compatibility", compatibility_check)
    monkeypatch.setattr(main, "get_vector_store", vector_store_factory)
    monkeypatch.setattr(main, "create_provider", provider_factory)
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = api_request(
        "POST",
        "/api/chat",
        json={"question": "최근 수강신청 공지를 알려줘"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["response_type"] == "clarification"
    assert payload["answer"] == (
        "질문 의도를 이렇게 이해했습니다. 무엇을 찾을지 선택해 주세요."
    )
    assert payload["grounded"] is False
    assert payload["sources"] == []
    assert payload["suggested_questions"] == []
    assert payload["recent_notices"] == []
    assert payload["interpreted_intent"] == {
        "topic_key": "registration",
        "intent_key": "registration.main",
        "label": "일반 수강신청 일정과 공지",
        "example": "2026학년도 수강신청 일정과 유의사항",
    }
    assert [option["intent_key"] for option in payload["clarification_options"]] == [
        "registration.main",
        "registration.change",
        "registration.course_basket",
    ]
    assert all(
        set(option) == {"topic_key", "intent_key", "label", "example"}
        for option in payload["clarification_options"]
    )
    compatibility_check.assert_not_called()
    vector_store_factory.assert_not_called()
    provider_factory.assert_not_called()
    service_factory.assert_not_called()


def test_chat_invalid_confirmation_returns_clarification_without_rag_calls(monkeypatch) -> None:
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    compatibility_check = Mock(side_effect=AssertionError("index must not be checked"))
    provider_factory = Mock(side_effect=AssertionError("provider must not be created"))
    service_factory = Mock(side_effect=AssertionError("service must not be created"))
    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "get_index_compatibility", compatibility_check)
    monkeypatch.setattr(main, "create_provider", provider_factory)
    monkeypatch.setattr(main, "get_rag_service", service_factory)

    response = api_request(
        "POST",
        "/api/chat",
        json={
            "question": "최근 수강신청 공지를 알려줘",
            "confirmed_intent_key": "career.general",
        },
    )

    assert response.status_code == 200
    assert response.json()["response_type"] == "clarification"
    assert response.json()["interpreted_intent"]["intent_key"] == "registration.main"
    compatibility_check.assert_not_called()
    provider_factory.assert_not_called()
    service_factory.assert_not_called()


def test_rag_service_cache_rotates_with_index_fingerprint(monkeypatch) -> None:
    settings = replace(main.settings, ai_provider="local", openai_api_key=None)
    catalogs = iter([object(), object()])
    post_batches = iter([[object()], [object()]])
    vector_stores = iter([object(), object(), object()])

    class FakeRAGService:
        def __init__(self, **kwargs) -> None:
            self.topic_catalog = kwargs["topic_catalog"]
            self.posts = kwargs["posts"]
            self.vector_store = kwargs["vector_store"]

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(main, "create_provider", lambda settings: object())
    monkeypatch.setattr(main, "get_vector_store", lambda: next(vector_stores))
    monkeypatch.setattr(main, "load_topic_catalog", lambda path: next(catalogs))
    monkeypatch.setattr(main, "load_posts", lambda path: next(post_batches))
    monkeypatch.setattr(main, "enrich_posts", lambda posts, catalog: posts)
    monkeypatch.setattr(main, "RAGService", FakeRAGService)
    main.get_topic_catalog.cache_clear()
    main.get_enriched_posts.cache_clear()
    main.get_rag_service.cache_clear()

    try:
        first = main.get_rag_service("a" * 64, "generation-1")
        same = main.get_rag_service("a" * 64, "generation-1")
        replacement = main.get_rag_service("a" * 64, "generation-2")
        second = main.get_rag_service("b" * 64, "generation-3")
    finally:
        main.get_topic_catalog.cache_clear()
        main.get_enriched_posts.cache_clear()
        main.get_rag_service.cache_clear()

    assert first is same
    assert replacement is not first
    assert replacement.vector_store is not first.vector_store
    assert replacement.topic_catalog is first.topic_catalog
    assert replacement.posts is first.posts
    assert second is not first
    assert first.topic_catalog is not second.topic_catalog
    assert first.posts is not second.posts


def test_health_reopens_collection_after_external_reset(monkeypatch, tmp_path) -> None:
    settings = replace(
        main.settings,
        ai_provider="local",
        openai_api_key=None,
        chroma_path=tmp_path / "chroma",
        chroma_collection="reset_lifecycle",
    )
    monkeypatch.setattr(main, "settings", settings)
    cache_clear = getattr(main.get_vector_store, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()

    chunk = TextChunk(
        id="kumoh:1:0",
        post_id="1",
        source="kumoh",
        title="최신 공지",
        text="최신 공지 본문",
        url="https://example.com/1",
        published_at="2026-07-15",
        chunk_index=0,
        topic_key="general",
        topic_label="전체 공지",
        is_latest_topic=True,
    )
    embedding = [[1.0] + [0.0] * (settings.embedding_dimensions - 1)]
    signature = build_index_signature(settings)
    manifest = build_index_manifest(
        signature,
        indexed_chunks=1,
        now=datetime(2026, 7, 15, 1, 0, tzinfo=UTC),
    )
    main.get_rag_service.cache_clear()

    try:
        api_store = main.get_vector_store()
        api_store.upsert([chunk], embedding)
        write_index_manifest(settings.chroma_path, manifest)
        assert main.health().status == "ready"
        initial_compatibility = main.get_index_compatibility()
        assert initial_compatibility.generation is not None
        initial_service = main.get_rag_service(
            manifest.fingerprint,
            initial_compatibility.generation,
        )

        indexing_store = ChromaVectorStore(settings.chroma_path, settings.chroma_collection)
        indexing_store.reset()
        indexing_store.upsert([chunk], embedding)
        replacement_manifest = build_index_manifest(
            signature,
            indexed_chunks=1,
            now=datetime(2026, 7, 15, 2, 0, tzinfo=UTC),
        )
        write_index_manifest(settings.chroma_path, replacement_manifest)

        result = main.health()
        assert result.status == "ready"
        assert result.index_reason == "compatible"
        replacement_compatibility = main.get_index_compatibility()
        assert replacement_compatibility.fingerprint == initial_compatibility.fingerprint
        assert replacement_compatibility.generation != initial_compatibility.generation
        assert replacement_compatibility.generation is not None
        replacement_service = main.get_rag_service(
            replacement_manifest.fingerprint,
            replacement_compatibility.generation,
        )
        assert replacement_service is not initial_service
        assert replacement_service.vector_store.count() == 1
    finally:
        main.get_rag_service.cache_clear()
        cache_clear = getattr(main.get_vector_store, "cache_clear", None)
        if cache_clear is not None:
            cache_clear()
